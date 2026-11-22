"""The agent's table_* commands: ribbon, Table row.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

import json
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _insert_step, _post_steps, _q, command, opt, req


@command(
    "table_profile",
    "Profile of the grid's view (every column, or one with `column`): the page's Profile button. For a "
    "table with no grid, give `dataset` instead: its schema, row count, duplicate rows and a line a column "
    "(or one column's full profile with `column`), over the rows as loaded.",
    opt("grid", "Grid id (this, or dataset)."),
    opt("column", "One column; omit for the whole table."),
    opt("upto", "Profile the table entering this step index.", "int"),
    opt("dataset", "A dataset's name, for a table with no grid."),
    values=True,
)
def grid_profile(a: dict[str, Any]) -> Any:
    if a.get("grid"):
        return api.call(
            "GET", f"/grids/{_q(a['grid'])}/profile", params={k: a.get(k) for k in ("column", "upto")}
        )
    if not a.get("dataset"):
        raise CommandError("Give a grid, or a dataset for a table with no grid.")
    if a.get("column"):
        return api.call("GET", f"/agent/profile/{_q(a['dataset'])}", params={"column": a["column"]})
    return api.call("GET", f"/agent/describe/{_q(a['dataset'])}")


@command(
    "table_header_stats",
    "The column-header statistics the page shows (min, max, blanks...) for every column.",
    req("grid", "Grid id."),
    values=True,
)
def grid_stats(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/header-stats")


@command(
    "table_export",
    "Export the grid to the user's export folder. Waits for the user's approval click. Returns the saved path.",
    req("grid", "Grid id."),
    opt("format", "csv (default), txt, xlsx or parquet."),
    opt("file", "File name stem (letters, digits, _ and -)."),
    opt("scope", "view (default), rows, columns, selection, source or profile."),
    opt("columns", "Column names for scope=columns.", "list"),
    opt("rows", "Row positions for scope=rows.", "list"),
    opt("selection", "A selection for scope=selection.", "json"),
    opt("overwrite", "Replace an existing file.", "bool"),
    opt(
        "options",
        "More export options as an object: delimiter, line_ending, encoding, header, quote_all, sheet_name, compression, provenance, blank...",
        "json",
    ),
)
def grid_export(a: dict[str, Any]) -> Any:
    fmt = a.get("format") or "csv"
    scope = a.get("scope") or "view"
    approved = api.call(
        "POST", f"/agent/export-approval/{_q(a['grid'])}", params={"format": fmt, "scope": scope}
    )
    options = a.get("options") or {}
    if not isinstance(options, dict):
        raise CommandError('table_export: options must be an object, e.g. {"delimiter": ";"}.')
    params: dict[str, Any] = dict(options)
    params |= {"format": fmt, "save": "1", "ticket": approved.get("ticket")}
    for key in ("file", "scope", "overwrite"):
        if a.get(key):
            params[key] = a[key]
    for key in ("columns", "rows"):
        if a.get(key):
            params[key] = ",".join(str(v) for v in a[key])
    if a.get("selection") is not None:
        params["selection"] = json.dumps(a["selection"])
    return api.call("GET", f"/grids/{_q(a['grid'])}/export", params=params)


@command(
    "table_matching",
    "The ribbon's Matching: how filters and rules compare text. Omitted switches keep their value.",
    req("grid", "Grid id."),
    opt("case_sensitive", "Match case.", "bool"),
    opt("wildcards", "Treat % and _ as wildcards.", "bool"),
    opt("trim_spaces", "Ignore leading and trailing spaces.", "bool"),
    opt("empty_is_blank", "Treat empty text as blank.", "bool"),
)
def set_matching(a: dict[str, Any]) -> Any:
    # Only the switches change; the steps stay on the server as they are (never read back).
    settings = api.call("GET", f"/grids/{_q(a['grid'])}").get("settings", {})
    settings = {**settings, **{k: a[k] for k in settings if a.get(k) is not None}}
    return _post_steps(a["grid"], {"settings": settings}) | {"settings": settings}


#
# These are thin wrappers over the steps the Table and Column rows and a cell's right-click menu add. The page's buttons act
# on "the selected column(s)" or "the selected cells", which only the browser knows; an agent names
# the columns or values instead, so each wrapper takes them as arguments.
@command(
    "table_filter",
    "Keep rows that match a condition (the ribbon's Filter). ops: eq ne in not_in blank not_blank contains "
    "starts_with ends_with lt gt between before after date_between true false.",
    req("grid", "Grid id."),
    req("column", "Column name."),
    req("op", "The filter operation."),
    opt("value", "The value for eq, ne, contains, lt, gt, before, after...", "any"),
    opt("values", "The list for in and not_in.", "json"),
    opt("low", "Lower bound for between and date_between.", "any"),
    opt("high", "Upper bound for between and date_between.", "any"),
    opt("index", "Insert at this step position.", "int"),
)
def table_filter(a: dict[str, Any]) -> Any:
    params = {k: a[k] for k in ("column", "op", "value", "values", "low", "high") if a.get(k) is not None}
    return _insert_step(a["grid"], "filter", params, a.get("index"))


@command(
    "table_sort",
    "Sort by up to three columns with their own directions (the ribbon's Sort, a sort step).",
    req("grid", "Grid id."),
    req("keys", 'e.g. [["region", "asc"], ["amount", "desc"]]', "json"),
    opt("index", "Insert at this step position.", "int"),
)
def table_sort(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "sort", {"keys": a["keys"]}, a.get("index"))


@command(
    "table_group_by",
    "Group rows and add totals, counts or averages (the ribbon's Group by).",
    req("grid", "Grid id."),
    req("keys", "Columns to group by; [] gives one total row.", "list"),
    req("aggregates", 'e.g. [{"fn": "sum", "column": "amount", "as": "total"}]; fns in steps_kinds.', "json"),
    opt("index", "Insert at this step position.", "int"),
)
def table_group_by(a: dict[str, Any]) -> Any:
    return _insert_step(
        a["grid"], "group_by", {"keys": a["keys"], "aggregates": a["aggregates"]}, a.get("index")
    )


@command(
    "table_distinct",
    "Drop duplicate rows, the first one stays (the ribbon's Distinct rows).",
    req("grid", "Grid id."),
    opt("index", "Insert at this step position.", "int"),
)
def table_distinct(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "distinct", {}, a.get("index"))


@command(
    "table_clean_text",
    "Trim or change the case of text columns (the ribbon's Clean text).",
    req("grid", "Grid id."),
    req("fn", "trim_left, trim_right, trim_both, upper or lower."),
    opt("columns", "Text columns; every text column when omitted.", "list"),
    opt("index", "Insert at this step position.", "int"),
)
def table_clean_text(a: dict[str, Any]) -> Any:
    params = {"fn": a["fn"], "columns": a.get("columns") or "*text"}
    return _insert_step(a["grid"], "transform", params, a.get("index"))


# ----- a table's connection swapped (its steps kept), and the code that named the old one -----
@command(
    "table_connection",
    "A table's connection, how it is read, the others, its undo",
    req("table", "Its name."),
)
def table_connection(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/tables/{_q(a['table'])}/connection")


@command(
    "table_swap_connection",
    "Read a table from another connection, steps kept. Answers swapped, or review (send its sql back), "
    "or pick (send a place)",
    req("table", "Its name."),
    req("to", "The connection."),
    opt("place", '{"database", "schema", "table"} there.', "json"),
    opt("sql", "A read query to run there."),
    opt("all", "Every row.", "bool"),
)
def table_swap_connection(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("to", "place", "sql", "all") if a.get(k) is not None}
    return api.call("POST", f"/tables/{_q(a['table'])}/connection", body)


@command("table_swap_undo", "Undo a table's last connection swap", req("table", "Its name."))
def table_swap_undo(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/tables/{_q(a['table'])}/connection/undo", {})
