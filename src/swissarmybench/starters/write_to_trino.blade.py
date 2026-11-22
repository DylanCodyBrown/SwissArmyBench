# /// swissarmybench-blade
# format = 1
# name = "Write to Trino"
# kind = "other"
# description = "Write rows to Trino (or Presto) (dry run first; writes on the user's word)"
# tags = ["write", "trino"]
# family = "Write"
# variable = "write_trino"
# ///
"""Trino (or Presto): the rows written to a table, by `mode`: append, create, replace, upsert, delete.

    write_trino = sab.blade("Write to Trino")  # the project's functions.py will hold it
    write_trino("Warehouse", "iceberg.sales.orders", orders, mode="upsert", keys=["order_id"])  # a dry run

Dry run first: dry_run=True (the default) only says what it would do (the target, the rows and their
types, the statements, the counts, 5 rows) and changes nothing; dry_run=False writes. An agent sets
dry_run=False only after the user said to write, in their own words, in this conversation. It signs in
through the connection's own sign-in (sab.connection): no password here. Returns the write's report.

Trino writes row batches without a transaction: a failure part-way leaves the rows already written, and
says which batch failed and how many rows were written before it. So replace is one statement, CREATE OR
REPLACE TABLE ... AS (its columns' types and properties kept, all of its rows or none), on the catalogs that
have it (Iceberg's); a catalog without it (Hive's) refuses it and nothing changes: clear the table first
(sab.write(connection, table, None, "truncate")), then append. An upsert is MERGE, on the connectors that
have it (Iceberg, Delta Lake, Hive transactional tables, some JDBC ones).

Written by the adapter (adapter.write on its Sql source: Trino's own section of adapter.py, a statement a
batch; Plans/adapter.plan.md), the dry run its planned() (counted by reads). Laid out top to bottom: the
modes, then `write_trino`, the one you call: the rows checked against the table, what it would run said,
then written.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import trino  # noqa: F401 (the package this needs: the connection's driver)

from swissarmybench.client.write_sql import SqlWrite
from swissarmybench.client.writes import WriteError

MODES = ("append", "create", "replace", "upsert", "delete")


def write_trino(
    connection: str,
    table: str,
    rows: Any,
    mode: str = "append",
    keys: Sequence[str] = (),
    batch_size: int = 200,
    dry_run: bool = True,
) -> SqlWrite:
    """The rows written to `table` on the connection named `connection`.

    mode: append, create, replace (one statement: Iceberg), upsert, delete. keys: the columns that find a row.
    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
    return w.by_adapter(keys)
