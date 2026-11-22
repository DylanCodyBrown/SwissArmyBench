# /// swissarmybench-blade
# format = 1
# name = "Excel make a workbook"
# kind = "other"
# description = "Tables as a workbook: plain, or laid out by a design (formats, totals, charts)"
# tags = ["excel", "write", "format"]
# family = "Excel"
# variable = "make_workbook"
# ///
"""Make a workbook from tables: a sheet each as they are, or laid out by a design.

    make_workbook = sab.blade("Excel make a workbook")
    make_workbook("C:/reports/sales.xlsx", {"Orders": orders, "Totals": totals})     # plain: a sheet each

    design = {"sheets": [{"name": "Report", "freeze": "A3", "blocks": [
        {"id": "title", "kind": "title", "cell": "A1", "text": "Sales"},
        {"id": "orders", "kind": "table", "cell": "A2", "source": {"table": "orders"}, "total_row": True,
         "columns": [{"name": "region"}, {"name": "amount", "format": "currency", "total": "sum"}],
         "conditional": [{"column": "amount", "op": "<", "value": 0, "fill": "F8D7DA"}]},
        {"id": "chart", "kind": "chart", "cell": "E2", "chart": "column", "from": "orders"},
    ]}]}
    make_workbook("C:/reports/sales.xlsx", {"orders": orders}, design)

What the cell-level Excel starters did is a design option now: number formats and widths on a table's
columns, a total row, colours by a rule (conditional), a title or text over merged cells (w, h), freeze
panes and print setup on a sheet, a pivot (DuckDB's summary) and Excel's own charts. A design with no
sheets, {"style": {...}, "formats": {...}}, gives each table a sheet in that look.

Text from the data is always text, never a formula. The file is written beside its place, then put there.
The making is sab_excel's (sab_excel.build): the Accounting canvas draws the same designs.

Laid out top to bottom: the imports, then `make_workbook`, the one function, which you call.
"""

from pathlib import Path
from typing import Any

import duckdb  # noqa: F401 (the packages this needs: sab_excel writes the workbook with them)
import openpyxl  # noqa: F401

try:  # sab_excel.py beside this code (a project, an exported script carries it); in the app, the app's own
    import sab_excel  # type: ignore[import-not-found]
except ImportError:
    from swissarmybench import sab_excel


def make_workbook(path: str | Path, tables: dict[str, Any], design: dict[str, Any] | None = None) -> str:
    """The tables (by name) as the workbook at `path`: plain, or as `design` lays them out. Its path."""
    made: str = sab_excel.build(tables, design, out=Path(path).expanduser())
    return made
