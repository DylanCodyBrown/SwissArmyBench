# The Environment (the owner, 2026-11-21)

Status: decided; build after adapter phase 2 (a session reads a grid by name through the adapter). Mockup (made-up
data): the published Environment Mockup artifact; its source in the session scratchpad (environment/).

> "one shared space for all tables at the env level ... each project should have its own env ... a simple trigger and
> watcher for any tables, vars, structures that show ... easy to browse on one screen ... RStudio handles this concept
> beautifully."

## The owner's answers
- **One environment per project**, replacing per-notebook environments: the project's `.venv` at its top
  (Git-ignored; `requirements.txt` shared in Git so a teammate's clone rebuilds it).
- **One Python process for the whole project, as RStudio:** every notebook and script runs in the project's one
  kernel, so every value is visible everywhere. Accepted: one long cell makes the others wait, and a crash restarts
  the one session (say both plainly on the screen: Interrupt and Restart are the session's). The local sandbox API's
  host and the canvas's Play stay their own processes (a web server each), in the same `.venv`, reading tables through
  the adapter.
- **A table enters the shared space at once:** the moment code makes it, it is a grid (named Arrow table) every
  session, the API and the canvas read by name. In the one process this costs no copy for the kernel's own tables
  (Arrow's buffers shared where the type allows); a pandas frame is converted once.
- **The `${NAME}` settings page merges into the Environment page** as its own group (Settings and secrets: names,
  sources, a secret masked; the keyring and vault rules unchanged; Show stays the user's).
- **Remove on a shared table:** a tick, off by default, "Also delete it in Python".
- **The name:** Environment.

## The screen (from the design, Fable agent 2026-11-21)
- A rail page, Environment (taking the Structures and Variables places), and the same list as the Workbench's right
  pane (folds with Ctrl+B).
- Top bar: the project, Filter, List | Grid, Add table ▾ (from a connection, a file, paste, new query, sample: the
  grid page's add-a-table wiring moves here), Refresh, Clear… (the broom: one dialog with ticks), Interrupt, Restart.
  One line under it: Python version, libraries (Libraries…), memory in use, "Nothing here is saved unless you tick Keep".
- Groups: Tables, Values, Structures, Settings and secrets; one folded line for Functions and modules and Connections
  opened in code. Columns: Name (Shared, Keep marks), Type in plain words, Size, Value (a short look), From, Used by.
  The arrow unfolds a table's columns in place (RStudio's).
- Row actions: Open (Grids, or the Structures viewer), Preview, Insert into code, Copy name, Rename, Keep with the
  project (rows into `.sab/data/`, Git-ignored), Make a sandbox variant, Send to the agent, Remove. Enter, Space, F2,
  Delete; ticks for bulk Remove.
- Replaces: the Workbench's Variables pane, the Structures page's list and rail icon (the Structures editor stays as
  the viewer), the Variables page, the grid page's Open list. The Data Explorer's open tables read the Environment's
  one list; the Data Catalog stays.

## The watcher
The trigger: after each cell runs (IPython's post-run hook), and its timer for plain scripts; it reports tables,
values and structure-shaped values (names and sizes only) and the server sends one `environment_changed` notice.

## The agent
One grouped tool, `environment(action, ...)`: list, show, libraries, add, open, rename, keep, insert, remove, clear,
interrupt, restart. Waiting for the user's Allow: clear, keep with rows, installing a library, a structure file's
delete; a secret's value is never in an answer.

## Order
1. One listing service and the notice; the tool's list and show. 2. The screen, read-only, in both places. 3. Remove,
Rename, Clear, Add table, Keep. 4. One Python per project (the project's `.venv`, the one kernel; notebooks that had
their own environment moved, said once). 5. The post-run trigger; tables shared at once through the adapter. 6. The
Structures and Variables pages fold in.
