# /// swissarmybench-blade
# format = 1
# name = "Write CSV file"
# kind = "snippet"
# description = "The rows written to a CSV file (dry run first; writes on the user's word)"
# tags = ["write", "files", "csv", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# CSV file: the rows written to a CSV file.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
# Or one line for any connection: sab.write(connection, table, rows, mode, key) (the adapter's same write).
write_csv = sab.blade("Write to CSV")  # until the project's functions.py holds write_csv

write_csv(
    "<<file: C:/exports/orders.csv>>",
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    # A file connection instead (a folder): path = sab.connection("Exports") / "orders.csv"
    delimiter=",",
    overwrite=False,  # True: an existing file is replaced
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
