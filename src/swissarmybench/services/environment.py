"""The Environment (the owner, 2026-11-21/22; Plans/environment.plan.md; rules in domain/environment.py):
everything the project holds in one list, for the Environment page, the Workbench's right pane and the agent.

  listing    every row (tables, variables, structures, settings and secrets, libraries), each with where it
             is used; one search over every tab (each tab's count; a row matched itself or inside)
  show       one row whole (every place that uses it; a table's columns with their ranges and blanks)
  columns    a table's columns for the row that unfolds: type, range, blanks (one pass, asked when opened)
  open       where a row opens (a table: a grid, a view of it, made when it has none; a structure: its viewer)
  rename, remove, keep, clear, insert
  libraries  the project's Python and its libraries; check (the index's newest, only when asked), pin,
             install, update, remove: requirements.txt follows, the agent's waits for the user's Allow

`environment_changed` is the one notice: sent (once things settle) when anything the list is made of changes,
so the page follows by itself and has no Refresh. Names, types, sizes and short looks only: a secret's value
is never in an answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import environment as rules
from swissarmybench.domain import local_api, notebooks
from swissarmybench.domain.datasets import quote
from swissarmybench.domain.dictionary import plain_type
from swissarmybench.domain.environment import Document, Item, Used
from swissarmybench.domain.environments import LIBRARIES
from swissarmybench.domain.project_scope import CANVAS_SUFFIX
from swissarmybench.services.changes import raised
from swissarmybench.services.ports import BACKGROUND, Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

# The notices that change what the list is made of.
HEARD: frozenset[str] = frozenset(
    {
        "dataset_updated",
        "dataset_closed",
        "dataset_renamed",
        "grid_updated",
        "grid_closed",
        "grid_shown",
        "processes_changed",
        "project_python",
        "structures_changed",
        "variables_changed",
        "blades_changed",
        "cards_updated",
        "relationships_updated",
        "project_changed",
        "project_documents_changed",
        "local_api_changed",
        "canvas_changed",
        "sandbox_changed",
        "file_changed",
    }
)
SETTLE_SECONDS: float = 0.3
MAX_COLUMNS_LOOKED: int = 200
ORIGIN_WORDS: dict[str, str] = {
    "paste": "Made in the app · pasted",
    "sample": "Made in the app · sample data",
    "query": "Made in the app · a query",
    "dropped": "A file dropped here",
    "structure": "Made in the app · from a structure",
    "sandbox": "Sandbox",
}


class Libraries(Protocol):
    """The project's Python and its libraries (adapters/environment.py and server/environments.py)."""

    def python_of(self, folder: str | None) -> tuple[str, bool]: ...

    def version_of(self, python: str) -> str: ...

    def installed(self, python: str) -> dict[str, str]: ...

    def read_requirements(self, folder: str) -> str: ...

    def write_requirements(self, folder: str, text: str) -> bool: ...

    def latest(self, names: list[str]) -> dict[str, str]: ...

    async def install(
        self, python: str, specs: list[str], upgrade: bool = False
    ) -> tuple[int | None, str]: ...

    async def uninstall(self, python: str, names: list[str]) -> tuple[int | None, str]: ...


@dataclass
class Sources:
    """What the composition root hands over: each a plain callable, so a test gives a few lines."""

    # A table's origin (domain/table_cells.py's Origin) and the document a kernel was started for.
    origin_of: Callable[[str], Any]
    kernel_document: Callable[[str | None], str | None] = lambda kernel: None
    # The document whose code made a table, as said when it arrived (a project's one session: the kernel
    # alone does not name the document).
    table_document: Callable[[str], str | None] = lambda name: None
    # The open project ({"folder", "name", "tables": [{"name", "keep_rows"}]}) or None.
    project: Callable[[], Mapping[str, Any] | None] = lambda: None
    # The running kernels' ids, and one's variables (client/kernel_variables.py's snapshot; busy: True).
    kernels: Callable[[], list[str]] = list
    kernel_variables: Callable[[str], Awaitable[dict[str, Any]]] | None = None
    kernel_call: Callable[..., Awaitable[Any]] | None = None
    # The Python sessions' tables (services/processes.py's listing), and one asked to send a table of its
    # own (session id, table name: the watcher pushes it and its grid arrives).
    sessions: Callable[[], list[dict[str, Any]]] = list
    # Their variables (names, types and sizes only: the watcher's report), each with the kernel it is.
    session_values: Callable[[], list[dict[str, Any]]] = list
    open_python: Callable[[str, str], bool] | None = None
    # The code to look for names in, canvases as (name, text), API.py's endpoints, the board's cards.
    documents: Callable[[], list[Document]] = list
    canvases: Callable[[], list[tuple[str, str]]] = list
    # API.py's path and its endpoints (domain/local_api.py's).
    endpoints: Callable[[], tuple[str, list[Any]]] = lambda: ("", [])
    cards: Callable[[], list[Mapping[str, Any]]] = list
    relationships: Callable[[], Iterable[Any]] = list
    # Structures (services/structures.py) and the `${NAME}` settings (services/variables.py).
    structures: Any = None
    settings: Any = None
    remove_file: Callable[[str], None] | None = None
    # Tables: close, rename (services/datasets.py); keep with the project (services/sab_projects.py's save).
    close_table: Callable[[str, str], Awaitable[Any]] | None = None
    rename_table: Callable[[str, Any, str], Awaitable[Any]] | None = None
    save_project: Callable[[Any, str], Awaitable[Any]] | None = None
    # The project's code changed by an install (a requirements.txt written): told to the code files' watch.
    touched: Callable[[str], Awaitable[Any]] | None = None


@dataclass
class _Kernel:
    variables: list[dict[str, Any]] = field(default_factory=list)
    document: str | None = None


class Environment:
    def __init__(
        self,
        ws: Workspace,
        sources: Sources,
        libraries: Libraries,
        approvals: Approvals,
        project_python: Any = None,
    ) -> None:
        self.ws = ws
        self._s = sources
        self._libraries = libraries
        self._approvals = approvals
        self._seen: dict[str, _Kernel] = {}  # each kernel's variables as last read (kept while it is busy)
        self._latest: dict[str, str] = {}  # the index's newest versions, by a library's key (memory only)
        self._checked = False
        self._settling: asyncio.TimerHandle | None = None
        # One Python per project (services/project_python.py; the composition root hands it over): the
        # project's own .venv as it is made, the one session's words, a notebook's older environment offered.
        self.project_python: Any = project_python
        self._tasks: set[asyncio.Task[None]] = set()

    # ===== the notice =====

    def heard(self, message: Mapping[str, Any]) -> None:
        """A notice went to the pages (adapters/live_updates.py's listeners): when it changes what the list
        is made of, `environment_changed` follows once things settle (one for a burst)."""
        if message.get("type") not in HEARD:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._settling is not None:
            self._settling.cancel()
        self._settling = loop.call_later(SETTLE_SECONDS, self._say)

    def _say(self) -> None:
        self._settling = None
        task = asyncio.ensure_future(self.ws.live.broadcast({"type": "environment_changed"}))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def changed(self) -> None:
        await self.ws.live.broadcast({"type": "environment_changed"})

    # ===== the rows =====

    def _folder(self) -> str | None:
        project = self._s.project()
        folder = project.get("folder") if project else None
        return str(folder) if folder else None

    def _kept(self) -> set[str]:
        project = self._s.project() or {}
        return {str(t.get("name")) for t in project.get("tables", []) if t.get("keep_rows")}

    def _origin_words(self, name: str) -> str:
        origin = self._s.origin_of(name)
        kind = getattr(origin, "kind", "unknown")
        if kind == "connection" and getattr(origin, "connection", None):
            return str(origin.connection)
        if kind == "file" and getattr(origin, "path", None):
            return "File · " + str(origin.path).replace("\\", "/").rsplit("/", 1)[-1]
        if kind == "python":
            document = self._s.table_document(name) or self._s.kernel_document(
                getattr(origin, "kernel", None)
            )
            return _title(document) if document else "Python"
        return ORIGIN_WORDS.get(kind, "")

    async def _read_kernels(self) -> None:
        """Each running kernel's variables, read now; a busy one keeps what it last said."""
        running = self._s.kernels()
        for gone in set(self._seen) - set(running):
            del self._seen[gone]
        if self._s.kernel_variables is None:
            return
        for kernel in running:
            try:
                found = await self._s.kernel_variables(kernel)
            except Exception:  # noqa: S112 (a kernel that just stopped, or whose Python has no package)
                continue
            held = self._seen.setdefault(kernel, _Kernel())
            held.document = self._s.kernel_document(kernel)
            if not found.get("busy"):
                held.variables = list(found.get("variables") or [])

    def _python_tables(self) -> dict[str, tuple[str, dict[str, Any]]]:
        """The tables Python holds, by name: (where: its session's label, its entry with its session's id)."""
        found: dict[str, tuple[str, dict[str, Any]]] = {}
        # Oldest report first, so where two sessions hold a name the newest one's table is the row.
        for session in self._s.session_values() or self._s.sessions():
            for table in session.get("tables", []):
                entry = table | {"session": session.get("id")}
                found[str(table["name"])] = (str(session.get("label") or "Python"), entry)
        return found

    def _tables(self, uses: Mapping[str, list[Used]]) -> list[Item]:
        ws = self.ws
        kept = self._kept()
        python = self._python_tables()
        items: list[Item] = []
        for info in ws.store.all():
            grids = [
                {"id": g.id, "name": info.name, "steps": len([s for s in g.steps if s.enabled])}
                for g in ws.grids.for_dataset(info.name)
            ]
            origin = self._s.origin_of(info.name)
            sandbox = getattr(origin, "kind", "") == "sandbox"
            tags = tuple(
                t for t, on in (("Keep", info.name in kept), ("In Python", info.name in python)) if on
            )
            names = [c.name for c in info.columns]
            items.append(
                Item(
                    "table",
                    info.name,
                    type="Table",
                    size=rules.table_size(info.row_count, len(names)),
                    value=rules.columns_look(names),
                    origin=self._origin_words(info.name),
                    sub="sandbox" if sandbox else None,
                    tags=tags,
                    grids=tuple(grids),
                    used=(*rules.grid_uses(grids), *uses.get(info.name, ())),
                    kids=tuple((c.name, plain_type(c.type).lower(), "") for c in info.columns),
                    more={
                        "rows": info.row_count,
                        "columns": len(names),
                        "bytes": info.nbytes,
                        "open": True,
                        "in_python": info.name in python,
                    },
                )
            )
        opened = {i.name for i in items}
        for name, (label, table) in sorted(python.items()):
            if name in opened:
                continue
            kind = rules.TABLE_KIND_WORDS.get(str(table.get("kind")), "Table")
            items.append(
                Item(
                    "table",
                    name,
                    type=kind,
                    size=rules.table_size(table.get("rows"), table.get("columns")),
                    value=self._python_look(name),
                    origin=label,
                    tags=("In Python",),
                    used=tuple(uses.get(name, ())),
                    kids=self._python_kids(name),
                    more={
                        "rows": table.get("rows"),
                        "columns": table.get("columns"),
                        "bytes": None,
                        "open": False,
                        "in_python": True,
                    },
                )
            )
        return items

    def _variable(self, name: str) -> dict[str, Any] | None:
        for held in self._seen.values():
            for row in held.variables:
                if row.get("name") == name:
                    return row
        return None

    def _python_look(self, name: str) -> str:
        row = self._variable(name) or {}
        return rules.columns_look([k[0] for k in row.get("kids") or []]) or "a table in Python"

    def _python_kids(self, name: str) -> tuple[tuple[str, str, str], ...]:
        row = self._variable(name) or {}
        return tuple((str(k[0]), str(k[1]), str(k[2])) for k in row.get("kids") or [])

    def _variables(self, uses: Mapping[str, list[Used]], made: Mapping[str, str]) -> list[Item]:
        items: dict[str, Item] = {}
        for held in self._seen.values():
            where = _title(held.document) if held.document else "Python"
            for row in held.variables:
                name = str(row.get("name"))
                if row.get("table") or name in items:
                    continue  # a table is on the Tables tab
                kids = tuple(
                    (str(k[0]), rules.type_words(str(k[1])), str(k[2])) for k in row.get("kids") or []
                )
                items[name] = Item(
                    "variable",
                    name,
                    type=rules.type_words(str(row.get("type") or "")),
                    size=_size_words(row),
                    value=rules.short(str(row.get("value") or "")),
                    origin=made.get(name) or where,
                    used=tuple(uses.get(name, ())),
                    kids=kids,
                )
        # A session the app does not run (Jupyter, a script with sab.watch()): what its watcher reported,
        # names, types and sizes only.
        for session in self._s.session_values():
            if session.get("kernel") in self._seen:
                continue
            for row in session.get("variables") or []:
                name = str(row.get("name"))
                if name not in items:
                    items[name] = Item(
                        "variable",
                        name,
                        type=rules.type_words(str(row.get("type") or "")),
                        size=_size_words(row),
                        origin=made.get(name) or str(session.get("label") or "Python"),
                        used=tuple(uses.get(name, ())),
                    )
        return sorted(items.values(), key=lambda i: i.name.casefold())

    def _structures(self) -> list[Item]:
        structures = self._s.structures
        if structures is None:
            return []
        listing = structures.listing()
        items: dict[str, Item] = {}
        for file in listing.get("files", []):
            name = str(file["name"])
            try:
                references = structures.references(name).get("references", [])
            except Exception:
                references = []
            used = [
                Used(
                    "cell",
                    str(r.get("title") or r.get("name") or "")
                    + (f" · cell {r['cell']}" if r.get("cell") is not None else ""),
                    {k: r[k] for k in ("path", "cell", "line") if r.get(k) is not None} | {"to": "document"},
                )
                for r in references
            ]
            items[name] = Item(
                "structure",
                name,
                type=f"{str(file['format']).upper()} file",
                size=rules.bytes_words(int(file.get("size") or 0)),
                value="",
                origin=f"structures/{file['file']}",
                used=tuple(used),
                more={"open": file.get("open"), "path": file.get("path"), "saved": True},
            )
        for opened in listing.get("open", []):
            name = str(opened.get("name"))
            known = items.get(name)
            nodes = opened.get("nodes")
            size = rules.count(int(nodes), "key") if isinstance(nodes, int) else ""
            if known is not None and known.more.get("open") == opened.get("id"):
                known.size = f"{size} · {known.size}" if size else known.size
                continue
            items[f"{name}\u0000{opened.get('id')}"] = Item(
                "structure",
                name,
                type=f"{str(opened.get('format') or 'json').upper()}, not saved",
                size=size,
                origin="open, not saved",
                more={"open": opened.get("id"), "path": None, "saved": False},
            )
        for item in items.values():
            sid = item.more.get("open")
            if sid:
                item.kids = self._paths(str(sid))
                item.value = rules.columns_look([k[0] for k in item.kids], 2)
        return sorted(items.values(), key=lambda i: i.name.casefold())

    def _paths(self, sid: str) -> tuple[tuple[str, str, str], ...]:
        from swissarmybench.domain.explorer import structure_paths

        try:
            value = self._s.structures.node(sid)
        except Exception:
            return ()
        return tuple(
            (p.pointer, p.type, rules.short(str(getattr(p, "example", "") or ""), 80))
            for p in structure_paths(value, rules.MAX_KIDS)
        )

    def _settings(self) -> list[Item]:
        if self._s.settings is None:
            return []
        listed = self._s.settings.listing().get("variables", [])
        return [rules.setting_item(v, rules.setting_uses(v.get("uses") or [])) for v in listed]

    def python(self) -> dict[str, Any]:
        """The Python the project's code runs in: its path, its version, whether it is the project's own."""
        python, own = self._libraries.python_of(self._folder())
        state = self.project_python.state() if self.project_python is not None else {}
        return state | {"python": python, "version": self._libraries.version_of(python), "own": own}

    async def set_python(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The project's Python changed on request: {"make": true} makes its `.venv` now (Try again; it is
        made by itself as a project opens); {"offer": a document, "add": true | false} answers what a
        notebook's older environment offered (add: its libraries installed and written to requirements.txt,
        the agent's on Allow; false: Not now). The Python as it is now."""
        if self.project_python is None or not isinstance(body, dict):
            raise ValueError('Send {"make": true} or {"offer": "the document", "add": true}.')
        if body.get("make"):
            await self.project_python.make(body, who)
        elif isinstance(body.get("offer"), str):
            offers = self.project_python.state()["offers"]
            offer = next((o for o in offers if o["document"] == body["offer"]), None)
            if offer is None:
                raise NotFound("That offer is no longer there (it was added, or declined).")
            if body.get("add"):
                await self.install({"names": offer["libraries"]}, who)
            await self.project_python.settle_offer({"document": offer["document"]}, who)
        else:
            raise ValueError('Send {"make": true} or {"offer": "the document", "add": true}.')
        await self.changed()
        return self.python()

    def _library_items(self, documents: list[Document]) -> list[Item]:
        python, _ = self._libraries.python_of(self._folder())
        folder = self._folder()
        text = self._libraries.read_requirements(folder) if folder else ""
        return rules.library_items(
            self._libraries.installed(python),
            rules.requirements(text),
            rules.imported_in(documents),
            self._latest,
        )

    async def _items(self) -> list[Item]:
        await self._read_kernels()
        documents = await asyncio.to_thread(self._s.documents)
        infos = self.ws.store.all()
        python_names = {str(row.get("name")) for held in self._seen.values() for row in held.variables} | set(
            self._python_tables()
        )
        python_names |= {
            str(r.get("name")) for s in self._s.session_values() for r in s.get("variables") or []
        }
        tables = {i.name for i in infos}
        grids = {g.id: g.dataset for g in self.ws.grids.all()}
        api_path, api_endpoints = self._s.endpoints()
        uses = rules.merged(
            rules.cell_uses(documents, tables - python_names, fold=True),
            rules.cell_uses(documents, python_names),
            rules.canvas_uses(self._s.canvases(), tables | python_names),
            rules.endpoint_uses(api_endpoints, tables, api_path),
            rules.analysis_uses(self._s.cards(), grids),
            rules.erd_uses(self._s.relationships()),
            rules.made_from({i.name: i.query for i in infos}),
        )
        made = _made_in(documents, python_names)
        libraries = await asyncio.to_thread(self._library_items, documents)
        return [
            *self._tables(uses),
            *self._variables(uses, made),
            *self._structures(),
            *self._settings(),
            *libraries,
        ]

    async def listing(self, search: Any = None) -> dict[str, Any]:
        """Every row, or the ones the search finds: {"items": [...], "counts": {kind: n}, "python", "project",
        "memory"}; with a search each row says how it matched ({"own", "kids": [indexes]})."""
        items = await self._items()
        found, counts = rules.searched(items, search)
        project = self._s.project()
        rows = []
        for item, how in found:
            row = item.to_json()
            if isinstance(search, str) and search.strip():
                row["match"] = {"own": how.own, "kids": list(how.kids)}
            rows.append(row)
        return {
            "items": rows,
            "counts": counts,
            "tabs": [
                {"kind": k, "name": rules.TABS[k], "columns": list(rules.COLUMNS[k])} for k in rules.KINDS
            ],
            "python": self.python(),
            "project": {"name": project.get("name"), "folder": project.get("folder")} if project else None,
            "memory": rules.bytes_words(self.ws.store.used_bytes),
            "checked": self._checked,
        }

    async def _find(self, kind: Any, name: Any) -> Item:
        kind, name = rules.item_id(kind, name)
        for item in await self._items():
            if item.kind == kind and item.name == name:
                return item
        raise NotFound(f"There is no {kind} called {name} in the environment.")

    async def show(self, kind: Any, name: Any) -> dict[str, Any]:
        """One row whole: every place that uses it; a table open here with its columns' ranges and blanks."""
        item = await self._find(kind, name)
        row = item.to_json()
        if item.kind == "table" and item.more.get("open"):
            row["kids"] = (await self.columns(item.name))["columns"]
        return row

    async def columns(self, name: Any) -> dict[str, Any]:
        """An open table's columns for the row that unfolds: each one's type in plain words and a short look
        (its range and how many are blank), read in one pass."""
        info = self.ws.store.get(str(name))
        if info is None:
            raise NotFound(f"{name} is not a table open here.")
        columns = info.columns[:MAX_COLUMNS_LOOKED]
        parts = ", ".join(
            f"min({quote(c.name)})::VARCHAR, max({quote(c.name)})::VARCHAR, count(*) - count({quote(c.name)})"
            for c in columns
        )

        def read() -> tuple[Any, ...] | None:
            cursor = self.ws.views.adapted(self.ws.store.cursor())
            cursor.execute(f"SELECT {parts} FROM {info.table}")  # noqa: S608 (quoted names of its own table)
            return cursor.fetchone()

        try:
            row = await self.ws.workers.run(BACKGROUND, read) if columns else None
        except self.ws.engine_error:
            row = None
        kids = []
        for i, column in enumerate(columns):
            look = ""
            if row is not None:
                low, high, blank = row[i * 3 : i * 3 + 3]
                if low is not None:
                    look = (
                        rules.short(str(low), 40)
                        if low == high
                        else f"{rules.short(str(low), 40)} to {rules.short(str(high), 40)}"
                    )
                if blank:
                    look += (" · " if look else "") + f"{blank:,} blank"
            kids.append([column.name, plain_type(column.type).lower(), look])
        return {"name": info.name, "columns": kids}

    # ===== what a row does =====

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Where a row opens: a table in Grids (a view of it, made when it has none: never a copy), a
        structure in its viewer; any other row where it is managed. {"kind", "name"} -> {"link": {...}}."""
        item = await self._find(_field(body, "kind"), _field(body, "name"))
        if item.kind == "table":
            if not item.more.get("open"):
                # In Python only: its session is asked to send it (its grid arrives by itself).
                session = self._python_tables().get(item.name, ("", {}))[1].get("session")
                if (
                    not session
                    or self._s.open_python is None
                    or not self._s.open_python(str(session), item.name)
                ):
                    raise Conflict(
                        f"{item.name} is in a Python session that is not answering: run its cell again."
                    )
                self.ws.audit.write(who, "environment_open", item.name)
                return {"link": {"to": "python", "name": item.name}}
            grid = self.ws.grids.first_for(item.name) or self.ws.grids.create(item.name)
            return {
                "link": {"to": "grid", "grid": grid.id, "url": self.ws.addresses.grid(grid, with_token=False)}
            }
        if item.kind == "structure":
            return {"link": {"to": "structure", "id": item.more.get("open"), "path": item.more.get("path")}}
        if item.kind == "setting":
            return {"link": {"to": "setting", "name": item.name}}
        if item.kind == "library":
            return {"link": {"to": "library", "name": item.name}}
        return {"link": {"to": "variable", "name": item.name}}

    def insert(self, body: Any) -> dict[str, Any]:
        """What a row is inserted into code as: {"kind", "name"} -> {"python", "sql"?, "text"?}."""
        kind, name = rules.item_id(_field(body, "kind"), _field(body, "name"))
        line = ""
        if kind == "library":
            key = rules.library_key(name)
            line = next((lib.imports for lib in LIBRARIES if rules.library_key(lib.pip) == key), "")
        return rules.insert_code(kind, name, line)

    async def _kernels_do(self, function: str, *args: Any) -> list[Any]:
        if self._s.kernel_call is None:
            return []
        answers = []
        for kernel in self._s.kernels():
            answer = await self._s.kernel_call(kernel, function, *args)
            if answer is None:
                raise Conflict("Python is running code: do it again when the run is done.")
            answers.append(answer)
        return answers

    async def rename(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"kind", "name", "to"}: a table (its grids follow), a variable (the same object under its new
        name), an open structure, a setting (connections and Run settings follow)."""
        item = await self._find(_field(body, "kind"), _field(body, "name"))
        to = _field(body, "to")
        if not isinstance(to, str) or not to.strip():
            raise ValueError('Send {"kind", "name", "to": "the new name"}.')
        to = to.strip()
        if item.kind == "table":
            if not item.more.get("open") or self._s.rename_table is None:
                raise Conflict(f"{item.name} is in Python only: rename its variable there.")
            done = await self._s.rename_table(item.name, to, who)
        elif item.kind == "variable":
            answers = await self._kernels_do("rename", item.name, to)
            if not any(a.get("renamed") for a in answers):
                raise Refused(
                    next((a["why"] for a in answers if a.get("why")), "No Python session holds it.")
                )
            done = {"renamed": True}
            self.ws.audit.write(who, "environment_rename", f"{item.name} -> {to}")
        elif item.kind == "structure":
            if not item.more.get("open"):
                raise Conflict("Open the structure first: a saved file is renamed with Save as.")
            done = await self._s.structures.rename(str(item.more["open"]), {"name": to}, who)
        elif item.kind == "setting":
            done = await self._s.settings.rename({"name": item.name, "to": to}, who)
        else:
            raise Refused("A library keeps the name its makers gave it.")
        await self.changed()
        return {"renamed": True, "kind": item.kind, "name": to, "was": item.name} | (
            {"details": done} if isinstance(done, dict) else {}
        )

    async def remove(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"kind", "name", "python"?}: a table closes with its grids (and, on the tick "Also delete it in
        Python", its variable goes too); a variable is deleted in Python; an open structure closes, a saved
        one's file is deleted (the agent's waits for Allow); a setting or a library as its own Remove."""
        item = await self._find(_field(body, "kind"), _field(body, "name"))
        python = bool(isinstance(body, dict) and body.get("python"))
        done: dict[str, Any] = {"removed": True, "kind": item.kind, "name": item.name}
        if item.kind == "table":
            if item.more.get("open") and self._s.close_table is not None:
                await self._s.close_table(item.name, who)
            elif not python:
                raise Conflict(f"{item.name} is in Python only: tick Also delete it in Python to remove it.")
            if python and item.more.get("in_python"):
                done["python"] = bool(_flat(await self._kernels_do("forget", [item.name])))
        elif item.kind == "variable":
            if not _flat(await self._kernels_do("forget", [item.name])):
                raise NotFound(f"{item.name} is not a variable any more.")
            self.ws.audit.write(who, "environment_remove", item.name)
        elif item.kind == "structure":
            await self._remove_structure(item, who)
        elif item.kind == "setting":
            await self._s.settings.remove({"name": item.name}, who)
        else:
            return await self.uninstall({"name": item.name}, who)
        await self.changed()
        return done

    async def _remove_structure(self, item: Item, who: str) -> None:
        path = item.more.get("path")
        if path:
            await self._approvals.allowed(
                who,
                subject=item.name,
                action="delete a structure's file",
                detail=f"Delete {item.origin} from the project",
                otherwise="the file is as it was",
            )
        if item.more.get("open"):
            await self._s.structures.close(str(item.more["open"]), who)
        if path and self._s.remove_file is not None:
            await asyncio.to_thread(self._s.remove_file, str(path))
            self.ws.audit.write(who, "environment_remove", item.name, file=item.origin)

    async def keep(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Keep with the project: {"name", "keep": true|false}: the table's rows go into the project's
        .sab/data/ (Git-ignored) with its next save, done now (the agent's waits for the user's Allow)."""
        name = _field(body, "name")
        keep = body.get("keep", True) if isinstance(body, dict) else True
        if not isinstance(name, str) or not isinstance(keep, bool) or self.ws.store.get(name) is None:
            raise ValueError('Send {"name": "a table open here", "keep": true or false}.')
        if self._s.project() is None or self._s.save_project is None:
            raise Conflict("Keep needs a project: open or make one first (Home).")
        await self._s.save_project({"keep_rows": {name: keep}}, who)
        await self.changed()
        return {"name": name, "keep": keep}

    async def clear(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Clear…: {"tables", "variables", "structures"} (the ticks) clears what is ticked; with "dry_run"
        it only says what each tick would take. Kept tables, settings and libraries stay. The agent's waits
        for the user's Allow."""
        plan = rules.clear_plan(await self._items())
        if isinstance(body, dict) and body.get("dry_run"):
            return {"would": plan, "choices": rules.CLEAR}
        chosen = rules.clear_choice(body)
        words = rules.clear_words(plan, chosen)
        await self._approvals.allowed(
            who,
            subject="Environment",
            action="clear the environment",
            detail=words,
            otherwise="nothing was cleared",
        )
        cleared: dict[str, list[str]] = {}
        if "tables" in chosen and self._s.close_table is not None:
            for name in plan["tables"]:
                if self.ws.store.get(name) is not None:
                    await self._s.close_table(name, who)
                    cleared.setdefault("tables", []).append(name)
        if "variables" in chosen and plan["variables"]:
            cleared["variables"] = sorted(set(_flat(await self._kernels_do("forget", plan["variables"]))))
        if "structures" in chosen and self._s.structures is not None:
            for item in [i for i in await self._items() if i.kind == "structure" and i.more.get("open")]:
                await self._s.structures.close(str(item.more["open"]), who)
                cleared.setdefault("structures", []).append(item.name)
        self.ws.audit.write(who, "environment_clear", details=words)
        await self.changed()
        return {"cleared": cleared}

    # ===== libraries =====

    async def libraries(self, check: Any = False) -> dict[str, Any]:
        """The Libraries tab: the project's Python and its libraries; with `check`, the index is asked for
        each one's newest version first (when the tab opens or the user asks: never in the background)."""
        documents = await asyncio.to_thread(self._s.documents)
        if check:
            python, _ = self._libraries.python_of(self._folder())
            names = [
                i.name for i in await asyncio.to_thread(self._library_items, documents) if i.more["installed"]
            ]
            found = await asyncio.to_thread(self._libraries.latest, names)
            self._latest = {rules.library_key(name): version for name, version in found.items()}
            self._checked = True
            _ = python
        items = await asyncio.to_thread(self._library_items, documents)
        return {
            "python": self.python(),
            "libraries": [i.to_json() for i in items],
            "checked": self._checked,
            "outdated": [i.name for i in items if i.more["latest"] and not i.more["pinned"]],
        }

    def _own_folder(self) -> str:
        folder = self._folder()
        if folder is None:
            raise Conflict("Libraries are a project's: open or make one first (Home).")
        return folder

    async def _library(self, name: Any) -> Item:
        name = rules.check_library(name)
        key = rules.library_key(name)
        documents = await asyncio.to_thread(self._s.documents)
        for item in await asyncio.to_thread(self._library_items, documents):
            if rules.library_key(item.name) == key:
                return item
        raise NotFound(f"{name} is not one of the project's libraries.")

    async def _write(self, folder: str, text: str) -> bool:
        changed = await asyncio.to_thread(self._libraries.write_requirements, folder, text)
        if changed and self._s.touched is not None:
            await self._s.touched(folder)
        return changed

    async def pin(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "pinned": true|false}: Pin keeps the library at the version installed, written
        `name==version` in requirements.txt; Unpin writes its name alone. The agent's waits for Allow."""
        pinned = body.get("pinned", True) if isinstance(body, dict) else True
        item = await self._library(_field(body, "name"))
        folder = self._own_folder()
        if pinned and not item.more["installed"]:
            raise Conflict(f"{item.name} is not installed: install it, then pin it.")
        words = f"Pin {item.name} at {item.more['version']}" if pinned else f"Unpin {item.name}"
        await self._approvals.allowed(
            who,
            subject=item.name,
            action="change requirements.txt",
            detail=words,
            otherwise="requirements.txt is as it was",
        )
        text = await asyncio.to_thread(self._libraries.read_requirements, folder)
        new = (
            rules.with_pin(text, item.name, item.more["version"])
            if pinned
            else rules.without_pin(text, item.name)
        )
        changed = await self._write(folder, new)
        version = item.more["version"]
        said = f"Pinned {item.name} at {version}" if pinned else f"Unpinned {item.name}"
        change = (
            _library_change(item.name, version, not pinned, version, bool(pinned), said) if changed else {}
        )
        self.ws.audit.write(who, "environment_pin" if pinned else "environment_unpin", item.name, **change)
        await self.changed()
        return {"name": item.name, "pinned": bool(pinned), "changed": changed}

    async def _versions(self, python: str) -> dict[str, str]:
        """The project's Python's libraries by their key, each with its version, as installed right now."""
        found = await asyncio.to_thread(self._libraries.installed, python)
        return {rules.library_key(name): version for name, version in found.items()}

    def _said(self, who: str, action: str, names: str, changes: list[dict[str, Any]]) -> None:
        """One audit entry for what was asked; the change log's events with it (services/changes.py): on
        the entry itself for one library, an entry of its own for each of several."""
        changes = [c for c in changes if c]
        if len(changes) == 1:
            self.ws.audit.write(who, action, names, **changes[0])
            return
        self.ws.audit.write(who, action, names)
        for change in changes:
            self.ws.audit.write(who, "changed", change["change"]["object"]["name"], **change)

    async def _change(self, specs: list[str], upgrade: bool, who: str, words: str) -> None:
        python, _ = self._libraries.python_of(self._folder())
        await self._approvals.allowed(
            who,
            subject="Environment",
            action="install libraries",
            detail=words,
            otherwise="nothing was installed",
        )
        code, out = await self._libraries.install(python, specs, upgrade)
        if code is None:
            raise Conflict("The install took over 10 minutes and was stopped.")
        if code != 0:
            tail = "\n".join(out.strip().splitlines()[-15:])
            raise Refused(f"The install failed: {words}.", details=tail)

    async def install(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Install a library…: {"name"} (as pip knows it) into the project's Python, and into
        requirements.txt so a teammate gets it. The agent's waits for the user's Allow."""
        several = body.get("names") if isinstance(body, dict) else None
        if isinstance(several, list) and several:  # several at once: one install, one Allow
            names = [rules.check_library(n) for n in several[:60]]
        else:
            names = [rules.check_library(_field(body, "name"))]
        folder = self._own_folder()
        python, _ = self._libraries.python_of(folder)
        was = await self._versions(python)
        await self._change(names, False, who, f"Install {', '.join(names)}")
        text = await asyncio.to_thread(self._libraries.read_requirements, folder)
        for name in names:
            text = rules.with_library(text, name)
        await self._write(folder, text)
        now = await self._versions(python)
        self._said(
            who,
            "environment_install",
            ", ".join(names),
            [
                _library_change(n, was.get(rules.library_key(n)), None, now.get(rules.library_key(n), ""),
                                None, f"Installed {n}")
                for n in names
            ],
        )  # fmt: skip
        await self.changed()
        return {"installed": names[0]} if len(names) == 1 else {"installed": names}

    async def update(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name"}: that library to its newest version; {"all": true}: every one not pinned that has a newer
        version (a pinned one is never updated by Update all). A pinned library updated by name is pinned
        at its new version. The agent's waits for Allow."""
        folder = self._own_folder()
        documents = await asyncio.to_thread(self._s.documents)
        items = await asyncio.to_thread(self._library_items, documents)
        if isinstance(body, dict) and body.get("all"):
            chosen = [i for i in items if i.more["latest"] and not i.more["pinned"]]
            if not chosen:
                return {"updated": []}
        else:
            key = rules.library_key(rules.check_library(_field(body, "name")))
            chosen = [i for i in items if rules.library_key(i.name) == key and i.more["installed"]]
            if not chosen:
                raise NotFound("That library is not installed in the project's Python.")
        specs = [f"{i.name}=={i.more['latest']}" if i.more["latest"] else i.name for i in chosen]
        await self._change(specs, True, who, "Update " + ", ".join(i.name for i in chosen))
        python, _ = self._libraries.python_of(folder)
        now = {
            rules.library_key(n): v
            for n, v in (await asyncio.to_thread(self._libraries.installed, python)).items()
        }
        text = await asyncio.to_thread(self._libraries.read_requirements, folder)
        for item in chosen:
            key = rules.library_key(item.name)
            if item.more["pinned"] and key in now:
                text = rules.with_pin(text, item.name, now[key])
            if self._latest.get(key) and now.get(key) == self._latest[key]:
                del self._latest[key]
        await self._write(folder, text)
        changes = []
        for item in chosen:
            old, new = item.more["version"], now.get(rules.library_key(item.name), "")
            said = f"Updated {item.name} from {old} to {new}" if old and new else f"Updated {item.name}"
            changes.append(_library_change(item.name, old, None, new, None, said if old != new else ""))
        self._said(who, "environment_update", ", ".join(i.name for i in chosen), changes)
        await self.changed()
        return {
            "updated": [{"name": i.name, "version": now.get(rules.library_key(i.name), "")} for i in chosen]
        }

    async def uninstall(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A library taken out of the project's Python and of requirements.txt (the agent's: on Allow)."""
        item = await self._library(_field(body, "name"))
        folder = self._own_folder()
        python, own = self._libraries.python_of(folder)
        await self._approvals.allowed(
            who,
            subject=item.name,
            action="remove a library",
            detail=f"Remove {item.name}",
            otherwise="the library is as it was",
        )
        if own and item.more["installed"]:
            code, out = await self._libraries.uninstall(python, [item.name])
            if code != 0:
                raise Refused(f"{item.name} could not be removed.", details=out[-2000:])
        text = await asyncio.to_thread(self._libraries.read_requirements, folder)
        await self._write(folder, rules.without_library(text, item.name))
        change = raised("library", item.name, {"library": {"version": item.more["version"]}}, None,
                        f"Removed the library {item.name}")  # fmt: skip
        self.ws.audit.write(who, "environment_uninstall", item.name, **change)
        await self.changed()
        return {"removed": True, "kind": "library", "name": item.name}


def _library_change(
    name: str, was: str | None, was_pinned: bool | None, now: str, pinned: bool | None, words: str
) -> dict[str, Any]:
    """The change log's event for a library (services/changes.py raised): its version and whether it is
    pinned, before and after, by name. {} when neither moved and nothing is said."""

    def shape(version: str | None, pin: bool | None) -> dict[str, Any] | None:
        if version is None:
            return None
        return {"library": {"version": version} | ({} if pin is None else {"pinned": "yes" if pin else "no"})}

    return raised("library", name, shape(was or None, was_pinned), shape(now, pinned), words)


def read_documents(paths: Iterable[str], read: Callable[[str], tuple[str, str, float]]) -> list[Document]:
    """The documents' code as the rules read it: a notebook's code and SQL cells by number, a script whole.
    One that cannot be read is skipped."""
    found: list[Document] = []
    for path in paths:
        try:
            text, full, _ = read(path)
        except (OSError, ValueError, LookupError):
            continue
        if full.endswith(".ipynb"):
            try:
                cells = notebooks.read_document(text)[0]
            except ValueError:
                continue
            code = tuple((c.number, notebooks.code_of(c)) for c in cells if c.kind in ("code", "sql", "dax"))
        elif full.endswith(".py"):
            code = ((None, text),)
        else:
            continue
        found.append(Document(full, _title(full), code))
    return found


def sources_from(
    *,
    datasets: Any,
    sab_projects: Any,
    workbench: Any,
    sessions: Any,
    structures: Any,
    settings: Any,
    cards: Any,
    models: Any,
    document_paths: Callable[[], list[str]],
    read: Callable[[str], tuple[str, str, float]],
    project_names: Callable[[str], list[str]],
    project_file: Callable[[str, str], str | None],
    remove_file: Callable[[str], None] | None = None,
    touched: Callable[[str], Awaitable[Any]] | None = None,
) -> Sources:
    """The Environment's sources from the app's own services (bootstrap.py hands them over once built)."""

    def project() -> Mapping[str, Any] | None:
        found = sab_projects.state().get("project")
        return found if isinstance(found, dict) else None

    def folder() -> str | None:
        current = project()
        return str(current["folder"]) if current and current.get("folder") else None

    def canvases() -> list[tuple[str, str]]:
        where = folder()
        if where is None:
            return []
        found = []
        try:
            names = [n for n in project_names(where) if n.endswith(CANVAS_SUFFIX)]
        except OSError:
            return []
        for name in names:
            text = project_file(where, name)
            if text is not None:
                found.append((name[: -len(CANVAS_SUFFIX)], text))
        return found

    def endpoints() -> tuple[str, list[Any]]:
        where = folder()
        text = project_file(where, "API.py") if where else None
        if where is None or text is None:
            return "", []
        path = where.rstrip("/\\") + "/API.py"
        try:
            return path, list(local_api.parse(text).endpoints)
        except (ValueError, SyntaxError):
            return path, []

    return Sources(
        origin_of=datasets.origins.get,
        kernel_document=workbench.document_of,
        table_document=datasets.origins.document,
        project=project,
        kernels=workbench.running_kernels,
        kernel_variables=workbench.variables,
        kernel_call=workbench.kernel_call,
        sessions=sessions.listing,
        session_values=sessions.values,
        open_python=sessions.open_table,
        documents=lambda: read_documents(document_paths(), read),
        canvases=canvases,
        endpoints=endpoints,
        cards=cards.on_tables,
        relationships=lambda: models.model.relationships,
        structures=structures,
        settings=settings,
        remove_file=remove_file,
        close_table=datasets.close,
        rename_table=datasets.rename,
        save_project=sab_projects.save,
        touched=touched,
    )


def _flat(answers: list[Any]) -> list[Any]:
    return [name for answer in answers if isinstance(answer, list) for name in answer]


def _field(body: Any, key: str) -> Any:
    return body.get(key) if isinstance(body, dict) else None


def _title(path: str | None) -> str:
    return (path or "").replace("\\", "/").rsplit("/", 1)[-1]


def _size_words(row: Mapping[str, Any]) -> str:
    size = str(row.get("size") or "")
    kind = str(row.get("type") or "")
    if size.isdigit() or size.replace(",", "").isdigit():
        word = "key" if kind == "dict" else "character" if kind == "str" else "item"
        return rules.count(int(size.replace(",", "")), word)
    return size


def _made_in(documents: list[Document], names: set[str]) -> dict[str, str]:
    """Where code makes each variable: the last cell that assigns it ("data.ipynb · cell 2")."""
    from swissarmybench.domain.cell_facts import facts

    made: dict[str, str] = {}
    for document in documents:
        for number, source in document.cells:
            try:
                assigned = set(facts(source).makes) & names
            except Exception:  # noqa: S112 (code that does not read makes nothing)
                continue
            for name in assigned:
                made[name] = document.title + (f" · cell {number}" if number is not None else "")
    return made
