# The Workbench

Notebooks (`.ipynb`) and scripts (`.py`) on IPython kernels on this computer, in a browser window of
their own (the rail's Notebooks and Scripts open it; code never opens in the grid page).

## Files and kernels (no window needed)
- `workbench_home` (default folder, recent files), `workbench_open`, `workbench_save` (refused if the
  file changed on disk since, unless `force`).
- `workbench_pythons`, `workbench_kernel_start(python, path)`: each connection is a variable by its
  name in it, and each key vault's secrets are environment variables. With a project open, every document
  of the project (and a start with no document) gets the project's ONE Python session, in the project's own
  Python: the same kernel id each time, `session.shared` true (the environment guide: One Python per project).
- `workbench_run(kernel, code, kind)`: kind code (default), sql (a SQL cell on `connection`), dax (on
  `connection="Finance/Sales model"`), file (a script as python runs it), table (a table's cell), html.
  A run that stopped on an import says `missing` {feature, packages, python, command} in its error:
  run `%pip install <packages>` in that kernel, then the code again (the user gets a prompt).
- `workbench_run_notebook`: run every cell, save with the outputs. `workbench_input` answers input().
- `workbench_variables`, `workbench_inspect`, `workbench_is_complete`, `workbench_statement`,
  `workbench_kernel` (interrupt, restart, stop; the project's session: interrupt and restart act on it for
  every document, stop leaves it running, stop_session stops it).
- What the editors know (no window needed), at `code`, `line`, `column` (1-based; `kernel` for its live
  names, `path` for its project's modules, `notebook` for IPython's lines): `workbench_complete` (the
  member list: kind, signature, docs; connections, variables and blades inside strings; a project
  module's name with its import), `workbench_signature` (parameter info: the active parameter and its
  words; `hover` for the name's docs and type), `workbench_problems` (what the editors show now, each
  document's; `path` checks a file now: syntax, undefined names, unused imports, Ruff's rules).
- `workbench_to_grid(kernel, name)`: a DataFrame in the kernel opens as a grid.
- Environments: `workbench_environment_offer`, `workbench_environment_create` (uv, else venv),
  `workbench_environment_choose` (the Python a document runs in).

## The window (it must be open; the "front document" is the one in front)
- New ("file.newNotebook", "file.newScript"; "file.newApp" opens the Canvas page) and Open… ("file.open").
  Every notebook is a notebook (the owner, 2026-11-22: "we just have notebooks"): one tab kind `notebook`, one
  Notebooks list (data.ipynb first: the notebook data.py is made from), no `role`. App notebooks, live Streamlit cells and the old `.stapp.json` canvases went (2026-11-21): an app
  is widgets on the Canvas (the streamlit guide); a cell that calls Streamlit runs in the kernel like any
  other, and "file.open" of a `.stapp.json` says so in one line.
  The Files pane (the page's notebooks or scripts) and, on Scripts, the Blades pane are columns on the right
  of the code, each shown or hidden by its status bar button ("view.files", Ctrl+B; "view.blades").
  A JSON, YAML, XML or TOML file opens as a structure's tab beside the code, on either page ("structure.open";
  its tree, search and text: the structures guide).
  The Data Explorer (the left pane, off until opened: "view.explorer", Ctrl+Shift+E) sits beside every
  document; "documents" panes.data_explorer says open or closed. "explorer.search" searches it
  (as `explorer_search`), "explorer.insert" puts a result's insert code in the front document's cell,
  "explorer.popOut" opens the Data page (the one place to browse tables) in a window of its own.
- `workbench_window(command, args)`: any palette command. "documents" says what is open and how the
  groups are arranged; "commands" lists them all (cells, running, splitting, moving tabs, the Data Explorer).
- `workbench_pop_out` moves the front document (unsaved text, kernel) to a window of its own;
  `workbench_move_back` brings it back.
- Getting around: "nav.home" brings the home window (the grids) forward; "nav.back" and "nav.forward"
  are the browser's Back and Forward inside this window (its dialogs, Connections' forms).

## Cells
- A cell's number never changes and is never reused: `#7` in a notebook, `# %% [7]` in a script.
  `@cell7` in a comment links to it; `workbench_cell_goto` goes there. `workbench_cell_name` names one.
- SQL cell: `%%sql <connection>` (the source's own SQL; files and DataFrames through DuckDB).
  With no connection (DuckDB) it also reads a table open in Grids by its name (its view, steps applied).
- `sab.table("orders", columns=[...], filters=[("amount", ">", 100)], sort=[("amount", "desc")], limit=50)`:
  an open table as its grid shows it, an Arrow table, read through the adapter (the plan done by the app's
  DuckDB); read again each time, the table stays the app's one copy.
- A connection through the adapter in a kernel, as an exported API.py reads it: `from swissarmybench.adapters
  import adapter`, `db = adapter.Connection(adapter.source_from(sab.connection("Warehouse"),
  name="Warehouse"))`, then `db.read(...)`, `db.query(sql, params)` (its own SQL), `db.write(...)` (a real write:
  the user's word first, as the Write starters), `db.tables()`.
  A Python cell's missing open table: `workbench_window` command `tables.add` gives the document its cell.
- DAX cell: `%%dax Finance/Sales model`; `workbench_dax_add`.
- HTML cell: `%%html`, a design in a walled-off frame; `{{ name }}` is filled from the kernel when it
  runs. `workbench_html_add`, `workbench_html_cells`, `workbench_html_run`, `workbench_html_resize`,
  `workbench_html_fill` (without the window), `workbench_html_marks`.
- Snippets: `workbench_snippet_insert` (topic blades).

## Lineage and approved outputs
- `workbench_lineage(document, cell)` or `(app, page, block)`: back through every cell to the data
  (makes and reads, `@cell` links, a table's grid steps and origin, data.ipynb, controllers): nodes in
  flow order, edges, Mermaid text, and each node's value summarised (a table's shape, first rows and
  row change; a value; an error). Values are the user's data. `workbench_lineage_show` opens the
  overlay on the user's screen.
- Headless: `python -m swissarmybench.client.standalone data.ipynb` runs a notebook top to bottom (exit 1 on a
  failed cell).

## Every table has a read-only cell
- Each open table has a cell holding its grid steps as one DuckDB query over the table by its own name,
  in the Tables group at the top of the document whose kernel made it (in a project: data.ipynb). It
  changes only with the grid (never by typing). It opens unfolded; one the app wrote whole (no user's
  cell makes the table) runs by itself once on opening and shows the table as its output (not saved).
  A changed cell is out of date until run; a user's cell never runs by itself.
- `workbench_window("tables.transformations", {"table": "orders"})`: brings that table's cell into
  view (data.ipynb opened when needed), as the Scripts and Notebooks pages' Transformations cards do.
  `workbench_table_cells` gives each table's `step_words` (its steps in plain words).
- `workbench_table_cells` (every table's cell), `workbench_tables` (the front document's, with state),
  `workbench_table_run` (runs the out-of-date ones; a second run changes nothing),
  `workbench_tables_arrange`.
- A user's cell that names a table starts with `# uses orders @cell3`; the app keeps that line.

## Export as one Python script (or one notebook)
- `workbench_export_script(path, format?, to?, stub?, check?)`: the notebook or script as ONE file that
  runs with no Swiss Army Bench: `format` script (default: one .py, `python <file>`, `--install` pips its
  REQUIREMENTS; `main()` for an Azure Function's timer trigger) or notebook (one linear .ipynb for
  nbconvert or papermill; its settings cell is tagged `parameters`). Default `to`: beside it, as
  `<name>_automation.py` (or .ipynb). The window's palette: `file.exportScript`, `file.exportNotebook`
  (the front document as it stands, saved or not).
- Written out: each connection's own code, the key vaults a password comes from (an Azure Key Vault by
  its managed identity, standard library), each table's load and grid steps as DuckDB SQL, the cells.
  SETTINGS names every variable it reads and where it came from; no password value, no row.
- What cannot be exported (`!ls`, `%run`, `import *`, sab.stats) comes back in `problems` with `ask`:
  nothing is written. `stub: true` writes the rest, each such cell a stub that raises FILL IN. A pasted
  or pushed table is always such a stub. `check: true` writes nothing and gives the text.
- Refused (403) when it would hold a saved password's value or a row. Code only: it asks no Allow.

## From the user
- `agent_inbox`: what they sent with Send to the agent (an error with its place, values and traceback,
  or code, and their question).

## The modes (each document's own panels, beside it in its group)
- Kind colours: app pages violet, notebooks blue, scripts green (fixed, per theme).
- Notebook: `workbench_window` "notebook.runOrder" (each cell notRun, edited, outOfDate with the names
  made again), "notebook.outline", "run.upToHere", "notebook.present"; "mode.panel" opens a panel.
- Script: `workbench_script_settings` (arguments; each variable's source: env, value or vault, never a
  secret's value); Run file takes its arguments.
- Data (data.ipynb): "data.view" (cells, lineage, dictionary), "dictionary.list", "dictionary.describe"
  (kept in data.ipynb, written into data.py); `project_dictionary` reads a saved project's.


## Notebooks and Scripts: two pages (2026-11-21)

- A notebook opens only on the Notebooks page, a .py only on the Scripts page. `workbench_window` takes `page`
  (notebooks or scripts); without it, the page of `args.path`, the kind a command makes, else the window last used.
  `app_navigate` takes `window` notebooks or scripts.
- The Scripts page is a Python IDE over the project's code and the library's: `project_tree` (its groups, each
  module's outline), `workbench_outline`, `workbench_definition` (`source=true`: a library's file text, read-only),
  `workbench_references`, `workbench_rename` (a
  plan; `apply` writes it, never a made file), `workbench_search` (with `to`: replace), `workbench_format`,
  `workbench_fine_tune` (a table's transformations as a new script), `workbench_file` (move: rename a module or
  package, its imports in the project following, a plan until `apply`; package: a new one; duplicate). Delete
  (to the trash) is the user's own. `workbench_debug(action, document)`: the script in its running kernel
  under the debugger: start (code, breakpoints [{line, condition?, log?}]), state (paused line, frames,
  output), breakpoints, over, into, out, continue, variables, evaluate (expression in the frame), stop. The window's `view.fullScreen`,
  `view.files` (the Files pane on the right, Ctrl+B), `view.blades` (the Blades pane beside it), `view.codeSize`,
  `search.scripts`.
- Every code file changed anywhere is said with the `file_changed` notice; data.py edited by hand is kept
  (`project_export_data` with `replace` to write it again).
