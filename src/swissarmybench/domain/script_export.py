"""Export as one Python script (the owner, 2026-11-15: "export any data analysis notebook as an inline
python automation where all connections, vault logic, and data transformations are bundled into one
python script that is just downloadable"; and: "runnable as standalone from any Python terminal").

A notebook or a script becomes ONE .py file that runs with plain `python <file>` in any Python 3.10 or
later, with no Swiss Army Bench: unattended on a schedule, in an Azure Function's timer trigger, on
any machine. Pure rules, no I/O:

  requirements  what its code imports, as pip requirements (REQUIREMENTS in the script, checked
                before anything else is imported; `--install` installs the missing ones with pip,
                in the same Python, only when asked). A PEP 723 header says the same, for uv
  settings      every environment variable it reads, one per line, each with where it came from in
                the app (the keyring, a key vault's entry, a secret blade, a plain value). A
                secret's value is never written: only a plain value, which is no secret
  vaults        a key vault a password comes from, written out as its own code (the vault blade's):
                read at run time when the variable is not set already (an Azure Function's Key Vault
                reference sets it), with a managed identity or the app registration in the
                environment, as DefaultAzureCredential does
  connections   each connection and blade the document uses, written out as a small function of
                its own code: a database's Connect, a file's path, a Power BI workspace's sign-in
                and DAX, a connection from the user's own Python (Connect, Read a table), a blade
                (the Excel starters' functions). `%%sql <conn>` and `%%dax <conn>/<dataset>` cells
                and `sab.sql`, `sab.dax`, `sab.read`, `sab.blade` and `sab.connection` call them
  tables        each table's read-only cell: its load, then the grid's steps as one DuckDB query. A
                table the app cannot read again (pasted, dropped, sent from Python) is a stub that
                raises "FILL IN: ...". No rows are ever written
  cells         the code cells in order, Markdown as comments. What only shows something (HTML
                cells, Streamlit's, display(), a cell's last bare expression, sab.push) is left
                out with a line that says so. IPython's own lines are translated where Python has
                the same (%pip, %env, %cd, %time) or refused, naming the cell
  check         the script compiles, holds no saved password's value and no row

The script is laid out as: the header, REQUIREMENTS and their check, SETTINGS, the helpers the
connections need, the vaults, the connections and blades, `run()` (the cells), and `main()`, which
an Azure Function's timer trigger calls; `python <file>` runs `cli()`: logging to stdout, an exit
code that is not 0 on failure.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from swissarmybench.domain import cell_facts, dataverse, python_connections, table_cells
from swissarmybench.domain import script_runtime as runtime
from swissarmybench.domain.blades import env_name_for_secret, env_settings
from swissarmybench.domain.codegen import python_string, variable_name
from swissarmybench.domain.connections import env_name_for
from swissarmybench.domain.script_runtime import Secret
from swissarmybench.domain.streamlit_use import uses_streamlit, usual_name

SUFFIX: str = "_automation.py"
REQUIRES_PYTHON: str = ">=3.10"
# What a cell's `sab.<name>(...)` becomes, or that it only shows something in the app.
_CALLS: dict[str, str] = {"sql": "run_sql", "dax": "run_dax", "read": "read_table"}
_MADE: frozenset[str] = frozenset({"blade", "connection"})
_SHOWS: frozenset[str] = frozenset(
    {"push", "visualizations", "sandbox", "watch", "unwatch", "load", "complete"}  # sandbox: the old name
)
_PACKAGE_NAMES: frozenset[str] = frozenset({"swissarmybench", "swissarmygrid"})
# A cell's last bare expression that only shows a value (its methods), or display() anywhere.
_SHOWING_METHODS: frozenset[str] = frozenset(
    {"head", "tail", "describe", "sample", "info", "show", "style", "to_html", "plot", "hist"}
)
_SHOWING_CALLS: frozenset[str] = frozenset({"display"})
_PASTED = re.compile(r"\bFROM \(VALUES\b[\s\S]*?\) AS pasted\(")
_NO_LOAD = re.compile(
    r"^# (?P<table>.+?) was (?:made outside this file|dropped on the page|pasted into the grid|opened from) ",
    re.M,
)
_MAGIC = re.compile(r"^(?P<indent>\s*)(?P<mark>%%|%|!|\?)(?P<rest>.*)$")
_HELP = re.compile(r"^\s*(?:\?\S|\S.*\?\??\s*$)")
_FUTURE = re.compile(r"^from __future__ import [^\n]*\n?", re.M)
_TARGET = re.compile(r"^[A-Za-z_]\w*$")


class ScriptExportError(ValueError):
    """A document that cannot be exported as sent (the message says why)."""


# ===== what the service gathers =====


@dataclass(frozen=True)
class Piece:
    """A connection, vault or blade the script writes out: its own code, as saved in the app."""

    name: str
    kind: str  # the blade's kind: sql, other, vault, secret, snippet, analysis
    connection: str | None  # database, file, python, vault, or None (a blade)
    code: str
    variable: str
    dialect: str = "other"
    read: str | None = None  # a connection from your own Python: its Read a table box
    secrets: tuple[Secret, ...] = ()
    vault_mapping: Mapping[str, str] = field(default_factory=dict)  # variable -> entry
    vault_all: bool = False
    env_names: tuple[str, ...] = ()  # a secret blade's variables


@dataclass(frozen=True)
class ExportCell:
    kind: str  # code, sql, dax, html, markdown
    source: str
    connection: str | None = None  # a SQL cell's connection (`Shop -> orders`), a DAX cell's dataset
    role: str = ""
    table: str | None = None
    number: int | None = None
    name: str | None = None


@dataclass(frozen=True)
class Problem:
    """Something that cannot be exported: where, and why."""

    where: str  # "cell 4", or "Orders API"
    why: str
    cell: int | None = None  # the cell's index in the document

    def to_json(self) -> dict[str, object]:
        return {"where": self.where, "why": self.why}

    def __str__(self) -> str:
        return f"{self.where}: {self.why}"


@dataclass(frozen=True)
class Exported:
    text: str
    requirements: tuple[str, ...]
    settings: tuple[dict[str, object], ...]  # each variable, where it came from, whether it is a secret
    problems: tuple[Problem, ...]  # not exported (with `stub`: each such cell is a stub)
    stubs: tuple[str, ...]  # FILL IN: the tables and cells written as stubs
    skipped: tuple[str, ...]  # what was left out, in words
    places: tuple[tuple[int, int, str], ...]  # each cell's first and last line in the code, and its label
    code: str = ""  # a notebook's code cells one after another (what the checks read); a script: its text

    @property
    def python(self) -> str:
        """The Python the checks read: the script, or the notebook's code cells."""
        return self.code or self.text


def file_name(document: str | None, suffix: str = SUFFIX) -> str:
    """The export's file name: the notebook's or script's, as `<name>_automation.py` (or .ipynb)."""
    stem = re.split(r"[\\/]", document or "")[-1]
    stem = re.sub(r"\.(ipynb|py)$", "", stem, flags=re.I)
    return f"{module_name(stem)}{suffix}"


def module_name(stem: str) -> str:
    """A name Python can import the script by (an Azure Function's `import orders_automation`)."""
    words = re.sub(r"\W+", "_", stem.strip()).strip("_").lower()
    return words if words and not words[0].isdigit() else f"job_{words}".rstrip("_")


def script_cells(text: str) -> list[ExportCell]:
    """A Workbench script's cells: its Tables group's, its main code, its `# %%` cells."""
    parsed = table_cells.parse_script(text)
    return [
        ExportCell(
            "html" if c.html else "code",
            c.source,
            role=c.role,
            table=c.table,
            number=c.number,
            name=c.title or None,
        )
        for c in parsed.cells
    ]


# ===== reading a cell =====


@dataclass
class _Cell:
    """One cell as the script writes it."""

    label: str
    lines: list[str] = field(default_factory=list)  # Python, at run()'s level
    problems: list[str] = field(default_factory=list)
    uses: list[str] = field(default_factory=list)  # connections and blades it names
    requirements: list[str] = field(default_factory=list)  # %pip install
    settings: list[Secret] = field(default_factory=list)  # %env with a secret's name
    skipped: list[str] = field(default_factory=list)
    stub: str | None = None  # a table that cannot be read again


def sql_line(connection: str | None) -> tuple[str | None, str | None]:
    """A SQL or DAX cell's connection as the cell holds it: (the connection, the result's name).
    `Shop -> orders --grid`, `"My shop"`, `-> orders`, none."""
    if not connection:
        return None, None
    try:
        words = shlex.split(connection)
    except ValueError:
        words = connection.split()
    words = [w for w in words if w != "--grid"]
    target = None
    if "->" in words:
        at = words.index("->")
        after = words[at + 1 :]
        target = after[0] if len(after) == 1 and _TARGET.match(after[0]) else None
        words = words[:at]
    return " ".join(words) or None, target


@dataclass(frozen=True)
class QueryCell:
    """A SQL or DAX cell as its export calls it: the connection as the call names it (`Shop`,
    `Finance/Sales model`), the connection's own name, the query (its uses line taken off) and its
    result's name (`-> name` on its line, else the cell's own name when that is a Python name)."""

    kind: str  # sql or dax
    name: str
    base: str
    query: str
    target: str | None

    @property
    def call(self) -> str:
        return "run_dax" if self.kind == "dax" else "run_sql"


def query_cell(cell: ExportCell, default: str | None = None) -> QueryCell:
    """A SQL or DAX cell read as its export calls it (`default`: the connection %sql_connect named)."""
    named, target = sql_line(cell.connection)
    if cell.kind == "sql" and named is None:
        named = default
    if named is None:
        raise ScriptExportError(f"the {cell.kind.upper()} cell names no connection")
    base = named.split("/", 1)[0].strip() if cell.kind == "dax" else named
    query = table_cells.split_uses(cell.source, sql=True)[1].strip()
    if target is None and cell.name and _TARGET.match(cell.name.strip()):
        target = cell.name.strip()
    return QueryCell(cell.kind, named, base, query, target)


# The page values a query names (`{{ region }}`), read by the same text the page runs (sab_queries.py).
_PAGE: dict[str, object] = {"re": re, "Any": object}
exec(compile(runtime.PAGE_PARTS, "sab_queries.py", "exec"), _PAGE)  # noqa: S102 (our own text, read once)


def page_split(query: str, dax: bool = False) -> list[str | tuple[str]]:
    """A query as its text and its page values (`("region",)`), as sab_queries.py reads it."""
    found = _PAGE["page_parts"]
    return list(found(query, dax))  # type: ignore[operator]


def page_names(query: str, dax: bool = False) -> list[str]:
    """The page values a SQL or DAX query names: `{{ name }}` outside its strings and comments."""
    found = _PAGE["page_names"]
    return list(found(query, dax))  # type: ignore[operator]


def _byte_offsets(source: str) -> list[int]:
    """Where each line starts, in characters (ast gives a line and a UTF-8 byte column)."""
    starts = [0]
    for line in source.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    return starts


def _at(source: str, starts: list[int], line: int, byte_col: int) -> int:
    text = source.split("\n")[line - 1]
    return starts[line - 1] + len(text.encode("utf-8")[:byte_col].decode("utf-8", "replace"))


def _literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _translate_magics(cell: _Cell, source: str) -> str:
    """IPython's own lines as Python where Python has the same; the rest refused, by its line."""
    out: list[str] = []
    lines = source.split("\n")
    first = next((line for line in lines if line.strip()), "")
    if first.strip().startswith("%%"):
        magic = first.strip()[2:].split(" ", 1)[0]
        if magic in ("time", "capture", "timeit"):
            lines = [line for line in lines if line is not first] if lines else lines
            cell.skipped.append(f"{cell.label}: %%{magic} left out (the cell runs as it is)")
        else:
            cell.problems.append(
                f"%%{magic} is IPython's own cell magic: the cell is not Python, and plain Python has no same"
            )
            return source
    for number, line in enumerate(lines, start=1):
        found = _MAGIC.match(line)
        if found is None or _string_line(source, number):
            out.append(line)
            continue
        indent, mark, rest = found.group("indent"), found.group("mark"), found.group("rest").strip()
        words = rest.split()
        word = words[0] if words else ""
        if mark == "?" or (_HELP.match(line) and mark != "!"):
            out.append(f"{indent}{'pass  ' if indent else ''}# help ({line.strip()}): left out")
            continue
        if (mark == "!" and word == "pip") or (mark == "%" and word in ("pip", "conda")):
            wanted = [w for w in words[2:] if not w.startswith("-")] if len(words) > 1 else []
            cell.requirements += wanted
            out.append(f"{indent}{'pass  ' if indent else ''}# {line.strip()}: in REQUIREMENTS")
            continue
        if mark == "%" and word in (
            "matplotlib",
            "load_ext",
            "reload_ext",
            "autoreload",
            "config",
            "sql_connections",
            "sab_connections",
            "sag_connections",
            "who",
            "whos",
        ):
            out.append(f"{indent}{'pass  ' if indent else ''}# {line.strip()}: only the notebook's, left out")
            continue
        if mark == "%" and word in ("sql_connect", "sab_connect", "sag_connect"):
            out.append(f"{indent}{'pass  ' if indent else ''}# {line.strip()}: the later SQL cells name it")
            continue
        if mark == "%" and word in ("time", "timeit") and len(words) > 1:
            body = rest[len(word) :].strip()
            if word == "timeit":
                body = " ".join(w for w in body.split() if not re.match(r"^-[nr]\d*$", w))
            out.append(f"{indent}{body}")
            continue
        if mark == "%" and word == "env" and len(words) > 1:
            said = rest[len(word) :].strip()
            name, _, value = said.partition("=") if "=" in said else said.partition(" ")
            name, value = name.strip(), value.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", name):
                cell.problems.append(f"line {number}: {line.strip()} does not name a variable")
                out.append(line)
                continue
            if not value:
                out.append(f"{indent}print(os.environ.get({name!r}))")
            elif python_connections.looks_secret(name):
                # A secret typed into the notebook: never written here. The script asks for it.
                cell.settings.append(Secret(name, name, "notebook"))
                out.append(
                    f"{indent}{'pass  ' if indent else ''}# %env {name}=...: a secret, read from SETTINGS (never written)"
                )
            else:
                out.append(f"{indent}os.environ.setdefault({name!r}, {value!r})")
            continue
        if mark == "%" and word == "cd" and len(words) > 1:
            out.append(f"{indent}os.chdir({rest[len(word) :].strip()!r})")
            continue
        what = "a shell command" if mark == "!" else "IPython's own"
        cell.problems.append(f"line {number}: {line.strip()} is {what}: plain Python has no same")
        out.append(line)
    return "\n".join(out)


def _string_line(source: str, number: int) -> bool:
    """The line sits inside a text that started on an earlier line."""
    try:
        return number in cell_facts.string_lines(source)
    except Exception:
        return False


def _aliases(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """The names the package is imported under (`sab`), and its functions imported by name."""
    modules: set[str] = set()
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _PACKAGE_NAMES:
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _PACKAGE_NAMES:
            if node.module in _PACKAGE_NAMES:
                for alias in node.names:
                    functions[alias.asname or alias.name] = alias.name
    return modules, functions


def _package_call(node: ast.Call, modules: set[str], functions: Mapping[str, str]) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in modules:
        return func.attr
    if isinstance(func, ast.Name) and func.id in functions:
        return functions[func.id]
    return None


def _showing(node: ast.expr) -> bool:
    """An expression that only shows a value: no call in it, display(), or df.head() and the like."""
    if not any(isinstance(n, ast.Call) for n in ast.walk(node)):
        return not isinstance(node, ast.Constant)  # a text on a line of its own is a docstring
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SHOWING_CALLS:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in _SHOWING_METHODS:
            return True
    return False


def _rewrite(cell: _Cell, source: str) -> str:
    """The cell's Python with every package call written out, its imports of the package taken out,
    and what only shows something left out."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        cell.problems.append(f"line {error.lineno}: not Python ({error.msg})")
        return source
    modules, functions = _aliases(tree)
    starts = _byte_offsets(source)
    edits: list[tuple[int, int, str]] = []

    def span(node: ast.AST) -> tuple[int, int]:
        start = _at(source, starts, node.lineno, node.col_offset)  # type: ignore[attr-defined]
        end = _at(source, starts, node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]
        return start, end

    statements = {id(s.value): s for s in ast.walk(tree) if isinstance(s, ast.Expr)}
    top = {id(s) for s in tree.body}

    def gone(node: ast.stmt, words: str) -> str:
        """A statement left out: a comment, or `pass` where a block needs a statement."""
        return f"# {words}" if id(node) in top else f"pass  # {words}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = node.names if isinstance(node, ast.Import) else []
            ours = (
                isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _PACKAGE_NAMES
            ) or any(a.name.split(".")[0] in _PACKAGE_NAMES for a in names)
            if not ours:
                continue
            if isinstance(node, ast.ImportFrom) and node.module not in _PACKAGE_NAMES:
                cell.problems.append(
                    f"line {node.lineno}: `from {node.module} import ...` needs Swiss Army Bench itself "
                    "(only sab.sql, sab.dax, sab.read, sab.blade and sab.connection are written out)"
                )
                continue
            if isinstance(node, ast.Import) and any(
                a.name.split(".")[0] in _PACKAGE_NAMES and "." in a.name for a in names
            ):
                cell.problems.append(
                    f"line {node.lineno}: `import {', '.join(a.name for a in names)}` needs Swiss Army "
                    "Bench itself"
                )
                continue
            kept = [a for a in names if a.name.split(".")[0] not in _PACKAGE_NAMES]
            said = "Swiss Army Bench: what it gave is written out here"
            edits.append(
                (
                    *span(node),
                    f"{ast.unparse(ast.Import(names=kept))}  # {said}" if kept else gone(node, said),
                )
            )
            continue
        if not isinstance(node, ast.Call):
            continue
        called = _package_call(node, modules, functions)
        if called is None:
            if isinstance(node.func, ast.Name) and node.func.id in _SHOWING_CALLS and id(node) in statements:
                edits.append(
                    (
                        *span(statements[id(node)]),
                        gone(statements[id(node)], "display(...): shown in the notebook only"),
                    )
                )
            continue
        first = _literal(node.args[0]) if node.args else None
        if called in _SHOWS:
            if id(node) in statements:
                edits.append(
                    (
                        *span(statements[id(node)]),
                        gone(statements[id(node)], f"sab.{called}(...): it shows in the app, left out"),
                    )
                )
            else:
                cell.problems.append(
                    f"line {node.lineno}: sab.{called}(...) gives a value only Swiss Army Bench has"
                )
            continue
        if called in _CALLS or called in _MADE:
            if first is None:
                cell.problems.append(
                    f"line {node.lineno}: sab.{called}(...) must name its connection as a text "
                    '(sab.sql("Shop", ...)), so the script knows which one to write out'
                )
                continue
            base = first.split("/", 1)[0].strip() if called == "dax" else first
            if base not in cell.uses:
                cell.uses.append(base)
            func_start, func_end = span(node.func)
            edits.append((func_start, func_end, _CALLS.get(called, called)))
            continue
        cell.problems.append(f"line {node.lineno}: sab.{called}(...) needs Swiss Army Bench itself")
    # The last bare expression only shows its value in a notebook.
    body = tree.body
    if body and isinstance(body[-1], ast.Expr) and _showing(body[-1].value):
        start, end = span(body[-1])
        if not any(s <= start < e for s, e, _ in edits):
            shown = " ".join(source[start:end].split())[:60]
            edits.append((start, end, gone(body[-1], f"{shown}: shown in the notebook only")))
    # Any other use of the package's name is something only it has.
    edited = [(s, e) for s, e, _ in edits]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in modules and isinstance(node.ctx, ast.Load):
            start, _ = span(node)
            if not any(s <= start < e for s, e in edited):
                cell.problems.append(f"line {node.lineno}: `{node.id}` here needs Swiss Army Bench itself")
                break
    for start, end, text in sorted(edits, reverse=True):
        source = source[:start] + text + source[end:]
    return source


def _top_level_problems(source: str) -> list[str]:
    """What cannot sit inside run(): `import *`, and a return, yield or await outside a function."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[str] = []
    inner: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            inner.update(id(n) for n in ast.walk(node) if n is not node)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            found.append(f"line {node.lineno}: `from {node.module} import *` (name what it imports)")
        elif isinstance(node, ast.Return | ast.Yield | ast.YieldFrom | ast.Await) and id(node) not in inner:
            word = type(node).__name__.lower().replace("yieldfrom", "yield from")
            found.append(f"line {node.lineno}: `{word}` outside a function")
    return found


def _connection_names(source: str, code_names: Mapping[str, str], made: set[str]) -> list[str]:
    """The connections a cell reads by their variable (the Workbench's `shop`), not made above."""
    needs = table_cells.facts(source).needs
    return [name for name in needs if name in code_names and name not in made]


def _table_stub(cell: ExportCell, source: str) -> tuple[str, str] | None:
    """A table's read-only cell that cannot read the table again: its stub and what stays after it
    (the grid's steps, run once the load is filled in). None: it reads its table."""
    found = _NO_LOAD.search(source)
    pasted = _PASTED.search(source) is not None
    if not found and not pasted:
        return None
    table = cell.table or (found.group("table") if found else "the table")
    var = variable_name(table)
    if found is not None:
        line = source[found.start() :].split("\n", 1)[0]
        why = f"{table} was " + line[2:].split(" was ", 1)[1].strip()
    else:
        why = f"{table} was pasted into the grid"
    kept: list[str] = []
    try:
        tree = ast.parse(source)
        lines = source.split("\n")
        for statement in tree.body:
            text = "\n".join(lines[statement.lineno - 1 : statement.end_lineno])
            if _PASTED.search(text):
                continue
            kept.append(text)
    except SyntaxError:
        kept = []
    stub = (
        f"# ===== FILL IN: {table} =====\n"
        f"# {why.rstrip('. ')}: the app cannot read it again, and no rows are written here.\n"
        f"# Write the code that reads it ({var} = ...) in place of the line below.\n"
        f'raise FillIn("FILL IN: {table} has no load. Write the code that reads it ({var} = ...) in '
        f'run(), cell {cell.number if cell.number is not None else "?"}.")'
    )
    return stub, "\n".join(kept)


# ===== the pieces: connections, vaults and blades, written out =====


def _func_name(prefix: str, name: str) -> str:
    return f"{prefix}_{module_name(name) or 'piece'}"


def _wraps(code: str) -> bool:
    """The code can sit inside a function as it is."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    if _top_level_problems(code):
        return False
    return not any(isinstance(n, ast.Global | ast.Nonlocal) for n in ast.walk(tree))


def _uses_secret(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "secret(" in code
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "secret"
        for n in ast.walk(tree)
    )


def _secret_map(piece: Piece) -> str:
    named = {s.name: s.variable for s in piece.secrets if s.where != "value"}
    return "{" + ", ".join(f"{k!r}: {v!r}" for k, v in named.items()) + "}"


def _body(code: str, ending: Sequence[str], before: Sequence[str] = ()) -> str:
    code = _FUTURE.sub("", code).strip("\n")
    lines = [*before, code, *ending]
    return cell_facts.indented("\n".join(line for line in lines if line is not None))


def _last_as_return(code: str, fallback: str) -> str:
    """A box whose value is its last expression (the app's rule): that line returned, else `fallback`."""
    code = _FUTURE.sub("", code).strip("\n")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return f"{code}\nreturn {fallback}"
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        lines = code.split("\n")
        head = lines[: last.lineno - 1]
        expression = "\n".join(lines[last.lineno - 1 : last.end_lineno])
        return "\n".join([*head, f"return ({expression})", *lines[last.end_lineno :]])
    return f"{code}\nreturn {fallback}"


def _exec_fallback(piece: Piece, constant: str, label: str) -> str:
    secret = f"secrets_of({piece.name!r}, {_secret_map(piece)})"
    return (
        f"    # Its code cannot sit inside a function (global, or import *): it runs as the app runs it.\n"
        f'    names = {{"__name__": "__blade__", "secret": {secret}}}\n'
        f'    exec(compile({constant}, {label!r}, "exec"), names)  # noqa: S102 (its own saved code)\n'
        + (
            f'    return names[{piece.variable!r}], names.get("names")'
            if piece.kind == "vault"
            else f"    return names[{piece.variable!r}]"
        )
    )


def _piece(piece: Piece) -> tuple[str, str]:
    """A piece as a function of its own: (its name, its text)."""
    what = {
        "database": f"a database connection ({piece.dialect} SQL)"
        if piece.dialect not in ("other", "dax")
        else "a database connection",
        "file": "a file connection: its code gives the path DuckDB reads",
        "python": "a connection from your own Python: Connect, then Read a table",
        "vault": "a key vault: its code gives get(name)",
    }.get(piece.connection or "", "a blade")
    if piece.dialect == "dax":
        what = "a Power BI workspace: its sign-in, then DAX on one of its datasets"
    if dataverse.is_dataverse(piece.dialect):
        what = "a Dataverse environment: its sign-in, its tables read through the Web API, SQL on its SQL endpoint"
    prefix = "vault" if piece.kind == "vault" else "connect" if piece.connection else "blade"
    name = _func_name(prefix, piece.name)
    head = f'@functools.cache\ndef {name}():\n    """{piece.name}: {what}. Its own code, as saved in the app."""\n'
    if piece.kind == "snippet":
        return (
            name,
            f'def {name}():\n    """{piece.name}: a snippet\'s text."""\n    return {python_string(piece.code)}\n',
        )
    if piece.kind == "secret":
        names = ", ".join(repr(n) for n in piece.env_names)
        checks = "\n".join(f"    setting({n!r}, {piece.name + ' asks for it'!r})" for n in piece.env_names)
        return (
            name,
            f'def {name}():\n    """{piece.name}: a secret blade: its values, from SETTINGS."""\n{checks}\n    return [{names}]\n',
        )
    azure = runtime.azure_vault_url(piece.code) if piece.kind == "vault" else None
    if azure is not None:
        # Azure Key Vault: the standard library's sign-in and REST call, so the script needs nothing
        # installed for it (an Azure Function's managed identity; azure-identity only when it is there).
        how, parts = runtime.azure_sign_in(piece.code)
        said = {"managed": "its managed identity", "you": "you"}[how]
        lines = [
            f"@functools.cache\ndef {name}():",
            f'    """{piece.name}: an Azure Key Vault ({azure}), signed in to as {said} and read with Key',
            '    Vault\'s REST call (see azure_token): only "get secret" is needed, never list."""',
        ]
        if any("secret(" in expression for expression in parts.values()):
            lines.append(f"    secret = secrets_of({piece.name!r}, {_secret_map(piece)})")
        held = ", ".join(f'"{k}": lambda: {v}' for k, v in parts.items())
        lines.append(f'    sign_in = {{"how": {how!r}' + (f", {held}" if held else "") + "}")
        lines.append(
            f"    return (lambda entry: azure_secret({piece.name!r}, {azure!r}, entry, sign_in)), None"
        )
        return name, "\n".join(lines) + "\n"
    before: list[str] = []
    if piece.connection == "python":
        variables = [s.variable for s in piece.secrets]
        before.append(f"prepare({piece.name!r}, {variables!r})")
    if _uses_secret(piece.code) or (piece.read and _uses_secret(piece.read)):
        before.append(f"secret = secrets_of({piece.name!r}, {_secret_map(piece)})")
    if not _wraps(piece.code):
        constant = f"CODE_{module_name(piece.name).upper()}"
        text = f"{constant} = {python_string(piece.code)}\n\n\n{head}{_exec_fallback(piece, constant, f'<{piece.name}>')}\n"
        return name, text
    if piece.kind == "vault":
        lister = "names" if "names" in table_cells.facts(piece.code).made else "None"
        ending = [f"return {piece.variable}, {lister}"]
    elif _reads(piece):
        read = piece.read or 'raise ValueError("This connection has no Read a table box.")'
        inner = _last_as_return(read, "rows")
        reader = 'def read(schema, table, limit):\n    """Its Read a table box."""\n' + cell_facts.indented(
            inner
        )
        ending = ["", "", reader, "", f"return {piece.variable}, read"]
    else:
        ending = [f"return {piece.variable}"]
    return name, head + _body(piece.code, ending, before) + "\n"


def _reads(piece: Piece) -> bool:
    """A connection that reads a table by its own code: the user's own Python (its Read a table box),
    or a Dataverse environment (its Web API read)."""
    return piece.connection == "python" or dataverse.is_dataverse(piece.dialect)


# ===== the script's own helpers (written in only when used) =====


def _code_settings(code: str, label: str) -> list[Secret]:
    """The environment variables a cell's own code reads, by a name written in it."""
    return [
        Secret(read.name, read.name, "code", blade=label, required=read.required)
        for read in python_connections.env_reads(code)
        if not read.name.startswith("SWISSARMY")
    ]


# ===== the script =====


@dataclass(frozen=True)
class Block:
    """One step of the document, in order: a cell's Python (at the top level), or its Markdown."""

    label: str
    lines: tuple[str, ...]
    markdown: bool = False


@dataclass(frozen=True)
class Plan:
    """The one ordered list both renderings are made from: the script, and the notebook."""

    title: str
    source: str
    blocks: tuple[Block, ...]
    pieces: tuple[Piece, ...]
    settings: tuple[Secret, ...]
    extra: tuple[str, ...]
    problems: tuple[Problem, ...]
    stubs: tuple[str, ...]
    skipped: tuple[str, ...]
    clients: tuple[tuple[str, str], ...] = ()  # (module, code): an API_<name>.py the code imports, inline


def plan(
    title: str,
    source: str | None,
    cells: Sequence[ExportCell],
    pieces: Mapping[str, Piece],
    code_names: Mapping[str, str],
    stub: bool = False,
    clients: Sequence[tuple[str, str]] = (),
) -> Plan:
    """The document as steps: each cell translated (its connections' calls written out, what only
    shows left out, IPython's lines translated or refused), the pieces it uses, the settings they
    read. `pieces`: every connection, vault and blade by its name (the service gives those
    `references` named, and the vaults their passwords come from); `code_names`: each connection's
    variable in the Workbench (shop -> Shop). `stub`: a cell that cannot be exported is a stub that
    raises FILL IN, and the rest is exported. `clients`: each API client Add API made that the code
    imports, as (module, its code to paste: services/apis.py `inline`); it travels inside the export,
    so `import API_Orders` still works, and the variables it reads are settings."""
    by_name = {name.casefold(): piece for name, piece in pieces.items()}
    problems: list[Problem] = []
    stubs: list[str] = []
    skipped: list[str] = []
    used: list[str] = []
    extra: list[str] = []
    settings: list[Secret] = []
    blocks: list[Block] = []
    default: str | None = None
    made: set[str] = set()
    usual = usual_name(tuple(c.source for c in cells if c.kind == "code"))
    script = (source or "").lower().endswith(".py")

    def use(name: str, label: str, index: int) -> str | None:
        piece = by_name.get(name.casefold())
        if piece is None:
            problems.append(Problem(label, f"{name} is not a connection or blade the app has", index))
            return None
        if piece.kind == "analysis":
            problems.append(
                Problem(label, f"{piece.name} is an analysis blade: it runs only in the app", index)
            )
            return None
        if piece.name not in used:
            used.append(piece.name)
        return piece.name

    for index, cell in enumerate(cells):
        label = (
            f"cell {cell.number}"
            if cell.number is not None
            else "the main code"
            if script and cell.kind == "code"
            else f"cell {index + 1}"
        )
        if cell.role == "transformations" and cell.table:
            label += f": {cell.table}, its load and then the grid's steps as one DuckDB query"
        elif cell.name:
            label += f" ({cell.name})"
        if cell.role in ("tables", "table") or not cell.source.strip():
            continue  # the Tables group's headings: the app's own
        if cell.kind == "markdown":
            blocks.append(Block(label, tuple(cell.source.strip().split("\n")), markdown=True))
            continue
        if cell.kind == "html":
            skipped.append(f"{label}: an HTML cell only shows a design")
            blocks.append(
                Block(label, (f"# {label}: an HTML cell, a design shown in the notebook: left out",))
            )
            continue
        if cell.kind in ("sql", "dax"):
            try:
                asked = query_cell(cell, default)
            except ScriptExportError as error:
                problems.append(Problem(label, str(error), index))
                continue
            found = use(asked.base, label, index)
            if found is None:
                continue
            name = found if cell.kind == "sql" else f"{found}{asked.name[len(asked.base) :]}"
            target = asked.target
            result = target or "_"
            lines = [f"{result} = {asked.call}({name!r}, {python_string(asked.query)})"]
            if target is None:
                lines.insert(
                    0, "# The cell names no result (no -> name, no cell name): IPython keeps it as _"
                )
            made.add(result)
            blocks.append(Block(label, tuple(lines)))
            continue
        working = _Cell(label)
        held = table_cells.split_uses(cell.source)[1].strip("\n")
        if held.lstrip().startswith(("%%sql", "%%sab", "%%sag", "%%dax")):
            problems.append(
                Problem(label, "a SQL cell written as a code cell: open it in the Workbench once", index)
            )
            continue
        if held.lstrip().startswith("%%html"):
            skipped.append(f"{label}: an HTML cell only shows a design")
            continue
        if uses_streamlit(held, usual):
            skipped.append(f"{label}: it calls Streamlit, so it shows a page")
            blocks.append(
                Block(label, (f"# {label}: it calls Streamlit (a page shown in the app): left out",))
            )
            continue
        # %sql_connect: the SQL cells after it run on that connection.
        for line in held.split("\n"):
            found_connect = re.match(r"^\s*%(?:sql|sab|sag)_connect\s+(.+)$", line)
            if found_connect:
                try:
                    default = " ".join(shlex.split(found_connect.group(1))) or default
                except ValueError:
                    default = found_connect.group(1).strip() or default
        stub_of = _table_stub(cell, held) if cell.role == "transformations" else None
        before: list[str] = []
        if stub_of is not None:
            stub_text, held = stub_of
            stubs.append(cell.table or label)
            before = stub_text.split("\n")
        translated = _translate_magics(working, held)
        rewritten = _rewrite(working, translated) if not working.problems else translated
        working.problems += _top_level_problems(rewritten)
        if working.problems:
            for said in working.problems:
                problems.append(Problem(label, said, index))
            if stub:
                stubs.append(label)
                why = working.problems[0].replace('"', "'")
                filled = [
                    f"# ===== FILL IN: {label} =====",
                    *(f"# {said}" for said in working.problems),
                    *(f"# {line}".rstrip() for line in held.split("\n")),
                    f'raise FillIn("FILL IN: {label} could not be exported ({why}). Write it in Python here.")',
                ]
                blocks.append(Block(label, tuple(filled)))
            continue
        for name in working.uses:
            use(name, label, index)
        extra += working.requirements
        settings += working.settings
        settings += _code_settings(rewritten, label)
        skipped += working.skipped
        opened = []
        for variable in _connection_names(rewritten, code_names, made):
            found = use(code_names[variable], label, index)
            if found is not None:
                opened.append(f"{variable} = connection({found!r})  # the Workbench's {variable}")
        made.update(table_cells.facts(rewritten).made)
        body = _FUTURE.sub("", rewritten).strip("\n")
        blocks.append(Block(label, (*before, *opened, *([body] if body.strip() else []))))
    # The vaults the used pieces' passwords come from, and their own.
    for name in list(used):
        for secret in by_name[name.casefold()].secrets:
            if secret.where in ("vault", "every") and secret.vault and secret.vault not in used:
                if by_name.get(secret.vault.casefold()) is None:
                    why = f"its {secret.variable} comes from the key vault {secret.vault}, which the app does not have"
                    problems.append(Problem(name, why))
                    continue
                used.append(by_name[secret.vault.casefold()].name)
    ordered = [by_name[n.casefold()] for n in used]
    for piece in ordered:
        settings += list(piece.secrets)
        if piece.kind == "secret":
            settings += [Secret(n, n, "typed", vault=piece.name) for n in piece.env_names]
        # A certificate or keystore file mapped to a variable (the file itself never travels).
        files = [m["variable"] for m in env_settings(piece.code)] if piece.connection else []
        settings += [Secret(v, v, "file", blade=piece.name, required=False) for v in files]
        settings += [
            Secret(r.name, r.name, "environment", blade=piece.name, required=False)
            for r in python_connections.env_reads(piece.code, piece.read)
            if not r.required and r.name not in {s.variable for s in piece.secrets} and r.name not in files
        ]
    inline = tuple((module, _FUTURE.sub("", code).strip("\n") + "\n") for module, code in clients)
    for module, code in inline:
        settings += [
            Secret(r.name, r.name, "api", blade=f"{module}.py", required=False)
            for r in python_connections.env_reads(code)
        ]
    return Plan(
        title,
        source or title,
        tuple(blocks),
        tuple(ordered),
        tuple(settings),
        tuple(extra),
        tuple(problems),
        tuple(dict.fromkeys(stubs)),
        tuple(skipped),
        inline,
    )


@dataclass(frozen=True)
class _Shared:
    """What both renderings hold, as text: the requirements, the settings, the helpers, the pieces."""

    requirements: dict[str, str]
    requirements_text: str  # REQUIREMENTS and their check
    settings_text: str  # SETTINGS, SETTINGS_FROM, REQUIRED, FROM_VAULTS
    helpers: str  # setting(), check_settings(), secrets_of(), prepare(), from_vault()
    pieces: tuple[str, ...]  # each connection, vault and blade as its function
    registry: str  # MADE, VARIABLES, VAULTS, READERS, connection(), and the SQL, DAX and Read helpers
    inlined: str  # what is written out, in words
    clients: tuple[str, ...] = ()  # each API client, inline (its code, then what makes its import work)


def _shared(made: Plan) -> _Shared:
    pieces = made.pieces
    has_vault = any(p.kind == "vault" for p in pieces)
    texts: list[str] = []
    registry_made: list[str] = []
    readers: list[str] = []
    vaults: list[str] = []
    variables: list[str] = []
    for piece in pieces:
        name, text = _piece(piece)
        texts.append(text.rstrip("\n"))
        if piece.kind == "vault":
            vaults.append(f"    {piece.name!r}: {name},")
            registry_made.append(f"    {piece.name!r}: lambda: load_vault({piece.name!r}),")
        elif _reads(piece):
            registry_made.append(f"    {piece.name!r}: lambda: {name}()[0],")
            readers.append(f"    {piece.name!r}: {name},")
        else:
            registry_made.append(f"    {piece.name!r}: {name},")
        variables.append(f"    {piece.name!r}: {piece.variable!r},")
    helpers = [runtime.SETTINGS_HELPERS.strip("\n")]
    if any(p.connection == "python" for p in pieces):
        helpers.append(runtime.PREPARE.strip("\n"))
    vaulted = has_vault or any(s.where in ("vault", "every") for s in made.settings)
    helpers.append((runtime.VAULT_HELPERS if vaulted else runtime.NO_VAULTS).strip("\n"))
    if any(p.kind == "vault" and runtime.azure_vault_url(p.code) for p in pieces):
        helpers.append(runtime.AZURE_HELPERS.strip("\n"))
    registry: list[str] = []
    all_text = "\n".join(line for block in made.blocks if not block.markdown for line in block.lines)
    if pieces:
        registry += [
            runtime.LOAD_VAULT.strip("\n"),
            "# Each connection or blade by its name, as the notebook names it.\n"
            "MADE: dict[str, Callable[[], Any]] = {\n" + "\n".join(registry_made) + "\n}\n"
            "VARIABLES: dict[str, str] = {\n" + "\n".join(variables) + "\n}\n"
            "VAULTS: dict[str, Callable[[], Any]] = {\n"
            + "\n".join(vaults)
            + ("\n" if vaults else "")
            + "}"
            + (
                "\nREADERS: dict[str, Callable[[], Any]] = {\n" + "\n".join(readers) + "\n}"
                if readers
                else ""
            ),
            runtime.MADE_HELPERS.strip("\n"),
        ]
        if "run_sql(" in all_text or "run_dax(" in all_text:
            registry.append(runtime.SQL_HELPERS.strip("\n"))
        if "run_dax(" in all_text:
            registry.append(runtime.DAX_HELPERS.strip("\n"))
        if "read_table(" in all_text:
            registry.append(runtime.READ_HELPERS.strip("\n"))
    # What the requirements are read from: the pieces' code and the cells (the helpers import only
    # what those need: pandas for a query's table, duckdb for a file's or a table's SQL).
    scan = "\n\n".join([*texts, *(code for _, code in made.clients), all_text])
    if any("def run_sql(" in r for r in registry):
        scan += "\nimport pandas\n"
        if any(
            p.connection in ("file", None) for p in pieces if p.kind not in ("vault", "secret", "snippet")
        ):
            scan += "import duckdb\n"
    requirements = runtime.requirements_of(scan, made.extra)
    for module, _ in made.clients:  # travels inline: not a package to install
        requirements.pop(module, None)
    for module in ("pytds", "OpenSSL", "certifi"):  # Dataverse's SQL endpoint (python-tds), no SQL on it
        if "run_sql(" not in all_text and not any(
            module in p.code for p in pieces if not dataverse.is_dataverse(p.dialect)
        ):
            requirements.pop(module, None)
    listing = "\n".join(f"    {m!r}: {r!r}," for m, r in requirements.items())
    requirements_text = (
        "# ===== REQUIREMENTS: what it needs installed (checked before anything of them is imported) =====\n"
        "# module -> what pip installs. The same list goes in an Azure Function app's requirements.txt.\n"
        "REQUIREMENTS: dict[str, str] = {\n"
        + listing
        + ("\n" if listing else "")
        + "}\n\n"
        + runtime.REQUIREMENTS_CHECK.strip("\n")
    )
    words = []
    if pieces:
        words.append("its connections and blades")
    if made.clients:
        words.append("the API clients it imports (" + ", ".join(f"{m}.py" for m, _ in made.clients) + ")")
    if has_vault:
        words.append("the key vault lookups")
    words.append("the grid's steps (as DuckDB SQL)")
    words.append(
        "the notebook's cells, in order" if made.source.lower().endswith(".ipynb") else "its code, in order"
    )
    inlined = ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]
    return _Shared(
        requirements,
        requirements_text,
        runtime.settings_block(made.settings)[0].strip("\n"),
        "\n\n\n".join(helpers),
        tuple(texts),
        "\n\n\n".join(registry),
        inlined,
        tuple(code.rstrip("\n") for _, code in made.clients),
    )


def _exported(
    made: Plan, text: str, requirements: Mapping[str, str], places: Sequence[tuple[int, int, str]]
) -> Exported:
    _, listed = runtime.settings_block(made.settings)
    return Exported(
        text,
        tuple(requirements.values()),
        tuple(listed),
        made.problems,
        made.stubs,
        made.skipped,
        tuple(places),
    )


def export(
    title: str,
    source: str | None,
    cells: Sequence[ExportCell],
    pieces: Mapping[str, Piece],
    code_names: Mapping[str, str],
    stub: bool = False,
    file: str | None = None,
    clients: Sequence[tuple[str, str]] = (),
) -> Exported:
    """The document as one script (`plan` says what each argument is)."""
    made = plan(title, source, cells, pieces, code_names, stub, clients)
    return render_script(made, file or file_name(source or title))


def render_script(made: Plan, file: str) -> Exported:
    """The steps as one .py: `python <file>` runs it; main() is what an Azure Function calls."""
    shared = _shared(made)
    module = file.removesuffix(".py")
    run_body: list[str] = []
    places: list[tuple[str, int, int]] = []  # label, first line, last line (in run()'s body)
    for block in made.blocks:
        start = len(run_body)
        if block.markdown:
            run_body += [f"# {line}".rstrip() for line in block.lines]
        else:
            if not all(
                line.startswith("#") or not line.strip() for line in "\n".join(block.lines).split("\n")
            ):
                run_body += [f"# ----- {block.label} -----", f"log.info({block.label!r})"]
            run_body += "\n".join(block.lines).split("\n")
        run_body.append("")
        places.append((block.label, start, len(run_body)))
    if not any(line.strip() and not line.lstrip().startswith("#") for line in run_body):
        run_body.append("pass")
    requirements = shared.requirements
    head = runtime.HEAD_DOC.format(
        title=made.title.replace('"""', "'''"),
        source=re.split(r"[\\/]", made.source)[-1],
        inlined=shared.inlined,
        python_version=REQUIRES_PYTHON.lstrip(">="),
        file=file,
        module=module,
        pip_line=" ".join(shlex.quote(r) for r in requirements.values()) or "(nothing: it needs only Python)",
        requirements_txt="\n".join(f"    {r}" for r in requirements.values()) or "    (nothing)",
    )
    pep = "# dependencies = [\n" + "".join(f'#     "{r}",\n' for r in requirements.values()) + "# ]"
    shown = re.split(r"[\\/]", made.source)[-1]
    out = [
        "#!/usr/bin/env python3",
        "# /// script",
        f'# requires-python = "{REQUIRES_PYTHON}"',
        pep if requirements else "# dependencies = []",
        "# ///",
        head.rstrip("\n"),
        "",
        "from __future__ import annotations",
        "",
        runtime.IMPORTS,
        "",
        f"log = logging.getLogger({module!r})",
        "",
        shared.requirements_text,
        "",
        "",
        shared.settings_text,
        "",
        "",
        shared.helpers,
    ]
    if made.pieces:
        out += [
            "",
            "",
            "# ===== the connections, vaults and blades: each one's own code, as saved in the app =====",
            "",
            "",
            "\n\n\n".join(shared.pieces),
            "",
            "",
            shared.registry,
        ]
    if shared.clients:
        out += [
            "",
            "",
            "# ===== the API clients it imports: each made by Add API, inline (its import finds it here) =====",
            "",
            "",
            "\n\n\n".join(shared.clients),
        ]
    out += [
        "",
        "",
        "# ===== the notebook's cells, in order ====="
        if shown.lower().endswith(".ipynb")
        else "# ===== the script's cells, in order =====",
        "",
        "",
        "def run() -> None:",
        f'    """The cells of {shown}, in order."""',
        *(f"    # Not exported: {p}" for p in made.problems),
    ]
    first = len("\n".join(out).split("\n")) + 1
    out.append(cell_facts.indented("\n".join(run_body).rstrip("\n")))
    out.append(runtime.MAIN.replace("{file}", file).rstrip("\n"))
    text = "\n".join(out) + "\n"
    lines = [(first + s, first + e - 1, label) for label, s, e in places]
    return _exported(made, text, requirements, lines)


# ===== a Streamlit page's SQL and DAX blocks: their connections as one module beside the pages =====

QUERY_MODULE: str = "sab_queries"
QUERY_FILE: str = f"{QUERY_MODULE}.py"


@dataclass(frozen=True)
class QueryModule:
    """sab_queries.py: what the pages' SQL and DAX blocks call (`sql`, `dax`), with each connection
    they name written out as this exporter writes it for a script (its own code, its settings read from
    the environment, a password never written). Its requirements, settings and what it could not take."""

    text: str
    requirements: tuple[str, ...]
    settings: tuple[dict[str, object], ...]
    problems: tuple[Problem, ...]


def query_module(made: Plan) -> QueryModule:
    """The plan of a page's SQL and DAX cells (`plan` over them) as sab_queries.py: the connections,
    vaults and helpers a script would hold, then the page's own `sql` and `dax` (the page's values bound,
    never pasted; cached by Streamlit). Settings are read from the environment when a query runs."""
    shared = _shared(made)
    out = [
        '"""Written by Swiss Army Bench: the connections the SQL and DAX blocks of these pages query, each',
        "one's own code as saved in the app, and how a page's values go with a query (bound, never pasted",
        "into its text). No password is written here: each is read from the environment. Change the",
        'connections in the app, not this file."""',
        "",
        "from __future__ import annotations",
        "",
        runtime.IMPORTS,
        "",
        f"log = logging.getLogger({QUERY_MODULE!r})",
        "",
        shared.settings_text,
        "",
        "",
        shared.helpers,
    ]
    if made.pieces:
        out += ["", "", "\n\n\n".join(shared.pieces), "", "", shared.registry]
    out += ["", "", runtime.PAGE_PARTS.strip("\n"), "", "", runtime.PAGE_QUERIES.strip("\n"), ""]
    _, listed = runtime.settings_block(made.settings)
    requirements = dict(shared.requirements)
    requirements.pop("streamlit", None)  # the page's own
    return QueryModule("\n".join(out), tuple(requirements.values()), tuple(listed), made.problems)


# ===== the notebook: the same steps, one cell each =====

NOTEBOOK_SUFFIX: str = "_automation.ipynb"


def export_notebook(
    title: str,
    source: str | None,
    cells: Sequence[ExportCell],
    pieces: Mapping[str, Piece],
    code_names: Mapping[str, str],
    stub: bool = False,
    file: str | None = None,
    clients: Sequence[tuple[str, str]] = (),
) -> Exported:
    """The document as one self-contained, linear notebook (`plan` says what each argument is)."""
    made = plan(title, source, cells, pieces, code_names, stub, clients)
    return render_notebook(made, file or file_name(source or title, NOTEBOOK_SUFFIX))


def _settings_parameters(settings: Sequence[Secret]) -> tuple[str, str]:
    """The `parameters` cell (each setting a variable: None, or a plain value) and SETTINGS from it."""
    _, listed = runtime.settings_block(settings)
    values = {s.variable: s for s in settings}
    names = [str(row["variable"]) for row in listed]
    lines = [
        "# Settings: every environment variable this notebook reads. A value here (papermill's -p) is used",
        "# when the environment has none. A secret's value is never written here.",
    ]
    for row in listed:
        name = str(row["variable"])
        secret = values[name]
        default = repr(secret.value) if secret.where == "value" else "None"
        lines.append(f"{name} = {default}  # {row['where']}")
    if not names:
        lines.append("# (it reads none)")
    block = runtime.settings_block(settings)[0]
    taken = block.split("SETTINGS: dict[str, str | None] = {", 1)[1].split("\n}\n", 1)[1]
    built = (
        "SETTINGS: dict[str, str | None] = {\n"
        + "".join(f"    {n!r}: {n},\n" for n in names)
        + "}\n"
        + taken.strip("\n")
    )
    return "\n".join(lines), built


def render_notebook(made: Plan, file: str) -> Exported:
    """The steps as one .ipynb (nbformat 4, no outputs, no app's own metadata): the package check,
    the settings (tagged `parameters`), the helpers, the vaults and connections, then the cells."""
    shared = _shared(made)
    requirements = shared.requirements
    cells: list[dict[str, object]] = []
    places: list[tuple[int, int, str]] = []
    code_lines: list[str] = []  # every code cell, one after another: what ruff reads

    def add(kind: str, text: str, label: str = "", tags: Sequence[str] = ()) -> None:
        metadata: dict[str, object] = {"tags": list(tags)} if tags else {}
        cell: dict[str, object] = {
            "cell_type": kind,
            "id": f"cell-{len(cells) + 1}",
            "metadata": metadata,
            "source": text.split("\n")
            and [line + "\n" for line in text.split("\n")[:-1]] + [text.split("\n")[-1]],
        }
        if kind == "code":
            cell |= {"execution_count": None, "outputs": []}
            first = len(code_lines) + 1
            code_lines.extend([*text.split("\n"), ""])
            places.append((first, len(code_lines), label or f"notebook cell {len(cells) + 1}"))
        cells.append(cell)

    add(
        "markdown",
        runtime.NOTEBOOK_HEAD.format(
            title=made.title,
            source=re.split(r"[\\/]", made.source)[-1],
            inlined=shared.inlined,
            python_version=REQUIRES_PYTHON.lstrip(">="),
            file=file,
            requirements_txt="\n".join(f"    {r}" for r in requirements.values()) or "    (nothing)",
        ).strip("\n"),
    )
    add(
        "code",
        "# What it needs installed: checked before anything of it is imported.\n"
        "INSTALL = False  # True: pip installs the missing ones into this kernel's Python first\n\n"
        + runtime.IMPORTS
        + '\n\nlogging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)\n'
        + f"log = logging.getLogger({file.removesuffix('.ipynb')!r})\n\n"
        + shared.requirements_text
        + "\n\n\ncheck_requirements(INSTALL)",
        "the package check",
    )
    parameters, built = _settings_parameters(made.settings)
    add("code", parameters, "the settings", tags=("parameters",))
    add("code", built + "\n\n\n" + shared.helpers + "\n\n\ncheck_settings()", "the settings' check")
    for piece_text in shared.pieces:
        add("code", piece_text, "a connection")
    if shared.registry:
        add("code", shared.registry, "the connections by name")
    for (module, _), client in zip(made.clients, shared.clients, strict=True):
        add("code", client, f"{module}.py")
    for problem in made.problems:
        add("markdown", f"**Not exported:** {problem}")
    for block in made.blocks:
        if block.markdown:
            add("markdown", "\n".join(block.lines))
        else:
            add("code", f"# ----- {block.label} -----\n" + "\n".join(block.lines), block.label)
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    text = json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"
    exported = _exported(made, text, requirements, places)
    return Exported(
        exported.text,
        exported.requirements,
        exported.settings,
        exported.problems,
        exported.stubs,
        exported.skipped,
        exported.places,
        code="\n".join(code_lines),
    )


# ===== which connections and blades a document names =====


def references(cells: Sequence[ExportCell], code_names: Mapping[str, str]) -> list[str]:
    """The connections and blades the document uses, by their names (the service looks each up)."""
    found: list[str] = []
    default: str | None = None
    made: set[str] = set()
    for cell in cells:
        if cell.kind in ("sql", "dax"):
            named, _ = sql_line(cell.connection)
            named = named or (default if cell.kind == "sql" else None)
            if named:
                found.append(named.split("/", 1)[0].strip() if cell.kind == "dax" else named)
            continue
        if cell.kind != "code":
            continue
        source = table_cells.split_uses(cell.source)[1]
        for line in source.split("\n"):
            connect = re.match(r"^\s*%(?:sql|sab|sag)_connect\s+(.+)$", line)
            if connect:
                default = connect.group(1).strip().strip("'\"")
        working = _Cell("")
        rewritten = _rewrite(working, _translate_magics(working, source))
        found += working.uses
        found += [code_names[v] for v in _connection_names(rewritten, code_names, made)]
        made.update(table_cells.facts(rewritten).made)
    return list(dict.fromkeys(found))


def secret_sources(
    name: str,
    asked: Sequence[str],
    saved: Iterable[str],
    vaults: Sequence[tuple[str, Mapping[str, str], bool]],
    typed: Mapping[str, str],
) -> list[Secret]:
    """Where each secret("x") a database, file or blade's code asks for comes from, as the app finds
    it: saved in the keyring (read here from SHOP_PASSWORD: the connection's name and the secret's), a
    vault that maps it, a secret blade, a vault that loads every secret, else this computer's
    environment. `vaults`: (name, mapping, every)."""
    kept = set(saved)
    out: list[Secret] = []
    for secret in asked:
        mapped = next(((v, m[secret]) for v, m, _ in vaults if secret in m), None)
        if secret in kept:
            out.append(Secret(secret, env_name_for(name, secret), "keyring", blade=name))
        elif mapped is not None:
            out.append(Secret(secret, secret, "vault", vault=mapped[0], entry=mapped[1], blade=name))
        elif secret in typed:
            out.append(Secret(secret, secret, "typed", vault=typed[secret], blade=name))
        elif any(every for _, _, every in vaults):
            vault = next(v for v, _, every in vaults if every)
            out.append(Secret(secret, secret, "every", vault=vault, blade=name))
        else:
            out.append(
                Secret(
                    secret,
                    env_name_for(name, secret) if not _plain_variable(secret) else secret,
                    "environment",
                    blade=name,
                )
            )
    return out


def _plain_variable(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Z_][A-Z0-9_]*", name))


def python_sources(
    name: str, variables: Mapping[str, Mapping[str, str]], reads: Sequence[python_connections.EnvRead]
) -> list[Secret]:
    """A connection from your own Python: each environment variable its boxes read, and its source."""
    out: list[Secret] = []
    required = {r.name: r.required for r in reads}
    for variable in dict.fromkeys([*variables, *required]):
        source = variables.get(variable, {"from": "env"})
        origin = source.get("from", "env")
        need = required.get(variable, True)
        if origin == "vault":
            out.append(
                Secret(
                    variable,
                    variable,
                    "vault",
                    vault=source.get("vault", ""),
                    entry=source.get("secret", ""),
                    blade=name,
                    required=need,
                )
            )
        elif origin == "value":
            out.append(
                Secret(variable, variable, "value", value=source.get("value", ""), blade=name, required=need)
            )
        elif origin == "keyring":
            out.append(Secret(variable, variable, "keyring", blade=name, required=need))
        else:
            out.append(Secret(variable, variable, "environment", blade=name, required=need))
    return out


# ===== the check before writing =====


def check(text: str, secret_values: Iterable[str]) -> list[str]:
    """What is wrong with the script, in words: it does not compile, it holds a saved password's value,
    or it holds rows (a pasted table's written out). Empty: it may be written."""
    found: list[str] = []
    try:
        compile(text, "<the script>", "exec")
    except SyntaxError as error:
        found.append(f"line {error.lineno}: it does not compile ({error.msg})")
    for value in secret_values:
        if value and len(value) >= 3 and value in text:
            found.append(
                "it would hold a saved password's value: the cell that holds it must read it from the environment"
            )
            break
    if _PASTED.search(text):
        found.append("it would hold a pasted table's rows")
    return found


def place_of(places: Sequence[tuple[int, int, str]], line: int) -> str:
    """Which cell a line of the script is in (for a lint finding)."""
    for first, last, label in places:
        if first <= line <= last:
            return label
    return f"line {line}"


__all__ = [
    "ExportCell",
    "Exported",
    "Piece",
    "Problem",
    "ScriptExportError",
    "Secret",
    "check",
    "env_name_for_secret",
    "export",
    "file_name",
    "python_sources",
    "references",
    "script_cells",
    "secret_sources",
]
