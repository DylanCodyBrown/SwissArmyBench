# CLAUDE.md — Swiss Army Bench

A desktop app (PySide6: each page a window, drawn by Qt WebEngine) over a local Python server (Starlette +
uvicorn + in-memory DuckDB) that lives while the app is open: tabular data in live AG Grid pages, with steps,
profiling, SQL, export, verified code generation, charts and an MCP door for agents. The owner, 2026-11-18:
"Change that to the primary install. It's not an extension it is the app framework now and it should have been
since the start." The browser stays possible (`swissarmybench open --browser`), secondary. It runs only on the
user's machine. This repository is the whole product: the Python package at the root and its page in `web/` (the VS Code
extension went 2026-11-21, the simplicity pass).

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
  Write only the new names; the old ones are no longer read (removed 2026-11-21, the simplicity pass; README
  "Renamed from SwissArmyGrid"). The GitHub repository is DylanCodyBrown/SwissArmyBench (renamed; the old address redirects).
- **Renamed (the owner, 2026-11-16):** the Sandbox is **Visualizations** and the Diagram the **ERD**
  (`?view=erd`); both old names were removed 2026-11-21 (the simplicity pass). Internal names (aiPanel.ts, sandbox*.ts, the `agent` view, CSS classes) kept the old word.
- **Renamed (the owner, 2026-11-19): Visualizations is Analyze, and the analyses live there** ("Let's move the
  analyze from the table bar to the visualizations pane and then rename the visualizations pane Analyze" /
  "Every analysis should automatically push to the analysis visualization area" / "make it stupid simple";
  design principles 8.7 and 8.13). The Analyze page has a toolbar of every analysis and one guided form beside
  the board; every result lands on the board by itself; the grid page has no analysis on it (no Analyze menu,
  no Fit test or Outliers on a header, no Tie-out on the Compare row; Compare, the quick Profile and the Key
  Finder's window stay). **Each analysis has one data contract** (domain/analysis_contracts.py) that the form,
  the column picking, the made-up sample, the fixes ("Make it fit": grid steps, never applied by itself), the
  ranking (Check this table), the agent (`analyze_contracts`, `analyze_check`, `analyze_plan`, `analyze_run`)
  and Python (`sab.analyze.<analysis>(df)`) all read through one checker (domain/analyze.py). Write `analyze_*`,
  `sab.analyze`, `?view=analyze` (the chart's code is `analyze_chart_code`). The old names (`visualizations_*`,
  `sandbox_*`, `sab.visualizations`, `sab.sandbox`, their addresses and project.json keys) were removed
  2026-11-21 (the simplicity pass). Files on disk and internal names kept the old word
  (`.sab/visualizations.json`, client/visualizations_client.py, aiPanel.ts, sandbox*.ts).
- **What a connection is (the owner, 2026-11-17): "any connection ... exposes tables that we can write
  duckdb against" / "that is the definition of a connection here".** Every connection kind lists its tables
  and reads one through one contract, and DuckDB SQL names them by the connection
  (`SELECT * FROM [Finance Captive].model_Report`). A thing with no tables (a key vault) is not a connection.
  Connections, APIs, vaults, blades and variables are this computer's library, shared by every project and
  made to be a Git repository (Plans/library.plan.md; the owner, 2026-11-17): the **library** folder, below. An
  API lives in its `apis/<name>/` (API_<name>.py, the API blade, its web call blades, openapi.json, source.json);
  an API's tables are its web calls with Return as table on, and it is not on the Connections page. Key vaults
  are added and listed on the Environment's Settings and secrets tab, not the Connections page.
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
  Extensions page lists the extensions (Streamlit preinstalled; Accounting, Power Apps, Power BI and GitHub Copilot available, one click: Install). Until the manifest boundary is built (Plans/powerapps-spinoff.plan.md section 8a), front-end work
  continues as before; from then on, the rule holds.
- **A blade's screen is an IDE (the owner, 2026-11-21: "this entire panel should be an ide, with small save,
  saves, cancel buttons at the top and a play button to execute with a realtime linter and output at the bottom
  to see the results. This is an IDE not a save form"; it reverses 2026-11-17's read-only code).** One slim bar
  (Back, the name, the dirty dot, Save Ctrl+S, Save as…, Cancel, ▶ Run F5, Properties, "…": Show its file,
  Export, Remove, Copy as your own), Monaco with the Workbench's intelligence, Properties (name, description,
  tags, `table` checked live: GET /blades/table-name) closed until asked for, Output | Result | Problems folded
  until something runs (design principle 8.14; web/src/codeIde.ts). **The code's bytes are the file's:** Save
  writes the code after the file's header (PUT /blades/{name} {code, stamp}; only when the bytes change; the
  header's variable follows a renamed function); an edit made outside is noticed (the stamp, looked at every
  2 s: taken at once with nothing unsaved, else Reload / Keep mine; a Save over it is 409), never silently
  overwritten. A starter's Save is refused: Copy as your own. Run is Test's child process with the
  output streamed (POST /blades/{name}/run), the result a table (Open as grid) or a value, a failure the error
  panel with the line marked. The agent: `blades_update(code, stamp)`, `blades_run`, `blades_problems`,
  `blades_copy(code)`; Show its file stays the user's click (403 for the agent). The catalog checkbox and the
  blades page's catalog panel went ("what the heck does add to catalog do" / "we dont even need catalog if its
  just tables"): a connection's tables are always listed (a missing listing query is its starter's, on read).
- **Two things: the app and the project scaffold (the owner, 2026-11-22; design principle 12a).** The app is Swiss
  Army Bench itself (`src/swissarmybench/`, `web/`, `extensions/`, the library); the project scaffold is what it writes
  into a project folder and an export carries (`adapter.py`, `connections.py`, `API.py`, `data.py`, `data.ipynb`,
  `requirements.txt`, the type's deliverable, the sandbox mirror) and must run without the app. Say which one a change
  is about. **adapter.py and api_adapter.py are the most valuable files** (the owner: "the single most valuable piece of
  code here" / "the api_adapter is equally important ... a way to adapt duckdb and any API to a simple ready to go set
  of front end functions"; design principle 12b): everything above them calls only their plain functions; each one readable file, standard library + duckdb + pyarrow only, its contract changed only by
  adding (a break is the owner's call), its own version and change list, every change tested against every backend
  with the memory and speed numbers recorded, and committed on its own.
- **What SAB is for:** Python-to-DuckDB work on one screen instead of three. SAB brings Python's
  power (analysis, fast data); **DuckDB SQL does the transforming**. Generated transformations are
  DuckDB SQL over the user's own table, never a pandas translation.
- **Where it is going:** [Plans/standalone-workspaces.plan.md](Plans/standalone-workspaces.plan.md):
  a one-command installer that sets up everything; one local server with separate workspaces
  (`sab.create_workspace()`); code goes in the **Workbench** (our own notebooks and scripts on an
  IPython kernel, [Plans/workbench-and-connections.plan.md](Plans/workbench-and-connections.plan.md)),
  Jupyter or Python in the terminal (marimo was built in, then stripped on the owner's call, 2026-11).
  **Rule: code always opens in its own browser window, never in the grid page**, so it can sit on another
  screen. **Notebooks and Scripts are two pages** (the owner, 2026-11-21: "notebooks and scripts should not reuse
  the same page they are seperate things"): /notebooks (the window sab-notebooks: notebooks, and an app's canvas
  beside them) and /scripts (sab-scripts: every .py, never a notebook), each its own explorer on the left, tabs,
  session and layout; a file opens on its kind's page from anywhere, a wrong-kind take is refused in one line
  (domain/workbench_pages.py, web/src/workbenchPages.ts); /workbench redirects. **The Scripts page is a Python
  IDE** ("this is meant to expose the high level code of everything in the app for fine tuning"): Files (the
  project's scripts by module with outlines, Project code, the library's Connections, APIs, Key vaults, Widgets;
  Generated, read-only, with Fine-tune as a script) above Blades (a blade opens as a tab: bladeDoc, the blade
  IDE's seam); F12, Shift+F12, F2, Shift+Alt+F, Ctrl+Shift+F, F11 full screen, Ctrl+B; every code file
  follows a change anywhere (the file_changed notice); a made file saved by hand is kept from a regenerate; saved workspaces; the desktop app (PySide6 windows,
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
  completion, one Python session and one `.venv` a project, a loose file's own environment), every table's read-only cell there (its transformations as
  one DuckDB query, the Tables group, cell numbers, `@cell` links, the uses line; the copy buttons
  left the grid's steps strip), HTML cells (a design drawn from a cell's HTML in a walled-off frame,
  `{{ name }}` filled from the kernel), widgets and the Canvas (2026-11-21: a widget is the library's `widgets/<name>.widget.py`, its top-level
  values its properties with masks; the Widgets window writes and runs one; the Canvas lays pages out from
  containers and widget instances in pixels, rule-checked and undoable; Play, Launch, Export from one builder;
  Launch with the Performance Analyzer, Builds' Compare and Restore; a table property takes `[Conn].table`;
  app notebooks, `.stapp.json` canvases, live cells and controllers went),
  projects (a folder: data.ipynb and its export data.py, the canvas), named
  cells, the Data Explorer (one search over everything that holds data, in the Workbench's pane, its own
  window or the grid page's Ctrl+K), tabs that pop out into windows of their own (and move
  back) with their unsaved text and kernel, fixed kind colours (app violet, notebook blue, script green), the Workbench's modes (Notebook, Script, Data: each document's own panels; App mode went with app notebooks), the
  Analyze page (every analysis by its contract, results landing on its board), compare's diff, tie-out,
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
  project's scaffold, its own `.venv` (made by the app as a project is made or opened, Git-ignored: one Python per
  project, the owner 2026-11-21; uv or pip fetch its libraries from the package index then), `.sab/data/` only on
  the user's tick, the project scaffold's made files as the user works
  (`adapter.py`, `connections.py`: names only, never a value; README.md's Variables block; data.py's structures;
  `.sab/scaffold.json`, their hashes; services/scaffold.py), `sandbox/` at its top (moved once from an older
  project's `.sab/sandbox/`, Git-ignored) only on the user's Add to sandbox or Make a sandbox variant (and its
  grid's edits), and the sandbox mirror beside it (`sandbox_data.py`, `sandbox_connections.py`: names only; Remove
  the sandbox deletes the three, nothing else),
  `.sab/stats.json` (the calls' running figures: names, times, sizes) and `.sab/changes.jsonl` (the change log: names,
  types, fingerprints), both Git-ignored and never a value (Plans/stats.plan.md, Plans/changes.plan.md, 2026-11-22),
  `.sab/api-shapes/` as its local sandbox API's endpoints are called (each one's learned shape: paths and
  types, never a value; Try it's Keep as its example and its `.sab/api_examples.json` went, the owner,
  2026-11-22: "No need to ever keep values"), `.sab/api-discover.json` on the user's Allow for its discovery
  (a library API's Allow beside it: `apis/<name>/discover.json`; each until taken back), `data.ipynb` and a
  script the user picks on Build's Notebook cell and Script function:
  the project's sandbox, a DuckDB file of the tables a local sandbox API reads and writes, Git-ignored: a local
  sandbox API never touches live data, its process gets only the sandbox, through the adapter's door, and no
  connection's code, variable or secret), the audit log and, in beta mode,
  the beta log (`~/.swissarmybench/logs`: redacted errors, slow requests, processes, page errors and
  the user's notes; no data, SQL, code, secrets or paths; the owner's call for the beta, 2026-11-15).
  **GitHub sync (the owner, 2026-11-18; the Git extension) sends the team library's and shared projects' files to
  GitHub on the user's Clone, Pull, Push and Commit only (`sync.json` in the state folder: links, never a file's
  content or the token); see the library bullet.** **Sharing a running app (the owner, 2026-11-21: "I just wanted a place
  for a user to host a POC so others can connect to it like an app"; Plans none, docs/ideas.md "Share a running app")
  sends that app's own traffic through Microsoft Dev Tunnels on the user's Share… only** (the agent's `sharing_start`
  on Allow): organization only ("People open the link after signing in with their Microsoft work account... There are
  no public links at all": the tunnel's access is the signed-in user's Entra tenant, never anonymous, the access read
  back before hosting; a policy that blocks it is said with what to ask IT, never worked round), until you stop it
  ("A link always ends with its app": Stop sharing, the app's stop, Swiss Army Bench closing), and only the app's own
  127.0.0.1 port (a Streamlit launch's shared run), never this server's port, token, routes or pages. Microsoft's
  devtunnel command line is downloaded on the first share only, into the state folder's `devtunnel/`, from Microsoft's
  download store, checked against the Content-MD5 it publishes and, on Windows and macOS, its Microsoft signature;
  sign-in (`devtunnel user login --entra`, its token in the system's key chain by devtunnel) is the user's own. The
  Session log says which app was shared and stopped, never the link or a token.
  **The Environment's Libraries tab (the owner, 2026-11-22: "checked when the tab opens, never in the background")
  asks the package index (PyPI's JSON, a GET a library carrying only its name) for newer versions when the tab opens
  or the user asks, and installs with uv or pip on the user's Install or Update (the agent's on Allow); it writes
  the open project's requirements.txt (Pin, Unpin, Install, Remove), only when its bytes change.**
  **Otherwise one request leaves the computer, by the owner's call (2026-11-16):** the update check, PyPI's JSON for
  `swissarmybench` (then GitHub's latest release), at start and every six hours, carrying nothing but
  itself; its on/off is a hidden setting (`update.json`, the agent's `app_update_check on`), and Settings shows only
  **Click here to update**, only while an update is available (the owner, 2026-11-19). The desktop app's and updates' small state
  files: `desktop.json` (the app's process id and its 127.0.0.1 channel's port and key, owner-only), `desktop/`
  (its Qt WebEngine profile: cookies, local storage, cache; `windows.json`, each kind of window's place),
  `update_failed.json` (read once, then gone); `follow.json` (Follow the agent on or off); `rail.json` (the rail's names on or off); `library.json` (the library folder's path, when Settings moved it); `extensions.json` (a preinstalled extension the user removed, and the version its bring-back was tried at); `dialogs.json` (the file picker's recent folders per kind of pick: paths only).
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
  documents are ordinary files at its top, written by their own Save (API.py among them: the project's local
  sandbox API, its settings in its header, made by New project, the user's own file); the app's state is the project
  folder's `.sab/` (project.json: sorted, no timestamp; visualizations.json and visualizations/ (saved
  dashboards); model.json), written on Save, on New project (scaffolded where the user named, .gitignore
  and README.md only when absent), by Autosave (on by default) and by the Autosave switch, each file only
  when its bytes change. Rows only on the user's "Keep its rows" tick, into `.sab/data/` (Git-ignored);
  the agent's save or Copy project to with rows waits for the user's Allow. Copy project to copies the
  folder (`.sab/data/` on a tick). **Launch's builds (the owner, 2026-11-19: "think Visual Studio"; "we just have
  apps in folders"):** each launch of a Streamlit app writes `builds/<app>/<n>/` at the project's top (code,
  canvas.json, build.json; never rows or a secret; shared in Git), and a saved analyzer session goes beside it
  (perf-<time>.json: names, times, sizes, counts only). `recent_projects.json` holds the projects' folder paths and times only;
  `projects.json` the Project Explorer's projects folder, sort, custom order and hidden ones. The old
  single .sab file is not read any more (its conversion removed, the owner, 2026-11-17: `swissarmybench open
  x.sab` says so in one line); the installers take an earlier .sab registration away.
  **The library (the owner, 2026-11-17; Plans/library.plan.md):** connections, APIs, vaults, blades, relationship
  sets, variables and connection colours live outside every project, in one folder of text files made to be a Git
  repository: `~/.swissarmybench/library` (Settings' Library folder points it at another, a clone of a team's;
  `library.json` keeps the path): `connections/`, `vaults/`, `blades/<name>.blade.py`, `apis/<name>/`,
  `extensions/<id>/` (folder extensions: found at start, trusted like the blades, no signing; Plans/folder-extensions.plan.md),
  `relationship-sets/`, `variables.toml`, `colours.toml`, `catalog/` (the shared catalog, below), `local/` (this
  computer only, git-ignored: `local/variables.toml`, and `local/vault-names/<vault>.json`, a key vault's secret
  names and their variables as last read here, never a value, so a vault that loads every secret gives its
  variables from the first second after a start; one name, one variable: a vault's name already taken is given
  as `<VAULT>_<NAME>`; the owner, 2026-11-20), README.md and .gitignore made on first use. One file per item, the same text for the same thing: a save that changes
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
src/swissarmybench/
  settings.py            every limit (plan 6a) in one frozen dataclass
  stats.py               public: the analyses on your own table (what notebook code and sab.analyze call)
  bootstrap.py           the composition root: builds the adapters, hands them to the services; bootstrap() runs
                         its parts by area in order (_adapters, _connection_runs, _workspace_and_beta, _data, ...,
                         _exports), each reading what it needs from Built (the one typed record of what is made
                         so far; a closure reads a later one when it runs), then Services from it
  extensions.py          the extensions that are on (entry points `swissarmybench.extensions`, or
                         SWISSARMYBENCH_EXTENSIONS: extension_on(id)), their modules, every project type's
                         mode as data (the base's BASE_MODE, each extension's MODE); the library's folder
                         extensions (folders(): library/extensions/<id>/ loaded as the package sab_ext_<id>,
                         or kept with its error, its missing REQUIRES, a package of its id winning; use_library:
                         the server's library; SWISSARMYBENCH_EXTENSION_FOLDERS for tests), a folder's MODE and
                         New project files from its contract.json; contract(module): any extension's contract.json

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
                         registration (a vault's secret), ROPC (MSAL or stdlib; AADSTS codes in plain words), and
                         MultiFactorSignIn (a username with MFA: a browser, else a device code; the encrypted token
                         cache and the account remembered; Dataverse and SQL Server use it too)
    sharepoint.py        SharePoint through Graph as text: lists (typed columns, lookups, people, $filter,
                         $batch writes retried on 429) and documents (each library's file index, CSV/Parquet/
                         JSON-lines files and workbook sheets and named tables as tables, kept by eTag)
    powerbi.py           a Power BI workspace: a dataset's name with its connection (Finance/Sales model),
                         a table's name as a grid (the dataset's too when two share it), a dataset's own
                         relationships as the app's model (the INFO functions' rows, named or numbered)
    blade_templates.py   Template: a starter connection's or blade's code and listing query (re-exported by blades.py)
    blade_tables.py      the blade IDE's file rules (with_code: the code after the header, the file's line ends;
                         follow_variable; stamp; SECRET_STUB for the lint); a table blade's own table name (names_table; the live check's answers: available, a table,
                         a connection, another blade's table, not a valid name), a connection's listing query from
                         its starter (listing_for), whether the adapter lists its tables (listed_by_adapter: its
                         listing not the user's own, a dialect in ADAPTER_LISTED), New blade's choices, a file's header rewritten (with_header:
                         the code's bytes untouched)
    blade_header.py      the blade tab's Properties: every header field (FIELDS) for the kinds it applies to, a
                         save's changes, the kind's required part before a save (its line), New blade's scaffold
                         per kind (table, code, analysis, connection, snippet, secret: made-up rows, Run at once)
    debugger.py          the Scripts page's debugger's rules: breakpoints (plain, condition, log), steps, a stop's
                         frames (the script's own lines, a library's), variables, the Session
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
                         `import os` added; blades.env_settings lists the mappings (export, Run settings);
                         a key vault's certificate (2026-11-20): a box of one `${NAME}` written as
                         `certificate_file(os.environ["NAME"])` (CERTIFICATE_FILE in the code while used: a path
                         as itself, PEM text or base64 of it as a 0600 file removed at exit); VARIABLE_ONLY (the
                         vault keystore's password: a variable or none, never typed)
    keystores.py         Trino's client certificate: the keystore read inside the connection's own code
                         (PKCS#12 by cryptography, JKS/JCEKS by pyjks, PEM, by its first bytes; a file, or a
                         key vault's value: base64 PKCS#12/JKS or PEM text), its key and chain as 0600 PEM files
                         removed at exit; the three sign-ins' code (password, from a key vault, a file here)
    snippets.py          snippets (a blade kind): text for a cell with <<name>> placeholders, what each asks
                         for (read from its name), a value written safely for where it stands (DAX, Python, HTML)
    packages.py          the pip packages a blade's imports need (re-exported by blades.py); a missing package
                         said one way everywhere: {"missing": {feature, packages, python ("app" or a path),
                         command}}, the feature in plain words, MissingPackagesError (422 with it); the
                         imports a script lacks (missing_imports)
    stats.py             the shared statistics: chi-square, t, F and normal distributions, effect sizes
    analysis.py          the analyses' math and query text: the fit test (Benford, Nigrini), outliers
                         (amount fences, frequency on two scales), odds (ratios, Woolf's range), buckets,
                         find predictors' rules, identifiers, a wide table, and the notebook code (one
                         swissarmybench.stats call)
    analysis_contracts.py each analysis's data contract (FORMAT 1; the owner, 2026-11-19): the question, the
                         technical name, the group, the table's shape, the slots (words, kinds, how many,
                         checks, name hints), the options, the output, its own fixes, a deterministic made-up
                         sample; an analysis blade's read from its code (its CONTRACT, or `columns`), never run
    analysis_facts.py    a table's column facts (one DuckDB pass: types, counts, ranges, text that reads as
                         numbers or dates) and the one checker: check_column (fits a slot or not, and why)
    analysis_fixes.py    Make it fit: each fix as grid steps with one sentence and its count (text to number,
                         text to date in one style, a month column, the ten most common and Other, drop
                         blanks, keep positive, yes/no, totals per month or key)
    analyze.py           the Analyze page's rules on those: a form planned (the picks and why, what is
                         missing in one sentence, the options), the sentence of what will run, each analysis's
                         request, what a column fits, the ranking (fits now, after its fixes, or not), the
                         table's notes (the Data shape check)
    analysis_cards.py    a result as the board's cards (a report-style note and its Plotly chart), its rows
                         for Open as grid, its hand-offs to the next tool
    regression.py        linear and logistic regression: the terms as SQL, the sums, Cholesky, ranges,
                         what-if predictions, the model as SQL (predicted and miss columns)
    timeseries.py        periods, the seasonal index, anomalies against neighbours, steps in the level,
                         memory, growth; the forecast (trend, steps, season, predictors, held-back check)
    tieout.py            the tie-out report: shared columns, the two GROUP BYs joined, ties or off
    proofs.py            Show the math: each analysis result as a step-by-step proof (markdown)
    themes.py            the Analyze board's 20 themes and imported ones, every colour made readable (WCAG)
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
    vault_names.py       a key vault's secret names remembered (local/vault-names/<vault>.json: the names, each one's
                         variable as given out, the time read; sorted, byte-stable, never a value); one name, one
                         variable (assign: your variables and a vault's own entries keep theirs, a vault that
                         loads every secret gives a taken one as <VAULT>_<NAME>, then _2; a name given before
                         kept while free, so none jumps between starts); the refusal's one sentence
    library_setup.py     Set up this computer: each vault (readable, its sign-in, the variables it gives), the
                         values to type once, each connection's status (works, needs, only works here), shared
                         projects not set up here, the count's words, the notice
    sharing.py           Share a running app with your organization (Microsoft Dev Tunnels, 2026-11-21): devtunnel's
                         download (Microsoft's store, Content-MD5, Windows' and macOS' signatures), each command line
                         (values checked; never anonymous; never the server's port), its output read (--json, host's
                         address, the device code), a policy's words (what to ask IT), the states and the words
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
    found_connections.py Find connections on this computer (the owner, 2026-11-20): Found and Source (no field
                         for a password), kinds from a tool's words, connection strings, JDBC and database URLs,
                         objects with a host, port and database; every password cut out (clean); the list (merged,
                         Already added by its settings, kinds with no connection said); a row's import body from
                         its starter's code (its sign-in's way; its password secret("<NAME>_PASSWORD"))
    found_readers.py     the known tools read exactly (ODBC registry values, odbc.ini, .dsn; SSMS RegSrvr.xml and
                         UserSettings.xml; DBeaver data-sources.json, never credentials-config.json; Azure Data
                         Studio and VS Code settings.json; JetBrains dataSources.xml and its projects; pgAdmin 4's
                         rows; MySQL Workbench; HeidiSQL; .odc, .udl), PLACES (each tool's file per system), the
                         hint scan (connection-shaped strings; SKIP_NAMES: browsers, password managers, key stores,
                         sync caches, this app's own; size, count and time caps)
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
    environment.py       the Environment (the owner, 2026-11-21/22; Plans/environment.plan.md): one row's shape for
                         every kind (table, variable, structure, setting, library), Used in (grids, cells by number,
                         canvas widgets, API.py endpoints, analyses, the ERD, tables made from it), the one search
                         over every tab by the Data Explorer's matching (explorer.hit), requirements.txt read and
                         written (Pin name==version, Unpin, a library added or taken out), a newer version, what a
                         library is for and where it is imported, a secret masked, Clear's ticks, Insert's code
    environments.py      a loose notebook's own environment: the libraries offered (groups, presets, imports)
    project_python.py    one Python per project (the owner, 2026-11-21): which document is the project's (a path
                         inside its folder), what its `.venv` is made with (the kernel, the Excel readers,
                         requirements.txt's plain lines), the libraries someone chose in an older environment (the
                         ones no other needs) and what they offer the project, the states (none, making, ready,
                         missing, failed) and every word said (the session's Interrupt and Restart, ready, failed)
    errors.py            the error panel's words: what an error means and the fixes (replace, import, install,
                         run the cell that makes a name, a table open in Grids' cell); where a SQL error points,
                         the missing table (DuckDB's own-table "Did you mean" dropped)
    script_export.py     a notebook or script as one self-contained automation: one ordered plan of steps, rendered
                         as a .py (plain python) or a linear .ipynb; script_runtime.py the helper text it inlines
                         (the package check, settings, the vault by managed identity, connections)
    lineage.py           a cell's or a block's lineage back to the data: makes and reads, @cell links, a
                         table's grid steps and origin, data.ipynb, controllers; nodes, edges, Mermaid
    kind_colours.py      kind colours (app violet, notebook blue, script green): each theme's fixed one,
                         never amber; the readability rule the connection colours use (fitted)
    notebook_flow.py     Notebook mode: each cell's state from the run order (notRun, edited, outOfDate
                         with the names made again) and the Outline (headings, named cells)
    intellisense.py      the editors' intelligence around Jedi: docstrings (Google, NumPy, reST) for each
                         parameter's words, IPython's lines made Python of the same lines, the app's names
                         inside strings (sab.connection("|"), os.environ["|"], secret("|"), sab.blade("|")),
                         the small lint (compile, undefined names, unused imports, f-strings, == None, bare
                         except) and its fixes, where an import goes, SQL's syntax by sqlglot, the ranking
    workbench_pages.py   Notebooks and Scripts, two pages (2026-11-21): which page a file or a kind opens on, the
                         one line a wrong-kind take is refused with, the old /workbench addresses, a command's page
    code_tree.py         the pages' explorers: a .py's module (scripts/etl/load.py is etl.load), its outline by ast,
                         the groups (Your scripts, Project code, made files and what they are made from, the
                         library's Connections, APIs, Key vaults, Widgets, Generated), the notebooks' (data first)
    script_ide.py        the Scripts IDE's rules: search and replace across the scripts (regex, case, word), a
                         rename's plan and preview that never writes a made file, a Python name checked; a
                         module's imports rewritten when it is renamed (import_rewrite, move_plan), a copy's
                         name, a library's source that may be shown read-only (library_file)
    script_runs.py       Script mode: run settings (arguments; each variable's source: this computer, a
                         plain value, a key vault, never a secret's value), the variables a script needs
    dictionary.py        Data mode: data.ipynb's data dictionary (plain-word types, descriptions kept in
                         data.ipynb's metadata and written into data.py, where each column comes from)
    updates.py           versions (PEP 440), PyPI's and GitHub's release lists, which is offered, the
                         update's plan (uv tool install --force, each installed extension `--with`)
    extensions.py        extensions: the catalog (streamlit preinstalled; accounting, powerapps, copilot available), statuses
                         (preinstalled, available, installed, coming), an entry point's description read loosely,
                         the wheel on this version's GitHub release, Install's and Remove's plan; a folder
                         extension's card (source folder, path, on, error, missing: the one missing answer) and
                         a contract's project type and deliverable on a card
    extension_folders.py folder extensions' rules (Plans/folder-extensions.plan.md): the id (a Python name, never a
                         base word), the manifest's literals and REQUIRES read with ast before it loads, a load
                         error's one sentence with its file and line, the words; New extension's folder
                         (extension.py with one route, commands.py with one command, README.md, contract.json)
    scaffold.py          the project scaffold as text (Plans/adapter.plan.md "The exported project"; 12a): connections.py
                         (a marked section per connection the project uses, `# ===== connection: <name> =====` to its
                         end mark; its variables named, SETTINGS without values), README.md's Variables block (name,
                         source, uses; never a value; the rest of README.md byte for byte), data.py's structures read
                         as grids (a stdlib _records line each), the sandbox mirror (sandbox_data.py: tables, where
                         from, keys, baseline, checkpoints by name; sandbox_connections.py: each connection's stand-in
                         over sandbox/sandbox.duckdb, never its code), what to write (plan: write, remove, same, edited
                         by hand: kept, Take the new one; .sab/scaffold.json the hashes the app last wrote)
    project_contract.py  contract.json (FORMAT 1; Plans/adapter.plan.md): a project type as JSON (type, name,
                         deliverable, languages by pattern, cells, files: path, owner user or app, starter, made_from,
                         grows_on; requirements, canvas, export, areas, words); the one checker (one sentence naming
                         the key: unknown keys, a newer format, paths out of the project, the core files refused);
                         byte-stable text; New project's files from it, its MODE, a path matched to its entry
    beta_log.py          beta mode's default (one constant), the beta log's redaction (quoted text, numbers,
                         secrets, paths; table and column aliases), stacks as file:line, notes, the rate cap
    navigation.py        app_navigate's places: each window's (home, catalog, workbench) and the notice; the rail's
                         names (on until turned off: rail.json)
    sample_data.py       the made-up sample store (customers, products, orders that join them): Try it with
                         sample data on every empty page (POST /samples/store, datasets_sample)
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
                         relationship, a connection, a cell), names and counts only; the filter; Follow; a change's
                         words beside its entry (`change`), the `changed` entry of its own
    call_stats.py        every call's statistics (Plans/stats.plan.md): one record from the adapter's facts, a
                         finished slot ticket with its child's facts, api_adapter's (time in parts, size, folded vs
                         DuckDB, outcome, who and where, fingerprint; never a value); running figures (p50, p95,
                         errors, typical sizes); .sab/stats.json's text; hints in words; the stats tool's views
    changes.py           the change log (Plans/changes.plan.md): one change (the object, a difference by name, types
                         the only thing shown, words, fingerprints before and after; never a value), a notebook's or
                         a script's parts (document_shape), .sab/changes.jsonl's lines, last, history, since, search
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
    connection_slots.py  how many queries run at once on a connection (the owner, 2026-11-21): limits (8 at once,
                         4 the agent's, a 2-minute wait; the file's [queries] table), a Board of lines (FIFO within
                         a priority: the user's before background loads; the agent's share), places, leases, words
    query_text.py        a query's SQL formatted for reading (sqlglot's pretty printer in its dialect; DAX and what
                         does not parse as written; `${NAME}` as written): the Queries window's, the user's only
    file_dialogs.py      the system's own file dialog (the owner, 2026-11-17): a request checked, the tool per system
                         (Windows: Tk's IFileDialog, else PowerShell's Forms dialogs and IFileOpenDialog for a folder;
                         macOS: osascript, else Tk; Linux: kdialog on KDE, zenity, kdialog, else Tk; none without
                         a display or with SWISSARMYBENCH_SYSTEM_DIALOGS=off), each tool's command line (values as
                         arguments or an environment variable, never in a script's text), its answer read; the
                         recent folders per kind of pick (dialogs.json); New folder's name
    app_registrations.py an app registration (a library item: three variable names in app-registrations/<name>.toml)
                         and its access report (names, marks, reasons; never a token or a row), Microsoft's refusals
                         in plain words, a connection's access in one line; the Microsoft kinds it checks (Azure SQL,
                         Dataverse, SharePoint, OneLake, Data Lake: each one's scope, place, refusals in words) and a
                         connection's code made to sign in with a registration (signed_in_with: its place kept)
    sandbox.py           the project's sandbox (2026-11-21): sandbox/ at the project's top (sandbox.duckdb, baseline.duckdb,
                         checkpoints/, sandbox.json: each table's source and the client its rows are mocked as, the
                         baseline, checkpoints, the change log), names, the writes' SQL (checked names, bound values);
                         the Sandbox as a connection kind (CONNECTION_TYPE, its card's words, its indigo COLOUR), the
                         sorts (name, rows, source, created, changed), variants (a designation "orders · sandbox", the
                         origin kept and said), a grid edit's SQL (a row by every value it shows, CAST to its type;
                         a LIST, STRUCT or MAP cell as JSON: CAST(?::JSON AS its type)); keys (check_key, db_words: a
                         duplicate or blank key in one sentence); what an API made (made_record, unmade after Reset);
                         NAME_TAKEN (no connection called Sandbox); MAX_ROWS_ANSWERED one answer's size (the rest paged)
    sandbox_dialects.py  the sandbox's half of the adapter's query: the source's SQL and its driver's marks made
                         DuckDB SQL by sqlglot (each mark numbered in its own order; SELECT, INSERT, UPDATE, DELETE
                         on the sandbox's tables only); a view, a query's table (SELECT INTO too) or a sequence made
                         or dropped (DEFINES; NEXT VALUE FOR as nextval); what cannot be emulated refused with its
                         line; what a query names (names_in: Will this work for real?)
    local_api.py         API.py (2026-11-21): its `# /// swissarmybench-api` header (name, description, target,
                         base_path), its endpoints read with ast (method, path, parameters: path, query, body; the
                         answer; the connections and SQL it uses; problems with lines), models, OpenAPI 3.0, the
                         scaffold, the hosting process's environment made from nothing (runner_env); an endpoint's
                         one definition for every reader (body_fields, made_up: Try it, the Canvas's Event mapping,
                         Payload shapes, the agent), shapes (the API widgets and each Event wired to call one);
                         editor_problems (API.py's squiggles: its rules, a connection with no sandbox table, SQL the
                         mock would refuse, never run); agent_writes_words
    api_targets.py       a local sandbox API's framework targets as data (FastAPI, Azure Functions v2 on Linux, AWS
                         Lambda on Linux; an extension's API_TARGETS): each one's files from a Bundle, the fewest
                         (API.py as it is, adapter.py, connections.py: the real connections' own code, a section
                         each; requirements.txt; README with the deploy steps, the checklist and the variables; the
                         framework file with sab_api folded in as a module of its own, its OpenAPI document inside
                         for FastAPI; host.json and .funcignore, SAM's template.yaml; api_adapter.py only when
                         API.py calls another API; no secret), exports/api/<target>/ a made folder
    api_scaffold.py      the Table pattern: the CRUD set (list with limit and offset, get, create, update,
                         delete by a key; a TypedDict of the columns), one style for every source: the adapter's
                         connection(name).read and .write (2026-11-22); the imports a block needs (a date's too)
                         merged into API.py's own lines (imports_missing, with_imports); fitted (a file that
                         imports the datetime module: datetime.date); py (a value written as a formatter leaves it)
    api_patterns.py      the endpoint wizard's patterns as data (the owner, 2026-11-21): Step, Pairing, Pattern, the
                         nine (table, choices, search, summary, bulk, action, versions, reconcile, export: each its
                         own steps and the widgets that pair with its endpoints), Registry (ranked: a table's shape
                         against every pattern with one sentence why; planned: a pattern's steps with their columns
                         and defaults; make; role, pairings), from_extension (an extension's API_PATTERNS), the one
                         marker comment (`# pattern: summary of orders`: marked, pattern_at)
    api_pattern_code.py  each pattern's ONE template, filled from its fields and the table's catalog, its fit and
                         its defaults: connection(name).read / .query / .write only; filters, columns, sort, page
                         and keys in the read's plan; a summary by period and a reconcile one statement in the
                         source's own SQL (sqlglot, its dialect), else only the needed columns read and DuckDB over
                         the stream (Made.streams); Target, Taken, Made
    api_actions.py       an API's actions in the app (Plans/api-adapter.plan.md): `local` (the project's local sandbox
                         API), the shapes' folders (apis/<name>/shapes/, .sab/api-shapes/), Build's text (a notebook
                         cell, a script function: sab.run, sab.records) and widget plan (data_table on [API].action,
                         the local API's endpoint wired; api_form, api_metric: any API's action), why one
                         cannot be built; ref() (an action as the canvas names it: "GET /orders", "[Orders] GET
                         /orders"); tried() (Try it's form from the learned shape: made-up values by type);
                         with_cell, script_path, with_function (Build's cell into data.ipynb, its function into
                         a script); allow_text, allowed_since (Discover's Allow: apis/<name>/discover.json, the
                         local API's .sab/api-discover.json)
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
    analysis.py          the analyses on a grid's view: run_* functions over any cursor (the same code
                         swissarmybench.stats runs on a DataFrame), the notebook code
    analyze.py           the Analyze page: the toolbar and contracts (your analysis blades' too), a form
                         planned on a table's facts (kept by view), Check this table, a column's analyses,
                         fixes applied as steps on the caller's word, the sample opened as a table, run (a
                         time limit in plain words, cancel by token; the cards land at the top of the board),
                         a result Python computed landed, a run's math, rows as a grid, code and inputs;
                         the last columns and options per table and analysis (memory)
    regression.py        regression on a grid's view (run_regression, over any cursor) and what-if
    timeseries.py        time series and forecast on a grid's view (run_time_series, run_forecast)
    sql.py               the SQL box
    export.py            CSV, Excel, Parquet: a download, or saved (an agent's only with a ticket)
    codegen.py           copy as code: generate, then verify what the user will paste
    charts.py            the side panel's cards: charts, notes, tables, diagrams, cross-filtering
    agent.py             the agent door: approvals, export tickets, its reads, the current table,
                         listing and proposing blades (saved on the user's Allow)
    catalogs.py          load, remove, the tree, search
    catalog_loading.py   catalogs that load themselves in the background: on save, at start-up (once the
                         first window is open; not a browser-window sign-in), on first use; each a child
                         process, a few at once
    blades.py            save, inspect, fill, refresh, test, install, favourites, folders, export, import
    connections.py       connections: the list, the forms, test before saving, password sources
    found_connections.py Find connections on this computer: the scan off the loop (Cancel), the last list in memory,
                         import (each a connection by ConnectionService.save, its password a variable declared not
                         set); the agent's scan and import on the user's Allow
    session_log.py       the Session page: the audit heard (Heard: the file, the Session page, then the change log),
                         this session's entries in memory (Changes: only those that changed something), the
                         `session_entry` notice; Follow the agent (follow.json; 403 for the agent)
    call_stats.py        the statistics' three ears: adapter.observe here (the app's own session left out), the
                         slots' on_finished (a connection's call with its child's facts), api_adapter's envelopes
                         (Actions says its own; observe hears the rest); the last 3,000 calls in memory, the open
                         project's figures in .sab/stats.json (a few seconds after calls settle, only on change)
    changes.py           the change log: raised (a change on the audit entry a service writes: `change=`), the log
                         that hears it (stamped, appended to the open project's .sab/changes.jsonl, else memory), a
                         connection's settings and sign-in as it names them; the changes tool's views
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
                         session by what was sent, Refresh), the Connections page's tree, Open all of a dataset;
                         listed (a loaded catalog's tables as SQL names them) and read_named (one `[Conn].table`
                         read whole: a widget's table property)
    connection_slots.py  the one gate every connection run passes (bootstrap's run_blade): wait in line, Cancel
                         (the child killed), the wait limit (Try again); who from the request (CURRENT: the agent,
                         a page's X-Sab-Client, a kernel's X-Kernel); kernels' leased slots; the Queries window's
                         list, finished (memory, last 50), SQL (the user's); the limits saved; `connection_slots`
    environment.py       the Environment: the one list (listing with search, show, a table's columns with ranges and
                         blanks), open (a table: a grid, a view of it; one in Python only: its session sends it),
                         rename, remove (a table: also delete it in Python), keep, clear, insert; libraries (the
                         project's Python, check the index only when asked, pin, install (one or several),
                         update, uninstall: the agent's on Allow); python and set_python (the project's own
                         Python: Make it now, an offered notebook environment's libraries added or not);
                         `environment_changed` once things settle (heard: the live notices);
                         sources_from (the app's services as its Sources)
    explorer.py          the Data Explorer's search: a provider per source (connections and their loaded catalogs,
                         the open tables, variables, blades; a connection whose catalog is not loaded offered);
                         Structures' documents and paths and APIs' table-returning web calls registered from
                         theirs (register("structures"/"apis")); one failing source skipped
    sandbox.py           the project's sandbox: add (an open grid's view, a connection's table read once, a file,
                         columns), remove, Reset (the agent's on Allow), baseline, checkpoints, the adapter's door
                         (source_tables, read_arrow, query_arrow: the connection's SQL made DuckDB's, write_arrow:
                         counted, an open grid following), [Sandbox] in DuckDB SQL (SandboxAlias:
                         the `sandbox` tables kind), the Catalog's Sandbox section; listing sorted, variant (a grid's
                         view or a structure's records, named apart, never written back), mock (Mocked as a
                         connection), edit (its grid's cells, rows added and deleted: typed, counted, Reset undoes),
                         card (the Connections page's Sandbox); views, query tables and sequences an API makes
                         (_define); keys (set_key, a
                         connection's from the shared catalog, put back after Reset and Restore); mock_dialects
    local_api.py         the local sandbox API: state (each endpoint's data words), new, settings, run and stop
                         (started again when API.py changes), call (the agent's writes on Allow: one Allow covers
                         the session; api writes), log, address, the endpoint wizard (pattern_list; plan: the
                         tables, the patterns ranked, a pattern's steps and its code, nothing written; scaffold: a
                         pattern's endpoints appended to API.py, a dry run the code only; its key kept by the
                         sandbox; paired: each pattern-made endpoint with its widget, for the Canvas); each
                         endpoint's pattern and "DuckDB does part of it over the stream"; state brief (full: the
                         OpenAPI document)
    scaffold.py          the project scaffold kept as the user works: status, refresh (adapter.py once something
                         reads through it, connections.py for the connections the project uses, README.md's
                         Variables, data.py's structures, the sandbox mirror; only changed bytes; a hand edit kept),
                         take (Take the new one), export_core (an export's adapter.py and connections.py), a refresh
                         once the live notices settle; the type's deliverable from its contract.json (never named);
                         `project_scaffold`
    api_export.py        Export for a target: the bundle, the made folder (only changed bytes, stale files gone,
                         a hand-edited file kept until Replace), the sandbox's copy on the tick (the agent's on Allow)
    apis.py              Add API: preview, add (into this computer's library, apis/<name>/: API_<name>.py, its API
                         blade, a web call blade per operation, openapi.json, source.json), inline (the exporter)
    actions.py           every API's actions through api_adapter (the module handed in): list, describe, run (a
                         library API's in a child process through its API blade; the local API's through its
                         process; a write by the agent on Allow), the shape kept (types only, said once), offer,
                         discover (Allow asked once per API, kept with it until taken back: allow; reads
                         only), build (a cell into data.ipynb, a function into a script, each opened there;
                         hooks.canvas_put for a widget); refs (every action as the canvas's one picker names it),
                         carried (what a built app carries: api_adapter.py, sab_actions.json, an API's client),
                         local_learned (Try it's form)
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
                         a document moving to another window (handoffs: its state and its kernel); ONE Python
                         session per project (2026-11-22): start answers the same kernel for every document of
                         the open project (_join), a run says which document it is for, Interrupt and Restart
                         are the session's (session_restarted; Restart moves to a `.venv` made since), leave (a
                         closed document leaves it running), end_session (the project closed: session_ended); a
                         loose file keeps a kernel of its own
    project_python.py    the project's own `.venv`: made in the background on New project and on opening a
                         project without one (never waited for; the app's own Python meanwhile), Make it now and
                         Try again, the `project_python` notice (making, ready, failed), the session's folder and
                         Python for the Workbench, a notebook's older environment read once and offered (moved,
                         settle_offer); SWISSARMYBENCH_PROJECT_VENV=off: never by itself
    workbench_window.py  the agent's workbench_window: a palette command run in the Workbench window
    intellisense.py      the editors' intelligence: complete, signature, hover, lint (Jedi in the kernel or
                         a Script over the project; the app's names; Ruff or pyflakes where there; a worker
                         thread, a one-second budget, superseded requests skipped); what each editor shows,
                         for the agent (workbench_complete, workbench_signature, workbench_problems)
    modes.py             project modes: the open project's type (.sab/project.json) to its mode (canvases,
                         families, languages, cell kinds, tool group, export); GET /app/mode, app_mode; the rail's
                         areas the on extensions add (GET /app/areas: their RAIL, and the footer's mark route)
    navigation.py        app_navigate: a window sent Home, Back, Forward or to a view (the page moves itself);
                         the rail's names switch (GET/PUT /rail, rail.json, rail_changed; app_rail)
    lineage.py           a lineage with each step's value: from the kernel, a playing page, the grid
    script_ide.py        the Scripts IDE: its tree (the project's code, the library's, Generated), go to definition,
                         references and rename over the project's modules (the editors' one Jedi world), search
                         and replace, Format (Ruff in the script's Python), Fine-tune as a script; each write said
    debugger.py          the Scripts page's debugger: a session per kernel over the kernel's own debugpy (the
                         Jupyter debug protocol), the run and the events' watcher, steps, variables, evaluate,
                         stop; `debug_state` notices
    code_files.py        code files that update themselves everywhere: `file_changed` {path, hash, by} on the app's
                         writes (touched) and on a look every few seconds at the project's and library's .py and
                         .ipynb (off the loop); its listeners (a made file saved by hand: project_scope.saw)
    script_runs.py       a script's run settings (run_settings.json): Run file's arguments, the Variables page
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
                         agent's on Allow; Remove asks the user first; a development checkout says what to run);
                         a folder extension with no restart: Install (its missing packages, then Load again: its
                         routes mounted), Remove (to the trash, asked first), Show its folder (the user's only),
                         New extension (the agent's on Allow; written, loaded, mounted)
    claude.py            Launch Claude: what was found, the user's choices, the folder written, the terminal or
                         Desktop started (Desktop's config asked once); the agent reads only
    context_md.py        context.md kept current: gathered from the services, looked at after a notice (every
                         2 s), written once a change settled; what the agent last read (launch, prompt,
                         app_context) and the sections changed since; SEAM for APIs and Structures
    project_outline.py   the outline gathered (build) and written as ARCHITECTURE.md at the project's top, only
                         when its bytes change (write); seams: UsedTables.used(project) (the tables the project
                         uses) and Portability.verdict(connection) (default: "Not checked yet")
    table_cells.py       every open table as its read-only cell's text (the grid's steps as one DuckDB
                         query); a document's Tables group arranged; where each table came from; a table as
                         Arrow for a kernel's DuckDB SQL naming it (view); the Environment's tables as a source
                         of the adapter (adapter_tables, adapter_read: a plan over a grid's view, or over the
                         table as it is when no grid shows it: a table is shared at once, never opened first)
    hooks.py             what an extension hands the base's services once built (late binding): the documents
                         the Workbench windows hold, a canvas, what stops with a kernel or a window, an app's
                         own file, the cells shown live, a new project's app; a project's dataset connection
                         names resolving through its own setting (dataset_aliases: connection tables' DuckDB SQL and
                         a kernel's %%dax cell, GET /connections/sql/alias); each a plain default with none on
    data_export.py       data.ipynb -> data.py (New project, Export data.py, the Streamlit extension's Save as)
    projects.py          projects: a new one, the files the Workbench opens, Export data.py
    sab_projects.py      a project is a folder: new (scaffolded in the projects folder or where named, opened,
                         .sab/ written), open (a folder; a plain one made a project on request; each table
                         read again with its steps; Analyze's board, model, layout), save (.sab/, only changed
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
    sharing.py           Share…: status, install, sign in (the user's only), start (the target's port, a tunnel with the
                         tenant's access read back, the port, host, the link), stop; ends with the app (app_stopped)
                         and the server (stop_all); share_start and share_stop audited (the app, never the link)
    team.py              Settings' Team box: status, join, start, leave (the folders pointed and put back,
                         team.json), pull, push, show; the GitHub work is hooks.team's (the Git extension's TeamPort)
    library.py           the library: info, Settings' Library folder (the agent's on Allow), the notices said
                         once, an older project's blades taken in (the same skipped, `<name> from <project>`)
    shared_catalog.py    the shared catalog kept on the events (saved, listed, relationships, a project's usage),
                         pruned, the folder looked at for a pull's change (catalog_changed), a bad file left alone;
                         the listing, one table, the ERD's model, the Explorer's tables
    library_setup.py     Set up this computer: the vaults checked in child processes, the checklist, Move to
                         a vault
    vault_names.py       a key vault's names kept as they are read (the form, Set up this computer, a kernel's
                         load), written only when they change; given as its variables (Variables, the ${ list,
                         context.md, the checklist, a kernel's names); read again once the first window is open
                         (child processes, a few at once, never one that signs in with a window; a failure keeps
                         them: "Names from <time>: Read again"); a deleted or renamed vault's file follows
    project_scope.py     the open project's documents, and import: documents from another project folder or a
                         loose file into the project; an older project's connections and blades
                         into the library (services/library.py's take)
    app_registrations.py the library's app registrations: list, add, remove, the access report (Test, Check again;
                         never on a timer; audited: Power BI, and each Microsoft connection signing in with it), a
                         connection's Access section
    inbox.py             what the user sends their agent (Send to the agent): memory only, read by the
                         prompt hook (client/context_hook.py) and the agent_inbox tool
    relationships.py     the Key Finder, compares, the current model and its library
    relationship_scope.py the tables the open project uses (open, its own, named in its documents' code):
                         what the ERD and the Relationships window draw by default (scope project or all)
    tieout.py            the tie-out report on a compare's two grids
    processes.py         Python sessions offering tables: the registry and the Open list
    snapshots.py         a PNG of the page, drawn by the page (app_snapshot); nothing is kept

  adapters/              the driven edge: DuckDB, Arrow, files, the vault, websockets
    adapter.py       THE adapter (Plans/adapter.plan.md), one file the app, the API's process (as `adapter`)
                         and an export share, standard library + duckdb + pyarrow only: tables(source),
                         read(source, table, plan) -> (Arrow batches, Folded), query(source, sql, params) (its own
                         SQL: joins, CTEs; a write's count), write(source, table, batches, key, mode: insert,
                         update, merge, delete, truncate) -> Counts, planned() (a write's dry run by reads),
                         table(name) and refresh(name) (a table is the data, a grid its view); Connection (what
                         API.py's connection(name) gives, here and exported: tables, columns, read, query, write);
                         source_from(client) (a connection's own client or a file's path in its backend);
                         catalog_rows (tables as a listing's rows, descriptions too), listed(source) (a database's
                         whole catalog as its starter lists it: Dialect.listing and listing_shape); the Plan
                         (columns, filters, sort, limit,
                         offset, group, totals; what a source cannot fold done by DuckDB over the stream);
                         from_json (pages to Arrow with given types); sources DuckDB (a file, a connection, the
                         sandbox's gated cursor, the app's session as it is), Remote (the sandbox through
                         /sandbox/data/<key>/tables|read|query|write, a kernel's open tables with the token), Sql
                         (any DB-API connection; DIALECTS as data: quote, marks, LIMIT/OFFSET/FETCH, catalog; the
                         plan folded, writes in one transaction; SQL Server's and Azure SQL's writes their own
                         section: staged in the target's types from sys.columns, MERGE WITH (HOLDLOCK), TRUNCATE,
                         identity_insert, passing errors run again whole on a fresh connection (reopen); Trino's
                         row batches without a transaction, NO_TRANSACTION said, a truncate with rows refused),
                         statements() (what a write runs, for a dry run's report), OData (Dataverse's Web API; writes in $batch
                         change sets, choice labels, keys, 429), Rows (the lakes and SharePoint by their own read
                         and writes: Delta, a file, a list's Graph calls), Files (a file connection's CSV, Parquet,
                         JSON: COPY's options, a format, a partitioned folder); arrow_of (rows of any shape), a SQL
                         write's Batch beside the driver's error (batch_of); to_json and to_ipc (an endpoint's
                         Arrow answer). Allowed 3,000 lines (one file); it only grows (design principle 12b)
    api_adapter.py       THE API adapter (Plans/api-adapter.plan.md; 12b), one file the app, the API's process and an
                         export share (`api_adapter`), standard library only: actions(spec) (OpenAPI 3.x, Swagger
                         2.0), run(action, inputs) -> one envelope (inputs checked first; http() or from_client()
                         sign-in; 429 and passing retries; format, envelope, paging and types detected; drift against
                         the known shape: added, missing, retyped, moved, a rename offered once; facts and observe()
                         for the statistics), keep() and text() (an endpoint's shape, types only, byte-stable),
                         learn() (the widgets' contract), discover() (read-only probe, the mapping, master and detail
                         pairs), table(answer) (records through adapter). Allowed 3,000 lines; it only grows
                         Arrow answer); observe(hook) (each read's, query's and write's facts as it ends, for the
                         statistics; no hook, nothing wrapped); Trino's replace one CREATE OR REPLACE TABLE ... AS
                         (Iceberg). Version 1.3.0. Allowed 3,650 lines (one file); it only grows (design
                         principle 12b)
    call_stats.py        the open project's .sab/stats.json read, and written atomically only when it changes
    changes.py           the open project's .sab/changes.jsonl read, and one line appended per change
    atomic_files.py      write_atomic (a unique temporary file beside it, fsync, one replace; the mode given or
                         the file's own; if_changed), replacing (the same for a writer that needs a path: a
                         zip), JsonFile (a small JSON state file; state_files.py, desktop.py, updates.py) and
                         TextFolder (one of the library's folders of small text files: shared_catalog.py's
                         and vault_names.py's read and write)
    database.py          the locked DuckDB, the priority worker pool, DuckDB's own SQL grammar
    datasets.py          the dataset store and its limits; Arrow, CSV, Excel, Parquet, JSON loaders; load_adapted
                         (a file connection's file through the adapter's Files: DuckDB's types)
    views.py             the view cache and windows; Adapted (the engine's cursor: every grid query's execute is
                         adapter.query over the app's session, its values as DuckDB's fetch gives them)
    catalogs.py          loaded catalogs: tree queries and search in the locked DuckDB
    found_connections.py Find connections on this computer: each tool's files found per system (a stand-in home and
                         system for tests: SWISSARMYBENCH_FIND_HOME, _FIND_SYSTEM), the registry read through a
                         seam (named values only; winreg on Windows), pgAdmin's database read-only, the hint walk
    blades.py            saved blades (the library's connections/, vaults/, blades/<name>.blade.py: one portable
                         file each, written only when its text changes), blade folders (.blade.py files found
                         by their header), an API's blades in apis/<name>/, favourites; secrets via keyring
    shared_catalog.py    the catalog/ folder's files: stamps, read, written atomically only when the bytes change
    vault_names.py       local/vault-names/'s files: read, written atomically only when the bytes change, removed
    app_registrations.py app-registrations/ (a file each, its .access.json beside it) and the access report's
                         read-only calls (Microsoft's sign-in, Power BI's groups, datasets, one COUNTROWS; MicrosoftProbe:
                         Azure SQL by mssql-python with the token, Dataverse's WhoAmI and roles, Graph's site, lists
                         and libraries, a lake path's listing)
    team.py              a team's local copy and this library as files: hashes, copy, the layout written, show
    scaffold.py          the project scaffold's made files read, written atomically (only changed bytes), removed
    sandbox.py           a project's sandbox file (move_old: an older .sab/sandbox/ copied to sandbox/, checked file
                         by file, then removed; gitignore: the top's `sandbox/` line; drop_all: Remove the sandbox):
                         DuckDB with external access off, one lock, the baseline and the
                         checkpoints as whole-file copies (Reset is one copy; one table from the baseline read
                         alone), sandbox.json; a read's rest as Arrow (query_paged), keys (set_key: the file and
                         its baseline), definitions (define, kind_of); API.py's file (LocalApiFiles); an export's
                         folder (ExportFolder); the adapter's source (source(), arrow, read, write_arrow)
    tunnels.py           devtunnel's file: the download (HTTPS from Microsoft's store only, 200 MB at most), its
                         Content-MD5 checked, the signature check handed in, kept by one replace; the stand-in
                         (SWISSARMYBENCH_DEVTUNNEL_STANDIN: tests/devtunnel_standin.py)
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
                         SWISSARMYBENCH_EXTENSIONS (tests and development only); each one's contract.json;
                         FolderExtensions (the library's folders as cards, New extension's folder written, Remove's
                         system trash, Show its folder's file manager, Load again)
    projects.py          a project's folder: made, listed, its own files read and written, zipped
    sab_files.py         a project folder's .sab/ files (written atomically, only when their bytes change),
                         the scaffold's Git files, its documents listed, Copy project to;
                         recent_projects.json (folders)
    project_explorer.py  projects.json, the projects folder scanned, a project's facts (.git/HEAD read as text,
                         never git run), Show in folder (the file manager), the system's trash, a rename
    apis.py              Add API: the OpenAPI document read (a file, an address; YAML with PyYAML), API_<name>.py written
    structure_files.py   Structures' files (read, written whole), YAML by PyYAML (else the missing-package
                         answer), records as an Arrow table for Open as grid
    environment.py       the Environment's files: the project's Python (its .venv, else the app's own) and its
                         libraries read from site-packages' metadata (nothing runs), requirements.txt (atomic, only
                         when its bytes change), the package index's newest versions (one GET a library, only when
                         the Libraries tab opens or the user asks; SWISSARMYBENCH_PACKAGE_INDEX), a structure's file
                         removed; requires (each library with what it says it needs: a notebook's older environment)
    variables.py         the Variables page's files (the library's variables.toml, shareable; local/variables.toml,
                         this computer's), the keyring (`variable/<NAME>`), the server's own environment
    live_updates.py      the pages' and VS Code windows' sockets (the app's windows counted for the server's life)
    folders.py           a folder's contents for the page's own picker (hidden ones on request), its places (Home,
                         Desktop, Documents, Downloads), New folder
    code_files.py        a code file's stamp and hash, a folder's code files (hidden folders, caches, environments out)
    script_ide.py        Jedi's go to definition, references and rename (ScriptCode), a file read and written
                         atomically, Ruff's format on stdin
    workbench.py         the Workbench's files (saved on the user's click), recent files, each document's Python
    intellisense.py      Jedi's Project and Environment per folder and Python, the project's modules read,
                         pyflakes, Ruff in the document's Python (on stdin; never installed by itself), DuckDB's parser

  server/                the HTTP door, and everything that starts a process
    app.py               asks bootstrap for the services, mounts the routes behind the guard
    http.py              reading requests, shaping answers, each error as its status in the one refusal shape
                         (domain/refusals.py; refusal(), error_as(); UTF-8; the guard, an unknown address and a
                         method not taken answer it too; cli/api.py reads a words-only one as its words); the
                         handler wrappers: with_body, with_actor, answered, json_lines (a run streamed as JSON
                         lines); guarded (app.py): every route's handler under safely once, no route its own
    routes_*.py          one per feature: read the request, call the use case, shape the answer
                         (datasets, grids, analysis, analyze, regression, timeseries, tieout, agent, cards, catalog, blades, relationships,
                         processes, snapshots, connections, apis, folders, workbench, table_cells, lineage,
                         projects, project_scope, project_outline, navigation, script_runs, session_log,
                         structures, api_explorer, intellisense, sab_projects, project_explorer,
                         connection_swap, variables, connection_colours, connection_tables, connection_slots, sandbox, scaffold, local_api,
                         explorer, library,
                         shared_catalog, team, found_connections, script_ide, debugger, sharing, actions, call_stats,
                         changes). Every route serves
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
    updater.py           Update to X's helper: a copy run by the base Python once the app stopped, it
                         installs with uv, checks the version, starts the app, or the old one and a note;
                         Install and Remove an extension the same way (launch_change)
    routes_updates.py    the update check, its switch, Update to X
    routes_lifecycle.py  GET /lifecycle (app_lifecycle), POST /lifecycle/closed (the app's)
    routes_desktop.py    GET /desktop, POST /desktop/open (desktop_status, desktop_open)
    routes_claude.py     Launch Claude (GET for the agent too; PUT and the launch the user's only)
    tunnels.py           devtunnel run: Windows' Authenticode and macOS' codesign checks, a command's words, `host` and
                         `user login` as running processes (their lines as they come)
    dialog_runner.py     the system's file dialog in a short-lived child process: one at a time, ten minutes at
                         most, the start folder the nearest that is there; GET /dialogs says whether one opens
    claude_finder.py     finding Claude on each system (registry, PowerShell, mdfind, .desktop files) and
                         starting it detached; SWISSARMYBENCH_CLAUDE_STANDIN's stand-in for tests
    blade_runner.py      Refresh/Test in a child process; the blade IDE's Run (run_streaming: prints streamed,
                         the result a table or a value, a failure as the error panel's detail); installing packages
    kernels.py           the Workbench's IPython kernels (jupyter_client): run, complete, inspect, interrupt
    environments.py      making a loose notebook's environment and a project's `.venv` (make_venv: uv, else venv
                         and pip; its own .gitignore inside it); the client lent to kernels
    api_runtime.py       sab_api, what API.py imports (standard library; copied into each export): endpoint,
                         connection (use_clients; else the adapter's Connection), records (Arrow or a cursor),
                         ApiError, handle (one request: every target calls it; the most literal path answers:
                         /orders/search before /orders/{key}); download (rows as a CSV file or an Excel workbook
                         to save, written with the standard library);
                         the body checked against its model first (checked: 422 naming the field)
    api_host.py          a local sandbox API hosted (`python -I`): the app's client functions taken over first,
                         Starlette on 127.0.0.1, its key, the request log (a refusal's words and API.py line; the
                         line as a header of this host only), any other path the API's own 404; api_runs.py starts
                         and stops it and reads what it prints to the end (the last lines: Output)
    streamlit_proxy.py   live pages passed through this server under their own secret (their websockets too),
                         so a page's frame policy stays `frame-src 'self'`: the Streamlit extension's apps and
                         the Power Apps extension's dev server mount it with their own prefix
    blade_templates.py   the 40 starter blades (3 analyses; a Power BI workspace: code that signs in, lists
                         its datasets and sends DAX to one, each dataset shaped like a database connection)

  starters/              the built-in starter pack (99 read-only .blade.py: Power BI, Dataverse, SharePoint, Excel, Files,
                         DAX, HTML, Markdown, Write; the Streamlit extension brings its 52), listed apart, found by name, Copy as your own (tests/test_starters*.py);
                         Write: 16 functions (write_to_*: one public typed function a target, for functions.py) and
                         17 calls (a cell's text: the call only, dry_run=True; one a target, its mode a placeholder;
                         each points at sab.write); 15 of the functions write only through the adapter (the
                         Excel sheet its own until the Excel module: docs/ideas.md "One adapter"; Trino's replace
                         refused: no transaction)
  client/push_client.py  push(), ensure_server()
  client/writes.py       the Write starters' shared part: the rows staged in a DuckDB of their own, the dry run's
                         plan and the write's counts (Write), files (FileWrite: beside the target, then replaced);
                         write_sql.py each database's quoting, marks, values, types and checks (SqlWrite;
                         SqlServerWrite: the columns from the adapter's sys.columns read, computed and identity
                         columns, triggers, keys defaulting to the primary key; its write the adapter's, a copy of
                         the old starter refused in one line: GONE_METHODS); by_adapter (the Dataverse, SharePoint list, Delta and lake file
                         starters: the dry run the adapter's planned(), then its write; SqlWrite.by_adapter (the
                         adapter's statements and notes said; SQL Server and Trino count in a dry run only) and
                         FileWrite.by_adapter the SQL databases' and files'); write (sab.write: any connection, rows
                         of any shape or an open table's name, the adapter's five modes) and write_with (the
                         agent's connections_write runs it in a child process). Standard library only (the adapter
                         imported when a write runs)
  client/blades_client.py sab.load (a catalog), sab.blade (run a saved blade here), sab.blades, sab.read (a
                         table by a Python connection's own Read a table box), sab.table (an open table as its grid
                         shows it, through the adapter: Arrow, a plan folded by the app)
  client/api_client.py   sab.api(): the project's local sandbox API through the app (get, post, put, patch, delete);
                         sab.run(api, action, inputs): any API's action through api_adapter (POST /actions/run), its
                         envelope; sab.records(answer): its records as Arrow (api_adapter.table)
  client/connection_slot.py a Workbench kernel's query in one of its connection's slots (acquire, wait with its
                         place shown, renew, release); no gate outside a kernel or with no app
  client/connection_use.py a Workbench kernel's fire-and-forget count of a connection's call (a query, a read,
                         a connect) for the Connections page (nothing outside a Workbench kernel)
  client/structures_client.py sab.structure (a saved structure's value), sab.structure_table (its records as a
                         DataFrame), sab.show_structure (a dict or list as a Structures tab)
  client/completion.py   Tab completion of catalog names inside SQL in Jupyter and IPython (sab.complete)
  client/kernel_values.py what the kernel-side helpers share: a value's type name, is it a table, the user's
                         namespace (lineage_values.py keeps its own: a live page carries it as a file)
  client/kernel_errors.py the last error taken apart in the kernel (frames, columns, stack_data's values, facts)
  client/kernel_intel.py Jedi's answers (the member list, signatures, hovers): its Interpreter over a kernel's
                         namespace, asked in the kernel; its Script the server runs where no kernel has
  client/sql_cell.py     %%sql <connection> cells in Jupyter and IPython, sab.sql: a database in its own SQL,
                         files (CSV, workbook sheets, folders), DataFrames and the tables open in Grids (their
                         views, read when named) in DuckDB; %%dax
                         <connection>/<dataset> cells and sab.dax: DAX on one dataset of a Power BI workspace
  client/visualizations_client.py a figure, picture, table or text as a card on the Analyze board
                         (duck-typed); sab.visualizations and sab.sandbox, the old names, one release
  client/analyze_client.py sab.analyze: callable for a card; .<analysis>(df or an open table's name), .check,
                         .contract, .contracts, .sample: the page's contracts and checker, stats' functions
  client/watcher.py      a Python session's tables for the Open list (and, for the Environment, each variable's
                         name, type and size, never a value; after each cell runs, IPython's post-run hook, it looks
                         at once); an open one follows its variable
                         (never a table cell's own result: the grid would apply its steps twice)
  client/lineage_values.py  a value summarised for a lineage card (a table's shape and first rows), in the
                         kernel, and as sab_lineage.py beside a playing page (it notes each block's values)
  client/standalone.py   connections and blades without the app; a notebook run headless
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
  mcp/server.py          the stdio MCP server: one typed tool per command, generated from the registry (283 of them).
                         It holds no logic; add a command in cli/commands.py and it appears
web/src/                 main.ts (composition) + one module per panel; lazy/ holds Monaco, Vega, Mermaid
                         and Plotly (each loads when first needed; svgSafe cleans drawings);
                         lazyLoad.ts the one loader each for Monaco and the diagrams (loadEditors, loadDiagrams);
                         lazyPages.ts the rail's pages that load when first opened (APIs, Structures, Code App,
                         Source Control, Extensions: their names, whether a plug-in page is on, stand-in layers
                         (nav.ts registerLazyLayer), the shared cards' sync, what is heard before a page opens);
                         tourButton.ts the Projects page's Tour button (tour.ts loads on its first press);
                         nav.ts is getting around on every page and window (design principle 8.11): the mark
                         (the rail's first item: home, the Projects page; another window brings the home window,
                         named sab-home, forward showing Projects; Alt+Home),
                         views in the address (go: pushed for the user's moves, replaced for the app's; Back
                         and Forward are the browser's), layers (a dialog with views of its own, open=<key>:
                         Settings, Connections), every other dialog an entry Back closes, backButton (named
                         for where it goes), crumbs, setTitle (the page, then the place), app_navigate;
                         rail.ts is the slim icon rail down the left of every page and window, in the order of
                         the work (the owner, 2026-11-17; APIs beside Connections, 2026-11-18; 24px icons so more
                         fit, 2026-11-18; 2026-11-21: Home first, a house, "just call it home instead of projects";
                         Structures beside APIs; Scripts beside Blades; Catalog; Git): Home, Connections, APIs,
                         Environment (2026-11-22: it took the Structures and Variables places; the Structures page
                         stays as the viewer a structure opens into, off the rail; the Variables page went:
                         open=variables lands on the Settings and secrets tab), Catalog, Grids, ERD, Blades (the Scripts page's Blades pane),
                         Scripts, Notebooks, Canvas, Widgets, Analyze, Session, Settings at the
                         bottom: a click is a nav.ts move in this tab, and every icon lands on a page (no
                         dialog, no menu); the current area marked; Open in a new window on request; always
                         there (no switch), and the top tabs and the Application row no longer repeat its
                         areas (the owner, 2026-11-16); pageActions.ts the buttons an on extension adds to a
                         base page (the mode's page_actions: label and icon as data; a click runs the plug-in of
                         that id); extensionsPage.ts the Extensions page (open=extensions,
                         above Settings: a card per extension, Install's progress through the restart; a folder
                         extension's card from its data: Installed (folder), its path, Remove, Show its folder,
                         its error with Load again, its packages through the missing-package prompt; New
                         extension… in its heading);
                         library.ts Settings' Team box (Join a team…, Start a team…: one dialog of steps; the
                         Joined row: Pull, Push, …; Advanced: the two folders; Set up this computer) and the
                         notices said once (the move, a team library, a pull's catalog change; a kept step
                         opens Settings on the flow); areaPage.ts is a page of the rail's over any page
                         (Settings, Connections, Session: open=settings, open=connections, open=session; Projects
                         over the home page only, open=projects); projectsPage.ts the Projects page (the rail's
                         mark, 2026-11-18: the Project Explorer and the tour; the app opens on it with no table and
                         no project; /workspace?view=start lands on it; it makes way for a project opened there or
                         a table that arrives); keyVaults.ts the key vaults on the Environment's Settings and
                         secrets tab (a card each, Read again, Add key vault: moved from the Variables page, which
                         went 2026-11-22); dataPage.ts the Data Catalog page (open=data, the rail's Data Catalog, after Variables on the rail: the one place to browse and find tables, dataBrowse.ts its tree and a table's detail); sessionPage.ts the Session page
                         (this session's log, live, each entry a link; The agent / Me / Both; Changes, each change's words under it; Follow the agent: main.ts brings
                         the grids, Analyze and the ERD to the front, workbenchPage.ts a cell; never while the user
                         types; the rail's count); findConnections.ts the Connections page's Find connections on this computer… (the scan gated
                         with Cancel, the list: search, Select all, Already added, no connection yet, the amber mark;
                         Import); connectionsWindow.ts the
                         Connections page (cards, a card's detail: references, configuration, calls; no APIs);
                         callFigures.ts a connection's or an endpoint's running figures, small and out of the way
                         (the card's "usually 140 ms", the detail's Calls, the APIs page's What it answers line);
                         connectionSlots.ts a card's live "Running 3 of 8 · 1 waiting", the detail's limits and
                         Queries in progress…; queriesWindow.ts the Queries window (?panel=queries&connection=:
                         running and waiting queries, the SQL highlighted, Cancel, Finished); slotWait.ts a
                         page's query waiting in a connection's line, for loading.ts's words and Cancel;
                         connectionAccess.ts a card's Access section (what its app registrations reach, when and
                         where checked, Check again);
                         connectionTree.ts a connection's tables as a tree in its detail (search, Open, Preview,
                         Copy name, Open all, Import its relationships, Query in a notebook); connectionSql.ts the
                         connections a DuckDB query names (a SQL cell's head) and their completion;
                         workbenchLanding.ts a kind's landing page in the Workbench (?kind=notebook&view=list:
                         its documents as cards, Scripts' and Notebooks' Transformations cards first, Notebooks'
                         under Data notebook and App notebooks; New and Open… in the top bar);
                         aiPanel.ts is the Analyze board (a 12-column dashboard of resizable cards; an
                         analysis's cards land at its top and are marked; a result's actions under its card);
                         analyzePage.ts the Analyze toolbar (every analysis, grouped, everyday words first) and
                         its one form beside the board (the table line with Change, the columns as chips, Make
                         it fit with Apply, one sentence, Run gated with Cancel, More options, What your data
                         should look like with Try it on this sample; What can I do with a column?; Check this
                         table; Run again; no rule of its own: all from POST /analyze/plan);
                         analyzeMenu.ts sendCards (a profile, a value, a row sent to the board by hand);
                         analysisCards.ts those cards (a column's profile, the table's, a value, a row);
                         sandboxDashboards.ts saving and opening the board as named dashboards;
                         sandboxThemes.ts the board's own theme (tokens on its element only);
                         sandboxPages.ts Page view, Print to PDF and moving cards; sandboxExport.ts the
                         markdown export; cellMenu.ts the right-click menus on cells and headers
                         (Copy, Copy with headers, Copy as Markdown); headerCard.ts a column's numbers on
                         resting over its header (its profile: range, blanks, distinct, a histogram);
                         tour.ts is the first-time tour (on the Projects page only: a card per
                         place in the rail's order that goes there and lights up the real control,
                         two made-up tables staged and closed again, back to where it started;
                         nav.ts returnTo; loaded when first opened);
                         catalogRail.ts (the blades list, its "…": import, export, blade folders; the
                         catalog tree only where a page gives it a place: the Workbench's "+ Table") is the
                         Scripts page's Blades pane (the blades page went 2026-11-21: /catalog redirects there,
                         ?blade=<name> that blade's tab); bladeEditor.ts is the
                         blade screen, an IDE on codeIde.ts, and New blade; its pieces mount on their own in
                         another page's tab (bladeProperties: the header and the live table-name check;
                         runBladeCode into codeIde.ts's runPanel; watchOutsideEdits: Reload / Keep mine;
                         bladeEditorIntel; saveBladeAs; newBladeDialog: a name and a kind); codeIde.ts a page that is an IDE for one piece of
                         code (the slim bar, Monaco with the host's intelligence, Properties, runPanel: Output
                         | Result | Problems, resizable, folded until something runs; design principle 8.14);
                         bladeLibrary.ts is import (review first), export and the blade folders dialog.
                         connectionsWindow.ts's forms (a form per type) open in the Connections page;
                         addApi.ts is Add API (an OpenAPI document or endpoints, the sign-in, the preview), on the
                         APIs page; apisPage.ts the APIs page (open=apis: cards, search, the explorer, Author a
                         call, Refresh's diff); apiLearned.ts each operation's What it answers (api_adapter's learned
                         shape, maps to, drift marks, rename offers, Run, Build: a cell into data.ipynb, a
                         function into a picked script, opened there) and Discover (its Allow said, Take it
                         back); actionPicker.ts the one action picker for any API (the canvas's endpoint
                         property, In source and Event call: grouped by API); structuresPage.ts the Structures page (open=structures: tabs, the
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
                         recent folders per kind, breadcrumb, filter, New folder, hidden files, the keys).
                         shareApp.ts Share… for any running app (openShareDialog(app), shareMark(app);
                         globalThis.sabShare): the sentence, Install now, Sign in with your work account (or a code),
                         Share, the link with Copy and Open, Your organization, the amber note, Stop sharing; the
                         Shared mark beside an app's Launch / Stop. missingPackages.ts is the one missing-package
                         prompt ("<Feature> needs <package>": Install now, Not now; the reminder after
                         Not now, no nagging this session), used by every place that finds one;
                         emptyState.ts an empty page that leads somewhere (one sentence, the primary button, Try
                         it with sample data: Connections, Variables, Session, the Workbench's landing pages);
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
                         card; pictures go to Analyze), workbenchGroups.ts (tab groups as VS Code's
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
                         workbenchMenu.ts (its drop-
                         down menus), workbenchAgent.ts (right-click, Send to the agent),
                         workbenchPages.ts (Notebooks and Scripts, two pages: the page of a file or a kind, this
                         window's, openOnPage and bringPage by the windows' names, the old session split once);
                         codeExplorer.ts (each page's explorer on the left: the server's groups, a module's outline
                         as typed, marks, search, New; folds to a strip with Ctrl+B and resizes; on Scripts, Blades
                         below with a splitter); workbenchIde.ts (the Scripts IDE's F12, Shift+F12, F2, Shift+Alt+F
                         and Ctrl+Shift+F over /scripts/*; the tree's Rename with its imports' preview,
                         Duplicate, Delete, New package; a library's file read-only on F12);
                         workbenchDebug.ts (the debugger: gutter breakpoints, conditional and log points, the
                         panel under the code while debugging: call stack, variables, watch, output, console);
                         workbenchCommands.ts (every window action by one name: the palette (recent first), the keys (? lists
                         them: the shortcuts sheet, the grid page's too), and
                         the agent's workbench_window), workbenchNotebook.ts (cells, Jupyter's command
                         mode), workbenchScript.ts, workbenchConsole.ts (each document's console),
                         workbenchKernel.ts (runs), workbenchOutputs.ts (outputs drawn as they arrive:
                         colours, `\r`, caps, input boxes), workbenchErrors.ts (the error panel: Visual
                         Studio's Exception Helper; squiggles, hover cards and Ctrl+. fixes in the editor),
                         workbenchCompletion.ts, workbenchIntel.ts (the editors' intelligence: the member
                         list with its documentation panel, parameter info, quick info, the lint as you type,
                         the status bar's Problems count and list, the Ruff offer), workbenchEnvironment.ts,
                         environmentPage.ts (the Environment: the rail's page, open=environment&at=<tab>&name=<row>,
                         and the Workbench's right pane, environmentPane: tabs by kind with their own columns, one
                         search over every tab, rows that unfold, the viewer beside the list (Ctrl+B), Used in
                         links, Remove with the Python tick, Rename, Clear…, Keep, Libraries' Pin, Update and
                         Install through missingPackages.ts; the Settings and secrets tab's key vaults and Add
                         key vault; the Libraries tab's line about the project's Python; follows
                         environment_changed, no Refresh; it replaced workbenchVariables.ts and the Variables
                         page), projectSession.ts (one Python per project as the pages say it: the project's
                         Python's state and its one line, Make it now, a notebook's older environment offered;
                         workbenchKernel.ts holds the project's one session for each of its documents: Python
                         session in the status bar, Restart asked first, every window told), lazy/codeEditor.ts (Monaco: line edits that keep the
                         cursor, cell links, a script's folds and marker notes),
                         workbenchTables.ts (every table's read-only cell: its state against the text it
                         last ran, the folded lines' words, the uses line); the Tables group, cell
                         numbers and @cell links are drawn in workbenchNotebook.ts and workbenchScript.ts;
                         workbenchHtml.ts (HTML cells: the design's pane that resizes, its sandboxed
                         frame, the names filled by the server's rules, the out-of-date state);
                         a DAX cell (its dataset picker, Monaco's DAX grammar) is drawn in
                         workbenchNotebook.ts, its completion in workbenchCompletion.ts;
                         workbenchLineage.ts (the Lineage overlay: Mermaid flow, a value card per step;
                         window.openLineage);
                         cellClipboard.ts (a cell's name as typed, a script marker's words, a copied cell
                         pasted in any window; no live Streamlit cells: app notebooks went, 2026-11-21);
                         projects (New project, Open project, Export data.py) are in workbenchPage.ts;
                         kindColours.ts the kind colours (fixed: grid.css's tokens) and a
                         notebook's kind (in a project data.ipynb the data notebook; every other plain:
                         notebookRole, kindIcon);
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
                         startView.ts the New query page (/workspace?view=grids, view=new over grids: the grid page with no table
                         open, and the tab row's "+", Ctrl+T, Ctrl+N; the owner, 2026-11-20): Open tables (DuckDB)
                         first while a grid is open, then each connection that runs SQL (queryTab.ts
                         queryConnections, Query from's one list: its kind, colour, a password missing here); a
                         click or Enter opens the draft with Query from set (panes.ts openQueryDraft; the agent's
                         app_navigate query:<connection>); arrows move, a search past 8; no connection: the empty
                         state; the project's tables to fix below; queryTab.ts the draft (the SQL tray over a
                         blank grid) and a built table's tray; the project's group in the
                         Application row (Save, Copy to…, Close, Autosave) and the strip of tables to fix;
                         connectionColours.ts each connection's colour worn by whatever names it
                         (data-connections): its own box (a card, the Data Catalog's row, a tab group's head) as
                         its border and a light tint, what names it (tabs, cells, Session entries) as a stripe;
                         the swatch and palette on its detail; dom.ts dateTime and plural, the pages' one date
                         and one count; panes.ts groups the home page's tabs by connection;
                         localApis.ts the APIs page's Local sandbox APIs (one slim bar: name, where it runs, the
                         agent's session writes with Stop, Run / Stop, Open API.py, Properties folded: target, base
                         path, description; "…": New endpoint…, Will this work for real?, Export (its target said,
                         never asked); endpointsPane: API.py's Endpoints panel on the Scripts page (New endpoint…
                         there too); each endpoint labelled by the pattern that made it;
                         endpointWizard.ts New endpoint, the ONE wizard (a sandbox table, the patterns ranked by its
                         shape with one sentence why, that pattern's own steps drawn from its data, the code kept
                         current, Add to API.py; no rule of its own: POST /local-api/plan);
                         each endpoint's data words and Try it (the server's made-up request; a refusal as the one
                         error note with API.py's line; kept open over a redraw), problems with Go to line, the
                         request log and Output); on the Scripts page API.py's main Run is Run API and it takes no
                         Tables group (workbenchPage.ts isApiFile);
                         dataSandbox.ts the project's sandbox (Make a sandbox variant… for the grid's Table row and
                         the Structures page; the APIs page's panel, also the Connections page's Sandbox page: tables
                         sorted by their headings, their mock clients and Mocked as, the variant's mark and origin,
                         Open in Grids, Reset, Set as baseline, checkpoints, the log); sandboxGrid.ts a sandbox
                         table's grid (the bar: designation, origin, Add row, Delete rows, Reset; a cell edited in
                         place through gridView.ts's registerCellEditor, a LIST/STRUCT/MAP cell a JSON box; the tab's
                         designation);
                         swapConnection.ts the Table row's Connection: <name> (a table read from another
                         connection, its steps kept: the chooser, the other's catalog to pick, the SQL window
                         ?panel=connsql for a query), the strip's Use another connection… and its Undo rows,
                         Point these at <name> (the cells that named the old one, ticked);
                         updates.ts the status bars' "Update available" (Update to X, What's new) and
                         Settings' Click here to update (only while one is available); desktopApp.ts is the page in the desktop app (window.sabApp:
                         the browser's keys are the app's there, Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+Tab, Ctrl+Shift+T;
                         closeWindow); fileChanged.ts a table whose file changed on disk (its tab's dot, its
                         pane's Changed on disk: Reload, Not now);
                         claudeLaunch.ts the status bars' Launch Claude (one found: straight to it; both: a
                         menu; none: the install help), Desktop's one question, Settings' Claude;
                         the Workbench's modes: workbenchModes.ts (each document's own panels beside it
                         in its group, the status bar's toggles), workbenchDocModes.ts (Notebook's Outline,
                         Script's Run settings, Data's Dictionary and Lineage's place)
                         The grid page has no SQL box and no steps panel (decision 13): stepsStrip.ts is the
                         strip under the title; stepsPanel.ts shows only in its own window (?panel=steps)
web/build.mjs            the page's build (npm run build, build:release, watch): each page (main, workbench,
                         perf) split on its own (chunks/<page>-<hash>.js: what loads when first
                         opened), lazy/* and the workers as before, grid.css minified into build/grid.css
web/static/              index.html, grid.css (all theme tokens; the pages load build/grid.css), build/
                         (gitignored); design.html is the
                         page an HTML cell's design is drawn in (sandboxed; its policy loads nothing
                         over the network)
tests/                   unit + HTTP tests, golden/ (shared cases), e2e/ (Edge via Playwright; e2e/conftest.py
                         holds the one browser of the run and the waits' 15 s), live_server.py (a real server in
                         a thread on a socket already bound, stopped within a second or two),
                         desktop_drive.py (the desktop app really run under Qt off screen: windows, downloads,
                         Print to PDF, outside links, the server stopping with it; test_desktop_shell.py runs it),
                         copilot_standin.py (GitHub's Copilot Language Server stood in for: stdio LSP, a made-up
                         device flow and made-up suggestions),
                         test_architecture.py (the layers, the depth, the plain client),
                         driver_check.py (stdlib only: every starter's code against its installed client: calls,
                         keywords, SQL Server's connection strings; test_connection_drivers.py runs it, again in
                         SWISSARMYBENCH_DRIVERS_PYTHON),
                         lake_standins.py (Entra, the ADLS Gen2 DFS API over a made-up lake, OneLake, and Graph
                         for a made-up SharePoint site, all on 127.0.0.1),
                         trino_standin.py (a Trino over HTTPS asking for a client certificate; made-up
                         keystores), powerbi_standin.py (Power BI and its sign-in stood in for on this computer: a
                         workspace of three made-up datasets), dataverse_standin.py (a Dataverse environment's
                         Web API, its metadata and its sign-ins: a made-up company's accounts, contacts and
                         opportunities), dataverse_tds_standin.py (its SQL endpoint at python-tds's seam: a
                         made-up SQLite file), sqlserver_standin.py (SQL Server at mssql-python's seam over
                         DuckDB, the rows kept: the adapter's T-SQL run there), test_sql_server_real.py (a real SQL Server when
                         SWISSARMYBENCH_SQLSERVER_TEST names one), orders_service.py (a made-up web service
                         on 127.0.0.1, for a Python connection), api_standins.py (Add API's made-up
                         orders service, every sign-in it takes stood in for), libraries_standin.py (uv and pip stood
                         in for, a made-up .venv (a project's own made too) and a made-up package index on
                         127.0.0.1: the Environment's Libraries tab, one Python per project), devtunnel_standin.py (Microsoft's
                         devtunnel stood in for: sign-in with a device code, tunnels, access, host's lines), github_standin.py (GitHub's REST
                         and Git Data APIs and the device flow over in-memory repositories of made-up files),
                         folder_extension_example/stockroom/ (a made-up folder extension, never shipped: a project
                         type with one deliverable, one route, one command; test_folder_extensions.py proves it)
tools/                   screenshots.py; testbed/: the real-world test bed (testbed.py up|down:
                         PostgreSQL and MariaDB on ports of their own, made-up files; company.py, the made-up
                         company; standins.py, Power BI's Company model and Azure Key Vault) for
                         tests/e2e/test_real_world.py (eleven use cases, action counts, agent parity; 11: a widget on
                         a canvas in both layouts, played, exported);
                         large_company.py, Larkfield Goods: a made-up retail business of 14 tables at three scales
                         (small 10k order lines, medium 1M, large 10M in about 30 s), DuckDB SQL over range() with
                         hash-based randomness, deterministic by seed, its deliberate problems in
                         data_quality_issues; Parquet (and --duckdb) to a folder outside the repository
                         (`python -m tools.testbed.large_company --scale large --out <folder>`)
plugin/                  the swissarmybench plugin: skills/swissarmybench-use (SKILL.md, guide), .mcp.json,
                         hooks/hooks.json (the prompt hook: what was sent to the agent, the table in front)
.claude-plugin/          marketplace.json: this repository is a Claude Code marketplace (plugin/)
examples/sample_store.py made-up nine-table store with a relationship answer key (test bed for autodetection)
examples/forms_recon/    the owner's first app POC as a test app, made by the app through the agent's commands: API.py
                         (forms with versions, entries stored long, a PIVOT column store, monthly reconciliations),
                         three canvas pages, widgets/api_bridge.widget.py (the project's own widget); its
                         pattern-shaped endpoints made by the wizard (a form picker's choices, a reconciliation's
                         runs, a run's counts by status, its results as a CSV file);
                         tests/e2e/test_forms_recon_app.py plays it; tests/stress/test_local_api_stress.py
                         (SWISSARMYBENCH_STRESS=1) loads it with Larkfield Goods; tests/test_sandbox_speed.py the fixes
build.py                 build the page (release) and the one wheel
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
                         it the app is the BI base: no Canvas, no Widgets, its tools and its door say which
                         extension they need. tests/conftest.py puts its src on the path and switches it on.
                         Widgets and the Canvas (the owner, 2026-11-21) replaced app notebooks, .stapp.json
                         canvases, live Streamlit cells, controllers and the designer (2026-11-21; the Performance
                         Analyzer and Builds came back on the widget Canvas, branch canvas-rest2)
  src/swissarmybench_streamlit/
    extension.py         ID, NAME, ADDS, MODE (the Streamlit project: its canvas, widget_framework, its tools),
                         STARTERS, SECRET_PATHS (/streamlit/run/); routes(services) its composition root (widgets,
                         canvases, live runs, previews; the base's hooks: an old app file said, a new project's
                         canvas, the outline's canvas pages); scaffold (data.ipynb and an empty canvas)
    commands.py          the agent's widgets_* and canvas_* tools (canvas_builds and canvas_perf by an action), app_launch;
                         OLD_NAMES (canvas_list, canvas_show, canvas_stop answer one release);
                         GONE: the old app canvas's
                         commands, each said gone (cli/commands.py gone_commands)
    domain/widgets.py    a widget's file (library/widgets/<name>.widget.py: a swissarmybench-widget TOML header,
                         its Streamlit code), the header rewritten alone, names checked (available, taken, invalid)
    domain/widget_properties.py  a widget's properties: its top-level plain values (ast), each typed with a mask
                         (switch, number with a range, text, colour, date, datetime, time, dropdown, table, column,
                         variable, path, JSON); an annotation wins; a value checked before it is kept and written
                         into only its own characters; the assignments made `pass` for the page to give the values
    domain/widget_contract.py  a widget's I/O contract (2026-11-21): `x: In[T]`, `y: Out[T]`, `z: Event[dict]` at the top
                         level, read with ast (Table, str, int, float, bool, date, datetime, File, list[...], dict), each
                         one's problem in a sentence; a typed payload (Event[Order]) and Table[Row] from the widget's own
                         TypedDict or dataclass (records: schema, fields); fits, fits_value; declarations made pass
    domain/canvas_wiring.py  the canvas's wiring (an instance's `wires`): an In's source (a table, an Out, a page value,
                         (an endpoint is any API's action through api_adapter: "GET /orders" the local sandbox
                         API's, "[Orders] GET /orders" a library API's: action_ref)
                         a GET endpoint, a variable, a value, tables), an Event's actions (call, set, rerun), each
                         checked with the reason; any page's Outs (every_out: an app-wide value, a wire from another
                         page `cross`) and the app's own app.viewer; automatic wires by name (this page), readers,
                         broken wires, each Out[Table]'s columns (declared, else as Play last saw them), the run order;
                         pair_for (a widget just inserted and the endpoint a wizard's pattern pairs with it: the one
                         match, else the one over the table its nearest neighbour uses, never a guess)
    domain/widget_upgrade.py  Upgrade to In/Out: a widget's session state keys rewritten as declarations (a preview)
    domain/canvas_model.py  the canvas file (<app>.canvas.json, byte-stable; pages of containers holding containers
                         and widget instances; the pixel engine at one layout's design width; sizing: columns, row
                         height, gap, snap, step) validated on read (its line; newer: read-only; a missing widget a placeholder), the
                         layout's rules (problems: no overlap, nothing leaves its box, minimum sizes), the commands
                         (add_container, insert_widget, move, set_container, set_values, replace_widget, delete,
                         sizing: columns re-flow, pages), prune, rename
    domain/canvas_layouts.py  the two layouts (Phone, Desktop; format 2): each item's place per layout as fractions of
                         its parent's width (x, w) and pixels (y, h), show (both, desktop, phone), a widget's or a
                         container's hidden (Hidden in the app: the hide command); a layout viewed in
                         pixels for the engine and written back; an item new to one placed in the other (phone:
                         stacked full width); format 1 read as desktop; problems in both
    domain/canvas_build.py  the ONE page builder (Play, Launch, a widget run alone, a preview, Export): app.py,
                         (every built app carries api_adapter.py, sab_actions.json and a library API's client:
                         `carried`; the runtime's action(endpoint, inputs) is api_adapter's run, its envelope;
                         said, data, takes; api_call the older form)
                         app_pages/<page>.py (each box an st.container placed absolutely by its key's CSS: fractions
                         of its parent's width, pixels down; the phone's places under a 767 px media query), sab_widgets.py (the widgets inlined), sab_canvas.py (RUNTIME: render each widget in its
                         place, its failure there, its Ins, Outs and Events wired; table, sample(kind), var, key, choices,
                         marked, problem, api_call, File and as_file, viewer (name, email, id, roles): App Service's
                         sign-in headers on App Service (X-MS-CLIENT-PRINCIPAL's claims), st.user, SAB_LOCAL_VIEWER in
                         Play (the name only), else "unknown"; the app's Outs app.viewer, _email, _id, _roles; each
                         Out[Table]'s columns noted in Play and Launch, .sab_columns.json); a widget or a container
                         Hidden in the app (and a container of only such) taking no space; a container's title in the flow, its widgets in a box below it; the kernel's setup
                         Export folds Play's files into the fewest (folded: app.py holds the pages as functions,
                         the layout, the wiring and the runtime; widgets.py the widgets; sab_actions.json inside
                         app.py, folded_actions reads it back); a `[Conn].table` in an export read through adapter.py
                         and connections.py beside it (_connection_table, kept with cache_resource)
    domain/builds.py     Launch's builds (builds/<app>/<n>/ at the project's top: the files, canvas.json, build.json):
                         what changed between two canvases in words (canvas_changes), a build's widgets read back
                         with ast (widget_code), compare file by file
    domain/perf.py       the Performance Analyzer: a protobuf wire reader (a ForwardMsg's kind, element and path, a
                         BackMsg's rerun and widgets: never content), the socket per rerun, the page's records joined
                         (each block a widget instance), the caches, the hints in plain words
    adapters/widget_files.py  the open project's widgets/, the library's and the prebuilt ones (PLACES, in that order: a
                         project's name wins); a canvas file read with a stamp, written
                         atomically only when it changes, a broken one's copy; the previews' cache (by hash, theme)
    adapters/streamlit_files.py, build_files.py  a run's temporary folder and an export's; a build's folder
    services/widgets.py  Widgets: list (This project, Library, prebuilt; `where`, `hides`), get, new (where), save
                         (where it lives), header (a rename follows every canvas), properties live, set a default,
                         check a value, copy (Copy to project / to library), project_widgets (an export's widgets/),
                         delete (the agent's on Allow), Run in place, the
                         headless check, previews' state
    services/canvas.py   Canvases: open (validated), command (versioned: another window's change refused with the
                         canvas as it is now; a file changed on disk read first), undo, redo, state (missing, marks,
                         notes said once), play, check, export (the agent's on Allow), replace (one change: a
                         build's Restore), rename_widget; an inserted widget wired to its pattern's endpoint in
                         the same change (paired: the base's local_api.paired)
    services/launch.py   Launches: Launch (a build, then its run with sab_perf.py beside; analyzer from the first
                         load), Relaunch, Stop, builds (list, files, compare two or with now, Restore), the analyzer
                         (attach, the proxy's tap, session, hints, save into the build, a saved one)
    services/open_tables.py  the open tables' names and columns (the pickers, a value's check) and Parquet
    server/live_runs.py  LiveRuns: a widget run alone and a canvas's Play, each a Streamlit process passed through
                         at /streamlit/run/<key>-<secret>/; check: the pages headless with AppTest (CHECK_RUNNER);
                         `ended` (a run stopped or written again: a share of a launch ends), `launched` (its folder)
    services/sharing_target.py  Share… for a launched canvas app (the base's ShareTarget): a shared run of the
                         launch's folder on its own port at the root (SHARED_FLAGS), closed when the launch ends
    server/previews.py   each widget rendered once off screen (Play's builder and run, Qt WebEngine photographing its
                         box), one at a time in the background, kept by its file's hash and the theme
    server/streamlit_apps.py  a Streamlit process: `streamlit run` in the project's Python, 127.0.0.1 only, ended
                         with the server (Streamlit is never the app's dependency); install
    server/sab_perf.py   copied beside a launch's pages only: each rerun's trigger, each widget's time (sab_canvas.render
                         calls it), calls, caches; one JSON line a rerun, only while sab_perf.on is there
    server/routes_widgets.py, routes_canvases.py, routes_launch.py  /streamlit/widget (the window),
                         /streamlit/widgets/*, /streamlit/canvas (the page), /streamlit/canvases/* (…/launch,
                         …/builds…, …/perf…), /streamlit/perf (the analyzer's window)
    domain/widget_packs.py  the widget starter packs (2026-11-21): their order and descriptions; a prebuilt widget
                         names its pack in its header (`pack = "..."`); listed first, each under its heading
    widgets/             the 113 prebuilt widgets (read-only; each run with AppTest by tests/test_widgets_apptest.py),
                         53 of them in eight starter packs (sales_, ops_, cs_, de_, admin_, input_, excel_, form_);
                         four, api_*, call the local sandbox API
    starters/            the Streamlit, Components, Controllers and Text and layout starters (52)
web/src/widgetPage.ts    the Widgets window (static/widget.html, no rail): the list (This project, Library, prebuilt),
                         Copy to project / to library, Monaco with the Workbench's intelligence over a kernel of its
                         own, on codeIde.ts; Code | Preview (F5 Preview, Esc Code; a failure's error panel with Go
                         to line; remembered per widget this session), Properties (Name checked live, Description,
                         each property's mask); its panes fold (Ctrl+B)
web/src/widgetPacks.ts   a widget's heading in the lists (its pack, else its group) and a pack's description line
web/src/widgetFields.ts  one property's box by its mask (the Widgets window's and the Canvas's Properties; endpoint:
                         a picker of API.py's endpoints; path_values: a box per {name} of its endpoint's path, a
                         value, a variable or a page value each); a table's
                         picker grouped: sample, open tables, data.ipynb's, each connection's [Conn].table (typed
                         when its catalog is not listed yet)
web/src/canvasPage.ts    the Canvas page (static/canvas.html, with the rail): page tabs; the board (draw, move, size,
                         nest, snap with guides, nudge, zoom); right-click Insert widget; the Properties and Widgets
                         panes (hideable, resizable, a card's hover preview; Show on, Hidden in the app: faded, eye-off); the top row's Play (F5; its ▾:
                         Launch Ctrl+F5, Launch with the Performance Analyzer Ctrl+Shift+F5, Share… while launched,
                         Builds…; Stop while running) and Export (Ctrl+Shift+E), also every right-click menu's last group; the
                         bottom bar (sizing, Desktop | Phone and the preview width, Snap and step, Undo, Redo, the
                         panes' toggles, zoom); the frame's right-edge width
                         handle (px shown); versions and notices
web/src/canvasWiring.ts  the Canvas's Inputs, Outputs and Events sections (a source picker: Sandbox first, this page's,
                         another page's by its name, The app's viewer; readers; actions with a typed payload's fields),
                         the board's marks (sources, readers, broken) and the Wiring view: port dots on each widget's
                         edges, lines from the exact Out port to the In port, another page's wire a stub with its name
web/src/canvasGrid.ts    the Canvas's placement maths: the step, the grid's lines, edges and centres, nudges, dots
web/src/canvasBuilds.ts  the Canvas's Builds (newest first, what changed; Compare two or with now in Monaco's diff
                         editor; Open; Relaunch; Restore) and the analyzer's window (analyzerAddress, openAnalyzer)
web/src/perfPage.ts      the Performance Analyzer's window (static/perf.html, ?canvas=): Timeline, Calls, Cache, Web
                         socket, Hints; Pause, Clear, Save into the build; a saved session read-only
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
web/src/extensionArea.ts an extension's rail area with a `panel` route (GET /app/areas), drawn as a page of the
                         rail's from that data (the Power BI page), generic
web/src/gates.ts         a project type's gates (GET /app/gates): a closed area hidden on the rail, one line with Open
                         every feature on any other way in (the palette's commands and the Workbench's New entries
                         by their area: gatedRun; an address on a closed area covered by it: a popover over the
                         page), Settings' switch, the first-open pop-up once per project, the mode's own tour cards
web/src/areaMarks.ts     the footer's marks an extension's area answers (GET /app/areas' mark route), generic
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
extensions/powerbi/       the Power BI extension (swissarmybench-powerbi; entry point powerbi =
                         swissarmybench_powerbi.extension; project type powerbi, keeping some
                         features closed; a Power BI rail area drawn from data; in the Extensions catalog)
  src/swissarmybench_powerbi/
    extension.py         ID, NAME, ADDS, AREAS (powerbi_), PAGE_ACTIONS (the ERD's Export to Power BI…, as data),
                         SESSION_RULES; routes(services) its composition root; commands
    commands.py          powerbi_export (dry_run: what would go); Open in Power BI Desktop is the user's click;
                         powerbi_import_project, powerbi_file, powerbi_setup_status, powerbi_source,
                         powerbi_app_registration, powerbi_edit_files/_model/_plan/_apply
    domain/pbix_file.py  a .pbix as pbixray reads it (tables, M, relationships, measures, parameters, last refresh;
                         a thin report's dataset), the .pbix file connection's three boxes, its card's words
    domain/pbix_import.py a .pbix planned as a project (connections reused or made, variables, the dataset found or
                         asked, the paired grids' names, data.ipynb, .sab/powerbi.json, the round trip's M), To
                         finish setting up's rows
    domain/live_link.py  Edit in Power BI Desktop: port files and command lines read, Live / Not open, the allowed
                         changes (Microsoft Learn's external tools page), the dry run, our relationships and measures
    adapters/pbix_reader.py pbixray's frames as the domain's model (the reader seam tests fake)
    adapters/live_link.py the running Desktops found (Windows), the model client libraries fetched once (pinned,
                         hash checked), TomModel (pythonnet: metadata, DAX, edits)
    services/project.py  the Power BI project: the import, the .pbix connection, Read Power BI from (the project's
                         one dataset connection name resolved through it: DatasetAlias), To finish, the app
                         registration's re-pointing (every Microsoft kind), the Power BI page as data
                         (/powerbi/panel: Edit's dry run as `review`, another report's pages as `open`), the round
                         trip's inputs for the export (kept), a file opened with the app
    services/live_link.py discovery every 15 s while wanted (a notice, never a request), the model, plan, apply
    server/routes_project.py /powerbi/import, /powerbi/file-connection, /powerbi/setup, /powerbi/source,
                         /powerbi/registration, /powerbi/page, /powerbi/panel, /powerbi/opened, /powerbi/live/*
    domain/power_query.py Power Query (M) for a table's source, table driven (KINDS: SQL Server, PostgreSQL, MySQL,
                         Snowflake, Databricks, Oracle, Dataverse, SharePoint, CSV, Excel, Parquet, lakes); `${NAME}`
                         as parameters; a grid's steps as the source's SQL by sqlglot (or why not); M read back
    domain/report_swap.py another report's pages: a .pbix/.pbit's report part read safely (Report/Layout in UTF-16,
                         PBIR definition/, StaticResources; never DataModel), the fields its visuals, filters and
                         slicers name, the mapping by name (any case), every reference rewritten, the model's
                         measures (a .pbit's DataModelSchema, a .pbip's TMDL, a .pbix's through pbixray) brought
                         along with their DAX rewritten, an unmapped one said
    domain/export.py     the model as a Power BI Project (.pbip): types, the relationships and the one-active-path
                         rule, TMDL and the PBIR files byte-stable (CRLF, uuid5 lineage tags), stale files
    adapters/report_files.py a dropped report read (a zip's wanted parts only, a .pbip folder's files), a .pbix's
                         measures by pbixray (imported there only; never its rows)
    adapters/files.py    the export's folder: written only when bytes change, stale files removed, the zip, the
                         .pbip opened with its program (Windows) or its folder shown
    services/export.py   plan (the ERD's tables, why one cannot go, Include its rows), export (the project's
                         powerbi/, or a zip; rows on the agent's Allow), open (the user's click)
    server/routes.py     /powerbi/plan, /powerbi/export, /powerbi/report (a dropped file's bytes), /powerbi/open
web/src/powerbiExport.ts (a plug-in) the ERD's Export to Power BI… dialog: the tables with ticks, why one cannot go
                         and Include its rows, the relationships, Use an existing report's pages (drop or Choose
                         file…; its fields mapped, a picker or Leave it), Export, Open in Power BI Desktop
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
web/src/canvasSnap.ts    snapline maths over rectangles (guides, snapped, equalGaps, sameSize, inBand): pure,
                         tested as the page runs it (tests/test_canvas_snap.py: esbuild and Node)
web/src/inlineCompletion.ts ghost text from the provider the mode declares (`inline_completion`: its routes): the
                         ask (cancelled with Monaco's token), the shown/accepted/partial report, the status bar's
                         "Completions: <name> · on/off" (a click toggles); lazy/codeEditor.ts registers Monaco's
                         inline completions provider for Python and SQL (an editor's `inline: inlineSource(...)`)
web/src/extensionPanel.ts an extension's panel drawn from its data (lines, switches, actions with notes, choices,
                         rows to work through, a code and a page to open, a dry run to review and Apply, a plug-in opened
                         right there: pageActions.ts openPlugin): on its Extensions card and in Settings; projectFile.ts privateSwitch (the project
                         group's Private: POST /project/private)
web/src/codeAppPage.ts   (a plug-in) the rail's Code App page: tools, sign-in, project, connectors (the APIs
                         explorer's look), Run live's pane, Push, custom connectors, runs; shown while on
web/src/routedCells.ts   a cell another kernel runs, by the routes the mode declares (MODE cell_routes): a run's
                         stream, a TSX cell's page, Open as grid of a table result, the editor's declarations
web/src/workbenchCodeFile.ts (a plug-in) a code app's file in the Workbench's editor: Monaco's TypeScript
                         service (ts.worker.js) over the project's files; New TypeScript file in the code app mode
```

## Commands

See [README.md](README.md). Before a commit: `pytest -q --ignore=tests/e2e -n 4 --dist loadfile` and
`pytest -q tests/e2e -n 2 --dist loadfile` (pytest-xdist; plain `pytest -q` runs it all in one process),
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
