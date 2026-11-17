# /// swissarmybench-blade
# format = 1
# name = "Trino upsert"
# kind = "snippet"
# description = "Insert rows into a Trino table, or update them by key (dry run first)"
# tags = ["write", "trino"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Trino upsert: the rows inserted into a table in Trino (or Presto), or updated where a key matches.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Trino has no transactions on most connectors: each statement stands by itself, and a failure says
# which batch failed and how many rows were written before it.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
# MERGE works on the connectors that have it (Iceberg, Delta Lake, Hive transactional tables, some
# JDBC ones); on the others Trino refuses and the cell says so.
import duckdb  # the rows are staged in DuckDB
import trino  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: iceberg.sales.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
keys = ["<<key column>>"]  # the columns that find a row: ["region", "order_id"] for two
batch_size = 200

w = SqlWrite(connection, target, "upsert", rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
w.check_columns()  # every column of the rows is one of the table's
w.check_keys(keys, unique=True)  # a value in each, and no two rows share one
others = [c for c in w.rows.names if c not in keys]
merge = f"MERGE INTO {w.table} AS t USING (VALUES "  # a batch of rows in one statement
merge_end = (
    f") AS s ({w.columns})\n"
    "ON " + " AND ".join(f"t.{w.name(k)} = s.{w.name(k)}" for k in keys) + "\n"
    + ("WHEN MATCHED THEN UPDATE SET " + ", ".join(f"{w.name(c)} = s.{w.name(c)}" for c in others) + "\n" if others else "")
    + f"WHEN NOT MATCHED THEN INSERT ({w.columns}) VALUES ("
    + ", ".join(f"s.{w.name(c)}" for c in w.rows.names) + ")"
)
upsert = merge + "(...)" + merge_end
found = w.found(keys) if dry_run else None  # the table's rows the keys find
w.would(upsert, updated=found, inserted=None if found is None else w.rows.count - found)
if not dry_run:
    with w.transaction():
        before = w.count()
        w.each_values(merge, merge_end)
        inserted = w.count() - before
    w.done(inserted=inserted, updated=w.rows.count - inserted)
w
"""
