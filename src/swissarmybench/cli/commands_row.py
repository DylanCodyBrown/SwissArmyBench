"""The agent's row_* commands: rows.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

import json
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import DATA_NOTE, _csv, _defuse, _insert_step, _q, command, opt, req


@command(
    "row_read",
    "A window of a grid's rows exactly as the page draws them (what the user sees, after its steps), with "
    "highlight marks. format=csv gives the same rows as CSV, headed by the view's total row_count: the "
    "compact form for reading many rows (up to 1,048,576 in one read; the default form gives 1,000).",
    req("grid", "Grid id."),
    opt("start", "First row (default 0).", "int"),
    opt("end", "End row, exclusive (default start+100).", "int"),
    opt("upto", "Show the table entering this step index instead of the final view (not with csv).", "int"),
    opt("format", "csv for CSV text; omit for the page's own shape."),
    values=True,
)
def grid_rows(a: dict[str, Any]) -> Any:
    if a.get("format") in (None, ""):
        return api.call(
            "GET", f"/grids/{_q(a['grid'])}/rows", params={k: a.get(k) for k in ("start", "end", "upto")}
        )
    if a["format"] != "csv":
        raise CommandError("format is csv, or left out.")
    if a.get("upto") is not None:
        raise CommandError("format=csv reads the final view; leave upto out.")
    offset = int(a.get("start") or 0)
    limit = int(a["end"]) - offset if a.get("end") is not None else 100
    if limit < 0:
        raise CommandError("Need start <= end.")
    result = api.call("GET", f"/agent/read/{_q(a['grid'])}", params={"limit": limit, "offset": offset})
    summary = {
        "grid": a["grid"],
        "dataset": result["dataset"],
        "row_count": result["row_count"],
        "offset": result["offset"],
        "rows_returned": len(result["rows"]),
        "row_cap": result["row_cap"],
    }
    if result.get("capped"):
        summary["note"] = f"{limit} rows is above the cap of {result['row_cap']} rows per read."
    header = "\n".join(f"{k}: {v}" for k, v in summary.items())
    return (
        f'{header}\n{DATA_NOTE}\n<untrusted-data source={json.dumps(result["dataset"])} format="csv">\n'
        f"{_defuse(_csv(result['columns'], result['rows']))}</untrusted-data>"
    )


@command(
    "row_count",
    "The view's row count (and the dataset's total). `upto` counts the table entering that step.",
    req("grid", "Grid id."),
    opt("upto", "Step index.", "int"),
)
def grid_count(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/count", params={"upto": a.get("upto")})


@command(
    "row_highlight",
    'Mark rows matching conditions. Each is a filter-shaped object plus a "label"; [] clears them.',
    req("grid", "Grid id."),
    req("highlights", 'e.g. [{"column": "balance", "op": "lt", "value": 0, "label": "negative"}]', "json"),
)
def set_highlights(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/grids/{_q(a['grid'])}/highlights", {"highlights": a["highlights"]})


@command(
    "row_select",
    "Tell the grid how many rows are selected (the number the status bar and agent context show).",
    req("grid", "Grid id."),
    req("count", "Selected row count.", "int"),
)
def set_selection(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/grids/{_q(a['grid'])}/selection", {"count": a["count"]})


@command(
    "row_limit",
    "Keep only the first n rows (a limit step).",
    req("grid", "Grid id."),
    req("n", "How many rows to keep.", "int"),
    opt("index", "Insert at this step position.", "int"),
)
def row_limit(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "limit", {"n": a["n"]}, a.get("index"))
