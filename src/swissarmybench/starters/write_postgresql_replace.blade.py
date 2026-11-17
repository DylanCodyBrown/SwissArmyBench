# /// swissarmybench-blade
# format = 1
# name = "PostgreSQL replace"
# kind = "snippet"
# description = "Replace every row of a PostgreSQL table (dry run first; writes on the user's word)"
# tags = ["write", "postgres"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# PostgreSQL replace: every row of a table in PostgreSQL replaced by the rows.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
import duckdb  # the rows are staged in DuckDB
import psycopg  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: public.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 1000

w = SqlWrite(connection, target, "replace", rows, dry_run=dry_run, batch_size=batch_size, engine="postgres")
w.check_columns()  # every column of the rows is one of the table's
clear = f"TRUNCATE TABLE {w.table}"  # inside the transaction: undone on a failure
insert = f"COPY {w.table} ({w.columns}) FROM STDIN"  # COPY: the fastest way in
w.would(clear, insert, deleted=w.count(), inserted=w.rows.count)
if not dry_run:
    with w.transaction():
        deleted = w.count()
        w.execute(clear)
        inserted = w.copy(insert)
    w.done(deleted=deleted, inserted=inserted)
w
"""
