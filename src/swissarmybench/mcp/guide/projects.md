# Projects: a folder

A project is a folder (the owner, 2026-11-17): its notebooks, scripts, apps and structures are ordinary
files at its top, so it can be a Git repository and shared like one. The app's own state is a hidden
`.sab/` folder beside them, plain JSON that reads well in a diff: `.sab/project.json` (each table's source
and steps, the tabs and windows, autosave), `.sab/visualizations.json` and `.sab/visualizations/`
(Visualizations and its saved dashboards), `.sab/model.json` (the relationships). Rows are written only
on a tick, into `.sab/data/`, which Git ignores (`.gitignore`, `.sab/.gitignore`).

## The home page: the Project Explorer
- `projects_list(by?, descending?, type?, q?)`: every project as a card: the projects folder's (Settings'
  Projects folder; `projects_folder_set`, which waits for Allow) and every one opened from elsewhere. Each
  card: name, type (`needs` when its extension is off), last opened, last changed, created, its folder,
  counts (notebooks, scripts, apps, tables), Git (`repository`, `branch` from .git/HEAD), `missing`.
- `projects_sort(by)` (remembered): opened, name, type, changed, created, custom; `projects_sort(order=[...])`
  or `projects_sort(move=<folder>, step=-1|1)` for the custom order.
- `project_types()`: each type New project makes, explained for beginners (title, for whom, what you get,
  an example; `make` is what to send to `project_new`).
- `project_rename(path, name)` (not the open one), `project_remove_from_list(path)` (no file is touched;
  `to=<folder>` locates a moved one). Show in folder and Delete (to the system's trash) are the user's
  only: never yours.

## Open, new, save, close
- `project_new(name, type?, folder?)`: the folder made in the projects folder (or `folder`, or `path`: a
  new or empty folder), scaffolded (data.ipynb with the open tables, data.py, .gitignore, README.md, the
  type's own files) and opened; `.sab/` is written at once. Autosave is on unless `autosave=false`.
- `project_private(on)` (waits for Allow): kept in .sab/project.json; a private project's documents are never
  sent out by an extension (GitHub Copilot's completions). `project_recent` says `private`.
- `project_open(path)`: a project's folder. A plain folder answers `not_a_project`: `make=true` makes it
  one around its files, never writing over one. With unsaved changes open it is refused: save first, or
  `discard=true` when the user said to let them go.
- `project_save(keep_rows?)`: `.sab/` written, each file only when it changes (a save that changes nothing
  changes no byte). Documents are saved by their own Save (`workbench_save`). With no project open,
  `path` makes the open work a project there.
- `project_copy(path, data?)`: Copy project to a new or empty folder; `data=true` copies `.sab/data/`
  too, and then waits for the user's Allow.
- `project_close(discard?)`: its tables, Visualizations and relationships close; the folder stays.
- Nothing runs code on open: a table made by a notebook comes back when that notebook runs.
- A project of a newer format opens read-only: say so; it cannot be saved here.

## Everything is the project's own
- Its notebooks, scripts and apps: `project_documents(kind?)`. A document from elsewhere is copied in
  with `project_import(source=<file>)`; `project_import(source, list=true)` shows what another project
  folder offers.
- Connections, APIs, blades and variables are the library's (every project has them); its saved
  Visualizations dashboards are the project's.
- Never a password in a project: a connection's password comes from each computer's keyring,
  environment or vault, by name. Where none is set, `connections_list` gives the connection a
  `needs_password` with its fix, and its tables wait in `problems` with "Set the password".

## Tables come back from where they came from
- Each table keeps its source and its grids' steps: a connection (by name) with its table, a file
  (relative to the project when it is inside it), the project notebook that makes it, or a "+" tab's query.
- A pasted or pushed table has no source: its rows are kept only when ticked
  (`project_save(keep_rows={"pasted_1": true})`). Your save then waits for the user's Allow.
- A table that cannot come back is listed in `project_recent`'s `problems` with its fix: "Add
  connection Warehouse" (`connections_create`, then `project_table_fix(table)`), "Find orders.csv"
  (`project_table_fix(table, path=...)`), "Open data.ipynb" (run it), or "Remove"
  (`project_table_fix(table, remove=true)`).
