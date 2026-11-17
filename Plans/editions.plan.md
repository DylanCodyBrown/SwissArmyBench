# The base and its extensions (a plan)

Status: **planned** (the owner, 2026-11-17). Supersedes the earlier "three editions side by side" version of this
file. Builds on CLAUDE.md's rule that editions (now: extensions) never modify the front end, and on
Plans/powerapps-spinoff.plan.md section 8a (the manifest boundary).

## The owner's words (2026-11-17)
- "We will have another edition called BI edition that is built for notebooks and analysis. Which is the paired
  down version. And all three of the editions can be installed and the project type switches between them. BI
  editions projects will just a a BI notebook as the target deliverable"
- "And then the accounting edition includes a project type where the deliverable is an Excel workbook and the
  workflow is simply connection, data, build an python excel automation. The canvas can used to build excel files
  with pivots and charts and tools to import and build cession statements and invoices from python."
- "Powerapps edition and accounting edition are where I can get the most value perhaps we should just develop the
  editions as extensions that are optional for install. The user can start with the base the add on these
  extensions. Bi edition is the base install and powerapps, streamlit, and accounting are the extensions"

## The shape

| | Package | Adds a project type | Its deliverable |
|---|---|---|---|
| **The base: Swiss Army Bench (BI Edition)** | `swissarmybench` | BI project | a **BI notebook** |
| **Extension: Accounting** | `swissarmybench-accounting` | Accounting project | an **Excel workbook** from a Python automation |
| **Extension: Power Apps** | `swissarmybench-powerapps` | Code app project (canvas apps later) | a **Power Apps code app** |
| **Extension: Streamlit** | `swissarmybench-streamlit` | Streamlit project | a **Streamlit app** |

All built and released from this repository. The base runs alone; each extension is optional.

## How extensions work
1. **One app, plugged into:** an extension is a Python package that registers itself under the entry-point group
   `swissarmybench.extensions`; the base finds the installed ones at start (`importlib.metadata.entry_points`).
   No second server, port or state folder.
2. **What an extension brings:** its backend (domain, services, adapters, routes, under its own package); its
   part of the manifest (rail pages, commands and agent tools, project type and scaffold, connection kinds, cell
   kinds, starters and blades, Settings sections, context.md sections); and, where it needs a screen no general
   piece covers, the name of a front-end plug-in (the Streamlit canvas, the Excel canvas, the code app preview).
3. **The front end stays one:** the plug-ins' code lives with the shared front end in `web/` (built once, shipped
   in the base), shown only when an installed extension's manifest names it. CLAUDE.md's rule holds: extension
   work never changes the shared front end; a new plug-in is front-end work of its own, on the owner's word.
4. **Installing one:** `swissarmybench extensions add accounting` (and the Settings page's Extensions section:
   each one, what it adds, Add / Remove), running `uv tool install --with swissarmybench-accounting ...` into the
   base's uv tool, then a restart; an install command per extension too
   (`irm .../install-accounting.ps1 | iex`). The update check updates the base and its installed extensions
   together (one version line for all, released together).
5. **Project types:** a project folder's `.sab/project.json` records its type (`bi`, `accounting`, `powerapps`,
   `streamlit`). **New project** lists the base's type and every installed extension's. Opening a project whose
   extension is not installed opens what the base can (its notebooks, its data) and says, at the top, which
   extension it needs with its Add button.
6. **The library is one** (Plans/library.plan.md): connections, APIs, vaults, blades, functions, variables,
   colours, used by the base and every extension.
7. **The agent:** its tools are the base's plus each installed extension's; `context.md` says the project's type
   and the installed extensions.

## The base: Swiss Army Bench (BI Edition)
**For:** analysing data in notebooks and handing over a finished BI notebook.
**Has:** Grids and steps, the Analyze menu (Show the math), Visualizations, the ERD and Key Finder, compare and
tie-out, Connections and Variables, APIs and Structures, the Data Explorer, the Session page, Launch Claude and
context.md, notebooks (the data notebook and the BI notebook) with SQL, DAX and HTML cells, IntelliSense and lint,
the library, project folders.
**Its project:** `data.ipynb` (the data notebook) and `bi.ipynb` (**the BI notebook**, the deliverable), the made
modules (variables, connections, functions, data, structures), `%load_ext swissarmybench` in each notebook.
**Delivering a BI notebook:** open question 1.

## Extension: Accounting (high value: built early)
**For:** accounting work whose deliverable is an Excel workbook, built by a repeatable Python automation.
**The workflow:** connection → data (the data notebook) → **the workbook automation** (an `.xlsx` built by Python,
run again with new data).
**Adds:**
1. **The Accounting project:** scaffolded with the data notebook, `workbook.py` (the automation: plain Python,
   runs anywhere, the made modules imported), and the workbook's design file (`workbook.design.json`: sheets,
   blocks, bindings to data; no data).
2. **The Excel canvas** (a front-end plug-in, the Streamlit canvas's machinery reused): sheets as tabs, blocks
   placed on a grid of cells: a table bound to a query or grid, a title, a total row, a chart (bar, line, pie,
   combo: Excel's native charts), a **pivot** (see open question 2), formats (number, date, currency, a style per
   block), freeze panes, print setup. Play builds the workbook and shows it; Export writes `workbook.py`, the
   automation that builds the same workbook from the data. The design is data; the Python is generated from it
   and runs without the app.
3. **Cession statements and invoices:** templates (a design plus the data each needs: the contract, the cessions
   or line items, the parties, the periods), **Import** of an existing workbook as a template (its layout, its
   formats, its named ranges read with openpyxl), and **Build** one statement or invoice per party or contract
   from the data, numbered, dated, saved as files (or one workbook of sheets); a register of what was built.
4. **Excel functions** (the Excel starters, already in the starter pack, as functions in functions.py):
   write a table, styles, number formats, conditional colours, freeze panes, merge cells, add a sheet, copy a
   template.
5. **Writing back** where accounting needs it: the write blades (SQL Server, Dataverse, files) for posting results.
6. **The agent:** design a workbook (blocks on sheets), bind data, build, build statements and invoices (dry run
   first: the list of files it would make).

## Extension: Power Apps (high value)
As Plans/powerapps-spinoff.plan.md (now an extension of this app rather than an edition or a repository of its
own): pac-first; Dataverse into grids; the data notebook with SQL and TypeScript cells on Deno and DuckDB;
connectors and custom connectors in the APIs explorer; the code app project via `pac code init`; Run live;
TSX previews; push. Canvas apps later.

## Extension: Streamlit
Today's Streamlit work moved out of the base into an extension: the Streamlit project and canvas, app notebooks'
live cells, controllers, Test this page, the export and pages. **Migration:** today's `swissarmybench` installs
include Streamlit; the update that makes it an extension installs `swissarmybench-streamlit` automatically for
anyone who has a Streamlit project (or simply for every existing install: decide at the time), so nothing is lost.

## Order
1. The shared base work running or queued: the library, project folders, the data notebook (scaffold, made
   modules, `%load_ext`, functions.py), the Scripts IDE.
2. **The manifest boundary** (section 8a of the spin-off plan): one front end drawn from the backend's manifest.
3. **Extensions as data:** the entry-point group, discovery, the manifest's contributions merged, Settings'
   Extensions section and `swissarmybench extensions add/remove`, project types, the build making the extension
   wheels, the installers, the release workflow; Streamlit moved out first (it proves the mechanism on code that
   exists).
4. **The Accounting extension.**
5. **The Power Apps extension.**

## Open questions for the owner
1. What "delivering" a BI notebook means: a polished read-only report (HTML or PDF, code hidden), a notebook that
   refreshes on a schedule, the `.ipynb` itself, or several.
2. **Pivot tables in Excel workbooks:** the Python Excel libraries (openpyxl, XlsxWriter) write tables, formats,
   formulas and charts but cannot create real Excel pivot tables. Choices: (a) drive Excel itself through its
   automation interface (Windows with Excel installed: real pivots, the automation then needs Excel where it
   runs); (b) write the pivot's own file parts ourselves (works anywhere; hard and fragile); (c) summary tables
   computed with DuckDB and laid out like a pivot, with native charts (works anywhere; not interactive in Excel).
   Recommended: (c) by default, (a) when Excel is on the computer and the user asks for a real pivot.
3. The cession statement and invoice templates: start from your existing workbooks (Import), from a design made
   on the canvas, or both.
4. Streamlit's migration: install the extension for every existing install, or only where Streamlit projects
   exist.
