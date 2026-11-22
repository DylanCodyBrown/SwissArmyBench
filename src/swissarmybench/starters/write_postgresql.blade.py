# /// swissarmybench-blade
# format = 1
# name = "PostgreSQL write"
# kind = "snippet"
# description = "Write rows to PostgreSQL by mode (dry run first; writes on the user's word)"
# tags = ["write", "postgres"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# PostgreSQL write: the rows written as `mode` says (one of these):
#   append    the rows added to a table in PostgreSQL (COPY, the fastest way in).
#   create    a new table in PostgreSQL made from the rows, its types from DuckDB's.
#   replace   every row of a table in PostgreSQL replaced by the rows.
#   upsert    the rows inserted into a table in PostgreSQL, or updated where a key matches.
#   delete    a table's rows in PostgreSQL deleted where their keys are the rows' keys.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
# Or one line for any connection: sab.write(connection, table, rows, mode, key) (the adapter's same write).
write_postgresql = sab.blade("Write to PostgreSQL")  # until the project's functions.py holds write_postgresql

write_postgresql(
    "<<connection>>",  # its name in the Connections page
    "<<target: public.orders>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="<<mode: append>>",  # append, create, replace, upsert or delete
    keys=["<<key column>>"],  # upsert and delete: the columns that find a row: ["region", "order_id"] for two
    batch_size=1000,
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
