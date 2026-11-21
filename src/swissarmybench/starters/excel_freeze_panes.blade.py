# /// swissarmybench-blade
# format = 1
# name = "Excel freeze panes"
# kind = "other"
# description = "Keep the top rows or left columns in view"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "freeze"
# ///
"""Freeze panes: keep the rows above a cell and the columns left of it in view while scrolling.

    freeze = sab.blade("Excel freeze panes")
    freeze("C:/reports/sales.xlsx", "Orders")             # the header row (A2)
    freeze("C:/reports/sales.xlsx", "Orders", "B2")       # the header row and the first column
    freeze("C:/reports/sales.xlsx", "Orders", None)       # unfreeze

Returns the workbook's path. Changes are saved into the workbook.

Laid out top to bottom: opening and saving a workbook, then this starter's own functions; `freeze`, the
one you call, is last.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

# ===== opening and saving a workbook (the same in every Excel starter) =====


class ExcelError(ValueError):
    """The workbook, sheet or cells cannot be used as asked: the message says why."""


def _open(path: str | Path, create: bool = False) -> tuple[Any, Path]:
    """The workbook at `path` (a new, empty one when `create` and there is no file yet)."""
    file = Path(path).expanduser()
    if file.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ExcelError(f"{file.name} is not an Excel workbook (.xlsx or .xlsm).")
    if not file.exists():
        if not create:
            raise ExcelError(f"There is no workbook at {file}.")
        book = Workbook()
        book.remove(book.active)  # a new workbook starts with no sheet: the caller adds its own
        return book, file
    return load_workbook(file, keep_vba=file.suffix.lower() == ".xlsm"), file


def _sheet(book: Any, sheet: str | None) -> Any:
    """A sheet by its name (None: the first one)."""
    if sheet is None:
        return book.worksheets[0]
    if sheet not in book.sheetnames:
        listed = ", ".join(book.sheetnames) or "none"
        raise ExcelError(f"The workbook has no sheet {sheet!r}. It has: {listed}.")
    return book[sheet]


def _cells(target: Any, cells: str) -> list[list[Any]]:
    """A range's cells, row by row: "A1:D10", one cell ("B2"), a column ("C") or a row ("3")."""
    found = target[cells]
    if not isinstance(found, tuple):
        return [[found]]
    return [list(row) if isinstance(row, tuple) else [row] for row in found]


def _save(book: Any, file: Path) -> str:
    """Save the workbook where it came from; its path, for the next step."""
    if not book.worksheets:
        book.create_sheet("Sheet1")
    file.parent.mkdir(parents=True, exist_ok=True)
    book.save(file)
    return str(file)


# ===== this starter =====


def freeze(path: str | Path, sheet: str, cell: str | None = "A2") -> str:
    """Freeze the rows above `cell` and the columns left of it (None: unfreeze)."""
    book, file = _open(path)
    target = _sheet(book, sheet)
    target.freeze_panes = cell
    return _save(book, file)
