# Swiss Army Bench Power Apps Edition (a plan)

Status: **planned, not started** (the owner, 2026-11-17).

## The owner's words (2026-11-17)
- "How difficult would it be to go ahead and add in the workbench support for typescript in scripts with
  intellisence, a react tsx cell for notebooks, a custom connector, and we could use pac to streamline
  scaffolding as a brand new project type for powerapps code apps. Along with dataverse connections and
  custom connector support as API function blades for most of the powerautomate connectors that are
  currently included with powerautomate."
- "How hard would it be to make the app module based on the powerapps code app development platform? A power
  app code app project the whole app becomes gated on that project type"
- "Would it be easier to just create a new app altogether for just code apps"
- "take this existing app create a plan to make it focused on and only work with code apps"

## What it is
A desktop bench for building **Power Apps code apps**: React and TypeScript web apps that run inside Power
Apps, reach Dataverse and Power Platform connectors through the Power Apps SDK, and are scaffolded and
published with the Power Platform command line (`pac code ...`). Everything a code app developer does in
one place, with an agent that can do all of it too:

1. Sign in to an environment, start a code app (scaffold), open an existing one.
2. Browse the environment's **data**: Dataverse tables (columns, relationships, rows to look at) and
   **connectors** (their operations, inputs and outputs); add them to the app as data sources.
3. Write the app: TypeScript and React (TSX) with full IntelliSense, components previewed live, the
   generated data services browsable, the app running live beside the code.
4. Check it (type errors, lint, tests), then **push** it to the environment and see its versions.
5. Bring your own APIs: an OpenAPI document becomes a **custom connector** the app can use.

It does nothing else: no DuckDB grids, no Python notebooks, no Streamlit, no analysis menu.

## How: an edition of this repository (recommended), not a separate one
**Recommended: a third edition in this repository**, beside the full app and the Lite edition
(Plans/lite-edition.plan.md): one source tree, a build making a separate wheel,
`swissarmybench-codeapps` on PyPI with its own installer, version line, tray, update check, and the name
"Swiss Army Bench for Code Apps" in the status bar. The edition is fixed at install: the server mounts
only its routes, the rail shows only its pages, the agent gets only its tools. Nothing switches inside a
running app.
- **Why not a new repository:** the parts it keeps (below) are most of the app's hardest work (the server
  and its security, the Workbench editor, the library, APIs, Structures, the agent's door, Launch Claude,
  context.md, the updater, the installers). A copy would need every future fix twice.
- **Why not one app gated by project type:** every page would have to know which project type is open;
  an edition decides once, at start, and the data app stays exactly as it is.
- **The shared library folder** (Plans/library.plan.md): both editions read the same library (Dataverse
  connections, APIs, custom connectors, variables, blades), so an API set up for data work is already
  there for a code app, and the library goes to Git the same way.
- **To decide:** whether the code apps edition's wheel leaves out the data features' code (smaller; a
  second set of build tests) or only their dependencies (DuckDB, pandas, ipykernel, Streamlit: simpler).
  The Lite plan has the same question: decide it once for both.

## What it keeps, changes, drops, adds

### Keeps (as they are)
The server and its posture (127.0.0.1, the token, the cookie, Origin checks); the rail and navigation; the
Workbench window (tab groups, pop-outs, the palette, the console, the status bar, zoom); the library
(Plans/library.plan.md) and the Variables page; Structures (JSON: connector payloads, `power.config.json`,
generated schemas); the Session page and Follow the agent; Launch Claude and context.md; the agent's door
(the golden rule: every user action is a command); the updater, tray, installers, beta log.

### Changes
- **Connections:** only what a code app can use: **Dataverse** (the existing connection: its tables,
  columns, relationships) and the environment's **connections** to connectors (listed from the
  environment: each connector, its connection, its status). The ERD shows Dataverse tables' relationships.
- **APIs:** the explorer becomes the **Connectors** page: every connector the environment offers (the
  standard and premium ones Power Automate includes, and custom ones), each with its operations, inputs,
  outputs and descriptions, searchable (the explorer already built); **Add to app** runs
  `pac code add-data-source` for it. The owner's OpenAPI documents become custom connectors (below).
- **Blades:** **TSX blades** (React snippets: a form bound to a Dataverse table, a gallery, a data grid,
  a chart, a dialog) and **functions** (TypeScript utilities written into the app's `src/functions/`,
  the call inserted where you work: the same split as the data app's blades and functions).
- **The Workbench's languages:** TypeScript and TSX instead of Python, SQL and DAX (below).

### Drops (not in this edition)
Grids and their steps, the Analyze menu, regression and time series, Visualizations, compare and
tie-out, the Key Finder, DuckDB SQL across connections, Python notebooks and kernels, per-notebook
environments, the Streamlit canvas, HTML/SQL/DAX cells, Power BI, Trino, SQL Server and the other
database connections, the lakes, the data notebook and its exports.

### Adds
1. **Environments and sign-in:** `pac auth` profiles listed, one chosen per project (the environment's
   name and id shown everywhere), sign in through `pac auth create` (the browser), never a password kept
   by the app. Checks that code apps are enabled in the environment (an administrator's setting) and says
   so plainly when not.
2. **The Code App project:** New code app: a folder, `pac code init` with the app's name, the Vite +
   React + TypeScript starting point (Microsoft's current template, followed rather than invented), Node.js
   packages installed (`npm install`), the project opened. Open an existing code app folder. Tools needed
   (Node.js, npm, pac with .NET) found and offered through the missing-package prompt, with each system's
   install command.
3. **Data sources:** the project's sources (from its config file) listed; **Add a Dataverse table** and
   **Add a connector** (choose the connection) run `pac code add-data-source`; the generated models and
   services shown and browsable (the Data Explorer, re-pointed: tables, columns, connector operations,
   their TypeScript types); Remove a source.
4. **The editor:** TypeScript and TSX in Monaco with its built-in TypeScript language service (member
   lists, parameter info, hover, go to definition, rename, errors as you type), the project's own types
   and the generated services' types loaded into it; ESLint and Prettier when the project has them;
   `tsc --noEmit` problems in the Problems panel. A file tree by folder (the Scripts IDE's tree,
   b/scriptside.md, reused).
5. **Run live:** the app's dev server (`npm run dev` and the local runner the code apps tooling provides)
   started and shown in a pane of the Workbench through this server's proxy (as Streamlit is today),
   reloading on save; its console output in the console.
6. **Component previews:** a **TSX cell** in a component notebook (`*.components.ipynb`-like, or a
   `.tsx` file's own preview) renders one component in the walled-off frame with sample props (made-up
   data, or a Dataverse table's first rows read for the preview only), so a component can be built without
   running the whole app.
7. **Push and versions:** `pac code push` with its output, the app's link in the environment, the
   versions pushed (as the tooling reports them).
8. **Custom connectors from the APIs work:** an OpenAPI document (file, address, or an API already in the
   library) made into a custom connector's files (`apiDefinition.swagger.json`, `apiProperties.json`, the
   auth settings mapped from the API's sign-in), created in the environment with `pac connector create`,
   then added to the app like any connector. Updates with `pac connector update`.
9. **The agent:** every action as a command (golden rule); context.md for this edition (the environment,
   the app's sources and their generated services, the components, the routes, the build's problems);
   Launch Claude starts in the code app's folder.

## About "most of the Power Automate connectors"
Inside a code app, connectors are used the supported way: `pac code add-data-source` generates typed
services for any connector the environment has, so the Connectors page covers all of them without our
own client code. What this edition does not do is call those connectors from outside Power Platform
(Python blades calling the connector gateway directly): that is not a supported use, and it would be
fragile. Where an API is needed outside an app, the data edition's own APIs (Microsoft Graph for Outlook,
Teams, OneDrive, Planner, SharePoint) stay the way.

## Work, roughly (branches of the size this project has been built in)
1. **Editions as data:** the edition at start decides routes, rail, palette, menus, agent tools, the
   status bar's name (shared with Lite: build it once). The build makes the wheels; the installers per
   edition; the release workflow tests and publishes each. *(1 branch)*
2. **Environments, the Code App project and its tools:** pac and Node.js found and installed, sign-in,
   New and Open code app, the scaffold, `npm install`. *(1 branch)*
3. **Data sources and the Connectors page:** Dataverse tables and connectors listed from the environment,
   Add/Remove through pac, the generated services in the Data Explorer, the ERD for Dataverse. *(1-2
   branches)*
4. **TypeScript and TSX in the Workbench:** Monaco's language service with the project's types, the file
   tree, Problems from tsc and ESLint, Run live in a pane, TSX component previews. *(1-2 branches)*
5. **Push, versions, custom connectors.** *(1 branch)*
6. **TSX blades and TypeScript functions** (a starter pack of components bound to Dataverse), the agent's
   context.md for the edition, the user guide. *(1 branch)*
About 6 to 8 branches after the library and project folders land (they are the base this stands on).

## Not checkable here
A real Power Platform environment, pac signed in to a tenant, `pac code init/add-data-source/push`
against it, the code apps runtime and its local runner, custom connector creation. These are checked on
the owner's machine; the tests stand in for pac with a recorded fake (its commands and outputs) and for
the environment with made-up tables and connectors. The code apps tooling is new and changing: each
branch checks Microsoft's current documentation for `pac code` and the SDK before building, and records
what it relied on in docs/verified.md.

## Open questions
1. The edition's name: "Swiss Army Bench for Code Apps" (used here) or another.
2. Leave the data features' code out of the code apps wheel, or only their dependencies (shared with Lite).
3. Whether a code app project can also hold Python helpers (scripts that seed Dataverse, for example), or
   stays TypeScript only.

## Revised: pac-first, TypeScript data, the same GUI (the owner, 2026-11-17)
"pac actually simplifies a ton of this and instead of writing custom code to manage the project we let pac cli
do the work. We can write commands to get data with it from connected workspaces, we can use Dataverse to get
the grids and transform the data with typescript. And that becomes our data typescript. The custom connector
API we get for free, and we actually get a browsable power automate connector list for free with pac to import
it and its shape in the API explorer. Then we just get a data notebook with SQL and typescript cells for
testing on the back of duck db (if it's in typescript) right? This seems like a new version of the app and all
we do is reuse the gui and front end"

This supersedes the sections above where they differ.
1. **pac is the backend for everything Power Platform.** The app writes no project-management code of its
   own: every project action is a pac command run as a child process, its output shown and parsed (`pac auth`,
   `pac code init`, `pac code add-data-source`, `pac code push`, `pac connector create/update`, and whatever
   current pac offers for listing connectors and connections). Each command is also an agent command (the
   golden rule), and the Session page shows it. Before building, check Microsoft's current pac reference for
   which listing commands exist; where pac has none (the full connector catalogue, a connector's OpenAPI
   shape), read the same environment API pac reads, with the same sign-in, and say so in docs/verified.md.
2. **Data:** Dataverse through the existing connection (TDS for SQL speed, the Web API where TDS cannot) into
   **grids**; connectors' data through the generated services, which run only inside the code apps host (its
   local runner): the riskiest piece, proved first with a spike (one connector, one call, from a notebook
   cell in the host's context) before the rest is built on it.
3. **TypeScript is the data language:** transformations in TypeScript; the data notebook (`data.ipynb`) has
   **SQL cells** (DuckDB) and **TypeScript cells**, run by **Deno's Jupyter kernel** (TypeScript natively, npm
   packages, no compile step) with DuckDB's official Node package (`@duckdb/node-api`) so both cell kinds share
   one DuckDB database; its export is `data.ts` (as data.py is today), and the app's pages import from it. The
   variables/connections/functions/structures modules become `.ts` the same way.
4. **Connectors in the APIs explorer:** the environment's connector list browsable and searchable there, each
   connector's shape (operations, inputs, outputs) imported into the explorer; **Add to app** is `pac code
   add-data-source`. Custom connectors from OpenAPI documents: `pac connector create`.
5. **A new version that reuses the GUI:** the front end (rail, pages, Workbench, Structures, the APIs explorer,
   the Data Explorer, Session, Variables, Settings, zoom) is reused as it is. The Python server stays as the
   shell (security, the live-preview proxy, the agent's tools, context.md, the updater and installers) and
   calls pac, Node and Deno instead of DuckDB in Python and the IPython kernel. Rewriting the server in
   TypeScript is not planned: it costs much and changes nothing the user sees.
6. **Work, revised:** (1) editions as data, shared with Lite; (2) the pac layer (find and install pac, Node,
   Deno; run, parse and show commands; auth and environments); (3) **the connector spike** (point 2); (4) the
   Code App project via pac and the live app in a pane; (5) the data notebook on Deno with SQL and TypeScript
   cells on DuckDB, Dataverse into grids, `data.ts` and the `.ts` modules; (6) connectors and custom
   connectors in the APIs explorer; (7) TSX previews, TSX blades and TypeScript functions, push and versions.
   About 6 branches after the library and project folders.

## Decided: the name, the codebase, and canvas apps later (the owner, 2026-11-17)
"I think we go ahead and plan on that just being a different version out of this code base entirely and we
call it Swiss army bench power apps edition. And we can plan to later build canvas apps with it as an
expansion"
1. **Name: Swiss Army Bench Power Apps Edition** (wherever this plan says "Swiss Army Bench for Code Apps" or
   "the code apps edition", read this). The status bar says it; its PyPI package is
   `swissarmybench-powerapps` (replacing `swissarmybench-codeapps` above); its installers
   `install-powerapps.ps1` and `install-powerapps.sh`.
2. **Built out of this codebase:** a different version of the app from this one repository, as planned
   above (an edition fixed at install), reusing the GUI and the shell; open question 1 is answered.
3. **Later expansion: canvas apps.** After code apps, the same edition grows to Power Apps canvas apps,
   again through pac rather than our own code: an app's `.msapp` unpacked to its source (Power Fx and
   YAML, with `pac canvas unpack`, or whatever source format current pac and Power Apps use: check first),
   edited in the Workbench (Power Fx with IntelliSense for the app's controls and data sources), packed and
   imported back (`pac canvas pack`, a solution import). Data sources, connectors, Dataverse and custom
   connectors are the ones the code apps work already brings. Not started; a plan of its own when code apps
   are done.
