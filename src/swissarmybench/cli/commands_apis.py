"""The agent's apis_* commands: aPIs: each API added with Add API, its operations' inputs and outputs, Try it, Refresh.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "apis_make_into_blades",
    "Make an older API connection (apis_list's older) into blades in this computer's library: its API blade "
    "and a web call blade per operation, from the document it was made from (or the one given).",
    req("name", "The older API connection."),
    opt("spec_path", "Its OpenAPI document's file, when Add API did not keep it."),
    opt("spec_url", "Or its address."),
)
def apis_make_into_blades(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("spec_path", "spec_url") if a.get(k)}
    return api.call("POST", f"/apis/{_q(a['name'])}/make-into-blades", body)


@command(
    "apis_list", "Every API in the library: its operations, tables, sign-in type, source, calls this session"
)
def apis_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/apis")


@command(
    "apis_describe",
    "An API's operations (inputs, body example, outputs per status, its web call blade, SQL name) and its "
    "schemas; with operation: that one only",
    req("name", "The API."),
    opt("operation", "An operation (list_orders)."),
)
def apis_describe(a: dict[str, Any]) -> Any:
    query = f"?operation={_q(a['operation'])}" if a.get("operation") else ""
    return api.call("GET", f"/apis/{_q(a['name'])}" + query)


@command("apis_search", "Search every API's operations: name, method, path, text, tags, parameters, fields",
         req("q", "Words."))  # fmt: skip
def apis_search(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/apis/search?q={_q(a['q'])}")


@command(
    "apis_call",
    "Send an operation (its web call, after its API blade): the answer opens in Structures with its lineage; "
    "you get the status, time, headers and the structure's id (read it with structures_show)",
    req("name", "The API."),
    req("operation", "The operation."),
    opt("inputs", '{"order_id": 3} or {"path": {...}, "query": {...}, "header": {...}}.', "json"),
    opt("body", "The JSON body.", "json"),
)
def apis_call(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("inputs", "body") if k in a}
    return api.call("POST", f"/apis/{_q(a['name'])}/calls/{_q(a['operation'])}", body)


@command(
    "apis_save_call",
    "Save an operation's web call blade: its inputs and body; as_table=true makes it one of the API's tables "
    "in SQL (records: $.items; shape records|header_rows; header; columns; flatten; paging all|first)",
    req("name", "The API."),
    req("operation", "The operation."),
    opt("inputs", "Its inputs.", "json"),
    opt("body", "Its body.", "json"),
    opt("as_table", "Return as table.", "bool"),
    opt("records", "Where its rows are ($.items)."),
    opt("shape", "records or header_rows."),
    opt("header", "header_rows: its header's path, or first_row."),
    opt("columns", '{"id": "BIGINT"}.', "json"),
    opt("flatten", "Nested objects as columns.", "bool"),
    opt("paging", "all or first."),
    opt("conversion", "DuckDB's SQL over response (one row per page, page)."),
    opt("structure", "A Structures answer to read the settings from (with as_table)."),
)
def apis_save_call(a: dict[str, Any]) -> Any:
    keys = ("inputs", "body", "as_table", "records", "shape", "header", "columns", "flatten", "paging", "conversion",
            "structure")  # fmt: skip
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("PUT", f"/apis/{_q(a['name'])}/calls/{_q(a['operation'])}", body)


@command(
    "apis_write_rows",
    "Write a table's rows with a POST/PUT/PATCH/DELETE operation: a dry run by default (the first three "
    "requests, the rows, the calls, the fields unmapped); dry_run=false sends, only after the user said to "
    "write, in their own words; save=true saves it as a web call blade",
    req("name", "The API."),
    req("operation", "The operation."),
    opt("table", "An open table's name."),
    opt("structure", "Or a Structures document's id, with path."),
    opt("path", "Its list's path ($.items)."),
    opt(
        "mapping",
        '{"body.customer.name": {"column": "name"}, "query.dry": {"value": true}}; else by name.',
        "json",
    ),
    opt("batch", "One call for many rows (the body an array).", "bool"),
    opt("batch_size", "Rows per batched call.", "int"),
    opt("key_columns", "Columns the results keep.", "json"),
    opt("response_field", "The answer's field to keep (id).", "str"),
    opt("dry_run", "False sends.", "bool"),
    opt("retry", "A results structure: its failed rows only.", "str"),
    opt("save", "Save it as a web call blade.", "bool"),
)
def apis_write_rows(a: dict[str, Any]) -> Any:
    keys = ("table", "structure", "path", "mapping", "batch", "batch_size", "key_columns", "response_field",
            "dry_run", "retry")  # fmt: skip
    body = {k: a[k] for k in keys if a.get(k) is not None}
    where = f"/apis/{_q(a['name'])}/calls/{_q(a['operation'])}/write"
    return api.call("PUT" if a.get("save") else "POST", where, body)


@command(
    "apis_refresh",
    "Read an API's source again: what changed (operations, parameters, fields), nothing written; "
    "apis_apply_refresh writes it",
    req("name", "The API."),
)
def apis_refresh(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/apis/{_q(a['name'])}/refresh", {})


@command("apis_apply_refresh", "Write what apis_refresh showed", req("name", "The API."))
def apis_apply_refresh(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/apis/{_q(a['name'])}/refresh/apply", {})


@command(
    "apis_rename",
    "Rename an API (its blades too; the code that named it is listed), or set its check-for-changes switch",
    req("name", "The API."),
    opt("new_name", "Its new name."),
    opt("check", "Check for changes when the page opens.", "bool"),
)
def apis_rename(a: dict[str, Any]) -> Any:
    if a.get("check") is not None:
        return api.call("PUT", f"/apis/{_q(a['name'])}/check", {"on": a["check"]})
    return api.call("PUT", f"/apis/{_q(a['name'])}/name", {"name": a.get("new_name") or ""})


@command(
    "apis_delete",
    "Delete an API (its blades and folder): without confirm, the code that uses it; with confirm, it waits "
    "for the user's Allow",
    req("name", "The API."),
    opt("confirm", "Delete it.", "bool"),
)
def apis_delete(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/apis/{_q(a['name'])}/delete", {"confirm": bool(a.get("confirm"))})
