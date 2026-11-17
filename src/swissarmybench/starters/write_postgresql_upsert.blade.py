# /// swissarmybench-blade
# format = 1
# name = "PostgreSQL upsert"
# kind = "snippet"
# description = "Upsert PostgreSQL rows by key (dry run first; writes on the user's word)"
# tags = ["write", "postgres"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# PostgreSQL upsert: the rows inserted into a table in PostgreSQL, or updated where a key matches.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
# Needs a primary key or a unique index on exactly the key columns: ON CONFLICT names it.
import duckdb  # the rows are staged in DuckDB
import psycopg  # the connection's driver

from swissarmybench.client.write_sql import SqlWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: public.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
keys = ["<<key column>>"]  # the columns that find a row: ["region", "order_id"] for two
batch_size = 1000

w = SqlWrite(connection, target, "upsert", rows, dry_run=dry_run, batch_size=batch_size, engine="postgres")
w.check_columns()  # every column of the rows is one of the table's
w.check_keys(keys, unique=True)  # a value in each, and no two rows share one
others = [c for c in w.rows.names if c not in keys]
upsert = (
    f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})\n"
    f"ON CONFLICT ({w.names(keys)}) DO "
    + ("UPDATE SET " + ", ".join(f"{w.name(c)} = EXCLUDED.{w.name(c)}" for c in others) if others else "NOTHING")
)
found = w.found(keys) if dry_run else None  # the table's rows the keys find
w.would(upsert, updated=found, inserted=None if found is None else w.rows.count - found)
if not dry_run:
    with w.transaction():
        before = w.count()
        w.each_batch(upsert)
        inserted = w.count() - before
    w.done(inserted=inserted, updated=w.rows.count - inserted)
w
"""
