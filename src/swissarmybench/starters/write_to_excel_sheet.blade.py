# /// swissarmybench-blade
# format = 1
# name = "Write to an Excel sheet"
# kind = "other"
# description = "The rows as a workbook's sheet, others kept (dry run first; writes on the user's word)"
# tags = ["write", "files", "excel", "folder"]
# family = "Write"
# variable = "write_excel_sheet"
# ///
"""Excel sheet: the rows written to a sheet of a workbook, its column names on top. The workbook's other
sheets stay as they are; a new workbook is made when there is none.

    write_excel_sheet = sab.blade("Write to an Excel sheet")  # the project's functions.py will hold it

Dry run first: dry_run=True (the default) only says what it would do and changes nothing;
dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their own
words, in this conversation. Returns the write's report.

Written to a new file beside the workbook, then put in its place: a failure leaves it as it was.
Close the workbook in Excel first. Formatting: the Excel starters (Excel number formats, Excel range as
table, Excel autofit columns) work on the file it writes.
"""

from pathlib import Path
from typing import Any

import openpyxl  # noqa: F401 (the package this needs: writes the workbook)

from swissarmybench.client.writes import FileWrite


def write_excel_sheet(
    path: str | Path,
    sheet: str,
    rows: Any,
    if_there: str = "stop",
    dry_run: bool = True,
) -> FileWrite:
    """The rows written to a sheet of a workbook, its column names on top."""
    w = FileWrite(path, "xlsx", rows, dry_run=dry_run, overwrite=True)
    there = w.sheet_rows(sheet)  # None: no such sheet yet; else the rows it holds (its header too)
    if there is not None and if_there == "stop":
        raise ValueError(f"{path} has a sheet {sheet!r} already: set if_there to replace or add.")
    adding = there is not None and if_there == "add"
    w.would(
        f"{'add to' if adding else 'write'} the sheet {sheet!r} of {w.path}"
        + ("" if adding else ", its column names on top"),
        written=w.need_rows().count,
    )
    if not dry_run:
        w.done(written=w.sheet(sheet, add=adding))
    return w
