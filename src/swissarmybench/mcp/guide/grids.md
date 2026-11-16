# Grids and steps

The grid page: one tab per open grid (Visualizations, ERD and Workbench are the rail's, left); + makes a
table from a query. Over the grid, the Application row (Settings, Connections, Blades and catalog), then
the ribbon's Table and Column rows. A cell's tools are on its right-click menu. Under the title, the
steps strip counts the grid's steps; Edit steps opens them in a tab of their own.

## Data in
- `datasets_load(name, path)`: CSV, TSV, Parquet, JSON lines, Arrow or an Excel sheet, by full path
  (`datasets_sheets` lists a workbook's sheets). Pass the path, never the contents.
- `datasets_paste(name, text)`: a copied table. `tabs_new_query(name, sql)`: the + tab, one SELECT over
  the open tables as their grids show them.
- From Python the user calls `sab.push(df)`. `datasets_python_sessions` lists running Pythons and their
  tables; `datasets_open_from_python` asks one to send a table.
- `connections_open_table` opens a database's, file's or Power BI table (topic connections).
- `datasets_rename`, `datasets_close`, `tabs_create_grid`, `tabs_close_grid`, `tabs_cancel`.

## Reading
- `tabs_get`: columns, every step with its index and id, settings, the view's row count.
- `table_profile` (`dataset=` for a table with no grid), `column_profile`, `table_header_stats`.
- `row_read(format="csv", start, end)`: the rows as the user sees them, up to 1,048,576 a read; it
  starts with `row_count`, so page with start and end. `cell_view` gives one long value.
- `steps_run_sql`: one DuckDB SELECT; `grid` is the view after its steps, an open table by its name is
  that table as loaded. `CREATE TABLE x AS SELECT ...` (or `steps_save_result`) keeps the result as a
  new table with its own grid.

## Changing (each change is a step the user can see, switch off or undo)
- Table row: `table_filter`, `table_sort` (up to three keys), `table_group_by`, `table_distinct`,
  `table_clean_text`, `table_matching` (how text compares).
- Column row: `column_sort` (a header click; stays the last word), `column_keep`, `column_remove`,
  `column_rename`, `column_bucket` (dates by unit, numbers by edges or width), `column_categorize`.
- Cells and rows: `cell_keep`, `cell_exclude`, `row_limit`, `row_highlight`, `row_select`. You cannot see
  the user's selection: name the columns and values.
- Any step: `steps_add(grid, kind, params)` (`steps_kinds` has the vocabulary; indexes count from 0),
  `steps_edit`, `steps_delete`, `steps_toggle`, `steps_move`, `steps_put` (the whole list),
  `steps_undo`, `steps_redo`. `steps_apply_sql` adds one SELECT step over the table entering it (by its
  name, or `grid`). `steps_counts` gives the rows after each step.
- Code: `steps_python` gives the steps as one verified DuckDB query over the user's table by its
  name, and the Python line that runs it. The same query is the table's read-only cell in the
  Workbench (topic workbench).

## The page
- `app_snapshot(area)`: a PNG of what the user sees (app, ribbon, grid, steps or visualizations); the page's
  tab must be visible. It shows real values and is audited.
- `app_panels`: Settings' panel switches (all on at each start). `files_list`: a folder's files.
- `app_navigate(to, window, new_window)`: move a window as the user does. `home` (the mark), `back`,
  `forward`; the rail's areas from any window: `grids` (= home), `visualizations`, `erd`, `notebooks`,
  `scripts`, `apps` (the Workbench in that kind's mode; `new_window=true`: a Workbench window of its
  own; each lands on its kind's page of documents), `blades`, `connections` (the Connections page),
  `session` (the Session page), `settings` (the Settings page); `connection:<name>` (a connection's detail: where it is used, its
  configuration, its calls); the home window's `query`, `grid:<id>`; `add_connection`, `add_api`.
  The blades page (`window="catalog"`): `catalog:<name>/<schema>/<table>`, `blade:<name>`, `new_blade`.
  Views are in the page's address, so the user's Back undoes your move too.
- `app_session(who, limit)`: the Session page's log, newest first: what you made or changed this session
  (who=agent, the default; user; both), each entry's words, area and object (a grid, a card, a
  relationship, a connection, a cell), names and counts only. `follow`: whether the user follows you (each
  of your actions brings its area to the front, the object highlighted). It is the user's switch: you
  read it, never set it. Work so it reads well: one change per call, the object named.
- `agent_events`: wait for the user's next change instead of polling. `app_shutdown` stops the server.
