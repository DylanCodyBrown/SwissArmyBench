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
  `key("x")` a widget key of this instance's own, `var(NAME)` a variable, `sample(kind=...)` made-up rows:
  sales, orders, products, tickets, stock; `choices(options, frame, column)` a select's choices from a
  table's column, distinct and sorted, the first 1,000 with a note; `marked(label, required)` and
  `problem(words)` the inputs' one look).
- **Its contract (2026-11-21): Ins, Outs and Events**, declared at the top level and read with ast:
  `orders: In[Table] = None` (data coming in at run time; the value is its own when nothing is wired),
  `region: In[str] = "All"`, `picked: Out[int] = None` (data going out: the code assigns it), `saved:
  Event[dict] = None` (an action it fires: `saved(payload)`). Types: Table, str, int, float, bool, date,
  datetime, File (`sab_canvas.File`: name, size, type, bytes; input_file, input_camera and input_audio give
  `file: Out[File]`, excel_upload takes `file: In[File]`), list[...], dict. A typed payload `saved:
  Event[Order]` and `rows: Out[Table[Row]]` name a TypedDict or dataclass of the widget's own: the port
  gives `schema` and `fields` (the Events' body mapping offers them; a column property wired from the Out
  offers its columns). Plain values stay properties (the design-time settings). `widgets_get` and
  `widgets_properties` give `contract` {ins, outs, events}; a declaration that does not read has its
  `problem`. `widgets_upgrade` (apply=true saves; else the preview's diff) rewrites a widget's session state
  keys as Ins and Outs.
- Where a widget lives (`where`): the open project's `widgets/` folder (shared in Git with it) first, then
  the library's, then the prebuilt ones; a name in the project wins over the library's (`hides`). An export
  carries the widgets the canvas uses (the project's own too) inlined in its `widgets.py`.
- `widgets_list` (q), `widgets_get`, `widgets_new` (name, description, code; where=project), `widgets_save` (code, the
  header kept), `widgets_header` (new_name: checked, and every canvas instance renamed; description, group, size and
  min_size in grid cells, tags),
  `widgets_properties` (of a widget, or of code not saved yet), `widgets_set_property` (a default, written
  into only its own characters, checked first), `widgets_run` (headless with AppTest: each page's
  `failed` errors and what it drew; live=true also gives a live address), `widgets_copy` (a prebuilt one
  as your own: 113 ship read-only; to=project or to=library: Copy to project / Copy to library, the same name), `widgets_delete` (the user's Allow), `widgets_preview` (its picture's
  state: ready with its address, coming, failed with why).
- Starter packs (a prebuilt widget's `pack` in its header; `widgets_list` gives `packs`): Sales dashboard,
  Operations, Customer service, Data entry, Admin, User inputs, Excel, Form builder. Every prebuilt widget
  speaks the contract: a table In (`In[Table]`; not wired: its own made-up rows), each input's
  `value: Out[...]` and `default_from: In[...]`, a select's `options_table` and `options_column`, the pack
  hand-offs as Outs and Ins of one name that wire by themselves (`sales_filter`, `ticket_id`, `uploaded` ->
  `mapped` -> `valid`, `form_definition`, `form_submissions`), its Save/Submit/Send as an Event (`saved`,
  `sent`, `approved`, `rejected`). Excel widgets read through the
  adapter's Excel and make workbooks through `sab_excel.build` (adapter.py and sab_excel.py are carried beside
  the pages); they need openpyxl (an older .xls is saved as .xlsx first): a new project's Python gets it; an
  older one says so in place.

## The Canvas (`<app>.canvas.json`, a project file; two layouts, Phone and Desktop)
- `canvas_open` (path, or name: a new one; neither: the project's canvases), `canvas_state` (model, version, `missing`
  instances whose widget is gone, `marks`: an instance's values that no longer fit, `notes` said once).
- A page holds containers; a container holds containers and widget instances placed in its box. The
  rules hold for every command: nothing overlaps its siblings or leaves its container or the page's width,
  a widget is never smaller than its min_size; a refused command says why.
- Two layouts, `desktop` (designed at 1200 px) and `phone` (portrait, 390 px): the same items in both, each
  layout with its own places. `canvas_state`'s `views` gives each page's items in pixels at each layout's
  design width (`design`); the file keeps x and w as fractions of the parent's width, so the built page fits
  any width (desktop at 768 px and wider, phone below: a media query, no rerun). Every placing command takes
  `layout` (default desktop); an item made in one layout is placed in the other by itself (phone: stacked at
  full width in reading order). `canvas_move` with show (both, desktop or phone) hides an item in one layout;
  `canvas_move hidden=true` makes a widget or a container (a titled one too) **Hidden in the app**: its
  widgets run and their Outs flow, the played, launched and exported page give it no space (nor a container
  with no title holding only such widgets).
- `canvas_add_container` (page, parent, x, y, w, h, props: title, border, padding, height fit or fixed,
  scrollable, resizable, background, columns), `canvas_insert_widget` (widget, parent: no container makes
  one around it; x, y; values), `canvas_move` (x, y, w, h; parent: into another container, empty for the
  page), `canvas_set_container`, `canvas_set_values` (null: back to the default), `canvas_replace_widget`,
  `canvas_delete`, `canvas_set` (columns: a guide that re-flows, the row height, gap, snap, step 1, 2, 4, 8 or
  grid; both layouts), `canvas_page` (add, rename, move, remove), `canvas_undo` (redo=true redoes).
- `canvas_play` (live address; check=true: every page headless, each failing widget's own error),
  stop=play stops it. Play follows live data: a table it reads (an open table after its steps, a
  `[Sandbox].x`, data.ipynb's data.py) is written again into the run when it changes (a sandbox write, an
  API's or an Event's, an edit on the Tables page, a step, a reload, data.py exported) and the open pages run again by
  themselves; another connection's `[Conn].table` is the session's read (Refresh on its card reads it again).
  Launch follows the same way (a shared launch shows a change on its next interaction); an export is unchanged
  (its open and sandbox tables as Parquet copies, a connection's read through adapter.py and connections.py).
  `app_launch` (a build in the project's builds/<app>/<n>/, run in its own window; analyzer=true attaches the
  Performance Analyzer from the first load; stop=true stops it); `sharing_status`,
  `sharing_start app=<canvas id>` (waits for Allow; installs devtunnel if needed): the launched
  app's own port to the user's organization (work accounts of its tenant; never anonymous, never this server;
  the user signs in themselves), `sharing_stop` (Allow; a new launch or its stop ends it too), `canvas_export` (a
  folder that runs on a hosted Streamlit app, the fewest files: app.py (the pages, the layout, the wiring and the
  runtime), widgets.py (the widgets inlined), the API adapter's file, requirements.txt, README.md, the tables
  it names as Parquet, data.py; it copies rows, so it waits for the user's Allow).
- Builds (`builds/<app>/<n>/`: the code as launched, canvas.json, build.json saying what changed in words):
  `canvas_builds` by action: list, files (build), compare (build, b; no b: against the canvas now), relaunch,
  restore (the build's canvas back as one change; `canvas_undo` takes it back; the library's widgets
  are not changed). The Performance Analyzer on a launch: `canvas_perf` by action: attach, pause, clear, detach,
  session (each rerun's trigger and each widget instance's time, calls, caches, the web socket's kinds
  and sizes: never content), hints, save (into the build), saved (build, file).
- Wiring (`canvas_wire` id, port, wire; null unwires; one undoable change): an In's source is a table
  (`{"table": "orders"}`; the project's sandbox: `{"table": "[Sandbox].orders"}`, its made-up copy, never
  live data), another instance's Out on any page (`{"out": "w3.filtered"}`, its type fitting: a mismatch is
  refused with the reason; from another page an app-wide value kept in the session, said "<page> ·
  <widget>.<port>", its `wires` entry `cross` with its `page`), who is viewing (`{"out": "app.viewer"}`, a
  str: a sign-in the host vouches for, Azure App Service's headers on App Service or Streamlit's st.user,
  else this computer's user name in Play and Launch, else "unknown"; Dev Tunnels passes no viewer's name, so
  a shared app says "unknown"; an In[str] called viewer takes it by itself), the viewer's
  `app.viewer_email`, `app.viewer_id` (the account's object id) and `app.viewer_roles` (list[str]): only what
  App Service's sign-in (X-MS-CLIENT-PRINCIPAL, on App Service) or st.user gives, empty otherwise, never this
  computer's (an In of the same name takes each by itself; sab_canvas.viewer() returns them all), a page value (`{"page": "k"}`), a GET endpoint's answer
  (`{"endpoint": "GET /orders"}`), a variable, a typed value, or for a list[Table] `{"tables": [...]}`. An
  unwired In takes the page's one Out of its name and a fitting type by itself (`auto`). An Event's wire is
  `{"actions": [...]}`, its actions in order: `{"do": "call", "endpoint": "POST /visits", "body": "values" or {field: "values.x"},
  "params": {name: path}}`, `{"do": "set", "key", "value": path}`, `{"do": "rerun"}`. **An endpoint is any
  API's action, called through the API adapter:** `GET /orders` is the project's local sandbox API's, `[Orders] GET
  /orders` the library API Orders' (`actions(action="list")` names them; an endpoint property takes
  the same). Every built app (Play, Launch, Export) carries the API adapter's own file, `sab_actions.json` (the actions it
  calls: definitions and learned shapes, types only) and a library API's client `API_<name>.py`; an export's
  README.md names the variables to set (SAB_API_URL, SAB_API_KEY, SAB_API_BASE for the local API's deployed
  copy; a client's own). In a widget's code: `from sab_canvas import action, said, data, takes`;
  `answer = action("GET /orders/{id}", {"id": 7})` is the adapter's envelope (`ok`, `kind`, `records`,
  `record`, `value`, `paging`, `error`); `said(answer)` its error in a line; one request a call (`pages=`
  follows more). The older two-value call still works (the same call). `canvas_state`'s
  `wiring`: each instance's ports, `sources`, `readers` of each Out, `wires`, `columns` (each Out[Table]'s
  columns: declared Table[Row], else as Play or Launch last ran it), and `broken` (a deleted widget
  or Out, a type changed: both ends; `canvas_play` lists them too). The page runs each widget after what it
  reads. `canvas_set_values` with an In's name and a table's name wires it (an older canvas's table value is
  wired so as it opens).
- A table In or property takes an open table, a data.ipynb table (data.py's names) or a connection's table as
  DuckDB SQL names it, `[Conn].table` (`widgets_get`'s context lists each connection's as far as its
  catalog is loaded); a run reads it through the connection-tables contract, so through that connection's
  query limit; a connection not here is said with the fix.
- The page reproduces the canvas's places: each container and widget is an st.container placed
  absolutely by its key's CSS (x and w as fractions of its parent, y and h in pixels; within 1 px). A widget that fails shows its own error in its place; the page runs on.
