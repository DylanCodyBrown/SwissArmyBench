# /// swissarmybench-blade
# format = 1
# name = "Excel write table"
# kind = "other"
# description = "Write a DataFrame to a sheet, from a cell"
# tags = ["excel", "table"]
# family = "Excel"
# variable = "write_table"
# ///
"""Write a table (a pandas DataFrame) to a sheet, starting at a cell, with its column names on top.

    write_table = sab.blade("Excel write table")
    write_table("C:/reports/sales.xlsx", "Orders", orders)            # from A1
    write_table("C:/reports/sales.xlsx", "Summary", totals, start="B3")

The workbook and the sheet are made when they are not there. Cells that already hold values are
written over only with overwrite=True. Returns the workbook's path.
"""

from pathlib import Path
from typing import Any

import pandas as pd
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


def write_table(
    path: str | Path,
    sheet: str,
    frame: pd.DataFrame,
    start: str = "A1",
    header: bool = True,
    overwrite: bool = False,
) -> str:
    """Write `frame` to `sheet` from `start`: its column names (when `header`), then its rows."""
    book, file = _open(path, create=True)
    target = book[sheet] if sheet in book.sheetnames else book.create_sheet(sheet)
    top = target[start]
    rows: list[list[Any]] = [list(map(str, frame.columns))] if header else []
    for record in frame.itertuples(index=False):
        rows.append([None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in record])
    width = len(frame.columns)
    if not overwrite:
        for r in range(len(rows)):
            for c in range(width):
                if target.cell(row=top.row + r, column=top.column + c).value is not None:
                    where = target.cell(row=top.row + r, column=top.column + c).coordinate
                    message = f"{sheet}!{where} already holds a value: pass overwrite=True to write over."
                    raise ExcelError(message)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            target.cell(row=top.row + r, column=top.column + c, value=value)
    return _save(book, file)
