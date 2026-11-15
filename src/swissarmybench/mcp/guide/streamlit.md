# Streamlit: the canvas and projects

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
- Play: `streamlit_run`, then `streamlit_address`; `streamlit_stop`. Missing Streamlit:
  `streamlit_install` (into the notebook's Python; it is never the app's own dependency).
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

## Projects (a folder that starts with the data)
- data.ipynb: each table's cell (its load and its grid steps as DuckDB SQL) and the user's own cells.
  data.py is its export, never edited by hand; pages and other notebooks start `from data import ...`.
- `project_new(folder, name)`: data.ipynb, data.py, a canvas, notebooks. `project_files`,
  `project_export_data` (data.py again), `workbench_project_open` (its files as tabs).
- A pasted table has no source to read again: data.py gets a marked stub. When data.ipynb would hold
  pasted rows, `project_new` and `streamlit_save_as` wait for the user's Allow.

## App mode
- `streamlit_page_settings` (title, icon, layout wide or centered, logo, theme colours: written into the
  saved pages and the zip as st.set_page_config, st.logo and .streamlit/config.toml); `streamlit_state`
  (the live page's session state, each key with its block).
- In the window: "canvas.select", "canvas.properties", "canvas.settings", "canvas.session",
  "canvas.resetState", "canvas.undo", "canvas.redo", "canvas.duplicate", "canvas.align", "canvas.zoom",
  "canvas.preview" (desktop, tablet, phone; light or dark), "canvas.addStarter" (a starter written as a
  named cell of the mockups notebook, then placed), "data.starters", "data.starterList".
