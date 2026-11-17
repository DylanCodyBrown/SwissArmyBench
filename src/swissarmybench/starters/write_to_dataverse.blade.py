# /// swissarmybench-blade
# format = 1
# name = "Write to Dataverse"
# kind = "other"
# description = "Write rows to Dataverse (dry run first; writes on the user's word)"
# tags = ["write", "dataverse"]
# family = "Write"
# variable = "write_dataverse"
# ///
"""Dataverse: the rows written to a table through the Web API (its SQL endpoint is read-only), by
`mode`: create, update, upsert, delete.

    write_dataverse = sab.blade("Write to Dataverse")  # the project's functions.py will hold it
    write_dataverse("CRM", "account", accounts, mode="upsert", key="accountnumber")  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing;
dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their own
words, in this conversation. It signs in through the connection's own sign-in (sab.connection): no
secret here. Returns the write's report.

Each batch is one $batch change set: all of its rows or none (a failure names the batch; the
batches before it stay written). A throttled request (429) waits as Dataverse asks, then goes again.
A choice column takes its labels (Won, not 1); a lookup is a column named <column>@odata.bind.
"""

from typing import Any

from swissarmybench.client.write_dataverse import DataverseWrite
from swissarmybench.client.writes import WriteError


def _create(w: DataverseWrite, table: str, key: str, dry_run: bool) -> None:
    w.check_columns()  # each column is one of the table's
    w.would(
        f"POST {w.entity_set}: one record a row, in {w.change_sets()} $batch change sets",
        inserted=w.need_rows().count,
    )
    if not dry_run:
        answers = w.send(lambda row: ("POST", w.entity_set, w.body(row, skip_empty=True), {}))
        w.done(inserted=len(answers))


def _update(w: DataverseWrite, table: str, key: str, dry_run: bool) -> None:
    w.check_columns()  # each column is one of the table's
    w.check_key(key)  # a value in each row, one row each
    found = w.existing(key)  # the keys that are records
    missing = [k for k in w.keys_of(key) if k not in found]
    if missing:  # an update only updates: a key that is not a record stops it (the upsert starter makes them)
        raise ValueError(f"{len(missing):,} keys are not records of {table}: {', '.join(missing[:5])}")
    w.would(
        f"PATCH {w.entity_set}(<key>) with If-Match: * (update only), in {w.change_sets()} change sets",
        updated=len(found),
    )
    if not dry_run:
        answers = w.send(
            lambda row: ("PATCH", w.address(key, row), w.body(row, without=[key]), {"If-Match": "*"})
        )
        w.done(updated=len(answers))


def _upsert(w: DataverseWrite, table: str, key: str, dry_run: bool) -> None:
    w.check_columns()  # each column is one of the table's
    w.check_key(key)  # a value in each row, one row each
    found = len(w.existing(key)) if dry_run else None  # the keys that are records already
    w.would(
        f"PATCH {w.entity_set}(<key>) (Dataverse makes the record when it is not there), in {w.change_sets()} change sets",
        updated=found,
        inserted=None if found is None else w.need_rows().count - found,
    )
    if not dry_run:
        prefer = {"Prefer": "return=representation"}  # answered 201 when made, 200 when updated
        answers = w.send(lambda row: ("PATCH", w.address(key, row), w.body(row, without=[key]), prefer))
        w.done(inserted=answers.count(201), updated=answers.count(200))


def _delete(w: DataverseWrite, table: str, key: str, dry_run: bool) -> None:
    w.check_columns([key])  # the key is one of the table's columns
    found = w.existing(key)  # only the keys that are records are deleted
    w.would(f"DELETE {w.entity_set}(<key>), in {w.change_sets()} change sets", deleted=len(found))
    if not dry_run:

        def gone(
            row: dict[str, Any],
        ) -> tuple[str, str, None, dict[str, str]] | None:  # a key that is a record: DELETE it; else nothing
            return ("DELETE", w.address(key, row), None, {}) if str(row[key]).lower() in found else None

        answers = w.send(gone)
        w.done(deleted=len(answers))


_MODES = {"create": _create, "update": _update, "upsert": _upsert, "delete": _delete}


def write_dataverse(
    connection: str,
    table: str,
    rows: Any,
    mode: str = "create",
    key: str = "",
    batch_size: int = 1000,
    dry_run: bool = True,
) -> DataverseWrite:
    """The rows written to `table` (its logical name, entity set or display name) on the Dataverse
    connection named `connection`.

    mode: create, update, upsert, delete. key: the column that finds each record (update, upsert, delete): its id
    (accountid) or an alternate key's column. rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in _MODES:
        raise WriteError(f"mode is one of create, update, upsert, delete, not {mode!r}.")
    w = DataverseWrite(connection, table, mode, rows, dry_run=dry_run, batch_size=batch_size)
    _MODES[mode](w, table, key, dry_run)
    return w
