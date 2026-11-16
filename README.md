# Swiss Army Bench

A local server that shows any tabular data in live browser grids, with analysis built in. You
push a DataFrame from Python and get a URL; open it in Chrome, Edge or VS Code's built-in
browser. Everything stays on your machine: 127.0.0.1 only, a token on every data request, data
in memory, nothing sent anywhere.

What a grid page does:
- **Grid:** scroll millions of rows (the server sends only the rows on screen). A header can
  show its column's distinct count, blank percentage and a small histogram (the switch is in the
  grid's top-left corner, above the row numbers); its arrow button sorts on the server. Enter or
  F2 on a cell opens its whole value. The horizontal scrollbar is always on screen.
- **Excel-style selection:** click or drag the row numbers to select rows, a header to select its
  column, drag across cells for a block, the corner (or Ctrl+A) for everything; Shift extends,
  Ctrl adds. The status bar shows Count, Average and Sum over the whole selection, loaded or not,
  and Ctrl+C copies it as tab-separated text.
- **Ribbon:** the transformation tools grouped by what they act on: **Table** (filter, sort,
  columns, group by, distinct, profile, analyze, export) and **Column** (sort, filter, rename,
  remove, keep, clean, bucket, categorize, group by and profile, for the selected columns); a
  cell's tools (keep or exclude rows with its value, view, copy) are on its right-click menu.
  **Ctrl+Shift+P** lists every action of the page by name.
- **Steps** (like Power Query's applied steps): filter, sort, choose and rename columns, group
  by, distinct, keep first rows, clean text, bucket, categorize and SQL. The grid has the whole
  page: a strip under its title counts the steps (a header sort among them), lists them on
  hover with a remove button each, and offers Undo, Redo (Ctrl+Z, Ctrl+Y) and Clear; **Edit steps** opens
  Table Transformations in a tab of its own, where each step can be edited, turned off or reordered, with row counts as it goes.
- **Cell viewer:** double-click a cell. JSON objects and arrays show as tables you can open one
  layer at a time, markdown is formatted, and long text wraps.
- **Text matching** (the ribbon's Table row): Match case, Wildcards (`%` only, as in SQL LIKE),
  Trim, Empty = blank.
- **Column profile:** a popup from the Column row's Profile: statistics and value counts; click a
  value to filter on it. **Auto width** fits every column (Table row) or the selected ones.
- **SQL lives in your Python** (DuckDB SQL does the transforming): **every table has a read-only cell**
  in the Workbench notebook or script it belongs to, holding the grid's steps as one DuckDB query
  whose result is the table's own name (`orders = duckdb.sql("""...""").df()`). The cell follows the
  grid by itself and turns yellow (Out of date · Run) when the steps change; nothing runs by itself,
  and running it twice never transforms a table twice. All tables sit at the top of the file in a
  Tables group that folds to one line. Every cell has a number that never changes, `@cell7` in a
  comment links to it, and a cell that names a table starts with `# uses orders @cell3`. A SQL step
  (Edit steps, Add a SQL step) is one guarded SELECT over the table entering it.
- **HTML cells:** a notebook or script cell that holds HTML and shows it as a design in a pane that
  resizes: the HTML while you edit it, the design when you leave it. Its scripts run walled off from
  the app and nothing loads from the internet. `{{ total }}` is filled with a Python variable when
  the cell runs (a value as text, a table as its first 50 rows); such a cell turns yellow (Out of
  date · Run) when its HTML or a variable it names changes. In a notebook file it is a `%%html` cell.
- **Streamlit apps:** a data-first way to build one. A Python cell that calls Streamlit shows live in
  its cell; any open table is there by name as a DataFrame. **New app** opens a canvas as a Workbench
  tab (its own file, `sales.stapp.json`): drag any Python cell onto it, or copy and paste it, and it
  becomes a block that links to the cell, on a 12-column grid, on as many pages as you like. **Play**
  shows the page live in place; **Edit** goes back to the blocks. A cell that makes a name
  (`region = st.selectbox(...)`) drives every block on the page that reads it. **Export** writes a
  folder that runs on its own; **Save as zip** zips the project to add to your own app. Streamlit runs in
  the notebook's own Python and is not installed with the app. Cells can be named; the Data panel's
  **Streamlit cells** lists every cell that calls Streamlit by name, to drag onto a canvas. Any tab
  pops out into a Workbench window of its own (its unsaved changes and kernel go with it), and back.
- **Panels:** Settings can switch off any panel of the Workbench or the grid page; every one is on
  again the next time Swiss Army Bench starts.
- **Projects:** a folder that starts with the data. `data.ipynb` is where you work on the tables and
  variables; `data.py` is its export, and what your notebooks and pages import (`from data import
  orders`). The app's canvas exports `pages/*.py` the same way.
- **Export as one Python script… / as one notebook…** (a document's **…** menu): any notebook or
  script as ONE self-contained file for a scheduler or an Azure Function: its connections, key vault
  lookups and grid steps (as DuckDB SQL) written out, no Swiss Army Bench, no passwords, no rows.
  `python orders_report_automation.py` checks its packages first (`--install` pips them), names every
  setting it reads and where it came from, and has a `main()` for a timer trigger; an Azure Key Vault
  is read by the function app's managed identity with the standard library. The notebook runs top to
  bottom with nbconvert or papermill.
- **New table from a query:** the **+** after the last tab opens a SQL tray over a blank grid.
  A table name reads that table as its tab shows it (after its steps); Run turns the result into a
  table of its own, with every tool a pushed table has. The tray stays on the tab, so Run again
  rebuilds the table in place, and its own steps apply to the new rows.
- **Copy transformations as SQL or Python** (the steps window's Code tab, for a Python outside the
  Workbench): the view's steps, SQL steps included, as one DuckDB
  query over your own table by its variable name. **Copy as SQL** gives the query; **Copy as
  Python** gives `import duckdb` and one line, `orders_view = duckdb.sql("""...""").df()` (`.pl()`
  for Polars, `.to_arrow_table()` for Arrow). The copy is run exactly as copied, in a fresh namespace holding only your table,
  and compared with the grid before it's offered; only verified code gets the Copy buttons.
- **Relationships and tangs:** **Find relationships** works out how every open table joins, from
  the data: each join with its kind, the share of values that match, the orphans and why (names that
  don't match, a text column of numbers, two-column keys and second paths are handled; small number
  columns that overlap by accident are not suggested). Accept the joins, **Run** them to see which
  hold, and **Save as tang**: a `.tang` file with a name, description and tags, kept in your tangs or
  in a shared folder (the blade folders), where your coworkers' Relationships window lists it.
- **Packs:** blades and tangs a team keeps in a GitHub repository that is also a Claude Code plugin
  marketplace. Install a pack with `/plugin install` and its blades and tangs show up, marked with the
  pack; `/plugin marketplace update` brings the team's latest.
- **Analyze** (the Table row): analyses that hand off to each other, to help predict a metric. **Odds**:
  how often each value shows up, and with an outcome, each value's odds of it against the rest ("West:
  late 46% of the time, against 15% elsewhere: 4.85 times the odds"). **Find predictors**: every column
  tested against a target by chi-square, ranked by strength, with the pairs that say the same thing.
  **Fit test** and **Outliers** (below). **Show the math** on any result puts its proof in the Sandbox:
  each formula with the result's own numbers, worked to the values shown. Every result can go to the Sandbox, open as a grid, or go to
  the notebook as Python (`swissarmybench.stats`, the same code the window ran). **Regression**: linear or
  logistic (odds ratios), effects in words with ranges, what-if predictions, predicted and miss columns,
  and Check the misses (outliers of what the model cannot explain). Each form has a **Data shape**
  cheat sheet: a made-up table in the shape it needs, one that does not work, and a check of your grid.
  **Time series**: a metric per period from a date column, its trend, its season in words ("December
  runs 31% above a typical month"), the periods that stand out (Show these rows), steps in the level and
  how much one period predicts the next. **Forecast**: trend, season and steps carried forward with 80%
  and 95% ranges, predictors each with their own future, and the miss it earns on held-back periods.
- **The Sandbox as a report:** results arrive as a readable note (with real tables) and a chart side by
  side; drag cards to arrange them, edit any note, see it as letter or landscape pages, **Print to PDF**,
  or **Export markdown** (one file, charts embedded as pictures, ready for an AI model). Right-click a
  cell or a header to send a value, a row, a profile or distinct values; every details window has
  Send to Sandbox.
- **Fit test and outliers:** select columns and ask whether their values spread as expected (chi-square
  against even shares, Benford's law on the first one or two digits, another grid's spread, or two
  columns together), with the verdict in words and an effect size; or find the outliers in a column, by
  amount (robust median fences, Tukey's quartiles or z-scores, within each vendor or month if you like)
  or by frequency (a typo seen once, an amount copied forty times). **Show these rows** adds a step
  that keeps just them; **Exclude these**, one that leaves them out.
- **Key Finder:** pick another grid (or every other grid) and get the likely join columns:
  each column pair that shares values, with the percent of each side's distinct values found in
  the other, whether each side is unique (so which one looks like the key), and a score. Columns
  whose longest value is over 128 characters are left out. Click a pair for sample shared values
  and the values an inner join would drop.
- **Export:** CSV, delimited text, Excel or Parquet, with provenance and formula neutralization.
- **Tabs, split and compare:** every grid is a tab in one window (they wrap onto more rows, up
  to 50). Right-click a tab for **Compare with…** (or drag a tab onto another) to see two side
  by side; the key picker opens with the Key Finder already run and the key that is unique on both
  sides ticked, and compare keeps both grids aligned row by row (outer, anti, cross, or diff: only
  the rows and the columns that differ). A compare survives a reload. The ≡ button beside +
  lists every table: open, closed (each with Open) and in your Python sessions.
- **The Sandbox** (on the rail): a dashboard of cards for any table: Vega-Lite charts, notes,
  result tables, Mermaid and Graphviz diagrams, Plotly and ECharts figures, and images. Every card
  resizes from its corner on a 12-column grid, and what it draws fills it. Charts open large with
  wheel zoom, and clicking a bar filters the grid. The page loads nothing from the internet: figures
  that need outside maps or pictures say so instead.
- **Agent door (MCP):** the agent sees what the page shows; its exports wait for the user's
  Allow. Settings lists its activity and has a copyable prompt that installs the MCP in any agent.
- **Connections** (the Application row's **Connections**): your databases and files. Add one with a
  form per type (SQL Server, PostgreSQL, Snowflake... 21 databases; a Power BI workspace, its datasets read with DAX;
  a Dataverse environment, its tables read through the Web API and SQL on its SQL endpoint;
  a CSV, workbook, Parquet or JSON file, or a folder of them; or your own Python, for anything
  else), its password kept in the system keyring, **Test connection** before
  saving. Then `conn = sab.connection("Warehouse")` in any Python, or a whole SQL cell on it:
  `%%sql Warehouse` in Jupyter or IPython.
- **Blades and the catalog** (its own tab, from **Blades and catalog** in the Application row): a **blade** is any
  Python that reaches outside Python to load something (a database connection, a CSV or workbook,
  an API, a vault). Save it once, then `conn = sab.blade("Warehouse")` in any Python. Starters for
  21 databases, 5 file patterns and 8 vaults; the save screen shows the packages a blade needs and
  installs missing ones. A blade can fill the **catalog**: every schema, table and column of its
  source with its type, as a searchable tree, readable by the agent so it can write SQL in the
  source's own dialect.
- **Jupyter and Python in the terminal** are where code goes: drag a blade, table or column from the
  blades page into a cell or an editor for its line, query or name.
- **Themes:** light, dark, high contrast light and high contrast dark, following the system by
  default; Windows forced colors are supported. One zoom for the whole page, the Sandbox
  included: Ctrl+= and Ctrl+-.

The design is [Plans/swissarmybench-build-plan.md](Plans/swissarmybench-build-plan.md); what has
been checked against real versions is in [docs/verified.md](docs/verified.md); decisions and
open notes are in [docs/ideas.md](docs/ideas.md).

New here? The **Tour** button (the question mark in the Application row) explains every word, grid to
pack, by lighting up each one on the page, then plays a quick matching game.

## Renamed from SwissArmyGrid

Swiss Army Bench was called SwissArmyGrid until this release. Everything has the new name: the package
and the wheel (`swissarmybench`), the import (`import swissarmybench as sab`), the commands
(`swissarmybench`, `sab`, `swissarmybench-mcp`, `swissarmybench-context`), the MCP server, the Claude Code
plugin and its skill (`swissarmybench-use`), the VS Code extension, the state folder
(`~/.swissarmybench`), the environment variables (`SWISSARMYBENCH_*`), the blade header
(`# /// swissarmybench-blade`) and the notebook metadata (`swissarmybench`).

The old names still work for this release, and go in the next one:

- `import swissarmygrid as sag` works, with a DeprecationWarning that names the new import. Code the app
  writes (copied code, table cells, data.py) always uses the new names.
- `swissarmygrid`, `sag`, `swissarmygrid-mcp` and `swissarmygrid-context` are still installed: each says
  its new name in one line, then runs it. An already installed plugin or VS Code extension keeps working.
- Old notebooks run: `%sag_run`, `%%sag_table`, `%%sag_html` and `%%sag` still work, and the old
  `swissarmygrid` metadata, `# /// swissarmygrid-blade` headers, tangs, Streamlit apps and their saved
  pages are read. Files are written with the new names.
- On its first start the server moves `~/.swissarmygrid` to `~/.swissarmybench` and says so once in its
  log; if it cannot (an old server still running from it, say), it reads the old folder where it is. An
  existing `~/SwissArmyGrid` Workbench folder stays your folder while there is no `~/SwissArmyBench`.
- `SWISSARMYBENCH_*` variables are read first, then the old `SWISSARMYGRID_*` ones.
- Passwords saved in the system keyring under the old name are found, and copied to the new name on their
  first read. The page's remembered settings (theme, zoom, the Sandbox's card sizes) are read from their
  old keys when the new ones are empty.

The installers remove the old `swissarmygrid` uv tool before installing the new one, which brings the old
commands with it; by hand, that is `uv tool uninstall swissarmygrid`, then the install below. Update the
VS Code extension too: the new one finds the new install (and still finds an old one). The GitHub
repository is now DylanCodyBrown/SwissArmyBench (the old address redirects).

## Install it: one package, two installs

From a release (each release carries the wheel, the VS Code extension and two installers), one line:

```powershell
irm https://github.com/DylanCodyBrown/SwissArmyBench/releases/latest/download/install.ps1 | iex
```

```bash
curl -LsSf https://github.com/DylanCodyBrown/SwissArmyBench/releases/latest/download/install.sh | sh
```

The installer sets up uv when it is missing, then downloads the release's wheel and installs the server
with its own Python. Give it a wheel path to install one you downloaded instead.

Or straight from PyPI, with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install "swissarmybench[server]"   # the server, once per machine
uv pip install swissarmybench              # the client, in any project's environment
```

Or by hand: build it with `python build.py`, then:

```bash
uv tool install --force "swissarmybench-<version>-py3-none-any.whl[server]"   # the server, once per machine
uv pip install "swissarmybench-<version>-py3-none-any.whl"                    # the client, in any Python environment
```

The server install gives the `swissarmybench` command (start, stop, status), the `sab` agent
command and `swissarmybench-mcp`. The client install is standard library only, so it goes into any
project's environment without touching that project's own packages:

```python
import swissarmybench as sab

sab.push(orders)  # a grid named "orders" opens; push again to refresh it in place
```

Visual Studio Code is optional. Everything installs with uv; the extension in `vscode-extension/`
only points VS Code at what uv installed: Swiss Army Bench's MCP tools become VS Code's own tools (agent
mode), and an Open Swiss Army Bench button (the editor and notebook toolbars, the status bar) starts the
server when it is not running and opens it in its own window. It needs VS Code 1.101 or later. Where this is going (workspaces, `sab.create_workspace()`, an in-app Python terminal,
saved workspaces, a relationships view): [Plans/standalone-workspaces.plan.md](Plans/standalone-workspaces.plan.md).

Grids open as tabs in one window, the workspace (`/workspace`): the first push opens it, and
every later push adds its grid as a tab there (or brings its tab forward) instead of opening a new
window. That holds for pushes made while the window is still loading, too: they wait for it (up to
15 seconds) rather than each opening one. Close a tab with its ×, middle-click, or Delete; drag
tabs to reorder them.

With pyarrow present, pushes keep their column types. A push opens the browser only when no page
already shows that grid.

## One-time setup for working on Swiss Army Bench itself

```bash
uv sync                      # Python environment in .venv
cd web
npm install                  # AG Grid, Monaco, Vega, esbuild, TypeScript (local, no CDN)
npm run build                # bundles src/ into static/build/
cd ..
```

Made-up test data: `python examples/sample_store.py --push` pushes a nine-table store with known
relationships (and deliberate traps for autodetection) to the running server.

## Run it

```powershell
.venv\Scripts\python -m swissarmybench.server            # start (reuses the last port if free)
.venv\Scripts\python -m swissarmybench.server --port 8790  # exactly this port, or a clear error
.venv\Scripts\python -m swissarmybench.server status
.venv\Scripts\python -m swissarmybench.server stop
```

`uv run swissarmybench` works too, but while a server started that way is running, `uv` can't
update the environment (Windows locks the launcher). `python -m` avoids that.

From a notebook or script (the client starts a server if none is running):

```python
import swissarmybench as sab

orders = load_orders()  # a pandas or Polars frame, Arrow table, DuckDB relation, or list of dicts
sab.push(orders)  # the dataset (and the browser tab) is named "orders"; the grid opens
sab.push(orders)  # again: every open grid on it refreshes in place, keeping its sort
sab.push(orders, name="q3", new_grid=True)
url = sab.push(orders, open=False)  # no browser, just the link
```

`SWISSARMYBENCH_OPEN=0` turns the browser off everywhere (the tests set it).

Or the demo data:

```powershell
.venv\Scripts\python examples\push_demo.py --rows 1000000
```

`swissarmybench start` opens the page in your browser (`--no-browser` not to) and prints its full address,
including the `#token=` part; `swissarmybench open` opens it again while it runs. In VS Code: Ctrl+Shift+P, then
**Simple Browser: Show**, then paste the address. Once open, the page clears the token from the address
bar and keeps a cookie of its own (HttpOnly, SameSite=Strict, good until the server restarts), so a reload
or a bookmark of `http://127.0.0.1:<port>/workspace` works; with no cookie the page says to open the app
from its tray or with `swissarmybench open`.

## Projects: one .sab file

A project is one file, `name.sab` (a zip inside): its notebooks, scripts and app canvases, the open tables
with where each came from and its steps, the Sandbox, the relationships and the windows' layout. Open
it on any computer: each table is read again from its source (a connection by name, never a password;
a file beside the .sab first), and one that cannot come back offers its fix (Add connection, Find
orders.csv). A pasted or pushed table's rows go in only when you tick **Keep its rows in the file**.
The home page's **Start** view lists your recent projects (`recent_projects.json` in the state folder:
paths and times only) and has **New project** and **Open project…**.

```powershell
swissarmybench open "C:\Users\me\Documents\sales.sab"   # starts the app when it is not running
```

The installers register `.sab` for you: on Windows for your user only (HKCU\Software\Classes, its
icon, `swissarmybench open "%1"`), on a Linux desktop as an XDG MIME type and desktop entry. On macOS,
open one with `swissarmybench open`.

## The Workbench

Notebooks and Python scripts, in a window of their own: the grid page's **Workbench** tab opens it (or
brings it forward). On the left, your connections and blades (drag one into a cell or the script for
its line) and the data explorer (drag a table or column for its name).

- **Notebooks** are Python, SQL, DAX, HTML and Markdown cells, saved as `.ipynb` (Jupyter and VS Code
  open them; a SQL cell is saved as a `%%sql <connection>` cell, a DAX cell as
  `%%dax <connection>/<dataset>`). Shift+Enter runs a cell and moves on, Ctrl+Enter
  runs it in place; Run all, Interrupt, Restart. Outputs stream as they come: text, errors, DataFrames,
  pictures, Plotly figures.
- **Scripts** are an editor over a Python console: F5 runs the file, Ctrl+Enter the selection or the
  line, and lines typed in the console run there too.
- **Every connection is there by its name:** `warehouse.cursor()`, `pd.read_csv(orders_file)`, with no
  `sab.connection(...)` line and no password or connection code in the document. A connection opens
  the first time a cell uses its name (one never used never connects); a variable of the same name you
  make yourself wins. The left panel shows each one's name in code (Sales DB is `sales_db`).
- **Completion as you type:** Python from the running kernel (your variables, their attributes, a
  DataFrame's columns; hover for a signature and its help); a SQL cell from its connection's catalog
  (schemas, tables, columns: `orders.` gives orders' columns); a DAX cell from its dataset (DAX's
  functions, `'Sales'`, `'Sales'[Amount]`, `[Total Sales]`); `sab.connection("` gives your connections.
- **Each notebook's own environment:** pick **New environment…** in the Environment box: where it goes
  (a `.venv` beside the notebook), the Python version, and libraries from presets (Data analysis,
  Charts, Statistics and models, Databases) or by group, plus any other package. It is made with uv
  (or venv and pip), its imports can go in as a first cell, and the Workbench remembers it for the
  notebook (a `.venv` beside a notebook is found by itself). `sab` and `%%sql` work in any
  environment, installed there or not.
- **Files:** New, Open, Save, Save as (a file chooser showing real paths) and Recent. Save as starts in
  `~/Swiss Army Bench`. A file changed on disk since it was opened is not overwritten without asking.

The kernel runs on your computer only when you press Run, in the Python you chose; an agent can never
run code there.

## Connections and SQL cells

A **connection** is a database, a file or a key vault you reach: added in the app (**Connections** in
the Application row) with a form for its type, the Python it makes shown underneath. Each password says
where it comes from: saved on this computer (the system keyring), an environment variable, or a key
vault. SQL Server and Azure SQL have a **Sign in** choice: Windows, a user name and password, or MFA
(Microsoft Entra), each its own connection string, switched keeping what you typed. **Trust server
certificate** and **Encrypt** are checkboxes (SQL Server, Azure SQL, Trino). **Test connection** runs
the form before anything is saved. A connection's **catalog** (its tables and columns) loads itself
in the background: when the connection is saved, when Swiss Army Bench starts, and the first time a SQL
cell, the side bar or an agent uses it. Each load runs in its own process, a couple at a time, so nothing
waits, and the SQL cell's suggestions pick it up as it lands. One that signs in with a browser window
(MFA) is not loaded at start-up, only on first use. **Refresh catalog** reads it again after the
database changes. Catalogs stay in memory only. Connections are kept with the
blades (so folders, packs, the catalog and Refresh work the same) but listed apart.

A **Power BI workspace** is a connection too: one connection reaches every dataset (semantic model)
in the workspace, each read with DAX through Power BI's Execute Queries request. Its form asks for the
workspace id (it is in the workspace's address in Power BI) and how to sign in, never for a dataset.
The first way is an **app registration** (service principal):
its tenant id, client id and client secret are each picked as an entry of your key vault, so the
connection's code reads them by name (`secret("powerbi_client_secret")`) and the same notebook runs in
an Azure Function, where the function app's Key Vault references put those names in the environment.
The ids may also be typed, with only the secret from the vault; **Browser sign-in** is for trying a
workspace by hand (it needs Microsoft's `azure-identity`, installed with the form's Install button; the
app registration's way needs no package).

The catalog shows the workspace's datasets, each with its tables, their columns and, marked, their
measures. Datasets are read one after another (the first 25, for at most 200 seconds); one that cannot
be read is marked on itself and the rest still load. **Open as grid** runs
`EVALUATE TOPN(<rows to open>, 'Table')` on the table's dataset and counts the table, so the grid says
"first N of M rows". A grid is named after its table; when two datasets have a table of that name,
after the dataset too (`Sales_model_Date`).

In a notebook, DAX has **a cell kind of its own**: pick DAX in a cell's kind picker (or the toolbar's
DAX, or X in command mode), pick the dataset (`Finance/Sales model`: the connection, a slash, the
dataset) and write `EVALUATE ...`. It is coloured as DAX, completes DAX's functions and that dataset's
tables, columns and measures, and gives a DataFrame, as a SQL cell does. It is saved as a
`%%dax Finance/Sales model` cell, which plain Jupyter with the client runs too. In Python:

```python
import swissarmybench as sab

by_region = sab.dax(
    "Finance/Sales model",
    """
EVALUATE SUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales])
""",
)

conn = sab.connection("Finance")  # the workspace itself
conn.datasets()  # each dataset's name and id
conn.dataset("Sales model").cursor()  # one dataset, used as a database's cursor is
```

A workspace with one dataset needs only the connection's name; with several, `Finance` alone is
refused with their names. In a script a DAX cell is that `sab.dax(...)` call under a `# %% [dax]`
marker.

**Import its relationships** (on a dataset in the catalog: its page and its right-click; and offered
when one of its tables opens) reads that dataset's own relationships into the current model, so the
Diagram and the Key Finder's known joins show them: an inactive one stays inactive and is drawn
dashed. Power BI gives at most 100,000 rows or 1,000,000
values (rows times columns) for one query; an answer that reaches that is refused with a message, never
passed off as whole. The tenant must allow the Execute Queries request (the admin setting **Dataset
Execute Queries REST API**) and, for an app registration, service principals to use the Power BI APIs;
the sign-in needs Read and Build permission on each dataset. Not yet run against a real tenant: it is
tested against a stand-in on this computer.

A **Dataverse** environment is a connection too: its form asks for the environment's address
(`https://<name>.crm.dynamics.com`) and how to sign in: **As you** (the Azure command line's sign-in,
else a browser window, through Microsoft's `azure-identity`), a **managed identity** (for an Azure
Function; no package) or an **app registration** whose client secret is a key vault's entry, never
typed into the app. Its catalog is the Web API's metadata: one schema (dbo), every table with its display
name, every column with its type. **Open as grid**, the preview and `sab.read("Sales CRM", "account")`
read a table through the Web API (OData `$select`, `$filter`, `$top`, paging by `@odata.nextLink`), so
they work in every environment with no admin setting; a choice column reads as its labels. SQL cells
(`%%sql Sales CRM`, `sab.sql`) run T-SQL on the environment's read-only SQL endpoint (TDS, port 5558)
through `pyodbc` and ODBC Driver 18 with the same Entra token; when an environment has that endpoint off,
the cell says so and the error panel offers the `sab.read` line instead. In Python:

```python
conn = sab.connection("Sales CRM")
won = conn.read("opportunity", columns=["name", "estimatedvalue"], filter="statecode eq 1", limit=100)
rows = conn.fetch('<fetch top="10"><entity name="account"><attribute name="name"/></entity></fetch>')
```

Export as one Python script writes the connection out as it is, so a managed identity signs in inside
an Azure Function. Tested against a stand-in on this computer; not yet run against a real environment.

A **connection made of your own Python** (**Python (your own code)**, under Your own code) reaches
anything Python can: an internal web service, a vendor's library, your own files. Its form has three
code boxes. **Connect** makes `conn`, any object. **List the tables** returns its catalog: a list of
dicts or a DataFrame with `table` and `column`, and optionally `schema`, `type` and `description`.
**Read a table** returns a table's rows given `conn`, `schema`, `table` and `limit` (`None` means
all): a DataFrame, an Arrow table or a list of dicts, or `(rows, total)` so the grid can say how many
rows the source holds. The form finds every environment variable the boxes read
(`os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")`, `secret("X")`) and asks where each comes
from: this computer's environment, saved on this computer, a key vault's entry, or a plain value that
is no secret. The code is not changed: the values are set as environment variables before it runs, so
the same code runs unchanged where those names are set some other way (an Azure Function's settings).
**Test connection** runs the three boxes and shows the first table's first rows. The catalog, Open as
grid, the preview and Load all rows then work as for a database. In a notebook:

```python
api = sab.connection("Orders API")  # what Connect made
orders = sab.read("Orders API", "orders")  # a table, by your Read a table box
```

A **key vault** (Azure Key Vault, AWS Secrets Manager or Parameter Store, Google Secret Manager,
HashiCorp, 1Password, a `.env` file, the operating system's vault) is a connection whose secrets become
environment variables. By default it loads **every secret in the vault**, new ones included, each under
its own name: `SqlPassword` stays `SqlPassword`, `Sql--Password` becomes `Sql__Password` (Azure's
convention for a section), any other character a variable cannot hold becomes `_`. As soon as the vault
can be read (its address filled in, or opened to edit) the form lists its secrets by name, never a
value: leave a secret's box empty and it keeps the vault's name (shown faintly), or type another name
to map it. Untick Every secret to choose them instead.
Every Workbench kernel starts with those variables set, so `os.environ["WAREHOUSE_PASSWORD"]` and a
connection's `secret("WAREHOUSE_PASSWORD")` just work. The values go straight into the kernel's
environment: never saved, never shown, never sent to an agent. A password's **A key vault** offers
**New vault** when there is none yet, and comes back to the connection when it is saved.

```python
import swissarmybench as sab

conn = sab.connection("Warehouse")  # runs it here: the database connection, or the file's path
sab.sql("Warehouse", "SELECT TOP 10 * FROM sales.orders")  # a DataFrame
```

In Jupyter and IPython a whole cell can be SQL on a connection, like the SQL Server extension's
connection picker:

```
%%sql Warehouse -> late
SELECT * FROM sales.orders WHERE shipped > due
```

- `%sql_connect Warehouse` makes it the default (a bare `%%sql` uses it); `%sql_connections` lists them.
- `-> name` keeps the result as a variable; `--grid` opens it as a grid.
- **A database** runs the cell in its own SQL: any DB-API connection, DuckDB, BigQuery, ClickHouse,
  Spark and SQLAlchemy engines. A statement with no rows (UPDATE, INSERT) is committed and says how
  many rows changed.
- **A file** runs it in DuckDB in your Python: a CSV, Parquet or JSON file is a table named after the
  file; a workbook's sheets are tables named after the sheets (read again when the file is saved); a
  folder's files are tables. A blade that makes a DataFrame can be queried by its variable's name.
- Tab in the cell offers that connection's tables and columns. An error stops the cell with one line.
  `%%sql` is taken only where no other extension (JupySQL) has it; `%%sab` always works.
  `SWISSARMYBENCH_SQL_CELL=0` turns the cells off.

## Blades and the catalog

A blade is saved Python that reaches outside Python to load something. Write it once on the blades
page (**Blades and catalog** in the Application row, or `/catalog`), then use it anywhere:

```python
import swissarmybench as sab

conn = sab.blade("Warehouse")  # runs the saved code here and returns its variable
sab.blade("Azure vault")  # a vault blade: reads its secrets live, sets environment variables
sab.blade("Warehouse login")  # a secret blade: asks for values this Python does not have yet
sab.blades()  # every blade's name, favourites first
sab.blades(search="orders-function-app")  # by name, description or tag
sab.blades(tag="sales")
```

The Sandbox can wear its own theme (the grid keeps the app's): twenty built in, high contrast and
colourblind-safe first, every one readable by construction; import your own as a small JSON file (and remove an imported
one with the button beside the picker). The PDF and the markdown export take it.

`sab.sandbox(fig, "Title", key="monthly")` puts a matplotlib, seaborn, Plotly, Altair or graphviz
figure, a picture, a DataFrame's first rows, Markdown text or a file in the Sandbox; the same `key`
replaces the card in place when the cell runs again.

- **Kinds:** SQL connection (with its dialect), other (any code), vault (Azure Key Vault, AWS,
  Google, HashiCorp, 1Password, a `.env` file, the operating system's vault: each secret mapped to an
  environment variable), secret (variable names only; the values are typed each session) and
  **analysis**: your own analysis, `def analyze(df, columns): ...` over the grid's rows as a pandas
  DataFrame, returning markdown, a table or a figure. It shows under **Your analyses** in the Analyze
  menu, runs in a child process like Refresh, and its result can go to the Sandbox. Three starters.
- **Secrets:** `secret("password")` in a blade's code. Its value is kept in the operating system's
  vault (Windows Credential Manager, macOS Keychain), never in the blade's file; an environment
  variable of the same name works too.
- **Packages:** the save screen reads the code's imports, names the pip packages (and calls such as
  `read_excel`, which needs openpyxl), and installs missing ones into Swiss Army Bench's Python on your
  click. `sab.blade()` turns a missing driver into the exact `uv pip install` command.
- **The catalog:** a blade's catalog command (SQL on its connection, or Python) returns one row per
  column of the source; **Refresh** runs it in a child process and loads it. Or load one directly:

```python
sab.load(conn.execute("SELECT * FROM INFORMATION_SCHEMA.COLUMNS").df(), name="Warehouse", dialect="sqlserver")
```

### The starter pack

Every install has **Swiss Army Bench starters**, 113 read-only blades and snippets shipped inside the
package (`src/swissarmybench/starters/*.blade.py`), listed under **Starters** in the blade list by
family. **Copy as your own** makes one of your blades from a starter; a new version of the app brings
new starters and never touches your copies.

| Family | What | How it is used |
|---|---|---|
| Power BI (13) | refresh a dataset or a dataflow, refresh and wait, status and history, list datasets, reports and dataflows, read and update parameters, take over a dataset, the refresh schedule | `refresh = sab.blade("Power BI refresh dataset")`, `refresh("Finance/Sales model")`: signed in through the workspace connection's own sign-in (its new `conn.access_token()`), never a copy of the secret |
| Dataverse (2) | a FetchXML query's rows, a choice column's options (numbers and labels) | `fetch_xml = sab.blade("Dataverse FetchXML query")`, `fetch_xml("<fetch>...</fetch>")`: through the Dataverse connection's own sign-in |
| Excel (12) | add a sheet, set values, write a DataFrame, borders, fonts and fills, number formats, autofit, freeze panes, merge, conditional colours, a range as a table, copy a template | `add_sheet = sab.blade("Excel add sheet")`, `add_sheet("report.xlsx", "Summary")` (openpyxl; nothing written over without `overwrite=True`) |
| Files (3) | combine a folder of CSVs, split a CSV by a column, change a delimiter or encoding | a function each |
| DAX (11) | year to date, same period last year, running total, top N, percent of total, a measure by month, date table checks, the INFO functions | a **snippet**: dragged onto a DAX cell |
| HTML (10) | a styled table, KPI tile and row, progress bar, badge, CSS bar chart, list, header, card grid, invoice | a snippet for an HTML cell |
| Streamlit (29) | filters, metrics, tables, charts, a map, layout, downloads, a form, an upload, session state, a cache, messages | a snippet for a Python cell, documented for a learner; it names its cell |

**Snippets** are a blade kind of their own: text for a cell with `<<name>>` placeholders
(`<<measure>>`, `<<date column>>`, `<<name: by_{column}>>`), kept in their file as one Python string
(`snippet = r"""..."""`) so a blade file stays Python. A placeholder asks for what its name says (a
table, a column of it, a measure, a Python name, a number, text); the form fills it from a DAX cell's
dataset or the open tables, and the server writes each value safely for where it stands (DAX's quotes
doubled, Python strings escaped, names only where code goes, HTML escaped). `sab.blade("DAX year to
date")` gives a snippet's text.

### Portable blades, blade folders, tags and favourites

A blade travels as one plain Python file, `<name>.blade.py`: its own code under a header, like a
script's inline metadata, that holds what the app needs (TOML):

```python
# /// swissarmybench-blade
# format = 1
# name = "Orders app DB"
# kind = "sql"
# description = "The database the orders function app reads"
# tags = ["orders-function-app", "sales"]
# dialect = "postgres"
# variable = "conn"
# secrets = ["password"]
# ///
import psycopg

conn = psycopg.connect(host="db.example", user="reader", password=secret("password"))
```

- **Only names of secrets travel**, never their values: the person importing types their own.
- **Import** (the up-arrow above the blades, or drop `.blade.py` or `.zip` files on them) shows every
  blade first: its code, its description and tags, the secrets it asks for, and whether its name is
  taken (keep both, replace or skip). Importing runs nothing. **Export** gives one blade's file (on its
  save screen) or every blade as a zip.
- **Blade folders** (the folder button, or `SWISSARMYBENCH_BLADE_FOLDERS`, paths separated as in `PATH`):
  folders searched, four levels deep, for Python files that *start* with the header. Ordinary Python
  files, virtual environments, `node_modules` and hidden folders are left alone, so blades can live in
  a Git repository beside other code. A folder blade saves back into its own file; removing it is
  yours to do in the folder. A blade kept by the app wins a name clash.
- **Description and tags** on the save screen. The search above the blades finds a blade by its name,
  its description or any tag, and the tag chips narrow the list: tag a blade with the app it serves
  and searching for that app finds it.
- **Favourites:** the star pins a blade to the top. Kept on this computer, never in the file.
- **Fill in your values.** A blade from someone else is written with their server, database, user or
  file path. Swiss Army Bench finds these settings in the code (read, never run): connection arguments
  such as `host=` and `dbname=`, the parts of a connection string (`Server=...;Database=...;`), and top-level
  values and paths (`path = Path(r"C:\data\orders.csv")`). The import review and the save screen show
  a field for each, mark the ones still holding an example value (`my-server`, `<your host>`, a
  starter's path) as **needs your value**, and suggest values from your other blades and from standard
  environment variables such as `PGHOST`. Whatever you type is written into exactly that place in the
  code. Passwords are never settings: they stay `secret("...")`, and the import review lets you type them
  straight into this computer's vault.

### Packs: blades and tangs from a Claude Code plugin marketplace

A **pack** is a Claude Code plugin with a `blades/` folder (`.blade.py` files) and a `tangs/` folder
(`.tang` files). A team keeps its packs in a GitHub repository that is a plugin marketplace
(`.claude-plugin/marketplace.json`); each person installs a pack once in Claude Code:

```
/plugin marketplace add <owner>/<repository>
/plugin install sales@team-blades
```

- **Installed packs** are found in Claude Code's plugin folder (`~/.claude`, or `CLAUDE_CONFIG_DIR`, or
  `SWISSARMYBENCH_CLAUDE_DIR`; the cache follows `CLAUDE_CODE_PLUGIN_CACHE_DIR`). Their blades are on the
  blades page and their tangs in the Relationships window, marked **pack**, read-only: Claude Code
  replaces the installed copy on every update. **Save a copy** keeps your own; Test and Refresh the
  catalog work without saving. A pack switched off in Claude Code adds nothing.
- **Updates:** `/plugin marketplace update team-blades`. A pack with no `version` (as made here) is
  updated by every commit.
- **Making one:** **Packs** on the blades page, then **New marketplace**, or from a terminal:

  ```
  sab pack new ./team-blades --pack sales --owner "Sales team"
  ```

  It writes the marketplace, one pack and a README with the commands, and (from the page) adds the
  folder as a blade folder. Push it to GitHub.
- **Adding to one:** a clone of the repository in your blade folders is an **editable** pack. **Add to
  pack** copies chosen blades and tangs into it (files already there are kept unless you ask to
  replace them); then commit, open a pull request, and once it is merged everyone updates.
- **Trust:** a pack's blades are its maintainers' code, run on your computer when you use one, as with
  any plugin you install. Secrets never travel in a pack, only their names. The agent cannot list,
  make or fill packs.

**This repository is a marketplace too.** `/plugin marketplace add DylanCodyBrown/SwissArmyBench`
offers two plugins: `swissarmybench` (the user guide as a skill, and the agent tools, the
`swissarmybench-mcp` server the installer puts on your computer; remove a copy you added by hand so the
tools are not listed twice) and `sample-store`, an example pack with a made-up blade and a tang holding
the ten relationships of `examples/sample_store.py` (push its tables with
`python examples/sample_store.py --push`, then **Run** the tang).

The agent reads catalogs with `catalog_list`, `catalog_schemas`, `catalog_tables`, `catalog_columns`
(with a first SELECT quoted for the source) and `catalog_search`.

**The agent can make blades for you.** `blades_create` saves one as you would on the save screen
(the golden rule; the older window that asked you to Allow each new blade is gone). `blades_list` gives
it your blades' names, descriptions and tags (so it can reuse one), `blades_get` one blade's code and
`blades_templates` the starters. No answer it gets holds a password's value: it writes
`secret("password")` and you type the value.

## Code to your Python

**Copy code** (on an analysis result) copies the analysis as Python to the clipboard, its imports
first: the grid's steps as checked DuckDB SQL over your table by its own name, then one
`swissarmybench.stats` call, the same code the window ran. Paste it into Jupyter or any Python.

Tables your Python makes still show in the grid page's Open list: importing `swissarmybench` in Jupyter
or IPython starts the watcher (`sab.watch()` in a plain script).

**SQL completion.** In Jupyter and IPython, Tab inside SQL (a string with a SELECT, FROM or JOIN, or a
`%%sql` cell) offers the loaded catalogs' tables and columns; `orders.cu` Tab gives orders' columns.
It asks the running server and never starts one (`SWISSARMYBENCH_COMPLETE=0` turns it off).

## The agent commands: `sab` and the MCP server

**The golden rule: everything you can do, the agent can do too** (215 commands, each an MCP tool):
grids and steps, analyses, the Sandbox and dashboards, connections and blades (made, changed, tested,
refreshed), packs and tangs, and the Workbench (open and save notebooks and scripts, start
kernels and run code in them, read their variables, make environments). It acts directly, no prompts,
with two exceptions: its exports still wait for your Allow (and it cannot answer an approval), and no
answer the app gives it holds a password's value. Code it runs in a Workbench kernel can read whatever
that Python can, as yours can. The audit log (Settings) names everything it did.

Every action the page has is a named command in one registry (`swissarmybench/cli/commands.py`), 215 of
them. A command is named for the part of the app it works on, then the action, so a flat list sorts
into the app's layout: `tabs_new_query` (the + tab), `table_filter` and `table_group_by` (the ribbon's
Table row), `column_keep` and `column_bucket` (the Column row), `cell_exclude` (a cell's right-click menu),
`steps_add` and `steps_apply_sql` (Table Transformations), `compare_create`, `sandbox_add`,
`relationships_set`, `erd_draw`, and `agent_context` / `agent_events` for what only an agent has. The
registry is ordered the same way, and `commands` returns the catalog grouped by area. Two front ends
run it:

- `swissarmybench-mcp` is a stdio MCP server that registers one typed tool per command, generated from
  the registry, so the model sees `steps_add(grid, kind, params, index?)` with its real arguments
  rather than composing a generic call. Descriptions are one line each and the schemas are slimmed, so
  the whole tool list is about 11,000 tokens for 215 tools (a test holds it under a budget). The agent reads a
  short index first (the resource `swissarmybench://index`, or `guide` with no arguments; under 4,000
  characters, checked against the registry's prefixes); `guide(topic=...)` (also
  `swissarmybench://guide/<topic>`) and `commands` (the catalog) carry the detail. A command added
  to the registry becomes a tool with no change to the MCP server.
- `sab` is the same commands in a terminal (standard library only, in the plain wheel):
  `sab tabs_new_query top "SELECT ..."`, `sab steps_add g1 filter @step.json`,
  `sab agent_events --seconds 60`. `@file` reads a file and `-` reads standard input. `sab --help`
  prints the catalog.

`agent_events` listens to the server's live broadcasts (a grid changed and who changed it, a table
opened, an export approval asked for), so an agent can work alongside the user instead of polling.

`app_snapshot` returns a PNG of the page as the user sees it (the whole window, or the ribbon, grid,
steps strip or sandbox). The server draws nothing: it asks the open page, which draws itself with
html-to-image and uploads the picture, and the server hands it to the agent without writing it to disk.
The MCP returns it as image content; `sab app_snapshot` saves it and prints the path. It shows real
cell values, and each one is written to the audit log.

The ribbon's Column buttons and a cell's right-click menu act on the selected columns or cells, which only the browser
knows, so their commands take the column names or values as arguments.

`row_read` with `format=csv` returns the grid's view as CSV. The agent picks `start` and `end` (up to
1,048,576 rows, an Excel sheet, per read), and every read starts with the view's total `row_count`,
which the step commands report too. An agent export always waits for the user's click: the export
route writes an agent's file only against the one-time ticket that click gives.

Left out on purpose, because the server refuses an agent or they are the user's to do: resolving an
approval, shutting the server down, the audit log,
pushing table contents (an agent passes a path to `datasets_load`), and opening a table from
a Python session. Zoom, column widths and the theme live in the browser, so no command reaches them.

The plugin's `UserPromptSubmit` hook (`plugin/hooks/hooks.json`) runs `swissarmybench-context`, which
adds to each prompt what you sent your agent from the Workbench (right-click an error or selected code,
Send to the agent: once, then it is marked read; the `agent_inbox` tool reads it too) and a short
summary of the table in front (grid, row count, columns and types, steps; never cell values), the way an
IDE hands Claude the open file. It prints nothing when no server is running.
Build the one wheel (the page inside it) with `python build.py`; `python build.py --vsix`
packages the VS Code extension around it too.

## The tray icon and updates

`swissarmybench start` also puts Swiss Army Bench's icon in the system tray (Windows and macOS; Linux on
a desktop that has a tray), as its own process; `--no-tray` leaves it out, and `swissarmybench tray`
starts it alone. One tray at a time. **A click** opens the page. **A right click** lists what is open (each
table, each Workbench document; a • marks unsaved changes), then Open the Workbench, Open the blades page,
Restart, Start with Windows (Open at login on macOS and Linux) and Stop and quit. With the server stopped
the menu offers Start.

**It starts itself and stays running.** The installers turn on start at sign-in, start the app in the
background and open its page once (`-NoAutostart -NoStart` on Windows, `--no-autostart --no-start` on
macOS and Linux install only; a build machine, `CI` set, never gets either). At sign-in the tray starts,
and it starts the server in the background, with no window and no browser. The sign-in entry is a
Startup folder shortcut to the uv tool's `pythonw.exe -m swissarmybench.server tray` on Windows, a
LaunchAgent (`~/Library/LaunchAgents/com.swissarmybench.tray.plist`, RunAtLoad) on macOS, and an XDG
autostart entry (`~/.config/autostart/swissarmybench.desktop`) on Linux.

```bash
swissarmybench autostart on        # off, status; the tray's Start with Windows does the same
swissarmybench start --background  # detached, no console window; returns at once (the page opens)
```

A server started by hand, by the tray or at sign-in never stops on its own: only **Stop and quit**,
`swissarmybench stop` or signing out stop it (one VS Code started still ends with VS Code). If its process
dies, the tray starts it again, at most 3 times in 5 minutes; after that the menu says **Swiss Army Bench
stopped: Restart**, and the beta log has the crashes.

**Updates:** the server asks PyPI (`https://pypi.org/pypi/swissarmybench/json`, then GitHub's latest
release if PyPI cannot be read) at start and every six hours. That one request is the only thing that
leaves the computer, and it carries nothing but itself. A pre-release is offered only to someone on one.
When a newer version exists, the tray's icon gets a dot, its first menu item is **Update to X** (with
**What's new**), and the grid page's and the Workbench's status bars say **Update available**. Update to
X asks first only when notebooks have unsaved changes or kernels are running, and saves nothing for you;
the app stops, a small helper installs the version with `uv tool install --force
"swissarmybench[server]==X"`, and the new version starts with its tray and its page. If it fails, the old
version starts again and says why. **Settings, Updates, Check for updates** turns the check off (kept).
The agent has `app_update_check` and `app_update` (which waits for your Allow).

## Beta mode: the beta log and notes

During the beta, Swiss Army Bench keeps a **beta log** in `~/.swissarmybench/logs`: server errors with
their stacks, slow requests, kernel, Streamlit, blade and catalog processes, page errors, and the notes
you leave by right-clicking anything and choosing **Leave a note…**. It holds no cell values, SQL, code,
secrets or full paths; table and column names are aliases (`table#1`, `col#3`). A note's picture is
there only when you tick "Attach a picture of this window".

**Settings, Beta, Export beta log…** writes one zip: **send this zip to Claude.** **Beta mode** turns the
log and the notes off or on (kept across restarts; `SWISSARMYBENCH_BETA=0` or `1` wins). The agent reads
the same redacted log with `app_beta_log` and `app_beta_notes`.

## Iterate on the page

```powershell
cd web
npm run watch        # rebuilds on save; reload the tab
npm run typecheck
```

## Checks (run before a commit)

```powershell
.venv\Scripts\python -m pytest -q                 # 300+ tests, including the browser ones
.venv\Scripts\python -m pytest -q tests\e2e       # just the browser tests (Edge, headless)
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m mypy
cd web; npm run typecheck
```

The real-world test bed (`tools/testbed/README.md`) runs eleven of the owner's use cases end to end
in a real browser against real PostgreSQL and MariaDB and stand-ins for Power BI and Azure Key Vault,
counting the user's actions: `python tools/testbed/testbed.py up`, then
`python -m pytest -q tests/e2e/test_real_world.py`, then `python tools/testbed/testbed.py down`. Without
it up, those tests skip and say why.

`tools\screenshots.py` photographs every screen into `docs\screenshots\`, and
`tools\vscode_check.py <url> <png>` checks a grid inside VS Code's browser.

## Credits

Swiss Army Bench is built with Claude, by Anthropic.

**How it was built.** Dylan Brown designed it and decided every feature, one question at a time; Claude
wrote the code, the tests and the documentation, and checked each change in a real browser with made-up
data. The commit history covers four days, 12 to 15 November 2026: 268 commits and 12 releases (0.10.0
to 1.6.0), with commits spread over about 66 hours. Larger pieces (read-only table cells, HTML cells,
the cleanup and the last round of usability changes) were built by Claude working as several agents
in parallel, each checked before it was kept. The work before 1.0.0 was squashed into that release's
single commit, so it is not counted here.

## License

Licensed under either of the [Apache License, Version 2.0](LICENSE-APACHE) or the
[MIT License](LICENSE-MIT), at your option.

Unless you explicitly state otherwise, any contribution you intentionally submit for inclusion in
this project, as defined in the Apache-2.0 license, is dual licensed as above, without any additional
terms or conditions.
