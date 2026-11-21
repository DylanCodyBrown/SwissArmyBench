# /// swissarmybench-blade
# format = 1
# name = "Excel range as table"
# kind = "other"
# description = "Make a range an Excel table, with filters and banded rows"
# tags = ["excel", "table"]
# family = "Excel"
# variable = "as_table"
# ///
"""Make a range an Excel table: filter buttons on its header, banded rows, a name formulas can use.

    as_table = sab.blade("Excel range as table")
    as_table("C:/reports/sales.xlsx", "Orders", "A1:F41", "Orders")
    as_table("C:/reports/sales.xlsx", "Orders", None, "Orders")        # the sheet's whole used range

The range's first row is the header. Returns the workbook's path. Changes are saved into the workbook.

Laid out top to bottom: opening and saving a workbook, then this starter's own functions; `as_table`,
the one you call, is last.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

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


def as_table(
    path: str | Path,
    sheet: str,
    cells: str | None,
    name: str,
    style: str = "TableStyleMedium2",
) -> str:
    """Make `cells` (None: the sheet's used range) the table `name` (letters, digits and _, unique in
    the workbook), drawn in Excel's `style`."""
    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        raise ExcelError(f"A table's name is letters, digits and _, starting with a letter ({name!r}).")
    book, file = _open(path)
    target = _sheet(book, sheet)
    taken = {table for each in book.worksheets for table in each.tables}
    if name in taken:
        raise ExcelError(f"The workbook already has a table named {name!r}.")
    table = Table(displayName=name, ref=cells or target.dimensions)
    table.tableStyleInfo = TableStyleInfo(name=style, showRowStripes=True)
    target.add_table(table)
    return _save(book, file)
