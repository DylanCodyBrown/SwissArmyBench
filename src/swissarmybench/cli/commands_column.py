"""The agent's column_* commands: ribbon, Column row.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _insert_step, _q, command, opt, req


@command(
    "column_sort",
    "Sort by columns like clicking their headers (Sort A to Z / Z to A). It stays the last word over other sorts.",
    req("grid", "Grid id."),
    req("columns", "Columns to sort by, in order. An empty list clears the header sort.", "list"),
    opt("direction", "asc (default) or desc."),
)
def column_sort(a: dict[str, Any]) -> Any:
    direction = a.get("direction") or "asc"
    if direction not in ("asc", "desc"):
        raise CommandError("column_sort: direction must be asc or desc.")
    keys = [[column, direction] for column in a["columns"]]
    described = api.call("POST", f"/grids/{_q(a['grid'])}/header-sort", {"keys": keys})
    return {
        "grid": a["grid"],
        "steps": len(described.get("steps", [])),
        "step_error": described.get("step_error"),
    }


@command(
    "column_keep",
    "Keep only these columns (the Column row's Keep only).",
    req("grid", "Grid id."),
    req("columns", "Columns to keep, in the order to show them.", "list"),
    opt("index", "Insert at this step position.", "int"),
)
def column_keep(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "columns", {"keep": a["columns"]}, a.get("index"))


@command(
    "column_remove",
    "Remove these columns from the view (the Column row's Remove).",
    req("grid", "Grid id."),
    req("columns", "Columns to remove.", "list"),
    opt("index", "Insert at this step position.", "int"),
)
def column_remove(a: dict[str, Any]) -> Any:
    shown = [c["name"] for c in api.call("GET", f"/grids/{_q(a['grid'])}")["columns"]]
    unknown = [c for c in a["columns"] if c not in shown]
    if unknown:
        raise CommandError(f"column_remove: not columns of this view: {unknown}. The view has {shown}.")
    keep = [c for c in shown if c not in a["columns"]]
    if not keep:
        raise CommandError("column_remove: that would remove every column.")
    return _insert_step(a["grid"], "columns", {"keep": keep}, a.get("index"))


@command(
    "column_unnest",
    "Unnest a LIST column (a row per item) or a STRUCT column (its fields as columns): a SQL step.",
    req("grid", "Grid id."),
    req("column", "The list or struct column."),
    opt("index", "Insert at this step position.", "int"),
)
def column_unnest(a: dict[str, Any]) -> Any:
    body = {"column": a["column"]} | ({"index": a["index"]} if a.get("index") is not None else {})
    return api.call("POST", f"/grids/{_q(a['grid'])}/unnest", body)


@command(
    "column_rename",
    "Rename columns (a rename step).",
    req("grid", "Grid id."),
    req("mapping", 'e.g. {"old name": "new name"}', "json"),
    opt("index", "Insert at this step position.", "int"),
)
def column_rename(a: dict[str, Any]) -> Any:
    return _insert_step(a["grid"], "rename", {"mapping": a["mapping"]}, a.get("index"))


@command(
    "column_bucket",
    "Add a column that sorts a number or date column into buckets (the Column row's Bucket). Give `unit` for "
    "dates, `edges` or width+low+high for numbers.",
    req("grid", "Grid id."),
    req("column", "The number or date column."),
    req("new_column", "Name of the new column."),
    opt("unit", "Date buckets: day, week, month, quarter or year."),
    opt("edges", "Number buckets: increasing edges, e.g. [0, 10, 100].", "json"),
    opt("width", "Number buckets of equal width (with low and high).", "any"),
    opt("low", "Where equal-width buckets start.", "any"),
    opt("high", "Where equal-width buckets end.", "any"),
    opt("right_closed", "Buckets include their upper edge instead of their lower.", "bool"),
    opt("other_label", "Label for values outside every bucket (default Other)."),
    opt("index", "Insert at this step position.", "int"),
)
def column_bucket(a: dict[str, Any]) -> Any:
    params: dict[str, Any] = {"column": a["column"], "as": a["new_column"]}
    if a.get("unit"):
        params |= {"mode": "date", "unit": a["unit"]}
    elif a.get("edges") is not None:
        params |= {"mode": "edges", "edges": a["edges"]}
    elif a.get("width") is not None:
        params |= {"mode": "width", "width": a["width"], "low": a.get("low"), "high": a.get("high")}
    else:
        raise CommandError("column_bucket: give unit (dates), edges, or width with low and high (numbers).")
    for key in ("right_closed", "other_label"):
        if a.get(key) is not None:
            params[key] = a[key]
    return _insert_step(a["grid"], "bucket", params, a.get("index"))


@command(
    "column_categorize",
    "Add a column of labels from rules (the Column row's Categorize).",
    req("grid", "Grid id."),
    req("column", "The column the rules read."),
    req("new_column", "Name of the new column."),
    req(
        "rules",
        'e.g. [{"type": "contains", "value": "Corp", "label": "Business"}]; types in steps_kinds.',
        "json",
    ),
    opt("unmatched", "Label for rows no rule matches (default Other)."),
    opt("index", "Insert at this step position.", "int"),
)
def column_categorize(a: dict[str, Any]) -> Any:
    params: dict[str, Any] = {"column": a["column"], "as": a["new_column"], "rules": a["rules"]}
    if a.get("unmatched") is not None:
        params["unmatched"] = a["unmatched"]
    return _insert_step(a["grid"], "categorize", params, a.get("index"))


@command(
    "column_profile",
    "Profile one column of the grid's view (the Column row's Profile).",
    req("grid", "Grid id."),
    req("column", "Column name."),
    opt("upto", "Profile the table entering this step index.", "int"),
    values=True,
)
def column_profile(a: dict[str, Any]) -> Any:
    params = {"column": a["column"], "upto": a.get("upto")}
    return api.call("GET", f"/grids/{_q(a['grid'])}/profile", params=params)


@command(
    "column_values",
    "A column's values and row counts, most common first (Filter's checklist).",
    req("grid", "Grid id."),
    req("column", "Column name."),
    opt("search", "Only values holding this text."),
    opt("limit", "At most (200).", "int"),
    opt("upto", "Entering this step.", "int"),
    values=True,
)
def column_values(a: dict[str, Any]) -> Any:
    params = {k: a.get(k) for k in ("column", "search", "limit", "upto") if a.get(k) is not None}
    return api.call("GET", f"/grids/{_q(a['grid'])}/values", params=params)


@command(
    "column_fit_test",
    "Chi-square fit test on columns of the grid's view. expected: even (default), benford / benford2 "
    "(first digits of amounts), grid (another grid: reference), shares, together (two columns "
    "related?). Gives p, an effect size in words, the values furthest off."
    "values furthest from expected.",
    req("grid", "Grid id."),
    req("columns", "Column names.", "list"),
    opt("expected", "even, benford, benford2, grid, shares or together."),
    opt(
        "reference",
        'With expected=grid: {"grid": id, "column": name} (column defaults to the same name).',
        "json",
    ),
    opt("shares", 'With expected=shares: {"value": share, ...} (normalized for you).', "json"),
    values=True,
)
def column_fit_test(a: dict[str, Any]) -> Any:
    columns = a["columns"]
    body = {
        "columns": [columns] if isinstance(columns, str) else columns,
        "expected": a.get("expected") or "even",
        **{k: a[k] for k in ("reference", "shares") if a.get(k) is not None},
    }
    return api.call("POST", f"/grids/{_q(a['grid'])}/fit-test", body)


@command(
    "column_outliers",
    "Outliers in a column. look=amount (method robust (default), iqr or zscore; `by` judges each "
    "group) or look=frequency (values seen too often or too rarely). show / exclude add the step "
    "keeping or dropping them."
    "typos, copied amounts). show=true also adds the step that keeps just those rows.",
    req("grid", "Grid id."),
    req("column", "Column name."),
    opt("look", "amount or frequency."),
    opt("method", "robust, iqr or zscore."),
    opt("threshold", "How far out (3.5, 1.5, 3).", "any"),
    opt("by", "Judge each group of this column."),
    opt("show", "Add the step keeping them.", "bool"),
    opt("exclude", "Add the step dropping them.", "bool"),
    values=True,
)
def column_outliers(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("column", "look", "method", "threshold", "by") if a.get(k) not in (None, "")}
    found = api.call("POST", f"/grids/{_q(a['grid'])}/outliers", body)
    if a.get("show") and a.get("exclude"):
        raise CommandError("column_outliers: show or exclude, not both.")
    key = "step" if a.get("show") else "exclude_step" if a.get("exclude") else None
    if key and found.get(key):
        step = found[key]
        found["shown" if key == "step" else "excluded"] = _insert_step(
            a["grid"], step["kind"], step["params"]
        )
    return found
