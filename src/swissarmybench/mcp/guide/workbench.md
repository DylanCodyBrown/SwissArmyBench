# The Workbench

Notebooks (`.ipynb`) and scripts (`.py`) on IPython kernels on this computer, in a browser window of
their own (the rail's Notebooks, Scripts and Apps open it; code never opens in the grid page).

## Files and kernels (no window needed)
- `workbench_home` (default folder, recent files), `workbench_open`, `workbench_save` (refused if the
  file changed on disk since, unless `force`).
- `workbench_pythons`, `workbench_kernel_start(python, path)`: each connection is a variable by its
  name in it, and each key vault's secrets are environment variables.
- `workbench_run(kernel, code, kind)`: kind code (default), sql (a SQL cell on `connection`), dax (on
  `connection="Finance/Sales model"`), file (a script as python runs it), table (a table's cell), html.
  A run that stopped on an import says `missing` {feature, packages, python, command} in its error:
  run `%pip install <packages>` in that kernel, then the code again (the user gets a prompt).
- `workbench_run_notebook`: run every cell, save with the outputs. `workbench_input` answers input().
- `workbench_variables`, `workbench_inspect`, `workbench_is_complete`, `workbench_statement`,
  `workbench_kernel` (interrupt, restart, stop).
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
- Its top bar: Save, Save as…, New (the kind on show: notebook, script or Streamlit app; "file.newNotebook",
  "file.newScript", "file.newApp") and Open… ("file.open"). The rail's Notebooks, Scripts and Apps land
  on a page of cards. In a project data.ipynb is THE data notebook and every other notebook an app
  notebook (tab kinds `dataNotebook`, `appNotebook`; outside a project a plain `notebook`):
  `project_documents` and "documents" give each notebook's `role` (data, app or ""). The Notebooks page
  groups them under Data notebook and App notebooks; in a project "file.newNotebook" makes an app notebook.
  The Data Explorer (the left pane, off until opened: "view.explorer", Ctrl+Shift+E) sits beside every
  document; "documents" panes.data_explorer says open or closed. "explorer.search" searches it
  (as `explorer_search`), "explorer.insert" puts a result's insert code in the front document's cell,
  "explorer.popOut" opens the Data page (the one place to browse tables) in a window of its own. A canvas's
  Streamlit cells and Starters are its own left panels ("data.streamlitCells", "data.starters").
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
- An approved output is kept in the notebook's cell metadata; a later run that differs is "Changed
  since approved". `workbench_cell_approve(number)` (`remove`), `workbench_approvals` (each one's state),
  `workbench_approval_check(outputs, approved)` (no window). Headless:
  `python -m swissarmybench.client.standalone data.ipynb --check-approved` (exit 1 and a report).

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
- Kind colours: app pages violet, notebooks blue, scripts green; `app_kind_colours` reads or sets them.
- Notebook: `workbench_window` "notebook.runOrder" (each cell notRun, edited, outOfDate with the names
  made again), "notebook.outline", "run.upToHere", "notebook.present"; "mode.panel" opens a panel.
- Script: `workbench_script_settings` (arguments; each variable's source: env, value or vault, never a
  secret's value), `workbench_script_run` (Run as scheduled: a fresh process with no app; exit code,
  time, sources, log), `workbench_script_history` (memory only).
- Data (data.ipynb): "data.view" (cells, lineage, dictionary), "dictionary.list", "dictionary.describe"
  (kept in data.ipynb, written into data.py); `project_dictionary` reads a saved project's.


## Notebooks and Scripts: two pages (2026-11-21)

- A notebook opens only on the Notebooks page, a .py only on the Scripts page. `workbench_window` takes `page`
  (notebooks or scripts); without it, the page of `args.path`, the kind a command makes, else the window last used.
  `app_navigate` takes `window` notebooks or scripts.
- The Scripts page is a Python IDE over the project's code and the library's: `project_tree` (its groups, each
  module's outline), `workbench_outline`, `workbench_definition`, `workbench_references`, `workbench_rename` (a
  plan; `apply` writes it, never a made file), `workbench_search` (with `to`: replace), `workbench_format`,
  `workbench_fine_tune` (a table's transformations as a new script). The window's `view.fullScreen`,
  `view.files`, `view.codeSize`, `search.scripts`.
- Every code file changed anywhere is said with the `file_changed` notice; data.py edited by hand is kept
  (`project_export_data` with `replace` to write it again).
