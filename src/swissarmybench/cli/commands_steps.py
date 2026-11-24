"""The agent's steps_* commands: table Transformations panel and SQL box.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

import json
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _insert_step, _post_steps, _q, _step_op, command, opt, req

STEP_KINDS: dict[str, Any] = {
    "step": '{"kind": <kind>, "params": {...}, "enabled": true}',
    "kinds": {
        "filter": {"column": "name", "op": "<filter op>", "value / values / low / high": "per op"},
        "sort": {"keys": '[["column", "asc"|"desc"], ...]'},
        "columns": {"keep": "[column, ...] (the columns that stay, in order)"},
        "rename": {"mapping": '{"old": "new"}'},
        "group_by": {
            "keys": "[column, ...]",
            "aggregates": '[{"fn": <aggregate>, "column": "name", "as": "new name"}]',
        },
        "distinct": {},
        "limit": {"n": "whole number"},
        "transform": {"fn": "<transform>", "columns": "[column, ...]"},
        "bucket": {
            "column": "name",
            "as": "new column",
            "mode": '"date" (with "unit") or numeric (edges, "right_closed", "other_label")',
        },
        "categorize": {
            "column": "name",
            "as": "new column",
            "rules": "label + rule list",
            "unmatched": "label",
        },
        "sql": {"sql": "one SELECT over grid"},
    },
    "filter_ops": [
        "eq",
        "ne",
        "in",
        "not_in",
        "blank",
        "not_blank",
        "contains",
        "starts_with",
        "ends_with",
        "lt",
        "gt",
        "between",
        "before",
        "after",
        "date_between",
        "true",
        "false",
    ],
    "aggregates": ["count_rows", "count", "distinct_count", "sum", "min", "max", "mean"],
    "transforms": ["trim_left", "trim_right", "trim_both", "upper", "lower"],
    "date_units": ["day", "week", "month", "quarter", "year"],
    "rule_types": ["wildcard", "in", "contains", "starts_with", "range"],
    "note": "Read an open table with tabs_get to see its real steps (with ids) before editing them.",
}


@command("steps_kinds", "The step vocabulary: kinds, their params, filter ops, aggregates, transforms.")
def step_kinds(a: dict[str, Any]) -> Any:
    return STEP_KINDS


@command(
    "steps_run_sql",
    "Run one guarded SQL statement (DuckDB) over the open tables. A SELECT returns rows (at most 1,048,576); "
    "CREATE TABLE <name> AS SELECT ... pins the result as a new dataset with its own tab. `grid` is this "
    "table's view (after its steps); any open table by its name reads that table's rows as loaded.",
    req("grid", "The open table's id: the view `grid` means in the SQL."),
    req(
        "sql",
        "One SELECT, or CREATE TABLE name AS SELECT ... Name a connection's table as [Connection].table ([Connection].dataset.table, .schema.table).",
    ),
    opt("upto", "While editing step N, `grid` is the table entering that step.", "int"),
    values=True,
)
def run_sql(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"sql": a["sql"]}
    if a.get("upto") is not None:
        body["upto"] = a["upto"]
    result = api.call("POST", f"/grids/{_q(a['grid'])}/sql", body)
    # A pinned table carries no cells, so it is not marked as data.
    return json.dumps(result) if isinstance(result, dict) and "pinned" in result else result


@command(
    "steps_counts",
    "Row count after each step (the numbers beside the steps).",
    req("grid", "The open table's id."),
)
def step_counts(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/step-counts")


@command(
    "steps_categorize_stats",
    "Rows a categorize step leaves unmatched or matched twice.",
    req("grid", "The open table's id."),
    req("step", "Index of the categorize step.", "int"),
)
def categorize_stats(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/categorize-stats", params={"step": a["step"]})


@command(
    "steps_python",
    "The table's steps as code for the user's own Python, verified against the table (Copy as SQL / Copy as "
    "Python). `sql` is one DuckDB query over the user's table by its variable name; `code` is "
    "`import duckdb` plus one line running it.",
    req("grid", "The open table's id."),
)
def grid_code(a: dict[str, Any]) -> Any:
    result = api.call("GET", f"/grids/{_q(a['grid'])}/code")
    # "difference" can quote cells, so it stays out.
    keep = ("verified", "note", "rows_checked", "reads", "reason", "sql", "code")
    return {k: result.get(k) for k in keep if k in result}


@command(
    "steps_put",
    "Replace an open table's step list and/or text-matching settings. Steps: see steps_kinds. Omit `steps` to keep them.",
    req("grid", "The open table's id."),
    opt("steps", "The whole new step list.", "json"),
    opt("settings", "case_sensitive, wildcards, trim_spaces, empty_is_blank (booleans).", "json"),
)
def put_steps(a: dict[str, Any]) -> Any:
    return _post_steps(a["grid"], {k: a[k] for k in ("steps", "settings") if a.get(k) is not None})


@command(
    "steps_add",
    "Add one step (the ribbon's Filter, Sort, Group by...). Goes before a header-click sort unless `index` is given.",
    req("grid", "The open table's id."),
    req("kind", "Step kind (see steps_kinds)."),
    req("params", "The step's params.", "json"),
    opt("index", "Insert at this position.", "int"),
)
def add_step(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], a["kind"], a["params"], a.get("index"))


@command(
    "steps_edit",
    "Replace a step's params (the step's Edit button).",
    req("grid", "The open table's id."),
    req("index", "Step index, from 0.", "int"),
    req("params", "The full new params.", "json"),
)
def edit_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "edit", "index": a["index"], "params": a["params"]})


@command(
    "steps_delete",
    "Remove a step (the step's trash button).",
    req("grid", "The open table's id."),
    req("index", "Step index, from 0.", "int"),
)
def delete_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "delete", "index": a["index"]})


@command(
    "steps_toggle",
    "Turn a step off or on without deleting it (the step's checkbox).",
    req("grid", "The open table's id."),
    req("index", "Step index, from 0.", "int"),
    opt("enabled", "true/false; omit to flip.", "bool"),
)
def toggle_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "toggle", "index": a["index"], "enabled": a.get("enabled")})


@command(
    "steps_move",
    "Move a step to another position.",
    req("grid", "The open table's id."),
    req("index", "Step index, from 0.", "int"),
    req("to", "New index.", "int"),
)
def move_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "move", "index": a["index"], "to": a["to"]})


@command(
    "steps_undo",
    "Undo the last change to the table's steps (the page's Ctrl+Z): a step added, removed, edited, switched "
    "off or moved, the steps cleared, a header sort. Each table remembers its own changes.",
    req("grid", "The open table's id."),
)
def undo_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "undo"})


@command(
    "steps_redo",
    "Redo the step change last undone (the page's Ctrl+Y). A new change ends what can be redone.",
    req("grid", "The open table's id."),
)
def redo_step(a: dict[str, Any]) -> Any:
    return _step_op(a["grid"], {"op": "redo"})


@command(
    "steps_apply_sql",
    "Add a SQL transformation step (Create SQL transformation, Apply): one SELECT over the table as it stands, "
    "by the dataset's own name or `grid`. Later steps see its columns.",
    req("grid", "The open table's id."),
    req("sql", "One SELECT."),
)
def apply_sql_step(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "sql", {"sql": a["sql"]})


@command(
    "steps_save_result",
    "Run a SELECT over `grid` or dataset names and pin the result as a new dataset with its own tab.",
    req("grid", "The open table's id the SQL reads."),
    req("sql", "One SELECT."),
    req("name", "New dataset name."),
)
def save_result(a: dict[str, Any]) -> Any:
    result = api.call(
        "POST", f"/grids/{_q(a['grid'])}/sql", {"sql": f"CREATE TABLE {a['name']} AS {a['sql']}"}
    )
    return {"dataset": result.get("pinned"), "grid": result.get("grid")}
