# /// swissarmybench-blade
# format = 1
# name = "ODBC append"
# kind = "snippet"
# description = "Add rows to an ODBC table (dry run first; writes on the user's word)"
# tags = ["write", "odbc"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# ODBC append: the rows added to a table in any ODBC source.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_odbc = sab.blade("Write to ODBC")  # until the project's functions.py holds write_odbc

write_odbc(
    "<<connection>>",  # its name in the Connections page
    "<<target: orders>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="append",
    batch_size=1000,
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
