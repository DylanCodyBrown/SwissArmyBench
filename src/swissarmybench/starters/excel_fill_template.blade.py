# /// swissarmybench-blade
# format = 1
# name = "Excel fill a template"
# kind = "other"
# description = "A copy of a template workbook with its places filled; its table grows with its rows"
# tags = ["excel", "template"]
# family = "Excel"
# variable = "fill_template"
# ///
"""Fill a template: a copy of an existing workbook (its layout, formats and formulas kept) with its places
filled from your data.

    fill_template = sab.blade("Excel fill a template")
    fill_template(
        "C:/templates/invoice.xlsx", "C:/out/INV-1001.xlsx",
        places=[
            {"kind": "value", "place": "B2", "value": {"column": "customer"}},
            {"kind": "value", "place": "B3", "value": {"number": True}},
            {"kind": "table", "place": "A8", "columns": ["item", "amount"], "rows": 1},
        ],
        values=invoice, lines=lines, number="INV-1001",
    )

A place is a cell (B2, Invoice!B2) or a named range. A value place takes a column of `values` (its first
row), a text ({"text": "Statement for {customer}"}), the number or the date. A table place takes the rows
of `lines` from that cell down: the rows under it move down and the formulas over it grow (rows: how many
rows the template has there). The template itself is never changed.

One workbook per customer, numbered, with a register: sab_excel.build with "group_by" in its design.
The filling is sab_excel's (sab_excel.build with a template).

Laid out top to bottom: the imports, then `fill_template`, the one function, which you call.
"""

from pathlib import Path
from typing import Any

import openpyxl  # noqa: F401 (the package this needs: sab_excel fills the workbook with it)

from swissarmybench import sab_excel


def fill_template(
    template: str | Path,
    path: str | Path,
    places: list[dict[str, Any]],
    values: Any = None,
    lines: Any = None,
    number: Any = None,
) -> str:
    """A copy of `template` at `path`, its `places` filled from `values` and `lines`. Its path."""
    grids = {"values": values if values is not None else ([], [])}
    design = {"bindings": places, "data": "values", "number": number}
    if lines is not None:
        grids["lines"] = lines
        design["lines"] = "lines"
    made: str = sab_excel.build(
        grids, design, template=Path(template).expanduser(), out=Path(path).expanduser()
    )
    return made
