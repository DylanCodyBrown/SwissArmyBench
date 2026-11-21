# /// swissarmybench-blade
# format = 1
# name = "Excel number formats"
# kind = "other"
# description = "Number formats on a range: money, percent, dates, or your own"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "number_format"
# ///
"""Number formats on a range of cells: money, percent, thousands, dates, or a format of your own.

    number_format = sab.blade("Excel number formats")
    number_format("C:/reports/sales.xlsx", "Summary", "B2:B9", "money")      # 1,250.50
    number_format("C:/reports/sales.xlsx", "Summary", "C2:C9", "percent")    # 12.5%
    number_format("C:/reports/sales.xlsx", "Summary", "D2:D9", "yyyy-mm-dd")

The named ones (FORMATS below): money, whole, thousands, percent, date, datetime and text; anything
else is used as Excel's own format code. Returns the workbook's path. Changes are saved into the workbook.

Laid out top to bottom: opening and saving a workbook, then this starter's own functions;
`number_format`, the one you call, is last.
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

# Plain names for Excel's format codes.
FORMATS = {
    "money": "#,##0.00",
    "whole": "#,##0",
    "thousands": '#,##0,"k"',
    "percent": "0.0%",
    "date": "yyyy-mm-dd",
    "datetime": "yyyy-mm-dd hh:mm",
    "text": "@",
}


def number_format(path: str | Path, sheet: str, cells: str, format: str = "money") -> str:
    """Give every cell in `cells` the number format `format` (a name in FORMATS, or a format code)."""
    code = FORMATS.get(format, format)
    if not code.strip():
        raise ExcelError("Name a format: money, percent, date... or a format code such as 0.00.")
    book, file = _open(path)
    target = _sheet(book, sheet)
    for row in _cells(target, cells):
        for cell in row:
            cell.number_format = code
    return _save(book, file)
