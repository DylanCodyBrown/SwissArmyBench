"""The agent's cell_* commands: a cell's right-click menu.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _insert_step, _q, command, opt, req


@command(
    "cell_view",
    "One cell's full value (the page's View value).",
    req("grid", "The open table's id."),
    req("row", "Row position in the view.", "int"),
    req("column", "Column name."),
    values=True,
)
def grid_cell(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/cell", params={"row": a["row"], "column": a["column"]})


@command(
    "cell_selection_stats",
    "Count, sum and average for a selection, like Excel's status bar. selection: "
    '{"rows": [[first, last], ...] | null, "columns": [name, ...] | null}.',
    req("grid", "The open table's id."),
    req("selection", "The selection.", "json"),
    values=True,
)
def selection_stats(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/grids/{_q(a['grid'])}/selection-stats", {"selection": a["selection"]})


@command(
    "cell_keep",
    "Keep only rows with these values in a column (the cell's right-click Keep these).",
    req("grid", "The open table's id."),
    req("column", "Column name."),
    req("values", 'The values to keep, e.g. ["east", "west"].', "json"),
    opt("index", "Insert at this step position.", "int"),
)
def cell_keep(a: dict[str, Any]) -> Any:
    params = {"column": a["column"], "op": "in", "values": a["values"]}
    return _insert_step(a["grid"], "filter", params, a.get("index"))


@command(
    "cell_exclude",
    "Drop rows with these values in a column (the cell's right-click Exclude these).",
    req("grid", "The open table's id."),
    req("column", "Column name."),
    req("values", "The values to drop.", "json"),
    opt("index", "Insert at this step position.", "int"),
)
def cell_exclude(a: dict[str, Any]) -> Any:
    params = {"column": a["column"], "op": "not_in", "values": a["values"]}
    return _insert_step(a["grid"], "filter", params, a.get("index"))
