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
"""

from __future__ import annotations

import ast
import io
import json
import ntpath
import posixpath
import re
import tokenize
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from swissarmygrid.domain import notebooks, table_cells
from swissarmygrid.domain.blades import pip_name, provided
from swissarmygrid.domain.html_cells import check_height
from swissarmygrid.domain.streamlit_use import uses_streamlit, usual_name

__all__ = ["uses_streamlit", "usual_name"]

APP_SUFFIX: str = notebooks.APP_SUFFIX
APP_MARK: str = "streamlit-app"
APP_VERSION: int = 1
MAX_APP_CHARS: int = 2_000_000
_ANY_MARKER = re.compile(r"^# ?%%")

COLUMNS: int = 12
ROW_HEIGHT: int = 40  # pixels a unit of a block's height stands for (the Sandbox board's row)
DEFAULT_WIDTH: int = 6
MIN_WIDTH: int = 2
MAX_HEIGHT: int = 30
MAX_PAGES: int = 30
MAX_PLACED: int = 60
MAX_NAME: int = 80
MAX_PIECES: int = 2_000
MAX_PATH: int = 1_000
# Streamlit's widgets: a call of one of these gets a key of its own when it has none.
WIDGETS: frozenset[str] = frozenset(
    {
        "button",
        "download_button",
        "checkbox",
        "toggle",
        "radio",
        "selectbox",
        "multiselect",
        "slider",
        "select_slider",
        "text_input",
        "number_input",
        "text_area",
        "date_input",
        "time_input",
        "file_uploader",
        "camera_input",
        "audio_input",
        "color_picker",
        "data_editor",
        "pills",
        "segmented_control",
        "feedback",
        "chat_input",
    }
)
# What every page has before its blocks run: Streamlit and pandas, under their usual names.
PROVIDED: frozenset[str] = frozenset({"st", "pd"})
REQUIREMENTS: tuple[str, ...] = ("streamlit>=1.36", "pandas", "pyarrow")

# A block's cell: the linked file's path (as the app holds it) and the cell's own number. A piece
# shown alone in its own document has "" for the path.
Key = tuple[str, int]


class StreamlitError(ValueError):
    """An app, its pages or its cells that cannot be taken as sent (the message says why)."""


# ===== a cell: its title, what it makes and reads =====


def body(code: str) -> str:
    """A cell's own code: without the app's uses line."""
    return table_cells.split_uses(code)[1]


def piece_name(code: str, number: int) -> str:
    """A cell's title on the canvas: its first line when that is a comment (`# Region filter`), else
    its first line of code; "Cell N" for an empty one (N is the cell's own number)."""
    for line in body(code).split("\n"):
        if not line.strip():
            continue
        found = re.match(r"^#+\s*(.+?)\s*$", line)
        if found and not line.startswith("#!") and not _ANY_MARKER.match(line):
            return found.group(1)[:MAX_NAME]
        if _ANY_MARKER.match(line):
            continue
        return line.strip()[:MAX_NAME]
    return f"Cell {number}"


@dataclass(frozen=True)
class Facts:
    makes: tuple[str, ...] = ()  # names it gives a value at its top level
    reads: tuple[str, ...] = ()  # names it reads before making them itself (not built-ins)
    modules: tuple[str, ...] = ()  # the modules it imports, as written (`plotly.express`)
    problem: str | None = None  # its code is not whole Python: "line 3: ..."


def _modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return list(dict.fromkeys(found))


@lru_cache(maxsize=4096)
def facts(code: str) -> Facts:
    """What a cell makes and reads, by Python's own parser (the reading table cells use)."""
    text = body(code)
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        problem = f"line {error.lineno or 1}: {error.msg}"
        read = table_cells.facts(text)
        return Facts(read.made, read.needs, (), problem)
    except (ValueError, RecursionError):
        return Facts(problem="its code cannot be read")
    read = table_cells.facts(text)
    return Facts(read.made, read.needs, tuple(_modules(tree)))


def tables_named(code: str, tables: Iterable[str]) -> list[str]:
    """The tables a cell names (real names only: Python's tokenizer, as the uses line reads them),
    in the order it first names them. `tables` are the tables' names as Python variables."""
    known = set(tables)
    return [name for name in table_cells.names_used(body(code)) if name in known]


def live_cells(cells: Sequence[tuple[int, str]]) -> list[int]:
    """The cells of a document that call Streamlit (each is shown live in its cell), by number."""
    usual = usual_name(tuple(code for _, code in cells))
    return [number for number, code in cells if code.strip() and uses_streamlit(body(code), usual)]


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


def document_cells(path: str, text: str) -> list[tuple[int, str]]:
    """A notebook's or script's Python cells as (the cell's own number, its code), in file order: the
    cells a block can link to. A table's read-only cell and the Tables group's own lines are not the
    user's; a script cell without a number yet (never opened here) cannot be linked."""
    if notebooks.kind_of(path) == "notebook":
        cells, _ = notebooks.read_document(text)
        return [
            (c.number, c.source)
            for c in cells
            if c.kind == "code" and c.role in ("", "maker") and c.number is not None
        ]
    return [
        (c.number, c.source.rstrip("\n"))
        for c in table_cells.parse_script(text).cells
        if c.number is not None and not c.fixed and not c.html and c.role in ("", "maker")
    ]


def document_names(path: str, text: str) -> dict[int, str]:
    """The names a notebook's or script's Python cells have (a notebook's metadata, a script's marker
    words), by the cell's own number. A cell without a name is not listed."""
    if notebooks.kind_of(path) == "notebook":
        cells, _ = notebooks.read_document(text)
        return {c.number: c.name for c in cells if c.kind == "code" and c.number is not None and c.name}
    return {
        c.number: name
        for c in table_cells.parse_script(text).cells
        if c.number is not None and not c.fixed and not c.html and (name := table_cells.marker_name(c.title))
    }


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

    @property
    def key(self) -> Key:
        return (self.document, self.cell)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document": self.document,
            "cell": self.cell,
            "row": self.row,
            "column": self.column,
            "w": self.w,
            "h": self.h,
        }


@dataclass
class Page:
    id: str
    name: str
    blocks: list[Block] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "blocks": [b.to_json() for b in self.blocks]}


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


def next_id(prefix: str, taken: Iterable[str]) -> str:
    """The next id of a kind (p1, p2... for pages; b1, b2... for blocks), never one in use."""
    used = set(taken)
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def settle(blocks: list[Block], first: Block | None = None) -> None:
    """The blocks as the grid holds them: in reading order (row, then column), no two on the same
    columns of a row, none past column 12. A block that would lie on another starts a row of its
    own below; `first` (the block just moved or placed) keeps the place it was given, and the
    neighbour it would lie on goes below. Rows are counted from 1 with none empty."""
    order = {id(b): i for i, b in enumerate(blocks)}
    for block in blocks:
        block.w = max(MIN_WIDTH, min(COLUMNS, block.w))
        block.column = max(1, min(COLUMNS - block.w + 1, block.column))
    asked: dict[int, list[Block]] = {}
    for block in blocks:
        asked.setdefault(block.row, []).append(block)
    settled: list[list[Block]] = []
    for row in sorted(asked):
        waiting = sorted(asked[row], key=lambda b: (b is not first, b.column, order[id(b)]))
        while waiting:
            taken: set[int] = set()
            here: list[Block] = []
            below: list[Block] = []
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


def rows(blocks: Sequence[Block]) -> list[list[Block]]:
    """The blocks as the grid's rows (settled blocks: each row's in column order)."""
    out: dict[int, list[Block]] = {}
    for block in blocks:
        out.setdefault(block.row, []).append(block)
    return [out[row] for row in sorted(out)]


def free_place(blocks: Sequence[Block], width: int = DEFAULT_WIDTH) -> tuple[int, int]:
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
                )
            )
        settle(page.blocks)
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
#       "swissarmygrid": "streamlit-app",
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


def write_app(pages: Sequence[Page], link: Callable[[str], str] = lambda document: document) -> str:
    """The app's file text. `link` gives each block's path as the file should hold it (relative to
    the file: `relative_link`)."""
    said = json.dumps
    lines = ["{", f'  "swissarmygrid": {said(APP_MARK)},', f'  "version": {APP_VERSION},']
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
                comma = "," if index + 1 < len(page.blocks) else ""
                lines.append(f"        {said(held, ensure_ascii=False)}{comma}")
            lines.append("      ]")
        else:
            lines.append('      "blocks": []')
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
    if not isinstance(data, dict) or data.get("swissarmygrid") != APP_MARK:
        raise StreamlitError(
            'This is not a Streamlit app\'s file: it has no "swissarmygrid": "streamlit-app".'
        )
    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version > APP_VERSION:
        raise StreamlitError("This Streamlit app was saved by a newer SwissArmyGrid: update to open it.")
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


def _string_lines(code: str) -> set[int]:
    """The lines (1-based) that go on a text started on an earlier line: indenting them would
    change the text."""
    inside: set[int] = set()
    opened: list[int] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type == tokenize.STRING and token.end[0] > token.start[0]:
                inside.update(range(token.start[0] + 1, token.end[0] + 1))
            elif token.type == tokenize.FSTRING_START:
                opened.append(token.start[0])
            elif token.type == tokenize.FSTRING_END and opened:
                inside.update(range(opened.pop() + 1, token.end[0] + 1))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return set()
    return inside


def indented(code: str, by: str = "    ") -> str:
    """The code one level in (to sit under a `with`), leaving the lines inside a multi-line text."""
    skip = _string_lines(code)
    out = []
    for number, line in enumerate(code.split("\n"), start=1):
        out.append(line if number in skip or not line.strip() else by + line)
    return "\n".join(out)


def _runs_something(code: str) -> bool:
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


def _layout(placed: Sequence[Block]) -> list[str]:
    """The page's layout as empty slots: a row of `st.columns` for each row of the grid (the empty
    columns between and after the blocks are columns too, left empty), a container in each."""
    out: list[str] = []
    for number, row in enumerate(rows(placed), start=1):
        height = {b.id: "" if b.h is None else f"height={b.h * ROW_HEIGHT}" for b in row}
        if len(row) == 1 and row[0].w == COLUMNS:
            out.append(f"_slot_{row[0].id} = st.container({height[row[0].id]})")
            continue
        widths: list[int] = []
        slots: list[tuple[Block, int]] = []
        cursor = 1
        for block in row:
            if block.column > cursor:
                widths.append(block.column - cursor)
            slots.append((block, len(widths)))
            widths.append(block.w)
            cursor = block.column + block.w
        if cursor <= COLUMNS:
            widths.append(COLUMNS - cursor + 1)
        out.append(f"_row_{number} = st.columns({widths})")
        for block, index in slots:
            out.append(f"_slot_{block.id} = _row_{number}[{index}].container({height[block.id]})")
    return out


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
    problems: list[str] = []
    out: list[str] = [f"# {title}", *preamble(used, data, loader)]
    if also:
        out += ["", f"from data import {', '.join(also)}"]
    out.append("")

    out.append("# The layout: empty slots, drawn before any block runs.")
    out += _layout(placed)
    out.append("")

    def say(block_id: str, words: str) -> None:
        problems.append(words)
        out.extend([f"with _slot_{block_id}:", f"    st.error({words!r})", ""])

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
        far = [
            name
            for name in mine.reads
            if elsewhere
            and name in elsewhere
            and name not in used
            and name not in also
            and not any(k == block_id and n == name for k, n, _ in ordered.links)
        ]
        if far and elsewhere:
            cells = _listed([f"{name} ({elsewhere[name]})" for name in far])
            say(block_id, f"{piece.name} reads {cells}, which is not on this page: place that cell here too.")
            continue
        text = keyed(body(piece.code).rstrip("\n"), b.id)
        if notes and block_id in notes:
            text = f"st.caption({notes[block_id]!r})\n{text}"
        if not _runs_something(text):
            text = "pass"
        out.append(f"with _slot_{b.id}:")
        if guard:
            out.append("    try:")
            out.append(indented(text, "        "))
            out.append("    except Exception as _error:")
            out.append("        st.exception(_error)")
        else:
            out.append(indented(text))
        out.append("")
    return PageCode("\n".join(out).rstrip("\n") + "\n", tuple(used), ordered.order, tuple(problems))


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
"""A Streamlit app as SwissArmyGrid's Workbench shows it live (made by the app)."""
import json
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_MANIFEST = json.loads((_HERE / "manifest.json").read_text(encoding="utf-8"))
st.set_page_config(page_title=_MANIFEST["title"], layout="wide")
_PAGES = [
    st.Page(str(_HERE / page["file"]), title=page["title"], url_path=page["path"], default=page["default"])
    for page in _MANIFEST["pages"]
]
_current = st.navigation(_PAGES, position="hidden")
_designed = [page for page, said in zip(_PAGES, _MANIFEST["pages"]) if said["kind"] == "page"]
if _current is _PAGES[0] and _designed:
    st.switch_page(_designed[0])  # the app's own address: its first page
if st.query_params.get("sag") != "frame":
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
    needed = list(base)
    have = {re.split(r"[<>=!~ ]", line)[0].lower() for line in needed}
    for code in codes:
        for module in facts(code).modules:
            if provided(module):
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
{title}: a Streamlit app, made on SwissArmyGrid's Streamlit canvas.

Run it:

    pip install -r requirements.txt
    streamlit run app.py

app.py          the app: its pages
app_pages/      one module for each page, laid out as it was designed
data/           the tables the pages read, as Parquet
"""


def export(
    title: str,
    pages: Sequence[Page],
    pieces: Mapping[Key, PieceCode],
    tables: Iterable[str],
    found: Mapping[Key, Facts] | None = None,
    where: Mapping[Key, str] | None = None,
    gone: Mapping[str, str] | None = None,
) -> Export:
    """The pages as a runnable folder: app.py (st.navigation over the pages), one module a page,
    requirements.txt and README.txt. The tables it names go into data/ (the caller writes them)."""
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
        )
        files[f"app_pages/{module}.py"] = made.code
        modules.append((module, page.name))
        used += [t for t in made.tables if t not in used]
        problems += [f"{page.name}: {p}" for p in made.problems]
        codes += [pieces[b.key].code for b in page.blocks if b.key in pieces]
    lines = [
        f'"""{title}: a Streamlit app from SwissArmyGrid\'s Streamlit canvas. Run: streamlit run app.py"""',
        "import streamlit as st",
        "",
        f'st.set_page_config(page_title={title!r}, layout="wide")',
        "st.navigation(",
        "    [",
    ]
    for index, (module, name) in enumerate(modules):
        default = ", default=True" if index == 0 else ""
        lines.append(f'        st.Page("app_pages/{module}.py", title={name!r}{default}),')
    lines += ["    ]", ").run()", ""]
    files["app.py"] = "\n".join(lines)
    files["requirements.txt"] = "\n".join(requirements(codes)) + "\n"
    files["README.txt"] = README.format(title=title)
    return Export(files, tuple(used), tuple(problems))


# ===== Save as: the pages as modules of a project (domain/projects.py) =====


@dataclass(frozen=True)
class SavedPages:
    files: dict[str, str]  # pages/<page>.py, and its text
    tables: tuple[str, ...]  # the names the pages import from data.py
    problems: tuple[str, ...]
    requirements: tuple[str, ...]  # what the pages' own code needs installed


# A saved page's second line: whose export it is. Save as writes over (and takes away) only the
# pages/*.py of the same app; a page of the user's own, or of another app in the folder, stays.
PAGE_MARK: str = "# Written from {app} by SwissArmyGrid: change the canvas, not this file."


def page_mark(app: str) -> str:
    """The line a saved page of this app (its file's name: `sales.stapp.json`) carries."""
    return PAGE_MARK.format(app=app.replace("\n", " "))


def is_saved_page(text: str, app: str) -> bool:
    """A pages/*.py this app's Save as wrote (and may write again or take away)."""
    return page_mark(app) in text.split("\n", 3)[:3]


def saved_pages(
    pages: Sequence[Page],
    pieces: Mapping[Key, PieceCode],
    tables: Iterable[str],
    found: Mapping[Key, Facts] | None = None,
    where: Mapping[Key, str] | None = None,
    gone: Mapping[str, str] | None = None,
    app: str = "app.stapp.json",
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
        )
        title, _, rest = made.code.partition("\n")
        files[f"pages/{name}.py"] = f"{title}\n{page_mark(app)}\n{rest}"
        used += [t for t in made.tables if t not in used]
        problems += [f"{page.name}: {p}" for p in made.problems]
        codes += [pieces[b.key].code for b in page.blocks if b.key in pieces]
    needed = requirements(codes, ["streamlit>=1.36", "pandas"])
    return SavedPages(files, tuple(used), tuple(problems), tuple(needed))


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


# ===== heights =====


def check_pane(height: Any) -> int | None:
    """A live cell's pane, in pixels (None: the usual height)."""
    return check_height(height)
