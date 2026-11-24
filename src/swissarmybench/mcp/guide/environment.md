# The Environment

Everything the open project holds, on one page (the rail's Environment, `app_navigate environment`) and in one
tool, `environment(action, args)`. Five kinds, a tab each:

| Kind | What it is | Where it comes from |
|---|---|---|
| `table` | the data: a named table (a tab is only a view of it, never a copy) | a connection, a file, a paste, a query, code |
| `variable` | what the code makes: numbers, text, lists, dictionaries | the project's Python |
| `structure` | JSON, YAML, XML, TOML documents | `structures/` in the project, or open and not saved |
| `setting` | `${NAME}` settings and secrets (a secret's value never comes back) | the library's variables, the keyring, a key vault |
| `library` | the libraries of the project's Python | its `.venv`, `requirements.txt` |

## Reading
- `environment(action="list")`: every row: `id` (`table:orders`), `name`, `type`, `size`, `value` (a short
  look: column names, a value's start; a secret is masked), `from`, `tags` (`Keep`, `In Python`), `grids` (the
  views of a table: `{"id", "steps"}`), `used` (every place that uses it: `{"kind", "words", "link"}`) and
  `kids` (what the row unfolds to: a table's columns, a structure's paths, a list's items).
  `counts` has each tab's number.
- `args={"search": "cust"}`: one search over every tab, in any case and by parts (cust finds customer_id and
  CustomerKey); each row says how it matched: `{"own": true, "kids": [1]}` (itself, or the rows inside).
- `environment(action="show", args={"kind": "table", "name": "orders"})`: one row whole; a table's columns
  with their ranges and blanks.
- `used` kinds: `grid`, `cell` (a notebook's cells by number, a script), `widget` (a canvas page's widget),
  `endpoint` (API.py), `analysis` (the Analyze board), `erd`, `table` (a table made from it), `connection`.

## Doing
| Action | Args | Notes |
|---|---|---|
| `open` | `kind`, `name` | a table opens on the Tables page (a view is made when it has none); the app goes there |
| `insert` | `kind`, `name` | the code a row is written as (`python`, `sql`, a setting's `${NAME}` as `text`) |
| `rename` | `kind`, `name`, `to` | a table (its tabs follow), a variable (the same object), an open structure, a setting |
| `remove` | `kind`, `name`, `python`? | a table closes with its tabs; `python: true` also deletes it in Python; a saved structure's file waits for Allow |
| `keep` | `name`, `keep` | Keep with the project: its rows into `.sab/data/` (Git-ignored); waits for Allow |
| `clear` | `tables`, `variables`, `structures`, `dry_run`? | what is ticked; kept tables, settings and libraries stay; waits for Allow |

Tables are added on the Connections page (`connections_open_table`), by `datasets_load` / `datasets_paste`, or
by code; there is no add here. Interrupt and Restart are the Notebooks and Scripts pages' (`workbench_*`).

## One Python per project
- Every notebook and script of the open project runs in ONE Python session (as RStudio): one set of variables,
  one cell at a time. `workbench_kernel_start` answers that session (`session.shared`: true) for every document
  of the project, and with no document at all (`own: true` asks for a kernel of its own); a file outside the
  project's folder gets a kernel of its own, as before.
- `workbench_kernel` `interrupt` and `restart` act on the session for every document (Restart clears every
  variable, and each window is told); `stop` leaves it running for the user's documents; `stop_session` stops it
  (the next run starts a new one). `workbench_run` takes `document`: the document the code is for.
- Every table here is read by name from that session without opening it on the Tables page first: `sab.table("orders")`,
  or a DuckDB SQL cell naming it. One a tab shows is read as its tab shows it (its steps applied).
- `environment(action="python")`: the project's own Python: `status` (`making`, `ready`, `missing`, `failed`,
  or `none` with no project), `words`, `python`, `own`, `problem`, the session's `kernel` while it runs, and
  `offers` (a notebook that had its own environment: the libraries it chose that the project lacks).
- The app makes the project's `.venv` (in its folder, Git-ignored) as a project is made or opened; the app's own
  Python runs the code until it is ready, and the session uses it from its next restart.
  `environment(action="set_python", args={"make": true})` makes it now (after a failure);
  `args={"offer": "<document>", "add": true}` installs an offer's libraries (waits for Allow), `"add": false`
  declines it.
- `project_installs`: as a project opens (once its `.venv` is there), everything it needs is found (requirements.txt,
  its type, the imports of its notebooks, scripts, API.py and widgets, its connections' and canvases' packages) and
  what its Python lacks is installed in ONE install, then added to requirements.txt; the page shows a progress bar.
  `action="state"` (default): `state` (`checking`, `installing`, `done`, `failed`, `none`), `total`, `done`,
  `current`, `packages` (`name`, `why`, `status`), `words`, `problem` (Try again), `restart` (a running session
  needs Restart, asked first, to use them). `action="check"` looks again (installs nothing); `action="install"`
  runs it (waits for Allow).

## Settings and secrets, and key vaults
- The `${NAME}` settings are this tab (`variables_list`, `variables_set`, `variables_rename`,
  `variables_remove`); the key vaults that give settings are on the Connections page (their cards under the
  connections'; added with `connections_create` and a vault type from `connections_types`). The old Variables page is this tab (`app_navigate variables` goes here).

## Libraries
- `environment(action="libraries")`: the project's Python (`own`: its `.venv`) and each library: `version`,
  `pinned`, `latest` (a newer version, once checked), what it is for, where it is imported.
- `args={"check": true}` asks the package index for newer versions (only then: never in the background).
- `install` `{"name"}` (or `{"names": [...]}`: one install), `update` `{"name"}` or `{"all": true}` (never a
  pinned one), `pin` `{"name", "pinned"}` (`name==version` in requirements.txt). Each waits for the user's Allow.

The list follows the app by itself: `agent_events` says when it changed (read it again then).
