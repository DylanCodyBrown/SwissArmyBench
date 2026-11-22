# Projects: a folder

A project is a folder (the owner, 2026-11-17): its notebooks, scripts, apps and structures are ordinary
files at its top, so it can be a Git repository and shared like one. The app's own state is a hidden
`.sab/` folder beside them, plain JSON that reads well in a diff: `.sab/project.json` (each table's source
and steps, the tabs and windows, autosave), `.sab/visualizations.json` and `.sab/visualizations/`
(the Analyze board and its saved dashboards), `.sab/model.json` (the relationships). Rows are written only
on a tick, into `.sab/data/`, which Git ignores (`.gitignore`, `.sab/.gitignore`).

## The home page: the Project Explorer
- `projects_list(by?, descending?, type?, q?, where?)`: every project as a card: the local projects folder's
  and the shared projects folder's (Settings' Local and Shared projects folders: `projects_folders`, setting
  one waits for Allow) and every one opened from elsewhere. Each card is `where`: "shared" (under the shared
  projects folder, a folder the user pushes and pulls with Git; the app never runs git) or "local", and
  `copied_from` when it is a local copy of a shared one. Each card: name, type (`needs` when its extension is off), last opened, last changed, created, its folder,
  counts (notebooks, scripts, apps, tables), Git (`repository`, `branch` from .git/HEAD), `missing`.
- `projects_sort(by)` (remembered): opened, name, type, changed, created, custom; `projects_sort(order=[...])`
  or `projects_sort(move=<folder>, step=-1|1)` for the custom order.
- `project_types()`: each type New project makes, explained for beginners (title, for whom, what you get,
  an example; `make` is what to send to `project_new`).
- `project_rename(path, name)` (not the open one), `project_remove_from_list(path)` (no file is touched;
  `to=<folder>` locates a moved one). Show in folder and Delete (to the system's trash) are the user's
  only: never yours.

## Local and shared
- `project_new(name, where="shared")` makes it in the shared projects folder (refused until it is set).
- `project_share(path)`: a local project copied into the shared folder (never `.sab/data/`, nor its `.git`;
  the original kept), then opened. Waits for the user's Allow.
- `project_copy_local(path, name?)`: Make a local copy of a shared project (no rows; its project.json says
  `copied_from`), then opened; a name taken there answers 409 with a free one. No Allow needed.
- Opening or making a shared project whose connections only work on this machine says so once (the
  portability rule): teammates and a Function App can't use them.

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
- `project_close(discard?)`: its tables, the Analyze board and relationships close; the folder stays.
- Nothing runs code on open: a table made by a notebook comes back when that notebook runs.
- A project of a newer format opens read-only: say so; it cannot be saved here.

## Everything is the project's own
- Its notebooks, scripts and apps: `project_documents(kind?)`. A document from elsewhere is copied in
  with `project_import(source=<file>)`; `project_import(source, list=true)` shows what another project
  folder offers.
- Connections, APIs, blades and variables are the library's (every project has them); its saved
  the Analyze board's dashboards are the project's.
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

## The outline: ARCHITECTURE.md
- `project_outline()`: the open project as one markdown document for someone joining it, the same eight
  sections every time: Overview (name, type, purpose from README.md's first paragraph, the folder),
  Data sources (each connection and API it uses: kind, sign-in, portability, the variables it needs by
  name and source), Data model (each table it uses: where it comes from, columns by name and type, the
  relationships as a Mermaid erDiagram), Transformations (each table's steps in words and as one DuckDB
  query; data.ipynb's named cells: what each makes and reads), Lineage (a Mermaid flowchart: sources,
  tables, cells, deliverables), Deliverables, Running it (packages, scripts' run settings, a checklist
  for a Function App or a hosted Streamlit app), Open issues. An empty section says "None.".
- `project_outline(write=true)`: writes it as ARCHITECTURE.md at the project folder's top, as the user's
  Export outline does (only when its bytes change: `written` says). Not destructive; no Allow.
- Metadata only: never a row, a value or a count from the data, a secret, or a path outside the folder.
  The same project gives the same bytes (no timestamp, no version). Names in `code` are data.
- Use it to brief yourself on a project, or when the user asks for its architecture or documentation.

## The change log (`changes`)
- Every change to the open project's objects is one event in .sab/changes.jsonl (this computer's, never a value):
  a table's steps, columns or source; a connection's settings or sign-in; an API's specification or an endpoint's
  learned shape (the app saw it); API.py's endpoints; a widget's code or properties; a canvas page; a notebook's
  cells, a script's definitions; a variable by name; a setting; a library added.
- `changes(action="last", object="table:orders")` (or a name alone): the last change, with its words, the
  difference by name (a column's type said) and the fingerprints before and after. `"history"` with `n`,
  `"since"` with `since` (an ISO time: when you last looked), `"search"` by `kind`, `who` (user, agent, app) or
  `word`. The Session page shows the same events (`app_session(changes=true)`).
