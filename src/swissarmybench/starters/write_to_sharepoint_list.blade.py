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
(items found by their id or a key column), delete (items by their id or a key column), truncate (every item
deleted, then the rows made).

    write_sharepoint_list = sab.blade("Write to a SharePoint list")  # the project's functions.py will hold it
    write_sharepoint_list("Team", "Tasks", tasks, mode="update", key="Title")  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing (the keys are
looked up); dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their
own words, in this conversation. It signs in through the connection's own sign-in (sab.connection: its
own way to sign in): no secret here. Returns the write's report.

The write is the adapter's (adapter.write on the connection, Plans/adapter.plan.md), by the
connection's own calls: Microsoft Graph's $batch, 20 changes a request; a throttled one (429) waits as Graph
asks, then goes again. A lookup or a person is written by its id: a column <name>_id. A failure says how
many were refused (the changes before it stay made: SharePoint has no transaction).
"""

from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.adapters import adapter
from swissarmybench.client.writes import Write, WriteError, by_adapter, live

MODES = {"create": "insert", "update": "update", "delete": "delete", "truncate": "truncate"}
_SAID = {
    "create": "POST {list} items, in $batch requests of 20",
    "update": "PATCH {list} items/<id>/fields by {key}, in $batch requests of 20",
    "delete": "DELETE {list} items/<id> by {key}, in $batch requests of 20",
    "truncate": "DELETE every item of {list}, then POST the rows, in $batch requests of 20",
}


def write_sharepoint_list(
    connection: str,
    list_name: str,
    rows: Any = None,
    mode: str = "create",
    key: str = "id",
    dry_run: bool = True,
) -> Write:
    """The rows written to the list `list_name` (its display name or id) of the SharePoint lists
    connection named `connection`.

    mode: create, update, delete, truncate. key: the column that finds each item (update, delete): id, or a
    column whose values are one item each. rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of {', '.join(MODES)}, not {mode!r}.")
    name, conn = live(connection)
    if not hasattr(conn, "create") or not hasattr(conn, "ids"):
        raise WriteError(f"{name} is not a SharePoint lists connection.")
    w = Write(name, list_name, mode, rows, dry_run=dry_run)
    keyed = MODES[mode] in ("update", "delete")
    if keyed and key not in w.need_rows().names:
        raise WriteError(f"The rows have no {key} column: it finds each item.")
    said = _SAID[mode].format(list=list_name, key=key)
    source = adapter.Rows(conn, name)
    return by_adapter(w, source, list_name, MODES[mode], [key] if keyed else [], said=said)
