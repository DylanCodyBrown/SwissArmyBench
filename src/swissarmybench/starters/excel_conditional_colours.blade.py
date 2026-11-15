# /// swissarmybench-blade
# format = 1
# name = "Excel conditional colours"
# kind = "other"
# description = "Colour cells by a simple rule, such as below 0"
# tags = ["excel", "format"]
# family = "Excel"
# variable = "color_rule"
# ///
"""Colour cells by a simple rule (Excel's conditional formatting): the colour follows the values as
they change in Excel.

    color_rule = sab.blade("Excel conditional colours")
    color_rule("C:/reports/sales.xlsx", "Summary", "B2:B9", "<", 0)                   # negatives red
    color_rule("C:/reports/sales.xlsx", "Summary", "C2:C9", ">=", 1000, fill="C6EFCE", text="006100")
    color_rule("C:/reports/sales.xlsx", "Summary", "C2:C9", "between", 10, 20)

Rules: >, >=, <, <=, =, !=, between. Returns the workbook's path. Changes are saved into the workbook.
"""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill

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

RULES = {
    ">": "greaterThan",
    ">=": "greaterThanOrEqual",
    "<": "lessThan",
    "<=": "lessThanOrEqual",
    "=": "equal",
    "!=": "notEqual",
    "between": "between",
}


def color_rule(
    path: str | Path,
    sheet: str,
    cells: str,
    rule: str,
    value: Any,
    upper: Any = None,
    fill: str = "FFC7CE",
    text: str = "9C0006",
) -> str:
    """Fill (and colour the text of) each cell in `cells` whose value meets `rule` against `value`
    (between: from `value` to `upper`). The colours are hex: a pale red with dark red text by default."""
    if rule not in RULES:
        raise ExcelError(f"rule is one of {', '.join(RULES)}, not {rule!r}.")
    if rule == "between" and upper is None:
        raise ExcelError("between needs both ends: color_rule(..., 'between', 10, 20).")
    book, file = _open(path)
    target = _sheet(book, sheet)
    formula = [repr(value) if isinstance(value, str) else str(value)]
    if rule == "between":
        formula.append(repr(upper) if isinstance(upper, str) else str(upper))
    target.conditional_formatting.add(
        cells,
        CellIsRule(
            operator=RULES[rule],
            formula=[f.replace("'", '"') for f in formula],
            fill=PatternFill(fill_type="solid", start_color=fill.lstrip("#"), end_color=fill.lstrip("#")),
            font=Font(color=text.lstrip("#")),
        ),
    )
    return _save(book, file)
