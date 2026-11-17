# /// swissarmybench-blade
# format = 1
# name = "MySQL append"
# kind = "snippet"
# description = "Add rows to a MySQL table (dry run first)"
# tags = ["write", "mysql", "mariadb"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# MySQL append: the rows added to a table in MySQL or MariaDB.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
import duckdb  # the rows are staged in DuckDB

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: shop.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 1000

w = SqlWrite(connection, target, "append", rows, dry_run=dry_run, batch_size=batch_size, engine="mysql")
w.check_columns()  # every column of the rows is one of the table's
insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
w.would(insert, inserted=w.rows.count)
if not dry_run:
    with w.transaction():
        inserted = w.each_batch(insert)
    w.done(inserted=inserted)
w
"""
