# /// swissarmybench-blade
# format = 1
# name = "Excel add sheet"
# kind = "other"
# description = "Add a sheet to a workbook (made if it is not there)"
# tags = ["excel", "sheet"]
# family = "Excel"
# variable = "add_sheet"
# ///
"""Add a sheet to an Excel workbook; the workbook is made when there is none at that path.

    add_sheet = sab.blade("Excel add sheet")
    add_sheet("C:/reports/sales.xlsx", "Summary")              # at the end
    add_sheet("C:/reports/sales.xlsx", "Cover", index=0)       # first
    add_sheet("C:/reports/sales.xlsx", "Summary", overwrite=True)  # an empty one in its place

Returns the workbook's path, for the next step.
Changes are saved into the workbook itself. Nothing is written over without overwrite=True: an
existing sheet is never replaced, nor a file.
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


def add_sheet(path: str | Path, sheet: str, index: int | None = None, overwrite: bool = False) -> str:
    """Add the sheet `sheet` at `index` (None: the end). A sheet of that name is replaced by an empty
    one only with overwrite=True."""
    book, file = _open(path, create=True)
    if sheet in book.sheetnames:
        if not overwrite:
            raise ExcelError(f"{file.name} already has a sheet {sheet!r}: pass overwrite=True to replace it.")
        at = book.sheetnames.index(sheet)
        book.remove(book[sheet])
        index = at if index is None else index
    book.create_sheet(sheet, index)
    return _save(book, file)
