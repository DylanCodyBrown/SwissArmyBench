# /// swissarmybench-blade
# format = 1
# name = "Excel fonts and fills"
# kind = "other"
# description = "Bold, italic, size, text colour and fill on a range"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "style_cells"
# ///
"""Fonts and fills on a range of cells: bold, italic, size, the text's colour and the cells' fill.

    style_cells = sab.blade("Excel fonts and fills")
    style_cells("C:/reports/sales.xlsx", "Summary", "A1:D1", bold=True, fill="DDEBF7")
    style_cells("C:/reports/sales.xlsx", "Summary", "B2:B9", color="C00000", size=12)

Colours are hex (C00000 is a deep red, DDEBF7 a pale blue). What is not given stays as it was.
Returns the workbook's path. Changes are saved into the workbook.
"""

from copy import copy
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

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


def style_cells(
    path: str | Path,
    sheet: str,
    cells: str,
    bold: bool | None = None,
    italic: bool | None = None,
    size: float | None = None,
    color: str | None = None,
    fill: str | None = None,
) -> str:
    """Set the font (bold, italic, size, color) and the fill of every cell in `cells`."""
    book, file = _open(path)
    target = _sheet(book, sheet)
    for row in _cells(target, cells):
        for cell in row:
            font = copy(cell.font)
            if bold is not None:
                font.bold = bold
            if italic is not None:
                font.italic = italic
            if size is not None:
                font.size = size
            if color is not None:
                font.color = color.lstrip("#")
            cell.font = font
            if fill is not None:
                cell.fill = PatternFill(fill_type="solid", fgColor=fill.lstrip("#"))
    return _save(book, file)
