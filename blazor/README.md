# Swiss Army Bench: the Blazor front end (preview)

The same app's front end rebuilt in **Blazor WebAssembly** (.NET 10), side by side with the classic one in `web/`
(the owner, 2026-11-23). The Python server is not rewritten: this app calls the same HTTP routes
(`src/swissarmybench/server/routes_*.py`) and listens on the same live-updates websocket (`/ws`). The classic front
end stays the default; Settings' **Front end** row (in both front ends) or the agent's `app_frontend` picks the one
the app opens, and `swissarmybench open --blazor` opens this one once.

A page this front end does not have yet says so in one line, with **Open in the classic front end** to the same
place: the classic pages share the browser's session cookie, so the link opens at once.

## Build and run

```bash
# Once: the .NET SDK (blazor/global.json pins 10.0.404, latest patch) and the classic page's packages
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0 --install-dir ~/.dotnet
export PATH=$HOME/.dotnet:$PATH
(cd web && npm ci)                       # AG Grid, Mermaid... at the classic page's versions

python blazor/publish.py                 # interop bundles, then dotnet publish -c Release: blazor/publish/wwwroot
python blazor/publish.py --debug         # the same, quicker (no trimming)
swissarmybench open --blazor --browser   # or any running server: http://127.0.0.1:<port>/blazor/
```

The server serves `blazor/publish/wwwroot` in a checkout, or `swissarmybench/web_blazor/` in the wheel, at
`/blazor/` (`server/app.py` `BlazorFiles`: a page's own address, `/blazor/connections`, answers its `index.html` so
Back, a reload and a bookmark work). `python build.py` builds it when `dotnet` is on PATH and copies it into the
wheel; without `dotnet` it builds the wheel without it and says so. The release workflow sets up dotnet from
`global.json`. `SAB_NODE_MODULES` names another `node_modules` folder (a worktree may share another checkout's).

How the page gets its session: the launcher opens `/blazor/#token=...`; `shell.js` trades the token once for the
page's cookie (`POST /session`, the same as the classic `api.ts`) and drops it from the address. No token is ever in
this app's code or files, and every request after rides on the cookie (HttpOnly, SameSite=Strict).

## Checks

```bash
cd blazor && dotnet build SwissArmyBench.Web                             # warnings are errors
dotnet format SwissArmyBench.Web/SwissArmyBench.Web.csproj --verify-no-changes
dotnet test --project SwissArmyBench.Web.Tests                          # bUnit: components and state services
cd ..                                                                    # the rest from the repository's top
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_blazor_style.py tests/test_blazor_structure.py \
    tests/test_blazor_api_types.py tests/test_frontend_switch.py
python blazor/tools/generate_api.py                                     # after a server answer changes
PYTHONPATH=src .venv/bin/python -m pytest -q tests/e2e/blazor            # Chromium; skipped with no build
```

The C# style is the `csharp-clean-code` skill's (`.claude/skills/csharp-clean-code/SKILL.md`), enforced by
`blazor/.editorconfig` and `Directory.Build.props` (`EnforceCodeStyleInBuild`, warnings as errors, nullable on):
file-scoped namespaces, braces always, `string` not `String`, usings System first, `_camelCase` private fields,
`Async` on async methods, one type per file, an explicit `Program.Main`.

## How the code is laid out

```
blazor/
  global.json, nuget.config, Directory.Build.props, .editorconfig
  publish.py                 the build (interop bundles, then dotnet publish)
  interop/                   one plain JavaScript file per widget, bundled by build.mjs (esbuild, web's packages)
    shell.js                 the session, the theme, storage, the clipboard, the live-updates socket
    agGrid.js                AG Grid: the infinite row model asking /grids/{id}/rows itself (rows never pass C#)
    mermaid.js               Mermaid: the ERD (strict security, the app's colours)
  SwissArmyBench.Web/
    Program.cs               the composition root: ApiClient, a typed client per area, the state services
    Api/ApiClient.cs         the one door: HttpClient, snake_case JSON, a refusal read into Refusal, ApiException
    Api/<Area>/              one record per server answer, one file each, and the area's client
                             (App, Projects, Settings, SessionLog, Connections, Catalog, Environment, Grids,
                             Relationships, Files)
    State/                   ThemeState, LiveUpdates (the /ws notices), ProjectState, RailState, Notes, Dialogs:
                             small services shared by the pages, each raising one Changed event
    Navigation/              the rail's areas in the classic order (Areas.cs) and their classic addresses
    Layout/                  MainLayout (the session first), Rail, StatusBar, NoteCorner, DialogHost
    Components/              ErrorNote (the one error note), Busy (the one loading state), AppDialog, NotYet,
                             Icon and IconSet (the classic line icons), AgGrid, MermaidDiagram
    Pages/<Area>/            each page; logic over about 30 lines in its .razor.cs code-behind
    wwwroot/                 index.html (base /blazor/), css/tokens.css (the classic grid.css's theme tokens),
                             css/fluent-theme.css (Fluent UI's tokens set from them), css/app.css
```

Addresses: `/blazor/` Home, `connections` (`?name=`, `?add=1`, `?kind=`, `?edit=`, `?find=1`), `catalog`,
`environment?at=tables|variables|structures|settings|libraries`, `grids` (`?grid=`, `?table=`, `?new=1`), `erd`,
`session`, `settings`; every other area of the rail is its one line and the classic link.

## Built better than the classic

The owner's "build back better" (2026-11-23): the same pages, words and behaviour as the classic front end, with
these underneath, each enforced rather than remembered.

| What | How it is enforced |
| --- | --- |
| **Answer records generated from the server.** The server has no OpenAPI document (its routes answer plain dicts), so `blazor/tools/generate_api.py` (standard library only) starts a server of its own on made-up data, calls each route it lists, and writes one C# record per JSON object under `Api/<Area>/Generated/`. Generated now: the Grids answers (GridInfo and its columns, steps and text matching; the selection's numbers; the table profile; a column's values; the Key Finder; a table's connection) and the Workbench's home, open (notebook and script) and Tables-group arrange. Hand-written, each with its reason in the script's `HAND_WRITTEN`: the started kernel, a document's session (null outside a project), a table's cell text, the Files pane's groups, a blade's summary, a step's failure, the connection swap's four answers, the made table, the connection forms and Environment rows (their fields are the kind's), and the areas written before the generator (Projects, Settings, Session, Catalog, Relationships, App), moved to it area by area. | `tests/test_blazor_api_types.py` runs the generator with `--check`: a renamed or dropped field makes the committed files differ, and the C# that read it no longer builds. |
| **One state pattern.** Every state service (`State/`) holds its value and raises one `Changed`, refreshed from the live notices (`LiveUpdates` raises each notice as `NoticeArrived`; its own value is whether the socket is open); a service or component that subscribes lets go in its `Dispose`. | `tests/test_blazor_structure.py` (every `+=` on an event has its `-=` and the class is disposable; every state service has one `Changed`), and the bUnit tests count the subscribers before and after a component closes. |
| **Size limits.** No C# method over 80 lines, no `.razor` or `.cs` file over 400, no page's code-behind over 300. | `tests/test_blazor_structure.py`, with `TOO_BIG`, a list that only shrinks (empty today). |
| **LINQ for collection work.** Filtering, grouping, ordering, mapping lists of records and which tools apply are query chains (`Where`, `Select`, `GroupBy`, `OrderBy`, `Any`, `ToList`), never a loop that builds a list. The data itself (a grid's rows, a table's records, analysis results) stays in DuckDB on the server. | Review (the owner's rule, 2026-11-23). |
| **Accessibility.** Every control has an accessible name; a dialog takes the focus as it opens, Enter saves and Escape closes it; a menu's first line takes the focus and the arrow keys, Home and End move through it; Tab follows the page's order; focus shows (`:focus-visible`). | `tests/e2e/blazor/test_accessibility.py`: our own check of every visible button, link, field and menu line on each page (axe-core is not among `web/`'s packages), and the keyboard paths of the grid page's dialog and menu. |
| **Component tests.** `blazor/SwissArmyBench.Web.Tests` (xUnit v3 and bUnit, run by Microsoft.Testing.Platform: `global.json`): ErrorNote, Busy, AppDialog, the rail, the state services' subscribe and unsubscribe, the status bar's selection, the Grids ribbon's reasons, the refusal reader. | `dotnet test --project SwissArmyBench.Web.Tests`, run by `tests/test_blazor_style.py` beside the format check of both projects. |

## NuGet packages

| Package | Version | Why |
| --- | --- | --- |
| Microsoft.AspNetCore.Components.WebAssembly | 10.0.15 | Blazor WebAssembly itself (the template's) |
| Microsoft.AspNetCore.Components.WebAssembly.DevServer | 10.0.15 | `dotnet run`'s development server (not shipped) |
| Microsoft.FluentUI.AspNetCore.Components | 4.14.5 | the component library the brief names (2026-09-30); its tokens set from the app's |
| bunit | 2.13.3 | the component tests (test project only; the owner's approval, 2026-11-23; 2026-10-25) |
| xunit.v3 | 4.0.2 | the test framework under bUnit (test project only; 2026-10-09) |

No other package. The JavaScript widgets are the classic page's own npm packages at the same versions
(`web/package.json`): `ag-grid-community` 36.2.0, `mermaid` 11.4.1, `monaco-editor` 0.57.0 and `plotly.js-dist-min`
4.2.0.

## What works (2026-11-23, part two)

| Page | State | What is there, and what is missing |
| --- | --- | --- |
| Shell | done | The rail (same icons, order and names; the names switch kept in rail.json, every window following; the extensions' areas from GET /app/areas; Canvas and Widgets while a mode offers them; the Session count; each icon a real link, so Ctrl+click, a middle click and the browser's right-click open a new tab or window), Alt+Home, views in the address with Back and Forward, the status bar (the project, its unsaved dot and Save, the server's connection, the rows in view, the selection's Count, Sum and Average, the data budget's meter past 80%) and its footer marks (the version, Update available, the zoom with Ctrl+=, Ctrl+- and Ctrl+0, Beta, Launch Claude, the credit), the command palette (Ctrl+Shift+P: the page's commands with why one cannot run, recent first) and the keyboard shortcuts sheet (?), both themes (and the two high-contrast ones) from the same tokens, the live-updates socket, the one error note (what, where, the fixes as buttons, Details with Copy, Send to the agent), the one loading state (cover after 150 ms, the time after 3 s, Cancel), the app's own yes-or-no and text dialogs (their paragraphs kept), the file chooser (the system's dialog, else the page's own picker: Places, Recent and Drives, the breadcrumb, the path box, Filter, New folder, Hidden files, Save's File name, the keys), the first-time tour (a card per place in the rail's order, the real control lit up, two made-up tables and a practice variable staged and taken away again, back where it started; Right, Left, Enter, Escape), `${` in every text box (the variables listed under it, New variable…; right-click's Text menu: Cut, Copy, Paste, Insert variable…), the missing-package prompt (Install now, Not now held for the session, its reminder) and the error note's Install now and Set it (Add variable over any page), beta mode's Leave a note… at the end of every right-click menu, the footer's area marks, the desktop app's own keys (Ctrl+W, Ctrl+T, Ctrl+N, Ctrl+Tab, Ctrl+Shift+Tab, Ctrl+Shift+T), pop-out windows (a page of the app with no rail: `panel?panel=steps|keys|connsql`). Missing: the project type's gates (closed areas are shown). |
| Home (Projects) | done | The Project Explorer's cards (Local or Shared, counts, times, Git branch, missing, an extension needed, Copied from, the folder), search, type and place filters, the sorts and the custom order, What kind of project? (put away and back), New project (name, type, Local or Shared, folder), Open project… (a plain folder made a project on the user's word), Open a file…, Paste data, Close project, each card's menu (Open, Show in folder, Copy project to…, Share or Make a local copy, Rename, Locate…, Move left or right, Remove from list, Delete… on its typed name; a shared card's Pull, Push and sync words while the Git extension is on); unsaved work asked about in the classic words ("<name> has unsaved changes.", "Let them go and open <folder>?"); the Tour button with New here? until seen; Import… (the shared import dialog, `Components/ImportDialog.razor`: notebooks, scripts and apps from another project or a file into the open project; connections and blades into the library). |
| Settings | partly | Theme, Team (no team: the needs words and links; joined: Pull, Push, Show its folder, Open on GitHub; the local projects folder; Advanced), Front end, Open every feature (gated types), Follow the agent, Click here to update, Claude, Beta (switch, Leave a note…, Export, Clear), Connect an agent. Missing: Join a team… and Start a team…'s step dialogs and Leave (they link to the classic page), the extensions' own panels, Claude's choice of install. |
| Session | done | This session's log live (`session_entry`), The agent / Me / Both (remembered), Changes, Follow the agent, each entry a link to its place (Go to it; a grid gone since says It is not open any more), the empty log's Launch Claude. |
| Connections | partly | The cards (status in a word, calls, writes, Only works on your machine), a card's detail (Change, Test, Refresh, Remove, how code names it, its tables as a tree with search and Open, configuration, where it is used, its calls), Add connection's kinds and each kind's form drawn from the backend's data (fields by part written into the code by the server, passwords, Test, Save), Find connections on this computer with Import. A connection made of your own Python: its three code boxes in Monaco (Connect, List the tables, Read a table), the environment variables they read and whether each is set here (Set it), Rows to open, Test and Save. Missing: the vault and sign-in pickers in a field, the colour swatch, Access, the Queries window, a form's generated code in Monaco (shown as text). |
| Catalog | done | One search over everything that holds data (its kinds as chips, one connection, Tables with a column, the recent searches), grouped, each result's actions (Open as grid, Preview, Copy SQL name, Query in a notebook…) on its row, its right-click menu and a double-click, the arrows and Enter; a connection's catalog offered to load. With nothing typed, the tree: each connection with its state (Load, Show only this, Copy name), its tables by database and schema, a table's columns read when it opens, the open tables, the sandbox (Sort, kept), Structures, the APIs' tables and the blades; the selected table's detail (SQL name, From, the columns and their nulls, the SQL and Python cells' code, Import its relationships); the arrows, Home, End, Right, Left and Enter. Typed, the same tree narrowed to what matches (a matched column under its table under its connection and schema; the other kinds as their own sections; Nothing matches). Missing: Insert into a cell (the Workbench is a page of the same tab here, so no cell is in front). |
| Environment | partly | Every tab from the backend's own with its count, one search over every tab, Used in, Open (a table: its grid), Rename, Remove, a library's Pin, Update and Check for newer versions, the project's Python line, following `environment_changed`. The viewer beside the list (a row's name: what it is, its parts such as a table's columns and ranges, where it is used); Settings and secrets' Add variable… (a plain value, this computer only, or a secret in the keyring) and Add key vault… (the vault kinds, each opening its form on the Connections page); Libraries' Install a library…. Missing: Clear…, Keep, Make it now, the variables' Show and rename on that tab. |
| Grids | done | A tab per table (its menu, rename in place with F2, drag to reorder, groups by connection, Undo a close, the file-changed dot) and "+" the New query page (Open tables and each connection that runs SQL, a draft's SQL tray, the tables to fix); split views and the Compare row (Compare with…, the key picker with the Key Finder's pairs, the grids lined up and scrolling together, the modes and their counts, diff options, Stop compare, Close this side), kept in the address; AG Grid with the server's row windows; the ribbon in rows by what they act on (Table, Transformations as the steps strip, Column, Compare), folding its words when narrow; the selection like Excel with Count, Sum and Average; the right-click menus on cells and headers; the header's profile on resting and in the header; the value viewer (Formatted or Table, Raw text or JSON, drilling in); every step editor (the SQL step too) and the steps panel; Undo and Redo (Ctrl+Z, Ctrl+Y); profiles of a column and of the view; the Key Finder; the Relationships window (find, the joins in use, saved sets: Save as a set…, Check, Apply, Import, Export); Export (CSV, Excel, Parquet with the classic's options); Copy as code; Text matching; the tables list (Python sessions' tables, Open and Reload); opening, pasting and dropping files (a workbook's sheets picked); a sandbox table's bar (Add row, Delete rows, Reset, a cell edited in place); a file changed on disk (Reload, Not now); Connection: <name> (another connection's same table, a pick, a query reviewed, Undo, Point these at…); Find data (Ctrl+K); the palette's Table, Column, Steps, Cell, Tabs and Application commands; the project's group (Save asking Keep its rows once, Copy to…, Export outline, Close, Autosave, Private, Save now); the palette's Analyze entries (every analysis from the server's toolbar, opening `analyze?analysis=<id>&table=<grid>`); View steps, the Key Finder and the SQL window in windows of their own. |
| ERD | done | The model drawn by Mermaid (this project's tables or all), Fit, the Relationships window from its bar (Find relationships with the evidence, Add and Took out; the joins in use filtered, selected, their Run and Kind, Delete selected with Undo; saved sets with Check, Apply, Rename, Delete, Import and Export), Export the model as JSON. |
| APIs | partly | The library's APIs as cards (operations, sign-in, where the document came from); an API's explorer: its operations by method and path, one operation's inputs and body (its made-up example in Monaco), what it answers (the schema), its named schemas and where each is used; Try it: the call sent, its status and time, the answer opened as a structure right there (tree, path, Open as grid) and in Structures. Missing: Add API (the classic page's link), Author a call and Return as table, Write rows, Refresh's diff, rename and delete, the learned shapes and Build, Discover, search across APIs, the local sandbox APIs and the endpoint wizard. |
| Structures | partly | The open structures; New, Open a file… (JSON, YAML, XML, TOML), Paste…; a structure as a tree (folded past three levels, a node's children two hundred at a time, Show more), a node's path with Copy path and Open as grid; its text in Monaco in its own format, Apply (a text that does not parse is kept and its error said), Save to its file; Close; following `structures_changed`. Missing: the steps (pick, filter, rename...), the tree's edits, search, Format, Reload / Keep mine, Save as, lineage, a structure as a tab on the code pages. |
| Notebooks, Scripts | partly | Two pages (`notebooks`, `scripts`, `?path=` and `?new=1`), each its own Files pane on the right (the server's groups; a made file marked read-only) and the Blades pane (your blades and the starters by family, searched; Insert puts a blade's line at the cursor), each shown or hidden from the page's status bar and remembered. Monaco with the server's intelligence (completion, signatures, hover, the lint as you type). The notebook: Python, SQL (with its connection, DuckDB's open tables by default), Markdown (drawn until edited) and DAX cells; Run (Shift+Enter, Ctrl+Enter, Alt+Enter), Run all, the outputs as they arrive (text, errors with the server's explanation, pictures, Plotly figures, Markdown, HTML in a frame that runs no script), the kernel asking for a line, cell numbers, move and delete; the Tables group's read-only cells by the server's rules, each run as its table. The script: one editor, Run file (F5), Run selection (Ctrl+Enter), the console with a line of Python. The project's one Python session in the page's status bar (Ready, Running…, Interrupt, Restart, what happened to it). New, Open…, Save (Ctrl+S), Save as…. Missing: tabs and splits, the debugger, the palette, Copilot's ghost text, HTML cells' designs, the variables and lineage panels, a notebook's Outline, Go to definition and rename (F12, F2), Format, the script's Tables region, colours in a traceback (shown as plain text), a file changed elsewhere (Reload / Keep mine). |
| Analyze | partly | The toolbar of every analysis by group (the server's words: everyday questions first); the one guided form the server plans (POST /analyze/plan: the table, each slot's columns with their first values, the columns that do not fit with why, what is missing, Make it fit and Suggestions with Apply, the sentence of what will run, More options, What your data should look like with Try it on this sample); Run gated with Cancel; the board's cards in a twelve-column grid (a note as Markdown, a Plotly figure, a picture, a Mermaid diagram), the fresh ones marked, Remove; a result's Show the math, Open as grid, Copy code, Run again and its hand-offs (Show these rows, Exclude these). Missing: moving and resizing cards, saved dashboards, the board's themes, Page view and Print to PDF, the markdown export, Check this table's ranking view, What can I do with a column?, a Vega-Lite or table card (said, with the classic link). |
| Extensions | partly | A card per extension (what it adds, its status in the classic words: Preinstalled, Available, Installed, Coming), Install, Remove asked first; a copy that cannot install says what to run (the server's words). Missing: folder extensions (their cards, Load again, Show its folder, New extension), an extension's own panel, Install's progress through the restart. |
| Canvas, Widgets, Source Control, Power BI, Code App | not yet | The classic pages' links. |

## Decisions for the owner

- Fluent UI Blazor 4.14.5, not 5.x: 5.0 is a rewrite on new web components (released 2026-09/10); 4.14.5 is the
  current release of the line its documentation and samples cover. Moving to 5 later is a contained change.
- The pages keep the classic page's own CSS class names and measures (the rail, `.btn`, the area page), with
  Fluent UI's tokens set from the same theme tokens; most controls are plain HTML styled like the classic page
  rather than Fluent's web components, so both front ends look alike. Using more of Fluent's components is a
  choice to make once the pages are all here.
- AG Grid's rows go from the server straight into the grid (JavaScript `fetch` in `agGrid.js`) rather than through
  C#: thousands of cells crossing the interop on each scroll would be slow. The grid's steps, sort and cards are C#.
- The answer records are generated from the server's own answers on made-up data, not from an OpenAPI document:
  the server has none (its routes answer plain dicts). Giving the routes typed answer schemas (and an OpenAPI
  document) would let the generator read types instead of samples; until then a field that is sometimes a number
  and sometimes text is said by hand in the generator (`types`), and answers no sample pins stay hand-written.
- A grid's header: a click on its name selects the column (as the classic grid); sorting is the small arrow beside
  the name; resting over it shows the column's card (its profile), as the classic.
- Pop-out windows (the steps panel, the Key Finder, the connection's SQL window) are real windows, as the owner
  designed them (2026-11-23): `panel?panel=steps|keys|connsql` opened with window.open (the desktop app's window,
  else a browser pop-up), drawn by `Layout/WindowLayout` with no rail; the grid page hears their changes by the
  live notices.
