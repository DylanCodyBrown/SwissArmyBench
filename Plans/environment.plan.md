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
- **A table enters the shared space at once:** the moment code makes it, it is a table (named Arrow) every
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

## One page, search and browse that work
The owner: "Variables, tables, structs all are one page. Not exactly like RStudio but similar with a search and browse
that works." So:
- **One page, one list:** tables, values, structures and settings together, each row its kind's icon and colour;
  the groups are a filter (chips: All, Tables, Values, Structures, Settings), not separate screens.
- **Search that works:** one box over names, a table's columns, a structure's keys and paths, a value's type and
  short text, a setting's source; matched in any case and by parts (cust finds customer_id and CustomerKey), as the
  Data Explorer already does (domain/explorer.py: reuse it, never a second search); the match is shown highlighted in
  the row, and a column or a path that matched opens the row there.
- **Browse that works:** every row unfolds in place, one level at a time: a table to its columns (type, blanks,
  range, first values), a structure to its keys down its paths, a dictionary or a list of a value to its items, a
  setting to where it comes from and what uses it. Keys move through it (arrows, Right opens, Left closes, Enter
  opens the item's viewer), and the place is kept when the list refreshes.
- Not RStudio's three fixed panes: one list that is searched and browsed, the viewer opening beside it.

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

## Where it is used, and grids (the owner, 2026-11-22)
"I should be able to see where it's used anywhere in the app and know if it's a grid or not ... grids are just links
to the existing tables. Grids is just the visualization layer, not duplicate data. Tables can be created in app."
- **Used by, everywhere:** each row lists every place that uses it, each a link that goes there: the grids showing it
  (with their steps), notebook and script cells (by number), canvas widgets (page and widget), API.py endpoints,
  analyses on the Analyze board, relationships in the ERD, exports, other tables made from it. A count in the list
  ("Used in 6"), the whole list in the viewer.
- **Is it in a grid:** a mark on the row ("In 2 grids", a click lists and opens them); a grid is a view, never a copy,
  so its memory is the table's.
- **Made in the app:** From says so (Pasted, New query, Save as table from a grid, Add table), like a connection's.

## Tabs by kind (the owner, 2026-11-22)
"Should be grouped by type with a tab at the top to move between them instead of all one table." So the page has a
tab for each kind (Tables, Values, Structures, Settings and secrets), each with its own columns (Tables: rows by
columns, columns, grids, used in, from; Values: type, value, used in, from; Structures: format, size, paths, used in,
file; Settings: kind, value, comes from, used in). The one search runs over every tab: each tab's count lights up
with its matches, and a line names the other tabs that match ("Also matches in Values (1)"). Mockup: the published
Environment Mockup, version 6.

## Corrections (the owner, 2026-11-22)
"Values should be variables. And we don't need to know what is running and detection should be automatic, no need for
a refresh, and connections are where you add tables." So: the tab is **Variables** (what the code makes); no running
cell, Interrupt or Restart on this page (they stay in the Notebooks and Scripts pages); no Refresh: the list follows
the watcher's notices by itself; no Add table: tables are added on the Connections page (and made by code, or by
Save as table from a grid). Supersedes the bar and session line above.

## Libraries (the owner, 2026-11-22)
"What would be helpful is a drop down to see all the libraries that are in the env" / "Libraries should be another
type". So Libraries is a fifth tab (not a dropdown), with a search box (by name), each library's name, version and where it is imported (a
notebook or script, the adapter, the canvas, a connection, API.py; or "not imported yet"), and Install a library…
(the one missing-package prompt's install into the project's .venv; requirements.txt updated so a teammate gets it;
the agent's waits for Allow). Its columns: name, version, what it is for, imported in, from (requirements.txt); a row's actions: Upgrade, Insert import, Remove.
- **Pin and update** (the owner: "With a pin and update option"): a Pinned column (Pin keeps the library at its
  version, written `name==version` in requirements.txt; Unpin writes it unpinned); the Version column shows "→ x.y"
  when a newer one exists (checked when the tab opens, never in the background), a click updates that one; Update all
  not pinned updates the rest in one go; a pinned library is never updated by Update all. Updating and installing go
  through the one install prompt and the agent's wait for Allow.

The owner approved the mockup (version 10, 2026-11-22: "This looks good ... it's still pretty dense but a screen like
this has to be"). It is the brief for building this page. To keep the density calm: the yellow note is the mockup's
only; the viewer folds away (Ctrl+B) to give the list the whole width; less-used columns (From) can be hidden from the
column headings' menu and the choice is kept per tab.
