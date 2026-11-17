# /// swissarmybench-blade
# format = 1
# name = "Trino create table"
# kind = "snippet"
# description = "A new Trino table from the rows (dry run first; writes on the user's word)"
# tags = ["write", "trino"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Trino create table: a new table in Trino (or Presto) made from the rows, its types from DuckDB's.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Trino has no transactions on most connectors: each statement stands by itself, and a failure says
# which batch failed and how many rows were written before it.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
# Trino makes the table at once (CREATE TABLE commits by itself): if the rows then
# fail, the table is dropped again.
import duckdb  # the rows are staged in DuckDB
import trino  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: iceberg.sales.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 200

w = SqlWrite(connection, target, "create", rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
w.check_new()  # the table is not there yet
create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
insert = f"INSERT INTO {w.table} ({w.columns}) VALUES "  # a batch of rows in one statement
w.would(create, insert, inserted=w.rows.count)
if not dry_run:
    with w.transaction():
        w.execute(create)
        w.on_failure(f"DROP TABLE {w.table}")  # undo the CREATE when the rows fail
        inserted = w.each_values(insert)
    w.done(inserted=inserted)
w
"""
