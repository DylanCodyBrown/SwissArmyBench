# /// swissarmybench-blade
# format = 1
# name = "Excel autofit columns"
# kind = "other"
# description = "Widen each column to fit what it holds"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "autofit"
# ///
"""Widen each column of a sheet (or of every sheet) to fit the longest value it holds.

    autofit = sab.blade("Excel autofit columns")
    autofit("C:/reports/sales.xlsx")                 # every sheet
    autofit("C:/reports/sales.xlsx", "Summary", max_width=40)

Excel's own autofit needs Excel running; this measures each value's text instead (close, not exact).
Returns the workbook's path. Changes are saved into the workbook.

Laid out top to bottom: opening and saving a workbook, then this starter's own functions; `autofit`, the
one you call, is last.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

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


def autofit(path: str | Path, sheet: str | None = None, min_width: float = 6, max_width: float = 60) -> str:
    """Set each column's width to its longest value's length (plus a little), between min_width and
    max_width characters. `sheet` None: every sheet."""
    book, file = _open(path)
    sheets = [_sheet(book, sheet)] if sheet is not None else book.worksheets
    for target in sheets:
        longest: dict[int, int] = {}
        for row in target.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                text = f"{cell.value:,.2f}" if isinstance(cell.value, float) else str(cell.value)
                widest = max(len(part) for part in text.split("\n"))
                longest[cell.column] = max(longest.get(cell.column, 0), widest)
        for column, length in longest.items():
            width = min(max_width, max(min_width, length + 2))
            target.column_dimensions[get_column_letter(column)].width = width
    return _save(book, file)
