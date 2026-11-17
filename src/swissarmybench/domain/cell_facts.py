"""A Python cell's facts, as every feature reads them (Python's own parser; no Streamlit needed).

What the base needs of a cell that the Streamlit extension's canvas reads too (its domain/streamlit_cells.py
takes these from here):

  body       a cell's own code, without the app's uses line
  title      a cell's title (its first comment line, else its first line of code; "Cell N" when empty)
  facts      what a cell makes and reads, and the modules it imports
  WIDGETS    Streamlit's widget calls (a value the lineage says a widget gave)
  indented   code one level in, leaving the lines inside a multi-line text as they are
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from functools import lru_cache

from swissarmybench.domain import table_cells

_ANY_MARKER = re.compile(r"^# ?%%")
MAX_NAME: int = 80
# Streamlit's widgets: a call of one of these gives a value the page's user chose.
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


def body(code: str) -> str:
    """A cell's own code: without the app's uses line."""
    return table_cells.split_uses(code)[1]


def piece_name(code: str, number: int) -> str:
    """A cell's title: its first line when that is a comment (`# Region filter`), else its first line of
    code; "Cell N" for an empty one (N is the cell's own number)."""
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


def modules(tree: ast.AST) -> list[str]:
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
    return Facts(read.made, read.needs, tuple(modules(tree)))


def string_lines(code: str) -> set[int]:
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
    skip = string_lines(code)
    out = []
    for number, line in enumerate(code.split("\n"), start=1):
        out.append(line if number in skip or not line.strip() else by + line)
    return "\n".join(out)
