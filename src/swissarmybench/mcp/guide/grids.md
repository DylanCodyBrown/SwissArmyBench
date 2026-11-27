# Tables and steps

The Tables page: one tab per open table (Analyze, ERD and Workbench are the rail's, left); + makes a
table from a query. Over the table, the Application row (Settings, Connections, Blades), then
the ribbon's Table and Column rows. A cell's tools are on its right-click menu. Under the title, the
steps strip counts the table's steps; Edit steps opens them in a tab of their own.

## Data in
- `datasets_load(name, path)`: CSV, TSV, Parquet, JSON lines, Arrow or an Excel sheet, by full path
  (`datasets_sheets` lists a workbook's sheets). Pass the path, never the contents.
- `datasets_paste(name, text)`: a copied table. `tabs_new_query(name, sql)`: one SELECT over the open
  tables as their tabs show them; `tabs_new_connection_query(name, connection, sql)`: one on a connection,
  in its own SQL. SQL is written only on the Scripts page (the owner, 2026-11-24): the Tables page's + (and
  New query with no table open) opens a new .sql file there; `workbench_sql(action="run", path)` runs one as
  the table named after the file, `workbench_sql(action="for_table", table)` is a query's table's Edit in
  Scripts (its .sql file). `app_navigate(to="new_sql")` (old: new_query, query) is the +.
- `datasets_sample`: the made-up sample store (customers, products, orders; free names): the empty pages'
  Try it with sample data.
- From Python the user calls `sab.push(df)`. `datasets_python_sessions` lists running Pythons and their
  tables; `datasets_open_from_python` asks one to send a table.
- `connections_open_table` opens a database's, file's or Power BI table (topic connections).
- `datasets_rename`, `datasets_close`, `tabs_create_grid`, `tabs_close_grid`, `tabs_cancel`.
- `tabs_reopen`: the last closed tab again (the user's Ctrl+Shift+T), its steps kept; a closed table is read
  again from its file.
- A table read from a file is watched: `datasets_list` says `changed_on_disk` when its file changed since.
  `tabs_reload` reads it again in place (its tabs and steps kept); `not_now=true` keeps it as it is. Nothing
  reloads by itself.

## Reading
- `tabs_get`: columns, every step with its index and id, settings, the view's row count.
- `table_profile` (`dataset=` for a table no tab shows), `column_profile`, `table_header_stats`.
- `column_values`: a column's values with their row counts, most common first (`search`, `limit`, `upto`):
  the Filter form's checklist. Pick from it, then `table_filter` with `op: "in"`.
- `cell_selection_stats` leaves id-like columns (`order_id`, `CustomerKey`) out of Sum and Average (`id_like`
  names them) and gives `digits` to show each to its scale. `table_export` takes `format: "md"` (a Markdown table).
- `row_read(format="csv", start, end)`: the rows as the user sees them, up to 1,048,576 a read; it
  starts with `row_count`, so page with start and end. `cell_view` gives one long value.
- `steps_run_sql`: one DuckDB SELECT; `grid` is the view after its steps, an open table by its name is
  that table as loaded. `CREATE TABLE x AS SELECT ...` (or `steps_save_result`) keeps the result as a
  new table with its own tab.

## Changing (each change is a step the user can see, switch off or undo)
- Table row: `table_filter`, `table_sort` (up to three keys), `table_group_by`, `table_distinct`,
  `table_clean_text`, `table_matching` (how text compares).
- Column row: `column_sort` (a header click; stays the last word), `column_keep`, `column_remove`,
  `column_rename`, `column_bucket` (dates by unit, numbers by edges or width), `column_categorize`,
  `column_unnest` (a LIST column: a row per item; a STRUCT: its fields as `<column>.<field>`; a SQL step).
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
- `app_screen(window)`: what the user is looking at right now, as text, read from the app's memory (no page
  is asked, nothing waits): every window in brief, the focused one first, or one in full by its id, `focused`
  or its kind. Its page and address, the open tab and document (path, kind, unsaved), the cursor's line and
  the selected lines, the open panes and dialogs by title, a showing error's or notice's words, and the page's
  own part: the table in front (name, columns, steps by kind and column, sort, filter, the selected cells by
  row and column number, the rows on screen, the row count), a notebook's cell in focus and the cells on
  screen, the Canvas's page, selection and layout, Analyze's form and cards, the selected connection, the
  Settings section. Names only, never a cell's value: read values with `row_read`. Read it when you need to
  know what the user sees, instead of asking for a snapshot; also the resource swissarmybench://screen.
- `app_navigate(to, pop)`: with `pop`, a page or a table in a window of its own, as the user's Pop out button.
  `pop="out"` pops `to` out (a page: home, connections, catalog, tables, erd, analyze, environment, settings…; a
  table: `grid:<id>`), opened by the main window last in front (a browser may block a window no click asked for:
  then it is back in its place after 30 s); `pop="reattach"` brings it back to its old place and closes its
  window; `pop="show"` brings its window to the front; `pop="list"` says what is popped out (`popped`: key, name,
  address, connected) and how many main windows are open. One owner at a time: where it was, the main window
  shows "<name> is open in its own window" with Reattach. `app_screen` says it: a popped-out window's `pop_out`,
  the others' `popped_out` and the `placeholder` a window shows.
- `app_snapshot(area)`: a PNG of what the user sees (app, ribbon, grid, steps, analyze or projects:
  the Projects page while it is open); the page's tab must be visible. It shows real values and is audited.
- `app_rail(labels)`: the rail's names on or off (kept). `files_list`: a folder's files (`hidden` too); `files_new_folder`: a new folder in one. A system file dialog is the user's click only: pass paths to commands directly.
- `app_navigate(to, window, new_window)`: move a window as the user does. `home` and `projects` (the mark,
  the rail's first item: the Projects page, every project as a card; `start`, its old name, still works),
  `back`, `forward`; the rail's areas from any window: `tables` (only the open tables; `grids` is its old word), `analyze`, `erd`, `notebooks`,
  `scripts`, `apps` (the Workbench in that kind's mode; `new_window=true`: a Workbench window of its
  own; each lands on its kind's page of documents), `blades`, `connections` (the Connections page),
  `session` (the Session page), `settings` (the Settings page); `connection:<name>` (a connection's detail: where it is used, its
  configuration, its calls); the home window's `query`, `grid:<id>`; `add_connection`, `add_api`.
  The Scripts page's Blades pane (`window="scripts"`): `blade:<name>`, `new_blade` (a connection's tables: `connection:<name>`).
  Views are in the page's address, so the user's Back undoes your move too.
- `app_session(who, limit)`: the Session page's log, newest first: what you made or changed this session
  (who=agent, the default; user; both), each entry's words, area and object (an open table, a card, a
  relationship, a connection, a cell), names and counts only. `follow`: whether the user follows you (each
  of your actions brings its area to the front, the object highlighted). It is the user's switch: you
  read it, never set it. Work so it reads well: one change per call, the object named.
- `agent_events`: wait for the user's next change instead of polling. `app_shutdown` stops the server.
