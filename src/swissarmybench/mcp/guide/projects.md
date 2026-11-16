# Projects: one .sab file

A project is one file, `<name>.sab` (a zip inside, like .docx): its notebooks, scripts and app
canvases, the open tables with their steps, the Sandbox, the relationships and the windows' layout.
It can be emailed or shared; a double-click opens it. While it is open the app works in a folder of
its own (in the system's temporary folder); Save writes the .sab again.

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
- `project_new(name)`: a project to save as a .sab; the open tables go into its data.ipynb. With
  `folder`, a folder project instead (data.ipynb, data.py, a canvas, notebooks).
- `project_open(path)`: a .sab, or a project folder. With unsaved changes open it is refused: save
  first, or pass `discard=true` when the user said to let them go.
- `project_save(keep_rows?, path?)`: the first save of a new project needs `path`. The Workbench's
  unsaved documents of the project are saved first. `project_save_as(path)`; with `folder`, a
  folder project becomes one file.
- `project_close(discard?)`: its tables, Sandbox and relationships close; its working folder goes.
- Nothing runs code on open: a table made by a notebook comes back when that notebook runs.
- A file from a newer version opens read-only: say so; it cannot be saved here.
