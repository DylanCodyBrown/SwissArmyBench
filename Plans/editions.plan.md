# The editions: BI, Streamlit, Power Apps (a plan)

Status: **planned** (the owner, 2026-11-17). Builds on CLAUDE.md's rule "editions never modify the front end"
and Plans/powerapps-spinoff.plan.md section 8a (the manifest boundary).

## The owner's words (2026-11-17)
"We will have another edition called BI edition that is built for notebooks and analysis. Which is the paired
down version. And all three of the editions can be installed and the project type switches between them. BI
editions projects will just a a BI notebook as the target deliverable"

## The three editions

| Edition | For | A project's deliverable | Package and install |
|---|---|---|---|
| **Swiss Army Bench BI Edition** (the pared-down one) | notebooks and analysis | a **BI notebook** | `swissarmybench-bi`, `install-bi.ps1` / `install-bi.sh` |
| **Swiss Army Bench Streamlit Edition** (today's app) | data work and Streamlit apps | a Streamlit app | `swissarmybench` (unchanged), `install.ps1` / `install.sh` |
| **Swiss Army Bench Power Apps Edition** | Power Apps code apps (canvas apps later) | a code app | `swissarmybench-powerapps`, `install-powerapps.ps1` / `install-powerapps.sh` |

All three are built from this repository (one front end, one shared core, a backend per edition under
`src/swissarmybench/editions/<edition>/`), released together.

## Living side by side; the project type decides
1. **All three installable at once:** each its own package, uv tool, command (`swissarmybench`,
   `swissarmybench-bi`, `swissarmybench-powerapps`; `sab` stays the Streamlit Edition's, each edition's agent
   command line its own), port, state folder, tray entry and update check. They share **one library folder**
   (Plans/library.plan.md): connections, APIs, vaults, blades, variables, connection colours, set up once.
2. **A project has a type:** `.sab/project.json` records `edition: "bi" | "streamlit" | "powerapps"` (projects
   are folders, Plans: project folders). A project without one (older) is the Streamlit Edition's.
3. **Opening a project hands it to its edition:** from any edition's Start page, its tray, or
   `<any edition's command> open <folder>`: if the project's edition is this one, it opens; else the right
   edition is started (if not running) and told to open it, and this window points there; if that edition is
   not installed, its install command is shown (copy, or Install with the user's Allow). One small shared
   helper (in the shared core) finds the installed editions (their uv tools) and their running servers (each
   edition's lifecycle file in its state folder).
4. **New project** lists the project types of the editions installed (with the deliverable said: "BI notebook",
   "Streamlit app", "Power Apps code app"); choosing another edition's type creates the project there.
5. **Recent projects** are shared across editions (one list, each with its type and edition icon), so any
   edition's Start page reaches every project.
6. **The agent:** `project_open` on another edition's project answers which edition it belongs to and hands it
   over (the same as the user); context.md says the project's edition.

## The BI Edition
**For:** people who analyse data in notebooks and hand over a finished notebook.
**Keeps (manifest):** Grids and their steps, the Analyze menu (and Show the math), Visualizations, the ERD and
the Key Finder, compare and tie-out, Connections and Variables, APIs and Structures (reading data), the Data
Explorer, the Session page, Launch Claude and context.md, the Notebooks page with the data notebook and the
BI notebook, IntelliSense and lint in notebooks, SQL and DAX cells, HTML cells.
**Leaves out:** the Streamlit canvas and app notebooks' app parts, the Scripts IDE, the write blades (reading
and analysing only: open question 2), Streamlit export, Power Apps.
**Its project:** scaffolded with `data.ipynb` (the data notebook: variables, connections, tables, structures),
`bi.ipynb` (**the BI notebook**: the deliverable, reading from data with `from data import ...`, its analysis,
charts, Visualizations cards and narrative), the made modules (variables.py, connections.py, data.py,
structures.py, functions.py), `%load_ext swissarmybench` in each notebook's first cell (so it runs in VS Code
and Jupyter too).
**Delivering the BI notebook:** open question 1.

## Order
1. The library, project folders and the data notebook (running and queued: the shared base every edition needs).
2. The manifest boundary (Plans/powerapps-spinoff.plan.md section 8a): one front end drawn from the backend's
   manifest; the Streamlit Edition as the first backend.
3. **Editions side by side:** the project type, the hand-over, the shared recent list, installed-editions
   discovery, separate packages and installers in the build and the release workflow.
4. **The BI Edition** (mostly a smaller manifest and its project scaffold with the BI notebook).
5. **The Power Apps Edition** (Plans/powerapps-spinoff.plan.md), later.

## Open questions for the owner
1. What "delivering" a BI notebook means: a polished, read-only report (HTML or PDF, code hidden, outputs and
   Visualizations cards in reading order), a notebook that refreshes on a schedule, the `.ipynb` handed over
   as it is, or several of these.
2. Does the BI Edition write data anywhere (the write blades), or is it read and analyse only?
3. Does the BI Edition keep Python scripts at all (a Scripts page), or notebooks only?
