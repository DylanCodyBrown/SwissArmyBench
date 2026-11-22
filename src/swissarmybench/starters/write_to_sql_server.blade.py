# /// swissarmybench-blade
# format = 1
# name = "Write to SQL Server"
# kind = "other"
# description = "Write rows to SQL Server or Azure SQL (dry run first; writes on the user's word)"
# tags = ["write", "azuresql", "sqlserver"]
# family = "Write"
# variable = "write_sql_server"
# ///
"""SQL Server or Azure SQL: the rows written to a table, by `mode`: append, create, replace, upsert, delete.

    write_sql_server = sab.blade("Write to SQL Server")  # the project's functions.py will hold it
    write_sql_server("Warehouse", "dbo.orders", orders, mode="upsert", keys=["order_id"])  # a dry run

Dry run first: dry_run=True (the default) only says what it would do (the target, the rows and their
types, the statements, the counts, 5 rows) and changes nothing; dry_run=False writes. An agent sets
dry_run=False only after the user said to write, in their own words, in this conversation. It signs in
through the connection's own sign-in (sab.connection): no password here. Returns the write's report.

One transaction: a failure rolls every row back and says which batch failed. Azure's passing errors
(40613, 40197, 40501, 49918, 10928, 10929, 4221), a deadlock (1205) and a dropped connection run the
WHOLE transaction again, on a fresh connection, after 1, 2, 4 seconds: never half of one.
The target's own types (sys.columns) size every value: varchar stays varchar, a decimal its scale.
An upsert stages the rows in a #temp table of those types, then one MERGE ... WITH (HOLDLOCK).

Written by the adapter (adapter.write on its Sql source: SQL Server's own section of adapter.py;
Plans/adapter.plan.md), the dry run its planned() (the keys staged and counted by one join, rolled back).
Laid out top to bottom: the modes, then `write_sql_server`, the one you call: the rows checked against the
table (its columns, computed and identity columns, its triggers, the keys: none given, its primary key),
what it would run said, then written.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import mssql_python  # noqa: F401 (the package this needs: the connection's driver, no ODBC driver)

from swissarmybench.client.write_sql import SqlServerWrite
from swissarmybench.client.writes import WriteError

MODES = ("append", "create", "replace", "upsert", "delete")


def write_sql_server(
    connection: str,
    table: str,
    rows: Any,
    mode: str = "append",
    keys: Sequence[str] = (),
    batch_size: int = 1000,
    identity_insert: bool = False,
    dry_run: bool = True,
) -> SqlServerWrite:
    """The rows written to `table` on the connection named `connection`.

    mode: append, create, replace, upsert, delete. keys: the columns that find a row (upsert, delete); none: the primary key.
    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlServerWrite(
        connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, identity_insert=identity_insert
    )
    return w.by_adapter(keys)
