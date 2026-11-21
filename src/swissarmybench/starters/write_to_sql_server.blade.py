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

Laid out top to bottom: one function per mode (append, create, replace, upsert, delete), each checking
the rows, saying what it would do, then writing; `write_sql_server`, the one you call, is last and picks
the mode's function.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import mssql_python  # noqa: F401 (the package this needs: the connection's driver, no ODBC driver)

from swissarmybench.client.write_sql import SqlServerWrite
from swissarmybench.client.writes import WriteError


# append: the rows added to the table as it is.
def _append(w: SqlServerWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # the table's columns: computed ones refused, identity said, triggers said
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"  # executemany as arrays, a batch a round trip
    w.would(insert, inserted=w.need_rows().count)
    if not dry_run:
        w.done(**w.in_transaction(lambda: {"inserted": w.insert()}))


# create: a new table made from the rows' types, then the rows written to it.
def _create(w: SqlServerWrite, keys: list[str], dry_run: bool) -> None:
    w.check_new()  # the table is not there yet
    create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
    w.would(create, insert, inserted=w.need_rows().count)

    def write() -> dict[str, int]:
        w.execute(create)  # inside the transaction: undone on a failure
        return {"inserted": w.insert()}

    if not dry_run:
        w.done(**w.in_transaction(write))


# TRUNCATE is inside the transaction (undone on a failure); it fires no DELETE trigger. Where a foreign
# key points at the table, SQL Server refuses TRUNCATE: write DELETE FROM there instead.
def _replace(w: SqlServerWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # the table's columns: computed ones refused, identity said, triggers said
    clear = f"TRUNCATE TABLE {w.table}"
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
    w.would(clear, insert, deleted=w.count(), inserted=w.need_rows().count)

    def write() -> dict[str, int]:
        deleted = w.count()
        w.execute(clear)
        return {"deleted": deleted, "inserted": w.insert()}

    if not dry_run:
        w.done(**w.in_transaction(write))


# The rows go into a #temp table of the target's own types, then one MERGE ... WITH (HOLDLOCK) writes
# them (where MERGE is refused: UPDATE, then INSERT, in the same transaction).
def _upsert(w: SqlServerWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # the table's columns: computed ones refused, identity said, triggers said
    keys = w.check_keys(keys, unique=True)  # no keys: the primary key; a value in each, one row each
    found = None
    if dry_run:
        w.stage(keys, into="#sab_keys", distinct=True)  # the keys in a #temp table (rolled back)
        found = w.matching(keys)  # one COUNT join: the rows that will update
    w.would(
        "CREATE TABLE #sab_stage (the target's own types), the rows into it by executemany (as arrays)",
        w.merge_sql(keys),
        updated=found,
        inserted=None if found is None else w.need_rows().count - found,
    )

    def write() -> dict[str, int]:
        w.stage()
        return w.merge(keys)

    if not dry_run:
        w.done(**w.in_transaction(write))


# delete: the table's rows that the keys find are deleted.
def _delete(w: SqlServerWrite, keys: list[str], dry_run: bool) -> None:
    keys = w.check_keys(keys, unique=False)  # no keys: the primary key; a value in each
    w.check_columns(keys)  # the key columns are the table's
    found = None
    if dry_run:
        w.stage(keys, into="#sab_keys", distinct=True)  # the keys in a #temp table (rolled back)
        found = w.matching(keys)  # one COUNT join: the rows that will go
    delete = f"DELETE t FROM {w.table} AS t JOIN #sab_keys AS s ON {w.joined(keys)}"
    w.would(delete, deleted=found)

    def write() -> dict[str, int]:
        w.stage(keys, into="#sab_keys", distinct=True)
        return {"deleted": w.delete_staged(keys)}

    if not dry_run:
        w.done(**w.in_transaction(write))


_MODES = {"append": _append, "create": _create, "replace": _replace, "upsert": _upsert, "delete": _delete}


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
    if mode not in _MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlServerWrite(
        connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, identity_insert=identity_insert
    )
    _MODES[mode](w, [k for k in keys if k], dry_run)
    return w
