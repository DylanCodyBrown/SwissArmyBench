"""HTML cells (docs/ideas.md, 2026-11-14): a cell that holds HTML and shows it as a design.

Clicked into, the cell shows its HTML; left, it shows the design, drawn in a walled-off frame. Plain
HTML draws by itself. `{{ name }}` in the HTML is filled from the cell's kernel when the cell runs.
Pure rules, no I/O, standard library only (the kernel's side, client/html_cells.py, uses them too):

  names     the `{{ name }}` names in a cell's HTML
  values    a Python value as what goes into the design: text, a table, a picture, or "not found"
  fill      the HTML with its names filled. Where a name stands decides what goes in, so data can
            never become markup or script:
              among the words          text with its markup characters escaped; a table as an HTML
                                       table; a picture as an image
              inside a <script>        a JavaScript literal (a number, a quoted text, a list of rows)
              inside a tag or <style>  plain words and numbers only; anything else is left out
              inside a comment         nothing: it stays as written
  markdown  a Markdown cell's `{{ name }}` filled from the same values (docs/ideas.md, text cells on
            the canvas, 2026-11-15): a value is always text, its Markdown and markup characters
            escaped; inside code (a `span` or a fenced block) plain words and numbers only
  objects   a Python value as its record, told by its shape: a table, a figure or picture, a value
  pages     a Markdown or HTML block on a Streamlit page fills its names by these same rules
  scripts   the cell in a .py file: `# %% [7] [html] height=320`, then the HTML as one Python string
            that does nothing when the file runs
  frame     the Content-Security-Policy of the frame a design is drawn in

In a notebook file the cell is a code cell that starts with `%%html` (IPython's own cell magic, so
plain Jupyter draws it when run); domain/notebooks.py reads and writes it.

This module imports nothing of Swiss Army Bench: a Streamlit page with a Markdown or HTML block that
names a value carries a copy of it (`sab_text.py`), so the page fills its names without this app.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import html as markup
import io
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# A name to fill: `{{ total }}`. A Python variable's name, nothing else (no expression runs).
NAME: re.Pattern[str] = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")
MAX_NAMES: int = 200
# A table among the words is drawn up to this many rows and columns ("first 50 of 1,204 rows").
TABLE_ROWS: int = 50
TABLE_COLUMNS: int = 30
# A table inside a <script> is a list of rows, up to this many (a chart's data).
DATA_ROWS: int = 1_000
TEXT_CHARS: int = 10_000
CELL_CHARS: int = 200
PICTURE_BYTES: int = 3_000_000
# The design's pane, in pixels (the height saved with the cell).
HEIGHT_MIN: int = 60
HEIGHT_MAX: int = 2_000

# The frame a design is drawn in loads nothing over the network: only what is inside the cell.
FRAME_POLICY: str = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; media-src data:; form-action 'none'; base-uri 'none'"
)


def names(text: str) -> list[str]:
    """The names a cell's HTML asks for, each once, in the order they first appear."""
    return list(dict.fromkeys(NAME.findall(text)))[:MAX_NAMES]


def check_height(height: Any) -> int | None:
    """A saved height as the pane takes it (None: the design's own height)."""
    if isinstance(height, bool) or not isinstance(height, int | float) or not math.isfinite(height):
        return None
    return max(HEIGHT_MIN, min(HEIGHT_MAX, round(height)))


# ===== values: what goes into the design =====
#
# A value is a plain record: {"kind": "text" | "table" | "picture" | "missing", "text": words for a tag
# or a title, "html": what is drawn among the words, "json": a JavaScript literal for a <script>}.


def escape(text: str) -> str:
    """Text as HTML shows it: `&`, `<`, `>` and both quotes escaped."""
    return markup.escape(text, quote=True)


def _literal(value: Any) -> str:
    """A JavaScript literal that cannot end a <script> or start markup, wherever it lands."""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for mark, safe in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        text = text.replace(mark, safe)
    return text


def _plain(value: Any) -> Any:
    """A value as JSON holds it: numbers, texts, true, false and null as they are; the rest as text."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def text_value(value: Any) -> dict[str, Any]:
    """A single value (a number, a text, a date...): shown as its text, escaped."""
    text = _cut("" if value is None else str(value), TEXT_CHARS)
    plain = _plain(value)
    return {
        "kind": "text",
        "text": text,
        "html": escape(text),
        "json": _literal(_cut(plain, TEXT_CHARS) if isinstance(plain, str) else plain),
    }


def missing_value(name: str) -> dict[str, Any]:
    """A name the kernel does not hold: a plain marker in the design, never an error."""
    return {"kind": "missing", "text": "", "html": _marker(f"{{{{ {name} }}}} not found"), "json": "null"}


def _marker(words: str) -> str:
    return (
        '<span class="sab-marker" style="background:#fff3bf;color:#4a3800;padding:0 4px;'
        f'border-radius:3px;font-weight:normal">{escape(words)}</span>'
    )


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return _cut(str(value), CELL_CHARS)


def table_value(
    columns: Sequence[Any], rows: Sequence[Sequence[Any]], total_rows: int, total_columns: int | None = None
) -> dict[str, Any]:
    """A table: among the words, its first TABLE_ROWS rows and TABLE_COLUMNS columns as an HTML table
    that says what it leaves out ("first 50 of 1,204 rows"); in a <script>, its first DATA_ROWS rows as
    a list of {column: value}. `rows` holds the table's first rows (as many as were read)."""
    heads = [str(c) for c in columns]
    every = len(heads) if total_columns is None else max(total_columns, len(heads))
    shown_columns = heads[:TABLE_COLUMNS]
    shown = [list(row)[: len(shown_columns)] for row in rows[:TABLE_ROWS]]
    parts: list[str] = []
    if total_rows > len(shown):
        parts.append(f"first {len(shown):,} of {_count(total_rows, 'row')}")
    if every > len(shown_columns):
        parts.append(f"first {len(shown_columns):,} of {_count(every, 'column')}")
    caption = f"<caption>{escape(' · '.join(parts))}</caption>" if parts else ""
    head = "".join(f"<th>{escape(h)}</th>" for h in shown_columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(_cell(value))}</td>" for value in row) + "</tr>" for row in shown
    )
    data = [{h: _plain(v) for h, v in zip(heads, row, strict=False)} for row in rows[:DATA_ROWS]]
    size = f"{_count(total_rows, 'row')}, {_count(every, 'column')}"
    return {
        "kind": "table",
        "text": "",
        "html": (
            f'<table class="sab-table">{caption}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
        ),
        "json": _literal(data),
        "markdown": _markdown_table(shown_columns, shown, parts),
        "rows": total_rows,
        "columns": every,
        "size": size,
    }


def _markdown_table(heads: Sequence[str], rows: Sequence[Sequence[Any]], parts: Sequence[str]) -> str:
    """A table as Markdown: a pipe table, each cell escaped text, and under it what it leaves out."""
    if not heads:
        return markdown_text("(a table with no columns)")
    lines = [
        "| " + " | ".join(markdown_text(h) or " " for h in heads) + " |",
        "| " + " | ".join("---" for _ in heads) + " |",
    ]
    lines += ["| " + " | ".join(markdown_text(_cell(v)) or " " for v in row) + " |" for row in rows]
    if parts:
        lines += ["", "*" + markdown_text(" · ".join(parts)) + "*"]
    return "\n".join(lines)


def picture_value(png_base64: str, name: str) -> dict[str, Any]:
    """A picture (a figure, an image) as PNG bytes in base64: drawn from a data address."""
    if not re.fullmatch(r"[A-Za-z0-9+/=\s]*", png_base64):
        return text_value("(a picture that could not be read)")
    address = "data:image/png;base64," + re.sub(r"\s", "", png_base64)
    return {
        "kind": "picture",
        "text": "",
        "html": f'<img class="sab-picture" alt="{escape(name)}" src="{address}" style="max-width:100%">',
        "json": _literal(address),
    }


def digest(value: Mapping[str, Any]) -> str:
    """A short mark of what a value draws: the same mark, the same design."""
    drawn = json.dumps([value.get("kind"), value.get("text"), value.get("html"), value.get("json")])
    return hashlib.sha256(drawn.encode("utf-8", "replace")).hexdigest()[:16]


# ===== fill: the HTML with its names filled =====

# Elements whose content the browser reads as text, not markup, up to their own end tag.
_RAW: dict[str, str] = {
    "script": "script",
    "style": "style",
    "textarea": "raw",
    "title": "raw",
    "xmp": "raw",
    "iframe": "raw",
    "noembed": "raw",
    "noframes": "raw",
    "noscript": "raw",
    "plaintext": "raw",
}
_TAG = re.compile(r"</?([A-Za-z][^\s/>]*)")
_COMMENT_END = re.compile(r"--!?>")
_SCRIPT_MARK = re.compile(r"<!--|-->|</?script(?=[\s/>])", re.IGNORECASE)
_ENDS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"</{name}(?=[\s/>])", re.IGNORECASE) for name in _RAW if name != "plaintext"
}
# What may go inside a tag or a <style>: plain words and numbers (a width, a colour, a class).
_SAFE_IN_TAG = re.compile(r"[A-Za-z0-9_ .,%#+-]{0,200}")


def _script_end(text: str, start: int) -> int:
    """Where the browser ends a <script> whose code starts at `start`: HTML's own rule, which passes
    over a `</script>` between `<!--` + `<script` and `-->`."""
    state = "code"  # code, hidden (after <!--), nested (after <!-- and <script)
    at = start
    while True:
        found = _SCRIPT_MARK.search(text, at)
        if found is None:
            return len(text)
        mark = found.group(0).lower()
        at = found.end()
        if mark == "<!--":
            if state == "code":
                state = "hidden"
                at = found.end() - 2  # `<!-->` ends it again at once
        elif mark == "-->":
            state = "code"
        elif mark == "<script":
            if state == "hidden":
                state = "nested"
        elif state == "nested":
            state = "hidden"
        else:
            return found.start()


def _regions(text: str) -> list[tuple[int, str]]:
    """Where each part of the HTML starts and what it is, as the browser reads it: text (among the
    words), tag, comment, script, style, or raw (a <textarea>, a <title>: text the browser shows or
    keeps as it is). Where the two could differ, this errs to the stricter part."""
    regions: list[tuple[int, str]] = [(0, "text")]
    at, size = 0, len(text)
    while at < size:
        start = text.find("<", at)
        if start < 0:
            break
        if text.startswith("<!--", start):
            end = _COMMENT_END.search(text, start + 2)
            stop = size if end is None else end.end()
            regions += [(start, "comment"), (stop, "text")]
            at = stop
            continue
        if text.startswith("<![CDATA[", start):
            end_at = text.find("]]>", start)
            stop = size if end_at < 0 else end_at + 3
            regions += [(start, "comment"), (stop, "text")]
            at = stop
            continue
        found = _TAG.match(text, start)
        if found is None:
            at = start + 1
            continue
        index, quote = found.end(), ""
        while index < size:
            char = text[index]
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == ">":
                break
            index += 1
        stop = min(index + 1, size)
        regions.append((start, "tag"))
        name = found.group(1).lower()
        kind = _RAW.get(name) if not text.startswith("</", start) else None
        if kind is None:
            regions.append((stop, "text"))
            at = stop
            continue
        if name == "plaintext":
            close = size
        elif name == "script":
            close = _script_end(text, stop)
        else:
            ended = _ENDS[name].search(text, stop)
            close = size if ended is None else ended.start()
        regions += [(stop, kind), (close, "text")]
        at = close
    return regions


@dataclass(frozen=True)
class Filled:
    html: str
    names: tuple[str, ...]  # every name the HTML asks for
    missing: tuple[str, ...]  # asked for, and the kernel does not hold it
    waiting: tuple[str, ...]  # asked for, and not run yet
    notes: tuple[str, ...]  # what was left out, and why

    def to_json(self) -> dict[str, Any]:
        return {
            "html": self.html,
            "names": list(self.names),
            "missing": list(self.missing),
            "waiting": list(self.waiting),
            "notes": list(self.notes),
        }


def fill(text: str, values: Mapping[str, Mapping[str, Any]]) -> Filled:
    """The HTML with each `{{ name }}` filled from `values` (name -> a value record). A name with no
    value yet (the cell has not run) shows as written, marked; one the kernel does not hold shows
    "{{ name }} not found". Nothing here raises: a design never breaks on its data."""
    regions = _regions(text)
    out: list[str] = []
    notes: list[str] = []
    missing: list[str] = []
    waiting: list[str] = []
    at = 0
    part = 0
    for found in NAME.finditer(text):
        while part + 1 < len(regions) and regions[part + 1][0] <= found.start():
            part += 1
        where = regions[part][1]
        name = found.group(1)
        value = values.get(name)
        kind = str(value.get("kind")) if value is not None else "waiting"
        if kind == "missing" and name not in missing:
            missing.append(name)
        if kind == "waiting" and name not in waiting:
            waiting.append(name)
        out.append(text[at : found.start()])
        at = found.end()
        if where == "comment":
            out.append(found.group(0))
        elif where == "script":
            out.append(str(value.get("json", "null")) if value is not None else "null")
        elif where == "text":
            out.append(_marker(f"{{{{ {name} }}}}") if value is None else str(value.get("html", "")))
        elif value is None or kind == "missing":
            out.append("")
        elif where == "raw":
            words = str(value.get("text", "")) if kind == "text" else f"({kind}: {name})"
            out.append(escape(words))
        else:  # inside a tag, or a <style>
            words = str(value.get("text", ""))
            if kind == "text" and _SAFE_IN_TAG.fullmatch(words):
                out.append(words)
            else:
                place = "a <style>" if where == "style" else "a tag"
                why = (
                    "only plain words and numbers go there" if kind == "text" else f"a {kind} cannot go there"
                )
                note = f"{{{{ {name} }}}} is left out of {place}: {why}."
                if note not in notes:
                    notes.append(note)
    out.append(text[at:])
    return Filled("".join(out), tuple(names(text)), tuple(missing), tuple(waiting), tuple(notes))


def has_script(text: str) -> bool:
    """The HTML holds a <script> the browser would run (one inside a comment does not count): on a
    Streamlit page its block is `st.html(..., unsafe_allow_javascript=True)`, else Streamlit drops it."""
    return any(kind == "script" for _, kind in _regions(text))


# ===== markdown: a Markdown cell's names, filled =====
#
# The same values as an HTML cell's, written for Markdown: a value is always text. Its Markdown marks
# (asterisks, underscores, brackets, backticks...) are escaped with a backslash and its markup
# characters as HTML's own references, so it can neither format nor link nor become markup, in the
# Workbench, in Jupyter or on a Streamlit page. A value is one line (a line break would end a heading
# or a table's row). Inside code, where escapes show as they are, only plain words and numbers go.

_MARKDOWN_MARKS: frozenset[str] = frozenset("\\`*_{}[]()#+-.!|~:$=^")
_REFERENCES: dict[str, str] = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;"}
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_TICKS = re.compile(r"`+")


def markdown_text(text: str) -> str:
    """Text as Markdown shows it, whatever it holds: on one line, every mark escaped."""
    flat = re.sub(r"\s*[\r\n]+\s*", " ", text)
    return "".join(_REFERENCES.get(c) or (f"\\{c}" if c in _MARKDOWN_MARKS else c) for c in flat)


def _markdown_code(text: str) -> list[tuple[int, int]]:
    """Where Markdown holds code, as (start, end): fenced blocks, then the code spans outside them
    (a run of backticks up to the next run of the same length)."""
    spans: list[tuple[int, int]] = []
    at, fence, opened = 0, "", 0
    for line in text.split("\n"):
        found = _FENCE.match(line)
        if fence:
            if found and found.group(1)[0] == fence[0] and len(found.group(1)) >= len(fence):
                spans.append((opened, at + len(line)))
                fence = ""
        elif found:
            fence, opened = found.group(1), at
        at += len(line) + 1
    if fence:
        spans.append((opened, len(text)))
    blocks = list(spans)
    index = 0
    while True:
        found = _TICKS.search(text, index)
        if found is None:
            break
        index = found.end()
        if any(a <= found.start() < b for a, b in blocks):
            continue
        close = re.compile(rf"(?<!`){found.group(0)}(?!`)").search(text, found.end())
        if close is None:
            continue
        spans.append((found.start(), close.end()))
        index = close.end()
    return spans


def _alone_on_its_line(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return (
        not text[line_start:start].strip() and not text[end : len(text) if line_end < 0 else line_end].strip()
    )


def fill_markdown(text: str, values: Mapping[str, Mapping[str, Any]]) -> Filled:
    """A Markdown cell's text with each `{{ name }}` filled from `values` (the records an HTML cell's
    run gives), as `Filled` (its `html` holds the Markdown). Among the words a value is escaped text; a
    table alone on its line is a pipe table, elsewhere its size; a name with no value yet shows as
    written; one the kernel does not hold says "not found". In code only plain words and numbers go."""
    code = _markdown_code(text)
    out: list[str] = []
    notes: list[str] = []
    missing: list[str] = []
    waiting: list[str] = []
    at = 0
    for found in NAME.finditer(text):
        name = found.group(1)
        value = values.get(name)
        kind = str(value.get("kind")) if value is not None else "waiting"
        if kind == "missing" and name not in missing:
            missing.append(name)
        if kind == "waiting" and name not in waiting:
            waiting.append(name)
        out.append(text[at : found.start()])
        at = found.end()
        if any(a <= found.start() < b for a, b in code):
            words = str(value.get("text", "")) if value is not None else ""
            if value is None:
                out.append(found.group(0))
            elif kind == "text" and _SAFE_IN_TAG.fullmatch(words):
                out.append(words)
            elif kind != "missing":
                note = f"{{{{ {name} }}}} is left out of code: only plain words and numbers go there."
                if note not in notes:
                    notes.append(note)
        elif value is None:
            out.append(markdown_text(found.group(0)))
        elif kind == "missing":
            out.append("*" + markdown_text(f"{{{{ {name} }}}} not found") + "*")
        elif kind == "table":
            table = value.get("markdown")
            if isinstance(table, str) and _alone_on_its_line(text, found.start(), found.end()):
                out.append(f"\n{table}\n")
            else:
                out.append(markdown_text(f"({name}: {value.get('size') or 'a table'})"))
        elif kind == "picture":
            out.append(markdown_text(f"({name}: a picture; an HTML cell shows it)"))
        else:
            out.append(markdown_text(str(value.get("text", ""))))
    out.append(text[at:])
    return Filled("".join(out), tuple(names(text)), tuple(missing), tuple(waiting), tuple(notes))


# ===== objects: a Python value as its record, told by its shape =====
#
# pandas, Polars, Arrow, DuckDB and matplotlib are never imported: a value is read by its type's
# module and name, so this runs in any Python (the kernel's, a Streamlit page's).


def _module(value: Any) -> str:
    return str(getattr(type(value), "__module__", "") or "").split(".")[0]


def table_of(value: Any) -> dict[str, Any] | None:
    """A table's first rows, by its kind (None: not a table)."""
    module, kind = _module(value), type(value).__name__
    need = DATA_ROWS
    if module == "pandas" and kind == "DataFrame":
        head = value.head(need)
        columns = [str(c) for c in head.columns]
        rows = [list(row) for row in head.itertuples(index=False, name=None)]
        return table_value(columns, rows, len(value), len(columns))
    if module == "polars" and kind == "DataFrame":
        head = value.head(need)
        rows = [list(row) for row in head.rows()]
        return table_value(list(head.columns), rows, value.height, value.width)
    if module == "pyarrow" and kind in ("Table", "RecordBatch"):
        columns = list(value.schema.names)
        head = value.slice(0, need).to_pylist()
        rows = [[row.get(c) for c in columns] for row in head]
        return table_value(columns, rows, value.num_rows, len(columns))
    if module in ("duckdb", "_duckdb") and kind == "DuckDBPyRelation":
        columns = list(value.columns)
        rows = [list(row) for row in value.limit(need).fetchall()]
        total = len(rows)
        if total >= need:
            total = int(value.count("*").fetchall()[0][0])
        return table_value(columns, rows, total, len(columns))
    return None


def picture_of(value: Any, name: str) -> dict[str, Any] | None:
    """A figure or an image as a PNG (None: not a picture, or too large to put in a design)."""
    data: Any = None
    if _module(value) == "matplotlib" and hasattr(value, "savefig"):
        target = io.BytesIO()
        value.savefig(target, format="png", bbox_inches="tight")
        data = target.getvalue()
    elif hasattr(value, "_repr_png_"):
        data = value._repr_png_()
        if isinstance(data, tuple):  # (bytes, metadata)
            data = data[0]
        if isinstance(data, str):  # already base64
            data = base64.b64decode(data)
    if not isinstance(data, bytes | bytearray) or not data:
        return None
    if len(data) > PICTURE_BYTES:
        return text_value(f"({name}: a picture too large for a design)")
    return picture_value(base64.b64encode(bytes(data)).decode("ascii"), name)


def record_of(value: Any, name: str) -> dict[str, Any]:
    """What `{{ name }}` draws for a value this Python holds. A value that cannot be read says so in
    plain words, never an error."""
    try:
        return table_of(value) or picture_of(value, name) or text_value(value)
    except Exception as error:
        return text_value(f"({name} could not be shown: {type(error).__name__})")


# ===== pages: a Markdown or HTML block on a Streamlit page =====
#
#     import sab_text as _sab_text
#     st.markdown(_sab_text.page_markdown(r"""Total for {{ region }}""", {"region": lambda: region}))
#
# Each name is read where the page stands when the block runs (the block that makes it ran first: the
# run order counts the names); a name no block made says "not found".

Getters = Mapping[str, Callable[[], Any]]


def page_values(getters: Getters) -> dict[str, dict[str, Any]]:
    """Each name's record, read through its getter (a NameError: the page does not hold it)."""
    found: dict[str, dict[str, Any]] = {}
    for name, get in list(getters.items())[:MAX_NAMES]:
        try:
            held = get()
        except NameError:
            found[name] = missing_value(name)
            continue
        found[name] = record_of(held, name)
    return found


def page_markdown(text: str, getters: Getters) -> str:
    """A Markdown block's text with its names filled, for `st.markdown`."""
    return fill_markdown(text, page_values(getters)).html


def page_html(text: str, getters: Getters) -> str:
    """An HTML block's HTML with its names filled, for `st.html`."""
    return fill(text, page_values(getters)).html


# ===== scripts: the cell in a .py file =====
#
#     # %% [7] [html] height=320
#     r"""
#     <h1>Orders</h1>
#     <p>{{ total }} orders</p>
#     """
#
# The HTML is one Python string, a statement that does nothing: the file still runs as plain Python.

_OWN_LINE = re.compile(r"^[ \t]*#")


def script_body(text: str) -> str:
    """An HTML cell's lines in a script: the HTML as one string on lines of its own, written as it
    is (a raw string) whenever Python can hold it that way."""
    inner = text[:-1] if text.endswith("\n") else text
    for quotes in ('"""', "'''"):
        if quotes not in inner and "\r" not in inner:
            return f"r{quotes}\n{inner}\n{quotes}\n"
    escaped = inner.replace("\\", "\\\\").replace('"""', '\\"\\"\\"').replace("\r", "\\r")
    return f'"""\n{escaped}\n"""\n'


def read_script_body(body: str) -> tuple[str | None, str | None]:
    """The HTML an HTML cell's lines hold, as (html, None), or (None, what is wrong). The first
    statement is the HTML: a string by itself, or a string given a name (`card = \"\"\"...\"\"\"`)."""
    held, problem, _ = script_string(body)
    return held, problem


def script_string(body: str) -> tuple[str | None, str | None, int]:
    """`read_script_body`, and the last of the cell's lines the string takes (0: it has none): code
    after it in the same cell is the user's Python, and stays in view."""
    try:
        tree = ast.parse(body)
    except (SyntaxError, ValueError, RecursionError):
        return None, "This cell's HTML is not a whole Python string yet (check its quotes).", 0
    for node in tree.body:
        value = node.value if isinstance(node, ast.Expr | ast.Assign | ast.AnnAssign) else None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            held = value.value
            held = held[1:] if held.startswith("\n") else held
            return (held[:-1] if held.endswith("\n") else held), None, node.end_lineno or node.lineno
        break
    if not any(line.strip() and not _OWN_LINE.match(line) for line in body.split("\n")):
        return "", None, 0
    return None, 'An HTML cell holds its HTML as one string: r""" ... """ (not an f-string).', 0
