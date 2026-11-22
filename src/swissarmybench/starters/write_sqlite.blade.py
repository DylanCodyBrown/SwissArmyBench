# /// swissarmybench-blade
# format = 1
# name = "SQLite write"
# kind = "snippet"
# description = "Write rows to SQLite by mode (dry run first; writes on the user's word)"
# tags = ["write", "sqlite"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SQLite write: the rows written as `mode` says (one of these):
#   append    the rows added to a table in SQLite.
#   create    a new table in SQLite made from the rows, its types from DuckDB's.
#   replace   every row of a table in SQLite replaced by the rows.
#   upsert    the rows inserted into a table in SQLite, or updated where a key matches.
#   delete    a table's rows in SQLite deleted where their keys are the rows' keys.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
# Or one line for any connection: sab.write(connection, table, rows, mode, key) (the adapter's same write).
write_sqlite = sab.blade("Write to SQLite")  # until the project's functions.py holds write_sqlite

write_sqlite(
    "<<connection>>",  # its name in the Connections page
    "<<target: orders>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="<<mode: append>>",  # append, create, replace, upsert or delete
    keys=["<<key column>>"],  # upsert and delete: the columns that find a row: ["region", "order_id"] for two
    batch_size=1000,
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
