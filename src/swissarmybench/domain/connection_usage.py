"""A connection's usage (the owner, 2026-11-16: "a connections page where all the active connections are
presented as cards and I can click one to see all the references in the workbench that use that
connection and an overview of its configuration and how many times it has been called this session").

  [REFERENCES]  where a connection is named in the user's notebooks, scripts and Streamlit apps:
                a SQL cell (`%%sql Warehouse`), a DAX cell (`%%dax Finance/Sales model`), and in Python
                `sab.sql("Warehouse", ...)`, `sab.dax("Finance/...", ...)`, `sab.read("Orders API", ...)`,
                `sab.blade("Warehouse")`, `sab.connection("Warehouse")` (read with ast: a name inside
                another string or a comment is no use); a table's read-only cell's load says the same
                (`orders = sab.sql('Warehouse', ...)`) and is told apart; a canvas block is a use when
                the cell it links to is one.
  [CALLS]       the calls this session, by kind (catalog, query, read, test, connect), the last one's
                time and whether it worked. Memory only; the clock is the caller's.
  [STATUS]      a cheap word for a card, never a run: failing (its last call or its catalog failed),
                needs (a password is in none of its places), works (its last call worked), ready.
  [SETTINGS]    a form's settings as the configuration shows them: never one that names a password.
  [KIND FACTS]  what the pages draw for a connection's kind, as data (kind_facts, group_facts,
                secrets_legend): its group on the Connections page, how code names it, which detail actions
                it has, whether a query tab runs on it, its tree's group icon. The pages name no kind (the
                owner's front end / back end rule): a new kind is added here, never in web/.

Standard library only; no I/O (the files' text is given).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import dataverse, lakes, notebooks, powerbi, table_cells

CALL_KINDS: tuple[str, ...] = ("catalog", "query", "read", "test", "connect")
STATUSES: tuple[str, ...] = ("works", "ready", "needs", "failing", "resuming")
# The client's functions that take a connection's name first (sab.sql(name, query) ...).
_NAMED_FIRST = {
    "sql": "sab.sql",
    "dax": "sab.dax",
    "read": "sab.read",
    "blade": "sab.blade",
    "connection": "sab.connection",
}
_KEYWORDS = ("connection", "connection_name", "dataset_name", "name")
_MODULE = "swissarmybench"
_MAGIC = re.compile(r"^\s*[%!]")
_SECRETISH = re.compile(r"pass|pwd|secret|token|credential|api[_-]?key|private", re.IGNORECASE)
_IN_STRING = re.compile(r"(pass|pwd|secret|token|credential|api[_-]?key)\w*\s*[=:]", re.IGNORECASE)
MAX_LINE = 160
MAX_REFERENCES = 500


def same_name(a: str, b: str) -> bool:
    """Two spellings of one connection's name, as the client finds it (spaces squeezed, any case)."""
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _base(named: str) -> str:
    """The connection a cell's or a call's words name: `Finance/Sales model` -> `Finance`;
    `Warehouse -> orders` (a SQL cell that keeps its result) -> `Warehouse`."""
    return named.split(" -> ")[0].split("/")[0].strip()


def connection_named(named: str) -> str:
    """The connection's own name in a table's origin or a cell's words (Finance/Sales model -> Finance)."""
    return _base(named)


@dataclass(frozen=True)
class Use:
    """One use inside a piece of code: how it is written and its line."""

    how: str  # "%%sql", "%%dax", "sab.sql", "sab.dax", "sab.read", "sab.blade", "sab.connection"
    line: str


@dataclass(frozen=True)
class Reference:
    """A cell (or a canvas block, or an open grid) that uses a connection."""

    document: str  # the file's path ("" for a grid)
    title: str  # the file's name, or the grid's table
    kind: str  # notebook, script, app or grid
    how: str
    line: str
    cell: int | None = None  # the cell's own number (None: a script's main code, a grid)
    name: str | None = None  # the cell's own name
    table_cell: bool = False  # a table's read-only cell (its load names the connection)
    page: str | None = None  # a canvas's page and block
    block: str | None = None
    grid: str | None = None  # an open grid read from the connection

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "document": self.document,
            "title": self.title,
            "kind": self.kind,
            "how": self.how,
            "line": self.line,
            "cell": self.cell,
        }
        for key in ("name", "page", "block", "grid"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.table_cell:
            out["table_cell"] = True
        return out


def _short(line: str) -> str:
    text = " ".join(line.strip().split())
    return text if len(text) <= MAX_LINE else text[: MAX_LINE - 1] + "…"


def _python_tree(code: str) -> ast.Module | None:
    """The code as Python, its IPython lines (%magic, !shell) blanked so the rest still parses."""
    lines = ["" if _MAGIC.match(line) else line for line in code.split("\n")]
    try:
        return ast.parse("\n".join(lines))
    except (SyntaxError, ValueError):
        return None


def _aliases(tree: ast.Module, calls: Mapping[str, str] = _NAMED_FIRST) -> tuple[set[str], dict[str, str]]:
    """The names the module goes by here (`import swissarmybench as sab`), and its functions imported
    by name (`from swissarmybench import sql as run_sql` -> {"run_sql": "sql"})."""
    modules = {"sab", _MODULE}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _MODULE:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == _MODULE:
            for alias in node.names:
                if alias.name in calls:
                    functions[alias.asname or alias.name] = alias.name
    return modules, functions


def _named(call: ast.Call) -> str | None:
    """The text a call names its connection with: its first argument, or the keyword for it."""
    first = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg in _KEYWORDS), None)
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _python_calls(code: str, calls: Mapping[str, str] = _NAMED_FIRST) -> list[tuple[int, int, str, str]]:
    """Every call of the client's that names a connection: (line, column, how, the connection's name),
    in the code's order (ast: never in a comment or in another string)."""
    tree = _python_tree(code)
    if tree is None:
        return []
    modules, functions = _aliases(tree, calls)
    found: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        word: str | None = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules:
            word = func.attr if func.attr in calls else None
        elif isinstance(func, ast.Name):
            word = functions.get(func.id)
        named = _named(node) if word else None
        if word and named is not None and _base(named):
            found.append((node.lineno, node.col_offset, calls[word], _base(named)))
    return sorted(found, key=lambda f: (f[0], f[1]))


def python_uses(code: str, connection: str, calls: Mapping[str, str] = _NAMED_FIRST) -> list[Use]:
    """Where Python code names `connection` in a call of the client's (ast: never in a comment or in
    another string). `calls`: the client's functions that name it first (a structure's: sab.structure)."""
    lines = code.split("\n")
    return [
        Use(how, _short(lines[line - 1] if 0 < line <= len(lines) else ""))
        for line, _, how, named in _python_calls(code, calls)
        if same_name(named, connection)
    ]


def cell_connections(kind: str, source: str, named: str | None) -> list[str]:
    """The connections a cell names, each once, in its order (connection colours: a cell wears each
    one's mark): a SQL or DAX cell's by its first line, Python's by the client's calls."""
    if kind in ("sql", "dax"):
        return [_base(named)] if named and _base(named) else []
    if kind != "code":
        return []
    out: list[str] = []
    for _, _, _, name in _python_calls(source):
        if not any(same_name(name, seen) for seen in out):
            out.append(name)
    return out


def cell_uses(
    kind: str, source: str, named: str | None, connection: str, calls: Mapping[str, str] = _NAMED_FIRST
) -> list[Use]:
    """A notebook cell's uses: a SQL or DAX cell by its first line, Python by its calls."""
    if kind in ("sql", "dax") and calls is _NAMED_FIRST:
        if named and same_name(_base(named), connection):
            return [
                Use(
                    f"%%{kind}",
                    _short(notebooks.sql_line(named) if kind == "sql" else notebooks.dax_line(named)),
                )
            ]
        return []
    if kind == "code":
        return python_uses(source, connection, calls)
    return []


def notebook_references(
    path: str, title: str, text: str, connection: str, calls: Mapping[str, str] = _NAMED_FIRST
) -> list[Reference]:
    """Every cell of a notebook's file that uses the connection."""
    cells, _ = notebooks.read_document(text)
    found: list[Reference] = []
    for cell in cells:
        for use in cell_uses(cell.kind, cell.source, cell.connection, connection, calls):
            table = cell.role not in ("", "maker")
            found.append(Reference(path, title, "notebook", use.how, use.line, cell.number, cell.name, table))
    return found


def script_references(
    path: str, title: str, text: str, connection: str, calls: Mapping[str, str] = _NAMED_FIRST
) -> list[Reference]:
    """Every cell of a script that uses the connection (its main code too: no number)."""
    found: list[Reference] = []
    for cell in table_cells.parse_script(text).cells:
        if cell.html:
            continue
        for use in python_uses(cell.source, connection, calls):
            name = table_cells.marker_name(cell.title) if cell.title and not cell.role else None
            table = cell.role not in ("", "maker", "imports")
            found.append(Reference(path, title, "script", use.how, use.line, cell.number, name, table))
    return found


def document_references(
    path: str, title: str, text: str, connection: str, calls: Mapping[str, str] = _NAMED_FIRST
) -> list[Reference]:
    """A notebook's or a script's references by its kind (an app's need its cells: canvas_references)."""
    if notebooks.kind_of(path) == "notebook":
        return notebook_references(path, title, text, connection, calls)
    if notebooks.kind_of(path) == "script":
        return script_references(path, title, text, connection, calls)
    return []


# ===== the calls this session =====


@dataclass(frozen=True)
class Calls:
    counts: Mapping[str, int] = field(default_factory=dict)
    last_used: float | None = None
    last_kind: str | None = None
    last_ok: bool | None = None

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_kind": {kind: int(self.counts.get(kind, 0)) for kind in CALL_KINDS},
            "last_used": self.last_used,
            "last_kind": self.last_kind,
            "last_ok": self.last_ok,
        }


def call_kind(word: Any) -> str:
    """A call's kind as said (a run mode, a kernel's report): one of CALL_KINDS."""
    said = str(word or "").strip().lower()
    mapped = {"rows": "read", "queries": "query", "datasets": "catalog", "dax": "query", "sql": "query"}
    said = mapped.get(said, said)
    if said not in CALL_KINDS:
        raise ValueError(f"A call is one of {', '.join(CALL_KINDS)}.")
    return said


def record(calls: Calls | None, kind: str, ok: bool, at: float) -> Calls:
    """One more call of `kind` (checked by call_kind), at `at`."""
    was = calls or Calls()
    counts = dict(was.counts)
    counts[kind] = counts.get(kind, 0) + 1
    return Calls(counts, at, kind, ok)


def status(calls: Calls | None, missing: list[str], catalog_failed: bool, error: str = "") -> str:
    """The card's word: failing, resuming (a paused serverless database that is waking: its last error
    said so), needs (a password), works, ready."""
    if calls is not None and calls.last_ok is False and "is resuming" in error:
        return "resuming"
    if catalog_failed or (calls is not None and calls.last_ok is False):
        return "failing"
    if missing:
        return "needs"
    if calls is not None and calls.last_ok:
        return "works"
    return "ready"


def shown_settings(fields: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """A form's settings as the configuration lists them (name and value): one whose name speaks of a
    password, a key or a token is left out (its value may be one)."""
    out: list[dict[str, Any]] = []
    for f in fields:
        name = str(f.get("name") or f.get("key") or "")
        if not name or _SECRETISH.search(name) or _SECRETISH.search(str(f.get("key") or "")):
            continue
        value = f.get("value")
        if isinstance(value, str) and _IN_STRING.search(value):
            continue  # a connection string that carries a password
        out.append({"name": name, "value": value if isinstance(value, bool | int | float) else str(value)})
    return out


def sign_in_of(code: str, sign_ins: Iterable[Mapping[str, Any]]) -> str | None:
    """Which of a type's ways to sign in the code is (by the text only that way's code holds)."""
    for way in sign_ins:
        mark = str(way.get("mark") or "")
        if mark and mark in code:
            return str(way.get("label") or "") or None
    return None


# ===== what the pages draw for a connection's kind =====

LAKE_GROUP: str = "Lakes and SharePoint"  # the Connections page's group (the form's templates say the same)
_NO_SQL_CELL: tuple[str, ...] = (lakes.SHAREPOINT, lakes.SHAREPOINT_DOCS)  # read by code only


def reads_by_code(dialect: str | None) -> bool:
    """Whether a connection is read through its own code (sab.read) rather than a SQL session of its own:
    Dataverse, a lake, SharePoint."""
    return dataverse.is_dataverse(dialect) or lakes.is_kind(dialect)


def in_code(name: str, connection: str, dialect: str | None) -> str:
    """How code names a connection, in one line: a Power BI workspace's DAX cells, your own Python's
    sab.read, a key vault's sab.blade, a database's sab.connection and SQL cell."""
    cell = f'"{name}"' if re.search(r"\s", name) else name
    if dialect == powerbi.DIALECT:
        return f'sab.dax("{name}/<dataset>", …)  ·  %%dax {name}/<dataset>'
    if connection == "vault":
        return f'sab.blade("{name}")'
    if connection == "python" or reads_by_code(dialect):
        sql = "" if connection == "python" or dialect in _NO_SQL_CELL else f"  ·  %%sql {cell}"
        return f'sab.connection("{name}")  ·  sab.read("{name}", table){sql}'
    return f'sab.connection("{name}")  ·  %%sql {cell}'


def group_facts(tables_kind: str | None) -> dict[str, Any]:
    """A connection's tree as the pages draw it: its groups' icon, whether each group imports its own
    relationships (a Power BI dataset), whether a lone group opens by itself."""
    datasets = tables_kind == "powerbi"
    return {
        "icon": "diagram" if datasets else "folder",
        "relationships": datasets,
        "open_single": not datasets,
    }


def kind_facts(
    name: str, connection: str, dialect: str | None, tables_kind: str | None, type_label: str = ""
) -> dict[str, Any]:
    """One connection as the pages treat it, by its kind: every decision a page would otherwise make by
    naming a dialect."""
    lake = lakes.is_kind(tables_kind)
    group = {"file": "Files", "python": "Your own code"}.get(connection, "")
    if connection == "database":
        group = LAKE_GROUP if lake else "Databases"
    elif lake:
        group = LAKE_GROUP
    actions: list[str] = []
    if dialect == "sqlserver" and connection == "database":
        actions.append("import_relationships")  # its foreign keys into the ERD
    if tables_kind == "dataverse_web":
        actions.append("sql_endpoint")  # saved for the Web API: one click moves it to its SQL endpoint
    runs_queries = connection == "database" and tables_kind != "dataverse_web"
    datasets = tables_kind == "powerbi"
    return {
        "group": group,
        "in_code": in_code(name, connection, dialect),
        # A Test of it runs its own code (what each box gave), not a SQL session's connect.
        "test_reads": connection == "python" or reads_by_code(dialect),
        # A Test says what the server is: the detail is drawn again with it (SQL Server's card lines).
        "test_tells_about": dialect == "sqlserver",
        "actions": actions,
        # A query tab runs on it (Query from, the New query page): in DAX or its own SQL; its kind in words.
        "query": (
            {"dax": datasets, "type": type_label or ("Power BI workspace" if datasets else "Database")}
            if runs_queries
            else None
        ),
        "has_tables": bool(tables_kind) and tables_kind != "api",
        "on_connections_page": tables_kind != "api",  # an API has the APIs page
        "tree": group_facts(tables_kind),
    }


def secrets_legend(dialect: str | None) -> str:
    """The form's heading over a connection's secrets: an app registration's values (two ids and a secret)
    for Power BI and Dataverse, passwords for the rest."""
    return (
        "App registration" if dialect == powerbi.DIALECT or dataverse.is_dataverse(dialect) else "Passwords"
    )
