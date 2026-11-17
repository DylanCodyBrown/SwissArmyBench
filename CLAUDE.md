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
- **Renamed (the owner, 2026-11-16):** the Sandbox is **Visualizations** and the Diagram the **ERD**
  (`visualizations_*` commands, `sab.visualizations`, `?view=visualizations`, `?view=erd`). The old names
  answer for one release: `sab.sandbox` (a warning), `sandbox_*` (cli/commands.py OLD_NAMES: run, never
  listed), app_navigate's and app_snapshot's `sandbox`/`diagram`, the old addresses, a .sab's `sandbox/`
  entry. Internal names (aiPanel.ts, sandbox*.ts, the `agent` view, CSS classes) kept the old word.
- **What a connection is (the owner, 2026-11-17): "any connection ... exposes tables that we can write
  duckdb against" / "that is the definition of a connection here".** Every connection kind lists its tables
  and reads one through one contract, and DuckDB SQL names them by the connection
  (`SELECT * FROM [Finance Captive].model_Report`). A thing with no tables (a key vault) is not a connection.
  Connections, APIs, vaults, blades and variables are this computer's library, shared by every project and
  made to be a Git repository (Plans/library.plan.md; the owner, 2026-11-17). APIs already live there:
  `~/.swissarmybench/library/apis/<name>/` (API_<name>.py, the API blade, its web call blades, openapi.json,
  source.json); an API's tables are its web calls with Return as table on, and it is not on the Connections page.
- **The front end and the back end (the owner, 2026-11-17): "set a boundary on what is front end and what is back
  end ... a rule that we can never modify the front end of this app" / "including the edition right in this repo and
  a separated install command".** **Editions never modify the front end.** The front end (`web/`) is one, shared
  by every edition: it draws what the backend's manifest (`GET /app/manifest`: rail areas, pages, commands,
  connection kinds and their forms as data, cell kinds, languages, Settings, starters, context.md's sections) and
  its OpenAPI routes say exists, and it never names an edition or asks which one it is. An edition is backend only:
  the shared core in `src/swissarmybench/` plus `src/swissarmybench/editions/<edition>/` (Python and its manifest,
  never a `.ts`, `.tsx`, `.css` or `.html`). A front-end change is its own change, made for every edition, only on
  the owner's word, never as part of edition work. Tests enforce it (no edition names in `web/`; no front-end files
  under `editions/`; each edition's manifest and routes against the shared schema). Editions: **Swiss Army Bench
  Streamlit Edition** (`swissarmybench`, today's app) and **Swiss Army Bench Power Apps Edition**
  (`swissarmybench-powerapps`, its own install command; Plans/powerapps-spinoff.plan.md), both from this
  repository. Until the manifest boundary is built (Plans/powerapps-spinoff.plan.md section 8a), front-end work
  continues as before; from then on, the rule holds.
- **What SAB is for:** Python-to-DuckDB work on one screen instead of three. SAB brings Python's
  power (analysis, fast data); **DuckDB SQL does the transforming**. Generated transformations are
  DuckDB SQL over the user's own table, never a pandas translation.
- **Where it is going:** [Plans/standalone-workspaces.plan.md](Plans/standalone-workspaces.plan.md):
  a one-command installer that sets up everything; one local server with separate workspaces
  (`sab.create_workspace()`); code goes in the **Workbench** (our own notebooks and scripts on an
  IPython kernel, [Plans/workbench-and-connections.plan.md](Plans/workbench-and-connections.plan.md)),
  Jupyter or Python in the terminal (marimo was built in, then stripped on the owner's call, 2026-11).
  **Rule: code always opens in its own browser window, never in the grid page** (the rail's Notebooks,
  Scripts and Apps open it), so it can sit on another screen; saved workspaces; a tray icon; and a Power BI style
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
  imported; a Dataverse environment, its tables read through the Web API, SQL on its SQL endpoint; a
  connection made of the user's own Python, its environment variables mapped; Add API: an
  OpenAPI document or a form made into API_<name>.py and its connection, every auth type), the SQL
  cell (`%%sql <connection>`), the DAX cell (`%%dax <connection>/<dataset>`, `sab.dax`), the
  Workbench (notebooks, scripts,
  completion, per-notebook environments), every table's read-only cell there (its transformations as
  one DuckDB query, the Tables group, cell numbers, `@cell` links, the uses line; the copy buttons
  left the grid's steps strip), HTML cells (a design drawn from a cell's HTML in a walled-off frame,
  `{{ name }}` filled from the kernel), the Streamlit canvas (a Streamlit app is a Workbench document of
  its own, `.stapp.json`: pages of blocks, each a link to a Python cell, on a 12-column grid; Play shows
  the page live in place; a Python cell that calls Streamlit is live in its cell; Export; Save as;
  controllers: a cell's `# Makes:` contract with types and defaults, Test this page with AppTest, thin
  cells moved to data.ipynb),
  projects (a folder: data.ipynb and its export data.py, the canvas and its export pages/*.py), named
  cells, the Data panel's Streamlit cells pane, tabs that pop out into windows of their own (and move
  back) with their unsaved text and kernel, Settings' Panels (switches, all on at each start) and Kind colours (app violet, notebook blue, script green), the Workbench's four modes (App, Notebook, Script, Data: each document's own panels), the
  Analyze menu, Visualizations, compare's diff and tie-out,
  Copy code on analysis results (the analysis as Python, on the clipboard), and the built-in starter pack
  (Power BI actions, Excel and file functions, DAX, HTML and Streamlit snippets dropped into cells; Components:
  your own HTML and JavaScript as Streamlit pieces, four of them two-way; Controllers; Text and layout,
  its footer pinned to the window's bottom). Not built: M9 (sandbox)
  and the Jupyter display hook (the plan's "parallel extras").
- **Record verification results** in [docs/verified.md](docs/verified.md); decisions and open
  notes go in [docs/ideas.md](docs/ideas.md).
- **Data is sensitive.** Use only made-up data in tests, examples and screenshots. Keep the
  posture: 127.0.0.1 only, token on every data route (or, for the pages, the `sab_<port>` cookie the
  token buys once: HttpOnly, SameSite=Strict, a per-start secret, our own Origin on unsafe methods;
  `server/security.py`), DuckDB locked (`adapters/database.py`),
  nothing written to disk except explicit exports, saved dashboards, the audit log and, in beta mode,
  the beta log (`~/.swissarmybench/logs`: redacted errors, slow requests, processes, page errors and
  the user's notes; no data, SQL, code, secrets or paths; the owner's call for the beta, 2026-11-15).
  **One request leaves the computer, by the owner's call (2026-11-16):** the update check, PyPI's JSON for
  `swissarmybench` (then GitHub's latest release), at start and every six hours, carrying nothing but
  itself; Settings' Check for updates turns it off (`update.json`). The tray's and updates' small state
  files: `tray.json` (its process id), `update_failed.json`, `server_events.json` (read once, then gone); `follow.json` (Follow the agent on or off); `colours.toml` (each connection's colour, by name).
  **Variables (the owner, 2026-11-16/17):** this computer's, never in a .sab: `variables.json` (names, sources,
  plain values that may be shared), `local/variables.json` (values marked this computer only), a secret's
  value in the keyring only; the values are set in the server's environment while it runs.
  **Launch Claude (the owner, 2026-11-16):** on the user's click only (403 for the agent), the state
  folder's `claude/<project>/` is written (CLAUDE.md, .mcp.json, .claude/settings.json: metadata only, no
  row, value or secret); once a launch made it, its **context.md** (the app's live picture: connections,
  tables, the ERD, variables by name and source, documents, windows, the tool guide; metadata only, names
  as data) is rewritten while the app runs, atomically and only when its text changes (2026-11-17); `claude.json` keeps the chosen installs and the bypass switch, and a Claude
  Desktop install's claude_desktop_config.json gets the `swissarmybench` server (asked once, a dated
  backup first, nothing else changed, no token).
  **Projects as one .sab file (the owner, 2026-11-16):** a .sab is written on Save, on New project (where
  the user named, at once), by Autosave when the user turned it on, and by the Autosave switch itself
  (project.json only); the agent's save waits for the user's Allow when it keeps a table's rows. An open
  one is unpacked into a working folder in the system's temporary folder, removed when it closes or the
  server stops; `recent_projects.json` holds the recent projects' paths and times only. **Everything is
  the project's own (2026-11-16):** its connections and blades (`.sab/blades`, the blade store's JSON) and
  saved dashboards (`.sab/dashboards`) live in its working folder and its .sab; with no project open the
  stores are this computer's (~/.swissarmybench/blades, the state folder's dashboards). Never a secret,
  token or password in a .sab: a connection names where its password comes from (keyring, environment,
  vault), resolved on each computer by the connection's name.

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
    dataverse.py         a Dataverse environment: the connection's code as text (standard library: the Web
                         API's OData reads, paging, choice labels, the metadata as the catalog, FetchXML; SQL
                         on the read-only SQL endpoint, TDS port 5558, pyodbc with the Entra token), its three
                         sign-ins (as you, managed identity, an app registration whose secret is a vault's),
                         its Read a table, the SQL endpoint being off said plainly with the sab.read instead
    lakes.py             Lakes and SharePoint as connections (onelake, datalake, delta, sharepoint, sharepoint_docs):
                         each kind's code assembled, its sign-ins, READ (the connection's own read: columns and
                         filters sent), path names and @version/@time, the env variable names suggested
    lake_code.py         the lake kinds' shared code as text: stores (a folder, ADLS Gen2/OneLake by the DFS API
                         with a token, a SAS or a key-signed SAS; S3 by httpfs), a Delta log read here, the one
                         reader (delta_scan, else deltalake, else the log and read_parquet over HTTPS), the writes
    entra.py             Microsoft Entra sign-in as text for the five: as you, managed identity, an app
                         registration (a vault's secret), ROPC (MSAL or stdlib; AADSTS codes in plain words)
    sharepoint.py        SharePoint through Graph as text: lists (typed columns, lookups, people, $filter,
                         $batch writes retried on 429) and documents (each library's file index, CSV/Parquet/
                         JSON-lines files and workbook sheets and named tables as tables, kept by eTag)
    powerbi.py           a Power BI workspace: a dataset's name with its connection (Finance/Sales model),
                         a table's name as a grid (the dataset's too when two share it), a dataset's own
                         relationships as the app's model (the INFO functions' rows, named or numbered)
    blades.py            a blade as text and as a record: what its code makes, asks for and imports
                         (read with ast), its pip packages, the portable .blade.py file (a
                         `# /// swissarmybench-blade` TOML header, zips), its settings (found with ast,
                         placeholders, suggestions, written back), Blade, parse_blade, Template
    certificate_files.py a certificate or keystore file setting (verify, sslrootcert, sslcert, sslkey, keystore)
                         as a path or `os.environ.get("NAME", r"<this computer's path>")`: read back, written,
                         `import os` added; blades.env_settings lists the mappings (export, Run settings)
    keystores.py         Trino's client certificate: the keystore read inside the connection's own code
                         (PKCS#12 by cryptography, JKS/JCEKS by pyjks, by its first bytes), its key and chain
                         as 0600 PEM files removed at exit; the two sign-ins' code
    snippets.py          snippets (a blade kind): text for a cell with <<name>> placeholders, what each asks
                         for (read from its name), a value written safely for where it stands (DAX, Python, HTML)
    packages.py          the pip packages a blade's imports need (re-exported by blades.py); a missing package
                         said one way everywhere: {"missing": {feature, packages, python ("app" or a path),
                         command}}, the feature in plain words, MissingPackagesError (422 with it)
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
    themes.py            Visualizations' 20 themes and imported ones, every colour made readable (WCAG)
    diff.py              compare's diff mode: which cells differ (tolerance, trim, case), as SQL and Python
    python_connections.py a connection from the user's own Python (three boxes: Connect, List the tables,
                         Read a table): the environment variables its code reads (found with ast), where
                         each comes from (environment, keyring, a vault's entry, a plain value), the
                         catalog's shape, what Read returned ((rows, total), the limit)
    apis.py              Add API: an OpenAPI document (2.0, 3.x) or a form read into operations and tables, the
                         auth types (their settings and variables), the Azure, AWS and Google presets, the
                         connection's three boxes, what a re-import changes
    api_clients.py       Add API's made file, API_<name>.py: one stdlib class (a method per operation, retries,
                         paging, DataFrames, each auth type's signing), its mark, its methods read back, and
                         the file pasted inline (the exporter)
    api_explorer.py      the APIs page: an OpenAPI document read for people (each operation's inputs, body and
                         outputs as schema trees with made-up examples, the named schemas and where each is
                         used), search across APIs, Refresh's diff, Try it's request and answer (sign-in headers
                         hidden), a form-made API written as an OpenAPI document
    web_calls.py         web call blades (an API's one endpoint, through its API blade): their [web_call] header,
                         Return as table (the one gate to DuckDB SQL), the common shapes found (records,
                         envelopes, header and rows; the header's types as DuckDB's), DuckDB's conversion,
                         the code, and the tables contract (table_calls: exactly the switched-on calls)
    structures.py        Structures: JSON, YAML (the adapter's), XML (no DOCTYPE or entity) and TOML (written
                         here); paths ($.orders[3], [*]); steps replayed on the original (pick, filter, rename,
                         remove, set, add, sort, flatten); records for a grid; shapes; a structure's lineage
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
    controllers.py       a cell as a controller: its contract (the header's `# Makes: region: str = "All";
                         by_region: table = orders`, read with ast), role, widgets, query parameters; a
                         page's defaults for a maker not on it, its check (cycles, names made twice);
                         Test this page's plan, its AppTest runner (text) and its answer on the blocks
    thin_cells.py        a view cell's model work (a table filtered, grouped or joined) and its move to a
                         named cell of data.ipynb, one `from data import ...` line left
    projects.py          a project: data.py as the export of data.ipynb's code cells (imports in a plain
                         kernel, kept under Streamlit, a stub for a table with no load: no rows), a
                         notebook for a zip, requirements, README, which files open
    project_scope.py     what is the open project's own: its documents (by kind; data.py and pages/*.py
                         marked made; each notebook's role: data.ipynb data, any other app; notebook_kind), its .sab/blades and .sab/dashboards, an import's free names and
                         picks, a connection's passwords with no source on this computer and the fix
    sab_files.py         a project as one .sab file (a zip): project.json (each table's source and grids'
                         steps, the tabs, the windows' layout, autosave; unknown fields kept, a newer format read-only),
                         sources from origins (a file relative to the .sab), zip entries checked (no `..`,
                         no absolute path, no link, sizes), which files go in (code and text, never data),
                         notebooks without outputs, a table's fix when it cannot come back
    environments.py      a notebook's own environment: the libraries offered (groups, presets, imports)
    errors.py            the error panel's words: what an error means and the fixes (replace, import, install,
                         run the cell that makes a name); where a SQL error points
    packs.py             a pack (a Claude Code plugin with blades/ and tangs/): names, the new marketplace's
                         files, Claude Code's install record read loosely, which plugins are switched off
    panels.py            the panels Settings can turn off: their ids, pages and names; all on at the start
    script_export.py     a notebook or script as one self-contained automation: one ordered plan of steps, rendered
                         as a .py (plain python) or a linear .ipynb; script_runtime.py the helper text it inlines
                         (the package check, settings, the vault by managed identity, connections)
    lineage.py           a cell's or a block's lineage back to the data: makes and reads, @cell links, a
                         table's grid steps and origin, data.ipynb, controllers; nodes, edges, Mermaid
    approvals.py         approved outputs: a cell's outputs as a snapshot, the comparison, its lines, no
                         rows in a zip. Standard library only and standalone (an export can inline it)
    kind_colours.py      kind colours (app violet, notebook blue, script green): each theme's default, a
                         chosen colour made readable in every theme, never amber
    app_settings.py      App mode: a Streamlit app's page settings (title, icon, layout, logo, theme
                         colours) as st.set_page_config, st.logo, .streamlit/config.toml; the live page's
                         session state for the State panel (the tail each live page runs, its rows)
    notebook_flow.py     Notebook mode: each cell's state from the run order (notRun, edited, outOfDate
                         with the names made again) and the Outline (headings, named cells)
    script_runs.py       Script mode: run settings (arguments; each variable's source: this computer, a
                         plain value, a key vault, never a secret's value), the variables a script needs,
                         a scheduled run's plan, a run's record
    dictionary.py        Data mode: data.ipynb's data dictionary (plain-word types, descriptions kept in
                         data.ipynb's metadata and written into data.py, where each column comes from)
    updates.py           versions (PEP 440), PyPI's and GitHub's release lists, which is offered, the
                         update's plan (uv tool install --force), the tray's menu as data
    beta_log.py          beta mode's default (one constant), the beta log's redaction (quoted text, numbers,
                         secrets, paths; table and column aliases), stacks as file:line, notes, the rate cap
    navigation.py        app_navigate's places: each window's (home, catalog, workbench) and the notice
    claude.py            Launch Claude: Claude Code and Claude Desktop found loosely (registry, Store, Start menu,
                         bundles, .desktop files, PATH answers read), the official first; CLAUDE.md (a stable
                         header and `@context.md`), .mcp.json, the prompt hook (--folder); the user's terminal
                         as an argument list; Desktop's config merged; install help
    context_md.py        context.md, the app's live picture: its sections (Project, Connections with their
                         DuckDB SQL names and a loaded catalog's first 40 tables, APIs, Open tables, Structures,
                         Relationships, Variables, Documents, Windows, Tool guide), every name as code (data),
                         the budget's trims in order (columns, catalog lists, guide topics, long lists), each
                         section's digest and the prompt hook's "context.md changed: ..." line
    session_log.py       the Session page's log: each audit entry's words, area and object (a grid, a card, a
                         relationship, a connection, a cell), names and counts only; the filter; Follow
    write_capability.py  what each connection kind writes (its operations, how) or why it is read-only; the Write
                         starters each kind has (by their tags); a kind is connection_tables' (TABLE_KINDS), a
                         database's or file's its template: the Connections page's Writes / Read-only
    connection_usage.py  the Connections page's rules: a connection's references in notebooks, scripts and
                         canvases (%%sql, %%dax, sab.sql/dax/read/blade/connection, read with ast), the calls
                         this session by kind, a card's status word, the settings it may show (no password)
    connection_colours.py each connection's colour: the palette and its turns, the rail's colours refused or
                         turned away from, each theme's readable colour, colours.toml's text (sorted, stable)
    connection_swap.py   a table's connection swapped: a table matched in another catalog (name in any case,
                         schema then database; an ODBC database as Trino's catalog), a read query checked, the
                         code pointed at the new connection (the name only: ast, a %%sql/%%dax line; ticked cells)
    variables.py         the Variables page: this computer's variables (plain, this computer only, keyring), the
                         shareable and local halves, each variable's source (vault, value, keyring, env,
                         missing) and uses (connections, cells by ast, Run settings), which values show, rename
    connection_tables.py what a connection is: the tables contract (each kind's way to list and read; NO_TABLES and
                         why), a table named in DuckDB SQL by its connection ([Finance Captive].Sales: brackets,
                         references in sqlglot's tree, resolved in any case, a shared Power BI name asking for its
                         dataset), the work sent to the source (columns, plain filters, a safe LIMIT), the limit's words

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
    session_log.py       the Session page: the audit heard (Heard), this session's entries in memory, the
                         `session_entry` notice; Follow the agent (follow.json; 403 for the agent)
    connection_usage.py  the Connections page: the cards (status, calls), a connection's references (the
                         documents: recent, open, the project's: one seam), configuration (never a value),
                         and its calls this session (the app's runs, a Workbench kernel's report; memory only)
    connection_colours.py every connection's colour (this computer's: the same in every project), set by the
                         user or the agent, a new connection's next free one, the connections cells name
    connection_swap.py   a table read from another connection with its steps kept (matched, picked, or its query
                         reviewed), every table of a deleted connection moved, the undo (old rows in memory), the
                         cells repointed (an open document in the Workbench window, else its file)
    variables.py         the Variables page: list, add, change, rename (connections and Run settings follow),
                         remove, Show (the user's: 403 for the agent); the values set in this server's environment
    connection_tables.py the contract's list and read for every kind, DuckDB SQL naming a connection's table (each
                         read: every row the query needs, counted first, refused past the limit; kept for the
                         session by what was sent, Refresh), the Connections page's tree, Open all of a dataset
    apis.py              Add API: preview, add (into this computer's library, apis/<name>/: API_<name>.py, its API
                         blade, a web call blade per operation, openapi.json, source.json), inline (the exporter)
    api_explorer.py      the APIs page: the library's APIs (cards), explore, search, send (the answer in
                         Structures, its origin the call; Run again), save a web call (Return as table), the
                         API blade's tables made again, Refresh then apply, rename, delete (the agent's on Allow)
    structures.py        Structures: open (a file, a paste, New, an API's answer, a kernel's value), the text
                         view, steps, Open as grid, Save and Save as (the project's structures/), the project's
                         files and the ones open (project.json), sab.structure's read, references, lineage
    folders.py           the page's file chooser (a folder's names: real paths)
    workbench.py         the Workbench: open, save, recent; kernels; completion; environments, remembered;
                         a document moving to another window (handoffs: its state and its kernel)
    workbench_window.py  the agent's workbench_window: a palette command run in the Workbench window
    panels.py            the panels' switches: in memory, shared by every window (panels_changed)
    navigation.py        app_navigate: a window sent Home, Back, Forward or to a view (the page moves itself)
    lineage.py           a lineage with each step's value: from the kernel, a playing page, the grid
    kind_colours.py      the kind colours: shared by every window (kind_colours_changed), kept across
                         restarts (kind_colours.json)
    script_runs.py       a script's run settings (run_settings.json), Run as scheduled, its run history
                         (memory only)
    beta_log.py          beta mode (beta.json, SWISSARMYBENCH_BETA wins), the log's events, notes, export, clear
    updates.py           the update check (start, every six hours; the switch), Update to X (asks only when
                         work would be lost; the agent's waits for Allow), start at sign-in
    claude.py            Launch Claude: what was found, the user's choices, the folder written, the terminal or
                         Desktop started (Desktop's config asked once); the agent reads only
    context_md.py        context.md kept current: gathered from the services, looked at after a notice (every
                         2 s), written once a change settled; what the agent last read (launch, prompt,
                         app_context) and the sections changed since; SEAM for APIs and Structures
    table_cells.py       every open table as its read-only cell's text (the grid's steps as one DuckDB
                         query); a document's Tables group arranged; where each table came from
    streamlit.py         Streamlit apps: a canvas (pages, blocks: place, move, resize; its linked cells read
                         from the open documents, saved or not, else from the files), a document's live
                         cells; run (the tables as Parquet in a temporary folder), state (missing, out
                         of date), install, export, data.ipynb -> data.py, Save as (the project's zip)
    streamlit_ports.py   the ports those stand on: the app's temporary folder, a project's, the process
    streamlit_documents.py  a document's cells as an app reads them: sent by its window, or from its file
    controllers.py       a canvas page's controllers: the check, Test this page (the page written so each
                         block records its error, AppTest in the app's Python), a thin cell's move plan
    projects.py          projects: a new one, the files the Workbench opens, Export data.py
    sab_projects.py      a project as one .sab: new (saved first, where the user named), open (each table read
                         again with its steps; Visualizations, model, layout), save (rows only on a tick; the
                         agent's with them on the user's Allow), autosave (a quiet save once a change
                         settles), close, the recent list, a table's fix; unsaved changes worked out, not
                         tracked; each open, new and close points the stores at the project (scope)
    project_scope.py     the open project's documents, and import: documents from another .sab, a project
                         folder or a loose file; connections and blades from another project or this
                         computer's saved ones (a name the project has: skipped, or the next free one)
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
    beta_log.py          the beta log's files: a writer thread, rotation (7 days, 20 MB), pictures, the zip
    connection_colours.py colours.toml (the state folder's; the library's later by its path), written only
                         when it changes
    claude.py            Launch Claude's files: claude/<project>/ (its context.md atomically, only when changed),
                         claude.json, a Desktop config (backup first)
    updates.py           the release list's one GET, update.json, the helper's and the tray's notes
    streamlit_files.py   a Streamlit app's temporary folder (removed when it stops), and an export's
    projects.py          a project's folder: made, listed, its own files read and written, zipped
    sab_files.py         a .sab read (every entry checked first, counted as read) and unpacked into a working
                         folder, written atomically (a temporary file, then a replace); recent_projects.json
    apis.py              Add API: the OpenAPI document read (a file, an address; YAML with PyYAML), API_<name>.py written
    structure_files.py   Structures' files (read, written whole), YAML by PyYAML (else the missing-package
                         answer), records as an Arrow table for Open as grid
    variables.py         the Variables page's files (variables.json shareable, local/variables.json this computer's;
                         the library's later), the keyring (`variable/<NAME>`), the server's own environment
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
                         processes, snapshots, packs, connections, apis, folders, workbench, table_cells, lineage, streamlit,
                         projects, project_scope, panels, navigation, controllers, kind_colours, script_runs, session_log,
                         structures, api_explorer,
                         connection_swap, variables, connection_colours, connection_tables). Every route serves
                         the agent too (the golden rule) but answering approvals and /blades/{name}/python
    security.py          the guard: 127.0.0.1, the token, Host and Origin
    beta_requests.py     the beta log at the door: slow requests by route pattern, errors with their route
    lifecycle.py, launcher.py, __main__.py   ports, single instance, clean exit; `swissarmybench`
                         (start [--background], stop, status, open [file.sab], tray, autostart on|off|status)
    sab-file.ico, .svg   the .sab file's icon (the installers register .sab: `swissarmybench open <file>`)
    tray.py              the tray icon (pystray, Pillow): its menu (domain/updates.py's model), the left
                         click, the server started and watched (restarted 3 times in 5 minutes at most)
    autostart.py         start at sign-in: a Startup shortcut (Windows), a LaunchAgent (macOS), an XDG
                         autostart entry (Linux), each running the tray
    updater.py           Update to X's helper: a copy run by the base Python once the app stopped, it
                         installs with uv, checks the version, starts the app, or the old one and a note
    routes_updates.py    the update check, its switch, Update to X, the tray's menu, start at sign-in
    routes_claude.py     Launch Claude (GET for the agent too; PUT and the launch the user's only)
    claude_finder.py     finding Claude on each system (registry, PowerShell, mdfind, .desktop files) and
                         starting it detached; SWISSARMYBENCH_CLAUDE_STANDIN's stand-in for tests
    blade_runner.py      Refresh/Test in a child process; installing packages
    kernels.py           the Workbench's IPython kernels (jupyter_client): run, complete, inspect, interrupt
    environments.py      making a notebook's environment (uv, else venv and pip); the client lent to kernels
    streamlit_apps.py    a notebook's Streamlit process: `streamlit run` in the notebook's own Python,
                         127.0.0.1 only, ended with the server (Streamlit is never the app's dependency);
                         Test this page's runner, in that Python (`python -I`), in a temporary folder
    streamlit_proxy.py   the live Streamlit pages passed through this server under the app's own secret
                         (its websocket too), so a page's frame policy stays `frame-src 'self'`
    script_runner.py     Run as scheduled: `python <script> <arguments>` as a fresh process with no app
    blade_templates.py   the 40 starter blades (3 analyses; a Power BI workspace: code that signs in, lists
                         its datasets and sends DAX to one, each dataset shaped like a database connection)

  starters/              the built-in starter pack (188 read-only .blade.py: Power BI, Dataverse, SharePoint, Excel, Files,
                         DAX, HTML, Streamlit, Write), listed apart, found by name, Copy as your own (tests/test_starters*.py);
                         Write: 16 functions (write_to_*: one public typed function a target, for functions.py) and
                         54 calls (a cell's text: the call only, dry_run=True), for the connections that write
  client/push_client.py  push(), ensure_server()
  client/writes.py       the Write starters' shared part: the rows staged in a DuckDB of their own, the dry run's
                         plan and the write's counts (Write), files (FileWrite: beside the target, then replaced);
                         write_sql.py each database's quoting, marks, values, types and transaction (SqlWrite;
                         SqlServerWrite: sys.columns' types, #temp staging, MERGE WITH (HOLDLOCK), retried whole on
                         Azure's passing errors), write_dataverse.py ($batch change sets, choice labels, keys).
                         Standard library only; the statements stay in each Write function
  client/blades_client.py sab.load (a catalog), sab.blade (run a saved blade here), sab.blades, sab.read (a
                         table by a Python connection's own Read a table box)
  client/connection_use.py a Workbench kernel's fire-and-forget count of a connection's call (a query, a read,
                         a connect) for the Connections page (nothing outside a Workbench kernel)
  client/structures_client.py sab.structure (a saved structure's value), sab.structure_table (its records as a
                         DataFrame), sab.show_structure (a dict or list as a Structures tab)
  client/completion.py   Tab completion of catalog names inside SQL in Jupyter and IPython (sab.complete)
  client/kernel_errors.py the last error taken apart in the kernel (frames, columns, stack_data's values, facts)
  client/sql_cell.py     %%sql <connection> cells in Jupyter and IPython, sab.sql: a database in its own SQL,
                         files (CSV, workbook sheets, folders) and DataFrames in DuckDB; %%dax
                         <connection>/<dataset> cells and sab.dax: DAX on one dataset of a Power BI workspace
  client/visualizations_client.py sab.visualizations (sab.sandbox, the old name, one release): a figure,
                         picture, table or text as a Visualizations card (duck-typed)
  client/watcher.py      a Python session's tables for the Open list; an open one follows its variable
                         (never a table cell's own result: the grid would apply its steps twice)
  client/lineage_values.py  a value summarised for a lineage card (a table's shape and first rows), in the
                         kernel, and as sab_lineage.py beside a playing page (it notes each block's values)
  client/standalone.py   connections and blades without the app; a notebook run headless (--check-approved)
  client/table_cells.py  a table's read-only cell run in the kernel (%%sab_table, %sab_run): it starts
                         from the original its maker made (a reference, never a copy), so a second run
                         changes nothing
  client/html_cells.py   an HTML cell's names read in the kernel (%%sab_html): tables, figures and values
                         told by their shape; the marks that say a variable changed
  cli/                   the agent command layer: commands.py (the one registry of every page action,
                         named by app area: tabs_, table_, column_, cell_, steps_...), api.py (HTTP + event socket as the
                         agent), main.py (the `sab` terminal command; `sab pack new` runs here, no server)
  mcp/index.md, guide/   the agent's index (read first: the resource swissarmybench://index, and `guide` with no
                         arguments) and the guide's topics (swissarmybench://guide/<topic>, guide(topic=...))
  mcp/server.py          the stdio MCP server: one typed tool per command, generated from the registry (282 of them).
                         It holds no logic; add a command in cli/commands.py and it appears
web/src/                 main.ts (composition) + one module per panel; lazy/ holds Monaco, Vega, Mermaid,
                         Graphviz, Plotly and ECharts (each loads when first needed; svgSafe cleans drawings);
                         nav.ts is getting around on every page and window (design principle 8.11): the mark
                         (home; another window brings the home window, named sab-home, forward; Alt+Home),
                         views in the address (go: pushed for the user's moves, replaced for the app's; Back
                         and Forward are the browser's), layers (a dialog with views of its own, open=<key>:
                         Settings, Connections), every other dialog an entry Back closes, backButton (named
                         for where it goes), crumbs, setTitle (the page, then the place), app_navigate;
                         rail.ts is the slim icon rail down the left of every page and window, in the order of
                         the work (the owner, 2026-11-17): Connections, Variables, Grids, ERD, APIs, Structures,
                         Blades, Notebooks, Scripts, Apps, Visualizations, Session, Settings at the
                         bottom: a click is a nav.ts move in this tab, and every icon lands on a page (no
                         dialog, no menu); the current area marked; Open in a new window on request; always
                         there (no switch), and the top tabs and the Application row no longer repeat its
                         areas (the owner, 2026-11-16); areaPage.ts is a page of the rail's over any page
                         (Settings, Connections, Session: open=settings, open=connections, open=session); variablesPage.ts the Variables page (open=variables:
                         by source, uses, Add variable, Show for a keyring secret); sessionPage.ts the Session page
                         (this session's log, live, each entry a link; The agent / Me / Both; Follow the agent: main.ts brings
                         the grids, Visualizations and the ERD to the front, workbenchPage.ts a cell; never while the user
                         types; the rail's count); connectionsWindow.ts the
                         Connections page (cards, a card's detail: references, configuration, calls; no APIs);
                         connectionTree.ts a connection's tables as a tree in its detail (search, Open, Preview,
                         Copy name, Open all, Import its relationships, Query in a notebook); connectionSql.ts the
                         connections a DuckDB query names (a SQL cell's head) and their completion;
                         workbenchLanding.ts a kind's landing page in the Workbench (?kind=notebook&view=list:
                         its documents as cards, Scripts' and Notebooks' Transformations cards first, Notebooks'
                         under Data notebook and App notebooks; New and Open… in the top bar);
                         aiPanel.ts is Visualizations (a 12-column dashboard of resizable cards);
                         analyzeMenu.ts is the Table row's Analyze menu and every result's Send to Visualizations,
                         Open as grid and Copy code; analysisDialog.ts is its forms (odds, fit test, find
                         predictors, outliers; Fit test and Outliers are also on a column header's right-click menu);
                         modelDialog.ts the regression and what-if; timeSeriesDialog.ts time series and
                         forecast (Plotly charts in the window); cheatSheets.ts each form's Data shape;
                         analysisCards.ts every result as Visualizations cards (a report-style note and a chart);
                         sandboxDashboards.ts saving and opening Visualizations as named dashboards;
                         sandboxThemes.ts Visualizations' own theme (tokens on its element only);
                         tieOutDialog.ts the compare's tie-out report (Tie-out… in the Compare row);
                         bladeAnalysis.ts analysis blades (your own analyses) in the Analyze menu;
                         sandboxPages.ts Page view, Print to PDF and moving cards; sandboxExport.ts the
                         markdown export; cellMenu.ts the right-click menus on cells and headers;
                         tour.ts is the first-time tour (on the Start page only: a
                         spotlight card per word, then a matching game);
                         catalogRail.ts (blades + catalog navigation) is the blades page's
                         (catalogPage.ts, static/catalog.html); bladeEditor.ts is the save screen;
                         bladeLibrary.ts is import (review first), export and the blade folders dialog.
                         connectionsWindow.ts's forms (a form per type) open in the Connections page;
                         addApi.ts is Add API (an OpenAPI document or endpoints, the sign-in, the preview), on the
                         APIs page; apisPage.ts the APIs page (open=apis: cards, search, the explorer, Author a
                         call, Refresh's diff); structuresPage.ts the Structures page (open=structures: tabs, the
                         tree and the text, steps, Open as grid, Save, Run again, Lineage) and structureTree.ts
                         its tree and text view (shared with the APIs page);
                         pythonConnectionForm.ts is its form for Python (your own code): three code
                         boxes and the environment variables they read;
                         starters.ts is the starter pack in the page: Copy as your own, a snippet's drag,
                         its form and the Insert a snippet… picker;
                         fileChooser.ts picks real paths. missingPackages.ts is the one missing-package
                         prompt ("<Feature> needs <package>": Install now, Not now; the reminder after
                         Not now, no nagging this session), used by every place that finds one; The Workbench (static/workbench.html, its own
                         window): workbenchPage.ts (composition: the top row, each group's controls, the
                         status bar), workbenchLayout.ts (RStudio's panes: the groups, the console,
                         Variables, both closed until the status bar opens them; splitters; F1 help as a
                         card; pictures go to Visualizations), workbenchGroups.ts (tab groups as VS Code's
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
                         workbenchLineage.ts (the Lineage overlay: Mermaid flow, a value card per step;
                         window.openLineage), workbenchApprovals.ts (Approve the output, the amber note);
                         workbenchStreamlit.ts (a document's live cells: the Python cells that call
                         Streamlit, their state; a cell's link, dragged or copied); workbenchCanvas.ts
                         is a Streamlit app's canvas, a document tab (pages as tabs, blocks on a
                         12-column grid, Play showing the page live in place, Edit, Export, Save as;
                         Test this page, a default said quietly, a thin-cell hint and Move to data.ipynb);
                         projects (New project, Open project, Export data.py) are in workbenchPage.ts;
                         kindColours.ts the kind colours (Settings' section, the tokens on <html>) and a
                         notebook's kind (in a project data.ipynb the data notebook, any other an app notebook;
                         outside one plain: notebookRole, kindIcon; the Data panel is not beside the data notebook);
                         projectFile.ts a project as one .sab, shared by the home page and the Workbench
                         (open, new: saved first, then Autosave; save with Keep its rows in the file, close,
                         a table's fix, the ● mark); projectImport.ts the import dialog (documents,
                         connections, blades: from another .sab, a project folder, a file, this computer);
                         startView.ts the home page's Start view (/workspace?view=start: New project, Open
                         project…, recent projects, the tour: offered here only; Home brings it), the Grids
                         landing (/workspace?view=grids: a project open, no table: Open a file, Paste,
                         Query, its connections, its tables to fix), the project's group in the
                         Application row (Save, Save as, Close, Autosave) and the strip of tables to fix;
                         connectionColours.ts each connection's colour worn by whatever names it
                         (data-connections: tabs, cells, blocks, cards, the Data panel, Session entries), the
                         swatch and palette; panes.ts groups the home page's tabs by connection;
                         swapConnection.ts the Table row's Connection: <name> (a table read from another
                         connection, its steps kept: the chooser, the other's catalog to pick, the SQL window
                         ?panel=connsql for a query), the strip's Use another connection… and its Undo rows,
                         Point these at <name> (the cells that named the old one, ticked);
                         updates.ts the status bars' "Update available" (Update to X, What's new) and
                         Settings' Check for updates;
                         claudeLaunch.ts the status bars' Launch Claude (one found: straight to it; both: a
                         menu; none: the install help), Desktop's one question, Settings' Claude;
                         the Workbench's modes: workbenchModes.ts (each document's own panels beside it
                         in its group, the status bar's toggles), workbenchApp.ts (App: Properties, page
                         settings, State), workbenchStarters.ts (the Data panel's Starters gallery),
                         workbenchDocModes.ts (Notebook's Outline, Script's Run settings and Run history,
                         Data's Dictionary and Lineage's place); the canvas's selection, wiring, undo,
                         align, duplicate, zoom and Play's preview are in workbenchCanvas.ts
                         The grid page has no SQL box and no steps panel (decision 13): stepsStrip.ts is the
                         strip under the title; stepsPanel.ts shows only in its own window (?panel=steps)
web/static/              index.html, grid.css (all theme tokens), build/ (gitignored); design.html is the
                         page an HTML cell's design is drawn in (sandboxed; its policy loads nothing
                         over the network)
tests/                   unit + HTTP tests, golden/ (shared cases), e2e/ (Edge via Playwright),
                         test_architecture.py (the layers, the depth, the plain client),
                         lake_standins.py (Entra, the ADLS Gen2 DFS API over a made-up lake, OneLake, and Graph
                         for a made-up SharePoint site, all on 127.0.0.1),
                         trino_standin.py (a Trino over HTTPS asking for a client certificate; made-up
                         keystores), powerbi_standin.py (Power BI and its sign-in stood in for on this computer: a
                         workspace of three made-up datasets), dataverse_standin.py (a Dataverse environment's
                         Web API, its metadata and its sign-ins: a made-up company's accounts, contacts and
                         opportunities), dataverse_tds_standin.py (its SQL endpoint at the cursor: a made-up
                         SQLite file), orders_service.py (a made-up web service
                         on 127.0.0.1, for a Python connection), api_standins.py (Add API's made-up
                         orders service, every sign-in it takes stood in for)
tools/                   screenshots.py, vscode_check.py; testbed/: the real-world test bed (testbed.py up|down:
                         PostgreSQL and MariaDB on ports of their own, made-up files; company.py, the made-up
                         company; standins.py, Power BI's Company model and Azure Key Vault) for
                         tests/e2e/test_real_world.py (eleven use cases, action counts, agent parity)
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
