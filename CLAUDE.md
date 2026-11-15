# CLAUDE.md — Swiss Army Bench

A local Python server (Starlette + uvicorn + in-memory DuckDB) that shows tabular data in live
AG Grid pages, with steps, profiling, SQL, export, verified code generation, charts and an MCP
door for agents. It runs only on the user's machine. This repository is the whole product: the Python
package at the root, its page in `web/`, and the optional VS Code extension in `vscode-extension/`.

One package, two installs (`python build.py` builds the wheel, page inside): the plain wheel is a
standard-library-only push client for any Python environment; the `[server]` extra is the grid server,
installed once per machine as a uv tool (`uv tool install "<wheel>[server]"`), started by `swissarmybench`.

- **Renamed (the owner, 2026-11-15):** SwissArmyGrid is now Swiss Army Bench: `swissarmybench`, alias `sab`.
  Write only the new names; the old ones are read for one release (`renamed.py`, README "Renamed from
  SwissArmyGrid"). The GitHub repository is DylanCodyBrown/SwissArmyBench (renamed; the old address redirects).
- **What SAB is for:** Python-to-DuckDB work on one screen instead of three. SAB brings Python's
  power (analysis, fast data); **DuckDB SQL does the transforming**. Generated transformations are
  DuckDB SQL over the user's own table, never a pandas translation.
- **Where it is going:** [Plans/standalone-workspaces.plan.md](Plans/standalone-workspaces.plan.md):
  a one-command installer that sets up everything; one local server with separate workspaces
  (`sab.create_workspace()`); code goes in the **Workbench** (our own notebooks and scripts on an
  IPython kernel, [Plans/workbench-and-connections.plan.md](Plans/workbench-and-connections.plan.md)),
  Jupyter or Python in the terminal (marimo was built in, then stripped on the owner's call, 2026-11).
  **Rule: code always opens in its own browser window, never in the grid page** (the Workbench tab
  opens it), so it can sit on another screen; saved workspaces; a tray icon; and a Power BI style
  relationships view with autodetection. VS Code is optional.
- **The golden rule (the owner, 2026-11-14): every single thing the user can do, the agent can do
  too, through the MCP, with no prompts.** A new user action gets its command in `cli/commands.py`
  (so an MCP tool) in the same change. The only exceptions: the agent cannot answer its own approval
  requests, and no answer the app gives it holds a password's value (`/blades/{name}/python` stays
  refused). Code the agent runs in a Workbench kernel can read what that Python can, which the owner
  accepted; `tests/test_cli.py` NOT_COMMANDS lists the routes without a command and why.
- **The original plan:** [Plans/swissarmybench-build-plan.md](Plans/swissarmybench-build-plan.md).
  Follow its section 0 working agreements: typed Python, tests first for semantics, ask before
  adding a dependency the plan doesn't list. Milestone 9 (the agent running code) was the owner's
  call: made on 2026-11-14 by the golden rule (the agent runs code in Workbench kernels).
- **What exists:** milestones M0-M8, blades and the catalog, connections (database and file blades,
  added with a form; a Power BI workspace, its datasets read with DAX, a dataset's relationships
  imported; a connection made of the user's own Python, its environment variables mapped), the SQL
  cell (`%%sql <connection>`), the DAX cell (`%%dax <connection>/<dataset>`, `sab.dax`), the
  Workbench (notebooks, scripts,
  completion, per-notebook environments), every table's read-only cell there (its transformations as
  one DuckDB query, the Tables group, cell numbers, `@cell` links, the uses line; the copy buttons
  left the grid's steps strip), HTML cells (a design drawn from a cell's HTML in a walled-off frame,
  `{{ name }}` filled from the kernel), the Streamlit canvas (a Streamlit app is a Workbench document of
  its own, `.stapp.json`: pages of blocks, each a link to a Python cell, on a 12-column grid; Play shows
  the page live in place; a Python cell that calls Streamlit is live in its cell; Export; Save as),
  projects (a folder: data.ipynb and its export data.py, the canvas and its export pages/*.py), named
  cells, the Data panel's Streamlit cells pane, tabs that pop out into windows of their own (and move
  back) with their unsaved text and kernel, Settings' Panels (switches, all on at each start), the
  Analyze menu, the Sandbox, compare's diff and tie-out,
  Copy code on analysis results (the analysis as Python, on the clipboard), and the built-in starter pack
  (Power BI actions, Excel and file functions, DAX, HTML and Streamlit snippets dropped into cells). Not built: M9 (sandbox)
  and the Jupyter display hook (the plan's "parallel extras").
- **Record verification results** in [docs/verified.md](docs/verified.md); decisions and open
  notes go in [docs/ideas.md](docs/ideas.md).
- **Data is sensitive.** Use only made-up data in tests, examples and screenshots. Keep the
  posture: 127.0.0.1 only, token on every data route, DuckDB locked (`adapters/database.py`),
  nothing written to disk except explicit exports, saved dashboards, and the audit log.

## Layout

The Python is arranged after "Architecture Patterns with Python" (Cosmic Python); [REFACTOR.md](REFACTOR.md)
has the rules and why. Three layers, imports pointing inwards, nothing deeper than
`src/swissarmybench/<folder>/<file>.py`, one file per feature in each layer.
`tests/test_architecture.py` checks all of it.

```
src/swissarmygrid/       the old name, one release: `import swissarmygrid` is this package under it (a warning)
src/swissarmybench/
  settings.py            every limit (plan 6a) in one frozen dataclass
  renamed.py             the old name (SwissArmyGrid) for one release: SWISSARMYGRID_* read after the new
                         variables, the state folder moved on first start, the old commands; the next
                         release removes it, src/swissarmygrid/ and every OLD_* name (tests/test_renamed.py)
  stats.py               public: the Analyze menu's analyses on your own table (what notebook code calls)
  bootstrap.py           the composition root: builds the adapters, hands them to the services

  domain/                the model and its rules. Standard library and sqlglot only; no I/O, no clock
    datasets.py          Column, DatasetInfo, names, the dataset errors
    steps.py             steps -> SQL, each step in plain words, view settings
    grids.py             Grid, the registry, request generations, selections, windows, view keys
    sql_guard.py         what a SQL box, "+" tab or agent query may say
    codegen.py           generated code: the steps as one DuckDB query, and how it is pasted and run
    charts.py            chart spec validation, the aggregate query's text, Vega-Lite, Altair
    export.py            export options, provenance
    relationships.py     keys, the Key Finder's scoring, compare, relationship models, the ERD; tangs
                         (the .tang file: a saved, shared set of relationships) and the relationship
                         finder's rules (judge, suggest, implied joins, paths between tables)
    catalogs.py          catalog rules: dialects (DAX among them: 'Table'[Column], EVALUATE TOPN, COUNTROWS),
                         names, which source column is read as what
    powerbi.py           a Power BI workspace: a dataset's name with its connection (Finance/Sales model),
                         a table's name as a grid (the dataset's too when two share it), a dataset's own
                         relationships as the app's model (the INFO functions' rows, named or numbered)
    blades.py            a blade as text and as a record: what its code makes, asks for and imports
                         (read with ast), its pip packages, the portable .blade.py file (a
                         `# /// swissarmybench-blade` TOML header, zips), its settings (found with ast,
                         placeholders, suggestions, written back), Blade, parse_blade, Template
    snippets.py          snippets (a blade kind): text for a cell with <<name>> placeholders, what each asks
                         for (read from its name), a value written safely for where it stands (DAX, Python, HTML)
    packages.py          the pip packages a blade's imports need (re-exported by blades.py)
    stats.py             the shared statistics: chi-square, t, F and normal distributions, effect sizes
    analysis.py          the Analyze menu's math and query text: the fit test (Benford, Nigrini), outliers
                         (amount fences, frequency on two scales), odds (ratios, Woolf's range), buckets,
                         find predictors' rules, the Data shape check, and the notebook code (one
                         swissarmybench.stats call)
    regression.py        linear and logistic regression: the terms as SQL, the sums, Cholesky, ranges,
                         what-if predictions, the model as SQL (predicted and miss columns)
    timeseries.py        periods, the seasonal index, anomalies against neighbours, steps in the level,
                         memory, growth; the forecast (trend, steps, season, predictors, held-back check)
    tieout.py            the tie-out report: shared columns, the two GROUP BYs joined, ties or off
    proofs.py            Show the math: each analysis result as a step-by-step proof (markdown)
    themes.py            the Sandbox's 20 themes and imported ones, every colour made readable (WCAG)
    diff.py              compare's diff mode: which cells differ (tolerance, trim, case), as SQL and Python
    python_connections.py a connection from the user's own Python (three boxes: Connect, List the tables,
                         Read a table): the environment variables its code reads (found with ast), where
                         each comes from (environment, keyring, a vault's entry, a plain value), the
                         catalog's shape, what Read returned ((rows, total), the limit)
    connections.py       which blades are connections (database, file, key vault), the Add connection form, a
                         password's source (renamed in the code: secret("WAREHOUSE_PASSWORD")), a vault's
                         secret names as variables (warehouse-password -> WAREHOUSE_PASSWORD)
    notebooks.py         the Workbench's notebooks (.ipynb; a SQL cell is a %%sql code cell, a DAX cell a
                         %%dax one, an HTML cell a %%html one with its pane's height in its metadata) and scripts;
                         each cell's number (never changes, never reused), its name (a label, in its
                         metadata) and its part in the Tables group
    table_cells.py       every table's read-only cell: the names code makes, needs and uses; the uses
                         line (`# uses orders @cell3`); the Tables group's order and why a maker stays
                         put; a script's `# region Tables` and `# %% [7] [table] orders` markers; a
                         table's cell as text (its load, a small paste written out, its transformations)
    html_cells.py        HTML cells: the `{{ name }}` names; a value as what goes into a design (escaped
                         text, a table up to 50 rows, a picture); the filling, by where a name stands
                         (among the words, in a <script>, in a tag), so data never becomes markup or
                         script; a script's `# %% [7] [html] height=320` cell (the HTML as one string
                         that does nothing); the design frame's Content-Security-Policy
    streamlit_cells.py   a Streamlit app: its file (sales.stapp.json: pages, blocks, links; no code), a
                         link against the app's file, a cell (what it makes and reads, by ast), the
                         12-column grid (rows, settle), the run order (a cycle said), a page as ONE
                         Streamlit page (slots first, blocks in name order, widget keys of their own),
                         the tables' preamble, the export, the saved pages (pages/*.py)
    streamlit_use.py     which Python cells call Streamlit (ast): they are shown live. Standard library
                         only (a kernel's Run file reads a script by the same rule)
    projects.py          a project: data.py as the export of data.ipynb's code cells (imports in a plain
                         kernel, kept under Streamlit, a stub for a table with no load: no rows), a
                         notebook for a zip, requirements, README, which files open
    environments.py      a notebook's own environment: the libraries offered (groups, presets, imports)
    errors.py            the error panel's words: what an error means and the fixes (replace, import, install,
                         run the cell that makes a name); where a SQL error points
    packs.py             a pack (a Claude Code plugin with blades/ and tangs/): names, the new marketplace's
                         files, Claude Code's install record read loosely, which plugins are switched off
    panels.py            the panels Settings can turn off: their ids, pages and names; all on at the start

  services/              the use cases, one service class per feature, given their ports
    ports.py             the shared ports: SqlSession, Views, Datasets, Jobs, Audit, Notifier
    workspace.py         Workspace (the ports every use case shares, grid lookups and queries) and the
                         outcomes Refused, NotFound, TimedOut, Conflict
    datasets.py          every way data arrives (push, file, paste, the "+" tab's query), list, close
    grids.py             rows, counts, steps and step changes, highlights, the selection
    profile.py           column and table profiles, kept by view key
    analysis.py          the Analyze menu on a grid's view: run_* functions over any cursor (the same code
                         swissarmybench.stats runs on a DataFrame), the Data shape check, the notebook code
    regression.py        regression on a grid's view (run_regression, over any cursor) and what-if
    timeseries.py        time series and forecast on a grid's view (run_time_series, run_forecast)
    sql.py               the SQL box
    export.py            CSV, Excel, Parquet: a download, or saved (an agent's only with a ticket)
    codegen.py           copy as code: generate, then verify what the user will paste
    charts.py            the side panel's cards: charts, notes, tables, diagrams, cross-filtering
    agent.py             the agent door: approvals, export tickets, its reads, the current table,
                         listing and proposing blades (saved on the user's Allow)
    catalogs.py          load, remove, the tree, search
    catalog_loading.py   catalogs that load themselves in the background: on save, at start-up (not a
                         browser-window sign-in), on first use; each a child process, a few at once
    blades.py            save, inspect, fill, refresh, test, install, favourites, folders, export, import
    connections.py       connections: the list, the forms, test before saving, password sources
    folders.py           the page's file chooser (a folder's names: real paths)
    workbench.py         the Workbench: open, save, recent; kernels; completion; environments, remembered;
                         a document moving to another window (handoffs: its state and its kernel)
    workbench_window.py  the agent's workbench_window: a palette command run in the Workbench window
    panels.py            the panels' switches: in memory, shared by every window (panels_changed)
    table_cells.py       every open table as its read-only cell's text (the grid's steps as one DuckDB
                         query); a document's Tables group arranged; where each table came from
    streamlit.py         Streamlit apps: a canvas (pages, blocks: place, move, resize; its linked cells read
                         from the open documents, saved or not, else from the files), a document's live
                         cells; run (the tables as Parquet in a temporary folder), state (missing, out
                         of date), install, export, data.ipynb -> data.py, Save as (the project's zip)
    projects.py          projects: a new one, the files the Workbench opens, Export data.py
    inbox.py             what the user sends their agent (Send to the agent): memory only, read by the
                         prompt hook (client/context_hook.py) and the agent_inbox tool
    relationships.py     the Key Finder, compares, the current model and its library
    tieout.py            the tie-out report on a compare's two grids
    processes.py         Python sessions offering tables: the registry and the Open list
    snapshots.py         a PNG of the page, drawn by the page (app_snapshot); nothing is kept
    packs.py             list packs, make a marketplace, add saved blades and tangs to an editable pack

  adapters/              the driven edge: DuckDB, Arrow, files, the vault, websockets
    database.py          the locked DuckDB, the priority worker pool, DuckDB's own SQL grammar
    datasets.py          the dataset store and its limits; Arrow, CSV, Excel, Parquet, JSON loaders
    views.py             the view cache and windows
    catalogs.py          loaded catalogs: tree queries and search in the locked DuckDB
    blades.py            saved blades (~/.swissarmybench/blades, one JSON each), blade folders
                         (.blade.py files found by their header), favourites; secrets via keyring
    blade_run.py         run a blade, its catalog command, a vault, in this Python (standard library
                         only: sab.blade uses it too); which packages this Python has
    codegen.py           runs copied code and compares it with the grid
    export.py            CSV, Excel and Parquet writers; the export folder
    state_files.py       the audit log, saved dashboards and themes, the connection file, the model library
    streamlit_files.py   a Streamlit app's temporary folder (removed when it stops), and an export's
    projects.py          a project's folder: made, listed, its own files read and written, zipped
    live_updates.py      the pages' and VS Code windows' sockets
    folders.py           a folder's contents for the file chooser
    workbench.py         the Workbench's files (saved on the user's click), recent files, each document's Python
    packs.py             installed packs in Claude Code's plugin folder, editable ones in the blade
                         folders; writing a new marketplace and a pack's files

  server/                the HTTP door, and everything that starts a process
    app.py               asks bootstrap for the services, mounts the routes behind the guard
    http.py              reading requests, shaping answers, each error as its status
    routes_*.py          one per feature: read the request, call the use case, shape the answer
                         (datasets, grids, analysis, regression, timeseries, tieout, agent, cards, catalog, blades, relationships,
                         processes, snapshots, packs, connections, folders, workbench, table_cells, streamlit, projects,
                         panels). Every route serves
                         the agent too (the golden rule) but answering approvals and /blades/{name}/python
    security.py          the guard: 127.0.0.1, the token, Host and Origin
    lifecycle.py, launcher.py, __main__.py   ports, single instance, clean exit; `swissarmybench`
    blade_runner.py      Refresh/Test in a child process; installing packages
    kernels.py           the Workbench's IPython kernels (jupyter_client): run, complete, inspect, interrupt
    environments.py      making a notebook's environment (uv, else venv and pip); the client lent to kernels
    streamlit_apps.py    a notebook's Streamlit process: `streamlit run` in the notebook's own Python,
                         127.0.0.1 only, ended with the server (Streamlit is never the app's dependency)
    streamlit_proxy.py   the live Streamlit pages passed through this server under the app's own secret
                         (its websocket too), so a page's frame policy stays `frame-src 'self'`
    blade_templates.py   the 40 starter blades (3 analyses; a Power BI workspace: code that signs in, lists
                         its datasets and sends DAX to one, each dataset shaped like a database connection)

  starters/              the built-in starter pack (78 read-only .blade.py: Power BI, Excel, Files, DAX, HTML,
                         Streamlit), listed apart, found by name, Copy as your own (tests/test_starters*.py)
  client/push_client.py  push(), ensure_server()
  client/blades_client.py sab.load (a catalog), sab.blade (run a saved blade here), sab.blades, sab.read (a
                         table by a Python connection's own Read a table box)
  client/completion.py   Tab completion of catalog names inside SQL in Jupyter and IPython (sab.complete)
  client/kernel_errors.py the last error taken apart in the kernel (frames, columns, stack_data's values, facts)
  client/sql_cell.py     %%sql <connection> cells in Jupyter and IPython, sab.sql: a database in its own SQL,
                         files (CSV, workbook sheets, folders) and DataFrames in DuckDB; %%dax
                         <connection>/<dataset> cells and sab.dax: DAX on one dataset of a Power BI workspace
  client/sandbox_client.py sab.sandbox: a figure, picture, table or text as a Sandbox card (duck-typed)
  client/watcher.py      a Python session's tables for the Open list; an open one follows its variable
                         (never a table cell's own result: the grid would apply its steps twice)
  client/table_cells.py  a table's read-only cell run in the kernel (%%sab_table, %sab_run): it starts
                         from the original its maker made (a reference, never a copy), so a second run
                         changes nothing
  client/html_cells.py   an HTML cell's names read in the kernel (%%sab_html): tables, figures and values
                         told by their shape; the marks that say a variable changed
  cli/                   the agent command layer: commands.py (the one registry of every page action,
                         named by app area: tabs_, table_, column_, cell_, steps_...), api.py (HTTP + event socket as the
                         agent), main.py (the `sab` terminal command; `sab pack new` runs here, no server)
  mcp/server.py          the stdio MCP server: one typed tool per command, generated from the registry (232 of them).
                         It holds no logic; add a command in cli/commands.py and it appears
web/src/                 main.ts (composition) + one module per panel; lazy/ holds Monaco, Vega, Mermaid,
                         Graphviz, Plotly and ECharts (each loads when first needed; svgSafe cleans drawings);
                         aiPanel.ts is the Sandbox tab (a 12-column dashboard of resizable cards);
                         analyzeMenu.ts is the Table row's Analyze menu and every result's Send to Sandbox,
                         Open as grid and Copy code; analysisDialog.ts is its forms (odds, fit test, find
                         predictors, outliers; Fit test and Outliers are also on a column header's right-click menu);
                         modelDialog.ts the regression and what-if; timeSeriesDialog.ts time series and
                         forecast (Plotly charts in the window); cheatSheets.ts each form's Data shape;
                         analysisCards.ts every result as Sandbox cards (a report-style note and a chart);
                         sandboxDashboards.ts saving and opening the Sandbox as named dashboards;
                         sandboxThemes.ts the Sandbox's own theme (tokens on its element only);
                         tieOutDialog.ts the compare's tie-out report (Tie-out… in the Compare row);
                         bladeAnalysis.ts analysis blades (your own analyses) in the Analyze menu;
                         sandboxPages.ts Page view, Print to PDF and moving cards; sandboxExport.ts the
                         markdown export; cellMenu.ts the right-click menus on cells and headers;
                         tour.ts is the first-time tour (the Application row's question mark: a
                         spotlight card per word, then a matching game);
                         catalogRail.ts (blades + catalog navigation) is the blades page's
                         (catalogPage.ts, static/catalog.html); bladeEditor.ts is the save screen;
                         bladeLibrary.ts is import (review first), export and the blade folders dialog.
                         connectionsWindow.ts is the Application row's Connections (a form per type);
                         pythonConnectionForm.ts is its form for Python (your own code): three code
                         boxes and the environment variables they read;
                         starters.ts is the starter pack in the page: Copy as your own, a snippet's drag,
                         its form and the Insert a snippet… picker;
                         fileChooser.ts picks real paths. The Workbench (static/workbench.html, its own
                         window): workbenchPage.ts (composition: the top row, each group's controls, the
                         status bar), workbenchLayout.ts (RStudio's panes: the groups, the console,
                         Variables, both closed until the status bar opens them; splitters; F1 help as a
                         card; pictures go to the Sandbox), workbenchGroups.ts (tab groups as VS Code's
                         editor groups: drag to reorder or split with the five-way guide, splitters, the
                         layout as data for the session restore; the tab kind registry, registerTabKind,
                         where app pages are added), workbenchData.ts (the Data panel: the open tables,
                         the blades' variables, the Streamlit cells pane (every cell that calls
                         Streamlit, by name: dragged onto a canvas), a project's files once one exists (setFiles); "+ Table"
                         and "+ Blade" open catalogRail.ts beside it; folds), workbenchMenu.ts (its drop-
                         down menus), workbenchAgent.ts (right-click, Send to the agent),
                         workbenchCommands.ts (every window action by one name: the palette, the keys, and
                         the agent's workbench_window), workbenchNotebook.ts (cells, Jupyter's command
                         mode), workbenchScript.ts, workbenchConsole.ts (each document's console),
                         workbenchKernel.ts (runs), workbenchOutputs.ts (outputs drawn as they arrive:
                         colours, `\r`, caps, input boxes), workbenchErrors.ts (the error panel: Visual
                         Studio's Exception Helper; squiggles, hover cards and Ctrl+. fixes in the editor),
                         workbenchCompletion.ts, workbenchEnvironment.ts,
                         workbenchVariables.ts, lazy/codeEditor.ts (Monaco: line edits that keep the
                         cursor, cell links, a script's folds and marker notes),
                         workbenchTables.ts (every table's read-only cell: its state against the text it
                         last ran, the folded lines' words, the uses line); the Tables group, cell
                         numbers and @cell links are drawn in workbenchNotebook.ts and workbenchScript.ts;
                         workbenchHtml.ts (HTML cells: the design's pane that resizes, its sandboxed
                         frame, the names filled by the server's rules, the out-of-date state);
                         a DAX cell (its dataset picker, Monaco's DAX grammar) is drawn in
                         workbenchNotebook.ts, its completion in workbenchCompletion.ts;
                         workbenchStreamlit.ts (a document's live cells: the Python cells that call
                         Streamlit, their state; a cell's link, dragged or copied); workbenchCanvas.ts
                         is a Streamlit app's canvas, a document tab (pages as tabs, blocks on a
                         12-column grid, Play showing the page live in place, Edit, Export, Save as);
                         projects (New project, Open project, Export data.py) are in workbenchPage.ts
                         The grid page has no SQL box and no steps panel (decision 13): stepsStrip.ts is the
                         strip under the title; stepsPanel.ts shows only in its own window (?panel=steps)
web/static/              index.html, grid.css (all theme tokens), build/ (gitignored); design.html is the
                         page an HTML cell's design is drawn in (sandboxed; its policy loads nothing
                         over the network)
tests/                   unit + HTTP tests, golden/ (shared cases), e2e/ (Edge via Playwright),
                         test_architecture.py (the layers, the depth, the plain client),
                         powerbi_standin.py (Power BI and its sign-in stood in for on this computer: a
                         workspace of three made-up datasets), orders_service.py (a made-up web service
                         on 127.0.0.1, for a Python connection)
tools/                   screenshots.py, vscode_check.py
plugin/                  the swissarmybench plugin: skills/swissarmybench-use (SKILL.md, guide), .mcp.json,
                         hooks/hooks.json (the prompt hook: what was sent to the agent, the table in front)
.claude-plugin/          marketplace.json: this repository is a Claude Code marketplace (plugin/ and the pack)
examples/sample_store.py made-up nine-table store with a relationship answer key (test bed for autodetection)
examples/packs/          sample-store: an example pack (a made-up blade, the store's tang)
build.py                 build the page (release) and the one wheel; --vsix also packages the extension
installer/               install.sh and install.ps1 (uv, then the server as a uv tool); build.py stamps the version
.github/workflows/       release.yml: a v* tag builds, tests the installers on Linux and Windows, publishes
tools/smoke_install.py   start the installed server, push the sample store, check it all arrived (used by releases)
vscode-extension/        the optional VS Code extension (TypeScript): the uv install's MCP tools as VS Code tools,
                         and an Open Swiss Army Bench button (starts the server when needed, opens its window)
```

## Commands

See [README.md](README.md). Before a commit: `pytest -q` (includes the browser tests),
`ruff check .`, `ruff format --check .`, `mypy`, and `npm run typecheck` in `web/`. Run
Python as `.venv\Scripts\python -m ...`: `uv run` re-syncs first and fails while a server
started from `swissarmybench.exe` is running.

**Commits:** no `Co-Authored-By` line and no model names in commit messages; the credit to Claude is in
the README (the owner, 2026-11-15).

## Gotchas

- A step change that adds or removes columns must purge the grid's row cache (not just
  refresh), or old rows draw blank in the new column. `gridView.refresh()` handles this.
- AG Grid renders only on-screen columns; tests that look for a new column's header rely on
  `ensureColumnVisible` (done when a step adds a column).
- Starlette's TestClient sends `Host: testserver` on WebSockets; pass `Host: 127.0.0.1:<port>`.
- The e2e fixture gives each test its own grid (`new_grid=True`) and closes it; a plain re-push
  would reuse the first grid with every earlier test's steps.
- In a notebook the app's own cells (a Tables heading's line, a table's read-only cell) are
  `.wb-tcell`; `.wb-cell` is a cell of the user's. A browser test that counts `.wb-cell` counts
  the user's cells only.
- `npm run build` writes source maps (development); `build.py` uses `build:release`
  without them, and the wheel bundles `web/static` as `swissarmybench/web_static`.
- DuckDB quirks the engine depends on are listed in docs/verified.md (LIKE escape, case
  mapping, date_trunc type, parameterized GROUP BY aliases).
