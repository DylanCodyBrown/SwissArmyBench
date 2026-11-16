# Projects: one .sab file

A project is one file, `<name>.sab` (a zip inside, like .docx): its notebooks, scripts and app
canvases, the open tables with their steps, Visualizations, the relationships and the windows' layout.
It can be emailed or shared; a double-click opens it. While it is open the app works in a folder of
its own (in the system's temporary folder); Save writes the .sab again.

## Everything is the project's own
- A new project is saved first: `project_new(path)` writes its .sab at once (`autosave=true` to save
  quietly after each change; `project_autosave(on)` later). The user's page then shows its Grids.
- Its notebooks, scripts and apps: `project_documents(kind?)`. There are no recent files: a document
  from elsewhere is copied in with `project_import(source=<file>)`.
- Its connections and blades (`connections_list`, `blades_list`) and its saved Visualizations dashboards go
  with its file; another project sees none of them. With no project open they are this computer's
  saved ones.
- `project_import(source, list=true)`: what another .sab, a project folder or `"computer"` (this
  computer's saved connections and blades) offers; then `project_import(source, documents=[...],
  connections=[...], blades=[...])`. A name the project has is skipped (`skipped`); a document takes
  the next free name.
- Never a password in the file: a connection's password comes from each computer's keyring,
  environment or vault, by name. Where none is set, `connections_list` gives the connection a
  `needs_password` with its fix (the user types it, or `connections_password_source`), and its tables
  wait in `problems` with "Set the password".

## Tables come back from where they came from
- Each table keeps its source and its grids' steps: a connection (by name, never a password) with its
  table, a file (relative to the .sab when it sits nearby), the project notebook that makes it, or a
  "+" tab's query. Open reads each one again and applies its steps.
- A pasted or pushed table has no source: its rows go in only when ticked
  (`project_save(keep_rows={"pasted_1": true})`), as Parquet. Your save then waits for the user's Allow;
  a save with no rows asks nothing.
- A table that cannot come back is listed in `project_recent`'s `problems` with its fix: "Add
  connection Warehouse" (`connections_create`, then `project_table_fix(table)` to try again), "Find
  orders.csv" (`project_table_fix(table, path=...)`), "Open data.ipynb" (run it: the table arrives and
  its steps apply), or "Remove" (`project_table_fix(table, remove=true)`).

## The tools
- `project_recent`: the open project (`dirty`: unsaved changes; `problems`), and the recent ones.
- `project_new(path)`: a project saved as that .sab; the open tables (and their connections) go into
  it. With `folder`, a folder project instead (data.ipynb, data.py, a canvas, notebooks).
- `project_open(path)`: a .sab, or a project folder. With unsaved changes open it is refused: save
  first, or pass `discard=true` when the user said to let them go.
- `project_save(keep_rows?, path?)`: with no project open, `path` makes the open work one. The Workbench's
  unsaved documents of the project are saved first. `project_save_as(path)`; with `folder`, a
  folder project becomes one file.
- `project_close(discard?)`: its tables, Visualizations and relationships close; its working folder goes.
- Nothing runs code on open: a table made by a notebook comes back when that notebook runs.
- A file from a newer version opens read-only: say so; it cannot be saved here.
