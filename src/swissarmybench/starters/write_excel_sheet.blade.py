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
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
# Or one line for any connection: sab.write(connection, table, rows, mode, key) (the adapter's same write).
write_excel_sheet = sab.blade("Write to an Excel sheet")  # until the project's functions.py holds write_excel_sheet

write_excel_sheet(
    "<<file: C:/reports/orders.xlsx>>",
    "<<sheet: Orders>>",
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    if_there="stop",  # when the sheet is there: "stop", or "replace" its cells, or "add" the rows below its own
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
