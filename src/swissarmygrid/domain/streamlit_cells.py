"""Streamlit cells (docs/ideas.md, 2026-11-15): pieces built in the Workbench, assembled on pages.

A Streamlit cell is a piece: a chart, a filter, a table, a number. Push to page sends it to a page of
the page designer, where pieces sit on a 12-column board. Pieces talk by shared names: a piece that
makes `region` drives every piece on the same page that reads `region`. Pure rules, no I/O:

  cells     the cell in a file: in a notebook a code cell whose first line is `# %% [streamlit]`; in a
            script a `# %% [streamlit]` cell. Its body is plain Python either way
  facts     what a piece makes and reads (Python's own parser), its name, the modules it imports
  pages     pages and the pieces placed on them, checked; kept in the notebook's metadata, and in a
            script as a `# %% [streamlit-pages]` block of comments
  order     the order the pieces of a page run in, by the names they need; a cycle is said
  code      a page as ONE Streamlit page: its layout drawn first as empty slots, then each piece run
            in name order inside its own slot, its widgets given keys of their own
  tables    the tables a page names, read from Parquet by a small preamble
  export    the designed pages as a folder that runs without this app
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmygrid.domain import table_cells
from swissarmygrid.domain.blades import pip_name, provided
from swissarmygrid.domain.html_cells import check_height

# The first line of a notebook's Streamlit cell in the file, and a script's cell marker.
MARK: str = "# %% [streamlit]"
_MARK_LINE = re.compile(r"^# ?%% \[streamlit\]\s*$")
PAGES_MARK: str = "# %% [streamlit-pages]"
_PAGES_LINE = re.compile(r"^# ?%%(?: \[\d+\])? \[streamlit-pages\]\s*$")
_ANY_MARKER = re.compile(r"^# ?%%")
_PAGES_NOTE: str = (
    "# The pages of this file's Streamlit app (SwissArmyGrid's page designer keeps this block)."
)

COLUMNS: int = 12
ROW_HEIGHT: int = 40  # pixels a unit of a piece's height stands for (the Sandbox board's row)
DEFAULT_WIDTH: int = 6
MIN_WIDTH: int = 2
MAX_HEIGHT: int = 30
MAX_PAGES: int = 30
MAX_PLACED: int = 60
MAX_NAME: int = 80
MAX_PIECES: int = 500
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
# What every page has before its pieces run: Streamlit and pandas, under their usual names.
PROVIDED: frozenset[str] = frozenset({"st", "pd"})
REQUIREMENTS: tuple[str, ...] = ("streamlit>=1.36", "pandas", "pyarrow")


class StreamlitError(ValueError):
    """Pages or pieces that cannot be taken as sent (the message says why)."""


# ===== the cell in a file =====


def is_marked(source: str) -> bool:
    """A notebook code cell's text that is a Streamlit cell: its first line is the marker."""
    return bool(_MARK_LINE.match(source.partition("\n")[0]))


def marked(code: str) -> str:
    """A Streamlit cell's code as the notebook file holds it: the marker, then the code."""
    return f"{MARK}\n{code}"


def unmarked(source: str) -> str:
    """The code under the marker."""
    return source.partition("\n")[2] if is_marked(source) else source


# ===== a piece: its name, what it makes and reads =====


def body(code: str) -> str:
    """A piece's own code: without the app's uses line."""
    return table_cells.split_uses(code)[1]


def piece_name(code: str, number: int) -> str:
    """A piece's name: its first line when that is a comment (`# Region filter`), else "Piece N"
    (N is the cell's own number)."""
    for line in body(code).split("\n"):
        if not line.strip():
            continue
        found = re.match(r"^#+\s*(.+?)\s*$", line)
        if found and not line.startswith("#!") and not _ANY_MARKER.match(line):
            return found.group(1)[:MAX_NAME]
        break
    return f"Piece {number}"


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


def facts(code: str) -> Facts:
    """What a piece makes and reads, by Python's own parser (the reading table cells use)."""
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
    """The tables a piece names (real names only: Python's tokenizer, as the uses line reads them),
    in the order it first names them. `tables` are the tables' names as Python variables."""
    known = set(tables)
    return [name for name in table_cells.names_used(body(code)) if name in known]


# ===== pages and the pieces placed on them =====


@dataclass
class Placed:
    """A piece on a page: which cell it is, and its place on the 12-column board (the pieces flow
    left to right in order, a row holding as many as fit)."""

    id: str
    cell: int
    w: int = DEFAULT_WIDTH
    h: int | None = None  # in units of ROW_HEIGHT; None: as tall as what it draws

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "cell": self.cell, "w": self.w, "h": self.h}


@dataclass
class Page:
    id: str
    name: str
    pieces: list[Placed] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "pieces": [p.to_json() for p in self.pieces]}


_ID = re.compile(r"^[A-Za-z0-9]{1,16}$")


def check_width(width: Any) -> int:
    if isinstance(width, bool) or not isinstance(width, int | float):
        raise StreamlitError(f"A piece's width is a whole number of columns, {MIN_WIDTH} to {COLUMNS}.")
    return max(MIN_WIDTH, min(COLUMNS, round(width)))


def check_rows(height: Any) -> int | None:
    """A piece's height in board rows (None: as tall as what it draws)."""
    if height is None:
        return None
    if isinstance(height, bool) or not isinstance(height, int | float):
        raise StreamlitError(f"A piece's height is a number of rows (1 to {MAX_HEIGHT}), or null.")
    return max(1, min(MAX_HEIGHT, round(height)))


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip() or "\n" in name or len(name.strip()) > MAX_NAME:
        raise StreamlitError(f"A page's name is one line of at most {MAX_NAME} characters.")
    return name.strip()


def next_id(prefix: str, taken: Iterable[str]) -> str:
    """The next id of a kind (p1, p2... for pages; s1, s2... for placed pieces), never one in use."""
    used = set(taken)
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def read_pages(sent: Any) -> list[Page]:
    """Pages as a file or the page designer holds them, checked. Ids are made where they are missing
    or used twice; a placed piece's ids are its own across the whole app."""
    if sent is None:
        return []
    if not isinstance(sent, list) or len(sent) > MAX_PAGES:
        raise StreamlitError(f"Pages are a list (at most {MAX_PAGES}).")
    pages: list[Page] = []
    page_ids: set[str] = set()
    placed_ids: set[str] = set()
    for raw in sent:
        if not isinstance(raw, dict):
            raise StreamlitError('Each page is {"id", "name", "pieces": [{"id", "cell", "w", "h"}]}.')
        page_id = raw.get("id")
        if not isinstance(page_id, str) or not _ID.match(page_id) or page_id in page_ids:
            page_id = next_id("p", page_ids)
        page_ids.add(page_id)
        name = raw.get("name")
        page = Page(page_id, check_name(name) if isinstance(name, str) and name.strip() else "")
        pieces = raw.get("pieces") or []
        if not isinstance(pieces, list) or len(pieces) > MAX_PLACED:
            raise StreamlitError(f"A page holds at most {MAX_PLACED} pieces.")
        for item in pieces:
            cell = item.get("cell") if isinstance(item, dict) else None
            if isinstance(cell, bool) or not isinstance(cell, int) or cell < 1:
                raise StreamlitError("A placed piece names its cell by the cell's own number.")
            placed_id = item.get("id")
            if not isinstance(placed_id, str) or not _ID.match(placed_id) or placed_id in placed_ids:
                placed_id = next_id("s", placed_ids)
            placed_ids.add(placed_id)
            page.pieces.append(
                Placed(placed_id, cell, check_width(item.get("w", DEFAULT_WIDTH)), check_rows(item.get("h")))
            )
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


def rows(pieces: Sequence[Placed]) -> list[list[Placed]]:
    """The pieces as the board's rows: each row takes pieces, in order, while their widths fit in
    12 columns."""
    out: list[list[Placed]] = []
    used = COLUMNS
    for piece in pieces:
        if used + piece.w > COLUMNS:
            out.append([])
            used = 0
        out[-1].append(piece)
        used += piece.w
    return out


# ----- a script's pages: a block of comments, one page a line -----


def pages_block(pages: Sequence[Page]) -> str:
    """A script's pages as its `# %% [streamlit-pages]` block: comments only, so the file still runs.
    Empty when there are no pages."""
    if not pages:
        return ""
    lines = [PAGES_MARK, _PAGES_NOTE]
    lines += ["# " + json.dumps(page.to_json(), ensure_ascii=False) for page in pages]
    return "\n".join(lines) + "\n"


def _block_span(lines: Sequence[str]) -> tuple[int, int] | None:
    """The block's first line and the line after its last (0-based), when the script has one."""
    start = next((i for i, line in enumerate(lines) if _PAGES_LINE.match(line)), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and lines[end].startswith("#") and not _ANY_MARKER.match(lines[end]):
        end += 1
    return start, end


def script_pages(text: str) -> list[Page]:
    """The pages a script's block holds (none: no block). A line that is not a page is passed over."""
    lines = text.split("\n")
    span = _block_span(lines)
    if span is None:
        return []
    found: list[Any] = []
    for line in lines[span[0] + 1 : span[1]]:
        try:
            page = json.loads(line[1:].strip())
        except ValueError:
            continue
        if isinstance(page, dict):
            found.append(page)
    return read_pages(found[:MAX_PAGES])


def with_script_pages(text: str, pages: Sequence[Page]) -> str:
    """The script with its pages block as it should be: replaced where it is, added at the end,
    or taken away when there are no pages. Nothing else in the file is touched."""
    lines = text.split("\n")
    span = _block_span(lines)
    block = pages_block(pages).rstrip("\n").split("\n") if pages else []
    if span is not None:
        lines[span[0] : span[1]] = block
        return "\n".join(lines)
    if not block:
        return text
    kept = text if text.endswith("\n") or not text else text + "\n"
    return kept + "\n".join(block) + "\n"


def script_pieces(text: str) -> list[tuple[int | None, str]]:
    """A script's Streamlit cells as (the cell's number, its code), in file order."""
    return [(cell.number, cell.source) for cell in table_cells.parse_script(text).cells if cell.streamlit]


# ===== the order pieces run in =====


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
    """A piece as a page takes it."""

    cell: int
    name: str
    code: str


@dataclass(frozen=True)
class PageCode:
    code: str
    tables: tuple[str, ...]  # the tables it reads, as Python variables
    order: tuple[str, ...]  # the placed pieces' ids in the order they run
    problems: tuple[str, ...]  # what the page says instead of running a piece


def _listed(names: Sequence[str]) -> str:
    shown = list(names)
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def preamble(tables: Sequence[str], data: str) -> list[str]:
    """What a page starts with: Streamlit and pandas, and each table the page names read from its
    Parquet file (read again only when the file has changed). `data` is the Python expression of the
    data folder."""
    lines = ["import pandas as pd", "import streamlit as st"]
    if not tables:
        return lines
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


def page_code(
    title: str,
    placed: Sequence[Placed],
    pieces: Mapping[int, PieceCode],
    tables: Iterable[str],
    data: str = 'Path(__file__).resolve().parent / "data"',
    guard: bool = True,
    notes: Mapping[str, str] | None = None,
    elsewhere: Mapping[str, int] | None = None,
) -> PageCode:
    """A page as one Streamlit page.

    1. Its layout is drawn first, as empty slots: a row of `st.columns` for each row of the board, a
       container in each column.
    2. The pieces run in the order their names need (`run_order`); a cycle is an error on the page.
    3. Each piece fills its own slot (`with slot:`), so a filter can sit anywhere on the page.
    4. Each piece's widgets get keys of their own.

    `tables`: the open tables' names as Python variables; the page reads the ones its code names.
    `guard`: a piece that fails shows its error in its own slot and the others still run (the live
    page); without it the code is the plain page (the export). `notes`: a line of words above a
    placed piece (a piece's preview says where its inputs come from). `elsewhere`: names made by a
    piece that is not on this page, and that piece's cell.
    """
    known = [p for p in placed if p.cell in pieces]
    found = {p.id: facts(pieces[p.cell].code) for p in known}
    ordered = run_order([(p.id, found[p.id]) for p in known])
    by_id = {p.id: p for p in placed}
    named = list(tables)
    used: list[str] = []
    for p in known:
        used += [t for t in tables_named(pieces[p.cell].code, named) if t not in used]
    problems: list[str] = []
    out: list[str] = [f"# {title}", *preamble(used, data), ""]

    out.append("# The layout: empty slots, drawn before any piece runs.")
    for number, row in enumerate(rows(placed), start=1):
        height = {p.id: "" if p.h is None else f"height={p.h * ROW_HEIGHT}" for p in row}
        if len(row) == 1 and row[0].w == COLUMNS:
            out.append(f"_slot_{row[0].id} = st.container({height[row[0].id]})")
            continue
        widths = [p.w for p in row]
        spare = COLUMNS - sum(widths)
        out.append(f"_row_{number} = st.columns({widths + ([spare] if spare > 0 else [])})")
        for index, p in enumerate(row):
            out.append(f"_slot_{p.id} = _row_{number}[{index}].container({height[p.id]})")
    out.append("")

    def say(piece_id: str, words: str) -> None:
        problems.append(words)
        out.extend([f"with _slot_{piece_id}:", f"    st.error({words!r})", ""])

    for p in placed:
        if p.cell not in pieces:
            say(p.id, f"The piece from cell {p.cell} is gone: its cell was deleted. Take it off the page.")
    if ordered.cycle:
        names = _listed([pieces[by_id[i].cell].name for i in ordered.cycle])
        loop = sorted({name for key, name, source in ordered.links if key in ordered.cycle})
        for piece_id in ordered.cycle:
            say(
                piece_id,
                f"{names} need each other's names ({_listed(loop)}): "
                "no order runs them. One of them must not read what the other makes.",
            )
    for piece_id in ordered.order:
        p = by_id[piece_id]
        piece = pieces[p.cell]
        mine = found[piece_id]
        made = f": makes {_listed(mine.makes)}" if mine.makes else ""
        out.append(f"# {piece.name} (cell {piece.cell}){made}")
        if mine.problem:
            say(piece_id, f"{piece.name} (cell {piece.cell}) is not whole Python yet: {mine.problem}.")
            continue
        far = [
            name
            for name in mine.reads
            if elsewhere
            and name in elsewhere
            and not any(k == piece_id and n == name for k, n, _ in ordered.links)
        ]
        if far:
            cells = (
                _listed([f"{name} (the piece in cell {elsewhere[name]})" for name in far])
                if elsewhere
                else ""
            )
            say(piece_id, f"{piece.name} reads {cells}, which is not on this page: push that piece here too.")
            continue
        text = keyed(body(piece.code).rstrip("\n"), p.id)
        if notes and piece_id in notes:
            text = f"st.caption({notes[piece_id]!r})\n{text}"
        if not _runs_something(text):
            text = "pass"
        out.append(f"with _slot_{p.id}:")
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
    """Each piece's facts, by its cell, in the document's order."""
    return {cell: facts(codes[cell]) for cell in order if cell in codes}


def inputs_of(cell: int, found: Mapping[int, Facts], order: Sequence[int]) -> list[tuple[int, str]]:
    """The pieces a piece needs to show alone, as (cell, the name it gives): for each name it reads
    that another piece of the document makes, the nearest such piece above it (else the first below),
    and what those need in turn. In the document's order."""
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
    """A piece alone, live: the piece, and above it the pieces that make the names it reads (each
    with a line saying which cell it is), so its widgets and its links work in its own cell."""
    found = {c: facts(pieces[c].code) for c in order if c in pieces}
    inputs = inputs_of(cell, found, order)
    placed = [Placed(f"c{c}", c, COLUMNS) for c, _ in inputs] + [Placed(f"c{cell}", cell, COLUMNS)]
    notes = {f"c{c}": f"{name} comes from the piece in cell {c}" for c, name in inputs}
    return page_code(pieces[cell].name, placed, pieces, tables, notes=notes)


def elsewhere(page: Page, found: Mapping[int, Facts]) -> dict[str, int]:
    """The names made only by pieces that are not on this page, and the cell that makes each."""
    here = {p.cell for p in page.pieces}
    made_here = {name for cell in here if cell in found for name in found[cell].makes}
    out: dict[str, int] = {}
    for cell, mine in found.items():
        if cell in here:
            continue
        for name in mine.makes:
            if name not in made_here and name not in PROVIDED:
                out.setdefault(name, cell)
    return out


# ----- the live app: one entry that reads what there is to show -----

# The live app's entry never changes: it reads the manifest each time it runs, so a page changed in
# the designer shows without a restart.
ENTRY: str = '''\
"""A notebook's Streamlit app, as SwissArmyGrid's Workbench shows it live (made by the app)."""
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
    # The app in its own window: its designed pages, listed at the side.
    if len(_designed) > 1:
        with st.sidebar:
            for _page in _designed:
                st.page_link(_page)
_current.run()
'''

HOME: str = (
    "import streamlit as st\n\n"
    'st.title("No pages yet")\n'
    'st.write("Push a piece to a page in the Workbench, and the page shows here.")\n'
)


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


# ===== export: the designed pages as a folder that runs without this app =====


def requirements(codes: Iterable[str]) -> list[str]:
    """What the exported app needs: Streamlit, pandas and pyarrow, and what its pieces import (found
    with Python's parser; the standard library and this app left out)."""
    needed = list(REQUIREMENTS)
    have = {"streamlit", "pandas", "pyarrow"}
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
{title}: a Streamlit app, made in SwissArmyGrid's page designer.

Run it:

    pip install -r requirements.txt
    streamlit run app.py

app.py          the app: its pages
app_pages/      one module for each page, laid out as it was designed
data/           the tables the pages read, as Parquet
"""


def export(
    title: str, pages: Sequence[Page], pieces: Mapping[int, PieceCode], tables: Iterable[str]
) -> Export:
    """The designed pages as a runnable folder: app.py (st.navigation over the pages), one module a
    page, requirements.txt and README.txt. The tables it names go into data/ (the caller writes them)."""
    if not pages:
        raise StreamlitError("There is no page to export yet: push a piece to a page first.")
    named = list(tables)
    files: dict[str, str] = {}
    used: list[str] = []
    problems: list[str] = []
    codes: list[str] = []
    modules: list[tuple[str, str]] = []
    found = {cell: facts(piece.code) for cell, piece in pieces.items()}
    for page in pages:
        module = slug(page.name, [m for m, _ in modules])
        made = page_code(
            page.name,
            page.pieces,
            pieces,
            named,
            data='Path(__file__).resolve().parent.parent / "data"',
            guard=False,
            elsewhere=elsewhere(page, found),
        )
        files[f"app_pages/{module}.py"] = made.code
        modules.append((module, page.name))
        used += [t for t in made.tables if t not in used]
        problems += [f"{page.name}: {p}" for p in made.problems]
        codes += [pieces[p.cell].code for p in page.pieces if p.cell in pieces]
    lines = [
        f'"""{title}: a Streamlit app, made in SwissArmyGrid\'s page designer. Run: streamlit run app.py"""',
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


# ===== heights =====


def check_pane(height: Any) -> int | None:
    """A piece's pane in its cell, in pixels (None: the usual height)."""
    return check_height(height)
