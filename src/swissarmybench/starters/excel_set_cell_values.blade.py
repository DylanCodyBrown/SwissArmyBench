# /// swissarmybench-blade
# format = 1
# name = "Excel set cell values"
# kind = "other"
# description = "Set cells' values: a dict of cells, or rows from a cell"
# tags = ["excel", "cells"]
# family = "Excel"
# variable = "set_values"
# ///
"""Set cells' values in a sheet: a dict of cells, or rows of values starting at a cell.

    set_values = sab.blade("Excel set cell values")
    set_values("C:/reports/sales.xlsx", "Summary", {"A1": "Region", "B1": "Total", "B2": 1250.5})
    set_values("C:/reports/sales.xlsx", "Summary", [["North", 10], ["South", 12]], start="A2")

A value is a number, text, a date, True or False, or None (empties the cell); text that starts with
= is a formula ("=SUM(B2:B9)"). Returns the workbook's path. Changes are saved into the workbook.
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


def set_values(
    path: str | Path,
    sheet: str,
    values: dict[str, Any] | list[list[Any]],
    start: str = "A1",
) -> str:
    """Set each cell in `values` ({"A1": value}), or write `values` as rows from `start`."""
    book, file = _open(path)
    target = _sheet(book, sheet)
    if isinstance(values, dict):
        for cell, value in values.items():
            target[cell] = value
    elif isinstance(values, list):
        top = target[start]
        for r, row in enumerate(values):
            for c, value in enumerate(row if isinstance(row, list | tuple) else [row]):
                target.cell(row=top.row + r, column=top.column + c, value=value)
    else:
        raise ExcelError('Send the values as {"A1": value} or as rows: [[1, 2], [3, 4]].')
    return _save(book, file)
