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

## Add API (2026-11-15, branch add-api)

- **Checked against made-up services on 127.0.0.1** (`tests/api_standins.py`): an OpenAPI 3.0 document with a
  relative server and a Swagger 2.0 one; the made file run by a plain Python (`-I -S`: no site-packages, so no
  pandas and no keyring; lists of dicts come back) and by the app's Python (DataFrames), with every auth type:
  none; API key in a header, a query parameter and a cookie; bearer; basic; OAuth 2.0 client credentials (a
  `{tenant}` in its URL), authorization code with PKCE (the browser stood in for by a request that follows the
  redirect to the client's own 127.0.0.1 listener; the stand-in checks the S256 challenge), device code (one
  `authorization_pending`, then the token); JWT ready, login (its token runs out after two requests: a 401,
  then a second login), HS256, RS256 and ES256 (the stand-in verifies with the public key); SigV4 (the
  stand-in works the signature out again from the request it received); a Google identity token (the
  stand-in verifies the RS256 assertion, its `aud` and `target_audience`); Firebase email and password (its
  ID token runs out: refreshed with the refresh token) and a ready ID token. Paging by token, by a Link
  header and by page number; a 503 with `Retry-After: 0` retried; a 404's error says the method, address
  (without its query) and the answer.
- **SigV4 matches AWS's own test suite's `get-vanilla`** (signature `5fa00fa3…3fbf31`), standard library only.
- **RS256 and ES256** sign with `cryptography` (50.0 here); ES256's DER signature is turned into JWS's 64-byte
  r||s. Not checked against Google's or Firebase's real services, Entra ID, Cognito or a real Lambda or
  API Gateway: their shapes are from their documentation (Firebase `accounts:signInWithPassword` and
  `securetoken` refresh; Google's `jwt-bearer` grant with `target_audience` answering `id_token`).
- **YAML** read with PyYAML 6.0 where it is installed (here it is; it is not in uv.lock).
- **The app:** preview writes nothing; Add writes the file and saves the connection; Test, List the tables,
  the loaded catalog's columns, Open as grid (Rows to open) and a SQL cell in this Python (`sql_cell.sql`)
  work on it; re-import shows the removed operation, writes, and keeps the variables' sources; a file not
  made by Add API and a connection of that name not its own are refused (409). No answer, file or the state
  folder holds the key. The browser test adds one from a file and one from the form (the AWS preset).
- **The whole suite** with Chromium and the Streamlit Python: 2,677 passed, 9 skipped, 1 failed (the
  check that no file outside server/ names the browser module: the made file's OAuth code did; fixed, it
  passes with Add API's tests). `ruff`, `mypy`, `npm run typecheck` and `npm run build` clean.
- **Not checked:** Windows paths in Connect (the path goes in as a JSON-quoted literal, which Python reads
  the same); a real browser window for OAuth's authorization code; the keyring holding a refresh token on a
  real desktop.

### The Add API form, labelled (2026-11-16, branch add-api-form)

- **HTTP** (`tests/test_apis.py::test_try_it_...`): Try it on a form's GET table against the made-up
  service with a key typed for that try: its first rows (`sku`, `price`), the key in no answer, nothing
  written in the folder, no connection saved. No key: 400 naming `SHOP_API_KEY`; a wrong key: 400 with the
  service's 401, the key not echoed. A path parameter, a POST, a non-table and an unknown operation are
  each refused in plain words.
- **Browser** (`tests/e2e/test_add_api_page.py`, Chromium): from an OpenAPI file (the radio, File…,
  Save the file in; the document's sign-in; Try on `list_orders` with no key says `ORDERS_API_KEY`; Add;
  the vault; Test) and from the form with AWS Lambda (Hosted on, Base address, Sign in, two cards by
  label; the Needed chips: `order_id` ticked and fixed, `fields` ticked, which the made file types as
  needed; Try it on `/products` shows its two rows; Add sends the typed key for the keyring). Every field
  labelled, in light and dark, with one and three endpoints; at 560 px nothing runs off the side.
- **Not checked:** Add's keyring write from the page in a browser (this sandbox has no keyring: the test
  checks what the page sends and strips it on the way; the server's keyring path is the Add API HTTP
  test's); Try it with an OAuth sign-in that opens a browser; Edge (Chromium only here).

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

## Beta log (2026-11-15)

- Starlette 1.9's router puts the matched route on the request's scope (`scope["route"]`, its `.path` the
  pattern `/grids/{grid_id}/rows`) on the same dict a pure ASGI middleware passed down: the beta log
  reads the pattern there, never the URL.
- jupyter_client 8: `manager.provisioner.process.returncode` is a dead kernel's exit code (`os._exit(3)`
  reads 3); tests/test_cli.py checks it.
- Monaco 0.57: `editor.addAction({precondition: "key"})` with a key from `editor.createContextKey` hides the
  context menu entry while the key is false (not only greys it); setting the key in `onMouseDown` on the
  right button is in time for the menu that follows. The menu ignores a click right as it opens (the
  browser test waits 400 ms, as the Send to the agent test does).
- html-to-image's `toPng(document.body, {filter})` leaves the note's own dialog out of the picture by node.
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

- (2026-11-15) The whole suite after merging Beta mode: 2,622 passed, 9 skipped, 1 failed: the chart click by date
  (`test_chart_clicks_filter_by_date_by_heatmap_cell_and_never_by_a_whole_line`), which then passed 3 of 3 alone: a
  timing failure under the whole suite's load, not a bug. Browser tests are not part of the release workflow.

## One script, one notebook (2026-11-15)

- The exported script, run with plain `python` from a fresh venv (no Swiss Army Bench): without its
  packages it says the exact `pip install` and exits 3; with `--install` (`SWISSARMYBENCH_TEST_PIP=1`,
  pip from PyPI through this machine's proxy, 16 s) and with this machine's installed packages linked in
  (the default test), it reads the SQLite connection (password from an environment variable), the CSV
  with the grid's filter as DuckDB SQL, the SQL cell, the pandas cell, writes the workbook with the Excel
  starter's `write_table` and the CSV, and exits 0. A missing variable: named, exit 2, nothing written.
- The exported notebook, from a fresh venv with only its requirements and ipykernel, runs top to bottom
  in a plain kernel (jupyter_client, as nbconvert does), and by hand with `jupyter nbconvert --to notebook
  --execute` (nbconvert 7) and with `papermill ... -p SHOP_PASSWORD ...` (papermill 2): the same workbook
  and CSV. Without the password: MissingSetting in the settings' cell.
- The owner's chain, with stand-ins on 127.0.0.1: a Function App's managed identity endpoint
  (IDENTITY_ENDPOINT, X-IDENTITY-HEADER, `resource=https://vault.azure.net`, api-version 2019-08-01), a
  Key Vault (GET `/secrets/<entry>?api-version=7.4`, Bearer) holding made-up `pbi-tenant-id`,
  `pbi-client-id`, `pbi-client-secret`, and tests/powerbi_standin.py: the script, with no azure-identity
  installed and no secret in its file or environment, gets the entries, signs in to Power BI with them
  and writes the DAX rows. A 403 from the vault names the vault, the secret and the Key Vault Secrets
  User role; with no identity endpoint, what was tried (here the sandbox's IMDS address answered 403).
- `ruff check --isolated --select E9,F63,F7,F82` reads a script on stdin (`--stdin-filename`); its JSON
  gives `location.row`: it found the missing `urllib` import in an early export.
- DuckDB's replacement scan finds a DataFrame that is a local variable of `run()` (the cells run inside
  it): `duckdb.sql("... FROM orders")` reads run()'s `orders`.
- Not checked: a real Azure Function App, a real Key Vault and a real tenant; IMDS on a real Azure VM.
## Controllers, Test this page, thin cells, two starter families (2026-11-15)

Checked against Streamlit 1.67.0 (the throwaway environment, plus openpyxl for the starter runs), with
made-up tables only.

- **AppTest, as the runner uses it** (read and run, not from memory): `AppTest.from_file(path,
  default_timeout=)`; widgets by key (`at.selectbox(key=)`, `at.slider(key=)`...; a form's submit button
  is in `at.button`, with `form_id`); a Selectbox's `options` are the formatted options and
  `select_index(i)` picks one; a Slider has `min` and `max` (an int slider's are floats; `set_value`
  takes them) and a tuple value for a range; pills and a segmented control are a ButtonGroup with no
  `options`, read from `proto.options[*].content`; a NumberInput's ends are `proto.has_min/min` and
  `has_max/max`; `at.query_params[name] = value` before the run opens the page with it, and
  `dict(at.query_params)` gives `{"region": "North"}` after the page sets one; `at.exception` holds both
  an uncaught error and each `st.exception` the guard draws; `at.session_state` reads a key with `in`
  and `[...]`. `st.stop`'s StopException is a BaseException, so the page's `except Exception` guard
  does not swallow it. A run of the runner on a filter, a view that fails on one region and an action
  button: 6 tries, the failure on the view's block only (`tests/test_controllers.py`).
- **The contract** is read by `ast.parse` of the Makes line: `region: str = "All"; by_region: table =
  orders` parses as two annotated assignments; "Makes: a, b (the pick, the rows)" parses once its
  bracket is taken off. Every starter's Makes line now goes through this parser in the header test.
- **The pieces in AppTest** (`tests/test_starters_controllers.py`, 9 tests): all 14 run; a view on a
  page without its filter reads the defaults ("Total (All)"); the form refuses From 80 To 20 with
  "swap them" and keeps its rows, then takes 20 to 50; the action button puts a picked South back to
  All, and twice is once; the cross-page pick (East) survives a run in which its widget is not drawn;
  `?region=West` opens on West, an unknown value on All with the parameter taken away, and a pick
  writes `region=North`; the footer's caption and its `<style>` only when pinned; Test this page on a
  page of four controllers, a total and the footer: no failure, nothing untried.
- **In Chromium:** `tests/e2e/test_controllers_page.py` (the default said on the block, Test this page
  red on North only with the toast, the thin hint and its move into data.ipynb's named cell, `from data
  import big` left in the view). The pinned footer, by hand under `streamlit run` with Playwright: its
  box is `position: fixed` at the window's bottom edge (y 769 of 800, the full width), on the light
  theme's white; a picture in the screenshots folder. `st.container(key=)` marks its box with the class
  `st-key-<key>`, and `st.context.theme.type` is "light" there.
- **Tests:** test_controllers.py 13, test_controllers_canvas.py 5, test_thin_cells.py 3,
  test_starters_controllers.py 9, the browser test 1; test_starters.py with the new counts (111).
- **Not checked:** Edge itself; the dark theme of a real Streamlit page (the footer's dark colour is
  Streamlit's documented #0e1117, not looked at); a theme with colours of its own; a widget whose key is
  an f-string (said untried); Streamlit before 1.67 (which version brought the footer's `st.container(key=)` and
  `st.context.theme` was not checked); a component's JavaScript under Test this page (AppTest
  has no browser).
## Lineage with values, and approved outputs (2026-11-15)

- **The graph's rules** (`tests/test_lineage.py`, 28 tests with the HTTP ones): the nearest maker above;
  flow order (makers first, ties in file order); `@cell` links as dotted edges; a cycle of links ends; a
  table's read-only cell back through each grid step to its file, or to its user's maker cell; an open
  table no document holds as the grid's own; a SQL cell's connection and `-> name`; `sab.sql("Shop")`
  and `pd.read_parquet(r"C:\data\rates.parquet")` as sources; a widget cell as a controller; a Markdown
  cell's `{{ names }}`; `from data import x` into data.ipynb; a canvas page's first placed maker; the
  Mermaid labels escaped (`"`, `<b>`, `#` as `#quot;`, `#lt;b#gt;`, `#35;`).
- **Values over HTTP** (FakeRunner): a grid step's rows and its change from the step before (6 → 3,
  −3); a table's first rows; a window's error on the cell where the flow broke; a canvas block's flow
  (the grid's table, the filter on the page, the total); the page's notes read back as values (the
  filter's "West", the total's KeyError); a project's cell traced into data.ipynb; the agent's command
  marked as the user's data.
- **The real Streamlit 1.67 under AppTest** (`test_the_real_streamlit_runs_the_canvas_...`): the live
  page writes `lineage-p1.json` beside itself with the filter's choice ("West"); `sab_lineage.py` is
  only in the live folder, never in an export or the saved pages.
- **Mermaid 11.4.1** (the bundled one, `htmlLabels: false`, strict): `<br/>` in a quoted label draws
  separate lines of SVG text; a node is `g.node` with an id ending `flowchart-n3-<k>`, which is how a
  click finds it; `class n3 notebook` and `class n3 target` add both classes; `[( )]`, `[/ /]`,
  `[[ ]]`, `{{ }}` and `> ]` draw the source, step, table, controller and text shapes.
- **pandas' HTML** (the venv's pandas): a DataFrame's `_repr_html_` read by `html.parser` as its header
  row (the index's empty corner first) and body rows; a frame cut for display says `500 rows × 2
  columns` in a `<p>`, read as its shape.
- **IPython 9.18** for the headless run: `InteractiveShell.instance()`, `transform_cell` for magics,
  `display_formatter.format(value)` for the value a cell ends with, `capture_output(display=True)` for
  displays; `clear_instance()` after, so the test process keeps no shell.
- **Approvals** (`tests/test_approvals.py`, 19 tests): a snapshot's text, table, shape (500 rows kept to
  50), picture and error; addresses and run counts make no difference; a changed cell and a lost row
  said exactly; columns added and removed; 40 changed values capped at 20 and counted; a text diff; an
  error where there was none; an approval without rows still tells a change; the module imports only the
  standard library and nothing of the package; kept in the cell's metadata both ways; Save as's zip
  keeps the marks and shapes only (no "East" in it); the headless run passes, fails with a report, exits
  1 from the command line, and a failing cell is exit 1 too.
- **Browser (this machine's Chromium; `tests/e2e/test_lineage_page.py`, 3 tests):** a cell's lineage
  from its head's right-click: four Mermaid nodes, the cards in flow order beside their nodes, "6 rows
  × 2 columns", "−4 rows", "West", "260"; a click marks the card and its node; the kernel's values
  changed by code run elsewhere reach the cards ("145", "East", "−3 rows"); a double-click goes to the
  cell; the palette's command opens it again. A canvas block's lineage after Play: the grid's orders,
  the filter on the page ("East", marked page), and the filter changed on the same page in another tab
  ("West") reaching the open overlay. An output approved, the same run silent, a different run amber
  with "-total 390" and "+total 400", saved in the cell's metadata, approved again, removed by the agent.
- **The whole suite** with Chromium and the Streamlit environment: 2,682 passed, 5 failed, 9 skipped;
  three were this branch's and are fixed (a block's right-click menu with beta mode off; the error
  panel's own right-click menu; `workbench_lineage_show`'s number typed), one passed again in the rerun
  (`test_chart_clicks_filter_by_date_...`), and `test_an_agent_snapshot_follows_what_the_user_has_done`
  fails only in the full run and passes alone.
- **Not checked:** Windows; a Plotly or Altair figure's thumbnail (shown as "a chart": no picture
  without kaleido or vl-convert); the State panel (wb-modes) driving the cards (it reruns the page, the
  path checked here); the layout of a flow of more than a few dozen nodes; the one-script export's
  inlined check (that branch is not merged).

## The real-world test bed: use cases 1 to 11 (2026-11-15)

`python tools/testbed/testbed.py up` (PostgreSQL 16 on 127.0.0.1:55432, MariaDB on 53306, the made-up
company's files), then `tests/e2e/test_real_world.py` in Chromium (the browser swap), with the Power BI
and Key Vault stand-ins started by the tests and `SWISSARMYBENCH_STREAMLIT_PYTHON` set. All 14 tests
passed (127 seconds). Each use case counts the user's actions (clicks, keys, typed values, choices,
drags; code of more than one line is pasted, one typed value):

| | Use case | Result | Actions |
| --- | --- | --- | --- |
| 1 | orders from PostgreSQL cleaned in the grid, the notebook saved | passed | 35 |
| 2 | that notebook headless (`jupyter nbconvert`, the keyring's password) | passed | 1 |
| 3 | as an Azure Function (the exported connection file, SHOP_PASSWORD) | passed | 5 |
| 4 | Excel statements per customer from the template, the Excel starters | passed | 24 |
| 5 | a daily CSV export, then run as the scheduled task | passed | 12 |
| 6 | the daily CSV folder, both workbook sheets and MariaDB's customers; joins found | passed | 35 |
| 7 | a Power BI dataset's relationships and its five tables read in | passed | 26 |
| 8 | Power BI's Invoices tied out against PostgreSQL's (the regions of the missed day off) | passed | 10 |
| 9 | a forecast as a Sandbox report (note and chart), Page view, Print to PDF | passed | 14 |
| 10 | a story notebook: live Markdown, a by-region table, Mermaid, an HTML cell | passed | 20 |
| 11 | a project: data.ipynb, a pages notebook, three Streamlit starters on a canvas, Play, a zip | passed | 40 |

- **Agent parity** (MCP commands only, `execute_result`, as the MCP tools call them): use case 1 (a
  connection made with its password, never shown back; the four steps; the notebook saved and run),
  4 (the same 25 statements) and 11 (a project with a pages notebook, three snippets filled, blocks
  placed, played, saved as a zip): all passed. Nothing the user did was missing for the agent.
- **The zips run elsewhere:** each use case 11 zip, unzipped in a temporary folder, its page run by
  Streamlit's AppTest in a plain Python (the client wheel, psycopg, Streamlit; no app), data.py reading
  PostgreSQL through the connection's exported file and SHOP_PASSWORD: no exception, 1,198 invoices,
  and 316 once North is picked in the filter.
- **Bugs found and fixed** (each with a test): a blade or text dropped on an editor arrived with
  Monaco's `$0`, and a second dropped blade landed inside the first's line (e2e, test_starters_page);
  Send to Sandbox sent only the first card (`??=` with `await`), an analysis blade's too (e2e,
  test_push_anything, test_analysis_blade_page); a same-named table from another connection replaced
  the open one's rows, and one differing only in case was refused (test_connections); the Diagram said
  "No relationships yet." over an imported model with no table open (e2e, test_relationships_page); a
  tie showed -0 (test_tieout); a forecast counted a month with one day of rows (test_timeseries); 10,000
  to 99,999 in e notation (test_analysis); a snippet form's column defaulted to an identifier (e2e);
  the chart starters drew a database's Decimals as names (test_starters_streamlit).
- **The whole suite** with the bed up (Chromium): 2,646 passed, 6 skipped (17 minutes). **The test bed
  down:** with `SAB_TESTBED_DIR` pointing at an empty folder the 14 skip, saying "The
  real-world test bed is not up: python tools/testbed/testbed.py up (tools/testbed/README.md)."
- **Not checked:** a real Power BI tenant, a real Azure Key Vault, SQL Server (stand-ins only); Edge and
  Windows (Chromium on Linux here); the browser's own print dialog (stubbed; Chromium's PDF of the
  print view stands in for Save as PDF); a real scheduler (the commands it would run were run).
  The use cases' grids and notebooks share one app per module, each use case closing the tables before
  it starts.
- **Seen once, not again:** in one partial run, use case 9's print was noted without the print view's
  class on the page; it passed alone and in the full runs after. The stub now keeps the page's
  class changes, to say what happened if it comes back.

## Kind colours and the Workbench's modes (2026-11-15, branch wb-modes)

- **Checked:** every kind colour token per theme against the page, panels and captions (WCAG, a test);
  a chosen colour made readable in all four themes and never amber (a test). Streamlit 1.67: a page with
  the State tail runs under AppTest and writes its session (a selectbox's key, a list, a DataFrame as
  "DataFrame, 2 rows"); `embed_options=dark_theme` / `light_theme` on a frame's address switch the live
  page's theme (the browser test sees the dark page in the phone frame); `.streamlit/config.toml` in the
  folder Streamlit runs in carries the theme colours (Streamlit's documented place); `st.logo` and
  `st.set_page_config(page_icon=...)` as written in the entry. Run as scheduled: a script run with
  `SWISSARMYBENCH_INFO` naming a missing file finds no app (`push_client._read_info()` is None), its
  arguments, plain values and exit codes come back, a failing run keeps its traceback.
- **Not checked:** a key vault as a scheduled run's source against a real vault (the code path is the
  Python connections' vault jobs, tested there); a logo file on a real page (only the generated calls);
  the theme colours rendered by a real Streamlit page; the wiring drawn at zoom levels other than 80 and
  100%; Edge (the browser tests ran in Chromium).

## The integration branch: lineage, Add API, test-bed-2 and wb-modes merged (2026-11-15)

- **Add API inline in the one-script export:** `test_an_add_api_client_the_notebook_imports_is_inline_and_the_export_runs_in_a_fresh_python`
  (tests/test_script_export.py): a notebook that imports `API_Orders` (made against the made-up orders
  API with an API key header) exported through the agent's `workbench_export_script` as a script and as
  a notebook; both copied to another folder (no `API_Orders.py` there) and run in a fresh venv with only
  their requirements: 17 open orders and 7 regions written; without the key, exit 1; the key never in
  the files or the output.
- **wb-modes with lineage and controllers** (tests/e2e/test_workbench_modes.py, Chromium): the Data
  mode's Lineage view draws the lineage in place (no dialog), its target the orders table's cell, its
  Mermaid chart drawn, `--lineage-notebook` resolving to the theme's `--kind-notebook`; Properties
  shows a selected block's controller (Filter, makes region) and Lineage… opens the overlay (Escape
  closes it). `.cv-block.failed` (red) and the kind-colour left edge are both in grid.css; a failed
  block's red wins.
- **Script mode and the exporter read connections alike:** domain/script_runs.py `named_connections`
  is now the exporter's `references` (tests/test_script_runs.py unchanged and passing); both use
  `env_name_for` and `python_connections.env_reads`.
- **Approved outputs in the export:** not wired (docs/ideas.md, One script: why).
- **The whole suite on `integration`** (lineage, Add API, test-bed-2 and wb-modes merged, Chromium,
  Streamlit 1.67 in its own Python, the test bed down): 2,888 passed, 29 skipped (the test bed's use
  cases among them), 15 minutes. No test failed, so none needed a rerun alone.
- **Not checked:** Edge and Windows; the test bed's use cases with the bed up after the merge.

## The tray icon, updates, and start at sign-in (2026-11-16, branch tray-update)

- **Versions:** PEP 440 ordering in domain/updates.py against twelve pairs (dev before pre-releases, a
  final after its candidates, post releases, an epoch, `0.0.9` < `0.0.10`), equal spellings, refusals
  (tests/test_updates.py).
- **The check against a stand-in PyPI on 127.0.0.1:** newer (offered, the notice sent), the same and
  older (nothing, no notice), unreachable, an HTML answer, a 503 (an error, nothing offered), PyPI
  failing and GitHub's stand-in answering (offered, source github), a yanked release and one with no
  files (never offered), a pre-release only to someone on one. The request: one GET of the JSON path,
  no query, headers no more than Host, Accept, Accept-Encoding, User-Agent (Python-urllib) and
  Connection. **The switch off sends nothing** (the stand-in saw no request), kept across a restart
  (a new service reading update.json sent nothing either).
- **Update to X (the service):** hands the version to the helper and stops the app 0.5 s later; a second
  update is refused; asks first only with unsaved documents or running kernels (`{"confirm": ...}`, then
  `confirmed`); refuses a version that is not the offered one; the agent's waits for the Allow (declined:
  refused, nothing launched; the prompt names the unsaved documents), and asks even with nothing open.
- **The helper (fake operations):** wait, install, check, start, in order; three tries on a failed
  install, then the old version started and a note with uv's words; Windows' "Access is denied (os
  error 5)" said as files in use; a new version that does not start replaced by a reinstall of the old
  one; the wrong version installed is a failure; an app that does not stop is left alone and nothing is
  installed. The server's side: a copy not installed by uv refused, uv not found refused, the helper's
  copy and plan handed to the base Python with `-I`, waiting for the server and the tray, `UV_TOOL_DIR`
  set to this tool's own folder. The helper's file imports nothing from the package.
- **A real upgrade (tests/test_updater.py):** this repository's wheel built twice (the current version
  and `<version>.post42`, never on PyPI), the current one installed with `uv tool install` into a
  temporary `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, then the helper's `run` with `SystemOps` and `--find-links`
  installed post42 over it, checked the version and started it: the new server's connection file names
  post42 and the tool's Python (14 s here). Stopped afterwards.
- **The tray, without a desktop:** the menu as data with and without an update, stopped, given up, a long
  list ("3 more…"), unsaved marks; pystray's menu built from it with its dummy backend (the same texts
  and order, one default item, an item's action opening `/workspace#token=…&grid=…`, the menu read
  fresh); each item's action against a stand-in server (open, Workbench, blades, What's new, a document
  shown in the Workbench window, Update, Restart, Quit); the system box asked only when the server says
  so; the tray ending itself while the app updates; an update's failure said once; the icon's mark and
  its blue dot (pixels); one tray at a time (a second `swissarmybench tray` exits 0 while the lock is
  held); `run_tray` writing and removing tray.json and starting the server when none runs.
- **Stays running:** the watchdog's limit (3 in 5 minutes; spaced restarts never give up; the user's
  Restart counts afresh); a stand-in server dying four times: three restarts, then "Swiss Army Bench
  stopped: Restart", the events crash/restart ×3, crash/failed in server_events.json; a server stopped
  on purpose (no connection file) left stopped; at sign-in the tray starts a server when none runs.
- **Start at sign-in:** the entry's contents per system under a temporary home: the XDG .desktop (Exec
  quoted for a space, XDG_CONFIG_HOME honoured), the LaunchAgent plist (RunAtLoad, KeepAlive only on a
  crash), the Windows shortcut's PowerShell (Startup folder, pythonw.exe, `-m swissarmybench.server
  tray`, quotes doubled), its failure and a missing APPDATA said in words. `swissarmybench autostart
  status|on|off` in a subprocess with a temporary HOME; the route and the agent (`/autostart`).
- **`start --background`:** returned at once (under 10 s; the server took longer to answer), and the
  server it left answered /health with its token from another process; stopped with `stop`.
- **0.0.2's address:** `/` answered 401; `/workspace` answers 200 with the page (a test opens what
  `page_address` gives).
- **The installers:** read by a test (the `Quiet` helper, the flags, the CI and
  SWISSARMYBENCH_NO_AUTOSTART guards, `autostart on`, `start --background`); `sh -n install.sh`. The
  release workflow passes `-NoAutostart -NoStart` / `--no-autostart --no-start` and fails if
  `autostart status` is not off.
- **Browser (Chromium, tests/e2e/test_update_page.py):** a server whose feed is a stand-in with 9.9.9:
  the grid page's status bar says "Update available" (title "Update to 9.9.9"), its menu has Update to
  9.9.9 and What's new; Update to 9.9.9 on a copy run from source says "not installed with uv" and
  nothing stops; the Workbench's status bar says the same; the same version on the list: both marks go,
  live, and no status bar says "up to date". Settings' Check for updates: off hides the mark and a check
  sends nothing to the stand-in; on brings it back.
- **Not checked (no desktop here):** the real tray on Windows, macOS and a Linux desktop (pystray's
  win32 backend, the right click refreshing the menu, the notification, the dot at 16 px); the
  MessageBox, osascript and zenity questions; the Startup shortcut made by PowerShell and its start at
  sign-in; the LaunchAgent and the XDG entry at a real login; pythonw and CREATE_NO_WINDOW keeping every
  window hidden; `uv tool install --force` over a running MCP server on Windows (files in use: the note
  says so, untested); an update from PyPI itself (no newer release exists yet); the installers run on
  Windows PowerShell 5.1 and macOS with the new step (the release workflow runs them).
- **The cookie (tests/test_session_cookie.py, tests/e2e/test_session_page.py, Chromium):** only the
  token mints it (no credential, a wrong token: 401); HttpOnly, SameSite=Strict, Path=/, no Secure, named
  `sab_<port>`, its value not the token; it reads data like the token, another port's name or the token
  as its value does not; an unsafe method with it needs our own Origin (none, or another site's: 403),
  the Bearer token needs none; after a restart the old cookie gets the plain page (401, the words, no
  data), the page shell still loads; the websocket opens with it and refuses a wrong one or another
  site's Origin. In Chromium: the address bar shows the page with no fragment after load, the cookie is
  HttpOnly and Strict and `document.cookie` is empty, a reload works, a new tab at the bare `/workspace`
  (empty session storage) shows the table and takes a live push over the websocket, the bare
  `/workbench` loads; a browser with no cookie gets the words on `/workspace`, `/workbench`, `/catalog`
  and a data address. Pop-out windows, the Streamlit proxy and the grid page's own tests pass after the
  change (tests/e2e/test_workbench_groups.py, test_streamlit_page.py, test_ui.py, test_steps_page.py:
  93 passed). **Not checked:** Edge, Firefox and Safari's cookie handling on 127.0.0.1; VS Code's Simple
  Browser (it keeps the token in the address it was given).
- **The whole suite on tray-update** (0.0.3 merged, Chromium, Streamlit 1.67 in its own Python, the test
  bed down): 2,998 passed, 29 skipped (the test bed's use cases among them), 16 minutes. No test failed,
  so none needed a rerun alone.

## Navigation: the mark, Back, the address, breadcrumbs, titles (2026-11-16, branch navigation)

- **The agent's places (tests/test_navigation.py):** each window's places (home, catalog, workbench)
  read into the notice, a named view's names (`grid:g1`, `catalog:Warehouse/sales/orders`,
  `blade:x`), and the words for a place that is not one, a window that is not one, an empty name, a
  catalog path with a gap, a name past 512 characters. `/navigate` with no home page open: 409 and the
  words; with one (a `workspace=1` socket) the page gets the notice, `by` the agent; the blades page is
  told apart on the socket (`catalog=1`, not the Workbench's) and only an open one is told; no Workbench
  window: 409. The audit log says "home window to grid g7". `app_navigate` through the CLI's commands.
- **In Chromium (tests/e2e/test_navigation_page.py):** the home page's mark is a link to `/workspace`
  named Home; the Sandbox, Diagram and a table each put themselves in the address (`?view=sandbox`,
  `?view=diagram`, `/g/<id>`) and the title ("Sandbox", "Diagram", the table's name); Back three times
  and Forward twice walk them in order; a reload keeps the Diagram, and a table, with no token in the
  address; the mark and Alt+Home bring the grids back. Connections: `open=connections`, `&at=types`,
  `&at=form&type=postgres`, the titles ("Connections › Add connection › PostgreSQL"), the trail's three
  crumbs, "Back to Add connection"; a reload brings the form back with its trail; the visible Back, the
  browser's Forward, a crumb, then Back walks out one view at a time and closes the window on the page
  (still the same table); Forward opens it again; Escape takes its entries away; Settings is in the
  address and Back closes it. A plain dialog (Tables): Back closes it and the table stays; closed by its
  own Close, its entry goes, so the next Back is the tab before. The blades page: a schema and a table
  in the address and the title ("Blades · NavWarehouse › sales › orders"), the four crumbs, "Back to
  sales"; a reload opens the tree at the table; the catalog's own page (its counts); the welcome; the
  editor's address (`?blade=`) and "Back to Blades"; an address whose table is gone says so with a way
  back. The Workbench: its mark (titled "Home (Alt+Home)") brings the home window forward with no second
  window and no reload (the home window is named `sab-home`), the agent's `nav.home` too and never sends
  the Workbench away; with the home window closed, Alt+Home opens it again. `app_navigate`: sandbox,
  add_connection, back (closes it, the Sandbox stays), grid:<id>, home.
- **Found and fixed on the way:** a dialog closed by "Show" (the Sandbox) or "Open as grid" fires its
  close event after the page has already moved, and its history.back took the move away
  (tests/e2e/test_after_sending.py caught it): a push no longer carries a dialog that is already shut.
  Chromium counts a click just before a reload as the user's for a moment, so the reloaded page pushed
  its own address: the page's start now only replaces.
- **Existing tests changed:** tests/e2e/test_workbench_page.py's Connections Back buttons are named for
  where they go ("Back to Add connection", "Back to Connections"); test_ui.py's keyboard test: the first
  Tab stop is now the mark (Home), then the tabs.
- **The update's helper stops what else runs from the tool's folder (Windows; tests/test_updater.py with
  the Ops stand-in):** the plan carries `stop_in` only on Windows; the helper's steps are wait, stop,
  install, check, start; with no folder nothing is stopped; the real one does nothing off Windows. **Not
  checked:** the PowerShell process list on Windows itself (no Windows here).
- **The whole suite on navigation** (Chromium, Streamlit 1.67 in its own Python, before 0.0.5 merged):
  3,016 passed, 33 skipped, 2 failed, 16 minutes. The keyboard test failed for the mark's new Tab stop
  (changed, above); `test_chart_clicks_filter_by_date_by_heatmap_cell_and_never_by_a_whole_line` fails
  under the full run's load and passes alone. After merging 0.0.5: the updater, updates, navigation, CLI
  and architecture tests (263 passed).
- **Not checked:** Edge and Firefox (the tests run Chromium here; `navigator.userActivation` and named
  windows are in both); a mouse's back button and Alt+Left by hand (the browser's own Back, which the
  tests drive); the Windows taskbar's titles; bringing a window forward is the browser's choice (the
  tests see no second window and no reload, not the focus itself).

## The rail, and the icon glow-up (2026-11-16, branch nav-rail)

- **The places (tests/test_navigation.py):** every rail area (grids, sandbox, diagram, notebooks,
  scripts, apps, blades, connections, settings) is a place from every window, in the rail's order;
  `grids` is the same notice as `home`; `new_window: true` only for notebooks, scripts and apps (else
  said), and the audit log says "home window to apps, in a new window". Panels: `app.rail` (Every page,
  Navigation rail) is the last switch, on at each start (tests/test_panels.py).
- **In Chromium (tests/e2e/test_rail_page.py):** the home page's rail: nine areas in order, each named,
  48px, Grids marked; the mark, the tab row and the grid's first column start right of it; Settings at
  the bottom; the code areas in their kind colours. Sandbox and Diagram pushed (`?view=`), Back and
  Forward and a reload move the mark with them, a grid tab moves it back to Grids; Connections and
  Settings open their layers (marked while open, Back and Escape mark Grids again). Keys: one Tab stop
  (the current area), the tip on focus, arrows round both ends, Home, Enter goes, Alt+Home still the
  grids; the tip on hover. Other windows: Notebooks from the home page opens the Workbench at
  `?kind=notebook` with its menu (New notebook); a second click (Scripts) brings that window forward (no
  second window) with Scripts' menu; inside it Notebooks brings the notebook forward and Back the script;
  Sandbox and Grids from the Workbench move the home window (not reopened, not reloaded) and never send
  the Workbench away; Settings opens in the Workbench; the agent's `diagram` (from the Workbench window),
  `grids` and `notebooks` too. Open in a new window from the right-click menu (Apps) and a Ctrl+click
  (Scripts): a Workbench window of its own at that kind, its rail marking it. The blades page: rail,
  Blades marked, Settings opens there (it has the layer now), Diagram moves the home window. The steps
  window: the rail, Grids marked, Grids brings the home window's grids forward. Apps (the owner's "cell
  navigator"): with the Data panel folded, Apps then New Streamlit app: the Data panel open, the
  Streamlit cells pane listing the notebook's two cells, side by side (rail, panel, canvas), the Starters
  switch kept; a cell dragged onto the page links `rail mockups.ipynb @cell2` and is marked placed;
  folded again, Notebooks then Apps unfolds it with no menu. The Panels switch: off, the rail is gone,
  the body's padding 0, the grid's first column moves left by the rail's width, the mark still there;
  on again from the agent, back.
- **The Streamlit cells pane (tests/test_streamlit_apps.py):** a canvas linking a notebook no window
  holds lists that notebook's cells (read from its file; before, "No cells call Streamlit" in the App
  mode screenshot beside its own three linked blocks); a project's data.ipynb lists its named cells; a
  file both linked and in the project is listed once.
- **Icons (tests/test_icons.py):** the 36 connection types the server offers each have their own icon,
  all different; the Add API presets have theirs; every icon name web/src asks for exists. Looked at:
  the Add connection picker (light and dark), the saved list, the catalog tree with column kinds, the
  starter families, the Data panel, App mode's Starters.
- **Existing tests changed:** the Settings button is found in the Application row (the rail has one
  too) in test_ui.py and test_panels_page.py; the keyboard test's first Tab stop is the rail's Grids,
  then the mark; the Panels count is 17; the navigation test waits for a closed home window before
  Alt+Home (it raced the browser's close).
- **Found and fixed:** a narrow window (420px) scrolled sideways once the rail took 48px: the tour's
  bubble in the Application row did not wrap (it now goes under its button).
- **Not checked:** Edge (Chromium here); Windows' and macOS' pop-up rules for a rail click from another
  window (a click is a user's gesture, so it is allowed; the agent's from a window with no gesture can be
  blocked, and then it says so); forced-colors mode for the rail's bar (styled, not looked at).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,029 passed, 33 skipped, 0 failed,
  18 minutes. (A first run on the rail alone: 5 failed, all fixed above; tests/test_agent_index.py's
  MCP resources test failed once under load and passes alone.)

## Dataverse: a connection type (2026-11-16, branch dataverse)

- **Against the stand-in (tests/test_dataverse.py, tests/dataverse_standin.py):** the form (Address,
  three sign-ins each found by its own mark, the client secret offered from a vault only, azure-identity
  and pyodbc offered as packages); As you waits for first use (DefaultAzureCredential with the browser
  allowed); the app registration's client credentials request carries the environment's own scope
  (`<url>/.default`) and signs in once; the managed identity's request (IDENTITY_ENDPOINT,
  `api-version=2019-08-01`, `resource`, a user-assigned `client_id`); a wrong secret, an address that is
  not https (plain http only to 127.0.0.1) and no managed identity said plainly, the secret never in the
  words. The metadata (`EntityDefinitions`, `$filter=IsPrivate eq false`, `$expand=Attributes(...)`) as
  one schema, dbo, a private table left out, each table's display name, each column's type and display
  name, a choice's own name column and an image not read, a lookup's name column kept; loaded through
  Refresh, its tables' `title` in `catalog_tables`, its first SELECT in T-SQL without the schema. OData:
  `$select`, `$filter`, `$orderby`, `$top`, `$count` encoded; paging by `@odata.nextLink` with
  `Prefer: odata.maxpagesize` (three pages of a 1,000-row cap for 2,500 rows); past 5,000 the count comes
  from RetrieveTotalRecordCount, and a filtered read past 5,000 has none; a next link outside the
  environment is not followed. Choice labels (Picklist, State, Status), Yes/No as booleans, money and
  dates as themselves (the stand-in also sends the formatted text for them, as the real one does).
  FetchXML; Test (signed in, 4 tables, account's 12 rows); Open as grid through the Web API (Rows to open
  1,000: "first 1,000 of 6,200", `$top=1000`), the preview, the table's cell reading it again with
  `sab.read`; no secret, token or identity header in any answer, the audit log or a saved file. A typed
  client secret is refused on Test, Save and `blades_secrets`. The two starters run against it.
- **The SQL endpoint (TDS), with a stand-in for pyodbc only:** the connection string
  (`Driver={ODBC Driver 18 for SQL Server};Server=<host>,5558;Encrypt=yes;TrustServerCertificate=no;`, no
  user, no password), the token as SQL_COPT_SS_ACCESS_TOKEN (1256: its length, then UTF-16-LE),
  connected once; "TDS protocol endpoint is disabled" said as the endpoint being off with the admin
  center's setting, the SQL cell adding `account = sab.read("Sales CRM", "account")`, and the error panel's
  "Read the table instead" fix; a missing ODBC driver said plainly.
- **End to end (tests/test_dataverse_export.py):** the running app, `sab.read` and
  `sab.connection(...).read(filter=...)` in this Python; Export as one Python script with the managed
  identity: no pyodbc and no azure-identity required, no token in the script; run in a fresh Python with
  only its requirements, the two CSVs right; with no managed identity reachable, a plain message and a
  code that is not 0.
- **In Chromium (tests/e2e/test_dataverse_page.py):** the type's tile with its icon, the three sign-ins,
  App registration's fields written into the code, the client secret's source offering only an
  environment variable and a key vault (no password box), the vault's entry picked, Test ("It works:
  signed in and found 4 tables." and account's 12 rows), Save, the row's `sab.read` line, the catalog
  loading itself; the catalog page: dbo, four tables, User beside systemuser only, opportunity's page
  with the `sab.read` line, Picklist and Sales Stage, its first 50 rows; Open as grid; the grid's
  `salesstage` and `statecode` as labels.
- **Found and fixed on the way:** switching a form's Sign in kept the first way's packages (Dataverse's As
  you needs azure-identity, its app registration none): the form now offers the chosen way's own.
- **NOT checked against a real Dataverse** (no tenant here): the metadata request with `$expand` and
  `$filter=IsPrivate eq false` together, and its size and time on a real environment's ~800 tables;
  `$count` alongside `$top`; RetrieveTotalRecordCount's answer shape; the formatted values of
  multi-select choices; FetchXML's answer for linked entities; the SQL endpoint itself (pyodbc,
  ODBC Driver 18, the token's audience being the environment's URL, its exact refusal words when off,
  whether a `Database=` is needed); DefaultAzureCredential's browser window and the Azure CLI sign-in;
  a managed identity in a real Function App.
- **The whole suite on dataverse** (Chromium, Streamlit 1.67 in its own Python): 3,049 passed, 33
  skipped, 1 failed, 18 minutes. The one failure was tests/e2e/test_starters_page.py counting the starter
  families before Dataverse's (changed: the family is in the list); it passes after (7 passed).

## Projects as one .sab file (2026-11-16, branch sab-projects)

- **The format (tests/test_sab_files.py, 24 tests):** project.json round trips; fields this version does
  not know are kept at every level (the manifest, a table, its source, a grid) when the file is saved
  again; a newer format opens read-only with the writer's version in the words; a file that is not a
  project is refused. Zip safety: `..`, absolute paths, drives, backslashes, empty parts and control
  characters refused; a link, too many entries, an entry or a whole over its cap, a name twice, no
  project.json; an entry whose headers say 10 bytes but holds 4,000 stops while it is read; nothing is
  left behind when an open is refused. Only code and text go in (never CSV, Excel, Parquet or JSON data,
  environments, caches, checkpoints); a notebook goes in without its outputs. A file source is kept
  relative to the .sab when beside it (POSIX and Windows paths), and found beside a moved .sab first. The
  save is atomic: a refused entry half way leaves the old file whole and no temporary file. Rows round
  trip through Parquet. recent_projects.json holds paths and times only.
- **On the server (tests/test_sab_projects.py, 8 tests):** a project with a CSV table and two steps, a
  SQLite connection's table (its password in the keyring), a pasted table ticked and one not, a
  notebook, a canvas, a Sandbox note and a relationship: saved, closed (its working folder gone), opened
  again: the tables read again, the steps applied (3 of 4 rows), the ticked paste's rows back, the
  unticked one listed with Remove; the Sandbox, the model and the files back. No secret in the file:
  the keyring's password, a vault's value, a password typed into a form and the server's token are in no
  entry and not in the raw bytes. A missing connection says "Add connection Shop" and comes back on Try
  again once added; a moved file says "Find orders.csv" and comes back from where it is now, with its
  steps. Unsaved changes: refused (409) only when work would be lost; another program's open is asked
  through the page. The agent's save asks nothing without rows, and waits for Allow (Deny: 403, nothing
  written) with them. A folder project saves as one file and opens as a folder. `swissarmybench open
  sales.sab` asks the running app and opens the page only when none is open.
- **In the browser (tests/e2e/test_sab_projects.py, Chromium):** the Start view with two recent
  projects, one missing (marked, removed from the list); a reload keeps the view; a recent project opens
  (its table, its name in the Application row); Home brings the Start view, Back the table. Open
  project… through the file chooser. Save clears the ● and writes the new steps. Save as lists the
  pasted table (not the CSV one) with "Keep its rows in the file"; ticked, the file holds its Parquet.
  tests/e2e/test_navigation_page.py: the mark (and Alt+Home, and the agent's nav home) now goes to the
  Start view.
- **The installers' association (tests/test_autostart.py):** install.ps1's registry commands as text
  (HKCU\Software\Classes only, the ProgId, the icon from the package, `"...swissarmybench.exe" open "%1"`,
  registered before the start); install.sh's XDG MIME type and desktop entry. **Not run:** Windows' registry
  and Explorer (no Windows here), a Linux desktop's file manager; macOS is not registered.
- **The tool sweep:** the seven project tools swept with sensible and hostile arguments; it caught that a
  relative path saved into the server's own folder: a path is now refused unless it is whole.
- **Merged with 0.0.7 (the rail, icons, Dataverse):** Home stays the Start view; the rail's Grids shows the
  grids (it was the same place as home) and marks no area on the Start view; tests/test_navigation.py and
  tests/e2e/test_rail_page.py follow (Alt+Home goes to the Start view).
- **The whole suite after the merge** (Chromium, Streamlit 1.67 in its own Python): 3,114 passed, 33
  skipped, none failed, 18 minutes. ruff, ruff format, mypy (496 files), and the page's typecheck and build.
- **Not checked:** a double-click on a real desktop; a very large .sab (GBs of kept rows); two
  Workbench windows following one project; Edge and Firefox (Chromium here).

## Project scope: everything is the project's own (2026-11-16, branch project-scope)

- **The rules (tests/test_project_scope.py):** free names (analysis 2.ipynb, pages/a 2.py, sales
  2.stapp.json); the project's documents by kind, data.py and pages/*.py marked made, .sab/ entries never
  a document; .sab/blades and .sab/dashboards are the only app entries; a password needs a source here
  (keyring, environment, a vault's mapping, a secret blade; an own-Python variable from an unset
  environment variable counts as missing).
- **On the running server (tests/test_project_scope.py, tests/test_sab_projects.py):** New project
  without a path is refused (400), to a folder that is not there 404 with no project left open, with a
  path it writes the .sab at once (not dirty, in the recent list, autosave false in project.json); the
  open tables' connection comes with them. Autosave off: a change stays unsaved; on: project.json says so
  at once and the change is saved quietly once it settles; off again: kept in the file, the next change
  waits; a reopened file keeps the switch. Scope: a second project sees none of the first's notebook,
  connection, secret blade, dashboard; reopening the first brings them back from its file; with none
  open the blades are this computer's again and the documents list is empty. Import: from another .sab
  (a document named like one of the project's takes the next free name, the project's own untouched; a
  connection; the same connection again is skipped and said), from This computer (case-insensitive name),
  a loose notebook (copied, the original stays), a project folder (by the agent); saved, the imports are
  in the .sab; from a computer with no project open, 404. No password in the file whatever its source:
  a keyring password, a vault's value, an environment variable's value are in no entry and not in the raw
  bytes; on another computer (an empty keyring, the variable unset) the keyring and environment
  connections say Needs a password with Set the password, the vault one does not (its vault came with the
  project). A table from a connection without its password waits with "needs_password" and comes back
  after the password is set and Try again; a .sab without the connection's definition still says Add
  connection.
- **In the browser (tests/e2e/test_sab_projects.py, test_tour.py, Chromium):** New project: the file
  chooser in save mode first, then the Autosave switch, then the Grids landing (`?view=grids`: Open a
  file…, Paste, Query, Catalog, Add connection; no tour there), the switch on in the project's group and
  in project.json; a table arriving takes the landing's place, autosave saves it, closing it brings the
  landing back; the group's switch turns it off in the file. The tour: on the Start page, not in the
  Application row, the Workbench or the blades page; the whole tour and game from the Start page. Ctrl+S
  with loose tables and no project offers Keep its rows, then where. In the Workbench, Import… →
  Another project… → the chooser → analysis.ipynb ticked → it opens as a tab and is in the project's
  documents. test_workbench_page.py and test_workbench_groups.py follow the menu's In this project….
- **The tool sweep** caught project_documents sending a hostile kind unquoted in the address: quoted now.
- **Not checked:** Paste on the landing reading the clipboard (the browser asks; Ctrl+V is tested
  elsewhere); a connection's catalog reloading on a project switch with catalogs loading themselves (off in
  tests); a project switched while a Workbench kernel holds the old project's vault values (they stay in
  that kernel until it restarts); Edge and Firefox.
## Every rail icon lands on a page; the Connections page (2026-11-16, branch rail-pages)

- **Unit (tests/test_connection_usage.py):** a connection's uses in Python by ast (`sab.sql`,
  `sab.connection(name=...)`, `sab.read`, `sab.dax` by its workspace, a module alias and a function
  imported by name; a comment, a name inside another string, another connection whose name starts the
  same and `frame.read(...)` are not uses; IPython's `%` and `!` lines do not break the parse, a syntax
  error finds nothing); a notebook's SQL and DAX cells by their first line (a Markdown cell that says
  `%%sql Warehouse` is no use); a script's cells, a table's cell told apart, a cell's name; a canvas block
  on a referencing cell (its link relative to the app's file); the calls by kind and the status word;
  the configuration leaves out a setting named like a password, key or token and a connection string
  that carries one; the sign-in by its mark; a Workbench kernel reports a call, another Python does not
  (SWISSARMYBENCH_KERNEL), a Power BI dataset counts for its workspace.
- **HTTP (tests/test_connection_usage_routes.py):** four connections whose passwords are in the keyring,
  a vault's entry, an environment variable and nowhere: the cards' words (ready, needs) and each
  password's source by kind and name; neither the keyring's value, the vault code's value nor the
  variable's value appears in any answer (the agent's too). References from a saved notebook (a SQL cell
  and a sab.sql cell; a comment and a string are not), a script (sab.read), an app's canvas block, and
  the grid opened from the connection; a table read through the app and a kernel's report counted, the
  status "works"; a bad kind 400, an unknown connection 404.
- **Navigation (tests/test_navigation.py):** `connection:<name>` from every window; `connection:` alone
  refused. The CLI's every-route check: POST /connections/{name}/used is the kernel's (stated).
- **In the browser (tests/e2e/test_rail_pages.py, Chromium):** each rail icon from the home page, the
  Workbench and the blades page lands on a page with no `dialog[open]` and no menu; Connections and
  Settings as pages over the grids, the Workbench and the blades page, one at a time; Back and Forward walk
  Settings → Connections → the Diagram and back; the Notebooks and Scripts landing pages (their cards,
  the other kind's file not among them; New on the panel), a card opens the document and Back returns
  to the cards; New Streamlit app from the Apps page; the Connections page's card (Works, its calls), its
  detail (two notebook references and the grid, the SQL cell's @cell2, configuration, calls, Edit, Test,
  Remove), Back/Forward/reload on the detail, a reference opening the Workbench window at its cell, Edit
  and Back to the detail; the old addresses `?open=settings`, `?open=connections&at=types` and the blades
  page's `?open=settings` land on the pages.
- **Updated to pages:** tests/e2e/test_rail_page.py (the landing pages instead of the kind menus; the
  steps window's Grids now moves the steps window itself, the rule c18b411 made), test_navigation_page.py,
  test_catalog_page.py (the blades page in this tab), test_panels_page.py, test_beta_export_page.py,
  test_workbench_page.py, test_python_connection_page.py, test_powerbi_page.py, test_dataverse_page.py,
  test_add_api_page.py, test_ui.py (Settings), test_real_world.py (the counted Close is now the rail's
  Grids: the same count).
- **Not checked:** calls made from the user's own Jupyter or terminal are not counted (by design: no
  Workbench kernel there); references in unsaved edits (the saved file is read); a sign-in that opens a
  browser window reads "Ready" until its first call; Edge and Firefox (Chromium here); test_real_world.py
  runs only with the test bed up (not up here).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,134 passed, 33 skipped, 1 failed in
  17 minutes: tests/e2e/test_streamlit_page.py::test_the_agents_export_in_the_window_waits_for_the_users_allow
  failed once under the full run (the approval prompt's words not there in 5 s) and passed four times on
  its own. ruff, ruff format, mypy, and the page's typecheck and build.

## The Sandbox is Visualizations, the Diagram is the ERD (2026-11-16, branch renames)

- **The old names, tested:** `sab.sandbox` adds a card with a DeprecationWarning and is not in `__all__`
  (tests/test_sandbox_cards.py); every `sandbox_*` name runs its `visualizations_*` command through
  `execute`, the `sab` command and an MCP `call_tool`, and none is in the tool list (tests/test_cli.py);
  app_navigate `sandbox` and `diagram` (tests/test_navigation.py, and in the browser: the home window
  moves to `?view=visualizations` and `?view=erd`); app_snapshot's area `sandbox` asks the page for
  `visualizations` (tests/test_snapshots.py); the addresses `/workspace?view=sandbox` and `?view=diagram`
  land on the pages, are replaced by the new words, and the rail marks the area
  (tests/e2e/test_navigation_page.py); a .sab manifest with the old `sandbox` key reads its cards and
  writes them back under `visualizations` (tests/test_sab_files.py).
- **Updated:** every test that named the Sandbox or the Diagram as the user sees them (the rail's areas,
  titles "Visualizations" and "ERD", Send to Visualizations, the toasts, the theme picker, the palette's
  Go to Visualizations, the tour's twenty-one stops, the .sab's new entry, the theme routes).
- **Screenshots** (light, deviceScaleFactor 2, made-up orders and customers): the rail's Visualizations
  and ERD tips, the Visualizations page (a chart and a note), the ERD page; looked at.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,161 passed, 33 skipped, 1 failed in
  17 minutes: tests/e2e/test_streamlit_page.py::test_the_agents_export_in_the_window_waits_for_the_users_allow
  (the same one as before: failed under the full run, passed alone). ruff, ruff format, mypy, the page's
  typecheck and build; the agent's index 3,986 characters.
- **Not checked:** Edge and Firefox; a .sab really written by the previous release opened in this one (the
  manifest rule is tested, not a file from the old app); an MCP client calling an old name over stdio
  (the server's own `call_tool` is).

## The Workbench, the owner's feedback (2026-11-16, branch workbench-feedback)

- **Rules:** each notebook's role (tests/test_project_scope.py: data.ipynb data, a notebook a canvas
  links by a relative or whole path app, others plain; `/project/documents` lists the role); a table's
  `step_words` and `table_cells.run` returning the table (tests/test_table_cells_live.py).
- **In the browser** (Chromium, tests/e2e/test_workbench_feedback.py): New and Open… after Save as… on
  the Scripts, Notebooks and Apps pages and beside a document, no landing panel, New pushes so Back
  returns; data.ipynb's table cell unfolded, numbered, run by itself (its three filtered rows in the
  output, sorted), first before any cell of the user's, no unsaved mark, saved without outputs; a cell's
  width follows its pane at 2,200 and 1,100 pixels; data.ipynb, a plain notebook and an app's notebook
  wear dataNotebook, notebook and appNotebook; the Scripts page's Transformations card (2 steps, in
  words) opens the cell, the Notebooks page shows it too, and the agent's tables.transformations.
- **Updated:** the rail tests (New in the top bar, the page heading exact), the saved notebook test (it
  opens unfolded; its user-made table still waits).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,168 passed, 33 skipped, 1 failed in
  17 minutes: test_beta_notes_page's tab kinds (a notebook placed on a canvas is now an app notebook; the
  test was updated and passes, with the Data panel's file icons and the icon tagging made after the run:
  test_workbench_feedback, test_beta_notes_page, test_workbench_groups rerun, all pass).
- **Not checked:** a very large table's output (pandas' own truncation applies); Windows paths for the
  app-notebook role (the rule handles backslashes; not run on Windows).

## Data notebooks and app notebooks (2026-11-16, branch notebook-kinds)

- **Rules** (tests/test_project_scope.py): in a project data.ipynb (any case, at the top) is data, every
  other notebook app (a data.ipynb in a subfolder too), scripts and apps have no role;
  `notebook_kind` by whole path: inside the project data or app, outside it plain, with no project
  data.ipynb data and others plain, Windows paths, a sibling folder whose name starts the same is outside,
  a non-notebook None; `/project/documents` lists a .sab's analysis.ipynb as app.
- **In the browser** (Chromium, tests/e2e/test_notebook_kinds.py): a project's data.ipynb, an unused
  notebook and a canvas's notebook wear dataNotebook, appNotebook, appNotebook on their tabs (data-kind,
  icon, the icon's word) and in the Data panel's files (the word); the agent's "documents" roles; the
  Notebooks page's two headings in order with one data card and two app cards; New app notebook in the
  top bar makes an untitled app notebook; the Data panel hidden beside data.ipynb, back beside an app
  notebook (Tables shown) and the canvas, "documents" says away, `view.toggleSidebar` refused with its
  reason, the "…" menu has no Data panel entry; outside a project New notebook makes a plain notebook
  with the Data panel beside it. tests/e2e/test_workbench_feedback.py updated (an unused notebook in a
  project is an app notebook).
- **Screenshots** (2x, made-up orchard project): the Notebooks page's two groups, data.ipynb with no Data
  panel, an app notebook with it, a new app notebook; looked at.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,175 passed, 33 skipped, 1 failed in
  18 minutes: test_beta_notes_page's tab kinds (a canvas's notebook with no project open is now plain,
  not an app notebook; the test was updated and passes). ruff, ruff format, mypy, the page's typecheck and
  build.
- **Not checked:** Edge and Firefox; Windows paths in the page's rule (the domain rule's test has them);
  a .sab project opened from the home page with the Workbench already open (the folder project was used;
  both set the same project folder).

## Launch Claude (2026-11-16, branch launch-claude)

- **Rules** (tests/test_claude.py, made-up probe answers only): names matched loosely, uninstallers and
  updaters left out; the registry (an official install by its DisplayIcon, a company build by its
  InstallLocation, an App Paths default); a Store package's launch id and its config folder; Start menu
  shortcuts telling the app from the CLI; macOS bundles by bundle id or name; a .desktop file's Exec line
  as arguments (field codes dropped, other groups and translations ignored, a Terminal entry left to
  PATH); ranking once each, official first, the user's choice kept while it exists; the Linux and Windows
  finders against made-up folders and a made-up PowerShell answer (nothing run).
- **Desktop's config**: merged with every other entry kept, unchanged when already there (no write, no
  backup), no token; not JSON or a bad mcpServers refused in words; config places per system and by the
  app's name.
- **Claude Code's folder**: CLAUDE.md has the project, its .sab and working folder, a table's rows,
  columns and steps in words, connections and documents, the index; a made-up distinctive value in a
  filter, an "in" list and a SQL step appears nowhere. .mcp.json and settings.json have no token and no
  permissions; a path with spaces is quoted in the hook. Folder names made safe (quotes, `;`, `..`, CON).
- **The terminal**: gnome-terminal, konsole, x-terminal-emulator (first found), none (None); Windows
  Terminal with `;` escaped; a new console; macOS's one line read back by shlex into exactly the folder and
  the arguments, with a name holding quotes, spaces, `;`, `$()` and backticks. Bypass adds the flag last.
- **HTTP** (a stand-in finder and starter: nothing probed, no terminal): the agent reads `/claude` and
  `/claude/context` but gets 403 on the launch and on Settings; a launch writes the folder (no row value
  in CLAUDE.md) and records `x-terminal-emulator -e claude` in that folder; the bypass switch; none found
  (both kinds' help); both found (asks which); Desktop asked once, then the config written with a backup
  and the app started, the next launch writing nothing; an unofficial build with no config said, then the
  user's file used; Other… refuses a file that is not there.
- **MCP**: the resource swissarmybench://context listed and read (said plainly with no app running).
- **In the browser** (Chromium, tests/e2e/test_claude_launch_page.py): the button and its icon in the home
  page's footer and the Workbench's; a click records gnome-terminal in the no-project folder and CLAUDE.md
  names the pushed table without its values; both found: the menu, Claude Desktop, the one question, its
  config written beside a made-up server kept; none found: the dialog with the install commands and the
  download link; Settings' Claude: two found, one chosen, bypass on, and the next launch uses both.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,205 passed, 33 skipped, 2 failed in 18
  minutes: the narrow window's sideways scroll (421 of 420 pixels: the new button; fixed, the sparkle alone
  below 760 pixels, passes) and test_rail_page's new-window test (passes alone: load).
- **Not checked:** real Windows (registry, PowerShell's Store and Start menu answers, Windows Terminal,
  the new console), real macOS (Spotlight, Info.plist, Terminal through osascript), a real Linux terminal
  opening, a real Claude Code or Claude Desktop starting and reading the folder or the config.

## Trino by a keystore; certificate files from a variable (2026-11-16, branch trino-keystore)

- **Checked** (tests/test_keystores.py, made-up keys from a made-up CA): format detection; PKCS#12 (with
  its friendly name), JKS and JCEKS read (pyjks 20.0.0 in this branch's venv; pyjks writes JKS only, so the
  JCEKS file is a JKS with JCEKS's magic and its SHA-1 signature made again); several keys and the alias;
  the wrong password (PKCS#12, JKS), no private key, an unknown format, a missing file naming
  TRINO_KEYSTORE_PATH, pyjks missing (a child Python with `jks` blocked); the PEM files' modes (0600, the
  folder 0700) and their removal when the Python ends (a child process); the mapping's round trip for the
  keystore, Trino's verify, psycopg's sslrootcert/sslcert and pymysql's ssl_key; another field refused;
  the export's settings block (the path variable and the password named, never the file's bytes, nothing
  listed unmapped) and Run settings' list. End to end: a stand-in Trino on 127.0.0.1 over HTTPS with
  CERT_REQUIRED (tests/trino_standin.py; trino 0.340.0 client): Test (typed password), the agent's save,
  Open as grid (5 rows, 3 columns), every request carrying the client certificate; a password sign-in
  with no certificate refused in words. Browser (Chromium): the form's Sign in, the keystore's Browse…,
  Path / From an environment variable (TRINO_KEYSTORE_PATH suggested, the code updated both ways), the
  password from the keyring, Test "It works: signed in."
- **Not checked:** a real Trino with mutual TLS; a real Azure Function App (its Application settings or a
  Key Vault reference giving TRINO_KEYSTORE_PATH and the password); Windows' temp-folder ACL (mkstemp's
  folder in the user's own %TEMP% is assumed private); a keystore whose key password differs from the
  store's (said in words, not tested).

## The Session page and Follow the agent (2026-11-16, branch session-page)

- **Rules** (tests/test_session_log.py, made-up data only): each kind of action names its object (a step's
  grid with its op and kind, a grid opened, a card by id, a relationship by its tables and columns, a
  connection or a blade, a notebook's cell by path and number, a canvas page, an export, a project
  saved with its rows); reads, navigation, snapshots and settings make no entry; every rule fed a
  made-up value, query literal and password returns none of them; the filter (newest first, agent / user
  / both), the switch's words, follow.json read back.
- **HTTP**: the agent's grid, step, card, relationship and connection arrive naming their objects; the
  user's step delete shows under Me only; no pasted cell value or filter value anywhere in the log; the
  switch read by the agent and refused to it (403), kept across a restart; a new start's log is empty.
  `app_session` runs against a live server.
- **In the browser** (Chromium, tests/e2e/test_session_page.py): with Follow on, the agent's relationship
  brings the ERD (address view=erd) and its line is highlighted (data-followed, the pulse); its card brings
  Visualizations with the card in view and pulsed; its step brings the grid back; nothing counted on the
  rail. Follow off from Settings: nothing moves, the Session icon counts 2, the Session page lists both
  (the agent's only by default, Both adds the user's), its links go to the ERD (the line highlighted)
  and, after Back to the page, to the card. Typing in a text box: nothing moves and the box keeps its
  focus and words; leaving it, the waiting move happens. The rail tests (an area more) and the navigation
  tests pass.
- **Found and fixed**: the ERD's draw raced itself (a draw from before the model loaded painted "No
  relationships yet" over the diagram); two tests counted every live notice and now leave out
  `session_entry`.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,220 passed, 33 skipped, 4 failed
  in 20 minutes: two counted the new notice (fixed, pass), and test_open_file's catalog preview and
  test_ui's "+" tab (both pass alone: load).
- **Not checked:** the Workbench's follow of a cell (scroll and pulse after the agent's cell command) in a
  browser test (built, tried by hand only through the code path's types); a Mermaid version that names
  its relationship lines otherwise (the highlight finds `path.relationshipLine` in the text's order);
  Edge (Chromium here).

## Swapping a table's connection (2026-11-17, branch swap-connection)

- **The rules** (tests/test_connection_swap.py): a table matched in another catalog by its name in any
  case, its schema then its database breaking a tie (an ODBC database matching Trino's catalog), a tie or
  none asking to pick; only one read query runs (SELECT, WITH, VALUES, EVALUATE; a DELETE or a second
  statement refused, a semicolon inside quotes allowed); the name only changes (`EDP -> orders`,
  `EDP/Sales model`; `EDP2` untouched); Python calls by ast (aliases, `from swissarmybench import read as
  fetch`, the `connection=` keyword; a comment, another string, `print('EDP')` untouched; non-ASCII text
  before the call keeps the column right); a notebook's ticked cells only; a script's Tables group left to
  the app.
- **Over HTTP** (tests/test_connection_swap_routes.py, EDP and Trino as SQLite files, Trino's tables in an
  attached schema `sales` in lower case): ORDERS with two steps moved to Trino (the same grid, the same
  steps, Trino's extra row through them, its read-only cell reads Trino), undone (its rows and origin
  back); a table Trino lacks answers pick (its schemas, a suggested query), a picked table and a reviewed
  query run (a DELETE refused), a query table asks for review again; a project saved with EDP deleted
  opens with ORDERS waiting, moved at once with its steps, saved with Trino's place in project.json; a
  query run as it is on a connection without its schema fails in the source's words and nothing changes;
  the notebook's ticked cells only rewritten, an unticked `%%sql EDP` still listed; the agent's door.
- **In the browser** (Chromium, tests/e2e/test_swap_connection_page.py): the Table row's Connection: EDP,
  the chooser, the swap (the label follows, the strip's EDP → Trino and its Undo); the pick view's catalog
  tree, Write a query… in its own window, Run on Trino closes it; the strip's Use another connection… on a
  reopened project, Point these at Trino with one cell unticked (the file has the ticked one only).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python, on 26d1c50): 3,278 passed, 42 skipped, 3
  failed in 19 minutes, all three in tests/e2e/test_streamlit_page.py: two expected the prompt's old title
  (fixed on the base branch since, 1ca9404, merged in), one the pop-out across windows (load). After the
  merge, test_streamlit_page.py and this branch's tests: 79 passed.
- **Not checked:** a real ODBC-to-Trino move (two real servers, their naming differences); the Workbench
  window's own rewrite of an open, unsaved document (doc.repoint: typecheck only; the file path is
  tested); a DAX query moved between Power BI workspaces; a Python connection's table moved (its Read a
  table box is the same path as a database's, not run here).

## A missing package, in the user's face (2026-11-16, branch package-prompt)

- **The shape** (tests/test_missing_packages.py): `{"feature", "packages", "python", "command"}`, the
  packages once each, "app" for the app's own Python and a path for another; the sentence "<Feature> will
  not work without a, b and c."; features in plain words (Key Vault connections, Trino / Presto
  connections, The Sales blade); `MissingPackagesError` answered 422 with `error` and `missing`.
- **Each place over HTTP:** `/blades/inspect` (a made-up module: The Bakery blade; nothing missing: None);
  `/connections/types` (the Key Vault and Trino forms where their packages are absent; SQLite: None); a
  connection test that stops on a made-up import names the form's kind; a YAML API document with PyYAML
  made unimportable (the user's and the agent's answers); a failed refresh (tests/test_catalog_routes.py);
  a Streamlit app's and Test this page's problem (tests/test_streamlit_apps.py,
  tests/test_controllers_canvas.py); a kernel error's `missing` with the kernel's Python
  (tests/test_errors.py).
- **In the browser** (Chromium, tests/e2e/test_workbench_page.py, the package check and the installer
  stood in for with page routes, nothing downloaded): the Trino form's prompt at once, its title and
  sentence, Install now failing once (said, with its output, Try again), then installed (the toast, the
  form read again, no note left); Not now leaves the reminder and the command, the same form again does
  not ask, the reminder asks again and installs. tests/e2e/test_streamlit_page.py: a cell's run in a
  Python without Streamlit prompts "Streamlit apps needs streamlit…"; Not now; the canvas's Play does not
  ask again; its Install reminder does. Tests that open forms whose packages this Python lacks (SQL
  Server, Azure Key Vault, Dataverse's As you) say Not now first (test_ui.not_now).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,220 passed, 33 skipped, 4 failed in
  20 minutes; the four (test_open_file's catalog preview, test_ui's "+" tab query, test_compare's compare
  started elsewhere, test_processes' follow) pass alone: load.
- **Not checked:** a real install through the prompt (uv downloading a package); the notebook cell's
  prompt and its `%pip install` then re-run in a browser (the server's shape is tested, the page's path
  by typecheck only); the blade editor's and Add API's prompts in a browser; the Trino keystore's pyjks
  (another branch).

## The Variables page (2026-11-17, branch variables-page)

- **Rules** (tests/test_variables.py, made-up names and values): plain, local and keyring variables kept
  apart (the shareable file has names and sources and the region's value, never the local path nor the
  secret); a cloned file without local values reads them as Not set; a secret-looking name refused as a
  plain value; each source (vault, value, keyring, env, missing with a keystore's default) and its uses
  (a connection's password, a keystore setting, a script's `os.environ` and Run settings); a secret in the
  environment behind Show; rename in code (secret, environ[], .get, getenv); the server's environment
  given back; the files unchanged when nothing changed.
- **HTTP**: add (in os.environ at once), the agent's keyring secret never in any answer to the user or the
  agent nor in the file, Show 403 for the agent and the value for the user, a vault's refused, rename
  (the connection's code follows, the keyring value moves), remove (the environment lets go), the Session
  page's words, the server's stop gives the environment back; with a project open the same variables, and
  the saved .sab holds none.
- **In the browser** (Chromium, tests/e2e/test_variables_page.py, its own server with a keyring in a
  temporary file): the rail's Variables (aria-current, open=variables), the vault's row (vault · secret
  name, no Show), Add variable (the name in capitals), North in plain sight, This computer only marked,
  Show and Hide on a keyring secret, the source chip and the search, Remove listing the connection. Light
  and dark screenshots. The rail tests take the new area.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,301 passed, 42 skipped, 2 failed in
  20 minutes: test_streamlit_page's two canvas drag tests, which pass alone (load).
- **Not checked:** a real Workbench kernel reading a variable added while the server runs (the kernel
  inherits os.environ by the launcher's code path, not run here); a real system keyring (Windows Credential
  Manager, macOS Keychain); Edge (Chromium here).


## Connection colours (2026-11-17, branch connection-colours)

- **Rules** (tests/test_connection_colours.py): the palette clashes with none of the rail's colours and
  reads in every theme; the next free colour in turn and the least worn; the rail's colours refused with
  their words (violet, blue, green, red, amber), a chosen kind colour reserved from then on, a kept colour
  near it turned away; the connections a cell names (SQL, DAX, Python by ast; a comment is not a use);
  colours.toml sorted, stable, read back, broken text read as none, an unchanged save writes nothing; a new
  connection's colour, kept across a restart, refused over HTTP (400), 404 for no such connection, a
  rename carrying its colour, a colour sent with a new connection checked.
- **In the browser** (Chromium, tests/e2e/test_connection_colours_page.py, SQLite stand-ins Ledger and
  Depot): the tabs grouped Files, Ledger, Depot with the connection's colour on its tab; the arrow keys
  across groups; the agent's change followed live; a group folded and opened; the card's colour, its
  palette (eight), Magenta chosen and worn; the detail's swatch; a rail blue refused; notebook cells with
  one and two connections (two marks), a comment not marked, a `%%sql Depot` cell, a change followed; the
  Data panel's tables; a script's margin stripe; a canvas block's colour.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,305 passed, 42 skipped, 1 failed in
  19 minutes: test_ui's tabs test lost the tab order on a reload (the colours' first read redrew the empty
  tab row, which remembered an empty order before the saved one was read). Fixed; test_ui.py and the
  colours' tests again: 83 passed.
- **Not checked:** the high-contrast and dark themes in a browser (the colours per theme are unit-tested);
  a Session entry's stripe in a browser (the attribute is set by the same rule as the cards); dragging a
  group head; Monaco's stripe colour in a script after a theme change.


## Structures and the APIs page (2026-11-17, branch trees-apis)

Checked (made-up data; Chromium for the browser tests):
- Domain: every step on a made-up gates file, a field mapping and an orders payload; paths (quoted keys,
  indexes, `[*]`); JSON's error line; XML round trip and the DOCTYPE/ENTITY refusal; TOML written and read
  back by tomllib, its null refusal (tests/test_structures.py, 40).
- Web calls: each response shape (records, envelopes, OData, header and rows in five spellings, a header
  row first, nested under data or result) found; DuckDB's conversion run on paged data (the header read
  once, the header's types, a header row skipped, nested objects flattened, a list kept); the settings
  checked; the tables contract (tests/test_web_calls.py, 21).
- HTTP: open, paste, steps, undo/redo, the text view, Save and Save as in each format, Open as grid's rows,
  a .sab with a structure saved and opened again, references, sab.structure's read
  (tests/test_structures_routes.py); the APIs page against tests/api_standins.py: cards, search across two
  APIs, an operation's inputs and outputs, a call with a body edited as a step, its answer and lineage,
  Open as grid in the chain, Run again, Save as web call, Return as table as the only way into SQL, a
  required input named, Refresh's diff then apply, rename, delete with references first
  (tests/test_api_explorer.py); Add API's earlier tests moved to the library (tests/test_apis.py), a SQL
  cell over three switched-on web calls in a real kernel-less Python.
- Browser (tests/e2e/test_structures_apis_page.py): the rail's APIs page, its cards, search, explorer,
  Author a call (a body edit in the tree followed by the text, a schema error and its fix), Send into
  Structures, the lineage drawn, Refresh's diff applied; the Structures page's tree and text in step, a
  Filter step from a node, a tree edit as a step, Open as grid, a step removed. The rail's new order
  (tests/e2e/test_rail_page.py, tests/test_navigation.py).
- After the merge with the main line (connection-sql, context.md, Variables, colours): context.md's APIs and
  Structures sections fed (tests/test_context_md.py); the API blade read as `api` tables by DuckDB SQL
  (tests/test_connection_kinds.py, tests/test_connection_tables.py: is_api, web_call_table on a blade's
  `[web_call]`, a write rows call never a table). Unnest this column (tests/test_unnest_step.py: a list
  keeps an empty row, a struct's fields never clash; the header menu in a browser), The DuckDB query shown
  and saved on an operation (browser), the lineage on to the notebook cell that reads a structure
  (tests/test_structures_routes.py). The main line's grid.css had lost one closing brace in its merge
  (`.conn-block.conn-worn.conn-two`), which unstyled everything after it (Structures and APIs): put back.
- The whole suite after the merge, Chromium: 3,523 passed, 42 skipped (23 minutes).

NOT checked:
- A real company API (only the made-up services on 127.0.0.1), and OAuth sign-ins through Send.
- Very large documents in Edge (the tree shows 200 items of a list at a time and folds past depth 2; a
  50 MB document was not tried in a browser), and Edge itself (Chromium only here).
- Make into blades in a browser (HTTP only: tests/test_api_explorer.py, an older connection made from a
  made-up document beside its file, and one with nothing kept refused with what to give); an older
  connection made on another computer (a Windows path read here).
- Return as table…'s dialog in Structures in a browser (the HTTP path is tested; the dialog was not).
- `sab.structure` outside the app (it reads a file of that name beside the working folder).

## A connection's tables in DuckDB SQL (2026-11-17, branch connection-sql)

- **The rules** (tests/test_connection_tables.py): brackets quote a connection's name only (a list index
  and a string stay); references found in sqlglot's tree and resolved in any case, a Power BI table two
  datasets share asking for its dataset, a database name two schemas share asking for its schema, an
  unknown name suggesting the near one and listing what there is; the rewrite keeps each table's alias; a
  web call blade is a table only with return_as_table.
- **Over HTTP** (two SQLite connections and the Power BI stand-in, made-up data): one DuckDB query joining
  a Power BI dataset's Sales with two SQLite connections' tables (the right totals; the stand-in saw
  EVALUATE); the second query kept from the session's read (the stand-in not asked again), Refresh reads
  again; the grid's read-only cell reads `sab.sql(<query>)`; Date shared by two datasets refused with
  both names, an unknown table listing the tables, a key vault "not a connection"; the agent's same SQL;
  the tree (datasets, each table's SQL name), Open all of a dataset (4 grids), a kernel's prepare and the
  Arrow read. **Never a cut table:** 15,000 rows joined (a 10,000-row cut would give other counts), only
  the used columns sent; `region = 'South' AND order_id > 3000` sent (4,000 rows came back, not 15,000), a
  LIMIT sent alone and not with GROUP BY, ORDER BY or an unsent `<>`; past the limit (set to 10,000) the
  table refused with its count and how to narrow it, the narrowed query answered.
- **Every kind** (tests/test_connection_kinds.py): every starter template has a tables kind or a reason;
  the 113 built-in starters are none; each kind lists (its tree) and reads (`SELECT count(*) FROM
  [Kind].<table>` in the "+" tab) on a stand-in: SQLite, the Power BI stand-in, Dataverse's SQL endpoint
  stood in for at its cursor (a made-up SQLite file reading `SELECT TOP n` and INFORMATION_SCHEMA), the
  Dataverse Web API stand-in, a Python connection, an API connection (a Python one tagged api), a
  workbook's sheet, a folder's file by its name without .csv. The endpoint off said plainly (no Web
  API); a Web API connection's card offers the switch, and after it reads on the SQL endpoint.
- **In a real kernel** (tests/test_connection_sql_kernel.py): `%%sql -> by_manager` with no connection
  joins `[Shop].orders` with the kernel's DataFrame, its output saying the read; `sab.sql(query)` the same;
  an unknown table in the app's words.
- **In the browser** (Chromium, tests/e2e/test_connection_sql_page.py): the Connections page's tree
  (search, Preview, Copy name on the clipboard, Open all with its confirm, three grids); a `%%sql` cell on
  DuckDB completing `[Sh` to `[Shop].` and `ord` to `orders`, its head showing Shop, running to a
  DataFrame. Pictures: connection-tree.png, sql-cell-names-a-connection.png.
- **Not checked:** the owner's real Power BI workspace ("Finance Captive") and its 14 model_* tables; a
  real Dataverse SQL endpoint (TDS, pyodbc, ODBC Driver 18 and the Entra token: stood in for at the cursor
  only); filters sent to SQL Server, Trino, Snowflake or Oracle (written by sqlglot, run here on SQLite
  only); very large tables (the count-first and the limit on 15,000 rows, not millions; memory for a
  multi-million-row read); a Python connection's or the Web API's limit-plus-one read past the limit;
  Query in a notebook with the Workbench window open (the clipboard path is the one run); connection
  colours on the cell's head (another branch).
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,314 passed, 42 skipped, 2 failed in
  21 minutes; both were tests of this branch's own changes (the Add API test looked for an API's card on
  the Connections page, where APIs no longer show; the Dataverse page test loaded its catalog through the
  form's new SQL endpoint default, which needs pyodbc): fixed, those two files then 4 passed.

## context.md, the app's live picture beside the agent (2026-11-17, branch context-md)

- **Rules** (tests/test_context_md.py): from a made-up state (a PostgreSQL connection and a Power BI
  workspace with two datasets sharing a Date table, three grids with steps, a relationship, two variables,
  two documents) the sections in order, the SQL names (`[Warehouse].sales."Order Lines"`,
  `[Finance Captive]."Sales model".Date`, `[Finance Captive].model_Report`), a failing connection's error,
  steps in words; no filter value, SQL step text or variable value anywhere (scanned for the made-up
  value); APIs and Structures only when given; a hostile table and column name stays one code span (no
  line starts a heading); a catalog capped at 40 tables with the rest's count and catalog_search, a table
  at 30 columns; over the budget the trims in order (columns, then catalog lists), each with its note, and
  a last cut within the budget; which sections changed.
- **The service** (fakes, a stepped clock): a change written once it settled, a notice that changed
  nothing writes nothing, no notice writes nothing, a burst of changes is one write.
- **HTTP** (TestClient, the Claude stand-in): Launch Claude writes CLAUDE.md (`@context.md`, the stable
  header), context.md and the hook with `--folder`; context.md has the table, its step in words, the
  variable by name and no cell or filter value; `/claude/context` (app_context) and the MCP resource give
  the file's exact text; a prompt with nothing changed rewrites nothing (same mtime) and says nothing; a
  table pushed: the folder's hook prints "context.md changed: Open tables" with the path and the file has
  it; the plugin's hook (no flag) in that folder prints nothing. Two sqlite connections, a loaded catalog
  and a relationship model from a running app: colours by name, the catalog's tables by SQL name, the
  other's "catalog not loaded", the ERD's line, no source column names.
- **Not checked:** a real Claude Code reading `@context.md` at start and re-reading on the hook's line (the
  import syntax is Claude Code's documented `@path`; not run here); Claude Desktop reading the resource; a
  Power BI or Dataverse connection's live catalog in the file (the made-up state covers the naming); APIs
  and Structures (their branch); the file's write load during the browser suite beyond its passing.

## Lakes and SharePoint as connections (2026-11-17, branch lakes-sharepoint)

Checked here, against tests/lake_standins.py (one server on 127.0.0.1: Entra's token endpoint and a managed
identity's, the ADLS Gen2 DFS API over a made-up lake on disk, a OneLake workspace on the same API, Graph
for a made-up SharePoint site), made-up data only:
- each kind lists and reads through the contract and by name in DuckDB SQL (tests/test_connection_kinds.py,
  tests/test_lakes.py): Delta tables read by their log here (a checkpoint, then commits) over HTTPS with
  DuckDB's httpfs and a header secret; a local Delta Lake by DuckDB's own delta_scan (DuckDB 2.0.0, its
  delta extension installed); Parquet, CSV and hive-partitioned folders; OneLake's Tables/ and Files/;
  SharePoint lists (typed columns, lookups and people, paging, $filter on indexed columns, a refused filter
  applied by DuckDB); a library's file index, a workbook's sheets and named table, a CSV and a Parquet
  document (each downloaded once, by eTag);
- a filter on a partition column reads only that partition's files (the stand-in's requests);
- time travel by version and by day; a version past the last, and a version of a CSV, refused plainly;
- ROPC: the token endpoint takes grant_type=password; a wrong password is AADSTS50126 in plain words, an MFA
  account AADSTS50076; the password, the client secret, the token, the account key and the identity header
  are in no answer and no file of the state folder; a SAS's signature is never shown (sig=****);
- the account key signs an account SAS here, which the stand-in verifies with the made-up key;
- every setting mapped to an environment variable, read back into the form, listed by env_settings and on
  the Variables page;
- writes: Parquet and CSV files through the DFS API's create, append and flush; the Delta dry runs (counts,
  vacuum's refusal under 7 days); real Delta writes (merge, append, delete, optimize, vacuum's dry run) with
  deltalake 1.6.6 on a folder here (SAB_DELTALAKE_PATH: the package is not the app's; the test skips without
  it); SharePoint list items created (25: two batches of 20 and 5, each first answered 429), updated by
  id and by a key column, deleted;
- the browser (Chromium): the Lakes and SharePoint group and its five icons, each lake form's sign-ins, a
  SharePoint lists connection made through the form (ROPC first, the tenant from SHAREPOINT_TENANT_ID,
  the password from SHAREPOINT_PASSWORD), Test's first rows, the trees of a data lake (each table's words,
  a Preview) and a document library (by folder; a sheet opened as a grid).

Not checked (nothing real reached):
- a real Fabric workspace (OneLake's DFS endpoint, a lakehouse's Delta tables, a warehouse's SQL endpoint
  through pyodbc and ODBC Driver 18), a real storage account, a real SharePoint tenant or Graph;
- DuckDB's azure extension (abfss://, the access_token provider) and delta_scan against real Entra tokens:
  the stand-in moves the storage to http://127.0.0.1, where that extension's delta_scan does not go, so the
  log-read path is what runs there;
- the deltalake package against Azure or S3 (only on a folder here), and S3 at all (DuckDB's glob and
  read_blob with an s3 secret);
- MSAL's ROPC (the stand-in's sign-in uses the standard library's POST; MSAL would look for Microsoft);
- pypdf for a PDF's text (a Word document's text was checked).

## The Data Explorer (2026-11-17, branch data-explorer)

- **Rules** (tests/test_explorer.py): `cust` matches `customer_id`, `CustomerKey` (start), `id_customer` (a
  part), `Accustomed` (inside), not `orders`; `customerid` matches `customer_id`; words spread over the path
  but one must be in the name; the search as sent (kinds as a list or "a,b", an unknown kind refused, the
  limit capped at 200, a 201-character search refused); 32 results grouped in order and counted with the
  groups cut to the limit; each result's insert code (a connection's table, an open table, a quoted column
  with its table's variable, a variable, a blade and a vault).
- **The seam:** a stand-in "structures" provider joins the search (its path kept) and a failing provider
  is skipped; a kind filter leaves it out.
- **HTTP** (two made-up SQLite connections, two pasted grids, a variable): Ledger's catalog not loaded is
  offered and Shop's searched; `customers` with `[Shop].customers` and its insert; the columns
  `customer_id` (orders, typed INTEGER), `CustomerKey`, and the grid's `customer_id`; both loaded:
  `customer_id` across Ledger, Shop and the grid; `column=CUSTOMER_ID` gives invoices, orders, sales;
  the connection picker in any case; the grid's result (source, grid, variable); the variable by name with
  no value anywhere in it; an empty search lists without catalog columns; the agent's answer the same;
  a bad kind is a 400; `/workbench?panel=explorer` serves the window's page.
- **Browser** (Chromium; tests/e2e/test_data_explorer.py): the pane off, then beside the data notebook;
  `cust` grouped and counted with the SQL name's path; Insert into a SQL cell (the SELECT) and a Python cell
  (`sab.sql(...)`); beside a script; Show tables with this column; the agent's explorer.search drives the
  box; Ctrl+Shift+E closes it. App mode: the canvas's Streamlit cells panel lists a named cell; Starters
  takes its place. Pop out: the window titled Data Explorer, with the rail, carries the search; a search
  there; a table result's drag data (taken from the window's own dragstart) dropped on a SQL cell's editor
  in the Workbench writes the SELECT; Insert from the window into the Workbench's selected cell; Move back
  reopens the pane with the window's search and closes the window; the agent's explorer.popOut and
  explorer.moveBack do the same. Ctrl+K on the grid page: the dialog, its results, Open the Data Explorer.
  The older browser tests that used the Data panel follow the new places (panels, notebook kinds, groups,
  the rail's Apps, modes, connection colours, starters, text cells, Streamlit).
- **Structures and APIs** (after the merge): a structure's paths (lists as `[]`, a quoted key, the parts
  of the first place with a key, the cap); an API's Return-as-table call by `[Orders API].listOrders` with
  its columns, a plain call and a write rows call left out (a stand-in blade list); over HTTP a pasted
  structure's `customer id` gives `$.orders[].customer.id` with its parts and parent, and an empty search
  its name; in the browser a path's result, its Copy path title, and Open at this node showing the
  Structures page at `$.plums[0].grower.farm_id`.
- **Not checked:** a real drag between two browser windows (Playwright cannot; the drop is sent with the
  data the window's dragstart set); a canvas drop of a result (not built); an API result from a real API
  in the library (the provider is tested on its blade list); a saved structure file's Open at this node
  (opened first through /structures/open); Load its catalog's button in a browser (the
  route is the existing connections_load_catalog); the resize grip by pointer; Edge.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,394 passed, 42 skipped, 1 failed in
  22 minutes: the landing pages' test (it passed alone; its `.wb-data` check is now the Data Explorer's,
  off on a landing page), then that file 5 passed.
## Writing data: the Write starters (2026-11-17, branch write-blades)

- **Every starter** (tests/test_starters_write.py): the 13 Write functions are each one public function
  with a typed signature (dry_run True by default), private helpers, imports and constants only, and load
  without running anything; the 43 calls are the call only (`sab.blade` line, then the call, dry_run=True
  its last argument), each naming a function whose tags cover its own; every write test runs the call
  with its function's code in place of the `sab.blade` line (as functions.py will hold it). The calls read, fill from their form's
  values, say the agent's rule in their description, parse as Python, and their functions list their packages (DuckDB and
  each driver). Every connection kind is writable or read-only with a reason, and every one of
  connection_tables' tables kinds is writable, read-only (Power BI, your own Python, an API) or decided by
  its template (a database, a file); every writable kind has a
  starter, every starter names writable kinds only, a read-only kind has none. `/connections`,
  `/connections/usage`, a connection's detail and `/connections/types` carry `writes`; the Write family
  lists Excel's writers and Power BI's refreshes too (`also`); a starter's form offers the connections of
  its kind first.
- **SQLite** (a read-only connection, as the form makes it: the file opened again to write): a dry run
  writes nothing and says the target, rows, types, statements, counts and 5 rows; append, upsert,
  delete, replace and create table give the right rows and counts; a failing second batch rolls the
  first back and is named; a table changed since the dry run is said; wrong columns, shared keys, a
  connection of another kind and a table that is there already are refused in words; a DuckDB relation
  and an Arrow table are rows.
- **PostgreSQL 16 and MariaDB** (the test bed, tools/testbed, with pymysql in the test environment):
  create table (the rows' types made PostgreSQL's; Region found as region), COPY, ON CONFLICT and ON
  DUPLICATE KEY UPDATE upserts with their dry-run counts, a failed batch rolled back, delete, replace.
- **SQL Server and Azure SQL** against a stand-in pyodbc that records every call (no SQL Server here):
  the #temp stage's CREATE in the target's own types (nvarchar(40), varchar(10), decimal(12,2), COLLATE
  DATABASE_DEFAULT), setinputsizes (SQL_WVARCHAR 40, SQL_VARCHAR 10, SQL_DECIMAL 12,2), fast_executemany,
  NaN as NULL, the MERGE ... WITH (HOLDLOCK) text, a dry run's COUNT join and rollback; a dropped
  connection (08S01, 10054) and 40613 each running the whole transaction again on a fresh connection
  (rollback, rollback, commit); MERGE refused -> UPDATE then INSERT after a savepoint; keys from the
  primary key, none refused; the identity column refused unless chosen, then IDENTITY_INSERT ON and OFF;
  a computed column refused; multi-row VALUES under 2,100 parameters (524 rows of 4); a delete by a join
  on the staged, distinct keys; exact types: a uniqueidentifier's text, datetime2 sized (93, 27, 7) so its
  fractions stay, a datetimeoffset as text with its offset (the same instant: DuckDB holds zoned times as
  instants, so the offset sent is the session's, not the row's own), bit, varbinary(max) sized (-3, 0),
  NaN and NaT as NULL.
- **Trino** against a stand-in driver: MERGE a batch at a time (VALUES of 2 rows), no commit or
  rollback; a connector without MERGE refused in Trino's words with the hint and "nothing was written".
- **Dataverse** (tests/dataverse_standin.py, now with $batch change sets, upsert by an alternate key,
  If-Match, 429): create with choice labels sent as numbers (Retail -> 19), a throttled $batch sent
  again; upsert counted 201/200; update refusing keys that are not records; delete of the found keys
  only; a refused change set rolled back and named, the batch before it written.
- **Files**: CSV, Parquet, partitioned Parquet (a folder per region; "add" beside the old files), JSON
  and an Excel sheet (the workbook's other sheets kept, rows added below) written and read back; an
  existing file refused unless replaced.
- **In the browser** (Chromium, tests/e2e/test_write_starters_page.py): the Write family (60 with the
  cross-listed four) in the Workbench's blade list; SQLite upsert dragged into a cell (the call only, `write_sqlite = sab.blade("Write to SQLite")` above
  it), its form giving the SQLite connection first and order_id as the key; the cell run in the Workbench's kernel (the
  function fetched by sab.blade from the starter pack) as a dry run
  (nothing written, "update 1 row, insert 2 rows"), then with dry_run=False (written); the Connections
  page's cards reading Writes and Read-only, the detail listing the starters.
- **Not checked:** a real SQL Server or Azure SQL (fast_executemany with setinputsizes on real types,
  MERGE's locking under load, Azure's transient errors as they really arrive, IDENTITY_INSERT
  permissions, temp-table collation conflicts on a real server, datetime2's seventh digit and a
  datetimeoffset's text through the real ODBC driver, the 2,100-parameter path on a real wide table); a real Trino MERGE on Iceberg or Delta
  Lake; Oracle (no driver or server here: its MERGE from dual and DELETE-based replace are untested);
  an ODBC source; a real Dataverse $batch (its multipart answer, alternate keys defined in a real
  environment, the 429 limits); MySQL itself
  (MariaDB stands in); a write in a notebook's own environment with the missing-package prompt.

## The editors' intelligence: completion, parameter info, quick info, the lint (2026-11-17, branch intellisense)

- **Rules** (tests/test_intellisense.py): Google, NumPy and reST docstrings give each parameter its
  words, returns and raises; IPython's lines (`%time`, `!ls`, `x = !ls`, `name?`) are Python of the same
  lines and a cell magic's cell is not Python; the app's names inside strings for sab.connection, sab.sql,
  sab.read, sab.dax, sab.blade, sab.structure, os.environ[...], .get, os.getenv, secret, %%sql and a
  table's `["…"]`; the lint: a syntax error's place, undefined names knowing earlier cells, the kernel's
  and builtins, a star import said once, unused imports faded with their removal (a whole line or one
  name), f-strings, `== None` with its fix, a bare except; the fixes: an import (a project module's, a
  common alias, the standard library), the Variables page's definition, the close name; an import joins
  its module's line or goes after the imports (a blank line before code); SQL by sqlglot (brackets read
  as names; T-SQL's own) and DuckDB's error placed; a project module's public names; the ranking (scope,
  project, app, library; the recent first; each label once); a call's required arguments as tab stops.
- **The use case** (tests/test_intellisense_service.py, real Jedi): the member list's documentation and
  snippet for a function in an earlier cell; `sab.` without its layers; each string source; an open
  table's columns after `orders.` and the connections' code names; a functions.py name with its import,
  none when imported, Jedi reading the project's modules (`from functions import wr`); parameter info's
  active parameter by position (0, 1) and by keyword (`mode=` is 3), its span and words; the hover; the
  lint across cells (an import a later cell uses is used) and magics; Ruff in a made-up environment
  (the folder's ruff.toml applied, its own E402 joining the app's F401 and E711 with their fixes) when
  Ruff is on this computer; without Ruff the Ruff answer's missing-package shape; DuckDB and sqlglot
  for SQL cells; a superseded request skipped; a notebook on disk checked cell by cell; over HTTP with
  a real kernel: Jedi's Interpreter on the live DataFrame (rain_mm), the hover's type and shape, the lint
  knowing the kernel's names, a method's parameter info; the agent's problems (reported, read, a file
  checked, cleared).
- **In the browser** (Chromium, tests/e2e/test_intellisense_page.py): `write_` shows the member list with
  the documentation panel open beside it (the docstring, each parameter's words); `write_sqlite(` shows
  parameter info with `connection: str` bold and its words, `,` moves the bold to `table: str`; hovering
  the name shows its quick info; in a script a typo and a missing `pd` get red squiggles within three
  seconds and the status bar says 2 errors, its list goes to the place, Ctrl+. offers Add import pandas
  as pd and adds it, the count drops to 1 error, and the server's problems (what the agent reads) say
  F821 alone. The Workbench's own browser tests (completion from the catalog and the kernel, the
  console, scripts) and the connection-SQL page's still pass.
- **Not checked:** pyflakes (not installed here: its path is untested), a Ruff install from the Problems
  list into a real environment, Jedi's Environment for another Python (a notebook's own environment; the
  app's Python was used throughout), a big library's first look inside the one-second budget on a slow
  computer (the page asks once more), signature overloads shown with up and down (no overloaded function
  in the tests), Windows paths in the Ruff folder choice.
- **The whole suite** (Chromium): 3,697 passed, 44 skipped, 11 failed under load. Run alone, five of
  those passed (the beta export, the Streamlit export's Allow, the rail, the Workbench's landing pages,
  the database forms) and six failed the same way on the branch's base (ec0d298, run alone with the same
  Chromium): the narrow window's sideways scroll, the agent's snapshot, the Application row, a script's
  HTML cell, the Power BI workspace and the swap's code following: not this branch's.
- **After the merge with data-explorer** (4580879): quick info stopped showing in the browser test. The
  Workbench page had grown wider than the window (the body's one grid column was `auto`, so the longer
  status bar, Data Explorer's toggle added, set its width: 1,353 px in a 1,232 px space), Monaco's cursor
  scrolled the window 75 px sideways, and the rail covered the start of every line: the pointer meant for
  the name landed on the rail's Apps button. The page's column is now `minmax(0, 1fr)` (no sideways
  scroll; a crowded status bar is cut at its right end, as its own overflow already said), and the test
  checks the window does not scroll sideways before hovering.

- **After merging the main line (f96b8f9)** the whole suite (Chromium): 3,633 passed, 44 skipped, 9 failed
  and 1 error. Alone, four of those passed (Visualizations' pages, Show the math, a table cell's maker, the
  Workbench's agent test: load). The other six fail the same on f96b8f9 itself (run from its own tree):
  a script's HTML cell (+ Cell gone from scripts), the Power BI page, a deleted connection's tables, the
  agent snapshot, the narrow window and the Application row's Zoom (zoom moved to the status bars). None
  of them touch the Data Explorer.

## SQL Server and Azure SQL, made robust (2026-11-17, branch sql-server)

Checked here, with no SQL Server (no container could run: docker's daemon is not running in this
environment): tests/test_sql_server.py runs the connection's own code against a stand-in for pyodbc at the
seam (it records connection strings, the token attribute and statements, and answers typed rows), with a
clock and sleep of the test's own: each error number in words (18456, 40615 with its address, 40613,
certificate, IM002 per system, not found, timeout, 229, 3906), Azure's transient numbers, the resume wait
(1, 2, 4 s) and its words, other passing errors tried five times, a refused login never retried and the
password never in the words; the driver chosen (18, then 17; strict refused on 17; none said; mssql-python
used with no ODBC driver); every option in the string (a password with ; and } braced); the token's struct
and a new connection five minutes before it runs out; a read retried on a new connection, a write not;
geography, hierarchyid and sql_variant read as text; the Arrow type of 20 declared types (golden); batches
and a column that does not fit made text; datetimeoffset's bytes; SQLCancel on an interrupt (the main
thread interrupted while the statement waits); for_writes and the Write starters' detect; every sign-in's
code run (azure-identity stood in for; the app registration's and managed identity's requests stood in
for); environment variables written and read back on server, database, user, client_id, tenant_id; the
catalog, foreign key and count T-SQL parsed by sqlglot's tsql dialect; foreign keys (composite, unique ->
one-to-one, disabled) as the model, and through the route into /relationships; the card's about lines and
a failing card's words. Browser (Chromium): tests/e2e/test_sql_server_page.py (the form's eight sign-ins,
Options folded, Encryption a choice, the tick, the server from a variable kept across a sign-in switch; a
failing card's words; Import relationships).

NOT checked: a real SQL Server or Azure SQL (the T-SQL against the system views has only been parsed, not
run), ODBC Driver 17/18 and mssql-python themselves (mssql-python's `attrs_before` and `timeout` arguments
are assumed, with a fallback to the string alone), Azure SQL serverless resume, Entra tokens from Microsoft,
Windows integrated and Kerberos, the read replica routing, arrow-odbc (not measured), SQLCancel against a
real driver.

Whole suite with Chromium (2026-11-17, branch sql-server): 3,697 passed, 44 skipped, 11 failed. Run again
alone, on this branch and on its base (ec0d298) alike: test_beta_export_page (the zip), test_html_cells_page
(a script's HTML cell: Add cell never came), test_powerbi_page, test_ui's agent snapshot, narrow window and
Application row (Zoom out), test_swap_connection_page's deleted connection (the notebook not rewritten)
fail on the base too; test_rail_page and test_streamlit_page's export passed alone (load). One was this
branch's: test_workbench_page's database form order (the SQL Server sign-in's new label; fixed).

After merging claude/vibrant-mendel-j04osj (lakes and SharePoint) into sql-server: the whole suite with
Chromium, 3,767 passed, 45 skipped, 8 failed: the seven known on main (beta export zip, a script's HTML cell,
the Power BI page, swap-connection's deleted connection, the agent snapshot, the narrow window, the
Application row's zoom) and test_workbench_feedback's landing pages, which passes alone (load).

## Extensions page and install machinery (2026-11-17, branch extensions)
Checked: tests/test_extensions.py (the catalog's statuses; discovery from made-up entry points, a broken one left
out, the environment variable; the GitHub wheel's address; Install's exact uv command and its restore; an update of
the base keeping an installed extension at the new version and restoring it at the old; the helper's hand-over of a
change; a development checkout refusing with what to run; Remove asking first; the agent's Install and Remove
waiting for Allow; the routes with the token); tests/e2e/test_extensions_page.py in Chromium (the rail's icon above
Settings, the page's Preinstalled and Coming cards, the version mark's tooltip, Install's progress through a
stood-in restart with a made-up available extension, a development checkout's words on the card).
NOT checked: a real uv install of an extension wheel from a GitHub release (none exists yet); Windows (the helper's
stop_in path for an extension change is the update's, untested here); the page reopening after a real restart.

## The library (2026-11-17, branch library)

- **Rules** (tests/test_library.py, made-up names and values): variables.toml and local/variables.toml
  sorted, stable and read back (quotes, newlines, DEL); which folder each blade goes in (vaults/,
  connections/, blades/); `<name> from <project>` (no brackets, numbered, within 64 characters); the
  notice's words; every starter blade's portable text reads back to the same text.
- **HTTP**: nothing written until something is saved, then README.md and .gitignore (`local/`); a
  connection, a vault, a blade, an API (apis/Shop/), shareable, local and keyring variables and a colour
  each in its own file; every file scanned for the test's three made-up secrets (none); the user's README
  kept; everything saved again unchanged leaves every byte and every modification time as it was; a copy
  of the folder without local/ (a clone) on another state folder with an empty keyring: the same blades,
  Warehouse "needs a password", the shared variable's value, the local one empty, the keyring one Not set,
  the colour; its password set there, nothing lands in the folder; back to the default folder; the
  folder refused when relative or a file; the agent's change refused on No (403) and done on Allow; the
  choice kept across restarts. Migration: older blades/*.json, variables.json, colours.toml and tangs
  written as library files, the old ones in backup/before-library-<date>/, the notice taken once, nothing
  said on the next start; an older .sab's own blades: the same skipped, a different one kept as "Shop from
  older", a new one added, the notice, the library's own file untouched, the next save without
  .sab/blades. test_project_scope, test_sab_projects and test_connection_swap_routes rewritten for the
  library (dashboards still each project's own; import from a .sab into the library; "computer" refused).
  The standalone client (sab.blade without the app) reads the library (test_standalone).
- **In the browser** (Chromium, tests/e2e/test_library_page.py, its own server with older stores laid out):
  the move's notice on the page, Settings' Library (the folder, the counts, Change…), the Variables page's
  key vault card and Add key vault's types, the vault's detail opened from it, the Connections page with no
  vault card and no Key vaults types; test_workbench_page's vault made from a password's form now found on
  the Variables page.
- **The whole suite** (Chromium, Streamlit 1.67 in its own Python): 3,763 passed, 45 skipped, 10 failed in
  31 minutes. test_tour failed under load and passed alone. The other nine fail the same on 072ed1a,
  before this branch: test_intellisense_page (the hover), four test_starters_page drags,
  test_table_cells_page's maker link, test_write_starters_page's hover, test_client_install
  (adapters/intellisense.py starts a process), test_tool_sweep's workbench_problems (a 500).
- **Not checked:** a real GitHub clone on a second computer (a copied folder stands in); Windows paths
  (library.json, the backup's move, file names); a real system keyring (Credential Manager, Keychain);
  Edge (Chromium here).


## The Accounting extension (2026-11-17, branch ext-accounting)
Checked by tests (made-up data: a made-up reinsurer's cessions, tests/accounting_data.py):
tests/test_accounting_workbook.py (each block kind read back cell by cell with openpyxl: a title merged and
bold, text, a table's labels, formats, widths, total formulas, a colour rule's range, freeze panes, print
setup; a pivot against DuckDB's own GROUP BYs, with an average's total; a count pivot; the block DuckDB reading
no file; a chart with a wrong category said by its sheet and cell; Export's workbook.py run in a fresh Python
with a data.py beside it, the workbook the same cell by cell as Play's, charts and freeze panes too; a missing
table said by workbook.py), tests/test_accounting_statements.py (bindings checked; a template filled: fixed
text and its look, values, the number, a kept date format, three lines in a one-row area, the totals moved and
made longer, merged cells and a named range moved; build_statements' dry run writing nothing, the files, the
numbering, the totals, the register, nothing written over; one workbook of sheets; a file name naming a missing
column), tests/test_accounting_routes.py (the capability check; off: no /accounting, only the bi type, no
commands, a type refused; on: an Accounting project's files and .sab/project.json, its mode and a bi
project's; a design's blocks placed, moved, played through a grid's filter, downloaded, saved without rows,
exported; templates imported, bound, a place that is not there refused; the build refused without its dry
run, then built, the register as a grid; the extension's commands; the package's entry point and version;
the MCP listing the mode's tools first). Browser (Chromium): tests/e2e/test_accounting_page.py (the canvas
with a table, a pivot and a combo chart; a block dragged and sized; Play's preview and its chart; Download;
Save; Export; a template's cells clicked and bound; the statements' dry run then Build and the register;
"New Excel workbook" offered and the Blades page's Excel, Files and Write families with Show all in an
Accounting project, and neither in a bi project).
LibreOffice 7 (soffice --headless, to PDF) opened a played workbook (its totals recomputed, colour rules
shown), a built statement and a one-workbook build of six sheets.

NOT checked: Excel itself opening the files (Windows, macOS); the extension installed from its wheel with
`uv tool install --with` (its wheel was built and its entry_points.txt read; discovery was tested through
SWISSARMYBENCH_EXTENSIONS); the extensions branch's Install and Extensions page with this package.

Whole suite with Chromium (2026-11-17, branch ext-accounting): 3,859 passed, 45 skipped, 7 failed, 2 errors. One
was this branch's (a new project wrote .sab/project.json for the base's type too; now only an extension's type
writes it; fixed, test_streamlit_apps passes). test_client_install (adapters/intellisense.py) and test_tool_sweep's
workbench_problems fail on the base too (files this branch did not change). test_rail_page, test_table_cells_page,
test_ui's wide column, test_workbench_feedback's landing pages and test_workbench_page's two errors pass alone (load).

## The Power Apps extension, phase 1 (2026-11-17, branch ext-powerapps)

Relied on (read 2026-11-17):
- Microsoft Learn, **Power Apps CLI command reference** (code-apps/reference/cli, ms.date 2026-11-10): `pa app
  init|add data-source|remove data-source|run|push|list`, `pa auth login|status --json|switch`, `pa connector
  list --json` (id, name, displayName, description, isTabular), `pa connection list --json`; non-interactive
  use needs every option given. **Environment variables** (2026-10-02): `pa app run`'s local host on 8080,
  the app at `http://localhost:3000` unless `localAppUrl` says otherwise.
- **Quickstart** (code-apps/how-to/create-an-app-from-scratch, 2026-08-13): `npx degit
  github:microsoft/PowerAppsCodeApps/templates/vite my-app`, `npm install`, `pa app init`, `pa app run`
  (Local Play), `npm run build`, `pa app push`.
- **Connect to data** (2026-10-02): generated `src/generated/models/*Model.ts` and `services/*Service.ts`;
  Excel Online connectors not supported yet.
- **Overview** (2026-09-23): an administrator enables code apps per environment (Power Platform admin center,
  Manage, Environments, Settings, Product, Features, Power Apps code apps, Enable code apps); no command
  line reads that setting, so the app says it plainly when a command's error names it.
- **pac code** (power-platform/developer/cli/reference/code, 2026-10-25): "(Preview) ... use the npm-based
  Power Apps CLI instead": so `pa` is used (docs over the plan, said in docs/ideas.md).
- **pac auth** (2026-10-25: create, list, select, token), **pac env** (list, who), **pac connector**
  (create, update, download, list --json), **pac install** (the .NET tool `Microsoft.PowerApps.CLI.Tool`;
  `pac` alone prints "Version: x").
- The template's `package.json` and `vite.config.ts` (the Power Apps Vite plugin) read from the
  PowerAppsCodeApps repository's main branch.
- The npm packages themselves, read (not run against a tenant): `@microsoft/power-apps-cli` 1.4.2 (its
  `power.config.json` schema; `pa auth status --json`'s shape; the push's "App pushed successfully. You can
  play your app at <link>"; `pa app run` starting `npm run dev`; the connectivity service it reads for a
  connector, `https://api.powerplatform.com/connectivity/connectors/<name>?api-version=1&$filter=environment
  eq '<id>'`, its `properties.swagger`) and `@microsoft/power-apps` 1.6.0 (the host bridge: the spike in
  docs/ideas.md).
- The Power Platform API's documented **Get Connector By Id** (api-version 2024-10-01) returns no definition:
  the CLI's own `api-version=1` read above is what the app uses, not a documented contract.

Checked here: every command line (tests/test_powerapps_rules.py), the secret guard, each output's reading
(recorded made-up output in the documented shapes; pac's tables with headings a single space apart, as the
docs print them), power.config.json's sources, the generated files, the tree, the tools' versions and
install commands, the connectors in the explorer's model, custom connector files from a made-up OpenAPI
document (each sign-in), the TypeScript snippets; through the door with the tools stood in by recorded
fakes on a PATH of their own (tests/powerapps_fakes.py: pa, pac, npm, npx, node) and the connectivity
service by a made-up stand-in (tests/test_powerapps.py): off and on, the missing-tool answer, sign-in,
environments and profiles, New code app, code apps switched off said plainly, sources added and removed,
the editor's file read and saved (and refused outside the folder), connectors listed, searched, read from
the app's schemas and from the service (its token never in a run, the log or an answer), Run live through
the proxy (a made-up dev server; a wrong key refused), Push's dry run and the agent's push declined then
allowed, a custom connector made, every action an agent command. Node.js and npm for real (version
reading) where present (v22 here). Browser (Chromium): tests/e2e/test_codeapp_page.py (the rail's area off
and on; New code app to Push; a connector explored and added; Run live in the pane; the runs; a custom
connector's dry run and Make; App.tsx in the Workbench with Monaco's TypeScript service marking a type error,
saved with Ctrl+S; New TypeScript file in the code app mode; the Blades page's families).

NOT checked: a real Power Platform environment, a real `pa` or `pac` sign-in, `pa app init`, `add
data-source`, `push` or `pac connector create` against a tenant, the template downloaded and installed for
real (degit and `npm install` were stood in for), the Power Apps Vite plugin's dev server under `--base`
(its printed Local Play address, its own config route), Local Play itself, the local runner (`pa app run`),
the connectivity service's answer for a real connector, `pac env list`'s and `pac auth list`'s exact column
widths on Windows, Windows and macOS (the `.cmd` wrappers of the fakes are written but not run), the
connector spike in a running host.

Whole suite with Chromium (2026-11-17, branch ext-powerapps): 3,880 passed, 45 skipped, 6 failed. Mine: one
(test_streamlit_apps: a new folder project now holds .sab/project.json, from the base's project types; the test
fixed). The intellisense pair (test_client_install: adapters/intellisense.py starts a process;
test_tool_sweep: workbench_problems answers 500 for a path that is not there) are untouched by this branch.
test_sandbox_pages, test_table_cells_page and test_workbench_page's SQL cell passed alone (load).

## Extensions: one-click Install and Remove from the released app (2026-11-17, 0.0.17)

Checked on Linux in a container, as a user would run it: `uv tool install "swissarmybench[server]==0.0.17"`
from PyPI into its own tool folder and home, `swissarmybench start --background`, then the Extensions page's
routes (the buttons' calls) against that running app.

- Power Apps: Remove (asked first, then confirmed) restarted the app with Power Apps available; Install
  restarted it in about 10 seconds with Power Apps installed and `/powerapps/project` answering 200, no
  failure note. Accounting's Install then kept Power Apps: the tool holds swissarmybench,
  swissarmybench-accounting and swissarmybench-powerapps 0.0.17, and `/app/modes` lists bi, accounting and
  codeapp.
- Found and fixed on the way: 0.0.15's helper let uv fetch the wheel from the GitHub release, refused with
  401 on the release's download redirect (in this proxied network; curl and Python's urllib fetch it), so
  0.0.16 downloads the wheel itself and hands uv the file. 0.0.16 and 0.0.17's first try then failed with
  "no version of swissarmybench[server]==X" within a couple of minutes of the version reaching PyPI; 0.0.17
  adds `--refresh-package swissarmybench`, and the same Install minutes later worked. Right after a release
  the index can still lag: the app then starts as it was and says why (Install again a little later).

NOT checked: Windows and macOS installs (the installers' own jobs run on Linux and Windows in release.yml;
Install from the page was not run there), the tray's menu during Install, and Edge.

## Projects as folders and the Project Explorer (2026-11-17, branch project-folders)

Checked:
- New project scaffolds a folder (data.ipynb, data.py, .gitignore with `.sab/data/`, README.md,
  `.sab/project.json`, `.sab/.gitignore`), opens it and saves at once; a save that changes nothing changes
  no byte (same bytes and the same modification times); close and open bring the tables back with their
  steps, Visualizations and the relationships; Autosave (on by default) writes `.sab/project.json` once a
  change settles, off keeps it still (tests/test_sab_projects.py, test_project_scope.py).
- A folder made a project around its files writes nothing over (.gitignore, README.md, notes kept); a
  folder with data.ipynb and no .sab/ opens; Keep its rows writes `.sab/data/<table>.parquet` and an
  untick removes it; Copy project to (rows and caches left unless ticked); an old .sab imported (its
  Visualizations, model, steps, dashboards placed) and a hostile one (`../`) refused before anything is
  written; recent projects are folders; no secret, token or password in any written file.
- The Project Explorer: cards from a made-up projects folder (types, counts, the branch from a made-up
  `.git/HEAD`, a detached head), every sort and the custom order kept across a restart, filters, a moved
  project located, rename, remove from list (files kept), Show in folder and Delete refused to the agent,
  Delete to the freedesktop Trash on the typed name, the projects folder changed by the agent only on
  Allow, the types explained (the base's two, Accounting's when on) (tests/test_project_explorer.py).
- Browser (Chromium): the cards, a missing card removed, opening one, Home back to it; sort change and a
  dragged order kept after a reload, Move right; the empty state and New project from a beginner's card
  (the "?" explanations, the projects folder named); Open project… with the folder chooser; Save clears
  the ●; saving loose work makes a project and asks Keep its rows; Open a .sab file… imports into a
  folder; the tour on the Start page only; a notebook imported from another project folder
  (tests/e2e/test_sab_projects.py). Screenshots light and dark.

Not checked:
- The Windows Recycle Bin and macOS Finder trash paths, and Show in folder on a real desktop (no such
  desktop here; the freedesktop Trash was checked).
- The installers' unregistration on a real Windows or Linux desktop (checked as text only).

## The Streamlit extension, preinstalled (2026-11-17, branch ext-streamlit)

Checked:
- The whole suite with the extension on (tests/conftest.py), Chromium for the browser tests: 3954 passed,
  45 skipped; 6 failed and 1 error under load, each passing alone (test_structures_apis_page write rows,
  test_table_cells_page maker stays put, test_ui application row, test_workbench_feedback landing pages,
  test_workbench_page key vault and the agent works the window) and test_performance's million-row target
  (timing under load).
- The BI base without it (SWISSARMYBENCH_EXTENSIONS=-streamlit): /app/modes is the base alone with no canvas,
  /streamlit/* answers 404 naming the extension (user and agent), a new project has no canvas and no Streamlit
  requirement, a `streamlit` project is refused plainly, a .stapp.json says which extension opens it, a cell
  that calls Streamlit opens as a plain cell, the Extensions page offers it (Available, Install); a fresh `sab`
  lists no streamlit_* tool and a call names the extension (tests/test_streamlit_extension.py). In Chromium:
  no Apps area on the rail of the home page and the Workbench; with it, the card says Preinstalled with Remove.
- The package's layers (domain without I/O or services, services without adapters or doors) and that no base
  module imports it.
- The real wheels: `uv build` of the base and of extensions/streamlit (its entry point in the wheel); the
  built install.sh run on Linux with a temporary uv tool folder found the Streamlit wheel beside the base's and
  installed both (`--with`); tools/smoke_install.py against that install passed, including the new check (the
  extension installed and preinstalled, the streamlit type offered, /streamlit/apps answering).
- Remove (asked first) and Install of the preinstalled extension, an update keeping its wheel, and the
  bring-back at the first start after an update from a built-in version: with the helper stood in.

NOT checked: install.ps1 on Windows (the release's job runs it), a real update from 0.0.17 to the next
version through the bring-back (needs both released), Remove and Install of Streamlit from the released app's
page, macOS, and Edge.

## The Power Apps extension, phase 2: the data notebook on Deno (2026-11-17, branch ext-powerapps-2)

Relied on (read 2026-11-17):
- Deno's **Jupyter kernel** documentation (docs.deno.com/runtime/reference/cli/jupyter, last updated
  2026-08-26): `deno jupyter`; the kernel runs with `--allow-all` ("a temporary limitation"); rich output
  through an object's `Symbol.for("Jupyter.display")` method returning a MIME bundle; `npm:` imports.
- `deno jupyter --help` (Deno 2.9.6, here): `--kernel` and `--conn <file>` start the kernel (the kernelspec's
  argv the app writes). Its own warning: "deno jupyter is unstable and might change in the future".
- Deno's **installation** page (2026-07-09): `npm install -g deno` on every system, `brew install deno`,
  `winget install DenoLand.Deno`, the shell installers.
- DuckDB's **Node.js (Neo) client** documentation (duckdb.org/docs/2.0/clients/node_neo/overview; no date on
  the page, latest stable 2.0.0): `DuckDBInstance.create(":memory:")`, `instance.connect()`,
  `runAndReadAll`, `columnNames()`, `columnTypes()` (each `toString()`), `getRowObjectsJson()`, named
  parameters as an object to `run`. npm's dist-tags (2026-11-17): latest `2.0.0-r.1`.
- `deno bundle --help` (2.9.6): `--platform browser`, `--format esm`, `--no-remote`, `--no-npm`, `--config`,
  `-o` (experimental, says Deno); it fetches esbuild from npm once.

Checked here, with a real **Deno 2.9.6** (from npm, in a scratch folder) and the app's Python:
- The kernel through jupyter_client: state shared between runs, top-level await, `npm:@duckdb/node-api@2.0.0-r.1`
  imported and run (DuckDB 2.0 as in the app's Python), a `Symbol.for("Jupyter.display")` bundle as an
  execute_result, `console.log` and `console.error` as streams, an error as `ename`/`evalue`/`traceback`
  (`at <anonymous>:line:col`), completion (`Deno.ver` -> `version`). Plain values come with colour codes
  (taken out). **Deno's kernel refuses an ipc address** (`invalid host ... invalid char found in FQDN`): it
  listens on 127.0.0.1 with signed messages. **A folder with a package.json and node_modules (a code app)
  makes Deno refuse an `npm:` specifier the package.json does not list**; `DENO_NO_PACKAGE_JSON=1` (set for
  the kernel) lets it fetch DuckDB's package as anywhere else.
- DuckDB in that kernel: JSON rows give BIGINT as strings ("36") and DOUBLE as numbers; `read_json_auto` of
  a JSON-lines file; `COPY (...) TO ... (FORMAT parquet)`; `read_parquet` views of the app's Parquet;
  DuckDB 2.0's error words `Catalog Error: Table with name X does not exist!` with `LINE 1:` and a caret.
- `deno bundle` with a deno.json mapping `react` and `react-dom` to a node_modules folder (React 19.2.0,
  installed from npm in a scratch folder) and `jsx: react-jsx`: 12 modules, about 190 KB; the page drawn in
  Chromium under the HTML cells' FRAME_POLICY (no request, the button's state changing on a click).
- tests/test_powerapps_notebook.py's real-Deno test (SWISSARMYBENCH_TEST_DENO, SWISSARMYBENCH_TEST_REACT):
  a SQL cell over a pasted table, `sab.table` seen by the next SQL cell (one DuckDB), a tagged template's
  parameter, Open as grid (every row), data.ts's row type from the kernel, an error, and a TSX preview with
  the real React: passed.
- Everything else with Deno stood in by tests/deno_fake.py (a real Jupyter kernel answering with Deno 2.9.6's
  recorded outputs; `deno bundle` writing a small script): the door, the agent's commands, Deno missing as
  the missing-package answer, the kernel's key-only route, Use in app, Dataverse sources (no connection: what
  to add; one whose address matches, case and a trailing slash aside: opened through it), and the browser
  (tests/e2e/test_codeapp_notebook.py, Chromium: the Code App page's Data notebook, a SQL and a TypeScript
  cell's tables, Open as grid, a TSX cell drawn in the design frame with its props, an error in the panel,
  Use in app).

NOT checked: a real environment or tenant (the Dataverse connection's own read was stood in; the match by the
environment's address comes from the recorded `pac env list`), real connectors (the bridge was not built:
docs/ideas.md says why), Deno on Windows and macOS (its install commands are the documented ones, not run),
`deno bundle` of a real Vite code app's node_modules (a scratch React 19.2.0 install stood in), React 18
projects, Monaco's TypeScript service in a cell across many cells (drawn, not measured), a notebook with
thousands of rows in a table result (the first 200 are drawn; the rest is Open as grid), Edge.

### Phase 2 addendum: the files shown, and pages (2026-11-17, branch ext-powerapps-2)

Relied on (read 2026-11-17): Microsoft Learn, **Connect your code app to data** (2026-10-02): generated
`src/generated/models/*Model.ts` and `services/*Service.ts`, imported as `./generated/services/...`; a
tabular source's methods shown as `create`, `update`, `delete`, `get`, `getall` (the recorded `pa` writes
`getAll`: the app reads the method's spelling from the service file); `pa app refresh data-source` writes them
again.

Checked here:
- **The template, for real:** `npx degit github:microsoft/PowerAppsCodeApps/templates/vite` (its tar snapshot
  failed through this network; degit fell back to a git clone) and `npm install` (181 packages: React 19.2,
  TypeScript ~5.9.3, Vite 7.2, `@microsoft/power-apps` ^1.2.5, `@microsoft/power-apps-vite`, ESLint 9 with
  react-hooks 7 and react-refresh). Its files are docs/ideas.md's survey table. Its `tsconfig.app.json`:
  strict, `verbatimModuleSyntax`, `erasableSyntaxOnly`, `noUnusedLocals`, `allowImportingTsExtensions`.
- **The starter files and a new page over a generated service** (a made-up `OrdersService` with `getAll`):
  the template's own `tsc -p tsconfig.app.json --noEmit` passes, and its own ESLint passes (two of its rules
  changed the first draft: `react-hooks/set-state-in-effect` and `react-refresh/only-export-components`).
  tests/test_powerapps_pages.py runs both where SWISSARMYBENCH_TEST_CODEAPP names such a folder (skipped with
  the reason otherwise). data.ts under the same settings: tests/test_powerapps_notebook_rules.py.
- A TSX preview bundled with the installed template's own React 19.2 packages (and its real tsconfig.json
  beside them): bundled. **Deno's bundler reads the code app's tsconfig.json** next to those packages: an
  empty one (the old recorded template's) failed the bundle; the stand-in now writes `{}`.
- The shown set, the hidden files on disk, Show all files, a hidden file read by its path, New page (its
  folder, its line in src/pages.ts, opened in the Workbench), the rule as typed in the editor (a squiggle on
  the import), and the agent's `powerapps_files`, `powerapps_pages`, `powerapps_scaffold`, `powerapps_lint`:
  through the door with the recorded `pa`, and in Chromium (tests/e2e/test_codeapp_page.py).

NOT checked: `pa app init` and `pa app add data-source` for real (no tenant: their files are the recorded
stand-in's), a real generated service's exact types (the page's row type is inferred from its read-all
method's result), `vite build` and Run live of the starter files, the starter files on Windows and macOS.

### Phase 2: data.ts without DuckDB (2026-11-17, branch ext-powerapps-2)

Relied on: Microsoft Learn, **How to: Configure Content Security Policy** for code apps (ms.date 2026-04-07):
the default directives (`script-src 'self' <platform>`, `worker-src 'none'`, `child-src 'none'`,
`connect-src 'none'`), enforced by default, changed only by an environment's administrator.

Checked here: data.ts with types, SOURCES (the tables each query read, by sqlglot, its CTEs left out) and a
constant, together with the starter files, built by the installed template's own tsc (its browser settings);
no DuckDB or `.wasm` import in any data.ts or starter file, and `no_duckdb` refusing one
(tests/test_powerapps_notebook_rules.py). The real Deno test's data.ts (typed results, SOURCES, a constant
from the kernel's rows) passed.

NOT checked: the policy in a running code app (no tenant), DuckDB-Wasm refused there (taken from the
documented directives; the enforcement date the coordinator gave, 2026-01-30, is not on the page).

## 0.0.18 from the release, installed as a user would (2026-11-17)

Checked on Linux in a container, each in its own uv tool folder and home:
- **A new install through the release's install.sh** (`--no-autostart --no-start`): the tool holds
  swissarmybench and swissarmybench-streamlit 0.0.18. The Extensions page says Streamlit installed, and Accounting
  and Power Apps available. The Project Explorer's types are Analysis and Streamlit app.
- **One-click Install of Power Apps:** the app restarted in about 10 seconds with Power Apps installed and
  Streamlit kept, and no failure note. The types then include Power Apps code app.
- **New project** (the page's call) for Analysis and for Streamlit app: each made a folder in
  `~/Swiss Army Bench Projects` with `.sab/`, README.md and .gitignore. The Streamlit one also has app.ipynb,
  data.ipynb, data.py, its .stapp.json and requirements.txt. The Project Explorer lists both, with their types and
  counts.
- **Update from 0.0.17** (the check, then Update to 0.0.18): the app came back on 0.0.18 with Streamlit installed
  (swissarmybench-streamlit 0.0.18 in the tool), and no failure note.

NOT checked: macOS and Windows desktops, the tray during these restarts, Edge, a code app against a real Power
Platform environment.

## The .sab conversion removed (2026-11-17, branch remove-sab-import)

Checked (Linux, Chromium in place of Edge): `swissarmybench open x.sab` (there or not, any case) prints
"x.sab: this version opens project folders only." and neither starts the app nor asks it anything; no route
has "sab" in its path, `/project/import-sab` answers 404/405, `/project/open` of a .sab file answers 400 and
writes nothing; no command names the import; `project_import` takes a project folder or a loose file; the
Start view has no Open a .sab file…; the package carries no `server/sab-file.*`. A project folder's `.sab/`
(save, open, copy, autosave, Keep its rows) and an older folder's `.sab/blades` adoption pass as before.
Whole suite: 4,028 passed, 49 skipped; three browser tests failed under load and pass alone
(test_table_cells_page's maker link, test_ui's system theme, test_workbench_page's error panel).

NOT checked: the installers' removal of an earlier .sab registration on a real Windows or Linux desktop
(unchanged code; only its comments changed).

## The blade screen (2026-11-17, branch blade-screen)

- Checked (tests/test_blade_screen.py): the header's table name written and read, the code's bytes after it
  untouched (CRLF kept, an unchanged save writes no byte); every answer of the live check (available, a table,
  a connection, another blade's table, a reserved word, not a valid name); the route answers the page and the
  agent alike; saving and New blade refuse a taken name with the same words; no PUT changes code, kind or
  variable (user or agent), /blades/fill saves nothing; New blade's file in the library's blades/; a file
  edited outside read again without a restart; Show its file 403 for the agent, stood in for the user; a
  connection with no listing query gets its starter's on read (nothing written); the Connections tree and the
  Data Explorer still list a connection's tables; the Data Explorer lists a blade's table by its name;
  `sab.blade` registers a function blade's result under the name (a stand-in IPython namespace).
- Agent (tests/test_cli.py): blades_new, blades_update (header only, a reserved name refused),
  blades_table_name_check; navigation without the catalog places (tests/test_navigation.py).
- Browser (tests/e2e/test_catalog_page.py, Chromium): no Catalog panel; New blade makes the file; the viewer
  read-only, line numbers, sized to the code; Show its file (stood in by a route); the table name turning from
  taken to available as it is typed; no "Add to the catalog" on a function blade; a connection's How its
  tables are listed, folded; a starter's Copy as your own. Screenshots light and dark.
- Not checked: Show its file on Windows and macOS (Explorer /select, open -R); a real Jupyter's %%sql over a
  registered blade table (the registration is checked, %%sql's reading of the namespace is the existing one).

## The system's file dialog and the page's picker (2026-11-17, branch file-dialogs)

Checked (Chromium; tests/test_file_dialogs.py, tests/e2e/test_file_picker_page.py):
- Each system's plan built and read, never opened: Tk's script (compiles; the values one JSON argument),
  PowerShell's (base64 UTF-16 -EncodedCommand; values in SAB_DIALOG; IFileOpenDialog, no FolderBrowserDialog),
  osascript's (arguments; activate; -128 a cancel), zenity's and kdialog's command lines (filters, save name,
  folder); each answer read (a path, a cancel, a failure). Which tool per system, none without a display or
  with the switch off.
- The runner with its child process stood in: a path, a cancel, the ten-minute limit a cancel, one dialog at a
  time (a second is `busy`), a start folder that is not there started at the nearest one, Tk asked about once.
- The door: 403 for the agent; `unavailable` with no display; the test server reports system dialogs off.
- Recent folders per kind (dialogs.json, eight each, paths only), shown as places for that kind only; New folder
  (made, 409 when there, refused names: `a/b`, `..`, `con`, `x:y`); hidden files on request.
- The page: chooseFile with the system dialog stood in (the browser's requests answered by the test): Open file
  opened the path as a grid, a cancel opened nothing, a second click said "A file dialog is already open",
  Settings' Projects folder took the folder; the page's own picker never appeared. `unavailable` fell back to
  the page's picker and did not ask again. Every chooseFile caller imports it from fileChooser.ts and no other
  module lists folders (a source test).
- The page's own picker: places (Home, Desktop, Documents, Downloads, Projects from a made-up home), a place,
  a double-click into a folder, the breadcrumb (a part clicked), Filter, Hidden files, Backspace up, arrows and
  Enter into a folder and onto a file (it opened as a grid), Recent per kind (shown for Open file, not for Open
  project), New folder, Escape. Light, dark and phone width (no side scroll); screenshots looked at.
- **A real dialog on Linux:** uv's own Python (python-build-standalone 3.12.13, Tk 9.0.3) under Xvfb, opened by
  DialogRunner: the Tk save dialog in the start folder with the name suggested and the .csv filter; Return gave
  the path, Escape a cancel, a second request while it was open `busy` (screenshot looked at).

Not checked: a real dialog on Windows (Tk's IFileDialog, the PowerShell fallback, the C# folder picker
compiled by Add-Type, coming to the front past Windows' foreground lock) or on macOS (osascript's panels,
activate); zenity and kdialog on a real Linux desktop (not installed here). Debian's own Python has no Tk
without python3-tk; uv's managed Python has it.

## The Data page (2026-11-17, branch data-page)

Checked (Chromium, made-up SQLite connections; tests/test_explorer.py, tests/e2e/test_data_page.py):
- The rail's Data sits after Variables (the rail test's order and its keys); a click lands on the page
  (open=data), the area is marked, the search has the focus; Back takes the page away, Forward brings it.
- With nothing typed: each connection with its status (2 tables; Not loaded for one whose catalog was taken
  away, a look never loading it), its schema, its tables, a table's columns and types when it opens; the open
  tables with their columns and a structure with its paths (HTTP); Load loads the catalog in the background
  and the status follows (1 table). The filters (a kind, a connection) narrow the browse (HTTP).
- The detail side: columns with types and nulls (NOT NULL said No), From, the SQL name, the %%sql and Python
  code. Copy SQL name puts `[Orchard…].orders` on the clipboard; Open as grid opens its tab.
- A search narrows the tree: the matching tables under their connection and schema, the matched columns
  (CustomerKey, customer_id) under their tables; a connection with no match is not drawn.
- With a Workbench window open: Insert shows and goes into its selected cell; Query in a notebook adds a
  %%sql cell; a column's drag carries `{"sql": "CustomerKey", "python": "\"CustomerKey\""}`, and a table's
  drag dropped into a cell there writes its SELECT. Without one, Insert is not shown.
- The keyboard: Down from the search into the tree, Right opens, Down to a table, Enter opens it as a grid;
  / focuses the search.
- The pane's Pop out opens `/workspace?open=data&q=orders` in a window of its own with the search and closes
  the pane; the agent's explorer.popOut too. `/workbench?panel=explorer` redirects there (302, the #token
  kept). Ctrl+K's Open the Data page takes the dialog's search to the page.
- The agent: explorer_browse and explorer_table answer what the page shows (names only, never a value);
  app_navigate knows data.
- Screenshots, light and dark (2x): the page fills the window right of the rail, the tree and the detail
  side side by side, no strip under them.
- The whole suite with Chromium: 4044 passed, 49 skipped, 3 failed under load. Alone:
  test_data_page's Workbench test passes (twice); test_sandbox_pages' first test clicked the rail while the
  Apps icon appeared and moved the icons under it (fixed in the test: it waits for Apps); test_table_cells_page's
  maker test fails one run in two on the base (601944d) too.

NOT checked: a Power BI workspace and a SQL Server connection on the page (Import its relationships is
offered by rule, unit-tested; the request is the Connections page's own), Edge, a real drag between two
windows (Playwright carries the drag's data across instead), narrow windows (the detail goes under the tree
by a media rule, not looked at).

## 0.0.19 from the release (2026-11-17)

Installed through the release's install.sh into its own uv tool folder and home: swissarmybench and
swissarmybench-streamlit 0.0.19. `swissarmybench open old.sab` says "this version opens project folders only."
(exit 1). `/explorer/browse` answers; `/blades/table-name` says "available" for a free name and "not a valid
name: select is a word DuckDB's SQL keeps for itself"; `/project/import-sab` is 404. In Chromium: the rail has Data
after Variables; no "Open a .sab file…"; New project's Choose another folder… opens on the nearest existing
folder with its note; the rail's Data opens `open=data`; the Blades page has no Catalog panel.

NOT checked: Windows and macOS desktops, Edge.

## Relationship sets, the Relationships window's management, the project's ERD (2026-11-17, branch relationship-sets)

- The rename: a set saved writes `relationship-sets/<name>.relationships.json` in the library, marked
  `"swissarmybench": "relationship-set"`; saved again with nothing but the time changed, no byte is written. Old
  `.tang` files read from a shared folder, an older pack's `tangs/`, an import and `{"tang": name}` for a check;
  `POST /relationships/tangs` and `GET /relationships/tang` answer; `relationships_save_tang`, `_export_tang`,
  `_import_tang` run their `_set` commands and are not listed. The library's `tangs/` moves once at start (a
  broken file stays only in `backup/before-relationship-sets-<date>/tangs`), said once without the old word.
- The window, in Chromium at 700px and 1600px wide with 40 made-up foreign keys of long names: no sideways
  scroll (scrollWidth <= clientWidth for the dialog, its body, the table's box and the footer; the dialog inside
  the viewport), the Run column shown, names cut in the middle with their tooltip. Select all, Delete selected
  (40), the toast's Undo (40 back), the filter (10 of 40), a shift-click range (4 selected), Run off (4),
  select all of the filtered rows only (10), Kind and Run in place, sort by From descending, group by From
  table, a row's menu Delete. A saved set renamed and deleted from its menu (its files on disk checked).
- HTTP: delete, update and undo of the joins in use (40, then one step back), kind refused when not one of the
  four, the agent's the same; rename (the old file gone, a taken name refused), export a saved set, a pack's set
  refused (403); the agent's delete of a saved set waits for Allow (403 on decline).
- A deleted connection (a made-up CSV connection, FI-Atlas): `DELETE /blades/FI-Atlas` answers
  `relationships_removed: 40`, one join of other tables stays, a saved set keeps its 41; in the browser the
  Connections page's Remove shows "Removed 40 relationships that came from FI-Atlas.".
- The project's ERD: with a project open, the scope's used tables are the open ones, the project's and those its
  notebook (cell sources) and script name; 37 of 40 made-up FI-Atlas tables hidden and said in one sentence; a
  join drawn only with both ends used; `scope=all` draws everything; no project: everything, no switch. In
  Chromium: the switch, the count, cost_center not drawn until All tables, the window's In use now 1 row by
  default and 38 on All tables.
- Checks: ruff check, ruff format --check, mypy, npm run typecheck and npm run build clean. The whole suite with
  Chromium: 4094 passed, 49 skipped, 1 failed (test_catalog_page's packs test still clicked "Add blades and
  tangs": fixed, passes alone).

NOT checked: Edge, Windows paths, a real SQL Server's or Power BI dataset's imported relationships (made-up
models with their recorded sources stand in), a library clone pointed at in Settings that still has `tangs/`
(read by rule, not looked at in a browser), dark theme screenshots.


## Drivers that run anywhere, and "Only works on your machine" (2026-11-17, branch drivers)

Really ran, against a real **SQL Server 2022** (mcr.microsoft.com/mssql/server:2022-latest, CU28, Developer
Edition) in a container on 127.0.0.1:14333, with **mssql-python 1.18.0** and **python-tds 1.17.1** pip-installed
into a scratch environment (no ODBC driver installed by hand; mssql-python's wheel carries its own):
- tests/test_sql_server_real.py (SWISSARMYBENCH_SQLSERVER_TEST set): 6 passed. The SqlServer object signs in
  (SQL login), says its version and collation; every type read into Arrow as the golden cases say (decimal and
  money exact, tinyint as uint8, datetime2 as timestamp[us], datetimeoffset as the same instant in UTC, time as
  time64[us], uniqueidentifier, xml, nvarchar(max), geography by .ToString(), sql_variant by CAST); a query with a
  sql_variant column outside a plain read falls back from mssql-python's Arrow (it refuses type -150) to the
  rows; a wrong password, an untrusted (self-signed) certificate and a missing table are said in plain words,
  the password never in them; an interrupt (Ctrl+C) stops `WAITFOR DELAY '00:00:30'` on the server in 1.5 s
  and the connection reads again; the Write starter's upsert (dry run: "update 1 row, insert 2 rows", then the
  write) through mssql-python, Unicode, NULLs, datetime2's microseconds, a datetimeoffset and a
  uniqueidentifier as their text, read back exact; Dataverse's SQL cursor (its marks, its refusal words) on
  python-tds against the same server's TDS, signed in with a SQL login.
- mssql-python's own words, as the error table now reads them: "Driver Error: Invalid authorization
  specification; DDBC Error: [Microsoft][SQL Server]Login failed for user 'sa'." (a wrong database says the same
  login failed), "...SSL Provider: [error:0A000086:SSL routines::certificate verify failed:self-signed
  certificate]", "...TCP Provider: Error code 0x2AF9" (no such host), "Base table or view not found; ... Invalid
  object name 'nope'.", "Operation canceled". No native number in any of them.
- Speed, 264,900 rows (int, nvarchar, decimal(18,2), datetime): mssql-python's Arrow batches 0.23 s, the rows
  then Arrow 0.92 s (best of three). executemany of 20,000 rows into a #temp table: 0.3 s.
- Found against the real server and fixed: python-tds %-formats a statement whenever it is given a parameters
  tuple, an empty one too (`100 % 7` failed): a statement with no parameters is now sent alone.
- Encrypt=strict against the container's self-signed certificate: refused (a dropped connection, 0x2746), as
  TDS 8 wants a trusted certificate; not checked against a server with one.

Stood in for (no real service reached):
- Azure SQL, Azure SQL serverless resume, Microsoft Entra tokens (as you, managed identity, an app
  registration, a certificate), ActiveDirectoryDefault and ActiveDirectoryPassword, Windows integrated sign-in,
  a Fabric/OneLake SQL endpoint, a Dataverse TDS endpoint and its Entra federated authentication, an Azure
  Function App and a hosted Streamlit app: none was reached. The unit tests run the connection code against a
  stand-in mssql_python at its seam (errors shaped as the real one's) and a stand-in pytds at its seam
  (tests/dataverse_tds_standin.py, the real Dataverse code signing in at the Web API stand-in).
- "Runs on a Function App" is a rule read from the code (domain/portability.py), not a run on one.

Checks: the unit tests for the new code (tests/test_sql_server.py, test_portability.py, test_dataverse.py,
test_starters_write.py on both drivers, test_connection_kinds.py, test_agent_streamlit_export.py); browser tests
in Chromium (tests/e2e/test_sql_server_page.py: the form's portable first way and Windows sign-in's amber
note, the keyring's note, no Driver option; an ODBC connection's card and page; an older connection's Update to
the new driver; the script export asking before it writes; test_dataverse_page.py, test_lakes_page.py,
test_trino_keystore_page.py with the new orders and a password from a variable first). Screenshots in
scratchpad b/shots-drivers.

NOT checked: Edge, Windows and macOS desktops, the Streamlit export's confirm in the page (its check is tested
over HTTP), a real Azure anything.

## The project's outline (2026-11-17, branch project-outline)

Checked (Chromium on Linux; tests/test_project_outline.py, tests/e2e/test_project_outline_page.py):
- A made-up project (four of examples/sample_store.py's tables as CSV files inside it with their true
  relationships, a made-up SQLite connection with a keyring password, a data notebook with named cells and a
  DuckDB SQL cell naming `[Shop].suppliers`, an app notebook, a script with run settings, a Streamlit canvas)
  outlines byte-for-byte as tests/golden/project_outline/store_analysis.md; a new project as new_project.md.
- No planted row value, secret, token or path outside the project is in it; a read writes nothing; Export
  writes ARCHITECTURE.md, and a second Export changes no byte (written false, the same mtime); the file is not in
  its own layout, so the next outline is the same.
- Every section says "None." when it has nothing (the eight, in order); a hostile name stays in code
  formatting and the title is escaped; long lists fold under <details>; an inactive relationship is dotted.
- The two seams replaced whole change the tables and the portability words (and Open issues).
- The agent's `project_outline` returns the markdown, and with write writes the same bytes.
- In the browser: Export outline in the project's group writes ARCHITECTURE.md, its toast's Download saves the
  same bytes; a second click says "is up to date"; the Workbench's `project.outline` (through workbench_window)
  writes it too; the app's Mermaid (lazy/diagram.ts) draws both diagrams of the page's outline and of the golden
  store outline (an SVG each, no error).

NOT checked: Windows and macOS, Edge; GitHub's own rendering of the Mermaid blocks and <details>; a project with
APIs or saved dashboards end to end (their lines are covered by the rules only).

## The meta store: the shared catalog, Set up from the meta store, local and shared projects (2026-11-18, branch shared-catalog)

Really ran (this container, Linux, Chromium for the browser tests):
- tests/test_shared_catalog.py: the file is the golden text byte for byte (tests/golden/shared_catalog/
  warehouse.json) and reads back the same; the same events in another order make the same bytes; a planted row
  value, a relationship's note and evidence (numbers from the data) never reach it; a listing marks gone since
  that day, back to present when listed again, the date unchanged while still gone, removed after 30 days (a
  given date, no clock); a merge's markers and broken JSON said with the file's name; two people's independent
  additions merged by the real `git merge-file` (git 2.x here, in the test only) with no conflict and exactly
  the file either would write with both.
- tests/test_shared_catalog_http.py: a real SQLite connection (a made-up file) saved, Refreshed through its child
  process: its file written, the password (in the keyring) and a row's value absent; relationships set by the
  agent added with keys marked, deleted by the user taken out; a dropped table gone after the next Refresh; a
  Refresh that fails (the file moved) changes no byte; deleting the connection removes its file. A teammate's
  file dropped into catalog/ is picked up by Refresh and told over the page's websocket ("1 connection
  changed"), found by Explorer search and browse, drawn by the ERD's All tables, named in context.md. A file with
  conflict markers is reported and left as it was through the next Refresh, and written again once fixed. A
  project's open table and a table its script names are in `used_by`; taken out when the script stops naming it.
- tests/test_library_setup.py: a teammate's meta store (two key vaults, one whose names() fails as Azure's does
  when signed out; keyring and local variables; a connection whose password is in the teammate's keyring) cloned
  to a second computer (a separate state folder and keyring): the checklist's items and words over HTTP, 4 then 1
  things to set up as each value is typed; Move to a vault maps the teammate's keyring password to the readable
  vault (the vault's mapping and the connection's code checked).
- tests/test_shared_projects.py: projects.json's older key read as the local folder and written as
  local_folder; both folders scanned; Local and Shared marks and the filter; New project in Shared (refused
  until the folder is set); Share without .sab/data or .git, the original kept, opened; Make a local copy with
  copied_from (kept through a save, shown on the card), a name taken answered 409 with a free one; a shared
  project whose connection only works here said once; the checklist lists a shared project whose connection
  needs a password here.
- tests/e2e/test_meta_store_page.py (Chromium): Settings' Meta store folder (its line, the catalog's counts, the
  checklist: 2 things, the locked vault's Sign in to Azure, SHOP_TOKEN typed once then 1 thing), the Local and
  Shared projects folders; the Data page's "From the shared catalog" section and a teammate's table's detail;
  the Project Explorer's marks and filter, New project's Where, Make a local copy opened and its card's
  "Copied from". Screenshots looked at.
- ruff check, ruff format --check, mypy, npm run typecheck and npm run build: clean.
- The whole suite with Chromium: 4286 passed, 50 skipped, 3 failed (34 min, another agent's suite on the same
  machine). test_file_picker_page's system-dialog test asked for "The projects folder" (now "The local projects
  folder": fixed); its page-picker test (net::ERR_ABORTED on goto) and test_ui's repush test pass alone (5 passed).

Stood in for, or not checked:
- A real Azure Key Vault sign-in: the locked vault is made-up code that raises Azure's words. A real teammate's
  push and pull: a copied folder and a file written into catalog/ stand in for `git pull`.
- The 3-second watch loop itself is not timed in a test (Refresh, the same code, is); Windows paths only by the
  rules' test (C:\\Team vs c:/team).

## The GitHub Copilot extension (2026-11-18, branch ext-copilot)

Checked here:
- **The real Copilot Language Server, without a sign-in:** `npm install @github/copilot-language-server@1.572.0`
  from the registry into a scratch folder (7 packages: the server, its linux-x64 platform packages);
  `node dist/language-server.js --version` printed `1.572.0` (Node 22.23.4). Then the extension's own client code
  (domain/lsp.py's framing and messages) over `--stdio`, with a scratch HOME: `initialize` answered serverInfo
  "GitHub Copilot Language Server" 1.572.0 and capabilities executeCommandProvider, inlineCompletionProvider,
  notebookDocumentSync (notebook "*"), textDocumentSync (openClose, change 2: incremental), workspace; after
  `initialized` it asked `workspace/configuration` (answered telemetry off) and sent `didChangeStatus` "You are
  not signed into GitHub."; `checkStatus` {localChecksOnly} answered `{"status": "NotSignedIn"}`; `shutdown`
  answered null and `exit` ended it with code 0. Its package is MIT; its README points at GitHub Copilot's terms.
- Everything else against tests/copilot_standin.py (a stdio LSP server written from the README's messages, sharing
  no code with the client): tests/test_copilot_rules.py (framing in pieces and together, Content-Type read past,
  bad headers refused, UTF-16 positions, incremental changes, the documents mirrored as text documents and as a
  notebook with structure and text changes, the oldest closed, items read with their commands kept server-side,
  account and device-flow answers, Node.js's version and missing answer, the pinned install's command line) and
  tests/test_copilot.py (off: a 404 naming the extension and no provider in the modes; on: the provider in every
  mode and the panel route in the listing; before sign-in nothing is started; the device flow and the
  showDocument answer; sign-in/out the user's (403 for the agent, no code in the agent's panel); no plan said;
  a script opened, changed and completed with didFocus first; a notebook cell with its other code cells; shown,
  partial and accepted told back; a completion cancelled by $/cancelRequest; Off stops the server and sends
  nothing; a private project closes what was open and sends no didOpen or completion, and comes back when not
  private; the agent's private switch waits for Allow; the install's npm command line into the state folder and
  the agent's install waiting for Allow (a fake npm); Node.js missing is the missing-tool answer; no code, token,
  the server's log or a document's text in any answer, copilot.json or the audit log; the agent's three commands;
  the server ended with shutdown and exit when the app stops).
- In Chromium (tests/e2e/test_copilot_page.py, the stand-in behind a real server): ghost text in a notebook cell,
  Tab takes it and the accept command reaches the server; a SQL cell's ghost text, Esc lets it go; a script's
  two-line ghost text, Tab takes it; the status bar's "Completions: GitHub Copilot · on/off" and its click (nothing
  asked while off); the project group's Private switch writes `.sab/project.json` and the status bar says private
  and nothing is sent; the Extensions card's Sign in, the code, Open github.com/login/device (routed in the test:
  nothing leaves), signed in, On; Settings' panel and its On switch. Screenshots in scratchpad b/shots-copilot.

NOT checked: a real completion, sign-in or sign-out with the real server (needs a GitHub Copilot plan), Monaco's
Alt+] / Alt+[ cycling and Ctrl+Right partial accept in the browser (Monaco's own keys; the partial report is
tested over HTTP), Windows and macOS, Edge, the extension's wheel built by build.py and installed from a release.


## GitHub sync and the Source Control page, the Git extension (2026-11-18, branch github-sync)

Checked here, against **GitHub stood in for on 127.0.0.1** (`tests/github_standin.py`: the device flow, the user,
repositories, refs, commits (history and one commit's files), trees, blobs, compare, branches and the Git Data
API's writes over in-memory repositories of made-up files). **Real GitHub (api.github.com, github.com/login) was
not reached**: the request shapes follow GitHub's REST v3 documentation; the first real sign-in, clone and push are
for the owner to try.

- `tests/test_scm_rules.py` (8): git's blob SHA (`hello\n` = ce013625...), repository, branch and path checks,
  .gitignore patterns at every level and the app's own exclusions, diff3 (clean, the same change, one side, a
  conflict, inserts at one place, no base, not text), a pull's plan, secrets found, the words, VS Code's groups.
- `tests/test_scm.py` (8): a token's sign-in (refused one, the agent's 403, the keyring only, never in an answer or
  any file of the state folder), the device flow; clone (not signed in, not empty, the folder then the meta store's,
  its connection the library's), the status words, pull (taken, merged, deleted, a conflict with .theirs, the blades
  read again), push (behind refused, conflict refused, a secret refused and named, large files left out,
  `.gitignore` and `local/` never sent, the commit's message); connect (nothing written, then a conflict); the
  agent's clone, pull and push only on Allow; the Source Control routes (groups, stage, unstage, diff sides and
  unified text, commit of the staged file, discard on Allow, history order and parents, refs, a commit's files and
  diff, create a branch on GitHub, checkout refused when dirty, then checked out, sync); a shared project's scoped
  push, the footer's mark (↑1, ↓1 behind, none), the rail's area as data; off: the door names the extension.
- `tests/e2e/test_scm_page.py` (4, Chromium): the rail icon absent with the extension off; Settings' GitHub section
  (sign in with a token, Clone a repository… through the quick picks and the page's folder picker, Up to date);
  the Source Control page (M and U, the count, the placeholder, Stage Changes on hover, Staged Changes, Monaco's diff
  editor, F7, Inline View, Ctrl+Enter commits, the graph's four rows, the HEAD ring, two labels, a commit's file
  and its diff, Discard Changes' question and the file gone); the footer's mark appearing after a save and going
  after Commit; a shared card's Pull leaving a conflict ("Conflicts: 1"), the page's Merge Changes with `!` and
  the Yours ↔ Theirs diff; smart commit's question; the page in Dark Modern.
- Not checked: real GitHub; Sign in with GitHub against github.com (no client id yet); Windows' and macOS'
  keyrings; a side-by-side comparison with VS Code (none runs here: the values come from VS Code's source).
- The whole suite with Chromium (2026-11-18): 4321 passed, 50 skipped, 5 failed and 1 error under load. Alone: `test_extensions_page` failed for the catalog's fourth card (fixed: the test now counts four, Git among the available ones); `test_show_the_math`, `test_starters_page`'s DAX snippet, `test_streamlit_page`'s agent export, `test_workbench_page`'s export through the file chooser and its deleted-cell test passed when run alone (the export one twice): load-dependent, not this branch's.

## 0.0.20 checked from the release (2026-11-18)

Installed as a user would, in an empty home folder: `install.sh` from the v0.0.20 release (`--no-autostart
--no-start`), then `swissarmybench start --background`. Release run 54: build and tests, the installers on Linux,
macOS and Windows, the GitHub release (the base, five extension wheels, the installers, the .vsix) and PyPI all passed.
- The server reports 0.0.20. The Extensions list: Streamlit installed (preinstalled), Accounting, Power Apps, GitHub
  Copilot and Git available, all 0.0.20.
- One-click Install of Git, then of GitHub Copilot, each through the helper and the restart: both installed.
- With Git on: `/app/areas` lists Source Control; the rail shows its icon; the page opens with the token steps;
  Sign in with GitHub is disabled with its reason (no OAuth client id yet). No page errors.
- With Copilot on: its status answers (installed; the language server not yet installed; not signed in).
- `/dialogs`: no system dialog here (no display), said plainly. Set up from the meta store: "Ready: 0 connections".
  The shared catalog answers (empty). New project made; a pushed table and a "+" query table built; Export outline
  wrote ARCHITECTURE.md into the project.
- The footer: the same on the home page (version, rows, zoom, Beta).
- Not checked here: a real GitHub sign-in, clone or push; a real Copilot sign-in or suggestion; Windows and macOS
  by hand. A small fix for later: the disabled Sign in with GitHub button is drawn in full colour.

## An extension's Install with the tray running (2026-11-18)

The owner's Windows: Install of Git and of GitHub Copilot failed with update_failed.json saying "The app did not
stop." The helper waited for the server and the tray; the tray asks the server only every 5 s and the server stops
0.5 s after handing over, so the tray never heard and stayed, and the helper gave up after 60 s. (Not seen on
the release check here: no tray ran.) Fixed: the helper waits for the server, then gives the tray 6 s to quit and
ends it itself (TerminateProcess on Windows, SIGTERM elsewhere); the app started again brings its own tray; and the
tray's answer now says "updating" during an extension's Install or Remove too. Checked here for real: a build of
the fix installed as a uv tool, started without a tray, a stand-in tray process (that never quits) written into
tray.json, then Install Accounting: the helper ended the stand-in after about 9 s and Accounting installed, no
failure note. Unit tests: the tray ended and the install going on, a tray that cannot be ended said. Not checked
by hand on Windows: the fix reaches the owner only in the next version (the helper is a copy of the version
running).

## 0.0.21 checked from the release (2026-11-18)

Installed with the v0.0.21 release's install.sh into an empty home folder; the server reports 0.0.21. Started
without a tray, a stand-in tray process that never quits written into tray.json (the owner's Windows case), then
Install Git from the Extensions route: the helper ended the stand-in after about 9 s, Git installed at 0.0.21, no
update_failed.json. Release run: build and tests, the installers on Linux, macOS and Windows, the release and PyPI.
Not checked here: a real tray on Windows (the owner's machine).

## The desktop app on PySide6, the server's life, the tray gone (2026-11-18, branch ext-desktop)

Checked here (Linux container, Python 3.12, PySide6 6.12.0 with PySide6-WebEngine 6.12.0.140 installed into the
worktree's environment; libEGL, NSS and the xcb libraries added with apt for Qt WebEngine to load):
- **The app really run** (tests/desktop_drive.py, under `QT_QPA_PLATFORM=offscreen` in the suite and on Xvfb with
  xcb by hand; Chromium's sandbox off as root): the app started the server itself and showed the home page with
  the token (the page traded it for its cookie; its title never the address); a pasted made-up table drew;
  `window.open('/workbench', name)` made a second window, the same name again no third, and the Workbench's
  `window.open('', 'sab-home').focus()` raised the home window; an Export's blob download asked the Save dialog
  (stood in) with "orders.csv" and the CSV landed there, the status line saying "Saved orders.csv" with Show in
  folder; `window.print()` asked "Print to PDF" with the page's title and wrote an 85 KB PDF; a link with
  target=_blank, a window.open with noopener and `location.href` to https://example.com each went to the
  system's browser (stood in) and nothing loaded inside (the empty window closed); the developer tools opened in
  a window of their own; the channel's status listed the windows (no token) and opened /catalog; another key was
  refused; the Workbench closed at 40,50 900x640 reopened there; Open in browser handed the browser the page with
  the token; every window closed (each page asked first): the app told the server and the server stopped.
- **The clipboard** (writeText then readText, "North,120.50") works on Xvfb once the window has the system's
  focus; off screen no window ever has it ("Document is not focused"), so the suite accepts either there.
- **The app as a process** (`python -m swissarmybench.server app`): one at a time, a second start handed its page
  and ended, the server's "open a page" went to it, and once it ended the server stopped by itself after its
  grace (no request asked it anything meanwhile).
- **The server's life** with a fake clock: the start grace, the 30 s grace, a reload within it, an agent's
  request holding it ten minutes, VS Code connected and a request under way busy, the app's close at once, an open
  project saved first (Autosave on) or held (off). And for real: a server started with a 2 s grace stayed while a
  page socket was open and stopped after it closed.
- **The tray's leftovers removed:** an XDG autostart entry with the tray's command, a LaunchAgent plist and a
  Startup shortcut (made-up files under a temporary home), a stand-in tray process (ended), tray.json; the page's
  notice said once; someone else's autostart entry left alone.
- **install.sh** with a made-up uv: the .desktop entry and SVG icon written, the old entry removed, nothing opened
  on a build machine, `--uninstall` removed both and ran `uv tool uninstall`; `--no-autostart` still taken.
- **Sizes** measured with uv into fresh environments: `swissarmybench[server]==0.0.21` 499 MB; with the three Qt
  wheels and without pystray and Pillow 1,146 MB (PySide6 667 MB).
- Screenshots at device scale 2 on Xvfb: the home window with a made-up table, the download's status line, the
  Workbench window, the blades window.

Not checked here (only a machine of that kind can): **Windows** (install.ps1's Start menu shortcut to
pythonw.exe, its .ico in the shortcut, the window icons, the first start's time, the installed size, Chromium's
sandbox as a normal user, the native Save dialog, the old Startup shortcut and tray removed on a real upgrade);
**macOS** (the ~/Applications bundle opening, Gatekeeper's word on an unsigned bundle, the Dock icon, the old
LaunchAgent); a Linux desktop with a window manager (activation, the menu entry's icon); dragging a cell between
two windows (needs real mouse input: not driven off screen); the release workflow's three install jobs; Windows on
ARM (no Qt WebEngine wheel: the browser should open; not tried).

## 0.0.22 checked from the release, and 0.0.23's fix (2026-11-18)

- **0.0.22 from its GitHub release** (install.sh into a temporary home, Xvfb): 1.2 GB, the `.desktop` launcher,
  the app opened (server.json and desktop.json written), a stand-in tray ended and tray.json removed; a made-up
  autostart entry that was not the tray's own command left alone.
- **Found:** the server stayed up 10 minutes after the app closed. Two causes: the desktop app's `/health` checks,
  and the pages' own fetches, which carry the token as a Bearer header (web/src/api.ts) and so counted as a
  client's. Fixed: `/health` and `/lifecycle` are not work, and a request the browser marks
  `Sec-Fetch-Site: same-origin` is a page's, not a client's (domain/lifecycle.py `from_a_page`; the guard).
- **Checked for real** with a wheel of the fix: the app open, its home page loaded, `/lifecycle` said "a window is
  open" and no client; the app ended, the server stopped 34 s later (the 30 s grace).
- **0.0.23 from its GitHub release** (install.sh and the wheel downloaded, a temporary home, Xvfb): version 0.0.23;
  the app open, `/lifecycle` said "a window is open" and no client; one request with the token and no browser
  mark counted as a client; the app ended, the server still up 60 s later (held by that request) and stopped
  595 s after the close, 10 minutes after the request.

## The guided tour (2026-11-18, branch tour-guided)

- **In the browser (tests/e2e/test_tour.py, Chromium 1440x900):** opened from the Start page; with the user's own
  `tour_orders` open, the tour's tables arrive as `tour_orders_2` and `tour_customers` tabs; Connections opens its
  page and the spotlight's box is the Add connection button's (6 px round it); Grid: the tour's orders in front, its
  tab lit; Steps reads "1 step"; Compare puts the two side by side (data-split on) and lights the Compare row; Left
  goes back to Analyze with the split gone; ERD shows the ERD view; Notebooks lights the rail icon with the ERD left
  in place; Agent scrolls Settings to its Claude section and lights it. Escape mid-tour: the Start view again, the
  two tour tables closed on the server and as tabs, the user's `tour_orders` still open. A second run to the end:
  the game's five rounds, Start, the same clean-up.
- **By hand (screenshots, device scale 2):** every card walked at 1440x900; the card sits beside a rail icon,
  under a page's button, above Settings' Claude section.
- **Not checked:** a narrow window (420px) with the guided moves; the desktop app (Qt WebEngine) run; a user who had
  two tables side by side when the tour started gets one side replaced by the tour's while it runs (the address
  comes back, the split does not).
- **Sign in with GitHub (2026-11-18):** the owner registered the app (device flow on); its public client id is
  built in (extensions/git extension.py CLIENT_ID). The tests still run token-only unless they name one.

## The mark on the rail, and Projects as a page of its own (2026-11-18, branch projects-page)

- **Unit:** tests/test_navigation.py (`projects` the rail's first area from every window; `start` the old name for
  it; the refusal lists `home, projects, connections, …`); tests/test_snapshots.py (area `projects`, and `start`
  asking the page for it).
- **In the browser (Chromium):** test_navigation_page.py (the mark is the rail's first item on the grid page, the
  blades page and the Workbench and not in their top rows; a click shows Projects over the page under it, the point
  at the page's middle is the Projects page's, the address `…&open=projects`, the title "Projects", the mark
  current; Back takes it away; Alt+Home from Visualizations; `/workspace?view=start` lands on it, replaced; the
  Workbench's mark, reached by the rail's Home key, brings the same home window forward showing Projects, and with
  the home window closed opens one at `?open=projects`; app_navigate `home`, `projects`, `start`, `back`, `grids`);
  test_rail_page.py (the order with the mark first, its red square, icons 24 px, items 34 to 46 px high, the arrow
  keys and Home reach the mark, its tip says Alt+Home); test_sab_projects.py (the app starts on Projects with no
  table and no project; a card opens the project's grids and Projects goes; the mark brings it back with the open
  card marked; the grid page with no table and no project is the Grids landing with "No project is open." and its
  Projects link; screenshots light and dark); test_tour.py (from Projects, its new Projects card lights the mark,
  Escape and the game's end come back to Projects); the meta store, Source Control and file picker pages through
  `?open=projects`.
- **Found on the way:** a rail click made while the home page was still starting (Settings) was covered by the
  Projects page opened a moment later; the start now opens Projects only while the grids' landing is still what is
  shown. The landing is drawn while hidden too, so a fixed table's row never stays behind it (the swap test).
- **Whole suite (Chromium):** 4417 passed, 46 skipped, 9 failed on the first run. Fixed after it: test_icons (the
  rail's icon name), the keyboard test (the mark left the tab bar's Tab stops), the connection swap (the stale
  landing row). Failed under load and passed alone: test_copilot_page's private project, test_streamlit_page (four,
  one other when run as a file), test_table_cells_page's maker that stays put.
- **Not checked:** the desktop app (Qt WebEngine) run by hand; a narrow window (420 px) with the smaller rail.
