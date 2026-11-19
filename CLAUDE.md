# CLAUDE.md — Swiss Army Bench

A desktop app (PySide6: each page a window, drawn by Qt WebEngine) over a local Python server (Starlette +
uvicorn + in-memory DuckDB) that lives while the app is open: tabular data in live AG Grid pages, with steps,
profiling, SQL, export, verified code generation, charts and an MCP door for agents. The owner, 2026-11-18:
"Change that to the primary install. It's not an extension it is the app framework now and it should have been
since the start." The browser stays possible (`swissarmybench open --browser`), secondary. It runs only on the
user's machine. This repository is the whole product: the Python package at the root, its page in `web/`, and
the optional VS Code extension in `vscode-extension/`.

One package, two installs (`python build.py` builds the wheel, page inside): the plain wheel is a
standard-library-only push client for any Python environment; the `[server]` extra is the app (the server and
the desktop app, PySide6 6.12 pinned), installed once per machine as a uv tool (`uv tool install
"<wheel>[server]"`, the installers add a Start menu / Applications / applications-menu launcher), opened by
`swissarmybench`.

- **The server's life follows the app (the owner, 2026-11-18: "I wanted the server to simply run while the app
  is active and shutdown when it's not"; the tray and start at sign-in removed "entirely"):** it stops 30 s after
  the last window closes (at once when the desktop app closes), or 10 minutes after the last request of the
  agent, VS Code or a Python session with no window open (services/lifecycle.py; `app_lifecycle`); an open
  project is saved first (Autosave on) or the stop waits. No tray, no start at sign-in, no watchdog.

- **Renamed (the owner, 2026-11-15):** SwissArmyGrid is now Swiss Army Bench: `swissarmybench`, alias `sab`.
  Write only the new names; the old ones are read for one release (`renamed.py`, README "Renamed from
  SwissArmyGrid"). The GitHub repository is DylanCodyBrown/SwissArmyBench (renamed; the old address redirects).
- **Renamed (the owner, 2026-11-16):** the Sandbox is **Visualizations** and the Diagram the **ERD**
  (`visualizations_*` commands, `sab.visualizations`, `?view=visualizations`, `?view=erd`). The old names
  answer for one release: `sab.sandbox` (a warning), `sandbox_*` (cli/commands.py OLD_NAMES: run, never
  listed), app_navigate's and app_snapshot's `sandbox`/`diagram`, the old addresses, a project.json's
  `sandbox` key. Internal names (aiPanel.ts, sandbox*.ts, the `agent` view, CSS classes) kept the old word.
- **What a connection is (the owner, 2026-11-17): "any connection ... exposes tables that we can write
  duckdb against" / "that is the definition of a connection here".** Every connection kind lists its tables
  and reads one through one contract, and DuckDB SQL names them by the connection
  (`SELECT * FROM [Finance Captive].model_Report`). A thing with no tables (a key vault) is not a connection.
  Connections, APIs, vaults, blades and variables are this computer's library, shared by every project and
  made to be a Git repository (Plans/library.plan.md; the owner, 2026-11-17): the **library** folder, below. An
  API lives in its `apis/<name>/` (API_<name>.py, the API blade, its web call blades, openapi.json, source.json);
  an API's tables are its web calls with Return as table on, and it is not on the Connections page. Key vaults
  are added and listed on the Variables page, not the Connections page.
- **Connections scale beyond this computer (the owner, 2026-11-17: "we want to advise against any connectors that
  only work locally for the user, this is meant to scale to a function app or up to a hosted streamlit application" /
  "any connector that does not scale to a function app needs to carry a warning that it will only work on your
  machine").** What the app makes (a connection's code, an exported automation, a Streamlit app) must run unchanged on
  an Azure Function App or a hosted Streamlit app: Linux, no desktop, no installed drivers, no signed-in user. So the
  defaults are portable: SQL Server and Azure SQL on `mssql-python`, Dataverse's SQL endpoint on `python-tds`
  ("odbc does not work on function apps"); sign-ins by managed identity, an app registration or a vault. Anything
  that works only here (an installed ODBC driver, Windows integrated sign-in, Entra "as you", the keyring, a path on
  this disk, a desktop app) is advised against, never the default, and carries the amber "Only works on your
  machine: <reason>. On a Function App or hosted Streamlit app use <alternative>." wherever it is chosen or shown
  (the form, the card, the starters, an export), and the agent sees the same.
- **The front end and the back end (the owner, 2026-11-17): "set a boundary on what is front end and what is back
  end ... a rule that we can never modify the front end of this app" / "including the edition right in this repo and
  a separated install command".** **Editions never modify the front end.** The front end (`web/`) is one, shared
  by every edition: it draws what the backend's manifest (`GET /app/manifest`: rail areas, pages, commands,
  connection kinds and their forms as data, cell kinds, languages, Settings, starters, context.md's sections) and
  its OpenAPI routes say exists, and it never names an edition or asks which one it is. An edition is backend only:
  the shared core in `src/swissarmybench/` plus `src/swissarmybench/editions/<edition>/` (Python and its manifest,
  never a `.ts`, `.tsx`, `.css` or `.html`). A front-end change is its own change, made for every edition, only on
  the owner's word, never as part of edition work. Tests enforce it (no edition names in `web/`; no front-end files
  under `editions/`; each edition's manifest and routes against the shared schema). **The base and its extensions
  (Plans/editions.plan.md, the owner 2026-11-17):** the base install is **Swiss Army Bench (BI Edition)**
  (`swissarmybench`: notebooks and analysis, a BI notebook as the deliverable); optional **extensions** plug into
  the same app (entry points, one server, one library): **Accounting** (an Excel workbook from a Python
  automation; cession statements and invoices), **Power Apps** (code apps; Plans/powerapps-spinoff.plan.md) and
  **Streamlit** (today's app-building work, moved out of the base). A project's type names its extension.
  Read "edition" in this rule as "extension": its code is backend and manifest only. **Today (the owner,
  2026-11-17: "It's not an edition now it's the streamlit extension. Preinstalled"):** the app is **Swiss Army
  Bench, with the Streamlit extension preinstalled** (its name in the status bar: Swiss Army Bench); the rail's
  Extensions page lists the extensions (Streamlit preinstalled; Accounting, Power Apps and GitHub Copilot available, one click: Install). Until the manifest boundary is built (Plans/powerapps-spinoff.plan.md section 8a), front-end work
  continues as before; from then on, the rule holds.
- **A blade's code is edited in its file, never in the app (the owner, 2026-11-17: "the code box is read
  only though blades can only be edited in the folder not from the app").** The blade screen shows the code
  read-only (Monaco, as tall as the code) with **Show its file** (the user's click; 403 for the agent); New
  blade makes a `.blade.py` in the library's `blades/` from a template; the app writes only a file's header
  (name, description, tags, `table`), the code's bytes untouched (PUT /blades/{name}, `blades_update`). A
  table blade has a table name of its own ("Shouldnt the table it makes be namable by me with a realtime
  check for available names"), checked live (GET /blades/table-name). The catalog checkbox and the blades
  page's catalog panel went ("what the heck does add to catalog do" / "we dont even need catalog if its just
  tables"): a connection's tables are always listed (a missing listing query is its starter's, on read).
- **What SAB is for:** Python-to-DuckDB work on one screen instead of three. SAB brings Python's
  power (analysis, fast data); **DuckDB SQL does the transforming**. Generated transformations are
  DuckDB SQL over the user's own table, never a pandas translation.
- **Where it is going:** [Plans/standalone-workspaces.plan.md](Plans/standalone-workspaces.plan.md):
  a one-command installer that sets up everything; one local server with separate workspaces
  (`sab.create_workspace()`); code goes in the **Workbench** (our own notebooks and scripts on an
  IPython kernel, [Plans/workbench-and-connections.plan.md](Plans/workbench-and-connections.plan.md)),
  Jupyter or Python in the terminal (marimo was built in, then stripped on the owner's call, 2026-11).
  **Rule: code always opens in its own browser window, never in the grid page** (the rail's Notebooks,
  Scripts and Apps open it), so it can sit on another screen; saved workspaces; the desktop app (PySide6 windows,
  its pages in Qt WebEngine; built 2026-11-18, the browser secondary); and a Power BI style relationships view
  with autodetection. VS Code is optional.
- **The golden rule (the owner, 2026-11-14): every single thing the user can do, the agent can do
  too, through the MCP, with no prompts.** A new user action gets its command in `cli/commands.py`
  (so an MCP tool) in the same change. The only exceptions: the agent cannot answer its own approval
  requests, and no answer the app gives it holds a password's value (`/blades/{name}/python` stays
  refused), and a project's Delete (to the trash) and Show in folder are the user's own (the owner,
  2026-11-17: "the agent cannot delete"), and so is a system file dialog (it opens on the user's screen; the
  agent passes paths to every command directly). Code the agent runs in a Workbench kernel can read what that Python can, which the owner
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
  cells, the Data Explorer (one search over everything that holds data, in the Workbench's pane, its own
  window or the grid page's Ctrl+K), App mode's Streamlit cells panel, tabs that pop out into windows of their own (and move
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
  nothing written to disk except explicit exports, saved dashboards, the library folder (on the user's saves
  and the one-time move into it), the open project's folder (its `.sab/` on Save and Autosave, New
  project's scaffold, `.sab/data/` only on the user's tick), the audit log and, in beta mode,
  the beta log (`~/.swissarmybench/logs`: redacted errors, slow requests, processes, page errors and
  the user's notes; no data, SQL, code, secrets or paths; the owner's call for the beta, 2026-11-15).
  **GitHub sync (the owner, 2026-11-18; the Git extension) sends the team library's and shared projects' files to
  GitHub on the user's Clone, Pull, Push and Commit only (`sync.json` in the state folder: links, never a file's
  content or the token); see the library bullet.** **Otherwise one request leaves the computer, by the owner's call (2026-11-16):** the update check, PyPI's JSON for
  `swissarmybench` (then GitHub's latest release), at start and every six hours, carrying nothing but
  itself; Settings' Check for updates turns it off (`update.json`). The desktop app's and updates' small state
  files: `desktop.json` (the app's process id and its 127.0.0.1 channel's port and key, owner-only), `desktop/`
  (its Qt WebEngine profile: cookies, local storage, cache; `windows.json`, each kind of window's place),
  `update_failed.json` (read once, then gone); `follow.json` (Follow the agent on or off); `library.json` (the library folder's path, when Settings moved it); `extensions.json` (a preinstalled extension the user removed, and the version its bring-back was tried at); `dialogs.json` (the file picker's recent folders per kind of pick: paths only).
  **Variables (the owner, 2026-11-16/17):** the library's, never in a project: `variables.toml` (names, sources,
  plain values that may be shared), `local/variables.toml` (values marked this computer only), a secret's
  value in the keyring only; the values are set in the server's environment while it runs. **`${NAME}` anywhere
  a value is typed (design principle 12.7, the owner 2026-11-18; domain/variable_refs.py):** resolved at use on
  each computer, never stored resolved; a connection field is written into its code as `os.environ["NAME"]`, SQL
  binds it as a parameter, `$${NAME}` is the text; each connection's own saved password became a keyring
  variable once at start (`backup/before-variables-<date>/`), and `variable_refs.json` marks the one-time list
  of saved text that now names a variable. Every form's box is one box (web/src/variableBox.ts: `${` lists the
  variables, `{x}`, the line under it; no source, vault or entry pickers beside a field).
  **Launch Claude (the owner, 2026-11-16):** on the user's click only (403 for the agent), the state
  folder's `claude/<project>/` is written (CLAUDE.md, .mcp.json, .claude/settings.json: metadata only, no
  row, value or secret); once a launch made it, its **context.md** (the app's live picture: connections,
  tables, the ERD, variables by name and source, documents, windows, the tool guide; metadata only, names
  as data) is rewritten while the app runs, atomically and only when its text changes (2026-11-17); `claude.json` keeps the chosen installs and the bypass switch, and a Claude
  Desktop install's claude_desktop_config.json gets the `swissarmybench` server (asked once, a dated
  backup first, nothing else changed, no token).
  **A project is a folder (the owner, 2026-11-17: "consider entire folders projects and take out the
  .sab" / "share entire projects in git repos nativly"; it reverses 2026-11-16's one .sab file):** its
  documents are ordinary files at its top, written by their own Save; the app's state is the project
  folder's `.sab/` (project.json: sorted, no timestamp; visualizations.json and visualizations/ (saved
  dashboards); model.json), written on Save, on New project (scaffolded where the user named, .gitignore
  and README.md only when absent), by Autosave (on by default) and by the Autosave switch, each file only
  when its bytes change. Rows only on the user's "Keep its rows" tick, into `.sab/data/` (Git-ignored);
  the agent's save or Copy project to with rows waits for the user's Allow. Copy project to copies the
  folder (`.sab/data/` on a tick). `recent_projects.json` holds the projects' folder paths and times only;
  `projects.json` the Project Explorer's projects folder, sort, custom order and hidden ones. The old
  single .sab file is not read any more (its conversion removed, the owner, 2026-11-17: `swissarmybench open
  x.sab` says so in one line); the installers take an earlier .sab registration away.
  **The library (the owner, 2026-11-17; Plans/library.plan.md):** connections, APIs, vaults, blades, relationship
  sets, variables and connection colours live outside every project, in one folder of text files made to be a Git
  repository: `~/.swissarmybench/library` (Settings' Library folder points it at another, a clone of a team's;
  `library.json` keeps the path): `connections/`, `vaults/`, `blades/<name>.blade.py`, `apis/<name>/`,
  `relationship-sets/`, `variables.toml`, `colours.toml`, `catalog/` (the shared catalog, below), `local/` (this
  computer only, git-ignored), README.md and .gitignore made on first use. One file per item, the same text for the same thing: a save that changes
  nothing changes no byte. Never a secret, token, password or row in it (nor in a project): a connection names
  where its password comes from (keyring, environment, vault), resolved on each computer by its name; a
  clone asks for each missing one. This computer's older stores (blades/*.json, variables.json, colours.toml,
  tangs/) moved in once at start (the old files in `backup/before-library-<date>/`, said once on the page;
  the library's tangs/, a relationship set's old name, became relationship-sets/ once, 2026-11-17);
  an older project's own `.sab/blades` are copied in as it opens (the same skipped, a different one kept as
  `<name> from <project>`, said) and its next save leaves them out. The app never runs git: **GitHub sync is
  built in instead, as the Git extension (the owner, 2026-11-18: "connect a local GitHub repo and push and pull and fork
  projects so you could work a shared project and clone it into a local project"; chose "Built-in, signed in to
  GitHub"; then "literally steal VS Code's panel for git with the graph and commit and show it with a diff navigator on
  a new rail icon that shows up when you install the git extension" / "literally clone to exactly no deviation")**:
  `extensions/git` (swissarmybench-git, available in the Extensions catalog; not installed, none of it runs). The meta
  store and shared projects are cloned, connected, pulled and pushed through GitHub's web API (api.github.com),
  signed in with the user's GitHub account (a fine-grained token pasted once, or Sign in with GitHub's device flow
  once the app's OAuth client id is filled in; the token in the keyring only, never a file, an answer or a log;
  signing in and out the user's only), and only on the user's action (Clone, Connect, Pull, Push, Commit, Discard,
  Checkout) or the agent's on the user's Allow; no Git installed is needed. Each folder's link (repository,
  branch, the last synced commit, each file's blob SHA as the merge base, the staged files, the conflicts) is the
  state folder's `sync.json`, never in the repository. Pull merges by lines (diff3); a true conflict keeps the
  local file and saves GitHub's beside it as `<name>.theirs`, shown, never forced; Push is fast-forward only,
  refused while behind or when a file looks like it holds a secret; .gitignore's files, `local/`, `.sab/data/` and
  files over 50 MB never go. GitHub is asked only on an action or when Settings, the Explorer or the Source
  Control page asks, at most once a minute: never a background poll. Its **Source Control** page (a rail area the
  backend names, GET /app/areas) is VS Code's Source Control view and graph (its CSS values, graph code, words,
  menus, letters and codicons, MIT: THIRD_PARTY_NOTICES.md) with Monaco's diff editor; what needs a local Git
  (stash, local commits, rebase, amend, hunks, tags, worktrees, remotes) shows disabled. The footer's mark says
  when the open project (or the team library) is out of sync. "Fork" means a local copy of a shared project (Make a
  local copy), not a GitHub fork.
  **A team (the owner, 2026-11-19: "you have made linking a meta store and shared project folder way too
  difficult; the settings menu makes no sense"; it replaces 2026-11-17/18's Meta store folder):** ONE GitHub
  repository holds the team's library at its top and the team's shared projects in its `projects/`. Settings has
  one **Team** box (first after Theme; no rail page, no Projects-page entry): no team: Join a team… and Start a
  team…; joined: "Team: owner/repo", its sync words only when something is to do, Pull, Push and "…" (Open on
  GitHub, Set up this computer, Show its folder, Leave the team); the local projects folder's row; Advanced
  (folded): the two folders as their own paths. Join (one dialog: GitHub sync's Install, its step kept in the state
  folder's `team.json` over the restart; Sign in; the repository) makes the local copy itself in the state
  folder's `team/<owner>-<repo>/` (no path asked), points the library at it and the shared projects folder at its
  `projects/`, then shows Set up this computer; Start makes a private repository (README.md, .gitignore with
  local/ and .sab/data/, projects/) and pushes this computer's library; Leave asks whether to keep a copy of the
  team's items, puts both folders back as they were and leaves the local copy on disk (`team_status`, `team_join`,
  `team_start`, `team_leave`; the agent's on Allow; signing in the user's only). The screen says **Team library**
  (never meta store, working copy, clone or Git in its main words); the code keeps `library`, `shared_folder`,
  `sync`. The shared projects folder inside the team library syncs through that one link. Its `catalog/<connection>.json` is the **shared catalog** (names,
  types, keys, relationships, `used_by` project folder names, present or gone; never a value, count or secret),
  written on the events (a connection saved, its tables listed, relationships changed, a project opened or saved),
  pruned (a deleted connection's file, a table gone 30 days), byte-stable, and read again when the user's pull
  changes it (looked at every few seconds, said once); a file with merge markers is reported and left alone.
  **Set up this computer** (the Team box) is a new computer's checklist: vault sign-ins, values to type once,
  each connection's status, Move to a vault. **Local and shared projects (2026-11-18):** projects.json's
  `local_folder` (the older `folder` key read as it) and `shared_folder` (none by default; pushed and pulled by the user); each card Local or Shared; Share and Make a local copy (`copied_from` in its project.json),
  never .sab/data/ nor .git.

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
  extensions.py          the extensions that are on (entry points `swissarmybench.extensions`, or
                         SWISSARMYBENCH_EXTENSIONS: extension_on(id)), their modules, every project type's
                         mode as data (the base's BASE_MODE, each extension's MODE)

  domain/                the model and its rules. Standard library and sqlglot only; no I/O, no clock
    datasets.py          Column, DatasetInfo, names, the dataset errors
    steps.py             steps -> SQL, each step in plain words, view settings
    grids.py             Grid, the registry, request generations, selections, windows, view keys
    sql_guard.py         what a SQL box, "+" tab or agent query may say
    codegen.py           generated code: the steps as one DuckDB query, and how it is pasted and run
    charts.py            chart spec validation, the aggregate query's text, Vega-Lite, Altair
    export.py            export options, provenance
    relationships.py     keys, the Key Finder's scoring, compare, relationship models, the ERD; relationship
                         sets (the .relationships.json file: a saved, shared set; the old .tang read); the
                         joins in use managed (delete, kind, Run, a deleted connection's taken out) and the
                         relationship finder's rules (judge, suggest, implied joins, paths between tables)
    catalogs.py          catalog rules: dialects (DAX among them: 'Table'[Column], EVALUATE TOPN, COUNTROWS),
                         names, which source column is read as what
    dataverse.py         a Dataverse environment: the connection's code as text (standard library: the Web
                         API's OData reads, paging, choice labels, the metadata as the catalog, FetchXML; SQL
                         on the read-only SQL endpoint, TDS port 5558, python-tds with the Entra token), its three
                         sign-ins (an app registration whose secret is a vault's, managed identity, as you),
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
    blade_templates.py   Template: a starter connection's or blade's code and listing query (re-exported by blades.py)
    blade_tables.py      a table blade's own table name (names_table; the live check's answers: available, a table,
                         a connection, another blade's table, not a valid name), a connection's listing query from
                         its starter (listing_for), New blade's choices, a file's header rewritten (with_header:
                         the code's bytes untouched)
    blades.py            a blade as text and as a record: what its code makes, asks for and imports
                         (read with ast), its pip packages, the portable .blade.py file (a
                         `# /// swissarmybench-blade` TOML header, zips), its settings (found with ast,
                         placeholders, suggestions, written back), Blade, parse_blade, Template
    sql_server.py        SQL Server and Azure SQL made robust: the connection's code as text (a SqlServer object on
                         mssql-python, no ODBC driver: eight sign-ins, the Entra token beside the string and
                         refreshed, errors in plain words by number or words, passing errors tried again, a paused
                         serverless database waited for, mssql-python's Arrow batches typed, SQLCancel on an
                         interrupt, for_writes); the form's options, choices and variables; the catalog from the
                         system views; foreign keys into the ERD; the card; an older pyodbc code told apart and
                         made again with its settings (is_old, upgraded: Update to the new driver)
    portability.py       what runs only on this computer (an ODBC driver, Windows sign-in, Entra as you, a
                         certificate or file on this disk, an AWS profile, the keyring): each with why and what
                         runs on a Function App or a hosted Streamlit app instead; by kind, code and password
                         source; the form's ways, a starter's tags, an export's warning
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
    shared_catalog.py    the shared catalog (the library's catalog/<connection>.json): tables, columns, keys, relationships,
                         used_by, present/gone; the file's text (sorted, one table per block, byte-stable), read back
                         (merge markers and broken JSON said), a listing applied (gone since a date, pruned after N
                         days), the model's keys and relationships added, a deletion taken out, a project's usage
    library_setup.py     Set up this computer: each vault (readable, its sign-in, the variables it gives), the
                         values to type once, each connection's status (works, needs, only works here), shared
                         projects not set up here, the count's words, the notice
    team.py              a team (one GitHub repository: the library at its top, projects/): the layout (README.md,
                         .gitignore, projects/), the local copy's place (team/<owner>-<repo>), the steps and the one
                         kept over Install's restart, the repositories newest first, what a new team takes, Leave's
                         choices, the Joined row's words (only when something is to do)
    library.py           the library's rules: its layout, which folder a blade's file goes in (vaults/,
                         connections/, blades/), README.md and .gitignore, variables.toml and local/variables.toml
                         (sorted, stable), the JSON blades from before it, "<name> from <project>", the notices
    variable_refs.py     `${NAME}` (12.7): references found (positions, the `$${` escape, `:-default`), resolved in
                         one pass (MissingVariables: "NAME is not set on this computer", Set it), the preview
                         (a secret masked), SQL as bound parameters in each driver's style (strings, quoted names
                         and comments left; a name's place refused), the export form (`os.environ[...]` joined by
                         `+`) and read back; a vault's secret names as variables. Standard library only
    blade_suggestions.py a blade's settings' suggestions (other blades' values, the common environment variables)
    refusals.py          the server's one refusal shape (9.5): {error: one sentence, where, fixes: [{label, action:
                         install | set_variable | sign_in | open_settings | try_again, ...}], details: the source's
                         words}; Explained (Refused, NotFound, Conflict, TimedOut may name where and the fixes); a
                         failed run's sentence and details
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
    cell_facts.py        a Python cell's facts (ast): its body, title, what it makes and reads, the modules it
                         imports, Streamlit's widget calls, code indented under a `with` (the Streamlit
                         extension's canvas reads the same)
    streamlit_use.py     which Python cells call Streamlit (ast): they are shown live. Standard library
                         only (a kernel's Run file reads a script by the same rule)
    projects.py          a project: data.py as the export of data.ipynb's code cells (imports in a plain
                         kernel, kept under Streamlit, a stub for a table with no load: no rows), a
                         notebook for a zip, requirements, README, which files open
    project_scope.py     what is the open project's own: its documents (by kind; data.py and pages/*.py
                         marked made; each notebook's role: data.ipynb data, any other app; notebook_kind), its .sab/visualizations (and an older one's .sab/blades), an import's free names and
                         picks, a connection's passwords with no source on this computer and the fix
    sab_files.py         a project is a folder: .sab/project.json (each table's source and grids' steps, the
                         tabs, the windows' layout, autosave; sorted, no timestamp; unknown fields kept, a
                         newer format read-only, a type-only file a project with no tables), .sab/'s paths,
                         sources from origins (a file relative to the project), the scaffold's .gitignore and
                         README, which files are the project's own; a path inside the project checked (no
                         `..`, no absolute path, no drive); a table's fix
    project_explorer.py  the Project Explorer: projects.json read, each project's card (type, counts, Git
                         branch from .git/HEAD, times, missing, an off extension's "needs"), the sorts and the
                         custom order (moved left and right), the filters, the types explained for beginners
    environments.py      a notebook's own environment: the libraries offered (groups, presets, imports)
    errors.py            the error panel's words: what an error means and the fixes (replace, import, install,
                         run the cell that makes a name); where a SQL error points
    packs.py             a pack (a Claude Code plugin with blades/ and relationship-sets/): names, the new marketplace's
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
    notebook_flow.py     Notebook mode: each cell's state from the run order (notRun, edited, outOfDate
                         with the names made again) and the Outline (headings, named cells)
    intellisense.py      the editors' intelligence around Jedi: docstrings (Google, NumPy, reST) for each
                         parameter's words, IPython's lines made Python of the same lines, the app's names
                         inside strings (sab.connection("|"), os.environ["|"], secret("|"), sab.blade("|")),
                         the small lint (compile, undefined names, unused imports, f-strings, == None, bare
                         except) and its fixes, where an import goes, SQL's syntax by sqlglot, the ranking
    script_runs.py       Script mode: run settings (arguments; each variable's source: this computer, a
                         plain value, a key vault, never a secret's value), the variables a script needs,
                         a scheduled run's plan, a run's record
    dictionary.py        Data mode: data.ipynb's data dictionary (plain-word types, descriptions kept in
                         data.ipynb's metadata and written into data.py, where each column comes from)
    updates.py           versions (PEP 440), PyPI's and GitHub's release lists, which is offered, the
                         update's plan (uv tool install --force, each installed extension `--with`)
    extensions.py        extensions: the catalog (streamlit preinstalled; accounting, powerapps, copilot available), statuses
                         (preinstalled, available, installed, coming), an entry point's description read loosely,
                         the wheel on this version's GitHub release, Install's and Remove's plan
    beta_log.py          beta mode's default (one constant), the beta log's redaction (quoted text, numbers,
                         secrets, paths; table and column aliases), stacks as file:line, notes, the rate cap
    navigation.py        app_navigate's places: each window's (home, catalog, workbench) and the notice
    desktop.py           the desktop app's rules: what loads inside (the app's origin) and what goes to the system's
                         browser or is refused, named-window reuse (sab-home), each kind of window's place, pages
                         named without the token, the app's command line, its channel's messages (open, file,
                         status, quit), the clipboard the one permission, window titles, the launcher's icon (PNG,
                         .ico) made with the stdlib; a file opened with the app (its kind: a table, a notebook, a
                         blade, a project; the table's free name)
    lifecycle.py         the server's life: windows, the grace, the start grace, the app closed, the last client's
                         ten minutes, busy, held; when it stops and why (app_lifecycle)
    claude.py            Launch Claude: Claude Code and Claude Desktop found loosely (registry, Store, Start menu,
                         bundles, .desktop files, PATH answers read), the official first; CLAUDE.md (a stable
                         header and `@context.md`), .mcp.json, the prompt hook (--folder); the user's terminal
                         as an argument list; Desktop's config merged; install help
    context_md.py        context.md, the app's live picture: its sections (Project, Connections with their
                         DuckDB SQL names and a loaded catalog's first 40 tables, APIs, Open tables, Structures,
                         Relationships, Variables, Documents, Windows, Tool guide), every name as code (data),
                         the budget's trims in order (columns, catalog lists, guide topics, long lists), each
                         section's digest and the prompt hook's "context.md changed: ..." line
    project_outline.py   the project's outline, ARCHITECTURE.md (the owner, 2026-11-17): the same eight sections
                         every time (Overview, Data sources, Data model with a Mermaid erDiagram, Transformations
                         as DuckDB SQL, Lineage as a flowchart LR, Deliverables, Running it with the Function App
                         checklist, Open issues), "None." when empty; names and types only; the same bytes
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
    file_dialogs.py      the system's own file dialog (the owner, 2026-11-17): a request checked, the tool per system
                         (Windows: Tk's IFileDialog, else PowerShell's Forms dialogs and IFileOpenDialog for a folder;
                         macOS: osascript, else Tk; Linux: kdialog on KDE, zenity, kdialog, else Tk; none without
                         a display or with SWISSARMYBENCH_SYSTEM_DIALOGS=off), each tool's command line (values as
                         arguments or an environment variable, never in a script's text), its answer read; the
                         recent folders per kind of pick (dialogs.json); New folder's name
    explorer.py          the Data Explorer's search: words matched in any case and by parts (cust: customer_id,
                         CustomerKey; customerid: customer_id), spread over a result's path; results by kind
                         (connections, tables, columns, structures, apis, variables, blades), grouped, counted,
                         cut; the code a result is inserted as (a SQL cell's, a Python cell's); a structure's
                         keys by their paths ($.orders[].customer.id, the parts of one place). Names only

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
    explorer.py          the Data Explorer's search: a provider per source (connections and their loaded catalogs,
                         the open tables, variables, blades; a connection whose catalog is not loaded offered);
                         Structures' documents and paths and APIs' table-returning web calls registered from
                         theirs (register("structures"/"apis")); one failing source skipped
    apis.py              Add API: preview, add (into this computer's library, apis/<name>/: API_<name>.py, its API
                         blade, a web call blade per operation, openapi.json, source.json), inline (the exporter)
    api_explorer.py      the APIs page: the library's APIs (cards), explore, search, send (the answer in
                         Structures, its origin the call; Run again), save a web call (Return as table), the
                         API blade's tables made again, Refresh then apply, rename, delete (the agent's on Allow)
    structures.py        Structures: open (a file, a paste, New, an API's answer, a kernel's value), the text
                         view, steps, Open as grid, Save and Save as (the project's structures/), the project's
                         files and the ones open (project.json), sab.structure's read, references, lineage
    folders.py           the page's own file picker (a folder's names: real paths; its quick places; New folder)
    file_dialogs.py      the system's own file dialog on the user's click (403 for the agent), the picker's places
                         and recent folders per kind of pick
    workbench.py         the Workbench: open, save, recent; kernels; completion; environments, remembered;
                         a document moving to another window (handoffs: its state and its kernel)
    workbench_window.py  the agent's workbench_window: a palette command run in the Workbench window
    intellisense.py      the editors' intelligence: complete, signature, hover, lint (Jedi in the kernel or
                         a Script over the project; the app's names; Ruff or pyflakes where there; a worker
                         thread, a one-second budget, superseded requests skipped); what each editor shows,
                         for the agent (workbench_complete, workbench_signature, workbench_problems)
    panels.py            the panels' switches: in memory, shared by every window (panels_changed)
    modes.py             project modes: the open project's type (.sab/project.json) to its mode (canvases,
                         families, languages, cell kinds, tool group, export); GET /app/mode, app_mode; the rail's
                         areas the on extensions add (GET /app/areas: their RAIL, and the footer's mark route)
    navigation.py        app_navigate: a window sent Home, Back, Forward or to a view (the page moves itself)
    lineage.py           a lineage with each step's value: from the kernel, a playing page, the grid
    kind_colours.py      the kind colours: shared by every window (kind_colours_changed), kept across
                         restarts (kind_colours.json)
    script_runs.py       a script's run settings (run_settings.json), Run as scheduled, its run history
                         (memory only)
    beta_log.py          beta mode (beta.json, SWISSARMYBENCH_BETA wins), the log's events, notes, export, clear
    updates.py           the update check (start, every six hours; the switch), Update to X (asks only when
                         work would be lost; the agent's waits for Allow)
    lifecycle.py         the server's life: the windows counted, the clients' requests (from the guard), the stop
                         (an open project saved first, or held), the desktop app's closed
    desktop.py           desktop_status and desktop_open: the app's windows, a page opened in one
    file_watch.py        a table read from a file, watched (a stat every few seconds, off the loop): Changed on
                         disk said once (`file_changed`), Not now; Reload is datasets.py's (steps kept)
    extensions.py        the Extensions page: the cards, Install and Remove handed to the update's helper (the
                         agent's on Allow; Remove asks the user first; a development checkout says what to run)
    claude.py            Launch Claude: what was found, the user's choices, the folder written, the terminal or
                         Desktop started (Desktop's config asked once); the agent reads only
    context_md.py        context.md kept current: gathered from the services, looked at after a notice (every
                         2 s), written once a change settled; what the agent last read (launch, prompt,
                         app_context) and the sections changed since; SEAM for APIs and Structures
    project_outline.py   the outline gathered (build) and written as ARCHITECTURE.md at the project's top, only
                         when its bytes change (write); seams: UsedTables.used(project) (the tables the project
                         uses) and Portability.verdict(connection) (default: "Not checked yet")
    table_cells.py       every open table as its read-only cell's text (the grid's steps as one DuckDB
                         query); a document's Tables group arranged; where each table came from
    hooks.py             what an extension hands the base's services once built (late binding): the documents
                         the Workbench windows hold, a canvas, what stops with a kernel or a window, an app's
                         own file, the cells shown live, a new project's app; each a plain default with none on
    data_export.py       data.ipynb -> data.py (New project, Export data.py, the Streamlit extension's Save as)
    projects.py          projects: a new one, the files the Workbench opens, Export data.py
    sab_projects.py      a project is a folder: new (scaffolded in the projects folder or where named, opened,
                         .sab/ written), open (a folder; a plain one made a project on request; each table
                         read again with its steps; Visualizations, model, layout), save (.sab/, only changed
                         bytes; rows only on a tick, the agent's on the user's Allow), autosave (on by default,
                         once a change settles), Copy project to, close,
                         the recent list, a table's fix; unsaved changes worked out, not tracked; each open,
                         new and close points the dashboards at the project (scope); an older project's own
                         blades into the library as it opens (adopt)
    project_explorer.py  the Project Explorer: the cards (the local and shared projects folders' and every one
                         opened; each Local or Shared), sort and custom order (projects.json), both projects
                         folders (the agent's on Allow), Share (on Allow) and Make a local copy, rename,
                         remove from the list, locate; Show in folder and Delete (to the trash, on its typed
                         name) the user's only
    team.py              Settings' Team box: status, join, start, leave (the folders pointed and put back,
                         team.json), pull, push, show; the GitHub work is hooks.team's (the Git extension's TeamPort)
    library.py           the library: info, Settings' Library folder (the agent's on Allow), the notices said
                         once, an older project's blades taken in (the same skipped, `<name> from <project>`)
    shared_catalog.py    the shared catalog kept on the events (saved, listed, relationships, a project's usage),
                         pruned, the folder looked at for a pull's change (catalog_changed), a bad file left alone;
                         the listing, one table, the ERD's model, the Explorer's tables
    library_setup.py     Set up this computer: the vaults checked in child processes, the checklist, Move to
                         a vault
    project_scope.py     the open project's documents, and import: documents from another project folder or a
                         loose file into the project; an older project's connections and blades
                         into the library (services/library.py's take)
    inbox.py             what the user sends their agent (Send to the agent): memory only, read by the
                         prompt hook (client/context_hook.py) and the agent_inbox tool
    relationships.py     the Key Finder, compares, the current model and its library
    relationship_scope.py the tables the open project uses (open, its own, named in its documents' code):
                         what the ERD and the Relationships window draw by default (scope project or all)
    tieout.py            the tie-out report on a compare's two grids
    processes.py         Python sessions offering tables: the registry and the Open list
    snapshots.py         a PNG of the page, drawn by the page (app_snapshot); nothing is kept
    packs.py             list packs, make a marketplace, add saved blades and relationship sets to an editable pack

  adapters/              the driven edge: DuckDB, Arrow, files, the vault, websockets
    database.py          the locked DuckDB, the priority worker pool, DuckDB's own SQL grammar
    datasets.py          the dataset store and its limits; Arrow, CSV, Excel, Parquet, JSON loaders
    views.py             the view cache and windows
    catalogs.py          loaded catalogs: tree queries and search in the locked DuckDB
    blades.py            saved blades (the library's connections/, vaults/, blades/<name>.blade.py: one portable
                         file each, written only when its text changes), blade folders (.blade.py files found
                         by their header), an API's blades in apis/<name>/, favourites; secrets via keyring
    shared_catalog.py    the catalog/ folder's files: stamps, read, written atomically only when the bytes change
    team.py              a team's local copy and this library as files: hashes, copy, the layout written, show
    library.py           the library folder: where (library.json), README.md and .gitignore on first write,
                         counts, the one-time move of this computer's older stores (a dated backup), an older
                         project's .sab/blades read and dropped from its working folder
    blade_run.py         run a blade, its catalog command, a vault, in this Python (standard library
                         only: sab.blade uses it too); which packages this Python has
    codegen.py           runs copied code and compares it with the grid
    export.py            CSV, Excel and Parquet writers; the export folder
    state_files.py       the audit log, saved dashboards and themes, the connection file, the model library
    beta_log.py          the beta log's files: a writer thread, rotation (7 days, 20 MB), pictures, the zip
    connection_colours.py colours.toml (the library's), written only when it changes
    claude.py            Launch Claude's files: claude/<project>/ (its context.md atomically, only when changed),
                         claude.json, a Desktop config (backup first)
    updates.py           the release list's one GET, update.json, the helper's notes
    desktop.py           the desktop app's channel (127.0.0.1, a key, one JSON line each way), desktop.json, its
                         windows.json
    extensions.py        the installed extensions: entry points under `swissarmybench.extensions`, read at start;
                         SWISSARMYBENCH_EXTENSIONS (tests and development only)
    projects.py          a project's folder: made, listed, its own files read and written, zipped
    sab_files.py         a project folder's .sab/ files (written atomically, only when their bytes change),
                         the scaffold's Git files, its documents listed, Copy project to;
                         recent_projects.json (folders)
    project_explorer.py  projects.json, the projects folder scanned, a project's facts (.git/HEAD read as text,
                         never git run), Show in folder (the file manager), the system's trash, a rename
    apis.py              Add API: the OpenAPI document read (a file, an address; YAML with PyYAML), API_<name>.py written
    structure_files.py   Structures' files (read, written whole), YAML by PyYAML (else the missing-package
                         answer), records as an Arrow table for Open as grid
    variables.py         the Variables page's files (the library's variables.toml, shareable; local/variables.toml,
                         this computer's), the keyring (`variable/<NAME>`), the server's own environment
    live_updates.py      the pages' and VS Code windows' sockets (the app's windows counted for the server's life)
    folders.py           a folder's contents for the page's own picker (hidden ones on request), its places (Home,
                         Desktop, Documents, Downloads), New folder
    workbench.py         the Workbench's files (saved on the user's click), recent files, each document's Python
    intellisense.py      Jedi's Project and Environment per folder and Python, the project's modules read,
                         pyflakes, Ruff in the document's Python (on stdin; never installed by itself), DuckDB's parser
    packs.py             installed packs in Claude Code's plugin folder, editable ones in the blade
                         folders; writing a new marketplace and a pack's files

  server/                the HTTP door, and everything that starts a process
    app.py               asks bootstrap for the services, mounts the routes behind the guard
    http.py              reading requests, shaping answers, each error as its status in the one refusal shape
                         (domain/refusals.py; refusal(), error_as(); UTF-8; the guard, an unknown address and a
                         method not taken answer it too; cli/api.py reads a words-only one as its words)
    routes_*.py          one per feature: read the request, call the use case, shape the answer
                         (datasets, grids, analysis, regression, timeseries, tieout, agent, cards, catalog, blades, relationships,
                         processes, snapshots, packs, connections, apis, folders, workbench, table_cells, lineage,
                         projects, project_scope, project_outline, panels, navigation, kind_colours, script_runs, session_log,
                         structures, api_explorer, intellisense, sab_projects, project_explorer,
                         connection_swap, variables, connection_colours, connection_tables, explorer, library,
                         shared_catalog, team). Every route serves
                         the agent too (the golden rule) but answering approvals, /blades/{name}/python and a
                         project's Show in folder and Delete
    security.py          the guard: 127.0.0.1, the token, Host and Origin; each request told to the server's life
    beta_requests.py     the beta log at the door: slow requests by route pattern, errors with their route
    lifecycle.py, launcher.py, __main__.py   ports, single instance, clean exit; `swissarmybench`
                         (the app; open [folder] [--browser], start [--background] [--no-window], stop,
                         status, icon <file>; tray and autostart said gone)
    desktop.py           the desktop app from outside (no Qt): can it run, open a page in it (started when none
                         runs; else the browser), its status, `swissarmybench app`'s process (one at a time); a
                         grid nothing shows (show: the running server's fallback), a file opened with the app
                         (hand_file over the channel; file_page: what the server is asked, the page shown), the
                         app's quit (`swissarmybench stop`)
    desktop_shell.py     the desktop app (PySide6): windows, the persistent profile, window.open, outside links to
                         the browser, downloads, Print to PDF (afterprint once the PDF is written), permissions,
                         keys (the page's first), Open in browser, a file handed over the channel or dropped on a
                         window (its real path), the channel's quit, the server it starts (off the window
                         thread; Starting… meanwhile) and tells when its last window closed
    legacy_tray.py       an older version's tray and start-at-sign-in entry, removed once (said once)
    updater.py           Update to X's helper: a copy run by the base Python once the app stopped, it
                         installs with uv, checks the version, starts the app, or the old one and a note;
                         Install and Remove an extension the same way (launch_change)
    routes_updates.py    the update check, its switch, Update to X
    routes_lifecycle.py  GET /lifecycle (app_lifecycle), POST /lifecycle/closed (the app's)
    routes_desktop.py    GET /desktop, POST /desktop/open (desktop_status, desktop_open)
    routes_claude.py     Launch Claude (GET for the agent too; PUT and the launch the user's only)
    dialog_runner.py     the system's file dialog in a short-lived child process: one at a time, ten minutes at
                         most, the start folder the nearest that is there; GET /dialogs says whether one opens
    claude_finder.py     finding Claude on each system (registry, PowerShell, mdfind, .desktop files) and
                         starting it detached; SWISSARMYBENCH_CLAUDE_STANDIN's stand-in for tests
    blade_runner.py      Refresh/Test in a child process; installing packages
    kernels.py           the Workbench's IPython kernels (jupyter_client): run, complete, inspect, interrupt
    environments.py      making a notebook's environment (uv, else venv and pip); the client lent to kernels
    streamlit_proxy.py   live pages passed through this server under their own secret (their websockets too),
                         so a page's frame policy stays `frame-src 'self'`: the Streamlit extension's apps and
                         the Power Apps extension's dev server mount it with their own prefix
    script_runner.py     Run as scheduled: `python <script> <arguments>` as a fresh process with no app
    blade_templates.py   the 40 starter blades (3 analyses; a Power BI workspace: code that signs in, lists
                         its datasets and sends DAX to one, each dataset shaped like a database connection)

  starters/              the built-in starter pack (136 read-only .blade.py: Power BI, Dataverse, SharePoint, Excel, Files,
                         DAX, HTML, Markdown, Write; the Streamlit extension brings its 52), listed apart, found by name, Copy as your own (tests/test_starters*.py);
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
  client/kernel_intel.py Jedi's answers (the member list, signatures, hovers): its Interpreter over a kernel's
                         namespace, asked in the kernel; its Script the server runs where no kernel has
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
                         (the rail's first item: home, the Projects page; another window brings the home window,
                         named sab-home, forward showing Projects; Alt+Home),
                         views in the address (go: pushed for the user's moves, replaced for the app's; Back
                         and Forward are the browser's), layers (a dialog with views of its own, open=<key>:
                         Settings, Connections), every other dialog an entry Back closes, backButton (named
                         for where it goes), crumbs, setTitle (the page, then the place), app_navigate;
                         rail.ts is the slim icon rail down the left of every page and window, in the order of
                         the work (the owner, 2026-11-17; APIs beside Connections, 2026-11-18; the red mark first,
                         Projects, and 24px icons so more fit, 2026-11-18): Projects, Connections, APIs, Variables, Data, Grids, ERD, Structures,
                         Blades, Notebooks, Scripts, Apps, Visualizations, Session, Settings at the
                         bottom: a click is a nav.ts move in this tab, and every icon lands on a page (no
                         dialog, no menu); the current area marked; Open in a new window on request; always
                         there (no switch), and the top tabs and the Application row no longer repeat its
                         areas (the owner, 2026-11-16); extensionsPage.ts the Extensions page (open=extensions,
                         above Settings: a card per extension, Install's progress through the restart);
                         library.ts Settings' Team box (Join a team…, Start a team…: one dialog of steps; the
                         Joined row: Pull, Push, …; Advanced: the two folders; Set up this computer) and the
                         notices said once (the move, a team library, a pull's catalog change; a kept step
                         opens Settings on the flow); areaPage.ts is a page of the rail's over any page
                         (Settings, Connections, Session: open=settings, open=connections, open=session; Projects
                         over the home page only, open=projects); projectsPage.ts the Projects page (the rail's
                         mark, 2026-11-18: the Project Explorer and the tour; the app opens on it with no table and
                         no project; /workspace?view=start lands on it; it makes way for a project opened there or
                         a table that arrives); variablesPage.ts the Variables page (open=variables:
                         by source, uses, Add variable, Show for a keyring secret; the key vaults and Add key vault); dataPage.ts the Data Catalog page (open=data, the rail's Data Catalog, after Variables on the rail: the one place to browse and find tables, dataBrowse.ts its tree and a table's detail); sessionPage.ts the Session page
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
                         tour.ts is the first-time tour (on the Projects page only: a card per
                         place in the rail's order that goes there and lights up the real control,
                         two made-up tables staged and closed again, back to where it started; then
                         a matching game; nav.ts returnTo);
                         catalogRail.ts (the blades list; the catalog tree only where a page gives it a
                         place: the Workbench's "+ Table") is the blades page's (catalogPage.ts,
                         static/catalog.html: no catalog panel since 2026-11-17); bladeEditor.ts is the
                         blade screen (the code read-only, Show its file, Its table is called, a
                         connection's How its tables are listed) and New blade;
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
                         variableBox.ts `${NAME}` in any box (12.7): typing `${` lists the variables (names and
                         sources in words), `{x}` the same, the line under the box (previewLine: the value, a secret
                         masked, or the one error with Set it); variableLinks.ts Set it's and New variable…'s Add
                         variable form, over the page; variableAnywhere.ts the same list in any text box of the
                         app (typing `${`; right-click: Cut, Copy, Paste, Insert variable…; search boxes and
                         `[data-no-variables]` left alone) and `globalThis.sabVariables` for SQL editors;
                         fileChooser.ts picks real paths: the system's own dialog first (GET /dialogs, POST
                         /dialogs/choose; nothing of the page's shows), else the page's own picker (places,
                         recent folders per kind, breadcrumb, filter, New folder, hidden files, the keys). missingPackages.ts is the one missing-package
                         prompt ("<Feature> needs <package>": Install now, Not now; the reminder after
                         Not now, no nagging this session), used by every place that finds one;
                         loading.ts the one loading state (design principles 8.12, 2026-11-18): busy(host, words,
                         work, {abort, onCancel, errorIn}) gates an element (inert, aria-busy, a cover over its box
                         after 150 ms with a spinner, the words at the body's size, the time after 3 s, Cancel, the
                         error in place), loadingBlock(words) an empty area's placeholder, busyButton/busyClick a
                         button busy until its work ends, markBusy a button drawn busy from a view's own state; no
                         page has loading text of its own; errorNote.ts the one error component (9.5): the word
                         and icon, what happened, where, the fixes as buttons, Details folded with Copy, Send to the
                         agent; showError/clearError in place; errorHere (in place where the last action was: the control's row in its
                         card, panel, form or dialog, a floating note under a page bar, a menu item's opener;
                         pressed again, it goes); errorToast the same note in a toast with Show (background work
                         only); errorMark its inline form for one-line rows; problemsHere several as one; toast()
                         is info only; ApiError carries the refusal (`said`, saidOf); The Workbench (static/workbench.html, its own
                         window): workbenchPage.ts (composition: the top row, each group's controls, the
                         status bar), workbenchLayout.ts (RStudio's panes: the groups, the console,
                         Variables, both closed until the status bar opens them; splitters; F1 help as a
                         card; pictures go to Visualizations), workbenchGroups.ts (tab groups as VS Code's
                         editor groups: drag to reorder or split with the five-way guide, splitters, the
                         layout as data for the session restore; the tab kind registry, registerTabKind,
                         where app pages are added; the canvases' New entries follow the mode),
                         modes.ts (the open project's mode as the backend declares it: canvases offered,
                         families shown first with Show all, New <type> project), canvasKit.ts (what the
                         canvases share: Undo/Redo, the page tabs, the resize grip), excelCanvas.ts (the
                         Accounting extension's Excel canvas: workbook.design.json, blocks on a grid of
                         cells, Properties, Play, Download, Export workbook.py), excelPreview.ts (a built or
                         imported workbook's sheet drawn, its charts), excelTemplates.ts (templates bound by
                         clicking cells; statements: dry run, Build, register), workbenchExplorer.ts (the Data Explorer pane, which
                         replaced the Data panel (2026-11-17): left, resizable, off until Ctrl+Shift+E, per
                         window; a project's files at its foot (setFiles); "+ Table" and "+ Blade" open
                         catalogRail.ts beside it; Pop out), dataExplorer.ts (the Data Explorer itself, one
                         component for three hosts: the Data Catalog page (dataPage.ts, open=data: the one place to
                         browse tables, its tree and detail side dataBrowse.ts; the pane's Pop out opens it; /workbench?panel=explorer redirects to it), the pane, the
                         grid page's Find data dialog (Ctrl+K, gridCommands.ts): one search, chips, a
                         connection picker, recent searches, each result's actions, its drag
                         (EXPLORER_DRAG: lazy/codeEditor.ts drops the cell's language's code)),
                         workbenchCellsPane.ts (App mode's Streamlit cells panel: every cell that calls
                         Streamlit, by name: dragged onto a canvas), workbenchMenu.ts (its drop-
                         down menus), workbenchAgent.ts (right-click, Send to the agent),
                         workbenchCommands.ts (every window action by one name: the palette, the keys, and
                         the agent's workbench_window), workbenchNotebook.ts (cells, Jupyter's command
                         mode), workbenchScript.ts, workbenchConsole.ts (each document's console),
                         workbenchKernel.ts (runs), workbenchOutputs.ts (outputs drawn as they arrive:
                         colours, `\r`, caps, input boxes), workbenchErrors.ts (the error panel: Visual
                         Studio's Exception Helper; squiggles, hover cards and Ctrl+. fixes in the editor),
                         workbenchCompletion.ts, workbenchIntel.ts (the editors' intelligence: the member
                         list with its documentation panel, parameter info, quick info, the lint as you type,
                         the status bar's Problems count and list, the Ruff offer), workbenchEnvironment.ts,
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
                         outside one plain: notebookRole, kindIcon);
                         projectFile.ts a project as a folder, shared by the home page and the Workbench
                         (open a folder, "Make this folder a project?"; New project's dialog: name, type, "?"
                         for the types explained, where; save, Keep its rows asked once; Copy project to…;
                         close; a table's fix; the ● mark; Export outline: ARCHITECTURE.md, then Download);
                         projectTypes.ts the types for
                         beginners (their words from the backend, our own drawn pictures); projectExplorer.ts
                         the Project Explorer, drawn on the Projects page (cards marked Local or Shared, sort and dragged custom
                         order, filters, the types strip, the empty state, a card's menu: Share, Make a local copy;
                         the Team box's local projects row and Advanced's shared projects folder);
                         projectImport.ts the import dialog (documents, connections, blades: from another
                         project folder, a file, this computer);
                         startView.ts the grid page's Grids landing (/workspace?view=grids: no table open, a
                         project open or not: Open a file, Paste, Query, the connections, the project's tables to
                         fix, and with no project a link to Projects; the Start view left for projectsPage.ts,
                         2026-11-18), the project's group in the
                         Application row (Save, Copy to…, Close, Autosave) and the strip of tables to fix;
                         connectionColours.ts each connection's colour worn by whatever names it
                         (data-connections: tabs, cells, blocks, cards, the Data Explorer's results, Session entries), the
                         swatch and palette; panes.ts groups the home page's tabs by connection;
                         swapConnection.ts the Table row's Connection: <name> (a table read from another
                         connection, its steps kept: the chooser, the other's catalog to pick, the SQL window
                         ?panel=connsql for a query), the strip's Use another connection… and its Undo rows,
                         Point these at <name> (the cells that named the old one, ticked);
                         updates.ts the status bars' "Update available" (Update to X, What's new) and
                         Settings' Check for updates; desktopApp.ts is the page in the desktop app (window.sabApp:
                         the browser's keys are the app's there, Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+Tab, Ctrl+Shift+T;
                         closeWindow); fileChanged.ts a table whose file changed on disk (its tab's dot, its
                         pane's Changed on disk: Reload, Not now);
                         claudeLaunch.ts the status bars' Launch Claude (one found: straight to it; both: a
                         menu; none: the install help), Desktop's one question, Settings' Claude;
                         the Workbench's modes: workbenchModes.ts (each document's own panels beside it
                         in its group, the status bar's toggles), workbenchApp.ts (App: Properties, page
                         settings, State), workbenchStarters.ts (App mode's Starters panel: the gallery),
                         workbenchDocModes.ts (Notebook's Outline, Script's Run settings and Run history,
                         Data's Dictionary and Lineage's place); the canvas's selection, wiring, undo,
                         align, duplicate, zoom and Play's preview are in workbenchCanvas.ts
                         The grid page has no SQL box and no steps panel (decision 13): stepsStrip.ts is the
                         strip under the title; stepsPanel.ts shows only in its own window (?panel=steps)
web/static/              index.html, grid.css (all theme tokens), build/ (gitignored); design.html is the
                         page an HTML cell's design is drawn in (sandboxed; its policy loads nothing
                         over the network)
tests/                   unit + HTTP tests, golden/ (shared cases), e2e/ (Edge via Playwright),
                         desktop_drive.py (the desktop app really run under Qt off screen: windows, downloads,
                         Print to PDF, outside links, the server stopping with it; test_desktop_shell.py runs it),
                         copilot_standin.py (GitHub's Copilot Language Server stood in for: stdio LSP, a made-up
                         device flow and made-up suggestions),
                         test_architecture.py (the layers, the depth, the plain client),
                         lake_standins.py (Entra, the ADLS Gen2 DFS API over a made-up lake, OneLake, and Graph
                         for a made-up SharePoint site, all on 127.0.0.1),
                         trino_standin.py (a Trino over HTTPS asking for a client certificate; made-up
                         keystores), powerbi_standin.py (Power BI and its sign-in stood in for on this computer: a
                         workspace of three made-up datasets), dataverse_standin.py (a Dataverse environment's
                         Web API, its metadata and its sign-ins: a made-up company's accounts, contacts and
                         opportunities), dataverse_tds_standin.py (its SQL endpoint at python-tds's seam: a
                         made-up SQLite file), test_sql_server_real.py (a real SQL Server when
                         SWISSARMYBENCH_SQLSERVER_TEST names one), orders_service.py (a made-up web service
                         on 127.0.0.1, for a Python connection), api_standins.py (Add API's made-up
                         orders service, every sign-in it takes stood in for), github_standin.py (GitHub's REST
                         and Git Data APIs and the device flow over in-memory repositories of made-up files)
tools/                   screenshots.py, vscode_check.py; testbed/: the real-world test bed (testbed.py up|down:
                         PostgreSQL and MariaDB on ports of their own, made-up files; company.py, the made-up
                         company; standins.py, Power BI's Company model and Azure Key Vault) for
                         tests/e2e/test_real_world.py (eleven use cases, action counts, agent parity)
plugin/                  the swissarmybench plugin: skills/swissarmybench-use (SKILL.md, guide), .mcp.json,
                         hooks/hooks.json (the prompt hook: what was sent to the agent, the table in front)
.claude-plugin/          marketplace.json: this repository is a Claude Code marketplace (plugin/ and the pack)
examples/sample_store.py made-up nine-table store with a relationship answer key (test bed for autodetection)
examples/packs/          sample-store: an example pack (a made-up blade, the store's relationship set)
build.py                 build the page (release) and the one wheel; --vsix also packages the extension
installer/               install.sh and install.ps1 (uv, then the server as a uv tool); build.py stamps the version
.github/workflows/       release.yml: a v* tag builds, tests the installers on Linux and Windows, publishes
tools/smoke_install.py   start the installed server, push the sample store, check it all arrived (used by releases)
extensions/accounting/   the Accounting extension (swissarmybench-accounting, its own wheel on the base's version):
                         src/swissarmybench_accounting/ runtime.py (the one workbook builder: Play runs it, Export
                         writes it into workbook.py; pivots by DuckDB's GROUPING SETS, Excel's own charts,
                         templates filled, build_statements), design.py and templates.py (rules), exporter.py
                         (workbook.py's text), files.py (files, the preview), service.py, routes.py (/accounting),
                         commands.py (workbook_, template_, statements_), extension.py (describe, MODE, routes,
                         scaffold); tests in tests/test_accounting_*.py with tests/accounting_data.py (a made-up
                         reinsurer's cessions)
extensions/streamlit/    the Streamlit extension (swissarmybench-streamlit; entry point streamlit =
                         swissarmybench_streamlit.extension; project type streamlit), PREINSTALLED: the installers
                         and each update install it beside the base (an update from a built-in version brings it
                         back once at its first start, extensions.json: never against the user's Remove). Without
                         it the app is the BI base: no Apps area, no Streamlit canvas, its tools and its door say
                         which extension they need. tests/conftest.py puts its src on the path and switches it on
  src/swissarmybench_streamlit/
    extension.py         ID, NAME, ADDS, MODE (the Streamlit project: canvas, families, tools), BASE_MODE_ADDS (its
                         canvas in a BI project too, as before), STARTERS, SECRET_PATHS; routes(services) its
                         composition root (fills the base's services/hooks.py); stop; scaffold (app.ipynb, the
                         canvas); project_app (a BI project's canvas)
    commands.py          the agent's streamlit_* tools and the Workbench's canvas and live-cell commands
    domain/streamlit_cells.py  a Streamlit app: its file (sales.stapp.json: pages, blocks, links; no code), a link
                         against the app's file, the 12-column grid (rows, settle), the run order (a cycle said), a
                         page as ONE Streamlit page (slots first, blocks in name order, widget keys of their own),
                         the tables' preamble, the export, the saved pages (pages/*.py), a canvas's references
    domain/controllers.py  a cell as a controller: its contract (the header's `# Makes: region: str = "All";
                         by_region: table = orders`, read with ast), role, widgets, query parameters; a page's
                         defaults for a maker not on it, its check; Test this page's plan, its AppTest runner
    domain/thin_cells.py a view cell's model work and its move to a named cell of data.ipynb
    domain/app_settings.py  App mode: a Streamlit app's page settings (st.set_page_config, st.logo,
                         .streamlit/config.toml); the live page's session state for the State panel
    services/streamlit.py  Streamlit apps: a canvas (pages, blocks: place, move, resize; its linked cells read
                         from the open documents, saved or not, else from the files), a document's live cells;
                         run (the tables as Parquet in a temporary folder), state, install, export, Save as
    services/streamlit_ports.py, streamlit_documents.py  the ports; a document's cells as an app reads them,
                         and an app's own file for the Workbench (AppFile)
    services/controllers.py  a canvas page's controllers: the check, Test this page, a thin cell's move plan
    adapters/streamlit_files.py  a Streamlit app's temporary folder (removed when it stops), and an export's
    server/streamlit_apps.py  a notebook's Streamlit process: `streamlit run` in the notebook's own Python,
                         127.0.0.1 only, ended with the server (Streamlit is never the app's dependency); Test
                         this page's runner, in that Python (`python -I`), in a temporary folder
    server/routes_streamlit.py, routes_controllers.py  /streamlit/* (and the live pages, /streamlit/live/<key>/)
    starters/            the Streamlit, Components, Controllers and Text and layout starters (52)
extensions/git/          the Git extension (swissarmybench-git; entry point git = swissarmybench_git.extension; no
                         project type: a rail area, RAIL, and the footer's mark): GitHub sync and the Source Control
                         page, through GitHub's web API (no Git on the computer)
  src/swissarmybench_git/
    extension.py         ID, NAME, ADDS, AREAS (github_, scm_), RAIL ({area: scm, mark: /git/mark}), CLIENT_ID (the
                         device flow's OAuth app, empty until the owner registers it), SESSION_RULES; routes(services)
                         its composition root (the folders from the library and the Project Explorer, Allow, the
                         shared catalog read again after a pull); SWISSARMYBENCH_GITHUB_API/_WEB name a stand-in
    commands.py          github_status, _repositories, _clone, _connect, _disconnect, _pull, _push; scm_changes,
                         _stage, _discard, _commit, _sync, _history, _commit_files, _diff, _branches, _checkout
    domain/sync.py       git's blob SHA, .gitignore's patterns and the app's own exclusions, a folder's link, a pull's
                         plan, the line-based three-way merge (diff3 on difflib), a push's secrets, the words,
                         VS Code's groups and letters (merge, index, workingTree: M A D U !), unified diff text
    adapters/github.py    GitHubClient (urllib: user, repositories, refs, trees, blobs, compare, commits, branches, the
                         Git Data API's writes, the device flow), GitHubToken (the keyring), SyncLinks (sync.json),
                         SyncFolder (a folder's files walked, written atomically), known_secrets (the keyring's values)
    services/sync.py     GitHubSync: sign-in (token, device flow; the user's only), status (remote at most once a
                         minute), clone, connect, disconnect, pull, push (fast-forward, scoped to a project, named
                         paths), the footer's mark; a shared projects folder inside the team library synced by its link
    services/team.py     TeamPort: what the base's Team box asks (hooks.team): sign-in state, repositories, owners, a new
                         repository, the local copy (clone, or pull), its first push, status, pull, push
    services/scm.py      SourceControl: the page's repositories and groups, stage, discard, commit, sync, history, a
                         commit's files, the diff's two sides, branches, checkout and create
    server/routes.py     /git/*
web/src/scmPage.ts       (a plug-in) the Source Control page: VS Code's view (repositories, the message box, Commit and
                         its menu, the groups, inline actions, menus, list or tree), the graph, Monaco's diff editor
                         and the files beside it, the welcome and GitHub sign-in, Clone and Connect's quick picks;
                         the Team box's sign-in step (teamSignIn); a shared card's Pull, Push and words; Share's "Push it to GitHub
                         now?". scmGraph.ts the graph's swimlanes (ported from VS Code's scmHistory.ts, MIT)
web/src/areaMarks.ts     the footer's marks an extension's area answers (GET /app/areas' mark route), generic
vscode-extension/        the optional VS Code extension (TypeScript): the uv install's MCP tools as VS Code tools,
                         and an Open Swiss Army Bench button (starts the server when needed, opens its window)
extensions/powerapps/     the Power Apps extension (swissarmybench-powerapps; entry point
                         powerapps = swissarmybench_powerapps.extension; project type codeapp): Power Apps code
                         apps built with Microsoft's own command lines (pa for the app, pac for environments and
                         custom connectors); docs/ideas.md "The Power Apps extension, phase 1" and "phase 2" (the data
                         notebook: TypeScript, SQL and TSX cells on Deno's kernel and one DuckDB, data.ts)
  src/swissarmybench_powerapps/
    extension.py         what the base reads: ID, NAME, ADDS, MODE (the code app mode as data), AREAS, routes,
                         commands, STARTERS, SECRET_PATHS, SESSION_RULES, stop; its composition root
    commands.py          the agent's powerapps_* tools (Push, a custom connector, an install wait for Allow)
    domain/cli_lines.py  each action's command line (every value checked: one line, no option, never a secret)
                         and each command's output read (JSON, pac's tables by their headings)
    domain/tools.py      Node.js, npm, pa, pac, .NET, Deno: versions, each system's install, the missing answer
    domain/project.py    a code app's folder: power.config.json's sources, the generated files, the tree, the
                         .sab/project.json type
    domain/connectors.py a connector in the APIs explorer's model (read-only), custom connector files from an
                         OpenAPI document (Swagger 2.0, the sign-in as connection parameters, no secret)
    domain/ts_notebook.py the data notebook's kernel (phase 2): the `sab` prelude (DuckDB's Node package: sab.sql,
                         sab.table), a SQL cell as `await sab.sql(...)`, the open tables' views, a result's id,
                         outputs cleaned, an error as the panel's detail, the editor's declarations
    domain/shown.py      the files a code app lists: src/App.tsx, src/pages.ts, src/pages/**, src/shared/** (.ts/.tsx);
                         the rest stays in the folder (Show all files)
    domain/pages.py      pages, each owning everything it needs (src/pages/<Page>/: page, components, hooks,
                         state, types, index), the list of pages (src/pages.ts), the starter files (src/shared,
                         the Accounts page, App.tsx's switcher), the rule: a page never imports another page
    domain/data_ts.py    data.ts from the TypeScript cells (exported declarations, kernel cells left, npm: imports
                         plain, row types from DuckDB's types)
    domain/tsx_preview.py a TSX cell drawn: its props line, the bundler's deno.json (the project's own React), the
                         one page for the HTML cells' frame (FRAME_POLICY)
    services/notebook.py the data notebook: a Deno kernel per notebook (its temporary folder), runs, the open
                         tables as Parquet views, a connection's tables (the kernel's key route), Open as grid,
                         data.ts and Use in app, TSX previews, Dataverse sources into grids
    services/powerapps.py the use cases: runs (streamed, kept for the session, audited), sign-in, environments,
                         new and open, sources, connectors, Run live, Push, versions, custom connectors
    adapters/runner.py   child processes (time limits, lines as they come, stdin closed), a free port
    adapters/files.py    the code app's folder, the connector files, powerapps.json (the last code app opened)
    adapters/deno_kernel.py Deno's Jupyter kernel through jupyter_client (127.0.0.1, signed; DENO_NO_PACKAGE_JSON)
    adapters/notebook_files.py the notebook's temporary folder, Parquet read and written
    adapters/environment_api.py  a connector's definition from the connectivity service (pac's token, in memory)
    server/routes.py     /powerapps/* and the dev server's live pages (/powerapps/live/<key>/, the live proxy)
    starters/            TypeScript and React snippet starters (families TypeScript, React, Connectors)
extensions/copilot/      the GitHub Copilot extension (swissarmybench-copilot; entry point copilot =
                         swissarmybench_copilot.extension; no project type): Copilot's ghost text in the Workbench's
                         editors through GitHub's Copilot Language Server (npm @github/copilot-language-server,
                         MIT, pinned; installed by the extension into the state folder's copilot/, run by Node.js
                         20.8+); off until installed and signed in; nothing sent for a project marked private
  src/swissarmybench_copilot/
    extension.py         ID, NAME, ADDS, INLINE_COMPLETION (the editors' routes, as data), PANEL (its card's and
                         Settings' panel route), AREAS, SESSION_RULES, routes, stop, commands
    commands.py          copilot_status, copilot_toggle, copilot_install (Allow); sign-in is the user's only
    domain/lsp.py        the protocol: Content-Length framing, initialize, telemetry off, UTF-16 positions,
                         incremental changes, inline completion's parameters and items, signIn/checkStatus read
    domain/documents.py  the documents mirrored into the server: a script as a text document, a notebook as a
                         notebook of its code cells (made-up file:///swissarmybench/<key>/ addresses)
    domain/tools.py      Node.js and npm (the Power Apps extension's install commands and missing answer), the
                         pinned npm install
    adapters/language_server.py  the server as a child process (stdio; its logs dropped), the install, the
                         stand-in (SWISSARMYBENCH_COPILOT_STANDIN: tests/copilot_standin.py)
    services/copilot.py  one server per app: start, sign in (device flow), the On switch, private projects,
                         complete, cancel, shown/accepted/partial, the panel as data
    server/routes.py     /copilot/*
web/src/inlineCompletion.ts ghost text from the provider the mode declares (`inline_completion`: its routes): the
                         ask (cancelled with Monaco's token), the shown/accepted/partial report, the status bar's
                         "Completions: <name> · on/off" (a click toggles); lazy/codeEditor.ts registers Monaco's
                         inline completions provider for Python and SQL (an editor's `inline: inlineSource(...)`)
web/src/extensionPanel.ts an extension's panel drawn from its data (lines, switches, actions, a code and a page to
                         open): on its Extensions card and in Settings; projectFile.ts privateSwitch (the project
                         group's Private: POST /project/private)
web/src/codeAppPage.ts   (a plug-in) the rail's Code App page: tools, sign-in, project, connectors (the APIs
                         explorer's look), Run live's pane, Push, custom connectors, runs; shown while on
web/src/routedCells.ts   a cell another kernel runs, by the routes the mode declares (MODE cell_routes): a run's
                         stream, a TSX cell's page, Open as grid of a table result, the editor's declarations
web/src/workbenchCodeFile.ts (a plug-in) a code app's file in the Workbench's editor: Monaco's TypeScript
                         service (ts.worker.js) over the project's files; New TypeScript file in the code app mode
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
