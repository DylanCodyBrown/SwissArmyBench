# /// swissarmybench-blade
# format = 1
# name = "Write to a SharePoint list"
# kind = "other"
# description = "Write rows to a SharePoint list (dry run first; writes on the user's word)"
# tags = ["write", "sharepoint"]
# family = "Write"
# variable = "write_sharepoint_list"
# ///
"""A SharePoint list of a SharePoint lists connection, by `mode`: create (each row a new item), update
(items found by their id or a key column), delete (items by their id or a key column).

    write_sharepoint_list = sab.blade("Write to a SharePoint list")  # the project's functions.py will hold it
    write_sharepoint_list("Team", "Tasks", tasks, mode="update", key="Title")  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing (the keys are
looked up); dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their
own words, in this conversation. It signs in through the connection's own sign-in (sab.connection: its
own way to sign in): no secret here. Returns the write's report.

Microsoft Graph's $batch, 20 changes a request; a throttled one (429) waits as Graph asks, then goes again.
A lookup or a person is written by its id: a column <name>_id. A failure says how many were refused (the
changes before it stay made: SharePoint has no transaction).
"""

from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.client.writes import Write, WriteError, live

MODES = ("create", "update", "delete")


def _arrow(given: Any) -> Any:
    """The staged rows as an Arrow table (DuckDB 2's to_arrow_table, 1's fetch_arrow_table)."""
    found = given.db.sql("FROM sab_rows")
    return (getattr(found, "to_arrow_table", None) or found.fetch_arrow_table)()


def write_sharepoint_list(
    connection: str,
    list_name: str,
    rows: Any,
    mode: str = "create",
    key: str = "id",
    dry_run: bool = True,
) -> Write:
    """The rows written to the list `list_name` (its display name or id) of the SharePoint lists
    connection named `connection`.

    mode: create, update, delete. key: the column that finds each item (update, delete): id, or a column
    whose values are one item each. rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of {', '.join(MODES)}, not {mode!r}.")
    name, conn = live(connection)
    if not hasattr(conn, "create") or not hasattr(conn, "ids"):
        raise WriteError(f"{name} is not a SharePoint lists connection.")
    w = Write(name, list_name, mode, rows, dry_run=dry_run)
    given = w.need_rows()
    records = _arrow(given).to_pylist()
    batches = (len(records) + 19) // 20
    if mode == "create":
        w.would(f"POST {list_name} items, {batches:,} $batch requests", inserted=len(records))
        if not dry_run:
            w.done(inserted=conn.create(list_name, records)["done"])
        return w
    if key not in given.names:
        raise WriteError(f"The rows have no {key} column: it finds each item.")
    given.check_keys([key], unique=True)
    found = conn.ids(list_name, [r[key] for r in records], key)  # every key one item, or it says which
    if mode == "update":
        w.would(
            f"PATCH {list_name} items/<id>/fields by {key}, {batches:,} $batch requests", updated=len(found)
        )
        if not dry_run:
            w.done(updated=conn.update(list_name, records, key)["done"])
    else:
        w.would(f"DELETE {list_name} items/<id> by {key}, {batches:,} $batch requests", deleted=len(found))
        if not dry_run:
            w.done(deleted=conn.delete(list_name, [found[r[key]] for r in records])["done"])
    return w
