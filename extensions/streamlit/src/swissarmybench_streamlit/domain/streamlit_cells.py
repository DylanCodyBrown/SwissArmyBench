"""Streamlit apps (docs/ideas.md, the Streamlit canvas, 2026-11-15): Python cells linked onto pages.

A Streamlit app is a document of its own (`sales.stapp.json`): pages, and on each page blocks. A block
is a LINK to a Python cell of a notebook or a script (the file's path, the cell's own number) and its
place on a 12-column grid. The app holds no code: Play reads the linked cells as they are now. Blocks
talk by shared names: a block that makes `region` drives every block on the page that reads `region`.
Pure rules, no I/O:

  file      the app's file both ways: small, readable, one block a line; links relative to the file
  links     a link's path against the app's file; a linked file's Python cells
  facts     what a cell makes and reads (Python's own parser), its title, the modules it imports
  pages     pages and the blocks placed on them, checked; the grid's rows
  order     the order the blocks of a page run in, by the names they need; a cycle is said
  code      a page as ONE Streamlit page: its layout drawn first as empty slots, then each block run
            in name order inside its own slot, its widgets given keys of their own
  tables    the tables a page names, read from Parquet by a small preamble (or, in a saved project, imported
            from its data.py)
  export    the pages as a folder that runs without this app (the data as Parquet)
  save as   the pages as a project's pages/*.py: modules to drop into another Streamlit app, their
            tables imported from the project's data.py (domain/projects.py)

A Python cell that calls Streamlit (domain/streamlit_use.py) is also shown live in its own cell: a
piece alone, with the cells that make the names it reads.

A Markdown or HTML cell goes on a page too (docs/ideas.md, text cells on the canvas, 2026-11-15): it is
written as the Python a page runs (`text_code`): `st.markdown(...)`, or `st.html(...)` (with
`unsafe_allow_javascript=True` when it holds a <script>). Its `{{ name }}` values are what it reads, so
a filter drives the text and the run order counts them; they are filled by the HTML cells' own rules
(domain/html_cells.py, a copy of which goes beside the page as `sab_text.py`). It makes nothing.
"""

from __future__ import annotations

import ast
import dataclasses
import html
import json
import keyword
import ntpath
import posixpath
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import connection_usage as usage
from swissarmybench.domain import html_cells, notebooks, table_cells
from swissarmybench.domain import script_export as exporter
from swissarmybench.domain.blades import pip_name, provided
from swissarmybench.domain.cell_facts import (
    MAX_NAME,
    WIDGETS,
    Facts,
    body,
    facts,
    indented,
    piece_name,
)
from swissarmybench.domain.codegen import python_string
from swissarmybench.domain.datasets import DatasetInfo
from swissarmybench.domain.streamlit_use import uses_streamlit, usual_name
from swissarmybench_streamlit.domain import toolbox

__all__ = [
    "MAX_NAME",
    "WIDGETS",
    "Facts",
    "body",
    "facts",
    "indented",
    "piece_name",
    "uses_streamlit",
    "usual_name",
]

APP_SUFFIX: str = notebooks.APP_SUFFIX
APP_MARK: str = "streamlit-app"
# The marker's key; an app saved before the rename has SwissArmyGrid's, still read.
APP_KEY: str = "swissarmybench"
OLD_APP_KEY: str = "swissarmygrid"
APP_VERSION: int = 2  # 2: layout containers, blocks inside them, hidden and locked (2026-11-19)
MAX_CONTAINERS: int = 40
MAX_DEPTH: int = 4
MAX_APP_CHARS: int = 2_000_000

COLUMNS: int = 12
ROW_HEIGHT: int = 40  # pixels a unit of a block's height stands for (Visualizations board's row)
DEFAULT_WIDTH: int = 6
MIN_WIDTH: int = 2
MAX_HEIGHT: int = 30
MAX_PAGES: int = 30
MAX_PLACED: int = 60
MAX_PIECES: int = 2_000
MAX_PATH: int = 1_000
# What every page has before its blocks run: Streamlit and pandas, under their usual names.
PROVIDED: frozenset[str] = frozenset({"st", "pd"})
REQUIREMENTS: tuple[str, ...] = ("streamlit>=1.36", "pandas", "pyarrow")
# Where a page written for a test (`record`) puts each block's error: st.session_state[RECORD].
RECORD: str = "_sab_failures"
# A Markdown or HTML cell on a page: the kinds, and the module beside the page that fills its names (a
# copy of domain/html_cells.py, standard library only: nothing new to install).
TEXT_KINDS: tuple[str, ...] = ("markdown", "html")
TEXT_MODULE: str = "sab_text"
TEXT_FILE: str = f"{TEXT_MODULE}.py"
TEXT_HEADER: str = (
    "# Written by Swiss Army Bench: the rules that fill a Markdown or HTML block's {{ names }} on these\n"
    "# pages (its domain/html_cells.py). Standard library only.\n"
)
# st.html runs a block's own scripts with unsafe_allow_javascript, which Streamlit 1.52 brought.
SCRIPT_STREAMLIT: str = "streamlit>=1.52"
# A live page notes each block's values after it runs, for the lineage overlay (domain/lineage.py): a
# copy of client/lineage_values.py beside the page (standard library only), only while it plays here.
TRACE_MODULE: str = "sab_lineage"
TRACE_FILE: str = f"{TRACE_MODULE}.py"

# A SQL or DAX cell on a page (2026-11-19, the owner: "did we add DAX cells to the canvas?"): its code is
# the script exporter's own translation (domain/script_export.py `query_cell`), calling sab_queries.py
# beside the pages (the connections written out as the exporter writes them, `query_module`).
QUERY_KINDS: tuple[str, ...] = ("sql", "dax")
QUERY_MODULE: str = exporter.QUERY_MODULE
QUERY_ALIAS: str = f"_{QUERY_MODULE}"  # the block's own name for it (a name with _ is not one the page shows)
QUERY_FILE: str = exporter.QUERY_FILE
# The line a query block shows its result with ends with this mark (the view's choice replaces it).
SHOW_MARK: str = "# shown as:"
VIEWS: tuple[str, ...] = ("table", "bar", "line", "area", "metric")
CHARTS: tuple[str, ...] = ("bar", "line", "area")

# A block's cell: the linked file's path (as the app holds it) and the cell's own number. A piece
# shown alone in its own document has "" for the path.
Key = tuple[str, int]


class StreamlitError(ValueError):
    """An app, its pages or its cells that cannot be taken as sent (the message says why)."""


# ===== a cell: its title, what it makes and reads =====


def shown_makes(found: Facts) -> list[str]:
    """The names a cell makes as the pane and the canvas say them: not what the page gives every cell
    (st, pd), nor a name that starts with _ (the cell's own, by Python's habit; the starter pieces keep
    their helpers so). The run order still counts them all."""
    return [name for name in found.makes if name not in PROVIDED and not name.startswith("_")]


def tables_named(code: str, tables: Iterable[str]) -> list[str]:
    """The tables a cell names (real names only: Python's tokenizer, as the uses line reads them),
    in the order it first names them. `tables` are the tables' names as Python variables."""
    known = set(tables)
    return [name for name in table_cells.names_used(body(code)) if name in known]


def live_cells(cells: Sequence[tuple[int, str]], texts: Iterable[int] = ()) -> list[int]:
    """The cells of a document that call Streamlit (each is shown live in its cell), by number.
    `texts`: its Markdown and HTML cells (their page code calls Streamlit, but they are not live)."""
    skip = set(texts)
    python = tuple(code for number, code in cells if number not in skip)
    usual = usual_name(python)
    return [
        number
        for number, code in cells
        if number not in skip and code.strip() and uses_streamlit(body(code), usual)
    ]


# ===== a Markdown or HTML cell, as a page writes it =====

_BLOCK_TAGS = re.compile(
    r"</?(?:h[1-6]|p|div|li|ul|ol|tr|table|br|hr|header|footer|section|article|aside|nav|main|"
    r"blockquote|pre|figure|figcaption|caption|dl|dt|dd)\b[^>]*>",
    re.IGNORECASE,
)


def text_title(kind: str, text: str, number: int) -> str:
    """What a Markdown or HTML cell is called on a canvas without a name of its own: its first line of
    words (an HTML cell's without its tags; a Markdown cell's without its marks, outside its fenced
    blocks: one that is only a ```mermaid block is "Mermaid diagram"), else "Markdown cell N" or "HTML
    cell N" (N: the cell's own number)."""
    plain = text
    if kind == "html":
        plain = re.sub(r"<!--.*?(?:-->|$)", " ", plain, flags=re.DOTALL)
        plain = re.sub(r"<(script|style)\b.*?(?:</\1\s*>|$)", " ", plain, flags=re.DOTALL | re.IGNORECASE)
        plain = html.unescape(re.sub(r"<[^>]*>", "", _BLOCK_TAGS.sub("\n", plain)))
    else:
        fenced = sorted(html_cells.markdown_code(text), reverse=True)
        for start, end in fenced:
            if text.startswith(("```", "~~~"), start) or text[start:].lstrip(" ").startswith(("```", "~~~")):
                plain = plain[:start] + "\n" + plain[end:]
    for line in plain.split("\n"):
        words = line.strip()
        if kind == "markdown":
            words = re.sub(r"^(?:[#>]+|[-*+]|\d+[.)])\s+", "", words)
            words = re.sub(r"[*`]+|(?<!\w)_+|_+(?!\w)", "", words).strip()
            if re.fullmatch(r"[-=*_|: ]*", words):  # a rule, a table's rule row
                continue
        words = " ".join(words.split()).lstrip("%!")
        if words:
            return words[:MAX_NAME]
    if kind == "markdown" and html_cells.mermaid_blocks(text):
        return "Mermaid diagram"
    return f"{'Markdown' if kind == 'markdown' else 'HTML'} cell {number}"


def _python_text(text: str) -> str:
    """Text as a Python literal: as typed (a raw string) whenever Python can hold it that way."""
    plain = not re.search(r"[\x00-\x08\x0b-\x1f\x7f]", text)
    if plain and '"""' not in text and not text.endswith(('"', "\\")):
        return f'r"""{text}"""'
    return repr(text)


def text_code(kind: str, text: str, number: int) -> str:
    """A Markdown or HTML cell as a page runs it: `st.markdown(...)` or `st.html(...)`, the latter with
    `unsafe_allow_javascript=True` only when it holds a <script> the browser would run. Its `{{ name }}`
    values are read where the page stands (each through a lambda, so the run order counts them as
    reads) and filled by the HTML cells' rules, from the copy beside the page. Without names the text
    goes in as it is. An HTML cell's uses line is the app's, not the page's: it is left out."""
    text = table_cells.split_uses(text, html=True)[1] if kind == "html" else text
    head = f"# {text_title(kind, text, number)}"
    if not text.strip():
        return head + "\n"  # it shows nothing: the page runs `pass` in its slot
    named = [name for name in html_cells.names(text) if not keyword.iskeyword(name)]
    literal = _python_text(text)
    lines = [head]
    if named:
        getters = ", ".join(f'"{name}": lambda: {name}' for name in named)
        lines += [f"import {TEXT_MODULE} as _sab_text", ""]
        literal = f"_sab_text.page_{kind}({literal}, {{{getters}}})"
    if kind == "markdown":
        lines.append(f"st.markdown({literal})")
    else:
        scripts = ", unsafe_allow_javascript=True" if html_cells.has_script(text) else ""
        lines.append(f"st.html({literal}{scripts})")
    return "\n".join(lines) + "\n"


def query_title(kind: str, text: str, number: int, name: str | None = None) -> str:
    """What a SQL or DAX cell is called on a canvas without a name: its first line of the query (its
    comment's words, else the query), else "SQL cell N" or "DAX cell N"."""
    if name:
        return name
    query = table_cells.split_uses(text, sql=True)[1]
    for line in query.split("\n"):
        words = re.sub(r"^\s*(?:--|//)\s*", "", line).strip()
        if words:
            return " ".join(words.split())[:MAX_NAME]
    return f"{kind.upper()} cell {number}"


def query_code(kind: str, connection: str | None, text: str, number: int, name: str | None = None) -> str:
    """A SQL or DAX cell as a page runs it: the script exporter's translation of the cell (its connection
    and result's name, its query) as a call of sab_queries.py beside the page, its result shown as a table.
    The page's values it names (`{{ region }}`) are passed by name: bound as parameters (SQL), written as
    DAX literals (DAX); never pasted. No magic line: the page is plain Streamlit."""
    cell = exporter.ExportCell(kind, text, connection, number=number, name=name)
    head = f"# {query_title(kind, text, number, name)}"
    try:
        asked = exporter.query_cell(cell)
    except exporter.ScriptExportError as error:
        said = str(error)
        return f"{head}\nst.error({said[:1].upper() + said[1:] + ': pick one in its head.'!r})\n"
    result = asked.target or f"query_{number}"
    names = [n for n in exporter.page_names(asked.query, kind == "dax") if not keyword.iskeyword(n)]
    values = (", {" + ", ".join(f"{n!r}: {n}" for n in names) + "}") if names else ""
    call = f"{QUERY_ALIAS}.{kind}({asked.name!r}, {python_string(asked.query)}{values})"
    return (
        "\n".join(
            [
                head,
                f"import {QUERY_MODULE} as {QUERY_ALIAS}",
                "",
                f"{result} = {call}",
                f"st.dataframe({result})  {SHOW_MARK} table",
            ]
        )
        + "\n"
    )


def query_calls(code: str) -> list[exporter.ExportCell]:
    """The SQL and DAX cells a block's code calls sab_queries.py with (`query_code`), as the exporter
    reads cells: its kind, its query and its connection as the call names it."""
    if not is_query(code):
        return []
    try:
        tree = ast.parse(body(code))
    except SyntaxError:
        return []
    found: list[exporter.ExportCell] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        held = node.func.value
        if not (isinstance(held, ast.Name) and held.id == QUERY_ALIAS and node.func.attr in QUERY_KINDS):
            continue
        args = [a.value for a in node.args[:2] if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if len(args) == 2:
            found.append(exporter.ExportCell(node.func.attr, args[1].strip(), args[0]))
    return found


@dataclass(frozen=True)
class QueryFacts:
    """What a SQL or DAX block's pane shows: its kind, its connection (and a DAX block's dataset), its
    query, the name its result goes by, the page values it names, and the tables its query names."""

    kind: str
    connection: str
    dataset: str | None
    query: str
    result: str | None
    params: tuple[str, ...]
    tables: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "connection": self.connection,
            "dataset": self.dataset,
            "query": self.query,
            "result": self.result,
            "params": list(self.params),
            "tables": list(self.tables),
        }


_DAX_TABLE = re.compile(r"'((?:[^']|'')+)'")


def query_tables(kind: str, query: str) -> list[str]:
    """The tables a query names: a SQL query's by sqlglot's tree (a page value read as a value); a DAX
    query's quoted 'Table' names. Names only, in order; a query sqlglot cannot read names none."""
    if kind == "dax":
        text = "".join(p for p in exporter.page_split(query, dax=True) if isinstance(p, str))
        text = re.sub(r'"(?:[^"]|"")*"', '""', text)
        return list(dict.fromkeys(m.group(1).replace("''", "'") for m in _DAX_TABLE.finditer(text)))
    import sqlglot
    from sqlglot import exp

    text = "".join(p if isinstance(p, str) else "NULL" for p in exporter.page_split(query))
    try:
        trees = sqlglot.parse(text)
    except sqlglot.errors.SqlglotError:
        return []
    found: list[str] = []
    for tree in trees:
        if tree is None:
            continue
        ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            name = ".".join(part for part in (table.db, table.name) if part)
            if name and table.name not in ctes and name not in found:
                found.append(name)
    return found


def query_facts(code: str) -> QueryFacts | None:
    """A SQL or DAX block's facts from its code (`query_code`); None for any other block."""
    calls = query_calls(code)
    if not calls:
        return None
    cell = calls[0]
    connection = cell.connection or ""
    dataset = (
        connection.split("/", 1)[1].strip() or None if cell.kind == "dax" and "/" in connection else None
    )
    base = connection.split("/", 1)[0].strip() if cell.kind == "dax" else connection
    made = [n for n in facts(code).makes if n not in PROVIDED and n != QUERY_ALIAS]
    return QueryFacts(
        cell.kind,
        base,
        dataset,
        cell.source,
        made[0] if made else None,
        tuple(exporter.page_names(cell.source, cell.kind == "dax")),
        tuple(query_tables(cell.kind, cell.source)),
    )


def is_query(code: str) -> bool:
    """The code is a SQL or DAX block's (`query_code`)."""
    return f"import {QUERY_MODULE} as {QUERY_ALIAS}\n" in code and SHOW_MARK in code


def shown(code: str, view: Mapping[str, Any]) -> str:
    """A query block's code with its view: the result as a table, a chart (bar, line, area; x and y
    picked) or a metric (one value), and its cache off when the view says so."""
    if not view or not is_query(code):
        return code
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    call = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == QUERY_ALIAS
        ),
        None,
    )
    lines = code.rstrip("\n").split("\n")
    at = next((i for i, line in enumerate(lines) if line.endswith(f"{SHOW_MARK} table")), None)
    if call is None or at is None or not isinstance(call.targets[0], ast.Name):
        return code
    result = call.targets[0].id
    if view.get("cache") is False and call.value.end_lineno is not None:
        end = call.value.end_lineno - 1
        line = lines[end]
        cut = len(line.encode("utf-8")[: call.value.end_col_offset or 0].decode("utf-8")) - 1
        lines[end] = line[:cut] + ", cache=False" + line[cut:]
    how = view.get("as", "table")
    if how in CHARTS:
        given = "".join(f", {axis}={view[axis]!r}" for axis in ("x", "y") if view.get(axis))
        lines[at] = f"st.{how}_chart({result}{given})  {SHOW_MARK} {how} chart"
    elif how == "metric":
        label = view.get("label") or view.get("column") or result
        value = f"{QUERY_ALIAS}.one({result}, {view.get('column')!r})"
        lines[at] = f"st.metric({label!r}, {value})  {SHOW_MARK} metric"
    return "\n".join(lines) + "\n"


def uses_text_module(code: str) -> bool:
    """The code fills a text block's names from `sab_text.py` (the copy goes beside the page)."""
    return TEXT_MODULE in facts(code).modules


# ===== links: a block's file against the app's file; a linked file's Python cells =====


def is_app(path: str) -> bool:
    return path.lower().endswith(APP_SUFFIX)


def app_title(path: str | None) -> str:
    """An app's name from its file: `C:/work/sales.stapp.json` -> `sales`."""
    name = re.split(r"[\\/]", path or "")[-1]
    if name.lower().endswith(APP_SUFFIX):
        name = name[: -len(APP_SUFFIX)]
    return name or "Streamlit app"


def _flavour(path: str) -> Any:
    """Windows' path rules for a Windows path (`C:\\work`, `\\\\server\\share`), POSIX's otherwise."""
    return ntpath if re.match(r"^[A-Za-z]:[\\/]|^\\\\", path) else posixpath


def is_absolute(path: str) -> bool:
    return posixpath.isabs(path) or bool(re.match(r"^[A-Za-z]:[\\/]|^\\\\", path))


def relative_link(app_path: str | None, document: str) -> str:
    """A linked file's path as the app's file holds it: relative to the app's own folder, with forward
    slashes (so the two can move together). An app without a file yet, or a file on another drive,
    keeps the whole path."""
    if not is_absolute(document):
        return document.replace("\\", "/")
    if not app_path:
        return document
    rules = _flavour(app_path)
    try:
        return str(rules.relpath(document, rules.dirname(app_path))).replace("\\", "/")
    except ValueError:  # another drive
        return document


def resolve_link(app_path: str | None, link: str) -> str:
    """The whole path a link names: against the app's own folder when it is relative."""
    if is_absolute(link) or not app_path:
        return link
    rules = _flavour(app_path)
    return str(rules.normpath(rules.join(rules.dirname(app_path), link)))


def same_file(a: str, b: str) -> bool:
    """Two paths of one file, as far as their text says (slashes either way; Windows ignores case)."""
    left, right = a.replace("\\", "/"), b.replace("\\", "/")
    if _flavour(a) is ntpath or _flavour(b) is ntpath:
        return left.lower() == right.lower()
    return left == right


@dataclass(frozen=True)
class Linkable:
    """A cell a block can link to: its own number, its kind (code, markdown, html), its code as a page
    runs it (a Markdown or HTML cell's: `text_code`), and its own name."""

    number: int
    kind: str
    code: str
    name: str | None = None


def linkable(path: str, text: str) -> list[Linkable]:
    """A notebook's or script's cells that go on a page, in file order: its Python cells, its Markdown
    and HTML cells. A table's read-only cell and the Tables group's own lines are not the user's; a
    script cell without a number yet (never opened here) cannot be linked; a script's HTML cell whose
    string is not whole yet is left out."""
    found: list[Linkable] = []
    if notebooks.kind_of(path) == "notebook":
        cells, _ = notebooks.read_document(text)
        for c in cells:
            if c.number is None:
                continue
            if c.kind == "code" and c.role in ("", "maker"):
                found.append(Linkable(c.number, "code", c.source, c.name))
            elif c.kind in TEXT_KINDS and c.role == "":
                found.append(Linkable(c.number, c.kind, text_code(c.kind, c.source, c.number), c.name))
            elif c.kind in QUERY_KINDS and c.role == "" and c.source.strip():
                code = query_code(c.kind, c.connection, c.source, c.number, c.name)
                found.append(Linkable(c.number, c.kind, code, c.name))
        return found
    for s in table_cells.parse_script(text).cells:
        if s.number is None or s.fixed or s.role not in ("", "maker"):
            continue
        name = table_cells.marker_name(s.title)
        if not s.html:
            found.append(Linkable(s.number, "code", s.source.rstrip("\n"), name))
            continue
        held = html_cells.read_script_body(s.source)[0]
        if held is not None:
            found.append(Linkable(s.number, "html", text_code("html", held, s.number), name))
    return found


def document_cells(path: str, text: str) -> list[tuple[int, str]]:
    """A notebook's or script's cells a block can link to (`linkable`) as (the cell's own number, its
    code as a page runs it), in file order."""
    return [(c.number, c.code) for c in linkable(path, text)]


def document_names(path: str, text: str) -> dict[int, str]:
    """The names those cells have (a notebook's metadata, a script's marker words), by the cell's own
    number. A cell without a name is not listed."""
    return {c.number: c.name for c in linkable(path, text) if c.name}


def document_kinds(path: str, text: str) -> dict[int, str]:
    """Which of those cells are Markdown, HTML, SQL or DAX cells, by the cell's own number."""
    return {c.number: c.kind for c in linkable(path, text) if c.kind != "code"}


def cell_title(code: str, number: int, name: str | None = None) -> str:
    """What a cell is called on a canvas and in the Streamlit cells pane: its own name, else its first
    comment line or first line of code (`piece_name`)."""
    return name or piece_name(code, number)


# ===== pages and the blocks placed on them =====


@dataclass
class Block:
    """A cell on a page: the link (the file, the cell's own number) and its place on the 12-column
    grid: the row, the column it starts in, how many columns wide, how many rows of 40 pixels tall."""

    id: str
    document: str
    cell: int
    row: int = 1
    column: int = 1
    w: int = DEFAULT_WIDTH
    h: int | None = None  # in units of ROW_HEIGHT; None: as tall as what it draws
    # The container it sits in (None: the page itself) and which of its slots (a column, a tab).
    parent: str | None = None
    slot: int = 0
    hidden: bool = False  # hidden while designing (the page still draws it)
    locked: bool = False  # the designer does not move or size it
    # A SQL or DAX block's view (`check_view`): {"as": "bar", "x": .., "y": .., "cache": false}; {}: a table.
    view: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> Key:
        return (self.document, self.cell)

    def to_json(self) -> dict[str, Any]:
        said: dict[str, Any] = {
            "id": self.id,
            "document": self.document,
            "cell": self.cell,
            "row": self.row,
            "column": self.column,
            "w": self.w,
            "h": self.h,
            "parent": self.parent,
            "slot": self.slot,
            "hidden": self.hidden,
            "locked": self.locked,
        }
        return said | ({"view": dict(self.view)} if self.view else {})


@dataclass
class Container:
    """A layout container (the designer's, 2026-11-19: WPF's panels): columns, tabs, an expander, a
    container, a form, the sidebar, a popover. It has a place on the grid like a block (the sidebar has
    none), its own properties, and slots that hold blocks and other containers, each slot a 12-column grid
    of its own. It is the canvas's: no cell stands behind it, and it exports as plain Streamlit."""

    id: str
    kind: str
    row: int = 1
    column: int = 1
    w: int = COLUMNS
    h: int | None = None
    parent: str | None = None
    slot: int = 0
    props: dict[str, Any] = field(default_factory=dict)
    name: str = ""
    hidden: bool = False
    locked: bool = False

    def get(self, name: str) -> Any:
        """A property: what was set, else its default."""
        if name in self.props:
            return self.props[name]
        found = toolbox.CONTAINERS[self.kind].param(name)
        return None if found is None else found.default

    @property
    def slots(self) -> int:
        how = toolbox.CONTAINERS[self.kind].slots
        return (
            len(self.get("widths")) if how == "widths" else len(self.get("labels")) if how == "labels" else 1
        )

    def slot_names(self) -> list[str]:
        how = toolbox.CONTAINERS[self.kind].slots
        if how == "labels":
            return [str(label) for label in self.get("labels")]
        if how == "widths":
            return [f"Column {n}" for n in range(1, self.slots + 1)]
        return [""]

    @property
    def title(self) -> str:
        if self.name:
            return self.name
        label = self.get("label") if toolbox.CONTAINERS[self.kind].param("label") else None
        kind = toolbox.CONTAINERS[self.kind].label
        return f"{kind}: {label}" if isinstance(label, str) and label else kind

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "row": self.row,
            "column": self.column,
            "w": self.w,
            "h": self.h,
            "parent": self.parent,
            "slot": self.slot,
            "props": dict(self.props),
            "name": self.name,
            "hidden": self.hidden,
            "locked": self.locked,
        }


Item = Block | Container
Group = tuple[str | None, int]


@dataclass
class Page:
    id: str
    name: str
    blocks: list[Block] = field(default_factory=list)
    containers: list[Container] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        said: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "blocks": [b.to_json() for b in self.blocks],
        }
        return said | {"containers": [c.to_json() for c in self.containers]}

    def items(self) -> list[Item]:
        return [*self.blocks, *self.containers]

    def find(self, item_id: str) -> Item | None:
        return next((i for i in self.items() if i.id == item_id), None)

    def container(self, item_id: str | None) -> Container | None:
        return next((c for c in self.containers if c.id == item_id), None) if item_id else None


_ID = re.compile(r"^[A-Za-z0-9]{1,16}$")


def _whole(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value == value  # not NaN


def check_width(width: Any) -> int:
    if not _whole(width):
        raise StreamlitError(f"A block's width is a whole number of columns, {MIN_WIDTH} to {COLUMNS}.")
    return int(max(MIN_WIDTH, min(COLUMNS, round(width))))


def check_rows(height: Any) -> int | None:
    """A block's height in rows of the grid (None: as tall as what it draws)."""
    if height is None:
        return None
    if not _whole(height):
        raise StreamlitError(f"A block's height is a number of rows (1 to {MAX_HEIGHT}), or null.")
    return int(max(1, min(MAX_HEIGHT, round(height))))


def check_column(column: Any) -> int:
    if not _whole(column):
        raise StreamlitError(f"A block's column is where it starts, 1 to {COLUMNS}.")
    return int(max(1, min(COLUMNS, round(column))))


def check_row(row: Any) -> int:
    if not _whole(row):
        raise StreamlitError("A block's row is a whole number from 1.")
    return int(max(1, min(MAX_PLACED, round(row))))


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip() or "\n" in name or len(name.strip()) > MAX_NAME:
        raise StreamlitError(f"A page's name is one line of at most {MAX_NAME} characters.")
    return name.strip()


def check_link(document: Any, cell: Any) -> Key:
    if not isinstance(document, str) or not document.strip() or len(document) > MAX_PATH or "\n" in document:
        raise StreamlitError(
            "A block links to a cell: its notebook's or script's path, and the cell's number."
        )
    if isinstance(cell, bool) or not isinstance(cell, int) or cell < 1:
        raise StreamlitError("A block names its cell by the cell's own number.")
    return document.strip(), cell


def check_view(raw: Any) -> dict[str, Any]:
    """A SQL or DAX block's view as sent: {"as": table | bar | line | area | metric, "x"?: a column,
    "y"?: a column or a list of them (a chart), "column"?: the value's column and "label"?: its words (a
    metric), "cache"?: false}. A table, cached, is the default and is written as {}."""
    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, dict):
        raise StreamlitError('A block\'s view is {"as": "table" | "bar" | "line" | "area" | "metric", ...}.')
    shown = raw.get("as", "table")
    if shown not in VIEWS:
        raise StreamlitError(f"A query block shows its result as one of: {', '.join(VIEWS)}.")
    out: dict[str, Any] = {} if shown == "table" else {"as": shown}

    def column(name: str, value: Any) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME or "\n" in value:
            raise StreamlitError(f"{name} names one column of the result.")
        return value.strip()

    for name in raw:
        if name not in ("as", "x", "y", "column", "label", "cache"):
            raise StreamlitError(f"A query block's view has no {name!r}: as, x, y, column, label, cache.")
    if shown in CHARTS:
        if raw.get("x"):
            out["x"] = column("x", raw["x"])
        y = raw.get("y")
        if isinstance(y, list) and y:
            out["y"] = [column("y", v) for v in y][:12]
        elif y:
            out["y"] = column("y", y)
    if shown == "metric":
        if raw.get("column"):
            out["column"] = column("column", raw["column"])
        if raw.get("label"):
            out["label"] = column("label", raw["label"])
    if raw.get("cache") is False:
        out["cache"] = False
    elif "cache" in raw and not isinstance(raw["cache"], bool):
        raise StreamlitError("cache is true or false.")
    return out


def check_props(kind: Any, raw: Any, held: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A container's properties as sent, checked against its kind (toolbox.CONTAINERS): {"widths": [2, 1]},
    {"labels": ["Chart", "Table"]}, {"label": "Details", "expanded": true}... A property sent as null goes
    back to its default. `held`: what it has now (a part is enough)."""
    if kind not in toolbox.CONTAINERS:
        raise StreamlitError(f"A container is one of: {', '.join(toolbox.CONTAINERS)}.")
    if raw is None:
        return dict(held or {})
    if not isinstance(raw, dict):
        raise StreamlitError('A container\'s properties are {"name": value}.')
    known = toolbox.CONTAINERS[kind]
    out = dict(held or {})
    for name, value in raw.items():
        param = known.param(name)
        if param is None:
            listed = ", ".join(p.name for p in known.params) or "none"
            raise StreamlitError(f"{known.label} has no property called {name!r}. Its properties: {listed}.")
        if value is None:
            out.pop(name, None)
            continue
        if name == "widths":
            ok = (
                isinstance(value, list)
                and 1 <= len(value) <= COLUMNS
                and all(_whole(v) and 0 < v <= 100 for v in value)
            )
            if not ok:
                raise StreamlitError("Column widths are ratios, like [2, 1]: one to twelve numbers above 0.")
            value = [int(v) if float(v).is_integer() else float(v) for v in value]
        elif name == "labels":
            ok = isinstance(value, list) and 1 <= len(value) <= 20
            ok = ok and all(
                isinstance(v, str) and v.strip() and len(v) <= MAX_NAME and "\n" not in v for v in value
            )
            if not ok or len({v.strip() for v in value}) != len(value):
                raise StreamlitError("Tabs are named: one to twenty names, each its own.")
            value = [v.strip() for v in value]
        elif name == "submitted":
            if not isinstance(value, str) or (
                value and (not value.isidentifier() or keyword.iskeyword(value))
            ):
                raise StreamlitError("The name of a form's button value is one word, like submitted.")
        elif param.type == "bool":
            if not isinstance(value, bool):
                raise StreamlitError(f"{name} is true or false.")
        elif param.type == "choice":
            if value not in param.choices:
                raise StreamlitError(f"{name} is one of: {', '.join(param.choices)}.")
        elif not isinstance(value, str) or len(value) > MAX_NAME or "\n" in value:
            raise StreamlitError(f"{name} is one line of at most {MAX_NAME} characters.")
        if value == param.default and name not in ("widths", "labels"):
            out.pop(name, None)
        else:
            out[name] = value
    return out


def grouped(page: Page) -> dict[Group, list[Item]]:
    """The page's items by where they sit: (the container, its slot); (None, 0) is the page itself. The
    sidebar has no place of its own, so it is in no group."""
    out: dict[Group, list[Item]] = {}
    for item in page.items():
        if isinstance(item, Container) and item.kind == "sidebar":
            continue
        out.setdefault((item.parent, item.slot), []).append(item)
    for items in out.values():
        items.sort(key=lambda i: (i.row, i.column))
    return out


def depth_of(page: Page, item: Item) -> int:
    depth, parent, seen = 0, page.container(item.parent), set()
    while parent is not None and parent.id not in seen:
        seen.add(parent.id)
        depth += 1
        parent = page.container(parent.parent)
    return depth


def _inside(page: Page, item: Item, kind: str) -> bool:
    parent, seen = page.container(item.parent), set()
    while parent is not None and parent.id not in seen:
        if parent.kind == kind:
            return True
        seen.add(parent.id)
        parent = page.container(parent.parent)
    return False


def check_nesting(page: Page, item: Item, parent_id: str | None, slot: Any = 0) -> tuple[str | None, int]:
    """Where an item may go: into a container that is there, a slot it has; not into itself or what it
    holds; no form in a form; the sidebar only on the page itself; at most MAX_DEPTH deep."""
    if parent_id is None:
        return None, 0
    parent = page.container(parent_id)
    if parent is None:
        raise StreamlitError(f"This page has no container {parent_id}.")
    if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < parent.slots:
        raise StreamlitError(
            f"{parent.title} has {parent.slots} {'slot' if parent.slots == 1 else 'slots'}, from 0."
        )
    if isinstance(item, Container):
        if item.kind == "sidebar":
            raise StreamlitError("The sidebar is the page's own: it does not go inside a container.")
        up: Container | None = parent
        while up is not None:
            if up.id == item.id:
                raise StreamlitError("A container does not go inside itself.")
            up = page.container(up.parent)
        if item.kind == "form" and (parent.kind == "form" or _inside(page, parent, "form")):
            raise StreamlitError("A form does not go inside another form (Streamlit does not draw it).")
    if depth_of(page, parent) + 1 >= MAX_DEPTH:
        raise StreamlitError(f"Containers nest at most {MAX_DEPTH} deep.")
    return parent.id, slot


def settle_page(page: Page, first: Item | None = None) -> None:
    """Every grid of the page settled (`settle`): the page's own, and each slot of each container. An item
    whose container is gone, or whose slot is, comes up to the page. The blocks and containers are left in
    reading order, outside in."""
    ids = {c.id for c in page.containers}
    for item in page.items():
        parent = page.container(item.parent) if item.parent in ids and item.parent != item.id else None
        if parent is None:
            item.parent, item.slot = None, 0
        else:
            item.slot = max(0, min(parent.slots - 1, item.slot))
    # A container inside what it holds (a loop) comes up to the page.
    for container in page.containers:
        seen: set[str] = set()
        up = page.container(container.parent)
        while up is not None:
            if up.id in seen or up.id == container.id:
                container.parent, container.slot = None, 0
                break
            seen.add(up.id)
            up = page.container(up.parent)
    for bar in page.containers:
        if bar.kind == "sidebar":  # it has no place of its own
            bar.parent, bar.slot, bar.row, bar.column, bar.w, bar.h = None, 0, 1, 1, COLUMNS, None
    groups = grouped(page)
    for items in groups.values():
        settle(items, first if any(i is first for i in items) else None)
    ordered: list[Item] = []

    def walk(key: Group) -> None:
        for item in groups.get(key, []):
            ordered.append(item)
            if isinstance(item, Container):
                for slot in range(item.slots):
                    walk((item.id, slot))

    walk((None, 0))
    for bar in [c for c in page.containers if c.kind == "sidebar"]:
        ordered.append(bar)
        walk((bar.id, 0))
    page.blocks[:] = [i for i in ordered if isinstance(i, Block)]
    page.containers[:] = [i for i in ordered if isinstance(i, Container)]


def grids(page: Page) -> dict[str, list[list[str]]]:
    """Each grid's rows of ids: "" the page's own, "c1:0" a container's slot."""
    return {
        ("" if parent is None else f"{parent}:{slot}"): [[i.id for i in row] for row in rows(items)]
        for (parent, slot), items in grouped(page).items()
    }


def next_id(prefix: str, taken: Iterable[str]) -> str:
    """The next id of a kind (p1, p2... for pages; b1, b2... for blocks), never one in use."""
    used = set(taken)
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def settle(blocks: list[Any], first: Any = None) -> None:
    """The blocks as the grid holds them: in reading order (row, then column), no two on the same
    columns of a row, none past column 12. A block that would lie on another starts a row of its
    own below; `first` (the block just moved or placed) keeps the place it was given, and the
    neighbour it would lie on goes below. Rows are counted from 1 with none empty."""
    order = {id(b): i for i, b in enumerate(blocks)}
    for block in blocks:
        block.w = max(MIN_WIDTH, min(COLUMNS, block.w))
        block.column = max(1, min(COLUMNS - block.w + 1, block.column))
    asked: dict[int, list[Any]] = {}
    for block in blocks:
        asked.setdefault(block.row, []).append(block)
    settled: list[list[Any]] = []
    for row in sorted(asked):
        waiting = sorted(asked[row], key=lambda b: (b is not first, b.column, order[id(b)]))
        while waiting:
            taken: set[int] = set()
            here: list[Any] = []
            below: list[Any] = []
            for block in waiting:
                columns = set(range(block.column, block.column + block.w))
                if columns & taken:
                    below.append(block)
                else:
                    taken |= columns
                    here.append(block)
            settled.append(sorted(here, key=lambda b: b.column))
            waiting = below
    for number, held in enumerate(settled, start=1):
        for block in held:
            block.row = number
    blocks[:] = [block for held in settled for block in held]


def rows(blocks: Sequence[Any]) -> list[list[Any]]:
    """The blocks as the grid's rows (settled blocks: each row's in column order)."""
    out: dict[int, list[Any]] = {}
    for block in blocks:
        out.setdefault(block.row, []).append(block)
    return [out[row] for row in sorted(out)]


def free_place(blocks: Sequence[Any], width: int = DEFAULT_WIDTH) -> tuple[int, int]:
    """Where a new block goes when no place is said: beside the last one when the last row has the
    room, else a new row below. (row, column)."""
    if not blocks:
        return 1, 1
    last = max(b.row for b in blocks)
    end = max(b.column + b.w for b in blocks if b.row == last)
    return (last, end) if end + width - 1 <= COLUMNS else (last + 1, 1)


def read_pages(sent: Any) -> list[Page]:
    """Pages as the canvas or the agent sends them, checked:
    [{"id"?, "name", "blocks": [{"id"?, "document", "cell", "row", "column", "w", "h"}]}].
    Ids are made where they are missing or used twice; a block's id is its own across the whole app."""
    if sent is None:
        return []
    if not isinstance(sent, list) or len(sent) > MAX_PAGES:
        raise StreamlitError(f"Pages are a list (at most {MAX_PAGES}).")
    pages: list[Page] = []
    page_ids: set[str] = set()
    block_ids: set[str] = set()
    for raw in sent:
        if not isinstance(raw, dict):
            raise StreamlitError(
                'Each page is {"name", "blocks": [{"document", "cell", "row", "column", "w", "h"}]}.'
            )
        page_id = raw.get("id")
        if not isinstance(page_id, str) or not _ID.match(page_id) or page_id in page_ids:
            page_id = next_id("p", page_ids)
        page_ids.add(page_id)
        name = raw.get("name")
        page = Page(page_id, check_name(name) if isinstance(name, str) and name.strip() else "")
        blocks = raw.get("blocks") or []
        if not isinstance(blocks, list) or len(blocks) > MAX_PLACED:
            raise StreamlitError(f"A page holds at most {MAX_PLACED} blocks.")
        for index, item in enumerate(blocks):
            if not isinstance(item, dict):
                raise StreamlitError("A block links to a cell: its file's path and the cell's number.")
            document, cell = check_link(item.get("document"), item.get("cell"))
            block_id = item.get("id")
            if not isinstance(block_id, str) or not _ID.match(block_id) or block_id in block_ids:
                block_id = next_id("b", block_ids)
            block_ids.add(block_id)
            page.blocks.append(
                Block(
                    block_id,
                    document,
                    cell,
                    check_row(item.get("row", index + 1)),
                    check_column(item.get("column", 1)),
                    check_width(item.get("w", item.get("width", DEFAULT_WIDTH))),
                    check_rows(item.get("h", item.get("height"))),
                    item.get("parent") if isinstance(item.get("parent"), str) else None,
                    item["slot"] if type(item.get("slot")) is int and item["slot"] >= 0 else 0,
                    item.get("hidden") is True,
                    item.get("locked") is True,
                    check_view(item.get("view")),
                )
            )
        held = raw.get("containers") or []
        if not isinstance(held, list) or len(held) > MAX_CONTAINERS:
            raise StreamlitError(f"A page holds at most {MAX_CONTAINERS} containers.")
        for index, item in enumerate(held):
            if not isinstance(item, dict):
                raise StreamlitError(
                    'A container is {"kind": "columns", "props": {...}, "row", "column", "w"}.'
                )
            kind = item.get("kind")
            props = check_props(kind, item.get("props") or {})
            container_id = item.get("id")
            if not isinstance(container_id, str) or not _ID.match(container_id) or container_id in block_ids:
                container_id = next_id("c", block_ids)
            block_ids.add(container_id)
            name = item.get("name")
            if kind == "sidebar" and any(c.kind == "sidebar" for c in page.containers):
                raise StreamlitError("A page has one sidebar.")
            page.containers.append(
                Container(
                    container_id,
                    str(kind),
                    check_row(item.get("row", index + 1)),
                    check_column(item.get("column", 1)),
                    check_width(item.get("w", item.get("width", COLUMNS))),
                    check_rows(item.get("h", item.get("height"))),
                    item.get("parent") if isinstance(item.get("parent"), str) else None,
                    item["slot"] if type(item.get("slot")) is int and item["slot"] >= 0 else 0,
                    props,
                    check_name(name) if isinstance(name, str) and name.strip() else "",
                    item.get("hidden") is True,
                    item.get("locked") is True,
                )
            )
        settle_page(page)
        pages.append(page)
    for index, page in enumerate(pages):
        if not page.name:
            page.name = page_title(index + 1, [p.name for p in pages])
    return pages


def page_title(number: int, taken: Iterable[str]) -> str:
    """A new page's name: "Page N", the first not in use."""
    used = set(taken)
    while f"Page {number}" in used:
        number += 1
    return f"Page {number}"


def pages_json(pages: Sequence[Page]) -> list[dict[str, Any]]:
    return [page.to_json() for page in pages]


# ----- the app's file: sales.stapp.json -----
#
#     {
#       "swissarmybench": "streamlit-app",
#       "version": 1,
#       "pages": [
#         {
#           "name": "Overview",
#           "blocks": [
#             {"document": "sales.ipynb", "cell": 3, "row": 1, "column": 1, "width": 6, "height": null},
#             {"document": "sales.ipynb", "cell": 4, "row": 1, "column": 7, "width": 6, "height": 5}
#           ]
#         }
#       ]
#     }
#
# JSON, written by hand so each block is one line (a change to a block is a one-line diff). It holds
# the pages and their blocks' links and places, and nothing else: no ids, no code.


def write_app(
    pages: Sequence[Page], link: Callable[[str], str] = lambda document: document, settings: str | None = None
) -> str:
    """The app's file text. `link` gives each block's path as the file should hold it (relative to
    the file: `relative_link`). `settings`: the page settings' line (domain/app_settings.py file_line)."""
    said = json.dumps
    plain = all(
        not page.containers and not any(b.parent or b.hidden or b.locked or b.view for b in page.blocks)
        for page in pages
    )
    # A page with no container, nothing hidden and nothing locked is written as version 1 wrote it.
    lines = ["{", f"  {said(APP_KEY)}: {said(APP_MARK)},", f'  "version": {1 if plain else APP_VERSION},']
    if settings:
        lines.append(settings)
    if not pages:
        return "\n".join([*lines, '  "pages": []', "}"]) + "\n"
    lines.append('  "pages": [')
    for at, page in enumerate(pages):
        lines += ["    {", f'      "name": {said(page.name, ensure_ascii=False)},']
        if page.blocks:
            lines.append('      "blocks": [')
            for index, block in enumerate(page.blocks):
                held = {
                    "document": link(block.document),
                    "cell": block.cell,
                    "row": block.row,
                    "column": block.column,
                    "width": block.w,
                    "height": block.h,
                }
                if block.parent:
                    held |= {"parent": block.parent, "slot": block.slot}
                held |= {key: True for key in ("hidden", "locked") if getattr(block, key)}
                if block.view:
                    held["view"] = dict(sorted(block.view.items()))
                comma = "," if index + 1 < len(page.blocks) else ""
                lines.append(f"        {said(held, ensure_ascii=False)}{comma}")
            lines.append("      ]" + ("," if page.containers else ""))
        else:
            lines.append('      "blocks": []' + ("," if page.containers else ""))
        if page.containers:
            lines.append('      "containers": [')
            for index, box in enumerate(page.containers):
                kept: dict[str, Any] = {"id": box.id, "kind": box.kind}
                if box.name:
                    kept["name"] = box.name
                if box.kind != "sidebar":
                    kept |= {"row": box.row, "column": box.column, "width": box.w, "height": box.h}
                if box.parent:
                    kept |= {"parent": box.parent, "slot": box.slot}
                if box.props:
                    kept["props"] = box.props
                kept |= {key: True for key in ("hidden", "locked") if getattr(box, key)}
                comma = "," if index + 1 < len(page.containers) else ""
                lines.append(f"        {said(kept, ensure_ascii=False)}{comma}")
            lines.append("      ]")
        lines.append("    }" + ("," if at + 1 < len(pages) else ""))
    lines += ["  ]", "}"]
    return "\n".join(lines) + "\n"


def read_app(text: str, link: Callable[[str], str] = lambda document: document) -> list[Page]:
    """The pages an app's file holds. `link` gives the whole path of each block's file
    (`resolve_link`). A file that is not an app's says so."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise StreamlitError(f"This is not a Streamlit app's file: {error}.") from None
    if not isinstance(data, dict) or APP_MARK not in (data.get(APP_KEY), data.get(OLD_APP_KEY)):
        raise StreamlitError(
            'This is not a Streamlit app\'s file: it has no "swissarmybench": "streamlit-app".'
        )
    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version > APP_VERSION:
        raise StreamlitError("This Streamlit app was saved by a newer Swiss Army Bench: update to open it.")
    pages = read_pages(data.get("pages"))
    for page in pages:
        for block in page.blocks:
            block.document = link(block.document)
    return pages


# ===== the order blocks run in =====


@dataclass(frozen=True)
class Ordered:
    order: tuple[str, ...]  # the placed pieces' ids, in the order they run
    cycle: tuple[str, ...] = ()  # the ids that wait on each other (they do not run)
    # (the placed piece, the name it reads, the piece that makes it) for every link on the page
    links: tuple[tuple[str, str, str], ...] = ()


def run_order(pieces: Sequence[tuple[str, Facts]]) -> Ordered:
    """The order a page's pieces run in: a piece after the pieces that make the names it reads, and
    otherwise as they are placed. When two pieces make one name, the first placed is the maker."""
    place = {key: index for index, (key, _) in enumerate(pieces)}
    maker: dict[str, str] = {}
    for key, found in pieces:
        for name in found.makes:
            maker.setdefault(name, key)
    needs: dict[str, set[str]] = {key: set() for key, _ in pieces}
    links: list[tuple[str, str, str]] = []
    for key, found in pieces:
        for name in found.reads:
            source = maker.get(name)
            if source is not None and source != key and name not in found.makes:
                needs[key].add(source)
                links.append((key, name, source))
    done: list[str] = []
    waiting = [key for key, _ in pieces]
    while waiting:
        ready = [key for key in waiting if needs[key] <= set(done)]
        if not ready:
            break
        first = min(ready, key=lambda key: place[key])
        done.append(first)
        waiting.remove(first)
    # What is left waits on a cycle; the pieces of the cycle itself are those that reach themselves.
    cycle = tuple(key for key in waiting if _reaches(key, key, needs, set()))
    return Ordered(tuple(done), cycle or tuple(waiting), tuple(links))


def _reaches(start: str, goal: str, needs: Mapping[str, set[str]], seen: set[str]) -> bool:
    for other in needs[start]:
        if other == goal:
            return True
        if other not in seen:
            seen.add(other)
            if _reaches(other, goal, needs, seen):
                return True
    return False


# ===== code: widget keys, indenting, a page as one Streamlit page =====


def _offset(line: str, column: int) -> int:
    """ast's column (bytes of UTF-8) as a place in the line's text."""
    return len(line.encode("utf-8")[:column].decode("utf-8", "ignore"))


def keyed(code: str, prefix: str) -> str:
    """The code with a key of its own on each widget that has none (`key="<prefix>_1"`), so two copies
    of one piece on a page do not clash. Only the keys are added: the text is otherwise as typed."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return code
    lines = code.split("\n")
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in WIDGETS
        and not any(k.arg == "key" or k.arg is None for k in node.keywords)
        and node.end_lineno is not None
        and node.end_col_offset is not None
    ]
    calls.sort(key=lambda node: (node.lineno, node.col_offset))
    edits: list[tuple[int, int, str]] = []
    for number, node in enumerate(calls, start=1):
        row = (node.end_lineno or 1) - 1
        at = _offset(lines[row], node.end_col_offset or 0) - 1  # the closing bracket
        given: list[ast.AST] = [*node.args, *(k.value for k in node.keywords)]
        key = f'key="{prefix}_{number}"'
        if not given:
            edits.append((row, at, key))
            continue
        last = max(given, key=lambda g: (getattr(g, "end_lineno", 0), getattr(g, "end_col_offset", 0)))
        last_row = (getattr(last, "end_lineno", node.lineno) or node.lineno) - 1
        between = [lines[last_row][_offset(lines[last_row], getattr(last, "end_col_offset", 0)) :]]
        if last_row == row:
            between = [between[0][: at - _offset(lines[row], getattr(last, "end_col_offset", 0))]]
        else:
            between += [*lines[last_row + 1 : row], lines[row][:at]]
        quiet = "\n".join(re.sub(r"#.*$", "", part) for part in between)
        # After a comment on the same line a key would be part of the comment: it starts a new line.
        lead = "\n" if "#" in between[-1] else ""
        edits.append((row, at, lead + (key if "," in quiet else f", {key}")))
    for row, at, text in sorted(edits, reverse=True):
        lines[row] = lines[row][:at] + text + lines[row][at:]
    return "\n".join(lines)


def runs_something(code: str) -> bool:
    try:
        return bool(ast.parse(code).body)
    except (SyntaxError, ValueError, RecursionError):
        return False


@dataclass(frozen=True)
class PieceCode:
    """A cell as a page takes it."""

    cell: int
    name: str
    code: str
    where: str = ""  # the words for where it is: "cell 4", or "sales.ipynb @cell4" on a canvas

    @property
    def place(self) -> str:
        return self.where or f"cell {self.cell}"


@dataclass(frozen=True)
class PageCode:
    code: str
    tables: tuple[str, ...]  # the tables it reads, as Python variables
    order: tuple[str, ...]  # the blocks' ids in the order they run
    problems: tuple[str, ...]  # what the page says instead of running a block
    # (block, name): a name a block reads whose maker is not on the page, given its default instead
    defaulted: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Fallback:
    """A name's default, from the contract of the cell that makes it (domain/controllers.py), for a
    page that does not hold that cell: the default as Python, the words for that cell, and the table
    it names when the default is a table (`by_region: table = orders`)."""

    code: str
    maker: str
    table: str | None = None


def _listed(names: Sequence[str]) -> str:
    shown = list(names)
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def preamble(tables: Sequence[str], data: str, loader: str | None = None) -> list[str]:
    """What a page starts with: Streamlit and pandas, and each table the page names. Usually a table
    is read from its Parquet file (read again only when the file has changed; `data` is the Python
    expression of the data folder). With `loader` (a module's name: a project's data.py) they are
    imported from it instead: a saved project's pages, which hold no rows."""
    lines = ["import pandas as pd", "import streamlit as st"]
    if not tables:
        return lines
    if loader is not None:
        return [*lines, "", f"from {loader} import {', '.join(tables)}"]
    lines = ["from pathlib import Path", "", *lines]
    lines += [
        "",
        f"_DATA = {data}",
        "",
        "",
        "@st.cache_data(show_spinner=False)",
        "def _table(name: str, changed: float) -> pd.DataFrame:",
        '    return pd.read_parquet(_DATA / f"{name}.parquet")',
        "",
        "",
    ]
    for table in tables:
        lines.append(f'{table} = _table("{table}", (_DATA / "{table}.parquet").stat().st_mtime)')
    return lines


def _options(box: Container, names: Sequence[str]) -> str:
    """A container's own properties as arguments, the ones that are not Streamlit's defaults."""
    given = [f"{name}={box.props[name]!r}" for name in names if name in box.props]
    return "".join(f", {text}" for text in given)


def _layout(placed: Sequence[Block], containers: Sequence[Container] = ()) -> list[str]:
    """The page's layout as empty slots: a row of `st.columns` for each row of the grid (the empty
    columns between and after the blocks are columns too, left empty), a container in each. A layout
    container is opened where it sits (`st.columns`, `st.tabs`, `st.expander`, `st.container`, `st.form`,
    `st.popover`; the sidebar is `st.sidebar`) and each of its slots laid out the same way inside it."""
    page = Page("", "", list(placed), list(containers))
    groups = grouped(page)
    out: list[str] = []

    def opened(box: Container, holder: str) -> None:
        inside = f"_in_{box.id}"
        tag = f"{box.id}_"
        if box.kind == "columns":
            out.append(
                f"{inside} = {holder}.columns({box.get('widths')!r}"
                f"{_options(box, ('gap', 'vertical_alignment', 'border'))})"
            )
        elif box.kind == "tabs":
            out.append(f"{inside} = {holder}.tabs({box.get('labels')!r})")
        elif box.kind == "expander":
            out.append(
                f"{inside} = {holder}.expander({box.get('label')!r}{_options(box, ('expanded', 'icon'))})"
            )
        elif box.kind == "container":
            height = "" if box.h is None else f", height={box.h * ROW_HEIGHT}"
            out.append(f"{inside} = {holder}.container(border={box.get('border')!r}{height})")
        elif box.kind == "form":
            out.append(
                f"{inside} = {holder}.form({box.id!r}"
                f"{_options(box, ('clear_on_submit', 'enter_to_submit', 'border'))})"
            )
        elif box.kind == "popover":
            out.append(
                f"{inside} = {holder}.popover({box.get('label')!r}"
                f"{_options(box, ('icon', 'help', 'disabled'))})"
            )
        if box.slots == 1 and box.kind not in ("columns", "tabs"):
            lay((box.id, 0), inside, tag)
        else:
            for slot in range(box.slots):
                lay((box.id, slot), f"{inside}[{slot}]", f"{tag}{slot}_")
        if box.kind == "form":
            name = box.get("submitted") or f"_submitted_{box.id}"
            out.append(f"{name} = {inside}.form_submit_button({box.get('submit')!r})")

    def put(item: Item, holder: str) -> None:
        if isinstance(item, Container):
            opened(item, holder)
        else:
            height = "" if item.h is None else f"height={item.h * ROW_HEIGHT}"
            out.append(f"_slot_{item.id} = {holder}.container({height})")

    def lay(key: Group, into: str, tag: str) -> None:
        for number, row in enumerate(rows(groups.get(key, [])), start=1):
            if len(row) == 1 and row[0].w == COLUMNS:
                put(row[0], into)
                continue
            widths: list[int] = []
            slots: list[tuple[Item, int]] = []
            cursor = 1
            for item in row:
                if item.column > cursor:
                    widths.append(item.column - cursor)
                slots.append((item, len(widths)))
                widths.append(item.w)
                cursor = item.column + item.w
            if cursor <= COLUMNS:
                widths.append(COLUMNS - cursor + 1)
            out.append(f"_row_{tag}{number} = {into}.columns({widths})")
            for item, index in slots:
                put(item, f"_row_{tag}{number}[{index}]")

    lay((None, 0), "st", "")
    for bar in containers:
        if bar.kind == "sidebar":
            out.append(f"_in_{bar.id} = st.sidebar")
            lay((bar.id, 0), f"_in_{bar.id}", f"{bar.id}_")
    return out


LAYOUT_LINE: str = "# The layout: empty slots, drawn before any block runs."


def page_code(
    title: str,
    placed: Sequence[Block],
    pieces: Mapping[Key, PieceCode],
    tables: Iterable[str],
    data: str = 'Path(__file__).resolve().parent / "data"',
    guard: bool = True,
    notes: Mapping[str, str] | None = None,
    elsewhere: Mapping[str, str] | None = None,
    gone: Mapping[str, str] | None = None,
    loader: str | None = None,
    imports: Iterable[str] = (),
    fallbacks: Mapping[str, Fallback] | None = None,
    record: bool = False,
    trace: str | None = None,
    containers: Sequence[Container] = (),
) -> PageCode:
    """A page as one Streamlit page.

    1. Its layout is drawn first, as empty slots: a row of `st.columns` for each row of the grid, a
       container in each column.
    2. The blocks run in the order their names need (`run_order`); a cycle is an error on the page.
    3. Each block fills its own slot (`with slot:`), so a filter can sit anywhere on the page.
    4. Each block's widgets get keys of their own.

    `pieces`: each linked cell's code as it is now, by (file, cell). `tables`: the open tables' names
    as Python variables; the page reads the ones its code names. `guard`: a block that fails shows its
    error in its own slot and the others still run (the live page); without it the code is the plain
    page (an export). `notes`: a line of words above a block (a cell shown alone says where its
    inputs come from). `elsewhere`: names made by a cell that is not on this page, and where that
    cell is. `gone`: what to say for a block whose cell is not there, by the block's id. `loader`:
    the tables come from that module (a saved project's pages). `imports`: the other names the
    project's data.py gives; the ones the page reads are imported from it (`from data import TAX`).
    `fallbacks`: the defaults of names whose maker is not on the page (a controller's contract): a
    block that reads one gets its default, written once above the blocks. `record`: each block also
    writes its error into st.session_state (a test of the page reads them: domain/controllers.py).
    `trace`: the page's id, while it plays in the app: after each block runs, its names' values are
    noted for the lineage overlay (TRACE_MODULE), and its error when it fails.
    """
    known = [b for b in placed if b.key in pieces]
    found = {b.id: facts(pieces[b.key].code) for b in known}
    ordered = run_order([(b.id, found[b.id]) for b in known])
    by_id = {b.id: b for b in placed}
    named = list(tables)
    used: list[str] = []
    for b in known:
        used += [t for t in tables_named(pieces[b.key].code, named) if t not in used]
    also: list[str] = []
    if loader is None:
        given = [name for name in imports if name not in named]
        for b in known:
            also += [n for n in tables_named(pieces[b.key].code, given) if n not in also]
        # A name made on the page itself is the page's own.
        also = [n for n in also if not any(n in found[b.id].makes for b in known)]
    # The names each block reads whose maker is elsewhere: a default when the maker's contract gives
    # one, else the block says where its maker is.
    far: dict[str, list[str]] = {}
    for block_id in ordered.order:
        mine = found[block_id]
        far[block_id] = [
            name
            for name in mine.reads
            if elsewhere
            and name in elsewhere
            and name not in used
            and name not in also
            and not any(k == block_id and n == name for k, n, _ in ordered.links)
        ]
    fell = fallbacks or {}
    defaulted = [(b, n) for b in ordered.order if not found[b].problem for n in far[b] if n in fell]
    for _, name in defaulted:
        table = fell[name].table
        if table in named and table not in used:
            used.append(table)
    problems: list[str] = []
    out: list[str] = [f"# {title}"]
    if record:
        out += ["import streamlit as st", "", f"st.session_state[{RECORD!r}] = {{}}", ""]
    out += preamble(used, data, loader)
    if also:
        out += ["", f"from data import {', '.join(also)}"]
    out.append("")
    defaults = list(dict.fromkeys(name for _, name in defaulted))
    if defaults:
        out.append("# Defaults: their makers are not on this page.")
        if any(fell[n].code.startswith("_sab_date(") for n in defaults):
            out.append("from datetime import date as _sab_date")
        out += [f"{name} = {fell[name].code}  # {fell[name].maker}" for name in defaults]
        out.append("")

    if trace is not None:
        out += [f"import {TRACE_MODULE} as _sab_lineage", "", f"_sab_lineage.start(__file__, {trace!r})", ""]
    out.append(LAYOUT_LINE)
    out += _layout(placed, containers)
    out.append("")

    def say(block_id: str, words: str) -> None:
        problems.append(words)
        out.extend([f"with _slot_{block_id}:", f"    st.error({words!r})", ""])
        if record:
            out.extend([f"st.session_state[{RECORD!r}][{block_id!r}] = {words!r}", ""])

    for b in placed:
        if b.key not in pieces:
            words = (gone or {}).get(
                b.id
            ) or f"Cell {b.cell} is gone: it was deleted. Take its block off the page."
            say(b.id, words)
    if ordered.cycle:
        names = _listed([pieces[by_id[i].key].name for i in ordered.cycle])
        loop = sorted({name for key, name, source in ordered.links if key in ordered.cycle})
        for block_id in ordered.cycle:
            say(
                block_id,
                f"{names} need each other's names ({_listed(loop)}): "
                "no order runs them. One of them must not read what the other makes.",
            )
    for block_id in ordered.order:
        b = by_id[block_id]
        piece = pieces[b.key]
        mine = found[block_id]
        made = f": makes {_listed(mine.makes)}" if mine.makes else ""
        out.append(f"# {piece.name} ({piece.place}){made}")
        if mine.problem:
            say(block_id, f"{piece.name} ({piece.place}) is not whole Python yet: {mine.problem}.")
            continue
        missing = [name for name in far[block_id] if name not in fell]
        if missing and elsewhere:
            cells = _listed([f"{name} ({elsewhere[name]})" for name in missing])
            say(block_id, f"{piece.name} reads {cells}, which is not on this page: place that cell here too.")
            continue
        text = keyed(body(shown(piece.code, b.view)).rstrip("\n"), b.id)
        if notes and block_id in notes:
            text = f"st.caption({notes[block_id]!r})\n{text}"
        if not runs_something(text):
            text = "pass"
        out.append(f"with _slot_{b.id}:")
        noted = ""
        if trace is not None:
            getters = ", ".join(f"{name!r}: lambda: {name}" for name in mine.makes if name not in PROVIDED)
            noted = f"_sab_lineage.note(__file__, {trace!r}, {b.id!r}, {{{getters}}}"
        if guard:
            out.append("    try:")
            out.append(indented(text, "        "))
            if noted:
                out.append(f"        {noted})")
            out.append("    except Exception as _error:")
            out.append("        st.exception(_error)")
            if record:
                said = 'f"{type(_error).__name__}: {_error}"'
                out.append(f"        st.session_state[{RECORD!r}][{b.id!r}] = {said}")
            if noted:
                out.append(f"        {noted}, _error)")
        else:
            out.append(indented(text))
        out.append("")
    return PageCode(
        "\n".join(out).rstrip("\n") + "\n", tuple(used), ordered.order, tuple(problems), tuple(defaulted)
    )


def makers(codes: Mapping[int, str], order: Sequence[int]) -> dict[int, Facts]:
    """Each cell's facts, by its number, in the document's order."""
    return {cell: facts(codes[cell]) for cell in order if cell in codes}


def inputs_of(cell: int, found: Mapping[int, Facts], order: Sequence[int]) -> list[tuple[int, str]]:
    """The cells a cell needs to show alone, as (cell, the name it gives): for each name it reads
    that another of the cells makes, the nearest such cell above it (else the first below), and what
    those need in turn. In the document's order."""
    place = {c: i for i, c in enumerate(order)}
    wanted: dict[int, str] = {}

    def need(of: int) -> None:
        for name in found[of].reads:
            others = [c for c in order if c != of and c in found and name in found[c].makes]
            if not others:
                continue
            above = [c for c in others if place[c] < place[of]]
            source = above[-1] if above else others[0]
            if source != cell and source not in wanted:
                wanted[source] = name
                need(source)

    if cell in found:
        need(cell)
    return sorted(wanted.items(), key=lambda item: place[item[0]])


def preview_code(
    cell: int, pieces: Mapping[int, PieceCode], order: Sequence[int], tables: Iterable[str]
) -> PageCode:
    """A cell alone, live: the cell, and above it the cells that make the names it reads (each with a
    line saying which cell it is), so its widgets and its links work in its own cell. `pieces` are the
    document's cells that call Streamlit: only those are drawn with it."""
    found = {c: facts(pieces[c].code) for c in order if c in pieces}
    inputs = inputs_of(cell, found, order)
    shown = [*(c for c, _ in inputs), cell]
    placed = [Block(f"c{c}", "", c, row, 1, COLUMNS) for row, c in enumerate(shown, start=1)]
    notes = {f"c{c}": f"{name} comes from cell {c}" for c, name in inputs}
    keyed_pieces = {("", c): piece for c, piece in pieces.items()}
    return page_code(pieces[cell].name, placed, keyed_pieces, tables, notes=notes)


def elsewhere(page: Page, found: Mapping[Key, Facts], where: Mapping[Key, str]) -> dict[str, str]:
    """The names made only by cells that are not on this page, and where the cell that makes each is
    (`where`: the words for a cell). `found`: every Python cell of the linked files."""
    here = {b.key for b in page.blocks}
    made_here = {name for key in here if key in found for name in found[key].makes}
    out: dict[str, str] = {}
    for key, mine in found.items():
        if key in here:
            continue
        for name in mine.makes:
            if name not in made_here and name not in PROVIDED:
                out.setdefault(name, where.get(key, f"cell {key[1]}"))
    return out


# ----- the live app: one entry that reads what there is to show -----

# The live app's entry never changes: it reads the manifest each time it runs, so a page changed on
# the canvas shows without a restart.
ENTRY: str = '''\
"""A Streamlit app as Swiss Army Bench's Workbench shows it live (made by the app)."""
import json
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_MANIFEST = json.loads((_HERE / "manifest.json").read_text(encoding="utf-8"))
st.set_page_config(
    page_title=_MANIFEST["title"], page_icon=_MANIFEST.get("icon"), layout=_MANIFEST.get("layout") or "wide"
)
if _MANIFEST.get("logo"):
    st.logo(_MANIFEST["logo"])
_PAGES = [
    st.Page(str(_HERE / page["file"]), title=page["title"], url_path=page["path"], default=page["default"])
    for page in _MANIFEST["pages"]
]
_current = st.navigation(_PAGES, position="hidden")
_designed = [page for page, said in zip(_PAGES, _MANIFEST["pages"]) if said["kind"] == "page"]
if _current is _PAGES[0] and _designed:
    st.switch_page(_designed[0])  # the app's own address: its first page
if st.query_params.get("sab") != "frame":
    # The app at its own address: its pages, listed at the side.
    if len(_designed) > 1:
        with st.sidebar:
            for _page in _designed:
                st.page_link(_page)
_current.run()
'''

HOME: str = 'import streamlit as st\n\nst.title("No pages yet")\n'


def slug(name: str, taken: Iterable[str] = ()) -> str:
    """A page's name as a module's name: `Sales overview` -> `sales_overview`, never one in use."""
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "page"
    if base[0].isdigit():
        base = f"page_{base}"
    used = set(taken)
    found, n = base, 2
    while found in used:
        found = f"{base}_{n}"
        n += 1
    return found


# ===== export: the pages as a folder that runs without this app =====


def requirements(codes: Iterable[str], base: Sequence[str] = REQUIREMENTS) -> list[str]:
    """What the app needs: Streamlit, pandas and pyarrow (or `base`), and what its cells import (found
    with Python's parser; the standard library and this app left out)."""
    every = list(codes)
    needed = list(base)
    if any("unsafe_allow_javascript" in code for code in every):
        needed = [SCRIPT_STREAMLIT if re.match(r"streamlit\b", line) else line for line in needed]
    have = {re.split(r"[<>=!~ ]", line)[0].lower() for line in needed}
    for code in every:
        for module in facts(code).modules:
            if provided(module) or module in (TEXT_MODULE, QUERY_MODULE):
                continue
            name = pip_name(module)[0]
            if name.lower() not in have:
                have.add(name.lower())
                needed.append(name)
    return needed


@dataclass(frozen=True)
class Export:
    files: dict[str, str]  # each file's path in the folder, and its text
    tables: tuple[str, ...]  # the tables that go into data/, as Python variables
    problems: tuple[str, ...]


README: str = """\
{title}: a Streamlit app, made on Swiss Army Bench's Streamlit canvas.

Run it:

    pip install -r requirements.txt
    streamlit run app.py

app.py          the app: its pages
app_pages/      one module for each page, laid out as it was designed
data/           the tables the pages read, as Parquet
{text}"""

# What a README says of the copy that fills the Markdown and HTML blocks' names (nothing new to install).
TEXT_README: str = (
    f"{TEXT_FILE}     fills the {{{{ names }}}} of the Markdown and HTML blocks: standard library only, so\n"
    "                they need nothing new installed\n"
)


def text_file(helper: str) -> str:
    """`sab_text.py`: the HTML cells' rules (domain/html_cells.py's text, `helper`) with a line on top."""
    return TEXT_HEADER + helper


def export(
    title: str,
    pages: Sequence[Page],
    pieces: Mapping[Key, PieceCode],
    tables: Iterable[str],
    found: Mapping[Key, Facts] | None = None,
    where: Mapping[Key, str] | None = None,
    gone: Mapping[str, str] | None = None,
    helper: str = "",
    fallbacks: Mapping[str, Mapping[str, Fallback]] | None = None,
    head: Sequence[str] = (),
    config: str | None = None,
) -> Export:
    """The pages as a runnable folder: app.py (st.navigation over the pages), one module a page,
    requirements.txt and README.txt. The tables it names go into data/ (the caller writes them). A
    page with a Markdown or HTML block that names a value gets `sab_text.py` beside app.py: `helper`,
    the text of domain/html_cells.py (the pages import it; Streamlit puts app.py's folder on the path).
    `fallbacks`: each page's defaults (by its id), as `page_code` takes them."""
    if not pages:
        raise StreamlitError("There is no page to export yet.")
    named = list(tables)
    files: dict[str, str] = {}
    used: list[str] = []
    problems: list[str] = []
    codes: list[str] = []
    modules: list[tuple[str, str]] = []
    every = found if found is not None else {key: facts(piece.code) for key, piece in pieces.items()}
    for page in pages:
        module = slug(page.name, [m for m, _ in modules])
        made = page_code(
            page.name,
            page.blocks,
            pieces,
            named,
            data='Path(__file__).resolve().parent.parent / "data"',
            guard=False,
            elsewhere=elsewhere(page, every, where or {}),
            gone=gone,
            fallbacks=(fallbacks or {}).get(page.id),
            containers=page.containers,
        )
        files[f"app_pages/{module}.py"] = made.code
        modules.append((module, page.name))
        used += [t for t in made.tables if t not in used]
        problems += [f"{page.name}: {p}" for p in made.problems]
        codes += [pieces[b.key].code for b in page.blocks if b.key in pieces]
    lines = [
        f'"""{title}: a Streamlit app from Swiss Army Bench\'s Streamlit canvas. '
        'Run: streamlit run app.py"""',
        "import streamlit as st",
        "",
        *(head or [f'st.set_page_config(page_title={title!r}, layout="wide")']),
        "st.navigation(",
        "    [",
    ]
    for index, (module, name) in enumerate(modules):
        default = ", default=True" if index == 0 else ""
        lines.append(f'        st.Page("app_pages/{module}.py", title={name!r}{default}),')
    lines += ["    ]", ").run()", ""]
    files["app.py"] = "\n".join(lines)
    files["requirements.txt"] = "\n".join(requirements(codes)) + "\n"
    texts = bool(helper) and any(uses_text_module(code) for code in codes)
    if texts:
        files[TEXT_FILE] = text_file(helper)
    files["README.txt"] = README.format(title=title, text=TEXT_README if texts else "")
    if config:
        files[".streamlit/config.toml"] = config  # the page settings' theme colours
    return Export(files, tuple(used), tuple(problems))


def with_queries(made: Export, module: str, needed: Iterable[str]) -> None:
    """An export with its SQL and DAX blocks' sab_queries.py (`module`) beside app.py, and what that
    needs installed in requirements.txt."""
    made.files[QUERY_FILE] = module
    have = made.files["requirements.txt"].split()
    lower = {re.split(r"[<>=!~ ]", line)[0].lower() for line in have}
    extra = [line for line in needed if re.split(r"[<>=!~ ]", line)[0].lower() not in lower]
    made.files["requirements.txt"] = "\n".join([*have, *extra]) + "\n"
    made.files["README.txt"] += (
        f"{QUERY_FILE}  the connections the SQL and DAX blocks query, each one's own code (its settings\n"
        "                read from the environment: no password is written here)\n"
    )


# ===== Save as: the pages as modules of a project (domain/projects.py) =====


@dataclass(frozen=True)
class SavedPages:
    files: dict[str, str]  # pages/<page>.py, and its text
    tables: tuple[str, ...]  # the names the pages import from data.py
    problems: tuple[str, ...]
    requirements: tuple[str, ...]  # what the pages' own code needs installed
    # A page fills a Markdown or HTML block's names: sab_text.py goes beside data.py (`text_file`).
    texts: bool = False


# A saved page's second line: whose export it is. Save as writes over (and takes away) only the
# pages/*.py of the same app; a page of the user's own, or of another app in the folder, stays.
PAGE_MARK: str = "# Written from {app} by Swiss Army Bench: change the canvas, not this file."
# The line a page saved before the rename carries (SwissArmyGrid's): still this app's page to write over.
OLD_PAGE_MARK: str = "# Written from {app} by SwissArmyGrid: change the canvas, not this file."


def page_mark(app: str) -> str:
    """The line a saved page of this app (its file's name: `sales.stapp.json`) carries."""
    return PAGE_MARK.format(app=app.replace("\n", " "))


def is_saved_page(text: str, app: str) -> bool:
    """A pages/*.py this app's Save as wrote (and may write again or take away)."""
    head = text.split("\n", 3)[:3]
    return page_mark(app) in head or OLD_PAGE_MARK.format(app=app.replace("\n", " ")) in head


def saved_pages(
    pages: Sequence[Page],
    pieces: Mapping[Key, PieceCode],
    tables: Iterable[str],
    found: Mapping[Key, Facts] | None = None,
    where: Mapping[Key, str] | None = None,
    gone: Mapping[str, str] | None = None,
    app: str = "app.stapp.json",
    fallbacks: Mapping[str, Mapping[str, Fallback]] | None = None,
    head: Sequence[str] = (),
) -> SavedPages:
    """The pages as a project's pages/*.py: each a page to drop into a Streamlit app, starting with
    `from data import ...` for the tables (and blade variables) it names. `tables`: the names data.py
    can give. No data folder, no rows: data.py reads each table again. `app`: the app's file's name,
    on each page's second line (`page_mark`)."""
    if not pages:
        raise StreamlitError("There is no page to save yet.")
    files: dict[str, str] = {}
    used: list[str] = []
    problems: list[str] = []
    codes: list[str] = []
    names: list[str] = []
    named = list(tables)
    every = found if found is not None else {key: facts(piece.code) for key, piece in pieces.items()}
    for page in pages:
        name = slug(page.name, names)
        names.append(name)
        made = page_code(
            page.name,
            page.blocks,
            pieces,
            named,
            guard=False,
            elsewhere=elsewhere(page, every, where or {}),
            gone=gone,
            loader="data",
            fallbacks=(fallbacks or {}).get(page.id),
            containers=page.containers,
        )
        title, _, rest = made.code.partition("\n")
        if head:  # the page settings: st.set_page_config and st.logo, before the layout
            rest = rest.replace(LAYOUT_LINE, "\n".join([*head, "", LAYOUT_LINE]), 1)
        files[f"pages/{name}.py"] = f"{title}\n{page_mark(app)}\n{rest}"
        used += [t for t in made.tables if t not in used]
        problems += [f"{page.name}: {p}" for p in made.problems]
        codes += [pieces[b.key].code for b in page.blocks if b.key in pieces]
    needed = requirements(codes, ["streamlit>=1.36", "pandas"])
    texts = any(uses_text_module(code) for code in codes)
    return SavedPages(files, tuple(used), tuple(problems), tuple(needed), texts)


def bundle_names(documents: Sequence[str], taken: Iterable[str] = ()) -> dict[str, str]:
    """The name in a saved project's zip of each linked file that is outside the project's folder:
    its own name, one of a kind (`analysis.ipynb`, `analysis_2.ipynb` for a second file of that name
    from another folder, or when the zip already holds one: `taken`, the project's own files)."""
    names: dict[str, str] = {}
    held = {name.lower() for name in taken}
    for document in documents:
        if document in names:
            continue
        base = re.split(r"[\\/]", document)[-1] or "document"
        stem, dot, ending = base.partition(".")
        name, n = base, 2
        while name.lower() in held:
            name = f"{stem}_{n}{dot}{ending}"
            n += 1
        held.add(name.lower())
        names[document] = name
    return names


# ===== the agent's approval: what its export or Save as writes =====


def _rows_of(tables: Sequence[DatasetInfo]) -> list[str]:
    return [f"  {info.name} ({info.row_count:,} rows as loaded)" for info in tables]


def export_detail(target: str, pages: list[str], tables: Sequence[DatasetInfo]) -> str:
    """The approval prompt's words for the agent's Streamlit export: which folder, which pages, and
    which tables' rows are copied there."""
    lines = [
        "An app that runs alone (app.py, its pages, requirements.txt), written into the folder:",
        f"  {target}",
        f"Pages: {', '.join(pages) if pages else '(none)'}",
    ]
    if tables:
        lines.append("With a copy of these tables' rows, after their grid's steps, as Parquet in data/:")
        lines += _rows_of(tables)
    else:
        lines.append("No table rows: the pages read no open table.")
    return "\n".join(lines)


def save_as_detail(target: str, notebook: str, tables: Sequence[DatasetInfo]) -> str:
    """The approval prompt's words for a Save as that first writes the project's data.ipynb, which
    holds the rows pasted into the grid (the zip itself holds no rows)."""
    return "\n".join(
        [
            "The project as one zip (it holds no rows):",
            f"  {target}",
            "First, the project's data.ipynb, written into its folder:",
            f"  {notebook}",
            "It holds the rows pasted into the grid of:",
            *_rows_of(tables),
        ]
    )


# ===== the Connections page: a canvas's blocks that use a connection =====


def canvas_references(
    path: str,
    title: str,
    text: str,
    using: Iterable[usage.Reference],
    resolve: Callable[[str, str], str] = resolve_link,
) -> list[usage.Reference]:
    """Every block of a Streamlit app's canvas whose cell is one of `using` (the cells found above)."""
    cells = [r for r in using if r.cell is not None and r.kind in ("notebook", "script")]
    found: list[usage.Reference] = []
    for page in read_app(text, lambda link: resolve(path, link)):
        for block in page.blocks:
            hit = next(
                (r for r in cells if r.cell == block.cell and same_file(r.document, block.document)),
                None,
            )
            if hit is not None:
                where = f"{hit.title} @cell{hit.cell}"
                found.append(
                    dataclasses.replace(
                        hit,
                        document=path,
                        title=title,
                        kind="app",
                        line=where,
                        page=page.name,
                        block=block.id,
                        table_cell=False,
                    )
                )
    return found


def outline_pages(
    path: str, text: str, resolve: Callable[[str, str], str] = resolve_link
) -> list[tuple[str, list[tuple[str, int]]]]:
    """An app's pages for the project's outline (the base's hooks.app_pages): each page's name and the cells
    its blocks link (the document's whole path, the cell's number), in the order they sit on the page."""
    out = []
    for page in read_app(text, lambda link: resolve(path, link)):
        placed = sorted(page.blocks, key=lambda b: (b.row, b.column, b.id))
        out.append((page.name, [(b.document, b.cell) for b in placed]))
    return out
