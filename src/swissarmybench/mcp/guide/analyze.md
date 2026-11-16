# Analyze and Visualizations

## The Analyze menu (each on a grid's view, after its steps)
- `analyze_defaults` first: which columns are identifiers (never a measure) and the first number.
- `analyze_shape(grid, analysis)`: does the table suit it (a wide table needs unpivoting).
- `column_fit_test`: chi-square fit. `expected`: even, benford or benford2 (first digits of amounts,
  with Nigrini's conformity), grid (another grid's column), shares, together (two columns related?).
  Read `effect` as well as `p`. Over 200 values: bucket first.
- `column_outliers`: look=amount (robust by default; `by` judges each group) or look=frequency (values
  seen far too often or too rarely). `show=true` adds the step that keeps them.
- `analyze_odds`: each value's share; with `outcome`, its rate and odds ratio with a range. A range
  that includes 1 is not clearly different; under 30 rows is marked small.
- `analyze_predictors`: which columns go with a target, strongest first. Keep one of each `redundant`.
- `analyze_regression`: linear, or logistic with `outcome`. `analyze_predict` answers what-if from its
  `model`; its `steps.miss` added with steps_add, then column_outliers, finds rows it cannot explain.
- `analyze_time_series`: trend, season, periods that stand out, steps in the level.
  `analyze_forecast`: trend and season continued, with ranges and a held-back check. Give the range,
  and what it assumes.
- `analyze_code`: an analysis as Python for the user's notebook (one `swissarmybench.stats` call).
  `analyze_proof`: a result as a step-by-step proof (Show the math).
- `blades_analyses` and `blades_run_analysis`: the user's own analyses (topic blades).
- Say what you found in words: what goes together, not what causes what. An outlier is a question,
  not proof. Leave decisions to the user.

## Visualizations (the rail's second area: one dashboard of cards for every table)
- Called the Sandbox until 2026-11-16: a `sandbox_*` name still runs its `visualizations_*` tool for one
  release (not listed), `sab.sandbox` is `sab.visualizations` with a warning.
- `visualizations_formats` lists every card kind with an example: read it before drawing.
- `visualizations_add(kind, ...)`: `chart` (a spec on a grid; the server aggregates), `note` (markdown),
  `table` (sql over a grid, or rows of its own), `diagram` (Mermaid), `graphviz`, `plotly`, `echarts`,
  `image`, or a saved `file`. A plotly or echarts card with `grid` and `sql` follows the grid's steps.
  `key` names a card: the same key replaces it in place. `size` is {"w": 2-12, "h": 3-30}.
- `visualizations_update`, `visualizations_delete`, `visualizations_list`, `visualizations_all`,
  `visualizations_select` (a click on a chart's mark: adds the filter step), `visualizations_code` (a
  chart's Altair Python).
- `visualizations_dashboards` lists saved dashboards and their versions; `visualizations_dashboard`
  saves, opens or deletes one.
- `visualizations_theme` lists, sets or proposes a theme (kept only if the user keeps it);
  `visualizations_theme_remove` removes an imported one. The grid keeps its own theme.
- A short note card on what you changed and why: the user reads Visualizations, not your transcript.
