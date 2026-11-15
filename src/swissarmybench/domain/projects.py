"""Projects: data first (docs/ideas.md, "Projects: a data-first IDE for Streamlit", 2026-11-15).

A project is a folder. It always starts with the data:

    sales/
      data.ipynb         the data's canvas: the tables' read-only cells, blade cells, and the user's
                         own code cells that shape variables. The user works here
      data.py            its EXPORT: data.ipynb's code cells in order. Never edited by hand
      sales.stapp.json   the app's canvas: pages, blocks, links (domain/streamlit_cells.py)
      pages/*.py         its EXPORT: one module a page, each starting with `from data import ...`
      *.ipynb, *.py      any number of other notebooks and scripts (analysis, mock-ups): optional
      requirements.txt

The symmetry: data.ipynb -> data.py, and the app's canvas -> pages/*.py. A table's read-only cell
lives in data.ipynb; every other notebook and every page starts with `from data import ...`, so a
table has one text. Pure rules, no I/O:

  export    data.py from data.ipynb's cells: the code cells in order (a table's cell as it stands:
            its load, then the grid's steps as one DuckDB query); Markdown, outputs, SQL, DAX and HTML
            cells, cells that call Streamlit and IPython's own lines (%magic, !command) left out. A
            table the app cannot read again (pasted, dropped, sent from Python) is a clearly marked
            stub: no rows are ever written. It imports in a plain kernel with no Streamlit, and under
            Streamlit it runs once and is kept (st.cache_resource)
  names     what `from data import` can give: the names its cells make
  zip       a notebook for a zip: its outputs dropped and a pasted table's rows taken out
  rows      which tables' rows a notebook's cells hold (a small paste written out): what the agent
            may write to disk only on the user's Allow (docs/ideas.md, 2026-11-15)
  files     which of a folder's files the Workbench opens, data first; README, requirements
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from swissarmybench.domain import streamlit_cells, table_cells
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.streamlit_use import uses_streamlit, usual_name

DATA_NOTEBOOK: str = "data.ipynb"
DATA_FILE: str = "data.py"
REQUIREMENTS_FILE: str = "requirements.txt"
PAGES_FOLDER: str = "pages"
MAX_NAME: int = 60
MAX_FILES: int = 200
_FOLDER = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]+$")
# A table's cell that cannot read the table again: the notes domain/table_cells.py writes for a table
# no code made and no file or connection gives, and a small paste's rows written out.
_NO_LOAD = re.compile(
    r"^# .+ was (?:made outside this file|dropped on the page|pasted into the grid|opened from) ", re.M
)
_PASTED = re.compile(r"\bFROM \(VALUES\b[\s\S]*\) AS pasted\(")
_IPYTHON = re.compile(r"^\s*[%!?]")


class ProjectError(ValueError):
    """A project that cannot be made or exported as asked (the message says why)."""


def check_folder_name(name: str) -> str:
    """A new project's folder name (or a notebook's): one name, nothing a file system refuses."""
    said = name.strip() if isinstance(name, str) else ""
    if not said or len(said) > MAX_NAME or not _FOLDER.match(said) or said in (".", ".."):
        raise ProjectError("A name here is a file's or folder's own: one name, at most 60 characters.")
    return said


@dataclass(frozen=True)
class DataCell:
    """A cell of data.ipynb, as the export reads it."""

    kind: str  # code, sql, dax, html, markdown
    source: str
    role: str = ""  # its part in the Tables group (domain/table_cells.py)
    table: str | None = None
    number: int | None = None


@dataclass(frozen=True)
class DataModule:
    text: str
    names: tuple[str, ...]  # what `from data import` gives
    fill_in: tuple[str, ...]  # the tables left as stubs
    skipped: tuple[str, ...]  # what was left out, in words


HEAD: str = '''\
"""{title}: its data, exported from data.ipynb by Swiss Army Bench. Do not edit: change data.ipynb.

    from data import {example}

No rows and no passwords are kept here: each table is read again the way it was loaded.
"""
import functools

try:  # under Streamlit this runs once and is kept; in a plain kernel Python keeps it
    import streamlit as _st

    _once = _st.cache_resource(show_spinner=False) if _st.runtime.exists() else functools.cache
except ImportError:  # no Streamlit here (a notebook's kernel): nothing of it is needed
    _once = functools.cache
'''


def _wraps(code: str) -> bool:
    """The code can sit inside a function: whole Python, no `import *`, no `global`."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Global | ast.Nonlocal):
            return False
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            return False
        if isinstance(node, ast.Return | ast.Yield | ast.YieldFrom | ast.Await) and not _inside_function(
            tree, node
        ):
            return False
    return True


def _inside_function(tree: ast.AST, target: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) and any(
            child is target for child in ast.walk(node)
        ):
            return True
    return False


def _stub(table: str, variable: str, why: str) -> str:
    return (
        f"# ===== FILL IN: {table} =====\n"
        f"# {why} No rows are kept here.\n"
        f"# In data.ipynb, add a cell above this table's cell that reads it ({variable} = ...).\n"
        f"{variable} = None"
    )


def data_module(title: str, cells: Sequence[DataCell]) -> DataModule:
    """data.py: data.ipynb's code cells in order, as one module."""
    parts: list[str] = []
    skipped: list[str] = []
    fill_in: list[str] = []
    code_cells = [c for c in cells if c.kind == "code" and c.role not in ("tables", "table")]
    usual = usual_name(tuple(c.source for c in code_cells))
    for cell in cells:
        label = f"cell {cell.number}" if cell.number is not None else "a cell"
        if cell.kind == "markdown" or cell.role in ("tables", "table") or not cell.source.strip():
            continue
        if cell.kind != "code":
            skipped.append(
                f"{label}: a {cell.kind.upper()} cell is not Python (run it into a table instead)."
            )
            continue
        source = table_cells.split_uses(cell.source)[1].strip("\n")
        if cell.role == "transformations" and cell.table:
            variable = variable_name(cell.table)
            found = _NO_LOAD.search(source)
            pasted = _PASTED.search(source) is not None
            if found or pasted:
                why = "It was pasted into the grid." if not found else found.group(0)[2:].strip() + "..."
                why = f"{cell.table} cannot be read again by the app. {why}".replace("...", ".")
                # Without a cell of the user's that makes it, there is nothing to transform yet.
                made_above = any(
                    variable in table_cells.facts(c.source).made
                    for c in code_cells
                    if c.role != "transformations"
                )
                if pasted and made_above:
                    # Its cell holds the pasted rows: left out (no rows leave), the user's cell stays.
                    skipped.append(f"{label}: {cell.table}'s cell holds the rows pasted into the grid.")
                    continue
                if not made_above:
                    parts.append(_stub(cell.table, variable, why.split("\n")[0]))
                    fill_in.append(cell.table)
                    continue
        elif uses_streamlit(source, usual):
            skipped.append(f"{label}: it calls Streamlit, so it belongs on a page, not in the data.")
            continue
        lines = source.split("\n")
        if any(_IPYTHON.match(line) for line in lines):
            try:
                ast.parse(source)
            except SyntaxError:
                lines = [f"# {line}" if _IPYTHON.match(line) else line for line in lines]
                skipped.append(f"{label}: IPython's own lines (%magic, !command) are left out.")
        said = f"# cell {cell.number}" if cell.number is not None else "# a cell"
        if cell.role == "transformations" and cell.table:
            said += f": {cell.table}"
        parts.append(said + "\n" + "\n".join(lines))
    body = "\n\n".join(parts)
    names = _names(body)
    example = ", ".join(names[:2]) or "orders"
    head = HEAD.format(title=title.replace('"""', "'''"), example=example)
    if not parts:
        return DataModule(head, (), tuple(fill_in), tuple(skipped))
    if _wraps(body):
        text = (
            f"{head}\n\n@_once\ndef _load():\n{streamlit_cells.indented(body)}\n\n"
            '    return {name: value for name, value in locals().items() if not name.startswith("_")}\n\n\n'
            "globals().update(_load())\n"
        )
    else:
        # Code that cannot sit in a function runs as the module itself: Python keeps a module once
        # it is imported, under Streamlit too.
        text = f"{head}\n\n{body}\n"
    return DataModule(text, tuple(names), tuple(fill_in), tuple(skipped))


def _names(code: str) -> list[str]:
    """The names the code makes at its top level (what `from data import` can give): variables and
    functions, not the modules it imports."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    modules = {
        (alias.asname or alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    made = table_cells.facts(code).made
    return [name for name in made if not name.startswith("_") and name not in modules]


def _holds_rows(cell: DataCell) -> bool:
    """A table's read-only cell with a small paste's rows written out in it."""
    return cell.role == "transformations" and bool(cell.table) and _PASTED.search(cell.source) is not None


def tables_with_rows(cells: Sequence[DataCell]) -> list[str]:
    """The tables whose rows these cells hold, written out (a small paste's read-only cell), in order.
    A notebook made of these cells writes those rows to disk."""
    return list(dict.fromkeys(cell.table for cell in cells if cell.table and _holds_rows(cell)))


def without_rows(cells: Sequence[DataCell]) -> list[DataCell]:
    """A notebook's cells for a zip: a pasted table's rows (written out in its read-only cell) taken
    out. (Outputs are dropped by the caller: they show rows too.)"""
    out: list[DataCell] = []
    for cell in cells:
        if cell.table and _holds_rows(cell):
            variable = variable_name(cell.table)
            stub = _stub(cell.table, variable, f"{cell.table} was pasted into the grid.")
            out.append(DataCell(cell.kind, stub, cell.role, cell.table, cell.number))
        else:
            out.append(cell)
    return out


def script_without_rows(text: str) -> str:
    """A script for a zip: each pasted table's read-only cell (its rows written out) a stub, on the
    lines it held; everything else as it is."""
    lines = text.split("\n")
    for cell in reversed(table_cells.outline(text)["cells"]):
        body = "\n".join(lines[cell["line"] : cell["end"]])
        if cell["role"] == "transformations" and cell["table"] and _PASTED.search(body):
            stub = _stub(
                cell["table"], variable_name(cell["table"]), f"{cell['table']} was pasted into the grid."
            )
            lines[cell["line"] : cell["end"]] = [*stub.split("\n"), ""]
    return "\n".join(lines)


def data_requirements(text: str) -> list[str]:
    """What data.py needs installed, by what its code says."""
    needed = ["pandas"]
    if re.search(r"\b(?:duckdb|ddb)\.", text):
        needed.append("duckdb")
    if "read_excel" in text:
        needed.append("openpyxl")
    if re.search(r"\b(?:sab|sag)\.", text):  # sag: the old alias, in a notebook from before the rename
        needed.append(
            "# swissarmybench: install Swiss Army Bench's wheel (data.py reads through one of its "
            "connections or blades)"
        )
    return needed


def merged_requirements(held: str | None, needed: Sequence[str]) -> str:
    """requirements.txt with what is needed added: the lines it already holds stay as they are."""
    lines = (held or "").rstrip("\n").split("\n") if (held or "").strip() else []
    have = {re.split(r"[<>=!~ \[;#]", line.strip())[0].lower() for line in lines if not line.startswith("#")}
    notes = {line.split(":")[0] for line in lines if line.startswith("#")}
    for line in needed:
        if line.startswith("#"):
            if line.split(":")[0] not in notes:
                lines.append(line)
        elif re.split(r"[<>=!~ \[;]", line)[0].lower() not in have:
            lines.append(line)
    return "\n".join(lines) + "\n"


README: str = """\
{title}: a Swiss Army Bench project.

data.ipynb          the data's canvas: the tables and the variables everything starts from
data.py             its export: what the pages and the notebooks import (`from data import ...`)
{app:<19} the app's canvas
pages/*.py          its export: Streamlit pages ({pages})
requirements.txt    what to install

To add the pages to your own Streamlit app: copy pages/*.py into your app's pages/ folder and
data.py beside your app's main script, then install what requirements.txt lists.

To change the data or the pages: unzip, and open the folder as a project in Swiss Army Bench's Workbench.

No rows and no passwords are in this zip: data.py reads each table again the way it was loaded.
{notes}"""


def readme(
    title: str, pages: Sequence[str], app: str, fill_in: Sequence[str], documents: Sequence[str]
) -> str:
    lines: list[str] = []
    if fill_in:
        lines.append(
            "\nFILL IN: data.py cannot read "
            + ", ".join(fill_in)
            + " again (pasted, dropped, or sent from Python). Add the code that reads it to data.ipynb.\n"
        )
    if documents:
        lines.append("\nThe notebooks and scripts the pages' cells are in: " + ", ".join(documents) + "\n")
    return README.format(title=title, pages=", ".join(pages) or "none yet", app=app, notes="".join(lines))


def project_files(names: Iterable[str]) -> list[str]:
    """Which of a project folder's files the Workbench opens, in order: data.ipynb first, then the
    app's canvas, then the other notebooks, then scripts. data.py is an export: it is not opened."""

    def rank(name: str) -> int:
        lowered = name.lower()
        if lowered == DATA_NOTEBOOK:
            return 0
        if lowered.endswith(".stapp.json"):
            return 1
        return 2 if lowered.endswith(".ipynb") else 3

    wanted = [
        n
        for n in set(names)
        if n.lower().endswith((".py", ".ipynb", ".stapp.json"))
        and not n.startswith(".")
        and n.lower() != DATA_FILE
    ]
    return sorted(wanted, key=lambda n: (rank(n), n.lower()))[:MAX_FILES]
