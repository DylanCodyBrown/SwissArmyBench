# Analyze: the analyses and their board

The rail's Analyze page: a toolbar of every analysis, one guided form, and a board where every result lands
by itself. The user's form, your tools and `sab.analyze` in Python read the same contracts through the same
checker, so what you run is what the user would.

## Run an analysis: read its contract, then analyze_run
1. `analyze_contracts` (or the resource swissarmybench://analyze/contracts): each analysis's data contract.
   `slots` say which kinds of column each takes (number, whole number, date, text category, yes/no), how
   many, and the checks (never an identifier; at least two values; spans orders of magnitude...); `table`
   says the shape ("one row per order"); `options` have defaults; `sample` is a made-up table that fits.
   Ids: profile, check, benford, fit, together, outliers, odds, predictors, regression, whatif,
   time_series, forecast, tie_out, key_finder, and `blade:<name>` for each of the user's own analyses.
2. `analyze_check(table)`: Check this table: every analysis ranked (`status`: now, fixes or no; `reason`),
   the three that suit it in `top`. With `analysis`: that one's check: per slot the columns that fit and
   the ones that do not with why, what is `missing` in one sentence, and `fixes`.
3. `analyze_run(analysis, table)`: columns and options are picked by the app unless you give them
   (`columns` by slot key, `options` by option key). Its cards land on the Analyze board, as the user's do,
   and `result` holds the numbers. A table that does not fit is refused with why and the form as it stands
   (`plan`). `analyze_plan` shows the picks and the sentence without running.
- `analyze_tables`: the toolbar and the open tables; `table` is a grid id or a table's name, and defaults to
  the one Analyze last used. `analyze_column(table, column)`: the analyses a column fits.

## Make it fit: fixes are grid steps
- A fix (`analyze_check`'s `fixes`) is one plain sentence with its count and `steps`: text read as numbers
  or dates, a month column, the ten most common values and Other, blanks left out, values above zero, a
  yes/no column, totals per month or per key. `level` needed: the slot has nothing without it; better: it
  runs, this improves it.
- Apply one with `steps_add(grid, kind, params)` from its `steps`, or `analyze_fix(analysis, table,
  fixes=[id])`; `analyze_run(..., apply_fixes=true)` adds the needed ones and runs. The user sees each as a
  step in the steps strip and can undo it; the original rows never change. Say which fix you applied.

## A result's actions
- `analyze_runs`: this session's runs; with `run` and `show`: inputs (to run again with changes), math (the
  step-by-step proof), code (the analysis as Python: one `swissarmybench.stats` call) or grid (its table in
  a new tab). `analyze_cancel(token)` stops a run started with that token.
- `analyze_sample(analysis)`: the contract's made-up sample opened as a table; `analyze_run(sample=true)`
  runs on it.

## Reading results
- Read `effect` as well as `p`. A range that includes 1 (an odds ratio) is not clearly different; under 30
  rows is rough. An outlier is a question, not proof. Say what goes together, not what causes what.
- Forecasts: give the range and what it assumes. Regression: use `predictors` first to choose; `whatif`
  takes each predictor's value as the option `value:<column>`.
- The lower-level tools stay for what the form does not ask: `column_fit_test` (shares, another grid),
  `column_outliers` (threshold, show or exclude), `analyze_odds`, `analyze_predictors`,
  `analyze_regression`, `analyze_predict`, `analyze_time_series`, `analyze_forecast`, `analyze_code`,
  `analyze_proof`. They answer you only: nothing lands on the board.

## The board (cards, dashboards, themes)
- Called the Sandbox until 2026-11-16 and Visualizations until 2026-11-19: a `sandbox_*` or
  `visualizations_*` name still runs its `analyze_*` tool for one release (not listed; the chart's code is
  `analyze_chart_code`); `sab.visualizations` is `sab.analyze` with a warning.
- `analyze_formats` lists every card kind with an example: read it before drawing.
- `analyze_add(kind, ...)`: `chart` (a spec on a grid; the server aggregates), `note` (markdown), `table`
  (sql over a grid, or rows of its own), `diagram` (Mermaid), `graphviz`, `plotly`, `echarts`, `image`, or
  a saved `file`. A plotly or echarts card with `grid` and `sql` follows the grid's steps. `key` names a
  card: the same key replaces it in place. `size` is {"w": 2-12, "h": 3-30}.
- `analyze_update`, `analyze_delete`, `analyze_list`, `analyze_all`, `analyze_select` (a click on a chart's
  mark: adds the filter step), `analyze_chart_code` (a chart's Altair Python).
- `analyze_dashboards` lists saved dashboards and their versions; `analyze_dashboard` saves, opens or
  deletes one. `analyze_theme` lists, sets or proposes a theme; `analyze_theme_remove` removes one.
- A short note card on what you changed and why: the user reads the board, not your transcript.

## Python
- `sab.analyze.benford(df)`, `sab.analyze.odds(df, column="region", outcome="late")`,
  `sab.analyze.forecast("orders", horizon=3)` (an open table by its name runs in the app),
  `sab.analyze.check(df)`, `sab.analyze.contract("benford")`, `sab.analyze.sample("benford")`, and
  `sab.analyze(fig)` for a card. `blades_analyses`, `blades_run_analysis`: the user's own analyses.
