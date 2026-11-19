# Streamlit: the canvas and projects

The Streamlit extension (`swissarmybench-streamlit`), preinstalled with every install: the installers and
each update put it in, and the user can remove it on the Extensions page. Without it the app is the BI base:
no Apps area, no canvas, and a `streamlit_*` call says which extension it needs (`extensions_install
id=streamlit` waits for the user's Allow). A Streamlit project (`project_new type="streamlit"`) starts with
data.ipynb, app.ipynb and the canvas; a BI project gets the canvas too while the extension is on.

There is no Streamlit cell kind: a Python cell that calls `st.` shows live in its own cell (open tables
are DataFrames by name, after their grid steps). It runs in the document's Streamlit app, in the
notebook's own Python, on 127.0.0.1 only. A cell that makes a name (`region = st.selectbox(...)`)
drives the cells on the same page that read it.

## Live cells (the front document)
- `workbench_live_cells` (makes, reads, state), `workbench_live_run`, `workbench_live_resize`.
- `streamlit_cells`: every Python cell that calls Streamlit, by document (the Streamlit cells pane).

## The canvas (an app: `<name>.stapp.json`, pages of blocks on a 12-column grid, links to cells, no code)
- In the window: `workbench_new_app`, `workbench_canvas` (its app id), `workbench_canvas_play`,
  `workbench_canvas_edit`, `workbench_cell_copy` then `workbench_cell_paste` (a block).
- By app id, no window needed: `streamlit_open`, `streamlit_apps`, `streamlit_app` (pages, blocks,
  problems), `streamlit_page_add`, `streamlit_page_change`, `streamlit_page_remove`,
  `streamlit_block_place` (a saved document's cell onto a page), `streamlit_block_change` (move,
  resize, another page), `streamlit_block_remove`, `streamlit_save`, `streamlit_close`.
- Play: `streamlit_run`, then `streamlit_address`; `streamlit_stop`. Missing Streamlit: the problem
  is {kind "missing", feature, packages, python, command}; `streamlit_install` (into the notebook's
  Python; it is never the app's own dependency), then run again.
- Controllers: a cell's header line `# Makes: region: str = "All"; by_region: table = orders` is its
  contract (types: str int float bool date list table any; a table's default is a table's name;
  `# Role: filter|action|view` optional). A block whose maker is not on the page reads the default.
  `streamlit_app` gives each block's `controller` (role, makes with types and defaults, widgets),
  `defaults`, `contract`, `thin` and `failures`; `streamlit_check` the check alone (cycles, names made
  twice). `streamlit_test(app, page)`: Test this page (Streamlit's AppTest in the app's Python tries
  each controller's values; each block's failures). `workbench_canvas_move_to_data(block)`: a thin
  hint's model work into a named cell of data.ipynb, one `from data import ...` line left.
- `streamlit_export`: a folder that runs alone (app.py, pages, the tables as Parquet). It copies rows,
  so it waits for the user's Allow.
- `streamlit_save_as`: the project as one zip (data.py, pages/*.py, sources; no rows, no secrets).

## Project folders (a folder that starts with the data: guide projects)
- data.ipynb: each table's cell (its load and its grid steps as DuckDB SQL) and the user's own cells.
  data.py is its export, never edited by hand; pages and other notebooks start `from data import ...`.
- `project_new(name, app=true)`: a project folder (data.ipynb, data.py, a canvas, notebooks), opened. `project_files`,
  `project_export_data` (data.py again), `workbench_project_open` (its files as tabs).
- A pasted table has no source to read again: data.py gets a marked stub. When data.ipynb would hold
  pasted rows, `streamlit_save_as` waits for the user's Allow (`project_new` keeps rows out of it).

## App mode
- `streamlit_page_settings` (title, icon, layout wide or centered, logo, theme colours: written into the
  saved pages and the zip as st.set_page_config, st.logo and .streamlit/config.toml); `streamlit_state`
  (the live page's session state, each key with its block).
- In the window: "canvas.select", "canvas.properties", "canvas.settings", "canvas.session",
  "canvas.resetState", "canvas.undo", "canvas.redo", "canvas.duplicate", "canvas.align", "canvas.zoom",
  "canvas.preview" (desktop, tablet, phone; light or dark), "canvas.addStarter" (a starter written as a
  named cell of the mockups notebook, then placed), "data.starters", "data.starterList".

## The property pane and the designer (canvas_*)
- `canvas_inspect` (app; page; block): what the pane draws. A block: its `widgets` (each Streamlit element its
  cell calls: `index`, `call`, `arguments` as literal, name, state, variable or expression, `state_key`, `now`,
  `default`, `events`, `params`), `uses` (tables, variables, connections, cells, used_by, lineage), `cache`,
  `code` (what the page runs for it). `canvas_table` (a table's columns, steps in words, first rows).
- A cell's CODE changes only in the characters named, in its open document (the window that holds the app
  makes it, like typing): `canvas_set_default` (value=, index= or default=), `canvas_set_property` (any
  property; without value: reset), `canvas_bind` (kind name, state, variable or expression),
  `canvas_add_handler` (a stub and on_change= or on_click=), `canvas_set_cache` (kind data, resource or none;
  settings ttl, max_entries, show_spinner, persist). Code that is not a plain value is refused: change it in
  its cell. An app opened without a window (`streamlit_open`) is refused too: open it in the Workbench.
- Now, the RUNNING app only (Play first): `canvas_state_set` (a session state key, or forget), `canvas_cache_clear`.
- Designing: `canvas_toolbox` (the elements and containers; with element: its cell's code), `canvas_add` (an
  element as a cell of the app notebook and its block, on the front canvas), `canvas_container` (columns, tabs,
  expander, container, form, sidebar, popover), `streamlit_block_change` (parent, slot: into a container;
  hidden; locked; props: a container's own), `canvas_arrange` (left, right, centre, top, bottom, same_width,
  same_height, distribute; reset), `canvas_outline` (the page as a tree).
- In the window: "canvas.add", "canvas.selectMany", "canvas.arrange", "canvas.view" (snaplines, rulers,
  sampleRows, width), "canvas.panel" (toolbox, outline), "streamlit.addToApp" (the selected cell onto the page).
