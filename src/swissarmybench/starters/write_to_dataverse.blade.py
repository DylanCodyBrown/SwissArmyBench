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
`mode`: create, update, upsert, delete, truncate.

    write_dataverse = sab.blade("Write to Dataverse")  # the project's functions.py will hold it
    write_dataverse("CRM", "account", accounts, mode="upsert", key="accountnumber")  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing (its counts are
read from the table as it is); dry_run=False writes. An agent sets dry_run=False only after the user said
to write, in their own words, in this conversation. It signs in through the connection's own sign-in
(sab.connection): no secret here. Returns the write's report.

The write is the adapter's (adapter.write on the connection, Plans/adapter.plan.md): each batch is one
$batch change set, all of its rows or none (a failure names the batch; the batches before it stay
written); a throttled request (429) waits as Dataverse asks, then goes again; a choice column takes its
labels (Won, not 1); a lookup is a column named <column>@odata.bind. truncate deletes every record, then
makes the rows.
"""

from typing import Any

from swissarmybench.adapters import adapter
from swissarmybench.client.writes import Write, WriteError, by_adapter, live

# The starter's words for each mode, and the adapter's mode it is.
_MODES = {
    "create": "insert",
    "update": "update",
    "upsert": "merge",
    "delete": "delete",
    "truncate": "truncate",
}
_SAID = {
    "create": "POST {set}: one record a row, in $batch change sets",
    "update": "PATCH {set}(<key>) with If-Match: * (update only), in $batch change sets",
    "upsert": "PATCH {set}(<key>) (Dataverse makes the record when it is not there), in $batch change sets",
    "delete": "DELETE {set}(<key>) of the keys that are records, in $batch change sets",
    "truncate": "DELETE every record of {set}, then POST the rows, in $batch change sets",
}


def write_dataverse(
    connection: str,
    table: str,
    rows: Any = None,
    mode: str = "create",
    key: str = "",
    batch_size: int = 1000,
    dry_run: bool = True,
) -> Write:
    """The rows written to `table` (its logical name, entity set or display name) on the Dataverse
    connection named `connection`.

    mode: create, update, upsert, delete, truncate. key: the column that finds each record (update, upsert,
    delete): its id (accountid) or an alternate key's column. rows: a DataFrame (pandas, polars, Arrow) or a
    DuckDB relation (truncate with none only clears the table).
    """
    if mode not in _MODES:
        raise WriteError(f"mode is one of {', '.join(_MODES)}, not {mode!r}.")
    name, conn = live(connection)
    if not (hasattr(conn, "api") and hasattr(conn, "access_token") and hasattr(conn, "described")):
        raise WriteError(f"{name} is not a Dataverse connection: these starters write to Dataverse.")
    try:
        found = conn.table(table)
    except RuntimeError as error:  # the connection's own DataverseError, in plain words
        raise WriteError(str(error)) from None
    w = Write(name, table, mode, rows, dry_run=dry_run)
    w.fact("Table", f"{found['table']} (the Web API's {found['set']})")
    kinds = {str(c["name"]).lower(): str(c["type"]) for c in conn.described(found["table"])}
    named = [] if w.rows is None else w.rows.names
    choices = [n for n in named if kinds.get(n.lower()) in adapter.DV_CHOICES]
    if choices:
        w.fact("Choices", f"{', '.join(choices)}: labels sent as their numbers")
    keys = [key] if key and _MODES[mode] in ("update", "merge", "delete") else []
    if keys:
        w.fact("Key", key)
    source = adapter.OData(conn, name, batch_size=batch_size)
    return by_adapter(w, source, table, _MODES[mode], keys, said=_SAID[mode].format(set=found["set"]))
