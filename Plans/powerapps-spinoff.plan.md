# Swiss Army Bench Power Apps Edition: the hand-over

**Changed (the owner, 2026-11-17): the edition lives in THIS repository, with a separate install command**
("I wouldn't mind including the edition right in this repo and a separated install command"), behind the
front-end and back-end boundary of section 8a, now a rule in CLAUDE.md: **editions never modify the front end.**
Read "the new repository" below as "the edition's backend, `src/swissarmybench/editions/powerapps/`, in this
repository"; section 2's clone steps and section 8's parity steps 1 and 3 are not needed (one front end, one
repository). Its install: `install-powerapps.ps1` / `install-powerapps.sh` installing `swissarmybench-powerapps`
(built from this repository, the shared front end inside), released with the Streamlit Edition.

Status: **ready to start** (the owner, 2026-11-17: "Write a spin off plan with all of the app design notes in the
context so that I can start up a new git repo just for the power apps edition. Is there anything you suggest
where we can keep the front ends in parity while creating new editions").

This document is the hand-over. A new repository (and a new agent in it) should be able to start from this file
alone, plus the files it says to copy. Read it top to bottom once; then use section 9's first-week list.

It supersedes the "edition in this repository" choice in Plans/code-apps.plan.md: the Power Apps Edition now
lives in its own repository, built from this one. Everything else in that plan (pac-first, TypeScript data,
the connector spike, canvas apps later) stands and is repeated below.

---

## 1. What the Power Apps Edition is

A desktop bench for building **Power Apps code apps** (React and TypeScript web apps that run in Power Apps and
reach Dataverse and connectors through the Power Apps SDK), and later **canvas apps**. Everything a maker does,
in one place, with an agent that can do all of it too:
1. Sign in to an environment; start a code app or open one.
2. Browse the environment's data: Dataverse tables (columns, relationships, rows to look at) and connectors
   (operations, inputs, outputs); add them to the app.
3. Write the app in TypeScript and React with full IntelliSense, components previewed, the app running live.
4. Check it, push it, see its versions.
5. Turn an OpenAPI document into a custom connector.

**pac does the work.** Every project action is a Power Platform command line call (`pac auth`, `pac code init`,
`pac code add-data-source`, `pac code push`, `pac connector create/update`), shown and parsed. We write no
project-management code of our own. Check Microsoft's current pac and code apps documentation before building
each piece; the tooling is new and changing. Record what you relied on in `docs/verified.md`.

Its sister is **Swiss Army Bench Streamlit Edition** (this repository: data work and Streamlit apps).
(A Lite edition was planned and scrapped, 2026-11-17.)

## 2. Starting the new repository

**Recommended: start it as a copy of this repository with its history, then strip it.**
```
git clone https://github.com/DylanCodyBrown/SwissArmyBench swissarmybench-powerapps
cd swissarmybench-powerapps
git remote rename origin upstream          # this repository stays reachable as "upstream"
git remote add origin https://github.com/DylanCodyBrown/SwissArmyBench-PowerApps.git   # the new, empty one
git checkout -b main
git push -u origin main
```
Keeping the history is what makes section 8's parity work: shared files can be brought over later with
`git fetch upstream` and a merge, instead of copying by hand.

Then, in the first branch, strip what this edition does not have (section 5's "Drops"), rename the package
(`swissarmybench-powerapps` on PyPI; the import name `swissarmybench_powerapps` or kept `swissarmybench`: decide
once, section 10), and set the status bar's name.

## 3. Copy and keep these documents (the design notes)

These carry the design. Copy them as they are, then adapt only what is about the Streamlit Edition:
- **`docs/design-principles.md`**: the design rules (purpose first, three actions or fewer, placement, windows,
  layout patterns, the visual system, words, interaction patterns, the checklist at the end). The single most
  important file to keep in step between editions (section 8).
- **`CLAUDE.md`**: the project rules for agents. Rewrite its "what exists" and layout parts for this edition; keep
  the golden rule, the posture, the commands, the commit rules, the gotchas.
- **`REFACTOR.md`**: the code's layers and why (Cosmic Python: domain, services, adapters, server; imports point
  inwards; one file per feature per layer; nothing deeper than `src/<package>/<folder>/<file>.py`; 1,500 lines
  a file at most; `tests/test_architecture.py` checks it).
- **`Plans/swissarmybench-build-plan.md` section 0** (working agreements) and **section 6** (security musts):
  copy into the new build plan.
- **`docs/verified.md`** and **`docs/ideas.md`**: start empty, same use (what was checked against the real thing;
  decisions and open notes).
- **`Plans/code-apps.plan.md`**: the history of how this edition was decided.

## 4. The owner's decisions and preferences (all of them, for this edition)

### How the owner works with us
- **Full words, no acronyms** in anything a person reads (screens, docs, messages to the owner): "Random Access
  Memory", not RAM. Product and file names (`pac`, `TypeScript`, `.tsx`) are fine.
- A team, not a service: say what you recommend and why; ask only when the choice is the owner's.
- **"Go with your best judgment"**, leaning towards giving the agent the work.
- Screenshots of every visible change, reviewed before a merge.

### The golden rule (2026-11-14)
**Every single thing the user can do, the agent can do too, through the tool connection (MCP), with no prompts.**
A new user action gets its agent command in the same change. Exceptions: the agent cannot answer its own
approval requests; no answer ever holds a password's value; a few user-only switches (Launch Claude, the bypass
setting, Follow the agent) are refused to the agent (403) and listed with the reason.

### The posture (keep it, with this edition's one change)
- 127.0.0.1 only; a token on every data route, or the `sab_<port>` cookie the token buys once (HttpOnly,
  SameSite=Strict, a per-start secret, our own Origin on unsafe methods).
- Nothing written to disk except what the user asked for (saves, exports), the audit log, small named state
  files, and (beta mode) the redacted beta log.
- **Only made-up data** in tests, examples and screenshots.
- Never a secret, token or password in a file the app writes, a project, the library, an export, a log or an
  answer to the agent: a secret's *source* is named (keyring, environment variable, vault entry), never its value.
- Cell values and data are untrusted: given to the agent only inside clear data markers, never as instructions;
  names from data are written as code in context.md.
- **One request leaves the computer on its own: the update check** (PyPI's JSON for the package). Everything
  else that leaves is the user's own action. **This edition's change:** its purpose is talking to Power
  Platform, so calls made by pac and the Power Platform reads the user starts (environments, tables, connectors,
  push) are the product, always on the user's action or the agent's command, never in the background on their
  own. Write that into the posture explicitly before the first such call.
- Ask before adding a dependency the plan does not list. Each connection's or project's own packages (pac,
  Node.js, Deno) are installed on the user's word through the missing-package prompt, never silently.

### Words, names and families (decided)
- **Connection** = something that exposes tables you can query, named by the connection. A thing without
  tables (a key vault) is not a connection.
- **Blades** = text dropped into a cell (snippets). **Functions** = code you call: its definition goes into the
  project's functions file, only the call into the cell. Right-click: "Insert a blade…", "Insert a function…".
- **Structures** = JSON, YAML and XML documents (payloads, configurations), with steps, lineage, Open as grid.
- **APIs** = their own page, an explorer (search every operation, inputs and outputs, examples, schemas,
  Refresh with what changed); built from blades (one API blade, one web call blade per operation); **Return as
  table** is the only gate to querying a call in SQL; DuckDB does the conversion. In this edition the APIs page
  becomes **Connectors** (section 5).
- **The library** = connections, APIs, vaults, blades and variables live on this computer, outside any
  project, as a folder of plain text files made to be a Git repository (no secrets in it; per-computer values
  in `local/`, ignored by Git). Both editions read the same library format.
- **Projects are folders** (no zip file), shareable in Git as they are; the app's state in a hidden `.sab/`
  folder; rows only on the user's tick, in `.sab/data/`, ignored by Git.
- **Writes are blades with a dry run first** ("dry_run = True"; the agent writes only after the user said to,
  in their own words, in that conversation). No writing through SQL.
- Every connection setting can come from an environment variable (the Function App and deployment parity).

### The screens (decided; keep in both editions)
- **The rail**, down the left of every page and window, in the order of the work; a click moves this tab,
  every icon lands on a page (no pop-out menus), Settings at the bottom. This edition's order: Connections,
  Variables, Grids (Dataverse), ERD (Dataverse relationships), Connectors, Structures, Blades, Code App,
  Components (TSX previews), Session; Settings.
- **The status bar** on every page: the name and version at the left; **zoom** (- 100% +) beside Beta, with
  Ctrl + mouse wheel, Ctrl+= / Ctrl+- / Ctrl+0 on every page, every window following; Launch Claude.
- **Session page**: a live log of what the agent made and did, each entry a link; **Follow the agent** brings
  what it works on to the front.
- **Launch Claude**: Claude Code (or Desktop) started in a prepared folder with **context.md**, the app's live
  picture kept current (connections and their names, tables, the model, variables by name, documents, the tool
  guide), names as data, a size budget.
- **The Workbench**: code in its own browser window (never in the data page), tab groups, pop-out tabs,
  the palette, the console; **IntelliSense** (member list with documentation, parameter info with the current
  argument in bold, hover, go to definition) and **lint as you type**; the **Data Explorer** pane (one search
  over connections, tables, columns, variables, blades; pop out into its own window; Insert writes the right
  code for the cell's language).
- **Variables page**, **connection colours** (a colour per connection on everything tied to it; the rail's kind
  colours reserved), **Connections page** (cards, a table tree, usage, configuration, calls this session).
- Design principles 8.11 (getting around: the mark goes home, Back is the browser's) and 7.8 (the product's
  name is not on its screens, only in the status bar).

### Engineering rules
- Typed Python (mypy strict) and TypeScript (strict); ruff check and format; `npm run typecheck`.
- Tests first for anything with rules; browser tests (Playwright) for every visible change; the full suite before
  a merge; a test that every stylesheet's braces balance (a merge once dropped one and unstyled half the app).
- The agent's tool list has a size budget in `tests/test_cli.py`; the agent's index stays under 4,000
  characters.
- **Commits:** no `Co-Authored-By` line and no model names; the credit to Claude is in the README.
- Release: a version tag builds, tests the installers on Linux, Windows and macOS, and publishes to PyPI and
  the GitHub release; pushing to `main` releases, so only on the owner's word.
- Parallel work: one agent per branch in its own worktree, a written brief per branch (the owner's words
  quoted, what to build, tests, docs), the coordinator merges and reviews screenshots. After a container restart
  a stopped agent's work is on its branch; a new agent finishes it from the brief plus a list of every change
  the owner made since.

## 5. What it keeps, changes, drops, adds (from this repository)

**Keeps:** the server shell and its security; the rail, navigation, themes, tokens and icons; the status bar,
zoom, palette; the Workbench window (tabs, groups, pop-outs, console, IntelliSense machinery); the library and
the Variables page; Structures; the APIs explorer (as Connectors); the Data Explorer; the Session page and Follow;
Launch Claude and context.md; the agent's door; the updater, tray, installers, beta log; the Connections page
(Dataverse only).

**Changes:** Connections to **Dataverse** (TDS for SQL speed, the Web API where TDS cannot); APIs to
**Connectors** (the environment's connectors, each one's operations and shapes, **Add to app** =
`pac code add-data-source`; custom connectors = `pac connector create`); the Workbench's languages to
**TypeScript and TSX** (Monaco's own TypeScript service with the project's types and the generated services);
the data notebook to **SQL and TypeScript cells** on **Deno's Jupyter kernel** with DuckDB's Node package
(`@duckdb/node-api`), one DuckDB shared by both cell kinds; the project scaffold to `data.ts` and `.ts` modules.

**Drops:** the Python data features (the Analyze menu, regression, time series, Visualizations dashboards,
compare and tie-out, the Key Finder), Python notebooks and kernels, the Streamlit canvas, HTML/DAX cells,
Power BI, Trino, SQL Server and the other databases, the lakes and SharePoint connections, the Python write
blades.

**Adds:** pac (found, installed on the user's word, signed in: `pac auth`), environments; the **Code App
project** (`pac code init`, Vite + React + TypeScript per Microsoft's current template, `npm install`); data
sources; **Run live** (the dev server and the code apps local runner shown in a pane through our proxy, as
Streamlit is today); **component previews** (a TSX cell or a `.tsx` file's preview with sample props from
made-up data or a Dataverse table's first rows); **push and versions**; custom connectors; TSX blades (forms,
galleries, grids, charts bound to Dataverse) and TypeScript functions; context.md for this edition.

**The riskiest piece, proved first:** a connector's generated service called from a notebook cell, inside the
code apps host (its local runner). Spike it before building on it.

**Later: canvas apps.** `.msapp` unpacked to source (Power Fx and YAML: whatever current pac uses), edited with
Power Fx IntelliSense, packed and imported back. A plan of its own after code apps.

## 6. Its first work, in order (branches of the size used here)
1. **Strip and rename** (section 2): drop section 5's list, the package and installers renamed, the status bar
   name, the rail's areas; the suite green.
2. **The pac layer:** find and install pac, Node.js, Deno; run, parse and show commands; sign-in and
   environments; the posture's new paragraph.
3. **The connector spike** (section 5).
4. **The Code App project** via pac, and Run live in a pane.
5. **The data notebook** on Deno (SQL and TypeScript cells on DuckDB), Dataverse into grids, `data.ts`.
6. **Connectors and custom connectors** in the explorer.
7. **TSX previews, TSX blades, TypeScript functions, push and versions.**

## 7. Not checkable in a container
A real Power Platform environment, pac signed in to a tenant, `pac code` against it, the local runner, custom
connector creation: checked on the owner's machine. Tests stand in for pac with a recorded fake (its commands
and outputs) and for the environment with made-up tables and connectors.

---

## 8. Keeping the front ends in parity (the owner's question)

Two repositories that share most of a front end drift apart quickly unless sharing is designed in. My
recommendation, in three steps, cheapest first:

### Step 1, from day one: a shared-paths manifest and a drift check (cheap, do it now)
- Both repositories carry the same **`parity.toml`**: the list of shared paths, the files both editions use
  as they are. For example: `docs/design-principles.md`, `web/static/grid.css`'s token block, `web/src/dom.ts`
  (icons, buttons), `nav.ts`, `rail.ts`'s machinery, `theme.ts`, `zoom.ts`, `bottomBar.ts`, the Workbench's
  editor and tab-group modules, `lazy/codeEditor.ts`, Structures, the APIs explorer, the Data Explorer, the
  Session and Variables pages; on the server, `security.py`, `http.py`, the library adapters, the agent
  command framework, the updater.
- A small CI job in the Power Apps repository (**parity check**) fetches `upstream` and lists every shared file
  that differs, with the diff. Not a failure at first: a report on every pull request, so drift is seen.
- Bring shared changes across with **`git fetch upstream && git merge upstream/main`** (history was kept for
  this), resolving only edition files. Fixes to shared files are made in the Streamlit repository first, then
  merged across: one direction, one source.

### Step 2, in this repository soon: stop shared files from knowing about editions
Drift mostly comes from editing shared files for one edition. Give the shared code **registries** so an edition
adds itself without touching them (the "kit registry" idea already on this project's list):
- the rail's areas, pages and icons; the palette's and agent's commands; the Settings sections; the connection
  kinds and their forms; the cell kinds and editor languages; the starter packs; context.md's sections.
- Each edition registers its own in its own files (`edition.ts`, `edition.py`). A shared file that needs an
  `if edition == ...` is the sign something should be a registry.
Do this in this repository before the spin-off's first strip, so the strip deletes registrations rather than
editing shared files.

### Step 3, when both editions are stable: shared packages
When merging `upstream` becomes routine and the shared paths stop moving, extract them into a third
repository published as packages both editions pin to a version:
- **`@swissarmybench/ui`** (npm): the shell (rail, navigation, status bar, zoom, themes, tokens, icons), the
  Workbench machinery, Structures, the APIs explorer, the Data Explorer, Session, Variables.
- **`swissarmybench-core`** (PyPI): the server shell and security, the library, Structures' and APIs' services,
  the agent command framework and MCP door, the updater and installers' templates.
- **A shared conformance test suite** (Playwright and pytest) in the core repository that each edition's CI runs
  against itself: the rail, navigation and Back, zoom, themes and contrast, the palette, the agent parity check.
- `docs/design-principles.md` lives in the core repository; each edition links it.
Updating an edition is then a version bump (Dependabot or Renovate opens the pull request).

**Why not extract on day one:** the shared parts are still changing daily (this conversation changed the rail,
the status bar, the Data panel and the library in one day); packages before the shapes settle would slow both
editions down. Step 1 makes drift visible now, step 2 removes its main cause, step 3 makes parity automatic.

## 8a. The boundary: one front end, editions are backends (the owner, 2026-11-17)
"Would be cool if we could set a boundary on what is front end and what is back end for the app and for future
editions we could just develop the back end piece and leave the front end intact"

This is section 8's end state, chosen as the goal: **one front end, shared by every edition; an edition is a
backend.** The front end draws whatever the backend says exists.
1. **The contract:**
   - **`GET /app/manifest`**: the edition's name and version; its rail areas (name, icon, page kind, order);
     its commands (id, title, keys, arguments, where they show); its connection kinds with their **forms as
     data** (fields, labels, kinds, sources, environment-variable choices, sign-ins); its cell kinds and editor
     languages; its Settings sections; its starter packs; its context.md sections.
   - **The routes as an OpenAPI document**, generated from the server; the front end calls only what is in it.
   - **Contract tests on both sides:** the backend's manifest and routes against the schema; the front end's
     browser tests against a stand-in backend serving only the contract.
2. **A front end of general pieces**, drawn from the manifest: a grid of rows; a searchable tree (connections,
   Structures, the Data Explorer); a form from field descriptions; cards on a dashboard; the editor (tabs,
   IntelliSense, console); an explorer (operations, inputs, outputs); a log (Session); the rail, status bar,
   zoom, palette, themes and Settings. A new edition's backend says "Connectors: an explorer over this route"
   and the page exists.
3. **Plug-ins for the genuinely unique screens** (the Streamlit canvas, TSX previews, later a canvas app
   designer): front-end modules the manifest names, loaded on demand, kept with the shared front end.
4. **The agent's tools come from the same manifest**, so a command is a button, a palette entry and an agent
   tool at once: the golden rule by construction.
5. **Packaging:** the front end becomes `@swissarmybench/ui` (built once, its build bundled into each edition's
   wheel as `web_static` is today); each edition's repository is its backend plus that package at a version.

**Order:** do this in this repository **before** the Power Apps repository starts (about 3 to 4 branches: the
manifest and its schema; rail, commands and Settings from the manifest; connection forms as data; the general
pages drawing from it, with today's specific screens as plug-ins). It replaces section 8's step 2 (registries:
the same work, with the registries on the backend side of a stable line) and makes step 3's `ui` package the
natural result. The Power Apps repository then starts as a new backend plus the shared front end, and never
strips the front end.

## 9. The new repository's first week
1. Create it (section 2); copy section 3's documents; write its CLAUDE.md from this file's sections 1, 4 and 5.
2. Add `parity.toml` and the parity check (section 8, step 1).
3. Branch 1: strip and rename (section 6.1).
4. Branch 2 and 3 in parallel: the pac layer; the connector spike.
5. Decide section 10's questions with the owner.

## 10. Open questions for the owner
1. The Python import name: keep `swissarmybench` (the edition's code imports as today) or
   `swissarmybench_powerapps` (both editions installable side by side on one computer).
2. Both editions on one computer at once: one port and one state folder each, or one shared library folder
   (recommended: shared library, separate state and port).
3. Can a code app project also hold Python helpers (a script that seeds Dataverse), or TypeScript only?
4. Section 8a's front-end and back-end boundary in this repository before the spin-off starts (recommended),
   or after.
