# /// swissarmybench-blade
# format = 1
# name = "Excel borders"
# kind = "other"
# description = "Borders on a range: thin or thick, all cells or the outline"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "borders"
# ///
"""Borders on a range of cells: thin, medium or thick lines, on every cell or only around the outline.

    borders = sab.blade("Excel borders")
    borders("C:/reports/sales.xlsx", "Summary", "A1:D10")                          # thin, every cell
    borders("C:/reports/sales.xlsx", "Summary", "A1:D10", style="thick", where="outline")

Returns the workbook's path. Changes are saved into the workbook.

Laid out top to bottom: opening and saving a workbook, then this starter's own functions; `borders`, the
one you call, is last.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, Side

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

STYLES = ("thin", "medium", "thick", "dashed", "dotted", "double")


def borders(
    path: str | Path,
    sheet: str,
    cells: str,
    style: str = "thin",
    where: str = "all",
    color: str = "000000",
) -> str:
    """Draw `style` lines on `cells`: on every cell's four sides (where="all") or only around the
    range (where="outline"). `color` is a hex colour (000000 is black)."""
    if style not in STYLES:
        raise ExcelError(f"style is one of {', '.join(STYLES)}, not {style!r}.")
    if where not in ("all", "outline"):
        raise ExcelError(f'where is "all" or "outline", not {where!r}.')
    book, file = _open(path)
    target = _sheet(book, sheet)
    line = Side(style=style, color=color.lstrip("#"))
    rows = _cells(target, cells)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if where == "all":
                cell.border = Border(left=line, right=line, top=line, bottom=line)
                continue
            old = cell.border
            cell.border = Border(
                left=line if c == 0 else old.left,
                right=line if c == len(row) - 1 else old.right,
                top=line if r == 0 else old.top,
                bottom=line if r == len(rows) - 1 else old.bottom,
            )
    return _save(book, file)
