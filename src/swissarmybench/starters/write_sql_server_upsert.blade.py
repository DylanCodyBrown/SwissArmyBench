# /// swissarmybench-blade
# format = 1
# name = "SQL Server upsert"
# kind = "snippet"
# description = "Upsert SQL Server or Azure SQL rows by key (dry run first; writes on the user's word)"
# tags = ["write", "sqlserver", "azuresql"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SQL Server upsert: the rows inserted into a SQL Server or Azure SQL table, or updated where a key matches.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# One transaction: a failure rolls every row back and says which batch failed. Azure's passing errors
# (40613, 40197, 40501, 49918, 10928, 10929, 4221), a deadlock (1205) and a dropped connection run the
# WHOLE transaction again, on a fresh connection, after 1, 2, 4 seconds: never half of one.
# The target's own types (sys.columns) size every value: varchar stays varchar, a decimal its scale.
# It signs in through the connection's own sign-in (sab.connection): no password in this cell.
# The rows go into a #temp table of the target's own types, then one MERGE ... WITH (HOLDLOCK) writes
# them (where MERGE is refused: UPDATE, then INSERT, in the same transaction).
import duckdb  # the rows are staged in DuckDB
import pyodbc  # the connection's driver

from swissarmybench.client.write_sql import SqlServerWrite

dry_run = True
connection = "<<connection>>"  # its name in the Connections page
target = "<<target: dbo.orders>>"  # the table written to
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
keys = ["<<key column>>"]  # the columns that find a row; [] for the table's primary key
identity_insert = False  # True: the rows' own values go into the identity column
batch_size = 1000  # fewer for wide rows

w = SqlServerWrite(connection, target, "upsert", rows, dry_run=dry_run, batch_size=batch_size, identity_insert=identity_insert)
w.check_columns()  # the table's columns: computed ones refused, identity said, triggers said
keys = w.check_keys(keys, unique=True)  # no keys: the primary key; a value in each, one row each
found = None
if dry_run:
    w.stage(keys, into="#sab_keys", distinct=True)  # the keys in a #temp table (rolled back)
    found = w.matching(keys)  # one COUNT join: the rows that will update
w.would(
    "CREATE TABLE #sab_stage (the target's own types), the rows into it by fast_executemany",
    w.merge_sql(keys),
    updated=found,
    inserted=None if found is None else w.rows.count - found,
)


def write():
    w.stage()
    return w.merge(keys)


if not dry_run:
    w.done(**w.in_transaction(write))
w
"""
