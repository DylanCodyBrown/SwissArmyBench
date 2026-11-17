# /// swissarmybench-blade
# format = 1
# name = "Trino replace"
# kind = "snippet"
# description = "Replace every row of a Trino table (dry run first; writes on the user's word)"
# tags = ["write", "trino"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Trino replace: every row of a table in Trino (or Presto) replaced by the rows.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Trino has no transactions on most connectors: each statement stands by itself, and a failure says
# which batch failed and how many rows were written before it.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
import duckdb  # the rows are staged in DuckDB
import trino  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: iceberg.sales.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 200

w = SqlWrite(connection, target, "replace", rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
w.check_columns()  # every column of the rows is one of the table's
clear = f"DELETE FROM {w.table}"
insert = f"INSERT INTO {w.table} ({w.columns}) VALUES "  # a batch of rows in one statement
w.would(clear, insert, deleted=w.count(), inserted=w.rows.count)
if not dry_run:
    with w.transaction():
        deleted = w.count()
        w.execute(clear)
        inserted = w.each_values(insert)
    w.done(deleted=deleted, inserted=inserted)
w
"""
