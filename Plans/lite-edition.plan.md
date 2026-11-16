# Swiss Army Bench Lite (a future plan)

Status: **planned, not started** (the owner, 2026-11-16: "save this as a future plan").

## The owner's words (2026-11-16)
- "how hard would it be to build an install option that installs a lite version of this app that has the
  grids visualizations ERD connections and blades that is meant for data analysis work only and is geared for
  less advanced users that just want to let an agent help them write queries and see data and analyze data"
- "we can add Swiss Army Bench and Swiss Army Bench Lite as the app name in the bottom left of the app"
  (done: the status bar's name follows the edition; `SWISSARMYBENCH_EDITION=lite` says Lite)
- "I would want two seperate pypi releases"

## What Lite is
The same app, fewer parts: **Grids, Visualizations, ERD, Connections, Blades and Settings**, with the
Analyze menu, Transformations (steps, the SQL step's window), projects (.sab) and the agent's tools for
those. No Workbench: no Notebooks, Scripts or Apps on the rail, no kernels, no Streamlit, no per-notebook
environments. For people who want to see and analyse data and let an agent write the queries.

## Two packages on PyPI
- `swissarmybench`: the full app (as today).
- `swissarmybench-lite`: its own package, its own version line (released from the same repository,
  tagged together), installed by its own installer (`install-lite.ps1`, `install-lite.sh`), its own
  uv tool, its own tray and update check (PyPI's JSON for `swissarmybench-lite`).
- How: one source tree, one build script making two wheels. Lite's wheel leaves out the Workbench's
  heavy dependencies (jupyter_client, ipykernel and what they pull in) and sets the edition; the server
  reads the edition at start and does not mount the Workbench, kernel, Streamlit and environment routes.
- **To decide:** whether Lite's wheel also leaves out the Workbench's code and page files (smaller, a
  second set of build tests) or only its dependencies (simpler; the code stays, switched off).
- Both can be installed on one computer? Probably not at once (one port, one state folder): Lite's
  installer offers "Get the full version", which installs `swissarmybench` and removes Lite; projects,
  connections and blades carry over (the same files).

## Simpler for less advanced users
- The tour on first start; plain words everywhere (already the rule).
- The ribbon's advanced tools behind a More menu; Settings shows only what matters.
- The agent's tool list shrinks to Lite's parts (about 120 of the ~270), which also makes the agent more
  reliable.

## The agent: the decision still open
How does a less advanced user get an agent?
1. **Claude Desktop (recommended):** Lite's installer registers the app's tools in Claude Desktop's
   config, so the user opens Claude Desktop and asks. No network request from our app.
2. A chat panel inside the app: friendliest, but needs the user's own API key and breaks "one request
   leaves the computer".
3. Bring your own agent: simplest for us, least helpful for this audience.

## Work, roughly
1. The edition at start (done for the name); the routes, rail, palette, menus and agent commands each
   asking it.
2. The edges where the Workbench reaches into what Lite keeps (Copy code, a table's read-only cell,
   lineage, a .sab holding notebooks: kept untouched, not shown).
3. The build: two wheels, two installers, the release workflow publishing both (and testing both
   installers on Linux, Windows and macOS).
4. Tests: the browser tests for Lite's pages run in Lite mode; the tool list checked per edition.
5. Docs: README, the user guide's Lite part, the agent index per edition.
