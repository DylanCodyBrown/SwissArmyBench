# /// swissarmybench-blade
# format = 1
# name = "SQLite create table"
# kind = "snippet"
# description = "A new SQLite table from the rows (dry run first; writes on the user's word)"
# tags = ["write", "sqlite"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SQLite create table: a new table in SQLite made from the rows, its types from DuckDB's.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
import duckdb  # the rows are staged in DuckDB
import sqlite3  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 1000

w = SqlWrite(connection, target, "create", rows, dry_run=dry_run, batch_size=batch_size, engine="sqlite")
w.check_new()  # the table is not there yet
create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
w.would(create, insert, inserted=w.rows.count)
if not dry_run:
    with w.transaction():
        w.execute(create)
        inserted = w.each_batch(insert)
    w.done(inserted=inserted)
w
"""
