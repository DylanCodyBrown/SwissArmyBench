"""The agent's tabs_* commands: tab bar: the open tables and the + query tab.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "tabs_new_query",
    "New table from one SELECT over the open tables. "
    "New table from a query (the + tab): one SELECT over the open tables, each read as its tab shows it. "
    "Opens the result in a tab.",
    req("name", "Name of the new dataset."),
    req(
        "sql",
        "One SELECT (DuckDB dialect). Name open datasets as tables. Name a connection's table as [Connection].table ([Connection].dataset.table, .schema.table).",
    ),
    opt("replace", "Rebuild a table an earlier query made (the tab's Run again).", "bool"),
)
def build_from_query(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"sql": a["sql"]}
    if a.get("replace"):
        body["replace"] = True
    return api.call("POST", f"/datasets/{_q(a['name'])}/query", body)


@command(
    "tabs_new_connection_query",
    "New table from a query in a connection's own SQL. "
    "New table from a query run on a connection, in its own SQL. Run again reruns it there.",
    req("name", "Name of the new dataset."),
    req("connection", "The connection the query runs on (a database connection)."),
    req("sql", "One read query in the connection's SQL (DAX on Power BI)."),
    opt("dataset", "The Power BI dataset the DAX runs on."),
    opt("replace", "Rebuild a table this command made (Run again).", "bool"),
)
def build_from_connection_query(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"connection": a["connection"], "sql": a["sql"]}
    if a.get("dataset"):
        body["dataset"] = a["dataset"]
    if a.get("replace"):
        body["replace"] = True
    return api.call("POST", f"/datasets/{_q(a['name'])}/connection-query", body)


@command("tabs_list", "Every open table: id, dataset, step count and URL.")
def list_grids(a: dict[str, Any]) -> Any:
    return api.call("GET", "/grids")


@command("tabs_create_grid", "Open a new tab on a dataset.", req("dataset", "Dataset name."))
def create_grid(a: dict[str, Any]) -> Any:
    result = api.call("POST", "/grids", {"dataset": a["dataset"]})
    return {k: result.get(k) for k in ("grid", "grid_url", "workspace_url", "shown")}


@command(
    "tabs_get",
    "An open table: columns, steps, settings, row count. "
    "An open table in full: columns and types, every step (with ids), settings, step error, the view's row count "
    "(view_rows; row_count is the dataset's), how many rows are selected and how many highlight rules it has.",
    req("grid", "The open table's id."),
)
def get_grid(a: dict[str, Any]) -> Any:
    described = api.call("GET", f"/grids/{_q(a['grid'])}")
    try:
        view_rows = api.call("GET", f"/grids/{_q(a['grid'])}/count")["row_count"]
    except CommandError:
        view_rows = None  # the view fails to compute; step_error says which step
    return described | {"view_rows": view_rows}


@command(
    "tabs_close_grid",
    "Close a table's tab (the dataset stays open). Close an open table's tab (the dataset stays open).",
    req("grid", "The open table's id."),
)
def close_grid(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/grids/{_q(a['grid'])}")


@command(
    "tabs_reopen",
    "Reopen the last closed tab, its steps kept. "
    "Reopen the last closed tab (Ctrl+Shift+T), its steps kept: a closed table is read again from its file.",
)
def reopen_grid(a: dict[str, Any]) -> Any:
    return api.call("POST", "/grids/reopen")


@command(
    "tabs_reload",
    "Reload a table whose file changed, steps kept. "
    "A table whose file changed on disk (datasets_list: changed_on_disk): Reload it, its steps kept.",
    req("dataset", "The table."),
    opt("not_now", "Not now: keep it as it is (said again when the file changes again).", "bool"),
)
def reload_dataset(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/datasets/{_q(a['dataset'])}/reload", {"not_now": bool(a.get("not_now"))})


@command(
    "tabs_cancel",
    "Stop every query running for an open table. "
    "Stop every query now running for an open table: its rows, counts, profiles, SQL and exports.",
    req("grid", "The open table's id."),
)
def cancel(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/grids/{_q(a['grid'])}/cancel")
