"""The Workbench's documents: notebooks (.ipynb, so Jupyter and VS Code open them too) and scripts (.py).
Pure rules: no I/O. Plans/workbench-and-connections.plan.md.

A notebook here is a list of cells, each code (Python), sql (run on a connection), dax (run on one
dataset of a Power BI workspace), html (a design: domain/html_cells.py) or markdown, with the outputs
a run gave (kept as nbformat's own output records).
In the file, a SQL cell is a code cell that starts with its `%%sql <connection>` line (any Jupyter with
Swiss Army Bench runs it as it is), marked so the Workbench opens it as a SQL cell again. A DAX cell (the
owner, 2026-11-15: "a new kind of cell, a DAX cell") is the same with `%%dax <connection>/<dataset>`:
`%%dax Finance/Sales model`. An HTML cell is a
code cell that starts with `%%html`, IPython's own cell magic, so plain Jupyter draws it when run; the
height of its pane is kept in the cell's metadata.

There is no Streamlit kind of cell (the Streamlit canvas, 2026-11-15): a Python cell that calls
Streamlit is shown live in its cell (domain/streamlit_use.py), and its pane's height is kept in its
metadata too. A notebook saved when there was such a kind (a code cell marked `"kind": "streamlit"`,
its first line the comment `# %% [streamlit]`) opens with that cell as a Python cell: the marker line
goes, the code and the height stay. Pages once kept in a notebook's metadata
(`swissarmybench.streamlit.pages`) are not read and not written: an app is a file of its own now
(domain/streamlit_cells.py).

A TypeScript or TSX cell (a kind an extension's kernel runs, OTHER_KERNEL: the Power Apps extension's data
notebook, 2026-11-17) is a code cell kept as it is, marked with its kind in its metadata; the Python
kernel never runs it, and plain Jupyter shows it as text in a code cell.

Any cell may have a name (the owner, 2026-11-15): a short label of one line, kept in the cell's
metadata (`swissarmybench.name`), so plain Jupyter keeps it. The number stays the cell's identity: a
name changes nothing that links to the cell.

Every cell has a number that never changes (docs/ideas.md, 2026-11-14): given when the cell is made,
never reused or shifted when cells move or go. It is kept in the cell's metadata, with the cell's part
in the Tables group (domain/table_cells.py): the group's heading, a table's heading, the user's cell
that makes a table, the imports the tables need, a table's read-only transformations.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.approvals import check_approval
from swissarmybench.domain.html_cells import check_height

APP_SUFFIX: str = ".stapp.json"  # a Streamlit app's file (domain/streamlit_cells.py)
MAX_CELLS: int = 2_000
MAX_CELL_CHARS: int = 1_000_000
MAX_OUTPUTS_PER_CELL: int = 200
KINDS: tuple[str, ...] = ("code", "sql", "dax", "html", "markdown", "typescript", "tsx")
# Kinds another kernel runs (an extension's, as the project's mode declares: `cell_routes`): the code cell
# keeps its text as it is, marked with its kind; the Python kernel runs none of it.
OTHER_KERNEL: tuple[str, ...] = ("typescript", "tsx")
SIZED: tuple[str, ...] = ("html", "code", "tsx")  # kinds whose pane's height is kept
# What an older file or window may still call a Python cell that draws with Streamlit.
_OLD_STREAMLIT: str = "streamlit"
_OLD_STREAMLIT_LINE = re.compile(r"^# ?%% \[streamlit\]\s*$")
MAX_NAME: int = 80  # a cell's name: one line
MAX_CONNECTION_CHARS: int = 200  # a DAX cell's is a connection, a slash and a dataset's name
ROLES: tuple[str, ...] = ("", "tables", "table", "maker", "imports", "transformations")
MAX_STEPS_CHARS: int = 200_000
# %%sag: the SQL cell's own magic before the rename to Swiss Army Bench, still read (renamed.py).
_SQL_LINE = re.compile(r"^%%(?:sql|sab|sag)\b(?!_)")
_DAX_LINE = re.compile(r"^%%dax\b")
_HTML_LINE = re.compile(r"^%%html\b")


class NotebookError(ValueError):
    """A notebook or script that cannot be read or saved as sent (the message says why)."""


@dataclass
class Cell:
    kind: str  # code, sql, dax, html, markdown, typescript or tsx (OTHER_KERNEL)
    # A SQL or DAX cell's query, without its %%sql or %%dax line; an HTML cell's HTML, without %%html.
    source: str
    # A SQL cell's connection (None: the %sql_connect one); a DAX cell's dataset: Finance/Sales model.
    connection: str | None = None
    outputs: list[dict[str, Any]] = field(default_factory=list)
    execution_count: int | None = None
    number: int | None = None  # the cell's own number: never changes, never reused
    role: str = ""  # its part in the Tables group (ROLES); "" for a cell of the user's own
    table: str | None = None  # the table a heading, a maker or a transformations cell belongs to
    grouped: bool = False  # it sits in the Tables group
    # A transformations cell's steps as the grid holds them, so the grid gets them back when the
    # table is opened again.
    steps: list[Any] | None = None
    # An HTML cell's pane, or a Python cell's that is shown live, in pixels (None: the usual height).
    height: int | None = None
    name: str | None = None  # the cell's own label (None: it has none); the number stays its identity
    # Its output as the user approved it (domain/approvals.py): a later run that differs says so.
    approved: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "connection": self.connection,
            "outputs": self.outputs,
            "execution_count": self.execution_count,
            "number": self.number,
            "role": self.role,
            "table": self.table,
            "grouped": self.grouped,
            "steps": self.steps,
            "height": self.height,
            "name": self.name,
            "approved": self.approved,
        }

    def marks(self) -> dict[str, Any]:
        """What the file keeps about the cell beside its text (the notebook's `swissarmybench` metadata)."""
        kept: dict[str, Any] = {}
        if self.kind in ("sql", "dax"):
            kept |= {"kind": self.kind, "connection": self.connection}
        if self.kind == "html" or self.kind in OTHER_KERNEL:
            kept["kind"] = self.kind
        if self.kind in SIZED and self.height is not None:
            kept["height"] = self.height
        if self.number is not None:
            kept["number"] = self.number
        if self.role:
            kept["role"] = self.role
        if self.table:
            kept["table"] = self.table
        if self.grouped:
            kept["grouped"] = True
        if self.steps is not None and self.role == "transformations":
            kept["steps"] = self.steps
        if self.name:
            kept["name"] = self.name
        if self.approved is not None and self.kind != "markdown":
            kept["approved"] = self.approved
        return kept


def check_name(value: Any) -> str | None:
    """A cell's name as sent: one line of at most MAX_NAME characters (None or "": no name)."""
    if value is None:
        return None
    if not isinstance(value, str) or "\n" in value or "\r" in value or len(value.strip()) > MAX_NAME:
        raise NotebookError(f"A cell's name is one line of at most {MAX_NAME} characters.")
    return value.strip() or None


def sql_line(connection: str | None) -> str:
    """The first line of a SQL cell's code: `%%sql Warehouse`, quoted when the name has a space."""
    if not connection:
        return "%%sql"
    return f"%%sql {shlex.quote(connection) if re.search(r'\s', connection) else connection}"


def dax_line(dataset: str | None) -> str:
    """The first line of a DAX cell's code: `%%dax Finance/Sales_model`, quoted when it has a space."""
    return "%%dax" + sql_line(dataset)[len("%%sql") :]


def code_of(cell: Cell) -> str:
    """What the kernel runs for the cell (markdown runs nothing)."""
    if cell.kind == "sql":
        return f"{sql_line(cell.connection)}\n{cell.source}"
    if cell.kind == "dax":
        return f"{dax_line(cell.connection)}\n{cell.source}"
    if cell.kind == "html":
        return f"%%html\n{cell.source}"
    return cell.source if cell.kind == "code" else ""  # markdown, and the kinds another kernel runs


def _text(value: Any) -> str:
    """nbformat keeps text as one string or a list of lines."""
    if isinstance(value, list):
        return "".join(str(v) for v in value)
    return value if isinstance(value, str) else ""


def _lines(text: str) -> list[str]:
    """Text as nbformat writes it: a list of lines, each keeping its newline."""
    return text.splitlines(keepends=True)


# The notebook's and each cell's own metadata key; SwissArmyGrid's, before the rename, is still read (an
# old notebook keeps its cell numbers, names and kinds) and written over with the new one on save.
OWN_KEY: str = "swissarmybench"
OLD_KEY: str = "swissarmygrid"


def _own(raw: dict[str, Any]) -> Any:
    """What the file keeps under this app's key in `raw`'s metadata: the new key, else the old one."""
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None
    return metadata[OWN_KEY] if OWN_KEY in metadata else metadata.get(OLD_KEY)


def _marked(cell: Cell, raw: dict[str, Any]) -> Cell:
    """A cell with what the file keeps about it: its number and its part in the Tables group."""
    marks = _own(raw)
    if not isinstance(marks, dict):
        return cell
    number = marks.get("number")
    if isinstance(number, int) and not isinstance(number, bool) and number > 0:
        cell.number = number
    if marks.get("role") in ROLES:
        cell.role = str(marks["role"])
    if isinstance(marks.get("table"), str):
        cell.table = marks["table"]
    cell.grouped = marks.get("grouped") is True
    if isinstance(marks.get("steps"), list) and cell.role == "transformations":
        cell.steps = marks["steps"]
    if cell.kind in SIZED:
        cell.height = check_height(marks.get("height"))
    try:
        cell.name = check_name(marks.get("name"))
    except NotebookError:  # a name another tool wrote too long: the cell opens without it
        cell.name = None
    try:
        cell.approved = check_approval(marks.get("approved")) if cell.kind != "markdown" else None
    except ValueError:  # an approval another tool spoilt: the cell opens without it
        cell.approved = None
    return cell


def number_cells(cells: list[Cell], next_number: int = 1) -> int:
    """Give each cell without a number (or with an earlier cell's) the next one; the next after that.
    A number is never reused: `next_number` is the file's own count of the numbers given so far."""
    seen: set[int] = set()
    highest = max([next_number - 1, *(c.number for c in cells if c.number is not None)])
    for cell in cells:
        if cell.number is None or cell.number in seen:
            highest += 1
            cell.number = highest
        seen.add(cell.number)
    return highest + 1


def read_notebook(text: str) -> list[Cell]:
    """The cells of an .ipynb file's text (nbformat 4), each with its number."""
    return read_document(text)[0]


def read_document(text: str) -> tuple[list[Cell], int]:
    """A notebook's cells, and the number its next new cell gets."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise NotebookError(f"This is not a notebook file: {error}.") from None
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        raise NotebookError("This is not a notebook file: it has no cells.")
    if int(data.get("nbformat", 4)) < 4:
        raise NotebookError(
            "This notebook is in an old format (before 4): open it in Jupyter and save it again."
        )
    cells: list[Cell] = []
    for raw in data["cells"][:MAX_CELLS]:
        if not isinstance(raw, dict):
            continue
        source = _text(raw.get("source"))
        kind = raw.get("cell_type")
        if kind == "markdown":
            cells.append(_marked(Cell("markdown", source), raw))
        elif kind == "code":
            first, _, rest = source.partition("\n")
            own = _own(raw)
            marked = own.get("kind") if isinstance(own, dict) else None
            dax = bool(_DAX_LINE.match(first)) or (marked == "dax" and not _SQL_LINE.match(first))
            if marked in OTHER_KERNEL:
                cell = Cell(str(marked), source)
            elif dax or _SQL_LINE.match(first) or marked == "sql":
                words = first.split(None, 1)
                try:
                    named = " ".join(shlex.split(words[1])) if len(words) > 1 else None
                except ValueError:
                    named = words[1] if len(words) > 1 else None
                # A `%%sql Finance/Sales model` cell saved before DAX cells: only a Power BI
                # workspace's dataset is named with a slash (no connection's name has one).
                dax = dax or "/" in (named or "").split(" -> ")[0]
                cell = Cell("dax" if dax else "sql", rest, named or None)
            elif _HTML_LINE.match(first):
                cell = Cell("html", rest)
            elif _OLD_STREAMLIT_LINE.match(first):
                cell = Cell("code", rest)  # once a Streamlit cell: plain Python under its marker
            else:
                cell = Cell("code", source)
            outputs = raw.get("outputs")
            cell.outputs = (
                [o for o in outputs if isinstance(o, dict)][:MAX_OUTPUTS_PER_CELL]
                if isinstance(outputs, list)
                else []
            )
            count = raw.get("execution_count")
            cell.execution_count = count if isinstance(count, int) else None
            cells.append(_marked(cell, raw))
        elif kind == "raw":
            cells.append(_marked(Cell("markdown", source), raw))
    kept = _own(data)
    counted = kept.get("next_cell") if isinstance(kept, dict) else None
    return cells, number_cells(cells, counted if isinstance(counted, int) and counted > 0 else 1)


def read_cells(sent: Any) -> list[Cell]:
    """The cells as the Workbench page sends them, checked."""
    if not isinstance(sent, list) or len(sent) > MAX_CELLS:
        raise NotebookError(f"Send the cells as a list (at most {MAX_CELLS:,}).")
    cells: list[Cell] = []
    for raw in sent:
        if isinstance(raw, dict) and raw.get("kind") == _OLD_STREAMLIT:
            raw = raw | {"kind": "code"}  # a window that still holds the old kind: plain Python
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            raise NotebookError(
                'Each cell is {"kind": "code", "sql", "dax", "html", "markdown", "typescript" or "tsx", '
                '"source": "..."}.'
            )
        source = raw.get("source", "")
        if not isinstance(source, str) or len(source) > MAX_CELL_CHARS:
            raise NotebookError("A cell's source is text of at most a million characters.")
        connection = raw.get("connection")
        if connection is not None and (
            not isinstance(connection, str) or "\n" in connection or len(connection) > MAX_CONNECTION_CHARS
        ):
            raise NotebookError(
                "A SQL cell's connection is a connection's name; a DAX cell's, a connection and its "
                "dataset (Finance/Sales model)."
            )
        outputs = raw.get("outputs") or []
        if not isinstance(outputs, list) or not all(isinstance(o, dict) for o in outputs):
            raise NotebookError("A cell's outputs are a list of output records.")
        count = raw.get("execution_count")
        number = raw.get("number")
        if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number < 1):
            raise NotebookError("A cell's number is a whole number from 1.")
        role = raw.get("role") or ""
        table = raw.get("table")
        if role not in ROLES or (table is not None and (not isinstance(table, str) or len(table) > 64)):
            raise NotebookError("A cell's role is one of the Tables group's, and its table a table's name.")
        steps = raw.get("steps")
        if steps is not None and (not isinstance(steps, list) or len(json.dumps(steps)) > MAX_STEPS_CHARS):
            raise NotebookError("A table cell's steps are a list of the grid's steps.")
        try:
            approved = check_approval(raw.get("approved")) if raw["kind"] != "markdown" else None
        except ValueError as error:
            raise NotebookError(str(error)) from None
        cells.append(
            Cell(
                str(raw["kind"]),
                source,
                connection or None,
                outputs[:MAX_OUTPUTS_PER_CELL] if raw["kind"] != "markdown" else [],
                count if isinstance(count, int) else None,
                number,
                role,
                table or None,
                raw.get("grouped") is True,
                steps,
                check_height(raw.get("height")) if raw["kind"] in SIZED else None,
                check_name(raw.get("name")),
                approved,
            )
        )
    return cells


def write_notebook(
    cells: list[Cell],
    python_version: str = "3",
    next_number: int | None = None,
    dictionary: dict[str, Any] | None = None,
) -> str:
    """The cells as an .ipynb file's text (nbformat 4.5). Each cell's number is in its metadata, and
    the notebook's keeps the next number to give, so a deleted cell's number is never given again."""
    following = number_cells(cells, next_number or 1)
    own: dict[str, Any] = {"next_cell": following}
    if dictionary:  # a project's data.ipynb: its data dictionary's descriptions (domain/dictionary.py)
        own["dictionary"] = dictionary
    out: list[dict[str, Any]] = []
    for i, cell in enumerate(cells):
        marks = cell.marks()
        metadata = {OWN_KEY: marks} if marks else {}
        base: dict[str, Any] = {"id": f"cell-{i + 1}", "metadata": metadata}
        if cell.kind == "markdown":
            out.append(base | {"cell_type": "markdown", "source": _lines(cell.source)})
            continue
        out.append(
            base
            | {
                "cell_type": "code",
                "source": _lines(cell.source if cell.kind in OTHER_KERNEL else code_of(cell)),
                "outputs": cell.outputs,
                "execution_count": cell.execution_count,
            }
        )
    notebook = {
        "cells": out,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": python_version},
            OWN_KEY: own,
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"


def kind_of(path: str) -> str:
    """ "notebook", "script" or "app" (a Streamlit app: sales.stapp.json), by the file's ending."""
    lowered = path.lower()
    if lowered.endswith(APP_SUFFIX):
        return "app"
    if lowered.endswith(".ipynb"):
        return "notebook"
    if lowered.endswith(".py"):
        return "script"
    raise NotebookError(
        f"The Workbench opens notebooks (.ipynb), Python scripts (.py) and Streamlit apps ({APP_SUFFIX})."
    )


def quote_path(path: str) -> str:
    """A path as IPython's %run reads it: quoted when it has spaces (Windows backslashes kept)."""
    if not re.search(r'[\s"\']', path):
        return path
    return '"' + path.replace('"', '\\"') + '"'


# Lines that carry on the statement above them, not start a new one.
_CARRY_ON = re.compile(r"^\s*(?:elif\b|else\b|except\b|finally\b|case\b|[)\]}])")


def _top_level(code: str) -> list[tuple[int, int]]:
    """Each top-level statement's first and last line (a decorator's line is its function's first)."""
    spans: list[tuple[int, int]] = []
    for node in ast.parse(code).body:
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno, *(d.lineno for d in decorators)])
        spans.append((start, node.end_lineno or node.lineno))
    return spans


def statement_at(code: str, line: int) -> tuple[int, int, int | None] | None:
    """Ctrl+Enter in a script (RStudio's run line, VS Code's smart send): the whole top-level statement
    the 1-based `line` is in, as (first line, last line, the next statement's first line or None).
    None: the line is blank or a comment (nothing runs; the page moves on). While the file as a whole
    does not parse (something half typed further down), the statement is found by its indentation and
    the shortest run of lines that parses; failing that, the line alone, so Python's error says why."""
    lines = code.split("\n")
    if not 1 <= line <= len(lines):
        raise NotebookError(f"There is no line {line}: the code has {len(lines)}.")
    try:
        spans = _top_level(code)
    except SyntaxError:
        spans = []
        found = _by_indentation(lines, line)
        if found is None:
            return None
        start, end = found
        after = next((n for n in range(end + 1, len(lines) + 1) if _starts_statement(lines[n - 1])), None)
        return start, end, after
    for i, (start, end) in enumerate(spans):
        if start <= line <= end:
            return start, end, spans[i + 1][0] if i + 1 < len(spans) else None
    return None


def _starts_statement(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("#") and not text[:1].isspace()


def _by_indentation(lines: list[str], line: int) -> tuple[int, int] | None:
    here = lines[line - 1].strip()
    if not here or here.startswith("#"):
        return None
    start = line
    while start > 1 and (
        lines[start - 1][:1].isspace() or not lines[start - 1].strip() or _CARRY_ON.match(lines[start - 1])
    ):
        start -= 1
    while start < line and not _starts_statement(lines[start - 1]):
        start += 1
    for end in range(line, min(len(lines), line + 500) + 1):
        following = lines[end] if end < len(lines) else ""
        if following.strip() and (following[:1].isspace() or _CARRY_ON.match(following)):
            continue  # the statement goes on below
        try:
            ast.parse("\n".join(lines[start - 1 : end]))
        except SyntaxError:
            continue
        return start, end
    return line, line
