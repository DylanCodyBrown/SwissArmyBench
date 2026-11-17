# /// swissarmybench-blade
# format = 1
# name = "MySQL delete"
# kind = "snippet"
# description = "Delete MySQL rows by key (dry run first; writes on the user's word)"
# tags = ["write", "mysql", "mariadb"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# MySQL delete: a table's rows in MySQL or MariaDB deleted where their keys are the rows' keys.
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
keys = ["<<key column>>"]  # the columns that find a row: ["region", "order_id"] for two
batch_size = 1000

w = SqlWrite(connection, target, "delete", rows, dry_run=dry_run, batch_size=batch_size, engine="mysql")
w.check_columns(keys)  # the key columns are the table's
w.check_keys(keys, unique=False)  # a value in each
delete = f"DELETE FROM {w.table} WHERE " + " AND ".join(f"{w.name(k)} = {w.mark(i)}" for i, k in enumerate(keys))
w.would(delete, deleted=w.found(keys) if dry_run else None)
if not dry_run:
    with w.transaction():
        before = w.count()
        w.each_batch(delete, keys, distinct=True)
        deleted = before - w.count()
    w.done(deleted=deleted)
w
"""
