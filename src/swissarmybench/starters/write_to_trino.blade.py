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

Trino has no transactions on most connectors: each statement stands by itself, and a failure says
which batch failed and how many rows were written before it.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import trino  # noqa: F401 (the package this needs: the connection's driver)

from swissarmybench.client.write_sql import SqlWrite
from swissarmybench.client.writes import WriteError


def _append(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES "  # a batch of rows in one statement
    w.would(insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            inserted = w.each_values(insert)
        w.done(inserted=inserted)


# Trino makes the table at once (CREATE TABLE commits by itself): if the rows then
# fail, the table is dropped again.
def _create(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_new()  # the table is not there yet
    create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES "  # a batch of rows in one statement
    w.would(create, insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            w.execute(create)
            w.on_failure(f"DROP TABLE {w.table}")  # undo the CREATE when the rows fail
            inserted = w.each_values(insert)
        w.done(inserted=inserted)


def _replace(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    clear = f"DELETE FROM {w.table}"
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES "  # a batch of rows in one statement
    w.would(clear, insert, deleted=w.count(), inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            deleted = w.count()
            w.execute(clear)
            inserted = w.each_values(insert)
        w.done(deleted=deleted, inserted=inserted)


# MERGE works on the connectors that have it (Iceberg, Delta Lake, Hive transactional tables, some
# JDBC ones); on the others Trino refuses and the cell says so.
def _upsert(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    w.check_keys(keys, unique=True)  # a value in each, and no two rows share one
    others = [c for c in w.need_rows().names if c not in keys]
    merge = f"MERGE INTO {w.table} AS t USING (VALUES "  # a batch of rows in one statement
    merge_end = (
        f") AS s ({w.columns})\n"
        "ON "
        + " AND ".join(f"t.{w.name(k)} = s.{w.name(k)}" for k in keys)
        + "\n"
        + (
            "WHEN MATCHED THEN UPDATE SET " + ", ".join(f"{w.name(c)} = s.{w.name(c)}" for c in others) + "\n"
            if others
            else ""
        )
        + f"WHEN NOT MATCHED THEN INSERT ({w.columns}) VALUES ("
        + ", ".join(f"s.{w.name(c)}" for c in w.need_rows().names)
        + ")"
    )
    upsert = merge + "(...)" + merge_end
    found = w.found(keys) if dry_run else None  # the table's rows the keys find
    w.would(upsert, updated=found, inserted=None if found is None else w.need_rows().count - found)
    if not dry_run:
        with w.transaction():
            before = w.count()
            w.each_values(merge, merge_end)
            inserted = w.count() - before
        w.done(inserted=inserted, updated=w.need_rows().count - inserted)


def _delete(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
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


_MODES = {"append": _append, "create": _create, "replace": _replace, "upsert": _upsert, "delete": _delete}


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

    mode: append, create, replace, upsert, delete. keys: the columns that find a row (upsert, delete).
    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in _MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, engine="trino")
    _MODES[mode](w, [k for k in keys if k], dry_run)
    return w
