# /// swissarmybench-blade
# format = 1
# name = "Trino delete"
# kind = "snippet"
# description = "Delete Trino rows by key (dry run first; writes on the user's word)"
# tags = ["write", "trino"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Trino delete: a table's rows in Trino (or Presto) deleted where their keys are the rows' keys.
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
keys = ["<<key column>>"]  # the columns that find a row: ["region", "order_id"] for two
batch_size = 200

w = SqlWrite(connection, target, "delete", rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
w.check_columns(keys)  # the key columns are the table's
w.check_keys(keys, unique=False)  # a value in each
delete = f"DELETE FROM {w.table} WHERE "  # (k1 = ? AND ...) OR (...): a batch of keys at a time
w.would(delete, deleted=w.found(keys) if dry_run else None)
if not dry_run:
    with w.transaction():
        before = w.count()
        w.each_where(delete, keys)
        deleted = before - w.count()
    w.done(deleted=deleted)
w
"""
