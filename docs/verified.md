# Verified (plan section 17)

What has actually been checked, against which version, and how. Anything not listed here is
still an assumption. Last updated 2026-10-23.

| # | Item | Status | Result |
|---|---|---|---|
| 1 | AG Grid Community | Verified, 36.2.0 | The infinite row model (`IDatasource.getRows` with `startRow`, `endRow`, `sortModel`; `successCallback(rows, lastRow)`) works with server windows. `refreshInfiniteCache()` refetches in place keeping sort and scroll; `purgeInfiniteCache()` is needed when the column set changes, or stale rows briefly show the new column as blank. Custom header components (`IHeaderComp`, `progressSort`), `rowSelection: {mode: "multiRow"}`, `ensureColumnVisible`, `setColumnsVisible` all work. Themes use the theming API; color params accept CSS variables (`"var(--bg)"`), so one theme object follows all four page themes. Columns outside the viewport are not rendered (column virtualization). Filters: AG Grid's own filter UI is not used; filters are server steps. MIT license. To size its scroll area, AG Grid measures the tallest div the browser allows by growing a bare div appended to `<body>`; in a flex-column body that div shrinks, AG Grid reads 1,000,000px and switches every table over 31,250 rows to "stretched" scrolling (a wheel notch skipped hundreds of rows). `grid.css` keeps direct children of `body` from shrinking. |
| 2 | DuckDB | Verified, 2.0.0 | `enable_external_access=false` blocks `read_csv`, `COPY`, `ATTACH`, `INSTALL` and reading Python variables by name; explicitly registered Arrow tables still load. `lock_configuration=true` blocks later `SET`. `temp_directory=''` turns spilling off; an over-memory query fails with `OutOfMemoryException` and the connection keeps working. `trim(s, chars)`, `ltrim`/`rtrim` accept a character list. Backslashes are literal in strings. `LIKE ... ESCAPE '!'` works, but a backslash escape character cannot escape itself (`'a\b' LIKE 'a\\b' ESCAPE '\'` is false), so the engine uses `!`. `lower()`/`upper()` map one character to one (`upper('ß')` = `ẞ`, `lower('İ')` = `i`, `upper('ﬁ')` = `ﬁ`; Python gives `SS`, `i̇`, `FI`); the generators copy DuckDB. `date_trunc` returns TIMESTAMP even for DATE input (cast back). `date_trunc('week')` starts on Monday. `stddev_samp`, `quantile_cont` (linear) and `median` match pandas. `rowid` of a freshly created table is dense 0..n-1. A GROUP BY alias whose expression contains `?` parameters can fail to bind ("must appear in the GROUP BY clause"); histogram queries inline their two numbers and group by position. Default `memory_limit` was 25 GiB; the server sets twice the data budget (at least 256 MiB). |
| 3 | MCP library | Verified, mcp 2.3.0 | `mcp.server.mcpserver.MCPServer` with `@server.tool(description=...)` and `run("stdio")`; transports stdio, sse, streamable-http. The launcher is a separate stdio process calling the grid server over HTTP, so no routes are mounted into the MCP app. |
| 4 | Arrow data exchange interface | Verified | The push client converts pandas (`Table.from_pandas`), Polars and other objects with `__arrow_c_stream__` (`pa.table(obj)`), DuckDB relations (`to_arrow_table()`) and lists of dicts, with pyarrow 26. Dates keep their type end to end. |
| 5 | sqlglot | Verified, 30.24.0 | Parses the DuckDB dialect for the SQL box subset; WITH clauses live under the `with_` argument (not `with`) in this version; table functions parse as `exp.Table` with a function `this`. |
| 6 | VS Code | Verified, 1.143.0 | "Simple Browser: Show" opens the integrated browser as a real Chromium page (not an iframe); the grid, WebSocket, panel and title all work. Older versions use a sandboxed iframe and append `?id=&vscodeBrowserReqId=`; the page reads the grid id from the path and the token from the fragment, so both work. `tools/vscode_check.py` reproduces the check. Debugger-variable menu: not checked (VS Code extension not built). |
| 7 | Licenses and sizes | Verified | AG Grid Community MIT; Monaco 0.57 MIT; Vega 6.4, Vega-Lite 6.5, vega-embed 7.3 BSD-3-Clause; xlsxwriter 3.3 BSD-2-Clause; DuckDB MIT; pyarrow Apache-2.0; sqlglot MIT; Starlette and uvicorn BSD-3. Bundles (2026-11-15): main 1.4 MB (loads with the page), charts 0.83 MB and Monaco 4.4 MB (the Workbench's editors and the "+" tab's SQL box share it; each loads on first use). The release wheel is 5.9 MiB (19.5 MiB unpacked). Check the company's open-source policy before wider sharing. |
| 8 | Company policy on sending client data to an AI service | Not checked | A connected agent sees cell values (the privacy levels were removed on 2026-11-12), so check this before connecting an agent to client data. |
| 9 | Windows sandbox options | Not checked | Milestone 9 is not built. |
| 10 | Excel export | Verified | xlsxwriter `in_memory` mode (constant_memory would write temp files, against the no-disk default); `strings_to_formulas=False` writes `=1+1` as a string cell; integers over 15 digits stay exact as text; the row limit (1,048,576) and cell limit (32,767) are enforced with messages; round trips read back with openpyxl. CSV formula neutralization prefixes an apostrophe. Parquet round trips keep types, nulls, time zones and provenance metadata (pyarrow, snappy or zstd). |
| 11 | Resource limits | Verified | See item 2 for memory. `Content-Length` is checked first and the body is counted while streaming (Starlette `request.stream()`); Arrow and Parquet decode batch by batch so a 16 MB table compressed to under 200 KB is refused at 1 MB. `pyarrow.Table.nbytes` measures size cheaply. |
| 12 | uvicorn and asyncio sockets | Verified, 2026-11-12 | A listening socket made with the default protocol (0) is not recognised as TCP by asyncio, which then never turns Nagle off on accepted connections: every request on a kept-alive connection (how the page fetches windows while scrolling) waited about 40 ms for the client's delayed ACK. `server/lifecycle.py` creates the listener with `IPPROTO_TCP` and sets `TCP_NODELAY`: `/health` 44 ms → 0.33 ms, a 100-row window 48 ms → 4 ms. |

## Performance (plan section 14), measured 2026-10-21

`tests/test_performance.py`, 1,000,000 rows x 10 columns (78.6 MiB), through the full app on
this machine:

| Measure | Result | Target |
|---|---|---|
| Push (Arrow) | 0.15 s | |
| First window | 6 ms | 300 ms |
| Sort, then the first window | 320 ms | 500 ms |
| Filter step, then the first window | 117 ms | 500 ms |
| Profile of one column | 93 ms | 1 s |
| Jump to row 500,000 after the filter | 4 ms | |

A chart over 1,000,000 rows sends at most 5,000 points (`tests/test_cards.py`).

## Other checks

- uvicorn 0.54 on Windows serves from a socket bound and listening beforehand
  (`Server.run(sockets=[...])`).
- `SO_EXCLUSIVEADDRUSE` stops a second socket from binding the server's port even with
  `SO_REUSEADDR` (`tests/test_lifecycle.py`).
- On Windows the venv's `python.exe` is a launcher that starts the real interpreter as a child,
  so `Popen.pid` is not the server's pid; the connection file records the real one.
- Playwright 1.64 drives the installed Edge (`channel="msedge"`) with no browser download.
- `uv run` re-syncs the environment first, which fails while a server started from
  `swissarmybench.exe` holds that file; run the server with `python -m swissarmybench.server`
  during development.
- DuckDB keeps an ordered input's order through `row_number() OVER ()` (checked on 3,000,000
  rows with 8 threads: an `ORDER BY` subquery and a filtered ordered table, five runs each, no
  row out of place). A SQL step relies on this to number its rows; a query with no defined
  order (GROUP BY, DISTINCT, joins, windows, set operations, CTEs) is wrapped in `ORDER BY ALL`
  first, so the grid and the generated code agree run after run.
- (2026-11-12, DuckDB 2.0.0, pandas 3.0.6) For the copied query, on a 3,000,000-row pandas frame
  read by name with 8 threads, three runs each: `row_number() OVER ()` numbers the frame's rows in
  order; `ORDER BY k` alone is **not** stable (ties came out of order every run), while
  `ORDER BY k, row_number() OVER ()` matched pandas' stable sort; an ordered CTE keeps its order
  through a later CTE's WHERE and projection, and through LIMIT. A window function is allowed in
  ORDER BY. `SET disabled_filesystems = 'LocalFileSystem'` on the default connection blocks
  `read_csv`, `COPY`, `ATTACH` and `https://` reads but still reads Python variables by name
  (unlike `enable_external_access=false`), and `lock_configuration` then stops it being undone.
  DuckDB 2.0 relations have no `fetchone()`, and `.arrow()` returns a RecordBatchReader, so the
  copy uses `.to_arrow_table()` for Arrow pushes (tests/test_copied_code.py,
  tests/test_golden_codegen.py).
- DuckDB conversion errors quote the cell value ("Could not convert string 'North' to
  INT32"). Until the privacy levels were removed (2026-11-12) an agent below level 2 got a
  generic message instead; now everyone gets DuckDB's own text.
- Headless Edge shares the real Windows clipboard with the desktop, so the copy test captures
  what the page writes instead of reading the clipboard.
- AG Grid Community 36 has no range selection; the Excel-style selection is drawn with cell
  classes, and AG Grid's own Ctrl+A / Ctrl+C handling is pre-empted with a capture-phase key
  listener.
- (2026-10-23) A grid view's SQL, with its own WITH clause, works as a CTE inside another query
  once per table read (the "+" tab joins two tabs' views; `tests/test_query_tables.py`).
  `cursor.sql(q).to_arrow_table()` skips the extra copy that `execute(q).to_arrow_table()` makes,
  and `cursor.interrupt()` still stops it (the timeout test). AG Grid 36 shows its no-rows overlay
  with zero columns (the "+" tab's blank grid).
- (2026-10-23) Three pushes in a row with no window open opened three windows: each landed before
  the first window's page had connected its WebSocket. Reproduced with the real client and server
  (`webbrowser.open` stubbed), fixed in `LiveUpdates.shown_or_opening`, then one window.
- (2026-10-24) A SQL step's text runs unchanged in the user's Python: `duckdb.sql("SELECT ... FROM
  orders")` finds a local pandas frame named `orders` by DuckDB's replacement scan and returns the
  grid's rows in the grid's order (`tests/test_sql_step_and_selection.py`). The generated pandas
  and plain code register the step input under the name the query reads, and verify.
- (2026-10-24) `count(DISTINCT row(a, b))` counts a blank as a value of its own (`row(c)` gave 4
  where `count(DISTINCT c)` gave 3), so the Key Finder's most distinct combination treats NULL as
  GROUP BY does. One greedy round over 49 two-column combinations of a 400,000-row, 50-column
  table took 0.76 s, so the whole build (at most 8 rounds) finishes in seconds.
- (2026-10-24) `test_lifecycle.py::test_start_status_second_start_and_stop` timed out once in a
  full run (its 10 s start wait, under the browser tests' load) and passed alone, 11 of 11.
- (2026-11-12) SQL guard escapes, DuckDB 2.0.0 and sqlglot 30.24: a CTE name passed the table
  check anywhere in the query, but DuckDB scopes CTEs, so `SELECT * FROM (WITH ds_x AS (SELECT 1)
  SELECT 1), ds_x` read the raw table ds_x (also vc_ cache tables, duckdb_tables, duckdb_columns,
  pg_settings, sqlite_master). A non-recursive CTE's own name in its body is the real table
  (`WITH ds_x AS (SELECT * FROM ds_x)`), and so is a WITH RECURSIVE self-reference outside the
  recursive side of a UNION. `LATERAL json_execute_serialized_sql(json_serialize_sql('...'))` ran
  any SELECT, because sqlglot keeps a LATERAL function out of its Table nodes. The guard now renames
  every CTE to `__sab_cte_<n>` by scope, refuses every table-only function, and checks DuckDB's own
  parse (`json_serialize_sql`) of the rewritten query (`tests/test_sql_guard.py`).
- (2026-11-12) Engine hardening, DuckDB 2.0.0: DuckDB matches table and column names without
  case, so "ds_orders" is also the table of a dataset "Orders" (a push of "orders" replaced it)
  and a CTE or subquery renames a second "y"/"Y" to "y_1"; a column named rowid hides the rowid
  pseudo-column (every window came back empty). `CAST('...+05:00' AS TIMESTAMP)` drops the
  offset; TIMESTAMPTZ keeps the instant. GROUP BY binds a column before a select alias of the
  same name (profiles now group by position). A DROP while another cursor's query reads the
  table does not disturb that query (MVCC); a lookup between them fails, hence the view cache's
  leases. Fetching a TIMESTAMP WITH TIME ZONE value into Python (`fetchall`) needs pytz, which
  the server's dependencies do not include: such a column fails every window and profile
  (to_arrow_table does not need it). Not fixed: adding pytz is a dependency decision.
- (2026-11-12) Measured on 1,000,000 rows x 10 columns (`tests/test_performance.million`), at
  the engine, with a filter and a sort step, before -> after: column profile 589 -> 44 ms, text
  column profile 634 -> 65 ms, table profile 1556 -> 112 ms, header numbers 296 -> 79 ms (they
  read the view cache, `ViewEngine.reading`, instead of every step and the final sort); Key
  Finder pairs against 333,334 rows about 1.7-2.2 s -> 1.0-1.2 s; SQL box `SELECT * FROM grid
  LIMIT 100` 94 -> 6 ms; CSV export 6.2 -> 2.1 s (byte for byte the same); Excel export 50 ->
  45.6 s (xlsxwriter's own writes and close are the rest). `tests/test_performance.py` after:
  first window 13 ms, sort 247 ms, filter 51 ms, profile 39 ms.
- (2026-11-13) Measured through the full app (test client) on 2,000,000 made-up rows x 10 columns
  with a filter and a sort step (1,600,000 rows in view), 4 cores, before -> after. The Sandbox's
  five charts (`GET /cards`): 1,446 -> 157 ms the first time, 18 ms after (a chart reads the view
  cache, a grouped chart is one query, points are kept by view key and spec). Copy as code (DuckDB),
  checked against the grid: 18.6 -> 9.5 s. Compare against 1,000,000 rows: create 531 -> 396 ms,
  diff mode 3,427 -> 1,511 ms, a window of 200 rows 33 -> 15 ms (the same counts, rows and order
  in every mode). Key Finder against three other grids (1,000,000 rows): 5.7 -> 4.2 s. CSV export:
  6.2 -> 4.5 s, byte for byte the same over 128 option sets on every column type. A 294 MiB Arrow
  push: 172 ms and one copy of the table less (`pa.BufferReader`, not `io.BytesIO`). Agent describe:
  357 ms, then 2 ms until the table is pushed again. Measured and left alone: find predictors as
  one quartile query and one GROUPING SETS query (edges 160 -> 154 ms, cells 187 -> 126 ms of about
  550 ms: not worth a second code path).
- (2026-11-13) DuckDB 2.0.0 and pyarrow 26: `x IN (SELECT unnest(?))` with a list parameter reads
  only the row groups the values fall in, where 200 literals in `IN (...)` scanned the table (22 ms
  -> 4.5 ms on 1,600,000 rows). `Array.to_pylist()` on a date32 column makes a Python date a value
  (1.4 s for 1,600,000); `cast(pa.string())` gives the same ISO text in 0.1 s for days a Python date
  holds (0001-01-01 to 9999-12-31; past them `to_pylist` raises OverflowError, as before). A dataset
  closed and opened again under its name is version 1 again: view keys carry `DatasetInfo.serial`.
- (2026-11-12) Agent tool sweep (`tests/test_tool_sweep.py`): all 88 MCP tools through the MCP
  server's `call_tool`, at levels 0-3, with sensible and hostile arguments, against the sample
  store on a real port: 706 cases pass in about 75 s. Found and fixed on the way: 500s from a
  malformed step's description and from sqlglot's TokenError (an unclosed quote), a raw exception
  from `table_export` options, the column tracer counting `rowid` in `SELECT *` (every stepped grid
  untraced), and DuckDB error text at level 2 quoting a hidden column. sqlglot 30.24.0 qualifies a
  whole-row reference (`to_json(t)`) as `exp.TableColumn` and `#1` as `exp.PositionalColumn`;
  `server/level_zero.py` treats both as untraceable.
- (2026-11-12) Excel export, xlsxwriter 3.3.0, 1,000,000 rows x 10 columns (ints, floats,
  text, a date, a timestamp, a boolean), at the engine: 59.0 -> 21.9 s. Half the time was
  xlsxwriter's per-cell write calls and half its row-by-row XML loop at close(); the data sheet's
  cells are now written as XML directly (`export._SheetData`) and xlsxwriter writes every other
  part. Every part of the file but docProps/core.xml (its creation time) is byte for byte the same
  as with the per-cell calls (`tests/test_export_hostile.py`, and the 1,000,000-row file compared
  part by part). Of the 21.9 s, zip's deflate of the 389 MB sheet XML takes 9 s; level 1 would
  take 2 s but make the file 30% larger (56 -> 73 MB), so the default level stays. Format indexes
  depend on the order xlsxwriter first writes each format (row by row), and shared strings on
  the order of write calls (header, then each batch column by column); both are kept. A sheet
  with 16,385+ columns used to lose the extra columns silently (xlsxwriter returns -1 past XFD);
  it is refused now. DuckDB 2.0.0's ORDER BY over a very wide result is slow whatever the row
  count: `SELECT <4,000 columns> FROM t ORDER BY rowid` takes 2.4 s on 3 rows (SELECT * without
  the ORDER BY 0.09 s), and 16,390 columns took 47 s for every view request (rows and exports).
- (2026-11-12) Copy as Python (Altair), Altair 6.3.0 with vl-convert, pandas, DuckDB 1.4 in a
  clean virtual environment: the copy put column names into Altair's shorthand (`"col:on:N"` is a
  syntax error there, `a.b` reads a nested field, a `"` ended the Python string) and handed Altair
  the whole frame, which it refuses over 5,000 rows (MaxRowsError). It now runs the grid's own
  chart query over the frame with DuckDB (`charts.spec.chart_query`) and encodes the plain columns
  x, y, y2, color, bin_start and bin_end. All 24 chart kinds and options of the probe table (dates,
  time zones, 1850-9999, nulls, unicode, HUGEINT sums, +-1e300) ran and rendered to SVG, from a
  DuckDB `.df()` frame and from `pd.read_parquet` (dates as objects); on a 1,000,000-row frame a
  900-bar chart took 0.7 s and a scatter 0.2 s (5,000 sampled points). The tests run the copy with
  a recording stand-in for altair (not a dependency) and compare its points with the card's.
- (2026-11-12) Catalogs (engine/catalog.py), DuckDB 2.0.0: a 500,000-column catalog (40 schemas,
  20,000 tables) loads in 0.6 s; its schemas list in 18 ms, one schema's tables in 4 ms, one table's
  columns in 2 ms, a word search in 45 ms and a dotted (schema.table) search in 24 ms. DuckDB 2.0
  refuses `unregister` (ResourceInUseException) on a cursor whose last result was read with
  `fetchone()` and not to the end: the engine reads with `fetchall()` before touching the cursor
  again.
- (2026-11-12) Blades: Python's ModuleNotFoundError names only the top level it could not find
  (`snowflake` for `import snowflake.connector`), so the blade runner maps it back to the import as
  written before naming the pip package. `sqlite3.connect(path)` makes a new, empty database when the
  path is wrong, so the SQLite starter opens `file:...?mode=ro` with `uri=True`, which fails plainly.
  keyring 25 on a Linux container with no Secret Service gives `keyring.backends.fail.Keyring`; the
  blade store says plainly that secrets need a vault and suggests a secret or vault blade instead. A
  module attribute and a subpackage of the same name collide (`sab.blades` was the `blades` package
  once it was imported), so the package is `blade_core`.
- (2026-11-12) The notebook behind SAB, marimo 0.25.2 (server/notebook.py, routes_notebook.py):
  `marimo edit <folder> --headless --base-url /marimo --token-password-file - --no-skew-protection`
  starts in about 2 s and is served through SAB's own address (HTTP with `http.client` on worker
  threads, `read1` so server-sent events flow; websockets relayed with `websockets`). marimo accepts
  `Authorization: Bearer <token>`, so the proxy adds it and the browser never sees marimo's token. Skew
  protection needs a `Marimo-Server-Token` header the proxy cannot know, and SAB serves marimo's own
  page anyway, so it is off. A second viewer may join a running notebook as a kiosk
  (`/marimo/ws?session_id=<new>&file=<nb>&kiosk=true`): it is sent `kernel-ready` with the cell ids
  and codes, and a `create-cell` document change it posts to `/api/document/transaction` (with
  `Marimo-Session-Id` = its own id) appears in the person's open notebook and is saved. A kiosk may
  not run cells ("This connection is read-only for this action"); `/api/home/running_notebooks`
  gives the notebook's own session id, which may.
- (2026-11-12) Portable blades, release 1.4.0 (blade_core/portable.py, server/blade_store.py,
  routes_catalog.py, web/src/bladeLibrary.ts): every one of the 35 starters writes to a `.blade.py`
  file and reads back to the same blade, through `tomllib` on Python 3.12; names, descriptions and
  commands with quotes, backslashes, `'''` and newlines survive (a multi-line literal string when it
  is safe, a JSON-escaped basic string otherwise). A header that does not open the file is not a blade,
  so a module that mentions the marker in a docstring is left alone. Import of a file whose code writes
  a marker file never ran it, neither in review nor on Import. A blade folder skips `.venv`, `venv`,
  `node_modules`, `site-packages`, `__pycache__`, hidden folders, build and dist, and stops four levels
  down. Saving a folder blade rewrites its own file. In Chrome for Testing 153 through Playwright: the search
  matches a tag and a description, tag chips narrow and widen the list, a pinned blade comes first and
  stays first after a reload, a dropped name clash offers "keep both" first and saves "Bakery DB 2",
  and Export downloads `orders_app_db.blade.py`. Full suite: 1,356 passed.
- (2026-11-12) The agent makes blades, release 1.5.0 (routes_agent `/agent/blades`, commands
  `blades_list`, `blades_templates`, `blades_create`): a proposal waits for the user's Allow and is
  saved only then; the approval shows the blade's whole `.blade.py` file and the packages it imports that
  are missing. Refused before the user is asked: a secret's value, a taken name (in any letter case),
  code that is not Python or makes no variable, an unknown kind. A `folder` or `path` from the agent is
  ignored (the blade is kept by the app; the blade folder stayed empty). `blades_list` carries no code,
  catalog command or secret names. In Chrome for Testing 153: the approval window opens on the blades
  page with the code, and Allow saves it into the list. The tool list is 95 tools, 21,040 characters
  (cap 24,000). Full suite: 1,371 passed.
- (2026-11-12) Fill in your values, release 1.6.0 (blade_core/fill.py, `/blades/inspect` settings,
  `/blades/fill`, import `fill`): settings are found in 33 of the 35 starters (the 1Password and blank
  starters have none). Every setting of every starter, changed alone, is written back with every
  other setting and the rest of the code unchanged, and is found again at the same place. ast's columns
  are UTF-8 byte offsets: a setting after "Café" in a comment is written at the right place. Lines are
  counted on newlines only (str.splitlines also splits on form feeds). A raw-string path stays raw; a
  value a raw string cannot end with (a trailing backslash) is written as an escaped string; a backslash
  in a plain connection string (`db01\SQLEXPRESS`) is written doubled and found again. Refused: `;` or
  quotes in a connection-string part, a line break, a word for a number, a stale setting id. Passwords,
  tokens and keys are never settings, and no password environment variable is ever suggested. In Chrome
  for Testing 153: the import review marks host, dbname and user as needing a value, a suggestion button
  fills the field, and Import writes the values into the saved blade's code; on the save screen a
  changed setting rewrites the code box. Full suite: 1,431 passed.
- (2026-11-13) The Sandbox, page part (aiPanel.ts, lazy/plotly.ts, lazy/echarts.ts, lazy/graphviz.ts,
  lazy/svgSafe.ts, the grid page's Content Security Policy). In Chrome for Testing 153: Plotly 4.2.0,
  ECharts 6.1.0 and Graphviz (@viz-js/viz 3.31.0) cards draw, and the page requested nothing outside
  127.0.0.1 while a Plotly figure named an outside picture, an ECharts option an outside symbol and
  graphic image, and a DOT node a javascript: URL (the SVG kept no outside link). A Plotly map trace,
  text that is not JSON and an image that is not inline say so instead of drawing. With the policy, an
  injected <img onerror> handler does not run; the whole suite passes under it (Monaco, snapshots,
  Vega, the live socket). Dragging a card's corner grip grows it on the grid and the chart redraws
  taller; the arrow keys resize it and the size is kept after a reload. A card not resized fills its
  row; a small Mermaid diagram keeps its own size. A drawn Vega chart resizes in place (view.width /
  height), so a click while the page settles lands on the live marks. Full suite: 1,439 passed.
- (2026-11-13) The Cosmic Python refactor merged (fast-forward, 13 commits): 1,502 passed here too,
  ruff, format, mypy (strict, 150 files) and the TypeScript check clean; the 1.6.0 wheel built from it
  installs as a uv tool and passes the smoke test (the plain client, the server, the notebook).
- (2026-11-13) Tangs and the relationship finder (domain/relationships.py, services/relationships.py,
  adapters/state_files.py, relationshipsDialog.ts). On examples/sample_store.py the finder returns
  exactly the answer key's ten joins (the two-column returns -> order_lines key, customers.home_store
  text to stores.store_id number, orders.ship_date's second path to calendar inactive) and none of the
  six decoys, over HTTP and in Chrome for Testing 153. The greedy key search alone picked unit_price
  (a float, the most varied column) into order_lines' key; it now searches key-like columns only. A run
  of the accepted joins: nine hold, orders -> customers holds with orphans (90.9% match, 201 values).
  A tang saved into a shared (blade) folder is listed, as Shared with its author, tags and ten joins,
  by a second server pointed at the same folder, and applies there. Plain JSON, another program's
  JSON, a newer format and a malformed tang are refused with their reason. Full suite: 1,547 passed.
- (2026-11-13) Packs (domain/packs.py, adapters/packs.py, services/packs.py, routes_packs.py, the
  Packs window in bladeLibrary.ts). This repository's `.claude-plugin/marketplace.json` passes
  `claude plugin validate .` (Claude Code 2.1.323), with warnings only for the plugins' missing
  `version`, left out on purpose so every commit is an update. The sample-store pack copied into a
  made-up Claude folder's plugin cache and listed in its `installed_plugins.json` is found as
  `sample-store@swissarmybench`, with its blade (source pack, read-only) and its tang (where pack, ten
  joins); run against the pushed sample store, nine hold and orders -> customers holds with orphans
  (90.9%), the same as the tang saved by hand. A plugin switched off in `enabledPlugins` adds nothing;
  a plugin with no blades or tangs is not a pack. In Chrome for Testing 153, a pack blade opens
  read-only with Save a copy, and New marketplace plus Add to pack write a marketplace that takes
  saved blades.
- (2026-11-13) The tour (tour.ts), in Chrome for Testing 153, light and dark: the New here? bubble
  shows on a first visit and never again once the tour is opened (localStorage, so per browser); each
  card's spotlight surrounds its control (the grid's tab, Relationships, Blades and catalog) or the
  card sits in the middle when the control is off screen; the arrow keys and Escape work; five game
  rounds end on the score knife. Full suite: 1,563 passed (one older test listed the Application
  row's buttons exactly and now lists the four row buttons).
- (2026-11-13) The fit test and outliers (domain/analysis.py, services/analysis.py,
  routes_analysis.py, analysisDialog.ts). The chi-square p-value matches the textbook critical values
  (3.841 with 1 degree of freedom is 0.05, 11.07 with 5 is 0.05, 15.51 with 8 is 0.05) to 1e-9, and an
  even degree of freedom's closed form (100 with 10: 5.45e-17). DuckDB's `mad()` is the median absolute
  deviation (unscaled) and `printf('%.14e', x)` gives the first significant digit correctly rounded
  (9.9999999999999999 is 1.0e+01). On made-up invoices: log-uniform amounts fit Benford (p 0.68, close
  conformity) and evenly typed ones do not (p < 0.0001, nonconformity, w 0.62); region against late
  is related (Cramér's V 0.88); the three planted unit costs are the only outliers within vendor V2,
  and Show these rows keeps exactly rows 30, 1030 and 2030 in the grid's order; frequency finds the one
  misspelled region. In Chrome for Testing 153, light and dark.
- (2026-11-13) The Analyze menu, phase A (Plans/analyze-menu.plan.md): odds, find predictors,
  swissarmybench.stats, the three result actions. domain/stats.py matches printed tables: t (2.228 with
  10 degrees of freedom, 2.0096 with 49, 3.169 with 10 at 0.01), F (4.103 for 2 and 10, 2.5336 for 5
  and 30) and normal quantiles to 1e-12. Odds by hand: 20 of 100 against 10 of 100 is an odds ratio of
  2.25, Woolf's range 0.9943 to 5.0916. On made-up orders (West late 40% against 10%, office a copy of
  region): West's odds ratio 4.85 (4.16 to 5.65), clearly above 1; predictors of amount rank units and
  price strong and the categories none, skip the order number as an identifier; predictors of late put
  region moderate, size weak, and office as saying the same as region (Cramér's V 1.0). The notebook
  code (the steps as checked SQL, then the stats call) run on a plain pandas DataFrame gives the
  window's results for all four analyses, to 1e-9 (sums in another order differ in the last digit).
  A JSON push takes pandas' split shape, not records (Open as grid sends that). In Chrome for Testing
  153: odds, Test together, find predictors, Open as grid, Send to Sandbox and Exclude these.
- (2026-11-13) The Sandbox as a report and the regression (Plans/sandbox-report.plan.md,
  Plans/analyze-menu.plan.md phase B). Cards keep the server-side order, size and new-page flag; Plotly,
  ECharts, Graphviz and image cards are accepted from the server (they were refused before). Page view
  printed through Chromium's own print engine gives landscape letter pages on light paper with the
  charts drawn and no controls; notes measured at their page width grow so no table row is cut. The
  markdown export embeds Plotly figures as PNG (Plotly.toImage) and Mermaid drawings as PNG or, with HTML
  labels, as SVG. Playwright's simulated mouse drag does not raise HTML drag events in the Sandbox's
  scrolled panel; the tests fire the browser's own DragEvents (and use Move earlier). Regression on
  made-up orders with planted effects: linear recovers units 3.005 (3), West +19.93 (+20), East -4.88
  (-5), equal to numpy's least squares to 1e-9; logistic recovers West's odds ratio 4.52 (e^1.5 = 4.48)
  and units 0.021 (0.02) in 5 rounds; what-if gives 99.8 (100) and a chance of 0.498 (0.5). pandas'
  missing numbers arrive as NaN, which DuckDB does not count as blank: rows with a non-finite number
  in a used column are left out and counted. The Data shape check finds a wide table (jan_, feb_,
  mar_ sales), identifiers and Benford's range (on the values above zero). t quantiles match the
  printed table (2.228 for 10 degrees of freedom).
- (2026-11-13) Time series and forecast (domain/timeseries.py). On made-up monthly sales (trend of 10 a
  month, December +34%, February -20%, a 60% spike in June 2021, a +300 step in January 2023), over 200
  seeds with and without the step: the step found within a month of January 2023 every time it was
  planted and never otherwise, the spike always found, 2 of 200 series with one false flag. December
  reads +31%, February -20%. The forecast with the step built in: trend 10.5 a month, next month 2,036
  against a true level of about 2,020, held-back miss 3% (4% without the step). Show these rows keeps
  exactly the four sales of June 2021 in the grid's order. The notebook code reproduces the window's
  words for both.
- (2026-11-13) Catalog completion against real IPython 9.18.1 (a throwaway environment with the plain
  client): with a running server and a made-up catalog, `shell.Completer.complete()` on
  `conn.sql("SELECT * FROM ord` gave order_lines and orders, on `pd.read_sql("""\nSELECT orders.cu`
  gave orders.customer_id, and on `x = ord` (not SQL) nothing. IPython 9 still runs
  `Completer.custom_matchers` (the first matcher API), which ipykernel uses for Jupyter too.
- (2026-11-13) Connections and the SQL cell (Plans/workbench-and-connections.plan.md). The Connections
  window in Chromium: a CSV connection added through Browse… (the server lists the folder; a browser's
  own picker hides the path), named after the file, Test said "a file of 27 bytes" before saving, and
  the saved one listed under Files with its `sab.connection` and `%%sql` lines. A draft's typed password
  reaches the test run and never its error text; a missing path fails the test ("is not there"). The
  SQL cell in real IPython 9.18.1 against a real server: `%%sql Shop -> totals` on a SQLite connection
  gave the DataFrame and kept it; `%sql_connect` on a CSV connection, then a bare `%%sql`, read the file
  through DuckDB; a bad column stopped the cell with one line (`UsageError: Shop: OperationalError: no
  such column: nope`); Tab in the cell gave the CSV's own column. DuckDB lists a registered DataFrame as
  a temporary view in main, so one query finds files, sheets and tables alike.
- (2026-11-14) The Workbench (Plans/workbench-and-connections.plan.md) in Chromium against a real server
  and real IPython kernels (jupyter_client 8.10, ipykernel 7.4): opened from the grid page's tab in its
  own window; a Python cell printed and drew a DataFrame, a SQL cell on a CSV connection totalled by
  region through DuckDB; saved as .ipynb (the SQL cell as `%%sql Orders`), closed, reopened from Recent
  with its outputs; a script ran in its console and a typed line answered. Kernels use Unix sockets in a
  private folder off Windows (a relative socket name was read from two working folders and the kernel
  never answered). Completion: the first on pandas takes about 4.5 s (Jedi reading it; the kernel warms
  its completer at start), then 0.06 to 0.6 s. Sent the whole cell, Jedi reads `rainfall =
  pd.DataFrame(...)` as code and misses the live columns; the cursor's line alone gets them. A SQL
  cell's names come from the connection's catalog before any kernel runs. A new environment with uv
  and pandas took 5.8 s; the kernel ran in it with pandas 3.1.1 and `swissarmybench` lent from the client
  copy. Password sources: an environment variable and a new vault entry both rewrote the code's
  secret() name, and a saved connection lists the vault it runs first.
- (2026-11-14) Every connection by its name in the Workbench: an IPython AST transformer reads the names
  a cell uses before it runs and opens a connection only then (checked in a real IPython shell: one
  connection opened, a user's own variable of the same name kept, a failing one said why and the cell
  raised NameError). In Chromium a cell ran `pd.read_csv(orders)` on a CSV connection with no
  sab.connection line. With the suggestion list open, Monaco took Ctrl+Enter for the list and the cell
  never ran; the run keys are now caught first and close the list.

- (2026-11-14) The Workbench stress test's kernel findings, each now a test (tests/test_workbench.py) on
  real IPython 9.18.1 kernels: Run file is `%run` (so `__name__ == "__main__"`, `__file__`, `sys.argv`,
  `asyncio.run` and a spawn `multiprocessing.Pool` all work; an unsaved script runs from a private
  copy); `input()` asks the page and the answer goes back on the stdin channel (the agent's runs have no
  stdin and get StdinNotImplementedError at once); Interrupt cancels runs queued behind the one it
  stops; Restart ends the run under way; `os._exit` is reported as a dead kernel and the kernel is
  dropped; an error no longer drops the next queued run (`stop_on_error=False`); a thread printing after
  its run ended shows with the next run, marked late. IPython catches SystemExit before any custom
  handler, so `sys.exit(3)` is quieted by wrapping `showtraceback` (one line: "The code ended with
  sys.exit(3)."). The pager hook is read when the shell starts, so `display_page = True` set later did
  nothing; setting the `show_in_pager` hook (priority 90, before ipykernel's 99) makes `len?` an output.
  Saving keeps a UTF-8 byte-order mark, CRLF line endings, a latin-1 coding line and the file's mode; a
  file with no write bits is refused as read-only unless forced (as root `os.access` always says yes).
  Connection names never hide a builtin (`Print` becomes `print_`), and a cell that assigns a name
  never opens the connection of that name. One misbehaving object costs its own row in Variables.
- (2026-11-14) The Workbench's page fixes from the stress test, in Chromium against real kernels
  (tests/e2e/test_workbench_page.py): 6,000 flushed prints drew as they came (the run took seconds; it
  froze the page for over 100 s at 5,000 when every record redrew the run) with the newest 5,000 lines
  shown and the rest counted; colour codes show as colours and each `\r` writes over its line; `input()`
  is answered in a box in place; `os._exit` says the kernel stopped; Ctrl+Enter on a `for` line ran the
  whole block, then the next statement; the console took a block over two lines (Enter on an unfinished
  line adds one, an empty line runs it); F5 outside the editor ran the file and the kernel kept its
  variables (the browser would have reloaded); a deleted cell came back with Undo; a reload brought back
  an unsaved script and notebook (session storage only). Monaco's `insertText` re-indents what it
  inserts (a test typing a `for` block got the next line inside it), so tests with exact indentation
  open a written file.
- (2026-11-14) The Workbench's four panes (RStudio's skeleton) in Chromium: a notebook's own console
  answered `21 * 2`; the palette inserted a cell by typing "insert below"; command mode's B, D D, Z and
  M acted on the selected cell; a splitter moved by the arrow keys; Ctrl+Shift+1 showed the source
  alone; an SVG a script displayed gathered in Plots; F1 on `len` showed its help; the agent's
  `workbench_window` made a notebook, inserted and ran a cell (42), read the documents and the cells,
  and ran a line in the console. Monaco's `addCommand` registers in one keybinding service shared by
  every editor on the page: without a context key of the editor's own in the condition, the console's
  Enter ran in a notebook cell (the newlines typed there vanished) and the last cell's Escape answered
  for every cell. With two Workbench windows open, both answered a command and the wrong one could win;
  commands now go to the window last in front (it says so on focus, as a VS Code window does). A cell
  added from the toolbar took the focus 50 ms later even after a click into another cell, splitting
  typed text between two cells (the flaky notebook test); the focus now goes as soon as the editor
  exists, unless it moved meanwhile.
- (2026-11-14) The error panel against real kernels (tests/test_errors.py, tests/test_workbench.py,
  tests/e2e/test_workbench_page.py): a KeyError inside a function named the key, listed the dict's keys,
  offered the close one, and stack_data gave `region` = 'nroth' and the subscript's columns (17 to 30,
  1-based, as Monaco counts); `df.loc[..., 'amont']` lists the table's columns (pure_eval reads no
  properties, so the table before `.loc` is evaluated); pandas' compiled frames name their source
  relative to the package (`pandas/_libs/index.pyx`), which resolved against the working folder and
  counted as the user's own file until relative and `.pyx` names were made library frames; an earlier
  error that never touched the user's code (pandas' inner KeyError) is left out of the chain. A 0.6
  close-name cutoff offered 'south' for 'nroth'; 0.7 keeps real typos ('north' 0.8, 'total' 0.89). In
  Chromium a script's KeyError was explained, its line marked with the message at its end, and "Use
  'amount'" fixed it; a notebook's missing `np` got its import with one click and the cell ran. Monaco
  draws no injected text after an empty range: the end-of-line message sits on the line's last
  character. The grid page's wide-column scrolling test failed once under the full suite's load and
  passed three runs alone (a timing flake, not a change).
- (2026-11-14) The owner: "The bottom right pane isn't needed, it goes to the sandbox. Let's add a right
  click an error or highlight code and right click to send to an agent. It will send via hook in the
  MCP." The Plots and Help pane is gone (Variables has the right column; F1 help is a card over the
  source); a picture's Send to Sandbox made an image card titled after the script. Send to the agent:
  the error panel's button and right-click, and the editor's right-click (the selection, or the error
  under the cursor) post to an inbox kept in memory; `swissarmybench-context` (now shipped in
  plugin/hooks/hooks.json: the README named the hook but the plugin had no hooks file) prints what
  waits with the next prompt and marks it read; the `agent_inbox` tool reads it too. Monaco's context
  menu ignores a click that comes as it opens (the right button's release), so the browser test waits
  before choosing; a right-click outside a selection moves the cursor, so it right-clicks the selection.
  A new environment now needs a full path: the tool sweep's odd folder names ("x", "nope-does-not-exist")
  had made virtual environments in the app's own folder. The grid page's scroll and Key Finder tests
  failed once each under the full suite's load and passed twice alone.
- (2026-11-14) Beta 1.7.0b1, checked before the build: ruff, format, mypy (227 files), the TypeScript
  check, and the suite: 1,963 passed in the full run; the grid page's wide-column scroll test and the
  Key Finder's percent test failed in that full run (as in the run before), yet all 130 browser tests
  passed when run on their own (`pytest tests/e2e`) and each of the two passed twice alone. A
  load-order flake of the full run, not of the app; left open in docs/ideas.md.
- (2026-11-14) The 1.7.0b1 wheel (7.0 MB, `python build.py`) installed with its own `install.sh` as a uv
  tool on Linux, then tools/smoke_install.py against the installed server: ten made-up tables pushed and
  arrived, the page served, blades and a catalog, copied code verified, To Python and sab.paste(); and,
  new in the smoke test so every release checks it: a Workbench kernel in the tool's Python ran code
  (42), a failed run came with the error panel's reading ("Use 'north'"), and a Send to the agent came
  back through the installed `swissarmybench-context` prompt hook. Not tried here: Windows and macOS
  (the release workflow installs on Windows), and the VS Code extension.
- (2026-11-14) The beta's Workbench drew Monaco without its styles in a clean build: its page linked
  build/workbench.css, which only an old build had left in the folder (a clean build has the editor's
  styles in build/lazy/codeEditor.css). The first 1.7.0b1 wheel sent to the owner had that defect; the
  page now links the real file and the smoke test fetches every file each page links (it named
  /static/build/workbench.css for the first wheel). The two browser tests that failed only in full runs
  were real: the Key Finder's search on opening could answer after the user's own search and replace it
  (the window now keeps only the newest answer), and the scroll test aimed at a fixed point. The owner's
  "rid the app of over explanatory text and instructions that are in the gui": help paragraphs, how-to
  hints, long placeholders and repeated tooltips came off every screen (the tour, Show the math, the
  Data shape sheets and the error panel's explanation stay). Then: ruff, format, mypy (227 files), the
  TypeScript check, and the full suite, 1,965 passed and none failed; the rebuilt wheel installed with
  install.sh and passed the smoke test, every page's linked files included.
- (2026-11-14) The slim VS Code extension (the owner: "install everything with UV. The vscode
  extension just adds the mcp tools as vscode tools and adds the button to open Swiss army grid"): its
  19 unit tests pass and it packages to a 10 KB .vsix (the old packaging bundled a server wheel and
  failed on the beta's version, 1.7.0b1, which broke the release workflow's build). Against the uv tool
  install: the Open button's code found the tool's Python, started the server and the workspace page
  answered 200, a second press reused it; the MCP command it registers (the tool's Python, -m
  swissarmybench.mcp.server) answered initialize and listed 177 tools. Not run: inside a real VS Code
  (needs a VS Code download).
- (2026-11-14) The release workflow by hand on the branch (run 22; off main nothing publishes, and the
  release and PyPI jobs were skipped): the checks, the tests and the extension's tests passed, the wheel
  and the 1.7.0 .vsix built, and the installers installed the 1.7.0b1 wheel as a uv tool on Linux and
  macOS (install.sh) and Windows (install.ps1); on each the smoke test passed, the Workbench's kernel,
  the error panel, Send to the agent through the prompt hook and every page's linked files included.
- (2026-11-14) Key vaults as connections (the owner: "add an Azure password vault and then map the
  needed secrets in it directly into environment variables", then "Key vaults should be another
  connection, not a blade"). With a made-up vault in plain Python (the Azure starter's shape: names()
  and get()): Read the vault listed four secrets by name with suggested variables and no value in the
  answer, for the user and for the agent; a vault without names() said so; saved with two ticked, it was
  listed among the connections (Key vaults) and not given a Workbench variable; a password's New vault
  made one and came back to the PostgreSQL form with the vault's entry chosen. A Workbench kernel
  started with WAREHOUSE_PASSWORD set to the vault's value (and kept it over a restart), a vault that
  failed was named and the kernel started anyway, the start's answer held the variables' names only, and
  the server's own environment never got the value. Then: ruff, format, mypy (227 files), the TypeScript
  check, the non-browser suite (1,845 passed after one test was made independent of the order), and the
  Workbench and blades page browser tests (31 passed). Not tried: a real Azure Key Vault (no Azure
  account here; the starter's names() uses azure-keyvault-secrets' list_properties_of_secrets).
- (2026-11-14) A vault that loads every secret, each under its own name: with made-up secrets
  (SqlPassword, Sql--Password, api-key, 3d-token) a kernel started with SqlPassword and Sql__Password set
  to the vault's values, Test listed _3d_token, api_key and warehouse_password, a rename (api-key as
  CRM_KEY, warehouse-password as WAREHOUSE_PASSWORD) was the only entry saved and won, a password pointed
  at such a vault took the secret's own name without changing the vault, code with no names() was refused
  plainly, the portable file kept `vault_all = true` with no [vault] table, and the Variables pane listed
  the names it set. In the browser: Every secret is on for a new vault, a box renames, the PostgreSQL
  form came back with the vault and the secret's name still shown after Use it.
- (2026-11-14) The hybrid vault form in the browser: with the code filled in, the three made-up secrets were
  listed with no button pressed, each box empty with the vault's name as its placeholder; a typed name
  (CRM_KEY) was the only entry saved; opened to edit, the list came back at once with CRM_KEY in its box
  and the others empty. The Workbench and blades page browser tests passed (31).
- (2026-11-14) Trino with a linked .pem over SSL (the owner: "make sure the trino supports linking a .pem
  and ssl"). The starter, filled in as the form fills it, run by the app's own runner with the real
  trino client (0.340.0, a scratch environment; not a project dependency) against a made-up Trino over
  HTTPS signed by a made-up certificate authority: with the authority's .pem it connected and signed in
  with the password (BasicAuthentication); a .pem path that was not there and no .pem at all were both
  refused. Two findings that shaped the starter: (1) requests, under trino, prefers REQUESTS_CA_BUNDLE
  (often set on company computers) over the .pem it is given, so the linked .pem was silently ignored;
  the starter now gives trino its own session that ignores that setting (trust_env off), and the check
  passed with REQUESTS_CA_BUNDLE set. (2) Python 3.13 refuses a certificate authority whose certificate
  has no key usage entry (some older company authorities lack it): the made-up one had to carry it.
  Then: the form shows Certificate file (verify) with Browse… for .pem, .crt and .cer, Scheme (https)
  and the Password box; sslrootcert, ssl_ca and ca are certificate files too. The non-browser suite
  (1,854 passed) and the Workbench and blades page browser tests (31 passed).
- (2026-11-14) Sign in and Trust server certificate: each of the six SQL Server and Azure SQL versions read
  as the right fields (the password only for user name and password); in the browser, the SQL Server form
  switched Windows -> user name and password -> MFA keeping the server typed and the trust tick, the
  Password box came and went, and the tick wrote TrustServerCertificate=yes; Trino's tick writes
  trust_server_certificate = True. Not tried: a real SQL Server or Azure SQL (no server or Microsoft account
  here; the connection strings are Microsoft's ODBC Driver 18 keywords). The non-browser suite: 1,858
  passed; the Workbench and blades page browser tests: 30 of 31, then 15 of 15 three times (see ideas.md).
- (2026-11-14) Catalogs that load themselves: a saved CSV connection's catalog arrived with no Refresh
  (the completion's /catalogs had it); on a restart every connection loaded again, a missing file failed
  with its reason on the connection, one whose code signs in with a browser window waited, and its first
  use (the agent's POST) loaded it. In the browser: the Connections window showed "catalog loaded" for a
  new connection by itself, with one list and one set of buttons (an overlap of two redraws had doubled
  them; fixed), and a SQL cell on the folder connection suggested `region` from its catalog before any
  kernel ran. The non-browser suite: 1,863 passed; the Workbench and blades page browser tests: 32 passed.
- (2026-11-14) Round 1 of the usability test's fixes (docs/ideas.md has the findings and the owner's
  decisions). The SQL cell's error entry carries every field a Python error's does (the panel failed on
  "notes"); a cell turned to SQL shows its connection; a connection form tests before it is named; a
  form's Not installed note follows its code; the not-running message no longer says VS Code. A server
  stop with two Workbench kernels open took about 1 second and logged no traceback (4 seconds and three
  cancelled waits before; the test saw 10 seconds and a crash with six); a window's kernels stop a minute
  after it is gone, the agent's never. Find relationships searches open tabs and names a one-to-one join
  once; the crown checks every known join (order_date, the active one, now has it). Step forms open with
  the cursor in the first empty field and Enter adds the step. Then: ruff, format, mypy (228 files), the
  TypeScript check, the non-browser suite (1,868 passed) and every browser test (132 passed). The compare
  bugs (Diff's one-sided jump, the key chosen, a reload ending it) go with round 3's compare work.
- (2026-11-14) Round 2 of the usability test's fixes. Open file beside "+" and a file dropped on the page
  open as grids (a workbook asks which sheets, the first ticked). A catalog table, a connection's row and
  the catalog's right-click open a table as a grid, with its first rows previewed; the grid says "First
  1,000 of 2,500 rows" (the connection's Rows to open) beside Load all rows. A column's right-click starts
  with its own tools (sort, filter, rename, remove, keep only, group by); Rename... on a selected column
  shows its box alone; a double-click renames a header in place. A table is renamed from the Pasted
  toast's box or a double-click (F2) on its tab: the DuckDB table in place, every grid on it with its
  steps, the relationship model, every page (the agent's datasets_rename too; a taken name is refused).
  The Workbench: a table result has Open as grid (Out[n]; a bare variable keeps its name, anything else
  is out_<n>, so `rainfall.describe()` no longer replaced `rainfall`), a notebook's console is a title
  bar until used, and a new notebook has the cursor in its first cell. Then: ruff, format, mypy (233
  files), the TypeScript check, and the whole suite with the browser tests (2,017 passed).
- (2026-11-14) Every table has a read-only cell (docs/ideas.md has the spec and what was decided while
  building). Checked against a running server and a real kernel: a table's cell is the grid's steps as
  one DuckDB query whose result is the table's own name; run three times it gives the grid's rows each
  time; the kernel's watcher did not send the cell's result back (the grid kept its four rows and
  showed three), sent the maker's new data when the maker ran again, and sent the new original when the
  maker and the cell both ran before it looked; a script run as a file ran its table cell the same safe
  way, and the same file run as plain Python made the table and transformed it once. A small paste is
  written out and reads back the same; a file's cell reads the file again in a Python of its own. In
  the browser: the Tables group in a notebook and in a script (folded when a file opens, yellow when a
  cell is out of date, clear again when the grid change is undone), a maker that stays put with its
  link, cell numbers kept through a save, `@cell` links (click and hover), the uses line kept while
  typing with the cursor where it was and no edit after an undo, a saved notebook's steps given back
  to a grid opened again, and the steps strip without Copy as SQL, Copy as Python and To Python.
  Then: ruff, format, mypy (240 files), the TypeScript check, and the whole suite with the browser
  tests: 2,070 passed, none skipped (2,017 before; 53 new). Not checked: Polars tables (Polars is not
  installed here; the output form is tested as text), JupyterLab folding the headings, VS Code folding
  the region, Windows paths in a load.
- (2026-11-14) HTML cells (docs/ideas.md has the owner's decisions and what was decided while building),
  and the owner's rule on confirmation labels applied to table cells and HTML cells. Checked in a real
  browser: an HTML cell shows its HTML (coloured as HTML) while edited and its design when left, with
  no Run; a click inside the design stays in the design; the pane's bottom edge drags and moves with
  the arrow keys, and the height is saved (a notebook's cell metadata, a script's marker) and comes
  back. The design's scripts run; from inside it a remote picture, stylesheet and script did not load,
  fetch failed (to another site and to the app), a socket, a pop-up, a form, a link and a script's own
  navigation reached nothing (a second web server on another port saw no request at all), and the
  parent page, the token in its address, storage and cookies were closed to it. `{{ name }}` filled
  from a real kernel: a number, hostile text shown as text (no element made, no script run), a
  120-row table drawn as "first 50 of 120 rows", an unknown name as a plain marker, a number inside a
  style attribute, hostile text left out of a tag and said, a table as rows inside a script. The cell
  said Not run yet, nothing once run, "Out of date · total changed · last run" when the variable
  changed, Out of date when its HTML changed and nothing again when the edit was undone, Not run since
  opening on a saved file (with its last design), Not run yet after a restart. The uses line
  `<!-- uses sales @cell4 -->` appeared when the table opened and did not make the cell out of date.
  In a script: the design under the marker with the cell's lines put away, the lines back on a click
  on the marker, Run file filling the names, the height written on the marker, and the file still
  running as plain Python. Table cells: no "Up to date", "No steps yet" or "0 steps" anywhere.
  Then: ruff, format, mypy (244 files), the TypeScript check, and the whole suite with the browser
  tests: 2,137 passed, none skipped (2,070 before; 67 new). Not checked: real Polars tables and real
  matplotlib figures (neither is installed here: stand-ins with their methods are tested), plain
  Jupyter or VS Code opening the files, Edge (the tests ran in this machine's Chromium), Firefox and
  Safari (the frame's walls rest on the browser's sandbox and policy).
- (2026-11-14) The cleanup (docs/ideas.md, "Cleanup, 2026-11-14", has each decision). Checked in a
  real browser: the steps window's Code tab shows the one DuckDB copy with Copy as SQL and Copy as
  Python and no language picker, and no "Verified identical" badge; the steps window has no ribbon
  and no pop-out button; the ribbon's rows are Table and Column, and a cell's right-click menu keeps
  rows by the selected value (Keep these, Exclude these); Fit test and Outliers open from a column
  header's right-click menu; an analysis result's Copy code puts `from swissarmybench import stats`
  and the call on the clipboard and says "Copied."; a catalog table's right-click offers Open as
  grid alone; a blade's row has no refresh icon, its save screen refreshes its catalog (asking for a
  secret each time) and the icon beside the picker refreshes it again; the strip says nothing with no
  steps, the status bar has no "live" (and says "not live" when the socket closes) and no meter, a
  connection's row says nothing once its catalog has loaded, a ready kernel shows no state, Ctrl+S
  saves with no toast; the Variables pane has no Connections and blades block and no empty
  Environment, and shows a connection once a cell has opened it; an imported Sandbox theme is removed
  with the button beside the picker, and a built-in theme has no such button; an agent's export
  still opens the approval popup. Over HTTP: a recipe file left in the state folder is not applied
  and not deleted; the removed routes answer 404; `row_read` as CSV, `table_profile` on a dataset
  with no grid argument, `tabs_get` with the view's row count and `steps_run_sql` by table name give
  what the five old `agent_` commands gave.
  Then: ruff, format, mypy (238 files), the TypeScript check, and the whole suite with the browser
  tests: 1,994 passed, none skipped (2,137 before: the pandas and plain-Python runs of every golden
  case, and the tests of the queue, the old blade door, Script as and recipes went with what they
  tested; a few were added). Lines: `src` 37,667 to 36,189; `web/src` 21,896 to 21,744.
  Not checked: Edge (the tests ran in this machine's Chromium); the guide's screenshots, which still
  show the Cell row and the old labels (they were not retaken). One browser test fails now and then
  and did before this work (4 of 12 runs at bf17b95, alone): the HTML cell's "undoing the edit
  clears it by itself". Undo there works only when pressed straight after Edit HTML; a moment later
  the editor no longer undoes the edit, so the cell stays out of date. It passed in the final run.
- (2026-11-15) Round 3 of the usability test's fixes (docs/ideas.md has each decision and what was
  decided while building). Checked in a real browser, each with the user's actions counted:
  **Compare (5):** a tab's right-click offers Compare with…, Rename and Close; with two tables open
  a compare is three actions (right-click, Compare with…, Compare), the key picker opening with
  order_id ticked where it had ticked quantity = quantity; Diff shows the key and the one column that
  differs on both sides, with Only differing columns pressed; switched off, both halves go to the
  first differing column; scrolling either half sideways takes the other with it, by column; a
  column's own button takes both halves to it; after a reload the split, the mode, the counts and the
  rows are back with no key picker, and a stopped compare stays stopped.
  **Analysis (6, 7):** Odds, Outliers, Find predictors and Fit test open on quantity, not order_id;
  Time series and Forecast on the row count; a selected column is used as it is; a regression opens
  with every column but its target and order_id ticked, follows a change of target, keeps a box the
  user changed, and fits on the third action.
  **After sending (8):** Send to Sandbox leaves the window and its result; the toast's Show closes
  the window, goes to the Sandbox and outlines the card; Open as grid closes its window and the new
  tab is in front.
  **Reopen (9):** the status bar has no Datasets button; ≡ opens Tables with the budget's numbers,
  the open tables and the Python sessions; a closed table is back in two actions, the same table at
  the same version with one grid and no copy.
  **Connections (11 to 14):** a file connection is named after a picked or a typed path, tests with
  an empty name and shows its columns and first rows; Install sits beside the driver's command and
  the note goes when the install is done (the install itself was answered by the test: nothing was
  downloaded); Entry in the vault lists a made-up vault's secrets by name with no value anywhere on
  the page, and picking one writes it into the code; Trino, PostgreSQL and SQL Server read server,
  port, catalog or database, then the user and a labelled password, then the certificate and Trust
  server certificate.
  **First save (15):** with the app's folder deleted, Save opened the chooser in it (made, empty)
  and saved in three actions; any other missing folder is still refused and not made.
  **Steps (17):** the strip counts a header sort; hovering the count lists the steps in plain words
  and a step's remove button takes it out; Ctrl+Z walks back through a removal, the header's two
  clicks and the filter, and does nothing (and says nothing) when there is nothing left; Ctrl+Y and
  Ctrl+Shift+Z redo; in a tab's rename box the keys leave the steps alone.
  **Keyboard (18):** Ctrl+Shift+P lists a command for every button of the Application, Table, Column
  and Compare rows, the steps strip and the tab strip (the test compares the list with the buttons on
  the page), the Analyze menu's entries, the tabs and the cell's menu; a command that cannot run is
  greyed with its reason and its keys; a filter, an undo, Keep these, Go to Sandbox, an analysis and
  Compare with… each ran from it with no mouse. Enter and F2 on a cell open the value viewer; on a
  header they do not.
  **Settings (19):** the switch in the grid's corner turns the header profiles on and off, Select all
  still works beside it, Settings keeps the theme and has no profiles checkbox; the Sandbox has no
  zoom of its own and its text grows and shrinks with the Application row's zoom.
  **Relationships (20):** in a 900 by 520 window the diagram shows whole with no scrolling, Actual
  size makes it larger than the window, Fit puts it back, and a smaller window shrinks it; a Key
  Finder row's Add as relationship saves a many-to-one join and crowns the row, and Compare on these
  puts the two tables side by side in the grid window, lined up, with no key picker; Import
  relationships is the one name in the Diagram tab and the Relationships window, and takes a model as
  JSON (applied) or a .tang (reviewed, then applied).
  **Found since:** the HTML cell's "undo works only right after Edit HTML" was the browser's own
  undo, reached when Ctrl+Z was pressed before the editor had the keyboard; the editor's undo was
  never broken (it takes typing back a few words at a time, as in any cell). The test now waits and
  presses Ctrl+Z until the HTML is as it was (8 of 8 runs; it failed about 1 run in 6 before).
  `test_a_connection_is_added_with_a_form_tested_and_saved` failed 3 of 20 runs: the file chooser
  put the first folder's path in front of the path being typed ("/root" + "/tmp/…"), which could not
  be opened. Fixed in the chooser: 25 of 25 runs passed.
  Over HTTP: the identifier rule and the forms' defaults, the suggested key, the compare's
  only_differing (which does not rebuild the mapping), the list of running compares, compare_shown,
  a file connection's test preview, the forms' order, the app's own folder, undo and redo over every
  way steps change, and blades_install's body.
  Then: ruff, format, mypy (244 files), the TypeScript check, and the whole suite with the browser
  tests: 2,064 passed, none skipped (1,994 before; 70 new), twice. 187 commands (183 before:
  analyze_defaults, compare_list, steps_undo, steps_redo). The guide's screenshots were retaken with
  made-up data (all but the blades page's two, which did not change).
  Not checked: Edge (the tests ran in this machine's Chromium); a real driver install from the form
  (the browser test answers the install itself; the route is the blades page's, unchanged); a real
  key vault (a made-up one in plain Python stands in); the palette and the keys on macOS (Cmd is
  read as Ctrl in the code, not tried); Windows paths in a file connection's name (the rule is
  tested as text).
- (2026-11-15) The Power BI dataset connection (docs/ideas.md has the decisions). **Not run against a
  real Power BI tenant:** Power BI's Execute Queries request and Microsoft's sign-in are stood in for
  on this computer (tests/powerbi_standin.py: a made-up model of Sales, Customer, Product and Date,
  three measures, four relationships with one inactive, one of the date tables Power BI makes by
  itself, and errors in the real service's shape).
  **The connection, made from a vault:** a made-up vault in plain Python holds the tenant id, the
  client id and the client secret; the form's picker lists them by name, picking each writes its name
  into the code (`secret("powerbi_client_secret")`), Test connection signs in, and the stand-in
  receives exactly those three values with the right scope and grant; the query carries the token and
  `includeNulls`. None of the made-up values (nor the token) is in any answer to the page or the agent
  (the form, the lists, Test, Refresh, open, preview, the relationships import, two refusals), in the
  audit log or in the connection's saved file.
  **Answers as tables:** `Sales[Amount]` reads as Amount and `[Total Sales]` as Total Sales; whole
  numbers, decimals and Power BI's text dates arrive typed (BIGINT, DOUBLE, TIMESTAMP in the grid);
  a missing value stays missing; a name two tables share keeps its table.
  **DAX:** names quote as `'Order Lines'[Unit Price]`; Open as grid sends `EVALUATE TOPN(10, 'Sales')`
  and `EVALUATE ROW("n", COUNTROWS('Sales'))` (10 of 40 rows shown, the grid told 40), every row sends
  `EVALUATE 'Sales'`; the catalog page's first query is the EVALUATE.
  **The catalog:** four tables, columns with Power BI's types, measures on their own table marked
  "measure, Decimal"; the same from the numbered INFO functions when INFO.VIEW is refused, and tables
  and columns alone from COLUMNSTATISTICS when both are.
  **Messages:** a refused query says Power BI's own words ("Cannot find table 'Nope'"); a wrong secret
  says Microsoft's first line and what to check, never the secret; a wrong dataset id says what to
  check; no server says which one could not be reached; an answer at the row or value limit (tried
  with the limits lowered to 40 rows and 70 values) is refused as not whole.
  **A DAX cell:** `sab.sql` and the `%%sql` magic give a DataFrame, keep it under `-> name`, and say a
  refusal in one line; the uses line does not take `[Total Sales]` or `"Total Sales"` for the table
  Sales, in DAX or SQL.
  **Relationships:** the named and the numbered forms give the same model (many-to-one, "filters both
  ways", the inactive one inactive, the date table's left out); the import merges with the existing
  rules (a one-to-one held before becomes many-to-one and is said; another table's join is kept; a
  second import changes nothing); the Diagram draws an inactive join dashed and labelled; a connection
  that is not a Power BI dataset is refused; the agent may do it (`connections_import_relationships`).
  **In a browser** (one test, 5 runs): the form filled from the vault, tested and saved; the catalog
  with the Model node, the tables and Sales's two measures; Copy the EVALUATE; Open as grid, whose
  message offers Import its relationships; the grid's clean headers and a date; the Diagram with four
  tables, "inactive" and "filters both ways". By hand in a browser: DAX completion offers EVALUATE,
  `'Sales'`, `[Total Sales]` and SELECTCOLUMNS, and no SQL word. The browser sign-in's code was run
  once with Microsoft's real azure-identity (1.27.0) in a scratch environment, the sign-in window
  itself stood in for: it asks for Power BI's scope and reads the dataset.
  **Found since:** `test_a_script_runs_in_its_console` failed once in the whole run (the "row 1" race
  noted on 2026-11-14): the console asked the kernel whether a line was finished before adding the
  new line, so keys typed meanwhile landed on the old line. A line that opens a block or sits inside
  one now gets its new line at once, and an answer for text that has changed since is dropped. The
  whole suite passed after.
  Then: ruff, format, mypy (248 files), the TypeScript check, and the whole suite with the browser
  tests: 2,095 passed, none skipped (2,070 before; 25 new: 24 in tests/test_powerbi.py, 1 browser
  test). 188 commands (187 before: connections_import_relationships).
  Not checked: a real tenant (it needs the admin setting Dataset Execute Queries REST API, service
  principals allowed to use the Power BI APIs with the app registration a member of the workspace, and
  Read and Build permission on the dataset); whether the INFO functions answer through Execute
  Queries for a sign-in with Build permission only; the real names of INFO.VIEW's columns beyond the
  ones read (Table, Name, DataType; FromTable, FromColumn, ToTable, ToColumn, FromCardinality,
  ToCardinality, CrossFilteringBehavior, IsActive), which are from memory of Microsoft's pages; how
  the real service marks an answer cut at 15 MB; Microsoft's sign-in window itself; Edge.
- (2026-11-15) The Streamlit canvas and projects (docs/ideas.md has the owner's words and every
  decision). This replaces Push to page, the page designer window and the Streamlit kind of cell;
  the earlier entry below describes what was there before. Streamlit is still not a dependency: the
  tests that need it use the Python named by SWISSARMYBENCH_STREAMLIT_PYTHON (here Streamlit 1.67.0,
  pandas 3.1.1, pyarrow) and are skipped without it.
  **Rules** (tests/test_streamlit_cells.py, 27 tests): which Python cells call Streamlit (a call
  through `st` or the cell's own name for it, a name imported from it, `with st.sidebar:`; not an
  import alone, not another `st`, not half-typed code); a notebook saved with the Streamlit kind
  opening as Python cells with the code, number and height kept and the pages dropped; a script's old
  `[streamlit]` marker read as a plain cell and written as one; such a cell never the maker of a
  table; Run file leaving the cells that call Streamlit out on the same lines; the app's file both
  ways (the same text back, one block a line, links relative to the file, Windows paths, another
  drive); a linked file's Python cells; pages checked; the grid (rows, a block that would lie on
  another going below, the moved one keeping its place, where a new block goes); titles, makes and
  reads; the run order and a cycle; widget keys; a page as slots first with the gaps as empty
  columns; a missing cell's and a missing file's words; the export; the saved pages importing from
  data.py. **Projects' rules** (tests/test_projects.py, 5 tests): data.py as data.ipynb's code cells
  in order, imported for real in a Python with no Streamlit (a table read from a made-up CSV, its
  step applied); what is left out; code that cannot sit in a function; a pasted or pushed table as a
  stub with no rows written; requirements keeping the user's lines; which files open.
  **On the server** (tests/test_streamlit_apps.py, 16 tests): a document's live cells and their
  state; a canvas over HTTP (place, move, insert a row, resize, pages, another page, remove); Play
  from the file and then from the open, unsaved document; out of date after a cell is typed on, a
  table's step, a layout change; a deleted cell and a deleted file said with the path and number;
  the first linked file's Python, Install, the window and the kernel going; the app's file saved
  with relative links and opened again by the window's route and by the agent; the export folder; a
  new project (data.ipynb, data.py, the canvas, two notebooks, requirements), refused twice; Export
  data.py from an open unsaved data.ipynb; Play writing data.py and importing a variable from it;
  Save as (the zip's listing, no rows anywhere, the project's own pages/ written, a linked file from
  outside the folder, the zip opened again as a canvas and as a project, data.py imported from the
  unzipped folder); every action by the agent's commands; the live pages' door. With the real
  Streamlit: the canvas's page and a live cell run in Streamlit's AppTest (the filter drives the
  total though it sits below it; a grid step, Play, the new total), the process answers through the
  proxy with its websocket, the exported app is started and its pages fetched, and **a saved page is
  run by AppTest from the unzipped project** (it imports its table from data.py, which reads the CSV
  again and applies the grid's step).
  **In a browser** (tests/e2e/test_streamlit_page.py, 4 tests, 3 with the real Streamlit): two
  notebook cells live in their cells with no kind picked; New app; both cells dragged by their
  numbers onto the app's tab; the blocks' words; a block dragged to a row below and both resized with
  the keyboard (the focus staying on the grip); Play showing the page in place, West chosen, the
  total 260 above the filter; Edit; the cell edited in the notebook (not saved), "Out of date · Play",
  Play, the new label; a third cell copied with C and pasted with Ctrl+V on the canvas, and with V in
  the notebook; a second page renamed; Ctrl+S into the file chooser, the file's JSON, close, open
  again; Export into a chosen folder; Save as into a zip (its listing); a linked cell deleted, the
  block red with the path and number. A Python without Streamlit: the cell's note and Install, a
  plain cell running in the kernel, typing `st.write` making a cell live and taking it out making it
  plain, the palette, and the canvas's note and Install after Play. A script saved with the old
  markers and pages block: the markers rewritten plain, the cells live under their markers, Copy the
  cell and paste on a new canvas, Play. A project made from the window: its tabs, data in front,
  the folder's name, a cell typed into data.ipynb in the export.
  Screenshots looked at (2x, made-up data): a notebook window beside a canvas window with a cell
  dragged across and the drop's place shown; the blocks on the grid; the live page; out of date; a
  missing cell; two pages. Seen there and fixed: an app's tab showed "No console" and "No kernel"; after the merge, two
  buttons were named "Save as…" (the canvas's is "Save as zip…" now).
  Then: ruff, format, mypy (267 files), the TypeScript check, the build, and the whole suite with
  the browser tests: 2,282 passed before the Workbench redesign was merged in, and 2,288 passed, none
  failed and none skipped, after it (the canvas as the tab kind "page", its controls in the group's
  row, the project's files in the Data panel). No test failed under load in either run. 224 commands (215 before); the tool list is under its 53,500 budget.
  **Not checked:** a real drag between two browser windows (Playwright cannot drag across windows:
  the canvas was sent the dragover and drop events the other window's drag produces, with the same
  data); Windows (paths are tested as text only); Edge (the browser here is Chromium); the pop-out
  window (its command exists; no browser test opens it); Install itself in a browser; Save as's
  pages inside a user's real multi-page app (one page was run alone by AppTest); a project whose
  data comes from a connection (the entry is the read-only cell's own text, tested for a file, a
  paste and a push); dragging a script's cell (not built: copy and paste); a dark theme's look.
- (2026-11-15) Streamlit cells: pieces pushed to a page designer and linked by shared names
  (docs/ideas.md has the owner's calls and what was decided while building). Streamlit is not a
  dependency: the tests that need it use a Python named by SWISSARMYBENCH_STREAMLIT_PYTHON (here a
  throwaway environment with Streamlit 1.67.0, pandas 3.1.1 and pyarrow) and are skipped without it.
  **Rules** (tests/test_streamlit_cells.py): the cell in a notebook and in a script, both ways, with
  saved pages and layouts (the notebook's metadata, the script's `# %% [streamlit-pages]` block); the
  names each piece makes and reads; the run order, and a cycle said; the page's code (slots first,
  pieces in name order, widget keys of their own, text inside a multi-line string left alone); the
  preamble reading only the tables named; the export's files and requirements.
  **On the server** (tests/test_streamlit_apps.py): pieces and pages over HTTP and by the agent's
  commands; Parquet written for the tables a page names and only when they changed; the out-of-date
  rule (a grid step, the table pushed again, changed code; a header sort and the uses line never
  count); the temporary folder removed on stop, the app stopped with its kernel, its window or the
  server; a Python without Streamlit said, Install into that Python; the export folder; the live
  pages refused without the app's own secret, from another site or host name; the Workbench's frame
  policy unchanged. With the real Streamlit: the process answers through the proxy (pages, health,
  its websocket), the pages run in Streamlit's own AppTest (the filter drives the total though it sits
  below it), a grid step then a run gives the new data, the exported app is started on its own and
  its pages fetched, and the process ends when the server that started it goes.
  **In a browser** (tests/e2e/test_streamlit_page.py, with the real Streamlit): two pieces typed, each
  live in its cell (a selectbox; a total of 145 that follows the selectbox to 260); both pushed to a
  new page; in the page designer the total dragged before the filter and widened to 12 columns with
  the keys, so the filter sits below it on the live page, where choosing West and North changes the
  total; the page renamed; a second page with a piece added from the list; the pages saved in the
  notebook's file; a grid step turns both pieces "Out of date · orders changed" and the designer's
  button "Out of date · Run", nothing running by itself; Run gives the new data (the piece keeps its
  widget's choice); Open app shows the app in its own window, its second page reached from the side;
  Export through the file chooser writes app.py, two page modules, data/orders.parquet,
  requirements.txt and README.txt, and that folder runs with Streamlit alone (its pages fetched, its
  filter driving its total, laid out as designed); closing the notebook removes the temporary folder
  and the app. A Python without Streamlit shows the note and Install (not clicked: it would install
  into this project's environment). A script's Streamlit cells show live under their markers and its
  pages land in its comment block. Screenshots looked at: the code, the piece live, Push to page,
  the designer, the filter driving the total, two pages, out of date, the app's window, the export.
  **Found by the whole suite, and fixed:** (1) a kernel's output was dropped when the server was slow
  to read it (ZeroMQ's limit of 1,000 waiting messages): 6,000 quick prints arrived with lines
  missing from the middle on a busy computer (3 of 6 runs with four busy loops beside the test; 0 of
  8 after). (2) A restart that closed the channels a run was waiting on ended the run's stream with
  no last word; it now says "restarted" (the test waited a second and usually won the race; it now
  waits for the run's output, failed every time before the fix, and passes 6 of 6 under load).
  Then: ruff, format, mypy (257 files), the TypeScript check, and the whole suite with the browser
  tests: 2,181 passed, none skipped (38 new: 21 rules, 14 on the server, 3 in a browser). Without a
  Streamlit Python 4 of them are skipped (2 on the server, 2 in a browser). 210 commands (188 before).
  Not checked: Windows (the process's end-with-the-server watch has its own Windows branch, never
  run); Edge (the browser here is Chromium); Install itself in a browser (it is tested against a
  stand-in runner); uploads and downloads through the proxy; Streamlit older than 1.36 (st.navigation
  is needed) or custom components; a dark theme's look; a notebook whose environment has no pandas.
- (2026-11-15) Power BI per workspace, and the DAX cell (docs/ideas.md has the owner's words and the
  decisions). **Not run against a real Power BI tenant:** the stand-in (tests/powerbi_standin.py) is now
  a workspace of three made-up datasets: Sales model, Budget model (a Date table of its own) and Broken
  model, which answers every query with an error. Checked by tests/test_powerbi.py (36 tests) and one
  browser test (tests/e2e/test_powerbi_page.py):
  **The connection:** the starter is "Power BI workspace"; its form asks for the workspace id and the
  sign-in and has no dataset id; Test connection says "signed in and found 3 datasets"; the three
  sign-ins and the vault are as before, and no secret is in any answer. `conn.datasets()`,
  `conn.dataset(name or id).cursor()` and `conn.cursor(dataset=...)` reach each dataset; `conn.cursor()`
  is refused with the datasets' names when there are several. A connection saved for one dataset still
  loads, opens tables and imports relationships as a workspace of one.
  **The catalog:** each dataset is a schema with its tables, columns and measures; the INFO fallbacks
  work per dataset; the broken dataset is a schema with its reason and no tables while the other two
  load; the cap (25 datasets) leaves the rest marked "Not read". In the browser the broken one has
  the error mark and its page says why.
  **Open as grid:** `EVALUATE TOPN(...)` and the count go to the table's own dataset, with the row
  limit and first N of M; with the catalog loaded, the two Date tables open as `Sales_model_Date` and
  `Budget_model_Date`, and other tables under their own names. The table's cell in a notebook loads it
  with `sab.dax('Finance/Sales model', ...)`.
  **Relationships:** imported per dataset (by name or id), only that dataset asked; the model's tables
  are named as the grids are; several datasets and none named is refused with their names; the broken
  dataset says Power BI's words and changes nothing. In the browser: the offer on the "is open as a
  grid" message imports the Budget model's two, and the Diagram draws Budget, Department and
  Budget_model_Date. The Connections row has no Import button.
  **The DAX cell:** `%%dax` is registered beside `%%sql`; `sab.dax("Finance/Sales model", ...)` gives a
  DataFrame; the workspace alone with several datasets is refused naming them; a SQL connection is
  refused for DAX. A notebook writes and reads a DAX cell as a `%%dax 'Finance/Sales model'` code cell
  (by its first line alone too); an old `%%sql Finance/Sales model` cell reads as a DAX cell; a DAX
  cell gets no uses line. In the browser: the kind picker and the X key make a DAX cell; its picker
  lists only the three datasets (the unreadable one last) and a SQL cell's lists no Power BI
  connection; completion offers EVALUATE, then `'Customer'`, `[Region]` after `'Customer'[`, and
  `[Total Sales]`, each replacing the quote or bracket already typed, never the other dataset's tables
  and never SQL's WHERE; the cell runs and shows four rows; a script's DAX button and the agent's
  command write `# %% [dax]` over one `sab.dax()` call, and the text compiles.
  **The agent:** `connections_datasets`, `connections_import_relationships` with `dataset`,
  `workbench_dax_add`, and `workbench_run` with kind `dax`. 190 commands (188 before).
  **Found on the way, and fixed: a kernel's output could be lost.** In the whole run
  `test_outputs_keep_up_with_many_prints_colours_and_progress_bars` failed once; alone it failed about
  one time in three while other work kept this computer busy, and it failed the same way on the code
  from before this change. A script printing 6,000 lines showed fewer (lines missing from the middle),
  or its run never ended. Cause: ZeroMQ keeps 1,000 unread messages on the reading side and 1,000 on
  the kernel's, a local socket holds little more, and past that the kernel drops what it prints,
  the message that ends the run included. The server's side now has no limit
  (server/kernels.py `_client`). A new test holds it: 6,000 lines printed while nothing reads for five
  seconds all arrive and the run ends (it times out without the fix). The browser test then passed ten
  times in a row under the same load.
  Then: ruff, format, mypy (248 files), the TypeScript check, and the whole suite with the browser
  tests: 2,112 passed, none skipped (2,095 before).
  Screenshots looked at, against the stand-in: the form, the tree with three datasets, the broken
  dataset's page, the Budget table as a grid, a DAX cell with its picker and completion (coloured by
  Monaco's DAX grammar), the Diagram after one dataset's relationships.
  Not checked: a real tenant; whether the datasets list names datasets the sign-in may not query;
  more than 25 datasets against the real 120-queries-a-minute limit; `%%dax` in plain Jupyter outside
  the Workbench (the magic is the same function the Workbench's kernel runs, tested through IPython's
  registration); Tab completion of names inside a `%%dax` cell in Jupyter (sab.complete is SQL's);
  a table opened before the catalog has loaded takes its own name even when another dataset shares
  it; Edge.
- (2026-11-15) A connection from your own Python (docs/ideas.md has the decisions). Made-up data
  only: a tiny web service on 127.0.0.1 (tests/orders_service.py: `http.server`, two made-up tables as
  JSON, answering only to a made-up API key).
  **The variables** (tests/test_python_connections.py, 36 tests): `os.environ["X"]`,
  `os.environ.get("X")`, `os.getenv("X")` and `secret("X")` are each found by name, also `environ` and
  `getenv` imported from os and os under another name; a name built with an f-string or at run time, a
  name in a comment or a string, a variable that is set and not read, and another object's `.get` are
  not. Names come from all three boxes, once; a box that is not Python yet gives none. A source is
  checked (a name the code never reads, a vault with no secret named, a name given twice are refused).
  **The catalog's shape:** a list of dicts and a DataFrame, with table and column alone or with
  schema, type and description; a string, other column names, no rows, a row with no table or no
  column, and code that fails each say what is wrong, the line included.
  **Read a table:** a list of dicts, a DataFrame, an Arrow table and a dict of columns arrive typed;
  `(rows, total)` gives the count; code that ignores the limit has its first rows kept and its count
  known; fewer rows than the limit need no count; a tuple of two rows is rows.
  **The portable file** round trips the three boxes, the mapping and Rows to open, byte for byte; a
  file written before loads as it did; a value saved on this computer is never in the file.
  **Secrets:** a key in an error from either box is starred out; no answer (the list, the form, the
  blade, the export, a Test, a refused Test with a wrong key) and nothing in the state folder holds
  the key; the agent is refused what `sab.connection` is given.
  **Through the real child process:** the starter's own three boxes over the web service, the URL a
  plain value and the key an entry of a made-up vault: Test (2 tables, 3 columns, the first 20 of 30
  rows), a missing variable named before the code runs, a vault that is gone, Save, the list, the form
  again, `connections/{name}/tables`, Refresh, the catalog's schemas and columns, the preview, Open as
  grid (10 of 30, the note's numbers), Load all rows (30, no note), the saved connection's Test. Also
  the key saved on this computer, and both variables from this computer's environment. Over a live
  server: `sab.connection` gives `conn` with only this connection's variables set, and `sab.read`
  reads a table with a limit and a schema.
  **In a browser** (one test, tests/e2e/test_python_connection_page.py): the type under Your own code,
  three boxes in the Workbench's editor, the List and Read boxes typed in, the two variables found,
  one a plain value and one picked from the vault's entries, Test showing rows, Save, the row's own
  Test, the catalog tree, a table's columns with descriptions, its first rows and its `sab.read` line,
  Open as grid with "First 10 of 30 rows", and Load all rows.
  Then: ruff, format, mypy (252 files), the TypeScript check, and the whole suite with the browser
  tests: 2,142 passed, none skipped (2,095 before; 47 new: 36 in tests/test_python_connections.py,
  1 browser test, 10 new cases of the existing sweeps over the three new
  commands). 191 commands (188 before: connections_python_save, connections_python_variables,
  connections_python_tables).
  Three earlier whole runs each had one failure in a test this work does not touch, while other test
  runs loaded the machine (load average 6 to 9); each passes alone:
  `test_outputs_keep_up_with_many_prints_colours_and_progress_bars` (twice; 6,000 prints inside 30
  seconds) and the Power BI page test (once; a 404 from the stand-in after its ids were typed).
  Not checked: Edge (the tests ran in this machine's Chromium); a real key vault (a made-up one in
  plain Python stands in); a real vendor library or web service; code pasted from the clipboard into
  the editor (the test types unindented lines); a connection whose `conn` is a DB-API connection in a
  SQL cell (the SQL cell's own tests cover any `.cursor()`; none was written for this type).
- (2026-11-15) The Workbench redesign (docs/ideas.md has the owner's words and each decision; branch
  `workbench-redesign`). Made-up data only.
  **In a browser** (tests/e2e/test_workbench_groups.py, 5 new tests): Split right by the agent's
  command, Split down from the palette after focusing the first group, the refusal when a group has
  one tab ("only this tab"), only the focused group's row has controls, a splitter moved by keyboard,
  and after a reload the three groups, their tabs, the focused group and the splitter's place; a
  group goes with its last tab. By drag: a tab dragged before the first one reorders the row; dragged
  to a group's right edge the five-way guide shows "Split right" with the ghost tab, and the drop
  splits right; dragged to the lower part of another group it splits down; dropped in the middle of a
  group a group's only tab moves there and its group goes; Escape mid-drag puts it back; a splitter
  dragged by its grip; `tab.moveLeft` and `group.moveTab`. The Data panel: folded by its arrow, still
  folded after a reload, opened by Ctrl+B and `view.toggleSidebar`; "+ Table" → Open file… opens the
  file chooser and the table arrives with "3 rows" and "orders.csv", a step in the grid shows as
  "orders.csv · 1 step", a click on it selects the table's read-only cell; "+ Table" → a connection
  opens its catalog beside the panel with that connection picked, a table there opens its page with
  Open as grid; Escape puts the catalog away; "+ Blade" shows the blades and connections, a click
  elsewhere puts them away. The status bar: hidden while nothing is open, "not started" before a run
  and nothing once ready, the Environment picker, the Kernel menu (Interrupt, Restart; Restart says
  "Restarted"), Console and Variables pressed while open, `view.toggleConsole`; the top bar's name and
  unsaved dot. Every old toolbar action found in the top bar's "…", "+ Cell" (six kinds for a
  notebook, three for a script), Run all or Run file, the Document menu, and "+".
  The existing browser tests that clicked the old toolbar now use the new places (test_workbench_page,
  test_workbench_outputs, test_html_cells_page, test_streamlit_page, test_table_cells_page,
  test_powerbi_page); none was removed. The tables listing's new `source` has a unit test.
  Then: ruff, format, mypy (262 files), the TypeScript check, the build, and the whole suite with the
  browser tests in this machine's Chromium: 2,251 passed, none failed, none skipped.
  Screenshots at twice the size, looked at against the mockup: nothing open, a notebook, its Variables,
  the menus (Workbench, Document, + Cell, + Table, Kernel), two groups, a drag with the guide, three
  groups, the blades beside the panel, the panel folded, the console, the dark theme. Two things found
  and fixed that way: a cell's editor kept the width it was made at when its notebook moved to a
  narrower group (a grid track sized to its content), and the group row's controls lost their words
  in a group of normal width (the narrow rule now starts at 480 pixels).
  Not checked: Edge (Chromium here); the high contrast themes and forced colours; touch (the drag uses
  pointer events, untried with a finger); a window under 1,100 pixels with several groups; how it
  merges with the app pages' branch.
- (2026-11-15) The Streamlit canvas reviewed (docs/ideas.md, "The canvas's review, and four more of
  the owner's asks", has each change and decision), and named cells, the Streamlit cells pane, tabs
  that pop out and move back, and Settings' Panels. Branch `canvas-review`. Made-up data only.
  **Checked that the builder could not:**
  - *A project from a connection* (tests/test_streamlit_apps.py): a made-up SQLite file as the
    connection "Shop", its table opened in the grid with a filter step, New project: data.py reads it
    again with `sab.sql('Shop', ...)` then the step as one DuckDB query (`"amount" > 50`), names the
    connection and never its code, and imports in a Python of its own with no Streamlit (as a
    notebook's kernel), giving the filtered rows (75, 100, 250) through the running server.
  - *The saved pages in a real multi-page app*: the zip unzipped, an `app.py` of the user's own with
    `st.navigation` over `pages/sales_overview.py` and `pages/filter_only.py`, run in Streamlit 1.67's
    AppTest in one session: the first page's metric 100, the filter picked (250), then the second page
    by `switch_page`; no errors, each page's widget keys its own (b2_1, b3_1), data.py loaded once.
    (The exported folder's own app.py was already served by a real `streamlit run`.)
  - *The canvas in the dark theme*: screenshots (2x) of the blocks (a missing cell in red) and of the
    live page after Play, whose frame asks Streamlit for its dark theme; looked at: the canvas's
    colours are the theme's tokens, Edit | Play reads in both. One token the canvas used did not exist
    (`--text`, on its warnings): it uses `--fg` now.
  **The review's fixes, each with a test:** a script linked from the canvas zipped with a pasted
  table's rows (now a stub); data.py keeping pasted rows when a user's cell also made the table; Save
  as writing over and taking away pages/*.py that were not its own (a page of the user's own stays,
  and is said); a linked file from outside the project taking a project file's name in the zip; Play
  failing when data.py could not be written; Edit looking pressed during Play (now one Edit | Play
  pair, `aria-pressed` on the mode in front: checked in the browser test both ways); "Streamlit app"
  in the status bar (now the app's Python, checked by its tooltip, the whole path).
  **Named cells:** a notebook's name in its metadata both ways (with brackets and a hash; one too long
  from another tool dropped; old files without names); a script's on its marker line both ways, with
  the escape for words that read as the marker's grammar, kept through arranging the script again;
  the outline's names; a canvas block and a live cell called by a name. **The pane** over HTTP: an
  open notebook's cells (names sent with the cells) and a project's file on disk, a plain script left
  out, the agent's listing. **In a browser:** two cells named (in the head, and by the palette's
  command), the pane listing them by name, one dragged from the pane onto a canvas, its block showing
  the name and its link by number, the pane's mark, a click going to the cell, the names saved in the
  metadata.
  **Pop out:** on the server, a document handed to another window taken once, its kernel's variables
  kept and its owner moved (the first window gone stops nothing), a move to a named window refused
  to another, a cancel. **In two browser pages:** a notebook with a change not saved and a kernel that
  holds `x = 41` popped out from the tab's right-click menu; the new page has the tab with its change,
  its numbers, its name and its outputs, and `x + 1` gives 42 there; the first page has no copy; a
  cell dropped onto a canvas in the first page (Playwright cannot drag between two pages, so the drop
  is sent with the same data a cell's drag carries); moved back by the agent's command.
  **Panels:** the defaults, a switch set and refused, all on again on a new server, the agent's
  command; in a browser, Streamlit cells, Console and the grid's ribbon switched off in the
  Workbench's Settings and gone there and in the grid page, the console's command refused with its
  reason, still off after reloading both, on again from the grid page's Settings; the Data panel, both
  status bars and the steps strip by the agent's command.
  Then: ruff, format, mypy (273 files), the TypeScript check, the build, and the whole suite with the
  browser tests in this machine's Chromium and SWISSARMYBENCH_STREAMLIT_PYTHON set (Streamlit 1.67):
  2,312 passed, none failed, none skipped (one run; the move-back change to "a main window" came
  after it, and its tests, the Streamlit, panels and Workbench pages and the Workbench's unit tests,
  67, passed again). 228 commands (224 before: workbench_cell_name, streamlit_cells,
  workbench_move_back, app_panels); the tool list's budget raised to 54,500 characters.
  Not checked: Edge (Chromium here); a real drag between two browser windows; a canvas with a running
  Streamlit app moved to another window (it restarts on Play there); a pasted table's rows in a
  script's zip copy beyond the read-only cell's own form; the panels with the high contrast themes.

## The rename to Swiss Army Bench (2026-11-15)

- **Checked:** `tests/test_renamed.py` (24 tests: the variables, the state folder's move and its
  refusals, the old Workbench folder, the keyring on a memory vault, old notebooks, `%%sag` cells, blade
  headers, tangs, Streamlit apps and saved pages, the magics, `import swissarmygrid`, `python -m
  swissarmygrid.server`, the four old commands, the lent kernel copy, the old websocket subprotocol, an
  old HTML cell's output), a browser test of a theme kept under the old storage prefix, and the VS Code
  extension's tests (22, the old variables, state folder and uv tool among them).
- **Installed:** `python build.py` made `swissarmybench-1.7.0b1-py3-none-any.whl` (with `swissarmygrid/`
  inside it). In a made-up home with its own uv tool folders: the old `swissarmygrid` wheel (built from
  e834b27) installed as a uv tool, with a state folder holding a made-up blade; then `install.sh` with the
  new wheel removed the old tool and installed `swissarmybench` with all eight commands. `swissarmygrid
  status`, `sag`, `swissarmygrid-context` and `import swissarmygrid` each said the new name and worked;
  `swissarmygrid start` moved `~/.swissarmygrid` to `~/.swissarmybench` (the blade inside), said so once,
  and a second start said nothing. `tools/smoke_install.py` passed as the release runs it (`uv run
  --with <wheel>`) and with the installed tool's own Python.
- **The whole suite** with the browser tests in this machine's Chromium and
  SWISSARMYBENCH_STREAMLIT_PYTHON set (Streamlit 1.67): 2,336 passed, 1 failed:
  `test_table_cells_live.py::test_in_a_real_kernel_the_cell_runs_twice_and_the_grid_is_not_sent_its_result`
  (the watcher had not sent Run file's table within 20 s while the whole suite ran); it passed in eight
  runs after, alone and with its file. A timing flake under load, as far as seen.
- **Not checked:** Windows and macOS (install.ps1, the mutex, a folder held open by an old server), a
  real keyring, a real Claude Code plugin install from the renamed marketplace, the VS Code extension in
  VS Code itself, and PyPI (the new project name needs its trusted publisher).

## The agent's Streamlit Export waits for the user's Allow (2026-11-15)

- **Checked:** `tests/test_agent_streamlit_export.py` (9 tests). The agent's export waits for the user's Allow,
  and the prompt names the app, the resolved folder (a `..` worked out), the pages and only the tables the
  pages read. Once allowed, it writes that folder, and the audit log shows the user's approval and then the
  agent's export. A Deny writes nothing, and no answer (the timeout made short) is refused with nothing
  written. The agent cannot answer its own request, and the user's own Export asks nothing. A folder that no
  longer resolves to the path chosen (a link put in its place) is refused before anything is written. The
  agent's New project with a pasted table asks; denied, no folder is made. A project of code only (a file's
  load) asks nothing. The agent's Save as asks when it would first write a data.ipynb holding pasted rows:
  denied, no data.ipynb and no zip; a second Save as asks nothing. `tests/test_streamlit_apps.py`'s two
  agent tests now answer the prompts, and they check which actions asked.
- **Browser (this machine's Chromium):** a new test in `tests/e2e/test_streamlit_page.py`. The agent's
  `canvas.export` through `workbench_window` shows the prompt in the Workbench window with the folder and
  `orders`. Deny writes nothing and Allow writes the folder. The user's own Export… click right after it
  shows no prompt. `test_ui.py`'s two grid approval tests, the Streamlit page file and the Workbench page
  file: 31 passed together (with `SWISSARMYBENCH_STREAMLIT_PYTHON` set, Streamlit 1.67).
- **The suite without the browser tests:** 2,166 passed. `ruff check`, `ruff format --check`, `mypy`,
  `npm run typecheck` and `npm run build` were clean.
- **Not checked:** Windows paths in the prompt (resolve on Windows), and the prompt in VS Code's window.

## The starter pack (2026-11-15)

- **Every starter, read and filled:** `tests/test_starters.py`. The 78 files read as blades, pass the
  save check, and write back to the same bytes; each family has the count the guide says. A Python
  starter makes one public function, its variable; a Power BI one's only setting is `WORKSPACE`.
  Placeholders, their kinds and what they follow; a value written for its place in DAX (`'`, `]`, `"`
  doubled), Python (escaped in a string, braces doubled in an f-string, a name or a number bare) and
  HTML (escaped; a name only inside `{{ }}`). Every DAX snippet fills with its brackets and quotes
  paired; every HTML snippet fills with no address, `url(`, `@import`, `<link>` or `src=` in it.
- **Streamlit pieces, documented as they say:** each one filled is Python; what it makes and reads
  (the page designer's own `facts`, imports and `_` names left out) is what its `# Makes:` and
  `# Reads:` lines say; every `st.` function it uses is listed in its header; a piece with a `key=`
  says why, the cached one says when it forgets, the session state one why it is needed.
- **Streamlit pieces, run:** `tests/test_starters_streamlit.py` runs all 29 under Streamlit's own
  `streamlit.testing.v1.AppTest`, filled, each with a made-up `orders` table (40 rows), in a throwaway
  environment under the scratchpad (Streamlit 1.67.0, pandas 3.1.1, pyarrow 26.0.1, openpyxl, Python
  3.12.3): no exception and no error box in any. The guide's five pieces run together as one page, and
  in any placing their run order follows their names. Without a Streamlit Python the run tests skip.
- **Power BI actions:** `tests/test_starters_powerbi.py` runs all 13 against the stand-in, which now
  answers refreshes (202 with a RequestId; Unknown in the history until asked about twice, then
  Completed, or Failed with `serviceExceptionJson` on the broken dataset), dataflows and their
  transactions, reports, parameters, Default.UpdateParameters (only after Default.TakeOver),
  Default.TakeOver and the refresh schedule, in the shapes the Power BI REST reference gives. One
  sign-in carries the app registration from the vault; no action request holds the secret; a refusal
  arrives in Power BI's words; refresh and wait follows its own request id, and stops at its timeout.
- **Excel and files:** `tests/test_starters_excel.py` runs the 12 Excel functions on a made-up
  workbook in a temporary folder and checks it with openpyxl 3.1.5 (sheets, values and formulas,
  borders per side, fonts and fills, number formats, column widths, freeze panes, merged cells,
  conditional formats, a table, a copied template), and the three file functions on made-up CSVs
  (a folder combined, a split by a column with `;`, a cp1252 file rewritten as UTF-8). Each refuses to
  write over without `overwrite=True`. Every signature is the one its first lines document.
- **The app:** the pack listed by family and apart from `/blades`; a starter refused for change and
  removal; Copy as your own (named, numbered, kept editable); a snippet's form with the open tables as
  choices and its filled text; a snippet cannot be run.
- **Browser (this machine's Chromium):** `tests/e2e/test_starters_page.py`, 6 tests: the pack in the
  blade list by family, a search, a starter opened read-only and copied as your own; a DAX snippet
  dragged onto a DAX cell, its form filled from the stand-in workspace's loaded catalog (a measure
  moves its table), the text inserted, an HTML snippet on the DAX cell refused with its message; an
  HTML KPI row from the cell's Insert a snippet… drawn in the walled-off frame; a Streamlit piece
  filling an empty cell and naming it, in the Streamlit cells pane by name, the agent's insert making
  a named cell, and the piece dragged onto a canvas; the guide's five pieces dragged from the pane
  onto a canvas and played live (with Streamlit); and in a script, a piece as a named cell and an HTML snippet as an HTML cell. Monaco 0.57's `getTargetAtClientPoint` places a
  drop where it lands.
- **The whole suite** with the browser tests in this machine's Chromium and SWISSARMYBENCH_STREAMLIT_PYTHON
  set (the throwaway environment, with duckdb added for the saved pages' data.py): 2,507 passed, none
  skipped. The first run found two things: the catalog page's tests now meet two search boxes (the
  blades' shows whenever there are starters) and name theirs; and its new SQLite blade's tree was drawn
  again closed when the list waited on the starters after a save (they are asked for once now; five runs
  of that file passed after). `ruff check`, `ruff format --check`, `mypy` and `npm run typecheck` clean.
- **Not checked:** a real Power BI tenant (Microsoft's documented shapes only), the DAX snippets run
  against a real model, the map piece's background (it is fetched from the internet), Edge itself,
  Windows paths in the Excel and file functions.

## The agent's index, read first (2026-11-15)

- **mcp 2.3.0 resources:** `MCPServer.add_resource(TextResource(uri, name, title, mime_type,
  annotations, text))` lists and reads over the protocol; the in-process `mcp.Client(server)` sees the
  title, `text/markdown` and the annotations (`audience`, `priority`), and `client.instructions` is the
  server's. `tests/test_agent_index.py` lists and reads all nine resources that way.
- **The index** (`src/swissarmybench/mcp/index.md`, 3,451 characters against a 4,000 limit) names every
  tool prefix the registry has (derived with `area_of`, so a new prefix fails the test with what to add)
  and only commands that exist; so does each topic (`mcp/guide/<topic>.md`). `guide` with no arguments
  returns it as plain text (no JSON escaping), `guide(topic=...)` a topic, an unknown topic the list.
- **The tool list** grew 10 characters (54,731 against the 55,000 budget): the one `topic` argument.
- **The wheel** (`uv build --wheel`) holds `swissarmybench/mcp/index.md` and the eight `guide/*.md`.
- **Facts checked against the code** while the long guide was rewritten: the agent can read the audit
  log, stop the server, save and open dashboards and ask a Python session for a table (the old guide
  said it could not); no command starts the server (`ensure_server` only connects); approvals are
  `table_export`, `streamlit_export`, and `project_new` / `streamlit_save_as` with pasted rows, each
  denied after 180 seconds without an answer.
## The Components starters (2026-11-15)

Nine Streamlit pieces of HTML, CSS and JavaScript (docs/ideas.md, "Components"), in a throwaway
environment with Streamlit 1.67.0 and pandas (SWISSARMYBENCH_STREAMLIT_PYTHON).

- **Streamlit 1.67, read and run:** `st.html(body, width=, unsafe_allow_javascript=)`;
  `st.components.v1.html` warns "Please replace `st.components.v1.html` with `st.iframe`" and "will be
  removed after 2026-06-01", so the frame pieces use `st.iframe(src, height=)` (an HTML string is its
  srcdoc, with same-origin access to the app, its docstring says). `st.components.v2.component(name,
  html=, css=, js=, isolate_styles=True)` gives a mount call `(key=, data=, default=, width=, height=,
  on_<name>_change=)` that returns a ComponentResult (a dict read by attribute); `default=` keys must
  each have their `on_<name>_change`. The JavaScript module's default export is called with `name`,
  `data`, `key`, `parentElement` (a ShadowRoot when styles are isolated), `setStateValue` and
  `setTriggerValue` (BidiComponent.js); it is called again when `data` changes, and the function it
  returns runs only when the component leaves the page.
- **`tests/test_starters_components.py`, 33 tests:** the family's nine pieces; the same "Three ways"
  paragraph in each; each names its way, says why, and uses that call only; nothing from the internet;
  no placeholder inside the HTML, CSS or JavaScript, and no innerHTML in it. Under AppTest with a
  made-up table: all nine run without an error; the KPI counter's number, the frames' JSON (the
  table's columns and dates, the gauge's words, the timeline newest first); the four two-way pieces
  register, mount and give back their defaults (no card, "All", no key) and send data only. A state put
  in `st.session_state[key]` (what setStateValue does in a browser) comes back from the mount call:
  the card South makes `picked_region == "South"` and `by_region` its 10 rows, and goes back to the page
  as `picked`. A trigger cannot be set from AppTest: a stand-in at the mount call gives `pressed = "n"`
  (the caption says it) and `copied = 40` (the toast says it). With `</script><b>x` in the table and
  every label: the st.html pieces show it escaped (no `<b>` tag, no script holding it), the frames hold
  it only as `\u003c/script\u003e...` in their JSON, which reads back as the same text, and the
  components hold it only in their data. `tests/test_starters.py` checks each piece's Makes and Reads
  against the app's name finder and every `st.` call against its header (`st.components.v2.component`
  by its whole name now). 186 passed in the five starter files; with test_cli.py and
  test_architecture.py, 340. Without SWISSARMYBENCH_STREAMLIT_PYTHON the four runs skip, saying why.
- **In Chrome (streamlit run, by hand with Playwright, not a test):** the slicer clicked on South lit
  South and the KPI counter and gauge followed it (41,403, 17% of 250,000); the table sorted by amount;
  the callout showed `</script><b>x` as text and closed on its x; a card clicked made
  `picked_region = 'West'` and 10 rows; `n` pressed made `pressed_key = 'n'` and its caption, `x` (not
  listened for) nothing; Copy table put five rows and a heading, tab-separated, on the clipboard and the
  toast said so; the timeline drew newest first. No console error. The screenshot (2x) is the guide's
  images/24-components-page.png. `tests/e2e/test_starters_page.py` (6) passed in this machine's
  Chromium with the seventh family's line.
- **Not checked:** Edge itself, a dark theme in the app (a frame follows the computer's setting), a
  page with two keyboard pieces, Streamlit before 1.67.

- (2026-11-15) **A table refused for now is sent again.** The release workflow's trial run for 0.0.1 failed
  `test_in_a_real_kernel_the_cell_runs_twice_and_the_grid_is_not_sent_its_result` once: after Run file,
  the kernel's new table did not reach the grid within 20 seconds. It failed 1 time in 6 here under four
  busy loops, and 0 times in 25 with logging added (the logging changed the timing). The cause was not
  caught. Two changes: the watcher no longer gives up on a table after one refused send (any error but
  too large or an unreadable type is tried again, up to 5 times, then said once; tests/test_watch.py has
  both cases), and the test waits up to 60 seconds on a busy machine.
## Text cells on the canvas: Markdown and HTML cells on a Streamlit page (2026-11-15)

- **The rules** (`tests/test_streamlit_cells.py`, `tests/test_html_cells.py`): a Markdown cell written
  as `st.markdown`, an HTML cell as `st.html` with `unsafe_allow_javascript=True` only when it holds a
  `<script>` the browser would run (not one in a comment or a `<textarea>`); their `{{ names }}` as
  reads, so a page with the text first and the filter last runs the filter first and links "reads
  region"; a text cell never live in its own cell; `sab_text` never in requirements.txt, and
  `streamlit>=1.52` once a block runs a script; the export's and the saved pages' copy of the filler
  only when a block names a value, and the README's line; an old app file (SwissArmyGrid's key) read,
  and a text block adding nothing to the file. The escaping: `</script><b>*x*</b>` (and links,
  backticks, `$`, `:red[...]`) is text in Markdown (every mark escaped, markup as references, one
  line) and in HTML (escaped by where it stands); inside code only plain words; a table alone on its
  line as a pipe table; on a page, a name no block makes says "not found". In a Mermaid block a value
  is Mermaid text (its `"]`, `-->`, `%%{init}%%`, `;` in full-width forms).
- **Streamlit 1.67** (the throwaway environment): `st.html(body, *, width, unsafe_allow_javascript)` is
  the signature; the parameter first appears in 1.52.0 (checked in the wheels of 1.45 to 1.55).
- **The real Streamlit under AppTest** (`test_the_real_streamlit_fills_a_markdown_and_an_html_block_
  from_a_filter`): a canvas placed by the agent's commands with a filter, a total, a Markdown block
  reading `region` and `total`, and an HTML block with a script; the live page in its temporary folder:
  "Sales in East … **140**", picking West gives "Sales in West … **250**", the HTML block's body
  `<b>250</b> in West` and `window.sabTotal = 250;` with `unsafe_allow_javascript` true, the hostile
  value as text in both; the export's page (`sab_text.py` beside `app.py`, `streamlit>=1.52`, the README's
  line) and the saved project's page (`sab_text.py` in the zip) run alone the same way.
- **The window's cells and the pane** (FakeRunner): a window's Markdown and HTML cells (`kind`) and a
  script's HTML cell's lines (`form: "script"`) listed under Text with what they read; the canvas's
  blocks with their `kind`; Play writes `sab_text.py` beside the page.
- **Starters:** 88 (Markdown 10); each Markdown snippet fills with its defaults, reads exactly the names
  its description says, holds no HTML and nothing from outside, and is `st.markdown` on a page. A typed
  value's marks are escaped; inside a code span it goes as typed (no backtick); inside `{{ }}` only a name.
- **Browser (this machine's Chromium; `tests/e2e/test_text_cells_page.py`, 3 tests):** a Markdown cell's
  `{{ total }}` filled after Run all (`**480**`, the hostile note shown as text, no `b`/`em`/`script`
  made of it), Out of date · total changed after the console changes it, Run gives 512; the HTML cell's
  design filled the same; the Streamlit cells pane's Text heading with both, marked T; both dragged from
  the pane onto a new canvas and the Python cell by its number onto the app's tab; Play shows the
  Markdown and the KPI card live (with Streamlit). A Markdown starter (KPI sentence) inserted from the
  cell's menu, its typed `*` escaped, the cell drawn with "Not run yet"; a Markdown snippet refused in a
  Python cell. A ```mermaid flowchart drawn as SVG (two nodes), a broken one saying "This diagram could
  not be drawn: Parse error on line 3 …", and a name in a diagram (`East --> West`) drawn as one label.
- **The whole suite** with the browser tests in Chromium and SWISSARMYBENCH_STREAMLIT_PYTHON set: 2,536
  passed, 2 skipped (the two Streamlit starter tests want openpyxl in that environment). `ruff check`,
  `ruff format --check`, `mypy`, `npm run typecheck` and `npm run build` clean.
- **Not checked:** Edge itself; a Mermaid diagram on a Streamlit page (it stays a code block there);
  a picture named in a Markdown cell; Jupyter's own rendering of the escaped Markdown (CommonMark's
  rules, which the Workbench now follows for backslashes and references).

## The pre-release sweep for 0.0.1 (2026-11-15)

Design principles 13b: a read of what the release ships, for dead code, bloat and anything made slower.
No behaviour changed and no tests were added. Found with ripgrep and small ast and regex scans (vulture
is not installed here): every Python function, class and module constant named only where it is
defined; every TypeScript export and module nothing imports; every class in `grid.css` and `catalog.css`
that no module, page or server string gives an element (classes built as `mark-${kind}`, `tie-${status}`
and `role-${role}` counted as used); identical function bodies in two modules.

- **Bloat: Monaco twice.** `lazy/sqlEditor.js` (the "+" tab's SQL box) bundled all of Monaco again,
  4.4 MB of script and 171 KB of stylesheet, beside `lazy/codeEditor.js`. Its `createSqlEditor` now ends
  `lazy/codeEditor.ts`, so a page that has both loads one copy. The release wheel: 7.40 MB → 6.19 MB
  (24.0 → 19.5 MiB unpacked, 274 → 272 files). Checked in the browser: the "+" tab's editor is Monaco
  (not the text box it falls back to) and completes a column's name. The wheel holds no tests, pictures,
  source maps or caches. What remains large is what the page uses: Plotly 4.7 MB, Monaco 4.4 MB,
  Mermaid 2.5 MB, Graphviz 1.5 MB, ECharts 1.1 MB, Vega 0.8 MB, each loaded on first use, and AG Grid
  (1.0 of main's 1.4 MB), which the grid page needs at once.
- **A leak: a closed document stayed alive.** Closing a notebook or script removed its element but left
  its cells' Monaco editors and models, its console's prompt and its HTML panes alive, and each notebook
  added a window `blur` listener that was never removed. Measured in Chromium over CDP, twelve rounds of
  opening and closing a notebook and a script: the heap after garbage collection grew 13.6 → 30.4 MB with
  13 blur listeners; with the views' new `dispose()` (called when the document closes), 12.7 → 17.3 MB
  and none.
- **Dead code removed:** Python `streamlit_proxy.key_of`, `services/streamlit.KernelStopped`,
  `streamlit_cells.check_pane`, `AppFiles.remove_all` (stop_all already removes each folder); CSS
  `.visually-hidden`, `.ag-theme-host`, `.wb-project`. The `dz-*` classes, the old toolbar's and side
  bar's rules, the page designer and the Streamlit cell kind had already gone. Every TypeScript export is
  used.
- **Duplicates merged:** `quote()` (DuckDB identifiers) had identical copies in `domain/steps.py` and
  `domain/analysis.py`: one, in `domain/datasets.py`. The page's `plural` and `pct` had two copies each.
  Left on purpose: the starter blades' shared helpers (each `.blade.py` is a file that runs alone), and
  the kernel-side `client/` modules' small helpers (each loads into a kernel on its own).
- **Hot paths read, nothing found slow:** the grid's windows (compiled views and materialized tables are
  LRU-bounded, a per-key lock builds a view once), the profile cache (512 entries), the watcher's scan
  (one dict lookup per variable by class), the Workbench's outputs (batched, capped), its Tables and
  Streamlit cells pane refreshes (debounced 120 and 150 ms; the server says `streamlit_cells` only when a
  pane's mark changes), the canvas (no polling: socket notices), the server's background loop (every few
  seconds) and the kernels' message waits.
- **Noted, not changed:** compare's shared scrollbar measures both grids every 250 ms while a compare is
  open (cheap, and it stops with the compare); a running canvas asks for its state on every grid change
  without a pause between; `GET /streamlit/cells` with a project folder reads and parses the project's
  files on the event loop (small files, a handful). `markdown.ts` and `valueViewer.ts` each have their own
  Markdown renderer (different output; merging them would change how one draws).
- **The whole suite** with the browser tests in Chromium and SWISSARMYBENCH_STREAMLIT_PYTHON set: 2,589
  passed, 9 skipped. `ruff check`, `ruff format --check`, `mypy`, `npm run typecheck` and `npm run build`
  clean.
