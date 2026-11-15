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
  scripts   the cell in a .py file: `# %% [7] [html] height=320`, then the HTML as one Python string
            that does nothing when the file runs
  frame     the Content-Security-Policy of the frame a design is drawn in

In a notebook file the cell is a code cell that starts with `%%html` (IPython's own cell magic, so
plain Jupyter draws it when run); domain/notebooks.py reads and writes it.
"""

from __future__ import annotations

import ast
import hashlib
import html as markup
import json
import math
import re
from collections.abc import Mapping, Sequence
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
        "rows": total_rows,
        "columns": every,
        "size": size,
    }


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
