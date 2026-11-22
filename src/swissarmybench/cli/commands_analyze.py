"""The agent's analyze_* commands: the Analyze page: every analysis (analyze_run), its cards on the board, dashboards, themes.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "analyze_all",
    "Every chart, note, table and diagram card on the Analyze board.",
)
def all_cards(a: dict[str, Any]) -> Any:
    return api.call("GET", "/cards")


@command("analyze_list", "The cards drawn on one grid.", req("grid", "Grid id."))
def list_cards(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/grids/{_q(a['grid'])}/cards")


_CARD_FIELDS = (
    opt("title", "Card title (up to 200 characters)."),
    opt(
        "body",
        "note: markdown; diagram: Mermaid; plotly: figure JSON; image: data URL.",
    ),
    opt(
        "spec",
        "Chart spec: {mark: bar|line|area|point|histogram|heatmap, x: {field, time_unit?, bins?, sort?}, "
        "y: {field?, aggregate: count|sum|mean|min|max}, color?: {field}, title?}.",
        "json",
    ),
    opt("sql", "A SELECT over `grid`: a table card's rows, or what fills a plotly body."),
    opt("size", '{"w": 2-12 columns, "h": 3-30 rows of 40px}.', "json"),
)


# What each card kind takes (analyze_formats): the agent's whole drawing vocabulary in one answer.
_FORMATS: dict[str, Any] = {
    "board": "12 columns wide, rows of 40px; size {w: 2-12, h: 3-30}. Cards go in order; analyze_update "
    "moves (before) and resizes them. Page view prints them as letter or landscape pages.",
    "kinds": {
        "chart": {
            "needs": "grid",
            "spec": '{"mark": "bar", "x": {"field": "region"}, "y": {"aggregate": "count"}}',
            "note": "Computed on the grid's view, redrawn when its steps change; clicking filters.",
        },
        "table": {
            "needs": "grid for sql",
            "sql": "SELECT region, sum(amount) FROM t GROUP BY 1",
            "or": "columns and rows of its own (no grid), first 100 rows",
        },
        "note": {
            "body": "Markdown: headings, lists, tables, code, quotes. An Analyze note is resizable like a text box."
        },
        "diagram": {"body": "Mermaid text: flowchart LR\n  A --> B"},
        "plotly": {
            "body": '{"data": [{"type": "bar", "x": ["a"], "y": [1]}], "layout": {}}',
            "note": 'No map traces. Colours may be "theme:accent" to follow the theme.',
            "bound": 'With grid and sql, a trace field naming a column ("x": "region") gets its values.',
        },
        "image": {"body": "data:image/png;base64,...", "or": "file: a PNG, JPEG, GIF, WebP or SVG you saved"},
        "vegalite": {"note": "From the user's own Python (Altair) only; the agent draws with chart."},
    },
    "data": "Read tables with the table tools (columns, profiles, steps_run_sql). A chart card, or a plotly "
    "card with sql (FROM grid, or its table's name: the grid as shown), computes on the grid "
    "itself (first 5,000 rows), follows its steps, and big "
    "data never passes through you. Use key to replace a card you made before.",
}


@command(
    "analyze_formats",
    "What each Analyze card kind takes, with an example, and how sizing works.",
)
def card_formats(a: dict[str, Any]) -> Any:
    return _FORMATS


@command(
    "analyze_add",
    "Add a card to the Analyze board (analyze_formats lists the kinds). Without grid it belongs to no table.",
    opt("grid", "Grid id: needed for chart and for table sql."),
    opt("kind", "chart, note, table, diagram, plotly or image."),
    *_CARD_FIELDS,
    opt("file", "A picture, .md or .mmd file on this computer."),
    opt("columns", "A table card's own column names.", "json"),
    opt("rows", "A table card's own rows: lists, one value per column.", "json"),
    opt("key", "Names the card: adding the same key again replaces it in place."),
)
def add_card(a: dict[str, Any]) -> Any:
    body = {
        k: a[k]
        for k in ("kind", "title", "body", "spec", "sql", "size", "columns", "rows", "key")
        if a.get(k) is not None
    }
    if a.get("file"):
        from swissarmybench.client.visualizations_client import card_for

        try:
            made = card_for(Path(a["file"]).expanduser(), a.get("kind"))
        except (OSError, ValueError, TypeError) as error:
            raise CommandError(f"Can't read {a['file']!r} as a card: {error}") from None
        body = made | {k: v for k, v in body.items() if k != "kind"}
    if "kind" not in body:
        raise CommandError("Name the kind, or give a file.")
    body.setdefault("title", "")
    path = f"/grids/{_q(a['grid'])}/cards" if a.get("grid") else "/cards"
    return api.call("POST", path, body)


@command(
    "analyze_update",
    "Change a card's title, body, spec, sql or size, pin it, move it (before a card) or start a page.",
    req("card", "Card id."),
    *_CARD_FIELDS,
    opt("pinned", "Pin it to the top.", "bool"),
    opt("before", "Move it just before this card id; 'end' moves it last."),
    opt("new_page", "In Page view (and the PDF), start a new page with this card.", "bool"),
)
def update_card(a: dict[str, Any]) -> Any:
    body = {
        k: a[k]
        for k in ("title", "body", "spec", "sql", "size", "pinned", "new_page")
        if a.get(k) is not None
    }
    if a.get("before"):
        body["before"] = None if a["before"] == "end" else a["before"]
    return api.call("PATCH", f"/cards/{_q(a['card'])}", body)


@command(
    "analyze_dashboards",
    "Saved dashboards; with name, its versions and cards (analyze_dashboard saves, opens and deletes).",
    opt("name", "A dashboard's name."),
)
def dashboards(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/dashboards/{_q(a['name'])}" if a.get("name") else "/dashboards")


@command(
    "analyze_theme",
    "The Analyze board's themes; set one (theme), or propose your own (file). The grid keeps its own theme.",
    opt("theme", "A theme's id, or app to follow the app."),
    opt("file", '{"name", "dark", "tokens": {"bg": "#rrggbb", ..., "cat": [8 colours]}}', "json"),
)
def analyze_theme(a: dict[str, Any]) -> Any:
    if a.get("file") is not None:
        return api.call("POST", "/analyze/themes", a["file"])
    if a.get("theme"):
        return api.call("PUT", "/analyze/theme", {"theme": a["theme"]})
    listed = api.call("GET", "/analyze/themes")
    # Names and notes only: the agent picks by id, and needs no colour values to do it.
    return {
        "current": listed["current"],
        "themes": [{k: t[k] for k in ("id", "label", "dark", "group", "note")} for t in listed["themes"]],
    }


@command("analyze_delete", "Remove a card.", req("card", "Card id."))
def delete_card(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/cards/{_q(a['card'])}")


@command(
    "analyze_select",
    "Click a chart's bar or point: adds the matching filter step to its grid (cross-filtering).",
    req("card", "Chart card id."),
    opt("value", "The x value clicked; omit for the blank bar."),
)
def card_select(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/cards/{_q(a['card'])}/select", {"value": a.get("value")})


@command("analyze_chart_code", "The Altair Python for a chart card.", req("card", "Chart card id."))
def card_code(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/cards/{_q(a['card'])}/code")


@command(
    "analyze_odds",
    "Each value's share and odds; with `outcome` (values, or op and value for a number) each value's "
    "rate of it against the rest and its odds ratio with a 95% range. Numbers are bucketed.",
    req("grid", "Grid id."),
    req("column", "The column whose values to count."),
    opt(
        "outcome",
        '{"column": "late", "values": ["late"]}, or {"column": "amount", "op": "gt", "value": 1000}.',
        "json",
    ),
    opt("buckets", "Ranges for a number column (2 to 20).", "int"),
    values=True,
)
def analyze_odds(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("column", "outcome", "buckets") if a.get(k) is not None}
    return api.call("POST", f"/grids/{_q(a['grid'])}/odds", body)


@command(
    "analyze_predictors",
    "Which columns go with a target: each tested by chi-square (numbers bucketed), ranked by "
    "Cramér's V with correlations; identifiers and dates skipped; pairs saying the same thing "
    "flagged."
    "pairs of candidates that say the same thing (give a regression the one to keep).",
    req("grid", "Grid id."),
    req("target", "A number or a category."),
    opt("candidates", "Only these columns.", "list"),
    opt("buckets", "Ranges for numbers (4).", "int"),
    values=True,
)
def analyze_predictors(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("target", "candidates", "buckets") if a.get(k) is not None}
    return api.call("POST", f"/grids/{_q(a['grid'])}/predictors", body)


@command(
    "analyze_regression",
    "Regression: linear for a number target, logistic with `outcome` (odds ratios). Effects in words "
    "with ranges and p, the fit, the verdict, `model` (for analyze_predict) and `steps` (predicted / "
    "miss columns for steps_add)."
    "with steps_add). Use analyze_predictors first to choose the predictors.",
    req("grid", "Grid id."),
    req("target", "The column to predict."),
    req("predictors", "Column names.", "list"),
    opt("outcome", "For yes/no: as in analyze_odds.", "json"),
    values=True,
)
def analyze_regression(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("target", "predictors", "outcome") if a.get(k) is not None}
    return api.call("POST", f"/grids/{_q(a['grid'])}/regression", body)


@command(
    "analyze_predict",
    "What-if: a model's (from analyze_regression) estimate for the values given, with its 95% range."
    "with its 95% range (where a new row would fall; for yes/no, the chance and its range).",
    req("model", "analyze_regression's model.", "json"),
    req("values", "{column: value} for every predictor.", "json"),
)
def analyze_predict(a: dict[str, Any]) -> Any:
    return api.call("POST", "/regression/predict", {"model": a["model"], "values": a["values"]})


@command(
    "analyze_time_series",
    "A metric per period from a date column: trend, season in words, periods that stand out (with a step "
    "showing their rows), steps in the level, memory, growth.",
    req("grid", "Grid id."),
    req("date", "The date column."),
    opt("metric", "A number column (omit to count rows)."),
    opt("total", "sum, avg or count."),
    opt("period", "day, week, month, quarter or year."),
    opt("split", "One line per value of this column."),
    values=True,
)
def analyze_time_series(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("date", "metric", "total", "period", "split") if a.get(k) is not None}
    return api.call("POST", f"/grids/{_q(a['grid'])}/time-series", body)


@command(
    "analyze_forecast",
    "Forecast a metric per period: trend and season continued, 80% and 95% ranges, a held-back check of "
    "its typical miss; predictors each with a future (last, trend or value).",
    req("grid", "Grid id."),
    req("date", "The date column."),
    opt("metric", "A number column (omit to count rows)."),
    opt("total", "sum, avg or count."),
    opt("period", "day, week, month, quarter or year."),
    opt("horizon", "Periods ahead (12).", "int"),
    opt("predictors", '[{"column", "future": "last|trend|value", "value"}].', "json"),
    values=True,
)
def analyze_forecast(a: dict[str, Any]) -> Any:
    keys = ("date", "metric", "total", "period", "horizon", "predictors")
    return api.call(
        "POST", f"/grids/{_q(a['grid'])}/forecast", {k: a[k] for k in keys if a.get(k) is not None}
    )


def _analyze_body(a: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: a[k] for k in keys if a.get(k) not in (None, "")}


@command(
    "analyze_contracts",
    "Each analysis's data contract: its slots (the kinds of column each takes, how many, the checks), the "
    "table's shape, options with defaults, what it makes, and a made-up sample. Read it, then analyze_run.",
    opt(
        "analysis",
        "One analysis's id (omit for all): benford, fit, together, outliers, odds, predictors, "
        "regression, whatif, time_series, forecast, tie_out, key_finder, profile, check.",
    ),
)
def analyze_contracts(a: dict[str, Any]) -> Any:
    if a.get("analysis"):
        return api.call("GET", f"/analyze/contracts/{_q(a['analysis'])}")
    return api.call("GET", "/analyze/contracts")


@command(
    "analyze_tables",
    "The Analyze toolbar (each analysis, by group) and the open tables it can run on, with the one its "
    "forms start on.",
    values=True,
)
def analyze_tables(a: dict[str, Any]) -> Any:
    return api.call("GET", "/analyze")


@command(
    "analyze_check",
    "Check this table: every analysis ranked for it (fits now, fits after its fixes, or not, with why) "
    "and the three that suit it. With `analysis`: that one's check: per slot what fits and what does not "
    "(and why), what is missing, and `fixes`, each with the steps (for steps_add) that make the table fit.",
    opt("table", "Grid id or table name (default: the one Analyze last used)."),
    opt("analysis", "One analysis's id."),
    opt("columns", "{slot: column} to check instead of the app's picks.", "json"),
    values=True,
)
def analyze_check(a: dict[str, Any]) -> Any:
    return api.call("POST", "/analyze/check", _analyze_body(a, "table", "analysis", "columns"))


@command(
    "analyze_plan",
    "An analysis's form for a table, as the page shows it: each slot's pick (and why), the columns that "
    "fit, the options and their defaults, and the sentence of what analyze_run would run.",
    req("analysis", "The analysis's id (analyze_contracts)."),
    opt("table", "Grid id or table name."),
    opt("columns", "{slot: column or [columns]}.", "json"),
    opt("options", "{option: value}.", "json"),
    values=True,
)
def analyze_plan(a: dict[str, Any]) -> Any:
    return api.call("POST", "/analyze/plan", _analyze_body(a, "analysis", "table", "columns", "options"))


@command(
    "analyze_column",
    "What can I do with a column? The analyses it fits (each runs with analyze_run); with no column, "
    "every column of the table with its type and what fits it.",
    opt("table", "Grid id or table name."),
    opt("column", "Column name."),
    values=True,
)
def analyze_column(a: dict[str, Any]) -> Any:
    return api.call("POST", "/analyze/column", _analyze_body(a, "table", "column"))


@command(
    "analyze_fix",
    "Make it fit: add the named fixes' steps to the table (the user sees them in the steps strip and can "
    "undo them), then the form again. The ids are analyze_check's `fixes`.",
    req("analysis", "The analysis's id."),
    req("fixes", "Fix ids.", "list"),
    opt("table", "Grid id or table name."),
    opt("columns", "{slot: column} already chosen.", "json"),
)
def analyze_fix(a: dict[str, Any]) -> Any:
    fixes = a["fixes"]
    body = _analyze_body(a, "analysis", "table", "columns") | {
        "fixes": [fixes] if isinstance(fixes, str) else fixes
    }
    return api.call("POST", "/analyze/fix", body)


@command(
    "analyze_run",
    "Run an analysis by its id: columns and options are picked by the app unless given. Its cards land on "
    "the Analyze board (as the user's do) and `result` holds the numbers. A table that does not fit is "
    "refused with why and the form (`plan`); apply_fixes adds the steps it needs first.",
    req("analysis", "The analysis's id (analyze_contracts)."),
    opt("table", "Grid id, table name or [Connection].table (default: the one Analyze last used)."),
    opt("columns", "{slot: column or [columns]}.", "json"),
    opt("options", "{option: value}.", "json"),
    opt("apply_fixes", "Add the fixes the table needs (grid steps) and then run.", "bool"),
    opt("sample", "Run on the contract's made-up sample instead (opened as a table).", "bool"),
    opt("token", "A name for this run, for analyze_cancel."),
    values=True,
)
def analyze_run(a: dict[str, Any]) -> Any:
    body = _analyze_body(a, "analysis", "table", "columns", "options", "token")
    body |= {k: True for k in ("apply_fixes", "sample") if a.get(k)}
    return api.call("POST", "/analyze/run", body)


@command(
    "analyze_cancel",
    "Stop a run started with a token; nothing of it lands.",
    req("token", "The run's token."),
)
def analyze_cancel(a: dict[str, Any]) -> Any:
    return api.call("POST", "/analyze/cancel", {"token": a["token"]})


@command(
    "analyze_runs",
    "This session's runs, newest first; with `run` and `show`, a result's actions: inputs (Run again), "
    "math (Show the math), code (Copy code) or grid (Open as grid: its table in a new tab).",
    opt("run", "A run's id."),
    opt("show", "inputs, math, code or grid."),
    values=True,
)
def analyze_runs(a: dict[str, Any]) -> Any:
    if not a.get("run"):
        return api.call("GET", "/analyze/runs")
    show = a.get("show") or "inputs"
    if show not in ("inputs", "math", "code", "grid"):
        raise CommandError("analyze_runs: show is inputs, math, code or grid.")
    if show == "grid":
        return api.call("POST", f"/analyze/runs/{_q(a['run'])}/grid", {})
    if show == "math":
        return api.call("GET", f"/analyze/runs/{_q(a['run'])}/math")
    if show == "code":
        return api.call("GET", f"/analyze/runs/{_q(a['run'])}/code")
    return api.call("GET", f"/analyze/runs/{_q(a['run'])}")


@command(
    "analyze_sample",
    "Open an analysis's made-up sample as a table (Try it on this sample): its grid and the columns each "
    "slot takes.",
    req("analysis", "The analysis's id."),
)
def analyze_sample(a: dict[str, Any]) -> Any:
    return api.call("POST", "/analyze/sample", {"analysis": a["analysis"]})


@command(
    "analyze_code",
    "An analysis as Python for the user's notebook (one swissarmybench.stats call): code and imports",
    req("grid", "The grid's id."),
    req("analysis", "fit_test, outliers, odds, predictors, regression, time_series or forecast."),
    req("body", "The analysis's own request, as its analyze_ command takes it.", "json"),
)
def analyze_code(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", f"/grids/{_q(a['grid'])}/analysis-code", {"analysis": a["analysis"], "body": a["body"]}
    )


@command(
    "analyze_proof",
    "Show the math: an analysis result as a step-by-step proof (markdown)",
    req("analysis", "The analysis's name."),
    req("result", "Its result, as the analyze_ command gave it.", "json"),
    opt("dataset", "The table's name, for the title."),
)
def analyze_proof(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        "/analysis-proof",
        {"analysis": a["analysis"], "result": a["result"], "dataset": a.get("dataset") or ""},
    )


@command(
    "analyze_dashboard",
    "Save Analyze as a dashboard (a new version), open one, or delete one",
    req("action", "save, open or delete."),
    req("name", "The dashboard's name."),
    opt("version", "open: which version (default: the newest).", "int"),
)
def analyze_dashboard(a: dict[str, Any]) -> Any:
    name, action = _q(a["name"]), a["action"]
    if action == "save":
        return api.call("POST", "/dashboards", {"name": a["name"]})
    if action == "open":
        return api.call(
            "POST", f"/dashboards/{name}/open", {"version": a.get("version")} if a.get("version") else {}
        )
    if action == "delete":
        return api.call("DELETE", f"/dashboards/{name}")
    raise CommandError("The action is save, open or delete.")


@command(
    "analyze_theme_remove",
    "Remove one of the user's imported Analyze themes",
    req("id", "The theme's id."),
)
def analyze_theme_remove(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/analyze/themes/{_q(a['id'])}")
