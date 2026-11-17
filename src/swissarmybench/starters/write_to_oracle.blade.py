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
"""

from collections.abc import Sequence
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)
import oracledb  # noqa: F401 (the package this needs: the connection's driver)

from swissarmybench.client.write_sql import SqlWrite
from swissarmybench.client.writes import WriteError


def _append(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
    w.would(insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            inserted = w.each_batch(insert)
        w.done(inserted=inserted)


# Oracle makes the table at once (CREATE TABLE commits by itself): if the rows then
# fail, the table is dropped again.
def _create(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_new()  # the table is not there yet
    create = f"CREATE TABLE {w.table} (\n{w.column_types()}\n)"
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
    w.would(create, insert, inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            w.execute(create)
            w.on_failure(f"DROP TABLE {w.table}")  # undo the CREATE when the rows fail
            inserted = w.each_batch(insert)
        w.done(inserted=inserted)


def _replace(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    clear = f"DELETE FROM {w.table}"  # not TRUNCATE: Oracle's TRUNCATE commits by itself
    insert = f"INSERT INTO {w.table} ({w.columns}) VALUES ({w.marks()})"
    w.would(clear, insert, deleted=w.count(), inserted=w.need_rows().count)
    if not dry_run:
        with w.transaction():
            deleted = w.count()
            w.execute(clear)
            inserted = w.each_batch(insert)
        w.done(deleted=deleted, inserted=inserted)


# MERGE INTO ... USING (SELECT ... FROM dual), a row at a time in batches: no unique index is needed.
def _upsert(w: SqlWrite, keys: list[str], dry_run: bool) -> None:
    w.check_columns()  # every column of the rows is one of the table's
    w.check_keys(keys, unique=True)  # a value in each, and no two rows share one
    others = [c for c in w.need_rows().names if c not in keys]
    upsert = (
        f"MERGE INTO {w.table} t\n"
        "USING (SELECT "
        + ", ".join(f"{w.mark(i)} AS {w.name(c)}" for i, c in enumerate(w.need_rows().names))
        + " FROM dual) s\n"
        "ON ("
        + " AND ".join(f"t.{w.name(k)} = s.{w.name(k)}" for k in keys)
        + ")\n"
        + (
            "WHEN MATCHED THEN UPDATE SET "
            + ", ".join(f"t.{w.name(c)} = s.{w.name(c)}" for c in others)
            + "\n"
            if others
            else ""
        )
        + f"WHEN NOT MATCHED THEN INSERT ({w.columns}) VALUES ("
        + ", ".join(f"s.{w.name(c)}" for c in w.need_rows().names)
        + ")"
    )
    found = w.found(keys) if dry_run else None  # the table's rows the keys find
    w.would(upsert, updated=found, inserted=None if found is None else w.need_rows().count - found)
    if not dry_run:
        with w.transaction():
            before = w.count()
            w.each_batch(upsert)
            inserted = w.count() - before
        w.done(inserted=inserted, updated=w.need_rows().count - inserted)


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
    if mode not in _MODES:
        raise WriteError(f"mode is one of append, create, replace, upsert, delete, not {mode!r}.")
    w = SqlWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size, engine="oracle")
    _MODES[mode](w, [k for k in keys if k], dry_run)
    return w
