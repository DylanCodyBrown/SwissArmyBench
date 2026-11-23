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
.venv/bin/python -m pytest -q tests/test_blazor_style.py tests/test_frontend_switch.py
.venv/bin/python -m pytest -q tests/e2e/blazor                           # Chromium; skipped with no build
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

## NuGet packages

| Package | Version | Why |
| --- | --- | --- |
| Microsoft.AspNetCore.Components.WebAssembly | 10.0.15 | Blazor WebAssembly itself (the template's) |
| Microsoft.AspNetCore.Components.WebAssembly.DevServer | 10.0.15 | `dotnet run`'s development server (not shipped) |
| Microsoft.FluentUI.AspNetCore.Components | 4.14.5 | the component library the brief names (2026-09-30); its tokens set from the app's |

No other package. The JavaScript widgets are the classic page's own npm packages at the same versions
(`web/package.json`): `ag-grid-community` 36.2.0 and `mermaid` 11.4.1 so far.

## What works (2026-11-23)

| Page | State | What is there, and what is missing |
| --- | --- | --- |
| Shell | done | The rail (same icons, order and names; the names switch kept in rail.json, every window following; the extensions' areas from GET /app/areas; Canvas and Widgets while a mode offers them; the Session count), views in the address with Back and Forward, the status bar (the project, its unsaved dot and Save, the server's connection), both themes (and the two high-contrast ones) from the same tokens, the live-updates socket, the one error note (what, where, the fixes as buttons, Details with Copy, Send to the agent), the one loading state (cover after 150 ms, the time after 3 s, Cancel), the app's own yes-or-no and text dialogs, the file chooser (the system's dialog, else a typed path). Missing: the right-click Open in a new window, the rail's arrow keys, the project type's gates (closed areas are shown). |
| Home (Projects) | done | The Project Explorer's cards (Local or Shared, counts, times, Git branch, missing, an extension needed), search, type and place filters, the sorts and the custom order, What kind of project? (put away and back), New project (name, type, Local or Shared, folder), Open project…, Open a file…, Close project, each card's menu (Show in folder, Share or Make a local copy, Rename, Move left or right, Remove from list, Delete… on its typed name). Missing: Paste data, the tour, Copy project to…. |
| Settings | partly | Theme, Team (no team: the needs words and links; joined: Pull, Push, Show its folder, Open on GitHub; the local projects folder; Advanced), Front end, Open every feature (gated types), Follow the agent, Click here to update, Claude, Beta (switch, Leave a note…, Export, Clear), Connect an agent. Missing: Join a team… and Start a team…'s step dialogs and Leave (they link to the classic page), the extensions' own panels, Claude's choice of install. |
| Session | done | This session's log live (`session_entry`), The agent / Me / Both (remembered), Changes, Follow the agent, each entry a link to its place. |
| Connections | partly | The cards (status in a word, calls, writes, Only works on your machine), a card's detail (Change, Test, Refresh, Remove, how code names it, its tables as a tree with search and Open, configuration, where it is used, its calls), Add connection's kinds and each kind's form drawn from the backend's data (fields by part written into the code by the server, passwords, Test, Save), Find connections on this computer with Import. Missing: the Python connection's three code boxes, the vault and sign-in pickers in a field, the colour swatch, Access, the Queries window, the code in Monaco. |
| Catalog | partly | One search over everything that holds data, grouped, Copy the SQL, Open a table. Missing: the browse tree and a table's detail side. |
| Environment | partly | Every tab from the backend's own with its count, one search over every tab, Used in, Open (a table: its grid), Rename, Remove, a library's Pin, Update and Check for newer versions, the project's Python line, following `environment_changed`. Missing: the viewer beside the list, Clear…, Keep, Install, Settings and secrets' Add variable and key vaults (linked to the classic page), Make it now. |
| Grids | partly | A tab per table and "+" the New query page (DuckDB SQL into a new table, Try it with sample data), AG Grid with the server's row windows and its header sort, the steps strip (on or off, removed, the failing one marked), Undo and Redo, a column's card (its numbers, Sort, Keep rows where, Rename, Remove the column), Close table, following the server's notices. Missing: the cell selection and its statistics, highlights, the steps panel's editors (group by, transform, bucket, categorize), Compare, export, Copy as code, the header profiles, the SQL draft tray, split views. |
| ERD | partly | The model drawn by Mermaid (this project's tables or all), Find relationships with the evidence and Add, the joins in use with Delete and Undo. Missing: the Power BI style canvas and its dragging, relationship sets, Key Finder. |
| APIs | not yet | The classic page's link. |
| Structures | not yet | The classic page's link (the Environment's Open of a structure goes there). |
| Notebooks, Scripts | not yet | The classic pages' links (Monaco, the kernel's runs and the outputs are the next large piece). |
| Analyze | not yet | The classic page's link (Plotly cards and the guided form). |
| Canvas, Widgets, Extensions, Source Control, Power BI, Code App | not yet | The classic pages' links. |

## Decisions for the owner

- Fluent UI Blazor 4.14.5, not 5.x: 5.0 is a rewrite on new web components (released 2026-09/10); 4.14.5 is the
  current release of the line its documentation and samples cover. Moving to 5 later is a contained change.
- The pages keep the classic page's own CSS class names and measures (the rail, `.btn`, the area page), with
  Fluent UI's tokens set from the same theme tokens; most controls are plain HTML styled like the classic page
  rather than Fluent's web components, so both front ends look alike. Using more of Fluent's components is a
  choice to make once the pages are all here.
- AG Grid's rows go from the server straight into the grid (JavaScript `fetch` in `agGrid.js`) rather than through
  C#: thousands of cells crossing the interop on each scroll would be slow. The grid's steps, sort and cards are C#.
