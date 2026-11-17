# /// swissarmybench-blade
# format = 1
# name = "Write Excel sheet"
# kind = "snippet"
# description = "The rows as a workbook's sheet, others kept (dry run first; writes on the user's word)"
# tags = ["write", "files", "excel", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Excel sheet: the rows written to a sheet of a workbook, its column names on top. The workbook's other
# sheets stay as they are; a new workbook is made when there is none.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Written to a new file beside the workbook, then put in its place: a failure leaves it as it was.
# Close the workbook in Excel first. Formatting: the Excel starters (Excel number formats, Excel range as
# table, Excel autofit columns) work on the file it writes.
import openpyxl  # writes the workbook

from swissarmybench.client.writes import FileWrite

dry_run = True
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
path = "<<file: C:/reports/orders.xlsx>>"
sheet = "<<sheet: Orders>>"
if_there = "stop"  # when the sheet is there: "stop", or "replace" its cells, or "add" the rows below its own

w = FileWrite(path, "xlsx", rows, dry_run=dry_run, overwrite=True)
there = w.sheet_rows(sheet)  # None: no such sheet yet; else the rows it holds (its header too)
if there is not None and if_there == "stop":
    raise ValueError(f"{path} has a sheet {sheet!r} already: set if_there to replace or add.")
adding = there is not None and if_there == "add"
w.would(
    f"{'add to' if adding else 'write'} the sheet {sheet!r} of {w.path}" + ("" if adding else ", its column names on top"),
    written=w.rows.count,
)
if not dry_run:
    w.done(written=w.sheet(sheet, add=adding))
w
"""
