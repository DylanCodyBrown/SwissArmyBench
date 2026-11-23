"""The project's outline, ARCHITECTURE.md (rules and text in domain/project_outline.py): gathered here from
the services, metadata only.

  build    the open project's outline as markdown: its files, the connections and APIs it uses (each one's
           kind, sign-in, portability and the variables it needs by name and source), the tables it uses
           (seam A) with their columns' names and types, their steps as one DuckDB query, the data
           notebook's named cells, the lineage, the deliverables (an app's pages through services/hooks.py,
           so the base never names the extension), what it needs to run, and what is open
  write    the same text as ARCHITECTURE.md at the project folder's top, atomically and only when its
           bytes change (the user's Export outline, and the agent's `project_outline` with write)

Two seams, each a Protocol with a small default, so the branches building the real ones replace them:

  A. UsedTables   used(project) -> set[str]: the tables the project uses. Today: the open tables, the
                  ones .sab/project.json keeps, and the tables its documents name in DuckDB SQL
                  ([Connection].table). The relationship sets' "tables the project uses" replaces it.
  B. Portability  verdict(connection) -> {"portable": bool | None, "reason": str, "instead": str}: whether a
                  connection runs unchanged on a Function App or a hosted Streamlit app. Today: "Not
                  checked yet" for every connection (portable None: no guessing). The drivers branch's rule
                  replaces it.
"""

from __future__ import annotations

import ast
import posixpath
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from swissarmybench.domain import connection_sql as sql_names
from swissarmybench.domain import intellisense as lint_rules
from swissarmybench.domain import lineage as lineage_rules
from swissarmybench.domain import local_api as local_api_rules
from swissarmybench.domain import notebooks, project_paths, sab_files
from swissarmybench.domain import packages as package_rules
from swissarmybench.domain import project_outline as rules
from swissarmybench.domain import project_scope as scope_rules
from swissarmybench.domain.cell_facts import facts, piece_name
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.context_md import RelationshipFacts, code
from swissarmybench.domain.projects import data_requirements
from swissarmybench.domain.script_runs import ScriptRunError, split_arguments
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.lineage import document_cells
from swissarmybench.services.ports import Dashboards
from swissarmybench.services.workspace import NotFound, Workspace

MAX_DOCUMENTS: int = 200
REQUIREMENTS: str = "requirements.txt"
DATA_PY: str = "data.py"


class UsedTables(Protocol):
    """Seam A: the tables a project uses, by name (an open table's; `[Shop].customers` for one its
    documents name through a connection)."""

    def used(self, project: str) -> set[str]: ...


class Portability(Protocol):
    """Seam B: a connection's portability. `connection`: {name, kind, type, template, dialect, sign_in}.
    The answer: {"portable": True | False | None (not checked), "reason": words, "instead": words}."""

    def verdict(self, connection: Mapping[str, Any]) -> dict[str, Any]: ...


class NotChecked:
    """Seam B's default: no connection is judged (no guessing)."""

    def verdict(self, connection: Mapping[str, Any]) -> dict[str, Any]:
        return {"portable": None, "reason": rules.NOT_CHECKED, "instead": ""}


class CardPortability:
    """Seam B, wired: a connection card's "local" list (services/connection_usage.py, domain/portability.py's
    rule): none is portable; any is "Only works on your machine" with its reasons and what works instead."""

    def __init__(self, cards: Callable[[], Iterable[Mapping[str, Any]]]) -> None:
        self._cards = cards

    def verdict(self, connection: Mapping[str, Any]) -> dict[str, Any]:
        card = next((c for c in self._cards() if c.get("name") == connection.get("name")), None)
        if card is None:
            return NotChecked().verdict(connection)
        local = list(card.get("local") or [])
        if not local:
            return {"portable": True, "reason": "", "instead": ""}
        return {
            "portable": False,
            "reason": "; ".join(str(item.get("reason", "")) for item in local),
            "instead": "; ".join(dict.fromkeys(str(item.get("instead", "")) for item in local)),
        }


class BothTables:
    """Seam A, wired: the ERD's tables in the project (services/relationship_scope.py: open tables, the
    project's saved tables, names in its documents) and the outline's own finder ([Connection].table)."""

    def __init__(self, scope: Callable[[], set[str] | None], own: UsedTables) -> None:
        self._scope = scope
        self._own = own

    def used(self, project: str) -> set[str]:
        return (self._scope() or set()) | self._own.used(project)


class OutlineFiles(Protocol):
    """The project folder (adapters/sab_files.py's SabArchive)."""

    def files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def read_state(self, folder: str, relative: str) -> bytes | None: ...

    def write_state(self, folder: str, relative: str, body: bytes) -> bool: ...

    def real(self, path: str) -> str: ...


def bracket_name(connection: str, parts: Sequence[str]) -> str:
    return f"[{connection}]." + ".".join(parts)


def _texts_of(path: str, text: str) -> list[str]:
    """The SQL a document may name a connection's tables in: its SQL cells, and its Python's strings."""
    out: list[str] = []
    if path.endswith(".ipynb"):
        try:
            cells, _ = notebooks.read_document(text)
        except notebooks.NotebookError:
            return out
        for cell in cells:
            if cell.kind == "sql":
                out.append(cell.source)
            elif cell.kind == "code":
                out += _strings(cell.source)
    elif path.endswith(".py"):
        out += _strings(text)
    return out


def _strings(code_text: str) -> list[str]:
    try:
        tree = ast.parse(code_text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def named_tables(
    documents: Iterable[tuple[str, str]], connections: Sequence[str]
) -> list[tuple[str, tuple[str, ...]]]:
    """The connections' tables the documents name in DuckDB SQL: (connection, the rest of its name)."""
    found: dict[tuple[str, ...], tuple[str, tuple[str, ...]]] = {}
    for path, text in documents:
        for sql in _texts_of(path, text):
            if not sql_names.might_name(sql, connections):
                continue
            try:
                refs = sql_names.references(sql_names.quote_brackets(sql, connections), connections)
            except (sql_names.ConnectionSqlError, ValueError):
                continue
            for ref in refs:
                found.setdefault(ref.key, (ref.connection, ref.parts))
    return [found[k] for k in sorted(found)]


class ProjectTables:
    """Seam A's default: the open tables, the ones .sab/project.json keeps, and the connections' tables
    the project's documents name in DuckDB SQL."""

    def __init__(
        self,
        open_tables: Callable[[], Iterable[str]],
        saved: Callable[[], Iterable[str]],
        documents: Callable[[str], Iterable[tuple[str, str]]],
        connections: Callable[[], Sequence[str]],
    ) -> None:
        self._open = open_tables
        self._saved = saved
        self._documents = documents  # a project folder's documents: (path, text)
        self._connections = connections

    def used(self, project: str) -> set[str]:
        names = set(self._open()) | set(self._saved())
        for connection, parts in named_tables(self._documents(project), self._connections()):
            names.add(bracket_name(connection, parts))
        return names


def _relative(path: str | None, folder: str, real: Callable[[str], str] | None = None) -> str | None:
    """A path as the project's own (relative to its folder); None outside it (domain/project_paths.py)."""
    return project_paths.relative_in(path, folder, real)


def _lower(words: str) -> str:
    """Run settings' words for a variable's source, as the outline says them."""
    if words == "This computer":
        return "this computer's environment"
    return words[:1].lower() + words[1:]


def _words(source: Mapping[str, Any]) -> str:
    """Where a password or variable comes from, in words, never its value."""
    origin = str(source.get("from") or "")
    if origin == "vault":
        return f"the key vault {code(source.get('vault') or '')}"
    return {
        "keyring": "this computer's keyring",
        "environment": "this computer's environment",
        "env": "this computer's environment",
        "value": "a plain value",
        "missing": "no source on this computer",
    }.get(origin, origin or "this computer's environment")


_QUERY = re.compile(r"\bselect\b|\bfrom\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Read:
    makes: tuple[str, ...]
    reads: tuple[str, ...]
    imported: frozenset[str]
    from_data: frozenset[str]  # names it imports from the project's data.py
    sources: tuple[tuple[str, str], ...]


def saved_dashboards(dashboards: Dashboards) -> list[dict[str, Any]]:
    """The open project's saved dashboards (the Deliverables section): each one's name and its last
    version's cards."""
    out = []
    for listed in dashboards.names():
        body = dashboards.read(str(listed["name"])) or {"versions": []}
        last = body["versions"][-1] if body["versions"] else {}
        out.append({"name": listed["name"], "cards": last.get("cards") or []})
    return out


class ProjectOutline:
    def __init__(
        self,
        ws: Workspace,
        files: OutlineFiles,
        *,
        project: Callable[[], dict[str, Any] | None],
        mode: Callable[[], Mapping[str, Any]],
        connections: Callable[[], list[dict[str, Any]]],
        usage: Callable[[str], dict[str, Any]],
        table_cells: Callable[[], Awaitable[dict[str, Any]]],
        origin_of: Callable[[str], Origin],
        kernel_document: Callable[[str | None], str | None],
        relationships: Callable[[], Mapping[str, Any]],
        dashboards: Callable[[], list[dict[str, Any]]],
        run_settings: Callable[[str], dict[str, Any]],
        app_pages: Callable[[str, str], list[tuple[str, list[tuple[str, int]]]]],
        used_tables: UsedTables | None = None,
        portability: Portability | None = None,
        scope_tables: Callable[[], set[str] | None] | None = None,
    ) -> None:
        self.ws = ws
        self._files = files
        self._project = project
        self._mode = mode
        self._connections = connections
        self._usage = usage
        self._table_cells = table_cells
        self._origin_of = origin_of
        self._kernel_document = kernel_document
        self._model = relationships
        self._dashboards = dashboards
        self._run_settings = run_settings
        # SEAM (the Streamlit extension, services/hooks.py): an app's pages and the cells each block links.
        self._app_pages = app_pages
        # SEAM A (relationship sets): the tables the project uses.
        self.used_tables: UsedTables = used_tables or ProjectTables(
            lambda: [i.name for i in ws.store.all()],
            lambda: [str(t["name"]) for t in (self._project() or {}).get("tables") or []],
            self.documents_text,
            lambda: [str(c["name"]) for c in self._connections()],
        )
        if scope_tables is not None:  # with the ERD's tables in the project (services/relationship_scope.py)
            self.used_tables = BothTables(scope_tables, self.used_tables)
        self._connection_names: list[str] = []  # as of the outline being gathered
        self._variables: set[str] = set()  # the open tables' Python names
        # SEAM B (drivers): each connection's portability.
        self.portability: Portability = portability or NotChecked()

    # ===== the project's files =====

    def _open(self) -> dict[str, Any]:
        project = self._project()
        if not project or not project.get("folder"):
            raise NotFound("No project is open: open or start one first.")
        return project

    def _listed(self, folder: str) -> list[dict[str, Any]]:
        # API.py is the project's local sandbox API: its endpoints are a deliverable of their own, not a
        # script.
        listed = [
            d for d in scope_rules.documents(self._files.files(folder)) if d["path"] != local_api_rules.FILE
        ]
        return listed[:MAX_DOCUMENTS]

    def _text(self, folder: str, relative: str) -> str | None:
        try:
            raw = self._files.read_state(folder, relative)
        except (OSError, ValueError):
            return None
        return None if raw is None else raw.decode("utf-8-sig", "replace")

    def documents_text(self, folder: str) -> list[tuple[str, str]]:
        """The project's notebooks and scripts (not the made ones): (path in the project, text)."""
        out = []
        for d in self._listed(folder):
            if d["kind"] in ("notebook", "script") and not d["made"]:
                text = self._text(folder, d["path"])
                if text is not None:
                    out.append((str(d["path"]), text))
        return out

    # ===== gathering =====

    def _overview(self, project: Mapping[str, Any], folder: str) -> rules.Overview:
        mode = self._mode() or {}
        name = str(project.get("name") or "")
        entries = [
            rules.FileEntry(path, scope_rules.kind_of(path) or "file", False)
            for path, _, _ in self._files.files(folder)
        ]
        known = {d["path"]: d for d in self._listed(folder)}
        entries = [rules.FileEntry(e.path, e.kind, bool(known.get(e.path, {}).get("made"))) for e in entries]
        return rules.Overview(
            name,
            str(mode.get("title") or ""),
            str(mode.get("name") or ""),
            str(mode.get("deliverable") or ""),
            rules.purpose(self._text(folder, sab_files.README_FILE), sab_files.readme(name)),
            tuple(entries),
        )

    def _origin(self, name: str, folder: str) -> tuple[str, str, str | None]:
        """A table's origin in words (names as code), its kind and its source (a connection, a file in the
        project) for the lineage."""
        origin = self._origin_of(name)
        if origin.kind in ("connection", "file") and origin.connection:  # a file connection's file too
            connection = origin.connection.split("/")[0]
            place = ".".join(p for p in (origin.place or ()) if p)
            how = f": {code(place)}" if place else (", a DAX query" if origin.dax else ", a query")
            return f"from connection {code(origin.connection)}{how}", "connection", connection
        if origin.kind in ("file", "dropped"):
            inside = _relative(origin.path, folder, self._files.real)
            if inside:
                sheet = f", sheet {code(origin.sheet)}" if origin.sheet else ""
                return f"from file {code(inside)}{sheet}", "file", inside
            base = posixpath.basename((origin.path or origin.filename or "").replace("\\", "/"))
            return f"from a file outside the project ({code(base)})", "file", None
        if origin.kind == "python":
            document = _relative(self._kernel_document(origin.kernel), folder, self._files.real)
            return (f"made by Python in {code(document)}" if document else "made by Python"), "python", None
        words = {"paste": "pasted into the app", "query": "from a query in the app's + tab"}
        return words.get(origin.kind, "where it came from is not known"), origin.kind, None

    async def _tables(self, project: Mapping[str, Any], folder: str) -> list[rules.TableFacts]:
        used = self.used_tables.used(folder)
        listing = {t["name"]: t for t in (await self._table_cells()).get("tables") or []}
        saved = {str(t["name"]): t for t in project.get("tables") or []}
        out: list[rules.TableFacts] = []
        open_sources: set[tuple[str, str]] = set()
        for name in sorted(used, key=str.casefold):
            info = self.ws.store.get(name)
            if info is None:
                continue
            origin, kind, source = self._origin(name, folder)
            place = self._origin_of(name).place
            if kind == "connection" and source and place:
                open_sources.add((source.casefold(), str(place[-1]).casefold()))
            cell = listing.get(name) or {}
            out.append(
                rules.TableFacts(
                    name,
                    origin,
                    kind,
                    source,
                    tuple((c.name, c.type) for c in info.columns),
                    tuple(str(w) for w in cell.get("step_words") or ()),
                    cell.get("query"),
                    cell.get("problem"),
                )
            )
        for name in sorted(used, key=str.casefold):
            if self.ws.store.get(name) is not None:
                continue
            if name in saved:
                entry = saved[name]
                out.append(
                    rules.TableFacts(
                        name,
                        f"from {code(entry.get('from') or entry.get('kind'))} (not open now)",
                        str(entry.get("kind") or "unknown"),
                    )
                )
                continue
            if name.startswith("["):
                connection, _, rest = name[1:].partition("].")
                if (connection.casefold(), rest.rsplit(".", 1)[-1].casefold()) in open_sources:
                    continue
                words = f"from connection {code(connection)}, named in DuckDB SQL"
                out.append(rules.TableFacts(name, words, "named", connection))
        return sorted(out, key=lambda t: t.name.casefold())

    def _sources(
        self, folder: str, tables: Sequence[rules.TableFacts]
    ) -> tuple[list[rules.SourceFacts], list[tuple[str, tuple[str, ...]]]]:
        """The connections and APIs the project uses, and the passwords each has no source for."""
        by_table: dict[str, list[str]] = {}
        for t in tables:
            if t.source and t.origin_kind in ("connection", "named"):
                by_table.setdefault(t.source.casefold(), []).append(t.name)
        naming: dict[str, set[str]] = {}  # the documents that name a connection's tables in DuckDB SQL
        for path, text in self.documents_text(folder):
            for connection, _ in named_tables([(path, text)], self._connection_names):
                naming.setdefault(connection.casefold(), set()).add(path)
        out: list[rules.SourceFacts] = []
        missing: list[tuple[str, tuple[str, ...]]] = []
        for card in sorted(self._connections(), key=lambda c: str(c["name"]).casefold()):
            name = str(card["name"])
            if card.get("connection") == "vault":
                continue
            try:
                usage = self._usage(name)
            except (NotFound, ValueError, LookupError):
                continue
            documents = sorted(
                {
                    inside
                    for r in usage.get("references") or []
                    if r.get("kind") != "grid" and (inside := _relative(str(r.get("document") or ""), folder))
                }
                | naming.get(name.casefold(), set()),
                key=str.casefold,
            )
            tables_here = sorted(by_table.get(name.casefold(), []), key=str.casefold)
            if not documents and not tables_here:
                continue
            config = usage.get("configuration") or {}
            variables = {
                str(v["name"]): rules.Variable(str(v["name"]), _words(v))
                for v in [*(config.get("passwords") or []), *(config.get("variables") or [])]
                if v.get("name")
            }
            api = card.get("tables_kind") == "api"
            facts = {
                "name": name,
                "kind": "api" if api else config.get("kind") or card.get("connection"),
                "type": card.get("type") or config.get("type") or "",
                "template": card.get("template"),
                "dialect": card.get("dialect"),
                "sign_in": config.get("sign_in"),
            }
            said = self.portability.verdict(facts)
            portable = said.get("portable")
            out.append(
                rules.SourceFacts(
                    name,
                    str(facts["kind"] or ""),
                    str(facts["type"] or ""),
                    config.get("sign_in"),
                    rules.Verdict(
                        portable if isinstance(portable, bool) else None,
                        str(said.get("reason") or ""),
                        str(said.get("instead") or ""),
                    ),
                    tuple(variables[k] for k in sorted(variables, key=str.casefold)),
                    tuple(documents) + tuple(tables_here),
                    tuple(t.split("].", 1)[-1] if t.startswith("[") else t for t in tables_here)
                    if api
                    else (),
                )
            )
            if card.get("missing"):
                missing.append((name, tuple(sorted(str(m) for m in card["missing"]))))
        return out, missing

    def _relationships(self) -> tuple[RelationshipFacts, ...]:
        model: Mapping[str, Any] = self._model() or {}
        found = [
            RelationshipFacts(
                str(r.get("from")),
                tuple(str(c) for c in r.get("from_columns") or ()),
                str(r.get("to")),
                tuple(str(c) for c in r.get("to_columns") or ()),
                str(r.get("kind") or "many-to-one"),
                r.get("active") is not False,
            )
            for r in model.get("relationships") or ()
        ]
        return tuple(
            sorted(found, key=lambda r: (r.from_table.casefold(), r.to_table.casefold(), r.from_columns))
        )

    def _cells(self, path: str, text: str) -> tuple[lineage_rules.DocCell, ...]:
        """A document's cells; a script with no cell markers is one cell, its whole text."""
        try:
            found = document_cells(path, text)
        except (notebooks.NotebookError, ValueError):
            return ()
        if not found and path.endswith(".py") and text.strip():
            return (lineage_rules.DocCell(1, "code", text),)
        return found

    def _named_cells(self, folder: str) -> list[rules.CellFacts]:
        text = self._text(folder, scope_rules.DATA_NOTEBOOK)
        if text is None:
            return []
        out = []
        for cell in self._cells(scope_rules.DATA_NOTEBOOK, text):
            if not cell.name:
                continue
            read = self._read(cell)
            out.append(
                rules.CellFacts(
                    scope_rules.DATA_NOTEBOOK,
                    cell.number,
                    cell.name,
                    read.makes,
                    tuple(sorted(set(read.reads), key=str.casefold)),
                    tuple(sorted(set(read.sources))),
                )
            )
        return out

    def _read(self, cell: lineage_rules.DocCell) -> _Read:
        """What a cell makes and reads, and the sources it names: the lineage's reading, with DuckDB SQL
        read by sqlglot (a SQL cell's, and the queries in a Python cell's strings)."""
        read = lineage_rules.read_cell(cell)
        reads = list(read.reads)
        sources = list(read.sources)
        if cell.kind == "sql":
            tables, used = rules.sql_tables(cell.code, self._connection_names)
            reads = tables if not cell.connection else []
            sources += [("connection", c) for c in used]
        elif cell.kind == "code":
            for text in _strings(cell.code):
                if not _QUERY.search(text):
                    continue
                tables, used = rules.sql_tables(text, self._connection_names)
                reads += [t for t in tables if t in self._variables]
                sources += [("connection", c) for c in used]
        makes = tuple(n for n in read.makes if n not in read.imported and n not in read.from_data)
        return _Read(
            makes, tuple(dict.fromkeys(reads)), read.imported, read.from_data, tuple(dict.fromkeys(sources))
        )

    def _document_flow(
        self, cells: Sequence[lineage_rules.DocCell]
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]:
        """What a document reads (from elsewhere) and makes, over its cells."""
        makes: dict[str, None] = {}
        reads: dict[str, None] = {}
        sources: dict[tuple[str, str], None] = {}
        imported: set[str] = set()
        for cell in cells:
            read = self._read(cell)
            imported |= read.imported
            for name in [*read.from_data, *read.reads]:
                if name not in makes and name not in imported:
                    reads[name] = None
            makes.update(dict.fromkeys(read.makes))
            sources.update(dict.fromkeys(read.sources))
        return (
            tuple(sorted(reads, key=str.casefold)),
            tuple(sorted(makes, key=str.casefold)),
            tuple(sorted(sources)),
        )

    def _deliverables(self, folder: str) -> list[rules.Deliverable]:
        out: list[rules.Deliverable] = []
        labels: dict[tuple[str, int], str] = {}
        flows: dict[str, tuple[lineage_rules.DocCell, ...]] = {}
        listed = self._listed(folder)
        for d in listed:
            if d["kind"] not in ("notebook", "script") or d["made"]:
                continue
            text = self._text(folder, d["path"])
            if text is None:
                continue
            cells = self._cells(d["path"], text)
            flows[d["path"]] = cells
            for cell in cells:
                title = cell.name or piece_name(cell.code, cell.number)
                labels[(d["path"], cell.number)] = f"{d['path']} @cell{cell.number} ({title})"
            if d["path"] == scope_rules.DATA_NOTEBOOK:
                continue
            reads, makes, sources = self._document_flow(cells)
            out.append(rules.Deliverable(str(d["kind"]), str(d["path"]), reads, makes, sources=sources))
        for d in listed:
            if d["kind"] != "app":
                continue
            text = self._text(folder, d["path"])
            if text is None:
                continue
            full = scope_rules.inside(folder, d["path"])
            try:
                pages = self._app_pages(full, text)
            except ValueError:
                pages = []
            linked: list[str] = []
            page_facts: list[rules.PageFacts] = []
            linked_cells: list[lineage_rules.DocCell] = []
            for page_name, blocks in pages:
                shown = []
                for document, number in blocks:
                    inside = _relative(document, folder) or posixpath.basename(document.replace("\\", "/"))
                    linked.append(inside)
                    shown.append(labels.get((inside, number), f"{inside} @cell{number}"))
                    linked_cells += [c for c in flows.get(inside, ()) if c.number == number]
                page_facts.append(rules.PageFacts(page_name, tuple(shown)))
            reads, _, _ = self._document_flow(linked_cells)
            out.append(
                rules.Deliverable(
                    "app",
                    str(d["path"]),
                    reads,
                    (),
                    tuple(page_facts),
                    tuple(sorted(set(linked), key=str.casefold)),
                )
            )
        for board in sorted(self._dashboards(), key=lambda b: str(b.get("name")).casefold()):
            cards = [c for c in board.get("cards") or [] if isinstance(c, dict)]
            reads = tuple(sorted({str(c["dataset"]) for c in cards if c.get("dataset")}, key=str.casefold))
            kinds = tuple(sorted({str(c.get("kind") or "card") for c in cards}))
            out.append(rules.Deliverable("dashboard", str(board.get("name")), reads, kinds))
        api_text = self._text(folder, local_api_rules.FILE)
        if api_text is not None:
            api = local_api_rules.parse(api_text)
            if api.endpoints:
                reads = tuple(sorted({n for e in api.endpoints for n in e.connections}, key=str.casefold))
                said = tuple(f"{e.method} {api.settings.base_path}{e.path}" for e in api.endpoints)
                out.append(rules.Deliverable("api", local_api_rules.FILE, reads, said))
        order = {"notebook": 0, "script": 1, "app": 2, "api": 3, "dashboard": 4}
        return sorted(out, key=lambda d: (order.get(d.kind, 9), d.name.casefold()))

    def _packages(self, folder: str) -> tuple[str, ...]:
        needed: list[str] = []
        data_py = self._text(folder, DATA_PY)
        if data_py:
            needed += data_requirements(data_py)
        documents = self.documents_text(folder)
        own = {posixpath.splitext(p)[0].replace("/", ".") for p, _ in documents if p.endswith(".py")}
        own |= {"data"}  # data.py, data.ipynb's export
        for path, text in documents:
            for cell in self._cells(path, text):
                if cell.kind != "code":
                    continue
                for module in facts(cell.code).modules:
                    top = module.split(".")[0]
                    if top in own or module in own:
                        continue
                    if top == "swissarmybench":
                        needed.append("swissarmybench")
                    elif not package_rules.provided(module) and not rules.standard(module):
                        needed.append(package_rules.pip_name(module)[0])
                if "sab." in cell.code:
                    needed.append("swissarmybench")
        return rules.packages(self._text(folder, REQUIREMENTS), needed)

    def _scripts(self, folder: str) -> list[rules.ScriptRun]:
        out = []
        for d in self._listed(folder):
            if d["kind"] != "script" or d["made"]:
                continue
            try:
                settings = self._run_settings(scope_rules.inside(folder, d["path"]))
            except (NotFound, ScriptRunError, ValueError, OSError):
                settings = {}
            try:
                count = len(split_arguments(str(settings.get("arguments") or "")))
            except ScriptRunError:
                count = 0
            variables = tuple(
                rules.Variable(str(v["name"]), _lower(str(v.get("words") or "this computer's environment")))
                for v in settings.get("variables") or []
                if v.get("name")
            )
            out.append(rules.ScriptRun(str(d["path"]), count, variables))
        return out

    def _problems(self, folder: str) -> list[tuple[str, int]]:
        """The lint's errors and warnings in each document (Python's compile and the small ast pass:
        the same here as on every computer)."""
        out = []
        for path, text in self.documents_text(folder):
            found: list[Any] = []
            if path.endswith(".ipynb"):
                try:
                    cells, _ = notebooks.read_document(text)
                except notebooks.NotebookError:
                    continue
                sources = [c.source for c in cells if c.kind == "code"]
                known: set[str] = set(self._variables)
                for i, source in enumerate(sources):
                    later = set().union(*(lint_rules.names_used(s) for s in sources[i + 1 :]))
                    found += lint_rules.lint(source, known, later, notebook=True)
                    known |= lint_rules.names_made(source)
            else:
                found = lint_rules.lint(text, self._variables)
            count = sum(1 for p in found if p.severity in ("error", "warning"))
            if count:
                out.append((path, count))
        return out

    def _fixes(self, project: Mapping[str, Any]) -> list[tuple[str, str]]:
        words = {
            "no_connection": "its connection is not on this computer",
            "needs_password": "its connection needs a password on this computer",
            "no_file": "its file is not where it was",
            "not_run": "the notebook that makes it has not run",
            "no_rows": "its rows were not kept",
        }
        out = []
        for p in project.get("problems") or []:
            state = str(p.get("state") or "")
            out.append((str(p.get("table")), words.get(state, "it could not be read again")))
        return sorted(out, key=lambda f: f[0].casefold())

    async def gather(self) -> rules.Outline:
        project = self._open()
        folder = str(project["folder"])
        self._connection_names = [str(c["name"]) for c in self._connections()]
        self._variables = {variable_name(i.name) for i in self.ws.store.all()}
        tables = await self._tables(project, folder)
        sources, missing = self._sources(folder, tables)
        return rules.Outline(
            self._overview(project, folder),
            tuple(sources),
            tuple(tables),
            self._relationships(),
            tuple(self._named_cells(folder)),
            tuple(self._deliverables(folder)),
            self._packages(folder),
            tuple(self._scripts(folder)),
            rules.Issues(tuple(self._fixes(project)), tuple(missing), tuple(self._problems(folder))),
        )

    async def build(self) -> str:
        """The open project's outline as markdown."""
        return rules.render(await self.gather())

    async def write(self, who: str = "user") -> dict[str, Any]:
        """ARCHITECTURE.md at the project folder's top, only when its bytes change: the text, its path in
        the project, and whether it was written."""
        project = self._open()
        text = await self.build()
        written = self._files.write_state(str(project["folder"]), rules.FILE_NAME, text.encode("utf-8"))
        self.ws.audit.write(who, "project_outline", rules.FILE_NAME, written=written)
        return {"file": rules.FILE_NAME, "path": scope_rules.inside(str(project["folder"]), rules.FILE_NAME),
                "written": written, "text": text}  # fmt: skip
