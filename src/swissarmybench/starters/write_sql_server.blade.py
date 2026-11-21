# /// swissarmybench-blade
# format = 1
# name = "SQL Server write"
# kind = "snippet"
# description = "Write rows to SQL Server by mode (dry run first; writes on the user's word)"
# tags = ["write", "sqlserver", "azuresql"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SQL Server write: the rows written as `mode` says (one of these):
#   append    the rows added to a SQL Server or Azure SQL table (fast_executemany, the target's own sizes).
#   create    a new SQL Server or Azure SQL table made from the rows, its types from DuckDB's.
#   replace   every row of a SQL Server or Azure SQL table replaced by the rows.
#   upsert    the rows inserted into a SQL Server or Azure SQL table, or updated where a key matches.
#   delete    a SQL Server or Azure SQL table's rows deleted where their keys are the rows' keys.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_sql_server = sab.blade("Write to SQL Server")  # until the project's functions.py holds write_sql_server

write_sql_server(
    "<<connection>>",  # its name in the Connections page
    "<<target: dbo.orders>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="<<mode: append>>",  # append, create, replace, upsert or delete
    keys=["<<key column>>"],  # upsert and delete: the columns that find a row; [] for the table's primary key
    identity_insert=False,  # append, replace and upsert: True: the rows' own values go into the identity column
    batch_size=1000,  # fewer for wide rows
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
