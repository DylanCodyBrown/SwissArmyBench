# Streamlit: widgets and the Canvas

The Streamlit extension (`swissarmybench-streamlit`), preinstalled with every install: the installers and
each update put it in, and the user can remove it on the Extensions page. Without it the app is the BI base:
no Canvas, no Widgets, and a `canvas_*` or `widgets_*` call says which extension it needs
(`extensions_install id=streamlit` waits for the user's Allow). A Streamlit project (`project_new
type="streamlit"`) starts with data.ipynb and an empty canvas; a BI project gets a canvas too.

App notebooks and the old `.stapp.json` canvases were replaced by widgets (2026-11-21): opening an old one
says so in one line.

## Widgets (the library's `widgets/<name>.widget.py`, shared like blades)
- A widget is a header (name, description, framework, group, size and min_size in grid cells) and its
  Streamlit code. Its top-level plain values are its properties, each typed with a mask: bool (switch), int
  and float (number; `# 0..100` a range), str, colour (`"#1f77b4"`), date, datetime, time, choice
  (`Literal[...]` or `# choices: a, b`), table (an open table's name; empty: made-up sample data), column
  (a `# column of` comment naming its table property), variable (`os.environ["NAME"]` or `"${NAME}"`), path, list and dict. An
  annotation wins over the guess. The comment lines above one are its help.
- Its code imports the runtime: `from sab_canvas import table, key, sample, var` (`table(name)` the table,
  `key("x")` a widget key of this instance's own, `var(NAME)` a variable).
- `widgets_list` (q), `widgets_get`, `widgets_new` (name, description, code), `widgets_save` (code, the
  header kept), `widgets_header` (new_name: checked, and every canvas instance renamed; description),
  `widgets_properties` (of a widget, or of code not saved yet), `widgets_set_property` (a default, written
  into only its own characters, checked first), `widgets_run` (headless with AppTest: each page's
  `failed` errors and what it drew; live=true also gives a live address), `widgets_copy` (a prebuilt one
  as your own: 56 ship read-only), `widgets_delete` (the user's Allow), `widgets_preview` (its picture's
  state: ready with its address, coming, failed with why).

## The Canvas (`<app>.canvas.json`, a project file; every place and size in pixels)
- `canvas_list`, `canvas_open` (path, or name: a new one), `canvas_state` (model, version, `missing`
  instances whose widget is gone, `marks`: an instance's values that no longer fit, `notes` said once).
- A page holds containers; a container holds containers and widget instances placed in its box. The
  rules hold for every command: nothing overlaps its siblings or leaves its container or the page's width
  (wide 1200 px, centered 704 px), a widget is never smaller than its min_size; a refused command says why.
- `canvas_add_container` (page, parent, x, y, w, h, props: title, border, padding, height fit or fixed,
  scrollable, resizable, background, columns), `canvas_insert_widget` (widget, parent: no container makes
  one around it; x, y; values), `canvas_move` (x, y, w, h; parent: into another container, empty for the
  page), `canvas_set_container`, `canvas_set_values` (null: back to the default), `canvas_replace_widget`,
  `canvas_delete`, `canvas_set` (columns: a guide that re-flows, the row height, gap, width, snap, step 1, 2,
  4, 8 or grid), `canvas_page` (add, rename, move, remove), `canvas_undo`, `canvas_redo`.
- `canvas_play` (live address; check=true: every page headless, each failing widget's own error),
  `app_launch` (a build in the project's builds/<app>/<n>/, run in its own window), `canvas_export` (a
  folder that runs on a hosted Streamlit app: app.py, a page file each, sab_canvas.py, sab_widgets.py, the tables
  it names as Parquet, data.py; it copies rows, so it waits for the user's Allow).
- The page reproduces the canvas's pixels: each container and widget is an st.container placed
  absolutely by its key's CSS. A widget that fails shows its own error in its place; the page runs on.
