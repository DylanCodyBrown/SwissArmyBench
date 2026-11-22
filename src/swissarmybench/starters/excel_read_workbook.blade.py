# /// swissarmybench-blade
# format = 1
# name = "Excel read a workbook"
# kind = "other"
# description = "A sheet or a named table of a workbook as a table (the adapter's one reader)"
# tags = ["excel", "read"]
# family = "Excel"
# variable = "read_workbook"
# ///
"""Read a workbook: one sheet, or one named table, as a DataFrame.

    read_workbook = sab.blade("Excel read a workbook")
    orders = read_workbook("C:/reports/sales.xlsx", "Orders")
    cities = read_workbook("C:/reports/sales.xlsx", "Report", cells="B3:F40")   # only these cells
    first = read_workbook("C:/reports/sales.xlsx", "Orders", columns=["region", "amount"], limit=100)

The first row is the column names (header_row: another row). A formula gives its last result. A column
that mixes kinds (a number column with an "n/a" in it) is read as text, every value kept. With no sheet
named, a workbook of one sheet gives it; one of several says their names.

The reading is the adapter's (adapter.Excel): the same rules as a workbook opened as a grid.

Laid out top to bottom: the imports, then `read_workbook`, the one function, which you call.
"""

from pathlib import Path
from typing import Any

import duckdb  # noqa: F401 (the packages this needs: the adapter's own two, and openpyxl for a workbook)
import openpyxl  # noqa: F401
import pyarrow  # noqa: F401

try:  # adapter.py beside this code (a project, an exported script carries it); in the app, the app's own
    import adapter  # type: ignore[import-not-found]

    if not hasattr(adapter, "Excel"):  # a copy from before 1.4.0 reads no workbook
        raise ImportError("the adapter.py beside this code is older than 1.4.0")
except ImportError:
    from swissarmybench.adapters import adapter


def read_workbook(
    path: str | Path,
    sheet: str = "",
    header_row: int = 1,
    cells: str = "",
    columns: list[str] | None = None,
    limit: int | None = None,
) -> Any:
    """A sheet (or a named table) of the workbook at `path` as a DataFrame."""
    source = adapter.Excel(Path(path).expanduser(), header_row=header_row, cells=cells)
    plan = adapter.Plan(columns=tuple(columns or ()), limit=limit)
    reader, _folded = adapter.read(source, sheet, plan)
    return reader.read_pandas()
