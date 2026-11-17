# /// swissarmybench-blade
# format = 1
# name = "SQL Server create table"
# kind = "snippet"
# description = "A new SQL Server or Azure SQL table (dry run first; writes on the user's word)"
# tags = ["write", "sqlserver", "azuresql"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SQL Server create table: a new SQL Server or Azure SQL table made from the rows, its types from DuckDB's.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed. Azure's passing errors
# (40613, 40197, 40501, 49918, 10928, 10929, 4221), a deadlock (1205) and a dropped connection run the
# WHOLE transaction again, on a fresh connection, after 1, 2, 4 seconds: never half of one.
# The target's own types (sys.columns) size every value: varchar stays varchar, a decimal its scale.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
import duckdb  # the rows are staged in DuckDB
import pyodbc  # the connection's driver

from swissarmybench.client.write_sql import SqlServerWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: dbo.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 1000  # fewer for wide rows

w = SqlServerWrite(connection, target, "create", rows, dry_run=dry_run, batch_size=batch_size)
w.check_new()  # the table is not there yet
create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
w.would(create, insert, inserted=w.rows.count)


def write():
    w.execute(create)  # inside the transaction: undone on a failure
    return {"inserted": w.insert()}


if not dry_run:
    w.done(**w.in_transaction(write))
w
"""
