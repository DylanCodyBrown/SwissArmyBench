# /// swissarmybench-blade
# format = 1
# name = "Write to Oracle"
# kind = "other"
# description = "Write rows to Oracle (dry run first; writes on the user's word)"
# tags = ["write", "oracle"]
# family = "Write"
# variable = "write_oracle"
# ///
"""Oracle: the rows written to a table, by `mode`: append, create, replace, upsert, delete.

    write_oracle = sab.blade("Write to Oracle")  # the project's functions.py will hold it
    write_oracle("Warehouse", "SALES.ORDERS", orders, mode="upsert", keys=["order_id"])  # a dry run

Dry run first: dry_run=True (the default) only says what it would do (the target, the rows and their
types, the statements, the counts, 5 rows) and changes nothing; dry_run=False writes. An agent sets
dry_run=False only after the user said to write, in their own words, in this conversation. It signs in
through the connection's own sign-in (sab.connection): no password here. Returns the write's report.

One transaction: a failure rolls every row back and says which batch failed.

Written by the adapter (adapter.write on its Sql source: its own INSERT, UPDATE and DELETE in one
transaction; an upsert updates the rows whose keys are there and inserts the others; Plans/adapter.plan.md),
the dry run its planned() (counted by reads). Laid out top to bottom: the modes, then `write_oracle`, the one you
call: the rows checked against the table, what it would run said, then written.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import oracledb  # noqa: F401 (the package this needs: the connection's driver)

from swissarmybench.client.write_sql import SqlWrite
from swissarmybench.client.writes import WriteError

MODES = ("append", "create", "replace", "upsert", "delete")


def write_oracle(
    connection: str,
    table: str,
    rows: Any,
    mode: str = "append",
    keys: Sequence[str] = (),
    batch_size: int = 1000,
    dry_run: bool = True,
) -> SqlWrite:
    """The rows written to `table` on the connection named `connection`.

    mode: append, create, replace, upsert, delete. keys: the columns that find a row (upsert, delete).
    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, engine="oracle")
    return w.by_adapter(keys)
