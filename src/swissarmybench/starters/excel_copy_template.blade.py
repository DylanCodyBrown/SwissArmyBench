# /// swissarmybench-blade
# format = 1
# name = "Excel copy template"
# kind = "other"
# description = "A new workbook copied from a template workbook"
# tags = ["excel", "template"]
# family = "Excel"
# variable = "copy_template"
# ///
"""A new workbook copied from a template workbook (an invoice, a report), to fill in after.

    copy_template = sab.blade("Excel copy template")
    path = copy_template("C:/templates/invoice.xlsx", "C:/invoices/invoice-0042.xlsx")

The template is never changed. A file already at the new path is written over only with
overwrite=True. Returns the new workbook's path, for the next step.
"""

import shutil
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


def copy_template(template: str | Path, path: str | Path, overwrite: bool = False) -> str:
    """Copy the workbook `template` to `path` (its folder is made when it is not there)."""
    source, file = Path(template).expanduser(), Path(path).expanduser()
    if not source.is_file():
        raise ExcelError(f"There is no template at {source}.")
    if file.suffix.lower() != source.suffix.lower():
        raise ExcelError(f"Keep the template's kind of file: {source.suffix} (not {file.suffix or 'none'}).")
    if file.exists() and not overwrite:
        raise ExcelError(f"{file} already exists: pass overwrite=True to write over it.")
    if file.resolve() == source.resolve():
        raise ExcelError("The new workbook's path is the template's own.")
    _open(source)  # it is a workbook Excel can open
    file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, file)
    return str(file)
