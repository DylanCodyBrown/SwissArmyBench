# /// swissarmybench-blade
# format = 1
# name = "Write to PostgreSQL"
# kind = "other"
# description = "Write rows to PostgreSQL (dry run first; writes on the user's word)"
# tags = ["write", "postgres"]
# family = "Write"
# variable = "write_postgresql"
# ///
"""PostgreSQL: the rows written to a table, by `mode`: append, create, replace, upsert, delete.

    write_postgresql = sab.blade("Write to PostgreSQL")  # the project's functions.py will hold it
    write_postgresql("Warehouse", "public.orders", orders, mode="upsert", keys=["order_id"])  # a dry run

Dry run first: dry_run=True (the default) only says what it would do (the target, the rows and their
types, the statements, the counts, 5 rows) and changes nothing; dry_run=False writes. An agent sets
dry_run=False only after the user said to write, in their own words, in this conversation. It signs in
through the connection's own sign-in (sab.connection): no password here. Returns the write's report.

One transaction: a failure rolls every row back and says which batch failed.

Laid out top to bottom: one function per mode (append, create, replace, upsert, delete), each checking
the rows, saying what it would do, then writing; `write_postgresql`, the one you call, is last and picks
the mode's function.
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import psycopg  # noqa: F401 (the package this needs: the connection's driver)

from swissarmybench.client.write_sql import SqlWrite
from swissarmybench.client.writes import WriteError


# append: the rows added to the table as it is.
def _append(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    insert = f"COPY {w.table} ({w.columns}) FROM STDIN"  # COPY: the fastest way in
    w.would(insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            inserted = w.copy(insert)
        w.done(inserted=inserted)


# create: a new table made from the rows' types, then the rows written to it.
def _create(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_new()  # the table is not there yet
    create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
    insert = f"COPY {w.table} ({w.columns}) FROM STDIN"  # COPY: the fastest way in
    w.would(create, insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            w.execute(create)
            inserted = w.copy(insert)
        w.done(inserted=inserted)


# replace: the table emptied and the rows written, in one transaction.
def _replace(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    clear = f"TRUNCATE TABLE {w.table}"  # inside the transaction: undone on a failure
    insert = f"COPY {w.table} ({w.columns}) FROM STDIN"  # COPY: the fastest way in
    w.would(clear, insert, deleted=w.count(), inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            deleted = w.count()
            w.execute(clear)
            inserted = w.copy(insert)
        w.done(deleted=deleted, inserted=inserted)


# Needs a primary key or a unique index on exactly the key columns: ON CONFLICT names it.
def _upsert(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    w.check_keys(keys, unique=True)  # a value in each, and no two rows share one
    others = [c for c in w.need_rows().names if c not in keys]
    upsert = (
        f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})\n"
        f"ON CONFLICT ({w.names(keys)}) DO "
        + (
            "UPDATE SET " + ", ".join(f"{w.name(c)} = EXCLUDED.{w.name(c)}" for c in others)
            if others
            else "NOTHING"
        )
    )
    found = w.found(keys) if dry_run else None  # the table's rows the keys find
    w.would(upsert, updated=found, inserted=None if found is None else w.need_rows().count - found)
    if not dry_run:
        with w.transaction():
            before = w.count()
            w.each_batch(upsert)
            inserted = w.count() - before
        w.done(inserted=inserted, updated=w.need_rows().count - inserted)


# delete: the table's rows that the keys find are deleted.
def _delete(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns(keys)  # the key columns are the table's
    w.check_keys(keys, unique=False)  # a value in each
    delete = f"DELETE FROM {w.table} WHERE " + " AND ".join(
        f"{w.name(k)} = {w.mark(i)}" for i, k in enumerate(keys)
    )
    w.would(delete, deleted=w.found(keys) if dry_run else None)
    if not dry_run:
        with w.transaction():
            before = w.count()
            w.each_batch(delete, keys, distinct=True)
            deleted = before - w.count()
        w.done(deleted=deleted)


_MODES = {"append": _append, "create": _create, "replace": _replace, "upsert": _upsert, "delete": _delete}


def write_postgresql(
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
    if mode not in _MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, engine="postgres")
    _MODES[mode](w, [k for k in keys if k], dry_run)
    return w
