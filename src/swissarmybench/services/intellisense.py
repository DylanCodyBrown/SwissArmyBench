"""The Workbench editors' intelligence (the owner, 2026-11-17): the member list with its documentation
panel, a call's parameter info, the hover, and a lint as you type, for every Python editor (notebook
cells, scripts, the console) and SQL cells. The user's page and the agent alike (workbench_complete,
workbench_signature, workbench_problems).

  PYTHON   Jedi does the work: its Interpreter over the kernel's own namespace where a kernel has run
           (client/kernel_intel.py, asked in the kernel), its Script over the document's text (a
           notebook's earlier cells first) with the project folder and the document's environment
           where none has
  THE APP  where Jedi cannot see: the app's names inside strings (connections, variables with their
           source, blades, structures, a table's columns), the connections' names in code, the
           project's modules' names (completed with their import), an open table's columns after `.`
  LINT     Python's compile and a small ast pass (domain/intellisense.py); pyflakes when the app's
           Python has it; Ruff when the document's environment has it (offered once, never nagged);
           a DuckDB SQL cell by DuckDB's parser, another database's by sqlglot in its dialect

Every answer is worked out in one worker thread (never the event loop), within a second (else nothing,
quietly), and once per document version; a request superseded by a newer one from the same editor is
not worked out at all.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from swissarmybench.domain import intellisense as rules
from swissarmybench.domain import local_api as api_rules
from swissarmybench.domain.packages import missing_packages
from swissarmybench.services.workspace import NotFound, Workspace

BUDGET_SECONDS: float = 1.0
KERNEL_SECONDS: float = 0.6
KERNEL_NAMES_SECONDS: float = 3.0
MAX_CACHE: int = 200
# What `sab.` offers: the package's public calls, never its own layers.
_SAB_INTERNAL = frozenset(
    {"adapters", "bootstrap", "cli", "client", "domain", "mcp", "server", "services", "settings", "renamed",
     "starters", "stats", "annotations", "import_module", "warnings", "sys", "os", "web_static"}
)  # fmt: skip
_PREAMBLE = "import swissarmybench as sab\n"
_IN_KERNEL = "__import__('swissarmybench.client.kernel_intel', fromlist=['ask'])"


class Engine(Protocol):
    """Jedi's answers (client/kernel_intel.answer) over a Script."""

    def __call__(
        self, request: dict[str, Any], namespace: Any = None, project: Any = None, environment: Any = None
    ) -> dict[str, Any]: ...


class World(Protocol):
    def project(self, folder: str | None, extra: tuple[str, ...] = ()) -> Any: ...

    def environment(self, python: str | None) -> Any: ...


class Modules(Protocol):
    def sources(self, folder: str | None, modules: tuple[str, ...]) -> dict[str, str]: ...


class Linters(Protocol):
    def pyflakes(self, text: str) -> list[dict[str, Any]] | None: ...

    def ruff_command(self, python: str | None) -> str | None: ...

    def ruff(self, text: str, command: str, folder: str | None) -> list[dict[str, Any]] | None: ...

    def duckdb_error(self, sql: str) -> str | None: ...


class Kernel(Protocol):
    python: str

    def idle(self) -> bool: ...

    async def evaluate(self, expression: str) -> Any: ...


class Intellisense:
    def __init__(
        self,
        ws: Workspace,
        engine: Engine,
        world: World,
        modules: Modules,
        linters: Linters,
        *,
        kernel_of: Callable[[str], Kernel | None],
        project_folder: Callable[[], str | None],
        blades: Callable[[], Sequence[Mapping[str, Any]]],
        variables: Callable[[], Sequence[Mapping[str, Any]]],
        structures: Callable[[], list[str]],
        dialect_of: Callable[[str], str | None],
        read_file: Callable[[str], str],
    ) -> None:
        self.ws = ws
        self._engine = engine
        self._world = world
        self._modules = modules
        self._linters = linters
        self._kernel_of = kernel_of
        self._project_folder = project_folder
        self._blades = blades
        # The project's sandbox (services/sandbox.py): its mocked connections and its tables, for API.py.
        self.sandbox_clients: Callable[[], list[tuple[str, str]]] = lambda: []
        self.sandbox_tables: Callable[[], list[tuple[str, list[str]]]] = lambda: []
        # API.py's squiggles: each mock name's dialect and tables (services/sandbox.py mock_dialects)
        self.sandbox_mocks: Callable[[], dict[str, tuple[str, list[str]]]] = lambda: {}
        self._variables = variables
        self._structures = structures
        self._dialect_of = dialect_of
        self._read_file = read_file
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sab-intel")
        self._latest: dict[str, int] = {}
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._kernel_names: dict[str, tuple[float, list[str]]] = {}
        # What each open document's editors last showed (the page tells): the agent reads the same.
        self._problems: dict[str, dict[str, Any]] = {}

    # ===== shared =====

    def _superseded(self, body: Mapping[str, Any]) -> bool:
        editor, seq = body.get("editor"), body.get("seq")
        if not isinstance(editor, str) or not isinstance(seq, int):
            return False
        return self._latest.get(editor, -1) > seq

    def _arrived(self, body: Mapping[str, Any]) -> None:
        editor, seq = body.get("editor"), body.get("seq")
        if isinstance(editor, str) and isinstance(seq, int):
            self._latest[editor] = max(seq, self._latest.get(editor, -1))
            if len(self._latest) > 2000:
                self._latest.clear()

    async def _work(
        self, body: Mapping[str, Any], job: Callable[[], dict[str, Any]], empty: dict[str, Any]
    ) -> dict[str, Any]:
        """The job in the worker thread within the budget; nothing (quietly) when it is late or superseded."""

        def run() -> dict[str, Any]:
            return empty | {"superseded": True} if self._superseded(body) else job()

        try:
            future = asyncio.get_running_loop().run_in_executor(self._pool, run)
            return await asyncio.wait_for(future, BUDGET_SECONDS)
        except TimeoutError:
            return empty | {"late": True}
        except Exception as error:  # Jedi or a linter stumbled: the editor carries on
            return empty | {"error": f"{type(error).__name__}"}

    def _cached(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        return self._cache.get(key)

    def _keep(self, key: tuple[Any, ...], answer: dict[str, Any]) -> dict[str, Any]:
        # Not kept: a late or failed answer, and a lint without Ruff (it may be installed any moment).
        ruffless = (answer.get("ruff") or {}).get("used") is False
        if not ruffless and not any(answer.get(k) for k in ("late", "superseded", "error")):
            self._cache[key] = answer
            while len(self._cache) > MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))
        return answer

    @staticmethod
    def _text(body: Mapping[str, Any]) -> tuple[str, int, bool, list[str], list[str]]:
        text = str(body.get("text") or "")
        offset = body.get("offset")
        if not isinstance(offset, int):
            line, column = int(body.get("line") or 1), int(body.get("column") or 1)
            lines = text.split("\n")
            offset = sum(len(x) + 1 for x in lines[: line - 1]) + column - 1
        offset = max(0, min(offset, len(text)))
        before = [str(c) for c in body.get("before") or [] if isinstance(c, str)]
        after = [str(c) for c in body.get("after") or [] if isinstance(c, str)]
        return text, offset, bool(body.get("notebook")), before, after

    def _kernel(self, body: Mapping[str, Any]) -> Kernel | None:
        kid = body.get("kernel")
        if not isinstance(kid, str) or not kid:
            return None
        kernel = self._kernel_of(kid)
        return kernel if kernel is not None and kernel.idle() else None

    def _python(self, body: Mapping[str, Any]) -> str | None:
        kid = body.get("kernel")
        kernel = self._kernel_of(kid) if isinstance(kid, str) and kid else None
        if kernel is not None:
            return kernel.python
        python = body.get("python")
        return python if isinstance(python, str) and python else None

    def _jedi_request(self, ask: str, body: Mapping[str, Any], with_kernel: bool) -> dict[str, Any]:
        """Jedi's request: the kernel's (the cell alone: the namespace holds the rest), or the Script's (a
        notebook's earlier cells and the kernel's `sab` first, so their names are known)."""
        text, offset, notebook, before, _ = self._text(body)
        code = rules.to_python(text) if notebook else text
        # Jedi reads sab_api as the runtime: its import lines rewritten, never the cursor's (the line and
        # column are read from the text as typed, so they hold)
        read = code
        if not notebook and "sab_api" in code:
            read = rules.sab_api_for_jedi(code, code[:offset].count("\n"))
        head = (
            "" if with_kernel else (_PREAMBLE if notebook or "sab" not in rules.imported_names(text) else "")
        )
        if not with_kernel and before:
            head += "\n".join(rules.to_python(c) if not rules.is_cell_magic(c) else "" for c in before) + "\n"
        prefix = head + code[:offset]
        line = prefix.count("\n") + 1
        column = len(prefix) - (prefix.rfind("\n") + 1)
        path = body.get("path") if isinstance(body.get("path"), str) else None
        return {
            "ask": ask,
            "code": head + read,
            "line": line,
            "column": column,
            "path": path,
            "folder": self._project_folder(),
        }

    async def _jedi(self, ask: str, body: Mapping[str, Any], empty: dict[str, Any]) -> dict[str, Any]:
        kernel = self._kernel(body)
        if kernel is not None:
            request = self._jedi_request(ask, body, True)
            try:
                found = await asyncio.wait_for(
                    kernel.evaluate(f"{_IN_KERNEL}.ask({json.dumps(request)!r})"),
                    KERNEL_SECONDS,
                )
                answer = json.loads(found) if isinstance(found, str) else None
                if isinstance(answer, dict) and "error" not in answer:
                    return answer | {"from": "kernel"}
            except Exception:  # noqa: S110 (busy, or a Python without the package: the Script answers)
                pass
        request = self._jedi_request(ask, body, False)
        folder = self._project_folder()
        python = self._python(body)

        def job() -> dict[str, Any]:
            project = self._world.project(folder)
            return self._engine(request, project=project, environment=self._world.environment(python)) | {
                "from": "script"
            }

        return await self._work(body, job, empty)

    # ===== the member list =====

    async def complete(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{text, offset (or line and column), notebook, before (earlier cells), kernel, path, python,
        recent (labels last chosen), editor and seq}: the completions, ranked, each with its kind, its
        signature or type, its documentation (markdown) and, for a project module's name, its import."""
        body = dict(body or {})
        self._arrived(body)
        text, offset, notebook, _, _ = self._text(body)
        recent = [str(r) for r in body.get("recent") or []][:50]
        quoted = rules.quoted_context(text, offset)
        if quoted is not None:
            items = self._quoted(quoted)
            return {"items": rules.rank(items, recent), "start": quoted.start, "end": offset, "from": "app"}
        importing = rules.SAB_API_IMPORT.search(text[max(0, offset - 300) : offset])
        if importing:  # API.py's `from sab_api import |`: the runtime's own names, with their words
            typed = importing.group(1)
            items = [i for i in rules.sab_api_names() if i["label"].startswith(typed)]
            return {
                "items": rules.rank(items, recent),
                "start": offset - len(typed),
                "end": offset,
                "from": "app",
            }
        word = re.search(r"[A-Za-z_]\w*$", text[:offset])
        start = offset - len(word.group(0)) if word else offset
        dotted = re.search(r"([A-Za-z_]\w*)\.\w*$", text[:offset])
        if re.search(r"(^|[^\w])[\"']$", text[:offset]):
            return {"items": [], "start": offset, "end": offset}  # a quote just typed: nothing yet
        # Kept by the document's version (a kernel's answer is not: its namespace changes with each run).
        key = ("complete", body.get("document"), body.get("version"), offset, hash(text))
        found = self._cached(key) if body.get("version") is not None else None
        if found is None:
            found = await self._jedi("complete", body, {"items": []})
            if body.get("version") is not None and found.get("from") == "script":
                self._keep(key, found)
        items = [dict(i) for i in found.get("items") or []]
        if dotted and dotted.group(1) == "sab":
            items = [
                i for i in items if i["label"] not in _SAB_INTERNAL and not str(i["label"]).startswith("_")
            ]
            for i in items:
                i["group"] = "app"
        elif dotted:
            items += self._table_columns(dotted.group(1), word.group(0) if word else "")
        elif word:
            items += self._code_names(word.group(0)) + self._project_names(word.group(0), text, notebook)
        for i in items:
            if (
                i.get("kind") in ("function", "class")
                and i.get("params")
                and not text[offset:].startswith("(")
            ):
                params = [tuple(p) for p in i["params"]]
                if any(p[1] for p in params if p[0] not in ("self", "cls")):
                    i["snippet"] = rules.snippet(str(i["label"]), params)
            i.pop("params", None)
        ranked = rules.rank(items, recent)
        return {"items": ranked, "start": start, "end": offset, "from": found.get("from", "")} | (
            {"late": True} if found.get("late") else {}
        )

    def _quoted(self, quoted: rules.Quoted) -> list[dict[str, Any]]:
        typed = quoted.typed.casefold()
        out: list[dict[str, Any]] = []

        def offer(label: str, kind: str, detail: str, doc: str = "") -> None:
            if label.casefold().startswith(typed) or (typed and typed in label.casefold()):
                out.append(
                    {"label": label, "kind": kind, "detail": detail, "documentation": doc, "group": "app"}
                )

        if quoted.kind == "connection":
            for b in self._blades():
                if b.get("connection"):
                    offer(
                        str(b["name"]),
                        "connection",
                        f"{b.get('kind')} connection",
                        str(b.get("description") or ""),
                    )
        elif quoted.kind == "blade":
            for b in self._blades():
                if not b.get("connection"):
                    asks = ", ".join(str(x) for x in b.get("env_names") or [])
                    doc = rules.markdown_doc(
                        f'sab.blade("{b["name"]}")',
                        str(b.get("description") or ""),
                        f"a {b.get('kind')} blade",
                    )
                    offer(
                        str(b["name"]),
                        "function",
                        str(b.get("kind") or "blade") + (f" · reads {asks}" if asks else ""),
                        doc,
                    )
        elif quoted.kind == "structure":
            for name in self._structures():
                offer(name, "struct", "structure")
        elif quoted.kind == "variable":
            for v in self._variables():
                where = str(v.get("words") or v.get("from") or "")
                offer(str(v["name"]), "variable", where, f"A setting (Environment): {where}" if where else "")
        elif quoted.kind == "column" and quoted.table:
            for column, kind in self._columns(quoted.table):
                offer(column, "column", f"{quoted.table} · {kind}")
        elif quoted.kind == "mock":
            for name, words in self.sandbox_clients():
                offer(name, "connection", words, "A mock of its client over the project's sandbox (API.py)")
        elif quoted.kind == "sandbox_table":
            for table, columns in self.sandbox_tables():
                offer(table, "table", f"sandbox · {len(columns)} columns", ", ".join(columns[:30]))
        elif quoted.kind == "sandbox_column":
            named = {t.casefold() for t in quoted.tables}
            listed = self.sandbox_tables()
            mine = [(t, cs) for t, cs in listed if t.casefold() in named] or listed
            seen: set[str] = set()
            for table, columns in mine:
                for column in columns:
                    if column.casefold() not in seen:
                        seen.add(column.casefold())
                        offer(column, "column", f"{table} · sandbox")
        elif quoted.kind == "dataset":
            for b in self._blades():
                if b.get("dialect") == "dax":
                    offer(str(b["name"]), "connection", "Power BI workspace")
        return out

    def _columns(self, table: str) -> list[tuple[str, str]]:
        for info in self.ws.store.all():
            if info.name == table or info.name.casefold() == table.casefold():
                return [(c.name, c.type) for c in info.columns]
        return []

    def _table_columns(self, table: str, typed: str) -> list[dict[str, Any]]:
        """An open table's columns after `orders.` (where pandas allows: a name that is an identifier)."""
        return [
            {"label": c, "kind": "column", "detail": f"{table} · {kind}", "group": "scope"}
            for c, kind in self._columns(table)
            if c.isidentifier() and c.casefold().startswith(typed.casefold())
        ]

    def _code_names(self, typed: str) -> list[dict[str, Any]]:
        """The connections by their names in code (there before the kernel has made them)."""
        out = []
        for b in self._blades():
            name = b.get("code_name")
            if name and str(name).startswith(typed):
                out.append(
                    {
                        "label": name,
                        "kind": "connection",
                        "detail": f"the connection {b['name']}",
                        "group": "app",
                    }
                )
        return out

    def _project_names(self, typed: str, text: str, notebook: bool) -> list[dict[str, Any]]:
        """The project's modules' names, each with the import that brings it (where it belongs: after the
        imports at the top; in a notebook, at the cell's top)."""
        if len(typed) < 2:
            return []
        have = rules.imported_names(text)
        out = []
        sources = self._modules.sources(self._project_folder(), rules.PROJECT_MODULES)
        for module, source in sources.items():
            for n in rules.module_names(source):
                if not n["name"].startswith(typed) or n["name"] in have:
                    continue
                line = f"from {module} import {n['name']}"
                edit = rules.import_edit(text, line)
                out.append(
                    {
                        "label": n["name"],
                        "kind": n["kind"],
                        "detail": n["signature"] or n["kind"],
                        "module": module,
                        "documentation": rules.markdown_doc("", n["doc"], f"{module}.py"),
                        "group": "project",
                        "imports": [edit.to_json()],
                        "import_line": line,
                    }
                )
        return out

    # ===== parameter info and the hover =====

    async def signature(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The call the cursor is inside: each signature (overloads), its label, each parameter's span (the
        current one bold), the active parameter, each parameter's words from the docstring, the return."""
        body = dict(body or {})
        self._arrived(body)
        found = await self._jedi("signature", body, {"signatures": []})
        return {"signatures": found.get("signatures") or [], "from": found.get("from", "")}

    async def hover(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The name at the cursor: its signature or type (the kernel's, when it has run) and its docstring."""
        body = dict(body or {})
        self._arrived(body)
        found = await self._jedi("hover", body, {"hover": ""})
        return {"hover": found.get("hover") or "", "from": found.get("from", "")}

    # ===== the lint =====

    async def _known(self, body: Mapping[str, Any]) -> list[str]:
        """The kernel's names (kept a few seconds), when it has run."""
        kernel = self._kernel(body)
        kid = str(body.get("kernel") or "")
        kept = self._kernel_names.get(kid)
        if kept and time.monotonic() - kept[0] < KERNEL_NAMES_SECONDS:
            return kept[1]
        if kernel is None:
            return kept[1] if kept else []
        try:
            found = await asyncio.wait_for(
                kernel.evaluate(
                    "__import__('swissarmybench.client.kernel_intel', fromlist=['names']).names()"
                ),
                KERNEL_SECONDS,
            )
            names = [str(n) for n in json.loads(found)] if isinstance(found, str) else []
        except Exception:
            names = kept[1] if kept else []
        self._kernel_names[kid] = (time.monotonic(), names)
        return names

    async def lint(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{text, language (python or sql), notebook, before, after, kernel, python, connection, document,
        version}: the problems, each with its place, severity, code, source and fixes; and Ruff's state
        (used, or not installed with the missing-package answer to offer once)."""
        body = dict(body or {})
        self._arrived(body)
        text, _, notebook, before, after = self._text(body)
        if body.get("language") == "sql":
            return await self._lint_sql(body, text)
        known = set(await self._known(body))
        for cell in before:
            known |= rules.names_made(cell, notebook)
        used_later: set[str] = set()
        for cell in after:
            used_later |= rules.names_used(cell, notebook)
        key = (
            "lint",
            body.get("document"),
            body.get("version"),
            body.get("path"),
            hash(text),
            hash(frozenset(known)),
            hash(frozenset(used_later)),
        )
        cached = self._cached(key)
        if cached is not None:
            return cached
        python = self._python(body)
        folder = self._project_folder()
        variables = {str(v["name"]): str(v.get("words") or v.get("from") or "") for v in self._variables()}
        api_file = not notebook and api_rules.is_api_file(body.get("path"))

        def job() -> dict[str, Any]:
            importable = {
                n["name"]: f"from {module} import {n['name']}"
                for module, source in self._modules.sources(folder, rules.PROJECT_MODULES).items()
                for n in rules.module_names(source)
            }
            own = rules.lint(text, known, used_later, importable, variables, notebook)
            source = rules.prepare(text, notebook)
            if source is None or any(p.code == "E999" for p in own):
                return {"problems": [p.to_json() for p in own], "ruff": self._ruff_state(python, None)}
            command = self._linters.ruff_command(python)
            path = body.get("path")
            where = folder or (path.rsplit("/", 1)[0] if isinstance(path, str) and "/" in path else None)
            if where is None and isinstance(path, str) and "\\" in path:
                where = path.rsplit("\\", 1)[0]
            external = self._from_ruff(source, command, where, notebook) if command else None
            used = "ruff" if external is not None else None
            if external is None:
                flakes = self._linters.pyflakes(source)
                external = self._from_pyflakes(flakes) if flakes is not None else None
                used = "pyflakes" if external is not None else None
            merged = self._merge(own, external or [], known, used_later)
            if api_file:
                merged = sorted(merged + self._api_problems(text), key=lambda p: (p["line"], p["col"]))
            return {
                "problems": merged,
                "ruff": self._ruff_state(python, command),
                "checker": used or "python",
            }

        return self._keep(key, await self._work(body, job, {"problems": []}))

    def _api_problems(self, text: str) -> list[dict[str, Any]]:
        """API.py's own rules as squiggles: the APIs page's problems, a connection with no sandbox table, SQL
        the mock would refuse (each across its line)."""
        try:
            mocks = self.sandbox_mocks()
        except Exception:  # no project, or its sandbox unreadable: API.py's own rules alone
            mocks = None
        lines = text.splitlines()
        out = []
        for p in api_rules.editor_problems(text, mocks or None):
            line = max(1, min(int(p["line"]), max(1, len(lines))))
            body = lines[line - 1] if lines else ""
            start = len(body) - len(body.lstrip())
            out.append(
                rules.Problem(
                    line, start, line, max(start + 1, len(body)), p["message"], "warning", "API", "API.py"
                ).to_json()
            )
        return out

    def _ruff_state(self, python: str | None, command: str | None) -> dict[str, Any]:
        if command:
            return {"used": True}
        missing = missing_packages("Linting with Ruff", ["ruff"], python or "app", own=python is None)
        return {
            "used": False,
            "reason": "Ruff is not installed in this document's Python",
            "missing": missing,
        }

    def _from_ruff(
        self, source: str, command: str, folder: str | None, notebook: bool
    ) -> list[dict[str, Any]] | None:
        found = self._linters.ruff(source, command, folder)
        if found is None:
            return None
        out = []
        for d in found:
            code = str(d.get("code") or "E999")
            if notebook and code in ("I001", "E402", "F404", "W292", "B018"):
                continue  # a cell is not a module: its imports, its last line shown as the output
            start, end = d.get("location") or {}, d.get("end_location") or {}
            fix = d.get("fix") or {}
            fixes = []
            if fix.get("edits") and fix.get("applicability") in ("safe", "unsafe"):
                edits = [
                    {
                        "line": e["location"]["row"],
                        "col": e["location"]["column"],
                        "end_line": e["end_location"]["row"],
                        "end_col": e["end_location"]["column"],
                        "text": e.get("content") or "",
                    }
                    for e in fix["edits"]
                ]
                fixes.append({"kind": "edit", "title": str(fix.get("message") or "Fix"), "edits": edits})
            name = re.search(r"`([^`]+)`", str(d.get("message") or ""))
            out.append(
                {
                    "line": start.get("row", 1),
                    "col": start.get("column", 1),
                    "end_line": end.get("row", start.get("row", 1)),
                    "end_col": end.get("column", start.get("column", 1) + 1),
                    "message": str(d.get("message") or ""),
                    "code": code,
                    "source": "Ruff",
                    "name": name.group(1) if name else "",
                    "fixes": fixes,
                }
            )
        return out

    @staticmethod
    def _from_pyflakes(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "line": d["line"],
                "col": d["col"],
                "end_line": d["line"],
                "end_col": d["col"] + max(1, len(str(d.get("name") or "")) or 1),
                "message": d["message"],
                "code": d["code"],
                "source": "pyflakes",
                "name": d.get("name") or "",
                "fixes": [],
            }
            for d in found
        ]

    @staticmethod
    def _merge(
        own: list[rules.Problem], external: list[dict[str, Any]], known: set[str], used_later: set[str]
    ) -> list[dict[str, Any]]:
        """The app's problems, then the linter's own others. The app knows the kernel's and the other
        cells' names: a linter's undefined name the app knows, or its unused import a later cell uses, is
        dropped; where both say the same, the app's (with its fixes) stays, with the linter's code."""
        mine = [p.to_json() for p in own]
        at = {(p["line"], p["code"]) for p in mine}
        for d in external:
            code = d["code"]
            if (d["line"], code) in at:
                continue
            if code == "F821" and (d["name"] in known or d["name"] in rules.BUILTINS):
                continue
            if code in ("F401", "F841") and d["name"].split(".")[0] in used_later:
                continue
            if code == "F821":
                continue  # the app's own check says the undefined names it is sure of
            severity = (
                "error"
                if code.startswith(("E9", "F82")) or code == "E999"
                else "hint"
                if code in ("F401", "F841")
                else "warning"
            )
            mine.append(d | {"severity": severity, "unnecessary": code in ("F401", "F841")})
        return sorted(mine, key=lambda p: (p["line"], p["col"]))

    async def _lint_sql(self, body: Mapping[str, Any], text: str) -> dict[str, Any]:
        connection = body.get("connection")
        dialect = self._dialect_of(connection) if isinstance(connection, str) and connection else "duckdb"

        def job() -> dict[str, Any]:
            if dialect in (None, "duckdb"):
                # [Connection].table is DuckDB SQL here (domain/connection_tables.py): read as a quoted name.
                plain = re.sub(r"\[([^\]\n]*)\]", lambda m: '"' + m.group(1).replace('"', "'") + '"', text)
                error = self._linters.duckdb_error(plain) if plain.strip() else None
                found = [rules.duckdb_error(error, text)] if error else []
            elif dialect == "dax":
                found = []
            else:
                found = rules.sql_problems(text, dialect)
            return {"problems": [p.to_json() for p in found], "dialect": dialect or "duckdb"}

        return await self._work(body, job, {"problems": []})

    # ===== what the editors show, for the agent =====

    def report(self, body: Any) -> dict[str, Any]:
        """The page's editors tell what they show: {document, title, problems} (an empty list clears it)."""
        body = dict(body or {})
        document = str(body.get("document") or "")
        problems = [p for p in body.get("problems") or [] if isinstance(p, dict)][:500]
        if not document:
            return {"documents": len(self._problems)}
        if problems:
            self._problems[document] = {
                "document": document,
                "title": str(body.get("title") or document),
                "problems": problems,
            }
        else:
            self._problems.pop(document, None)
        return {"documents": len(self._problems)}

    async def problems(self, path: str | None = None, who: str = "agent") -> dict[str, Any]:
        """Every open document's problems as its editors show them; with `path`, that file checked now."""
        if path:
            try:
                text = self._read_file(path)
            except OSError as error:  # not there, or not a file: said plainly (404), never a server error
                raise NotFound(str(error)[:300]) from None
            body = {"text": text, "notebook": False, "path": path, "language": "python"}
            if path.endswith(".ipynb"):
                return self._notebook_problems(path, text)
            found = await self.lint(body, who)
            return {"documents": [{"document": path, "problems": found.get("problems") or []}]}
        listed = sorted(self._problems.values(), key=lambda d: str(d["document"]))
        counts = {
            s: sum(1 for d in listed for p in d["problems"] if p.get("severity") == s)
            for s in ("error", "warning", "hint")
        }
        return {"documents": listed, "counts": counts}

    def _notebook_problems(self, path: str, text: str) -> dict[str, Any]:
        """A notebook on disk: each code cell checked with the cells before it (no kernel)."""
        try:
            cells = [c for c in json.loads(text).get("cells") or [] if c.get("cell_type") == "code"]
        except ValueError:
            return {"documents": [{"document": path, "problems": []}]}
        sources = [
            "".join(c.get("source") or [])
            if isinstance(c.get("source"), list)
            else str(c.get("source") or "")
            for c in cells
        ]
        out = []
        known: set[str] = set()
        for i, source in enumerate(sources):
            used_later = (
                set().union(*(rules.names_used(s) for s in sources[i + 1 :]))
                if i + 1 < len(sources)
                else set()
            )
            for p in rules.lint(source, known, used_later, notebook=True):
                out.append(p.to_json() | {"cell": i + 1})
            known |= rules.names_made(source)
        return {"documents": [{"document": path, "problems": out}]}
