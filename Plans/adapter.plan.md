# One adapter: the simple architecture (the owner, 2026-11-21)

Status: agreed; phase 1 built (branch `adapter`, 2026-11-21): Order 1 and the start of 2; phase 2 built (branch
`adapter-2`, 2026-11-22): the reading half of Order 2, the start of 3 and 4, `truncate`; phase 3 built (branch
`adapter-3`, 2026-11-22): `query`, the mock clients gone, the writes of Dataverse, SharePoint lists and the lakes,
the Catalog's listing, file connections, the engine's first paths (the owner's answers after phase 2).

### What is built (phase 3)

- `query(source, sql, params)`: SQL a plan cannot say (joins, CTEs, a write with RETURNING) in the source's own SQL
  and its driver's marks, answered as Arrow; a statement that returns no rows answers one `count` column. DuckDB,
  Sql, Remote and Files take it; the sandbox's door makes it DuckDB SQL over its tables (sandbox_dialects.py, kept
  as that backend's half: its refusals in one sentence with the line).
- `Connection(source)`: what API.py's `connection(name)` hands out, here and in an export: `tables()`,
  `columns(table)`, `read(table, columns=, filters=, sort=, limit=, offset=)`, `query(sql, params)`,
  `write(table, rows, key, mode)`. The mock clients (server/sandbox_clients.py) and the JSON op door
  (`/sandbox/data`) are gone; the old client calls are refused in one line. `source_from(client)` wraps a
  connection's own client (or a file connection's path) in its backend: an export's connections.py does.
- forms_recon's API.py and New endpoint from a table are on it (the scaffold: one style for every source).
- Writes: `OData.write` (Dataverse's $batch change sets, choice labels, keys, 429; insert, update, merge, delete,
  truncate), `Rows.write` (a lake's Delta table and a lake file; a SharePoint list by its own Graph calls).
  `planned()`: a write's dry run counted by reads. The Dataverse, SharePoint list, Delta and lake file Write
  starters call them (client/writes.py `by_adapter`); client/write_dataverse.py moved in and went.
- The Catalog lists a connection's tables through `tables()` (a table's schema, kind and database, a column's
  nullability carried; `catalog_rows`) for DuckDB, PostgreSQL and SQLite, unless its List the tables is the user's
  own (its text differs from its starter's, whitespace aside).
- `Files(path)`: a file connection's CSV, Parquet and JSON files as a source (read, query, whole-file write).
- The engine: every export's rows, a query made a table ("+" tab, SQL box) and a kernel's DuckDB SQL naming an
  open table read through `query` over the app's own DuckDB session (`DuckDB.session`).
- Not yet: the grid's windows, the steps' compile, the analyses and the profile (the view cache as a source of
  its own); the other 12 Write starters (SQL databases, files, Excel); the Catalog through the adapter for
  MySQL, Oracle, Snowflake, SQL Server, Trino, Databricks; a file connection's Open as grid (the app's loader);
  contract.json, the eight-file export, folder extensions, the Environment page, the Excel module, sab.write,
  the endpoint wizard (docs/ideas.md "One adapter": what each needs).

### What is built (phase 2)

- `truncate` for every source the adapter writes (DuckDB, the sandbox's door, SQL databases): no rows clears the
  table and keeps its columns; rows clear and insert in one transaction, all or none.
- The words: `table(name)`, `Tables`, `TableSource`, `make_table` (was grid(name), Grids...: a grid is a view).
- Each connection kind as a backend, read side: `Sql` (any DB-API connection; `DIALECTS` as data: PostgreSQL,
  MySQL/MariaDB, SQL Server/Azure SQL, Oracle, SQLite, Snowflake, Trino, Databricks; the whole plan folded into
  its own SQL, streamed from the cursor; writes in its own INSERT/UPDATE/DELETE in one transaction), `OData`
  (Dataverse's Web API: filters, columns, sort, limit into one OData read), `Rows` (the lakes and SharePoint, by
  their own read). Open as grid on all of them goes through the adapter.
- The open tables as a source (`/workbench/tables/adapter/tables|read`), a kernel's `sab.table(name, plan)`, and a
  kernel's DuckDB SQL naming an open table reading through it.
- API payloads: an Arrow answer as JSON records (`to_json`) or Arrow IPC for a caller that accepts it; a body
  `Annotated[pa.Table, Model]` checked, then made Arrow by `from_json`.
- The API export carries `sab_adapter.py` (duckdb and pyarrow in requirements.txt).
- Not yet (phase 3): the mock clients and sandbox_dialects.py (an endpoint's SQL in its source's dialect needs a
  decision: docs/ideas.md "One adapter"), the writes of Dataverse, SharePoint and the lakes through the adapter
  (each kind's Write starter still writes), the app's Catalog listing through `tables()`, the steps, SQL box,
  views, analyses and exports onto the open tables source, the canvas and script exports' files, file connections
  (CSV, Parquet, JSON) as a source.

### What is built (phase 1)

- `src/swissarmybench/adapters/sab_adapter.py`: the contract (tables, read with a plan and what was folded, write by
  mode, grid, refresh), the plan (columns, filters, sort, limit, offset, group, totals; the unfolded rest done by
  DuckDB over the stream), JSON pages to Arrow by DuckDB with given types, grids. Standard library, duckdb and
  pyarrow only: an export copies it as it is. Sources: `DuckDB` (a file, a connection given, a gated connection)
  and `Remote` (the sandbox through the app's data door, Arrow IPC both ways).
- Through it: the sandbox's Open in Grids and [Sandbox].table; a DuckDB file connection's Open as grid; a local
  sandbox API's sandbox (its one backend; API.py may `from sab_adapter import read, Plan`); every SQL mock's
  tables() and columns(); the SharePoint mock's reads and writes.
- Tests: tests/test_sab_adapter.py (memory stays flat: a streamed read grows the process far less than the rows
  held), test_adapter_grids.py, test_adapter_sandbox.py, test_adapter_boundary.py (every place outside the adapter
  that opens a driver or turns JSON into rows, listed; enforced for what moved). Larkfield's 10M order lines:
  docs/verified.md. Decisions and what each later step needs: docs/ideas.md "One adapter".
- Not yet: contract.json, folder extensions, the endpoint wizard, the other connection kinds as backends, the
  export's file list (sab_adapter.py beside sab_api.py), a kernel's grid, the answer path (Arrow to JSON), an Excel
  workbook as a source (Plans/excel.plan.md: it needs a `replace` write mode).

## The owner's words

> API -> sab_adapter.py (duckdb adapter) -> SAB_Tables
> Connections -> sab_adapter.py -> Grids
> Grids -> Notebooks
> Grids -> Widgets -> Canvas
> Blades -> Widgets
> Variables -> Widgets -> Canvas
> Structures -> Widgets -> Canvas
>
> "Why isnt it this simple"

> "I think we need to use my model and try to simplify this down to this architecture as close as possible. The
> beauty will be in the Adapter that Adapts read and writes in and out without holding onto the data when doing it to
> avoid parity, what is read from a connection is thrown away and the adapter makes sure only arrow tables for our
> grids remains" / "im writing this from an exported project standpoint" / "what I export should be the least amount
> files and code possible to build the app with"

## The model

```
Connections ─┐                     ┌─> Grids (Arrow tables, the only data kept) ─┬─> Notebooks
Sandbox ─────┼─> sab_adapter.py ───┤                                             └─> Widgets ─> Canvas
Structures ──┘   (read and write,  └─> API.py (endpoints)                 Blades, Variables ─┘
                  holds nothing)
```

- **The adapter holds nothing.** A read streams Arrow batches from the source (everything the source can do folded
  into its query: columns, filters, sort, limit, totals); what is read is thrown away once a grid is made from it. A
  write streams Arrow batches into the source's own insert or merge. No second copy, so nothing to keep in step.
- **A grid is the only data that stays:** a named Arrow table, made from one source and one DuckDB SQL (its steps).
  Notebooks, widgets and endpoints read grids by name; they never hold their own copy of a source.
- **Same code here and exported.** In the app, the backends are the open connections, the sandbox and structures;
  in an exported project, the same `sab_adapter.py` with the real connections behind it. A local sandbox API's
  backend is the sandbox only (never live data: unchanged).

## The one rule

The owner: "every single data call and every api payload in and out should travel through the adapter. This will
make everything else simple." So no code reads or writes data any other way: a grid's load, a notebook's SQL cell, a
widget's table, a blade that returns rows, a connection's Test and Preview, the Catalog's listing, an export's data,
an Add API web call, a local sandbox API's request body and its answer, a write back to a source. A request body
comes in through the adapter (JSON to Arrow, checked against its model); an answer goes out through it (Arrow to
JSON or Arrow). A test enforces it, like the layers test: outside sab_adapter.py and the sources it calls, nothing
imports a database driver, opens a source's HTTP client, or turns JSON into rows.

## The adapter's contract (sab_adapter.py)

Three calls, the same for every source:

| Call | Takes | Gives |
|---|---|---|
| `tables(source)` | a connection, the sandbox or a structure | names, columns and types |
| `read(source, table, plan)` | a plan: columns, filters, sort, limit, group and totals | a stream of Arrow batches, and what was folded |
| `write(source, table, batches, key, mode)` | Arrow batches; insert, update, merge or delete | counts |

and the grids:

| Call | Does |
|---|---|
| `grid(name)` | the named Arrow table (made on first use, then kept) |
| `refresh(name)` | read its source again through `read`, run its SQL, replace the table |

JSON pages (Dataverse, SharePoint, web calls, request bodies) become Arrow through DuckDB page by page, with the
catalog's types (what convert.py was to be: it folds into the adapter). A source plugs in by its three functions;
a new extension adds sources, never another reader.

## Shared core, and each project type's own architecture

The owner: "Each project type gets its own architecture but the adapter file, the connections, the APIs that all
stays the same structure for the most part." So every project, whatever its type, has the same core files with the
same structure; a project type (Streamlit, Power BI, Accounting, Power Apps, Databricks next) adds only its own
files on top, and never reshapes the core:

| Always the same structure (every type) | Each type's own |
|---|---|
| `sab_adapter.py`, `connections.py`, `API.py`, `data.py` (the grids) | its app or deliverable: Streamlit's `app.py` and `widgets.py`; Power BI's `.pbip`; Accounting's `workbook.py`; a code app's `src/`; Databricks' to be designed |

## The exported project: the fewest files that build the app

A file is exported only when the app uses it, and only the parts it uses (only the connections, grids, widgets and
endpoints the app touches; no unused helper):

For a Streamlit project:

| File | What it is | Made or yours |
|---|---|---|
| `sab_adapter.py` | the adapter: the contract, the Arrow conversion, the grids | made (the same in every project) |
| `connections.py` | the connections the app uses: each one's own list, read and write | made from the library |
| `data.py` | the grids: each one's source and its one DuckDB SQL | made from data.ipynb |
| `API.py` | the endpoints, if the app has any | yours |
| `app.py` | the pages, the layout and the wiring | made from the canvas |
| `widgets.py` | the widgets the pages use | made from the library |
| `requirements.txt` | duckdb, pyarrow, streamlit and what the connections import | made |
| `README.md` | how to run it and the variables to set | made |

Eight files at most. Today an exported canvas is `app.py`, `app_pages/<page>.py` per page, `sab_widgets.py`,
`sab_canvas.py`, `data.py` and the connections' code, and an exported API is a target folder with `sab_api.py` and
its own `connections.py`: those fold into the table above (the API target's framework file, such as
`function_app.py`, is the one addition when an API is exported for a platform).

### Who writes what

The owner: "The goal is the app will write these files as the user develops, the agents can create additional files
and structures and things as needed, but the app itself sticks to one uniform structure per project." So the app
writes only its own files, always with the same names in the same places for a project type, as the user works
(never all at once at New project); the user and the agent may add any other files and folders beside them, and the
app leaves those alone (it never moves, renames or regenerates them).

The files grow as the user works (the owner: "the files grow as the user creates new connections/apis, structures
and variables"), each new thing one new, clearly marked section in its one file, in the order it was made:

| The user makes | The app adds |
|---|---|
| a connection | its section in `connections.py` (its list, read and write; its variables by name only) |
| an endpoint | its function in `API.py` (yours to change after) |
| a grid | its source and its DuckDB SQL in `data.py` |
| a structure | its file in `structures/` and its line in `data.py` (a structure read as a grid) |
| a variable | its name, where it comes from and what uses it in `README.md`'s Variables list (never its value) |

Removing a thing removes its section. Nothing is written for a connection, endpoint or variable the project never
uses.

### The sandbox lives in its own files, never in the app's

The owner: "since its probably hell to find sandbox objects and clean them up later, why not create separate sandbox
files sandbox_data.py etc." / "dont mix them into the app scaffold". So everything that exists only for testing here
is in files whose names start with `sandbox`, beside the app's files and never inside them:

The owner: "They are a mirror image of the app that runs with the adapter but never share the app's guts." Each
app file the adapter reads has its sandbox mirror with the same shape; the adapter loads one side or the other, and
the two never import each other:

| The app's file | Its sandbox mirror | The mirror holds |
|---|---|---|
| `connections.py` | `sandbox_connections.py` | each connection's stand-in: the same names, backed by sandbox tables (never the real code, variables or secrets) |
| `data.py` | `sandbox_data.py` | the sandbox's tables: where each was read from once, its key, the baseline and checkpoints by name |
| (none: rows are not kept) | `sandbox/` | the rows: `sandbox.duckdb`, `baseline.duckdb`, checkpoints (Git-ignored; moved out of `.sab/sandbox/`) |

`API.py`, `app.py` and the widgets are not mirrored: the same code runs on both sides, because it only ever calls
the adapter.

- The app's own files (`sab_adapter.py`, `connections.py`, `API.py`, `data.py`, the deliverable) never name the
  sandbox. Which backend the adapter uses is decided where it runs: a local sandbox API run here gets the sandbox,
  always; an exported project gets its connections. Endpoint code is the same in both.
- **Find and clean up in one place:** Remove the sandbox deletes `sandbox_data.py` and `sandbox/`, and nothing else
  changes. An export never includes a `sandbox` file.
- Other sandbox-only things the user or the agent makes (made-up seed rows, test endpoints, test widgets) go in
  `sandbox_*.py` files too, so they are found and removed the same way.

### The project contract is the extension's, as JSON

The owner: "The contract for a project should be laid out by the extensions as they are added so the app kernel
doesn't require a change" / "A project's contract is laid out in json. Everything including the ide language. The
back end always remains python based with the duckdb adapter being the entry for data and apis in and out."

- The owner: "So extensions have a project.json in root." Each extension that adds a project type has one
  `contract.json` at its root (the base ships the BI one); one with no project type (Copilot, Git) has none. Named
  `contract.json` (the owner: "Contract.json is fine") so it is never mixed up with a project's own
  `.sab/project.json` (its state): the contract says what a type of project is, the state what one project holds. The contract: its
  files and folders, what the editors offer (languages, cell kinds, the IDE's language per file pattern), its canvas,
  what grows each file, its export, its words. The base reads only this file to scaffold, grow, list, check, open
  and export a project; it never names an extension's file, and the front end draws what the JSON says.
- **What may vary:** anything in the JSON: the files, the IDE's languages (a code app's TypeScript and TSX, a
  Databricks project's PySpark and Databricks SQL), the canvas, the deliverable.
- **What never varies:** the back end is Python; data and API payloads go in and out only through the DuckDB
  adapter (`sab_adapter.py`); the core files are the base's. A JSON contract can add, never replace, them.
- Today's `MODE` value in each extension.py moves into this file (one source, not two). A test checks each
  installed contract against the shared JSON schema, and that no base file names an extension's file.

A sketch (the Power BI type):

```json
{
  "format": 1,
  "type": "powerbi",
  "name": "Power BI",
  "deliverable": "a Power BI report",
  "core": "base",
  "languages": {"*.py": "python", "*.ipynb": "python", "*.tmdl": "tmdl", "*.dax": "dax", "*.m": "powerquery"},
  "cells": ["python", "sql", "dax"],
  "files": [
    {"path": "data.ipynb", "owner": "user", "made_from": null, "grows_on": ["table"]},
    {"path": "model.py", "owner": "app", "made_from": "the model", "grows_on": ["relationship", "measure"],
     "section": "# --- {kind}: {name} ---"},
    {"path": "powerbi/", "owner": "app", "made_from": "model.py and connections.py", "grows_on": ["export"]}
  ],
  "canvas": null,
  "export": {"target": "powerbi", "files": ["powerbi/"]},
  "areas": ["projects", "powerbi", "connections", "variables", "data", "grids", "erd", "notebooks", "session",
            "settings"],
  "words": {"for_whom": "For anyone who works on a Power BI report and wants its data checked at the source."}
}
```

### A Power BI project (mock-up)

```
sales-report/
  sab_adapter.py          made   the same adapter as every project
  connections.py          made   the report's sources (the warehouse, Dataverse ...) and the Power BI dataset
  data.py                 made   the grids: each table from its source + its DuckDB SQL, and the same table
                                 as Power BI has it (read with DAX through the dataset's connection)
  data.ipynb              yours  where the work happens: one SQL cell and one DAX cell per table
  model.py                made   the model as code: tables, relationships (one active path) and measures (DAX)
  powerbi/                made   the deliverable, a Power BI Project that Power BI Desktop opens
    Sales Report.pbip
    Sales Report.SemanticModel/definition/
      model.tmdl
      relationships.tmdl
      tables/<table>.tmdl    each table's columns, measures and its Power Query (M) from connections.py
    Sales Report.Report/      the report's pages (yours, or another report's brought over)
  API.py                  yours  only when the report needs one (rare)
  requirements.txt        made
  README.md               made   how to refresh it and the variables to set
  .sab/                   the app's state (project.json, powerbi.json)
```

The difference from a Streamlit project is only the deliverable: `model.py` and `powerbi/` instead of `app.py` and
`widgets.py`. One honest limit: Power BI refreshes the report by running its own Power Query, so the report's refresh
does not travel through the adapter; everything this app does with the data (the grids, the tie-out, the checks)
does.

## What it replaces

- the mock clients per source (`server/sandbox_clients.py`) and their dialects (`domain/sandbox_dialects.py`): an
  endpoint calls the adapter, and the sandbox is one more backend;
- the per-path table reads: `connection_tables` reads, a widget's `[Conn].table` read (`read_named`), the sandbox's
  tables as inputs, the open tables' Parquet copies, data.ipynb's tables: all become `grid(name)` or `read`;
- the separate runtimes an export carries (`sab_canvas.py`, `sab_api.py`, `script_runtime`'s helper text) as far as
  they read or write data;
- convert.py (never built: folded in);
- the Write starters' statements stay as each source's `write` (one per source, not one per source and mode).

## Order

1. The contract and the adapter, with the sandbox and DuckDB files as its first backends; grids as named Arrow
   tables. Tests: memory stays flat reading Larkfield's 10 million order lines; nothing kept after a read but grids.
2. Each connection kind as a backend (its list, read with folding, write), one at a time; the mock clients go.
3. Widgets, notebooks and API.py read through `grid` and `read`; the per-path reads go.
4. The export: the eight files; a test that an exported app and API run with only them.
5. The endpoint wizard and its patterns on top (Plans: b/local-apis.md).

## The owner's answers (2026-11-21)

- **When a grid refreshes in a deployed app:** when a page asks. Read on first use, kept, read again only when a page
  or the user asks (a Refresh, or a widget's event).
- **A snapshot of a grid in an export:** only on a tick. Off by default; "Keep a snapshot" per grid writes it as
  Parquet beside the export (Git-ignored, like `.sab/data/`); without the tick no row is ever written.
- **When to build:** now, in parallel with other work; 0.0.32 is not released yet.

## Tables and grids: the words (the owner, 2026-11-22)

"Grids are just links to the existing tables. Grids is just the visualization layer, not duplicate data. Tables can
be created in app." So, everywhere in this plan and the code:
- **A table** is the data: a named Arrow table in the project's environment, made by a read through the adapter, by
  code in the session, or in the app (paste, a query, Save as table from a grid's steps, Add table). It is the one
  copy; the read it came from is thrown away.
- **A grid** is a view of a table: the page that shows it, with its steps applied as a view (DuckDB SQL over the
  table), never a copy. Closing a grid leaves the table; several grids may show one table.
- Read "grid(name)" and "grids, the only data kept" above as **table(name)** and **tables, the only data kept**; the
  adapter's call is `table(name)` (refresh(name) re-reads a table from its source).

## The owner's answers after phase 1 (2026-11-21)
- **A fifth write mode, `truncate`** (the owner: "Truncate is better terminology. Truncate and insert" / "Sometimes
  you just wanna clear a table. So truncate is a much more flexible command"): with no rows it clears the table (or
  an Excel sheet), keeping its columns; with rows it clears it and inserts them, in one go, all or none. Everything
  else is kept. For every source.
- **The rule covers everything, the engine too** (asked: does "every data call goes through the adapter" cover the
  app's own DuckDB engine working on grids already loaded, the steps, the SQL box, views, analyses? The owner: "Yes,
  everything"). So the open grids are a source of the adapter like any other (tables: the open grids; read: a plan
  over a grid's view, steps applied; write: an edit), and the steps, the SQL box, views, the analyses, exports and
  kernels reach rows only through it. The boundary test (tests/test_adapter_boundary.py) grows to enforce it for every
  path as each one moves; its list from phase 1 is the work list.

## The owner's answers after phase 2 (2026-11-22)
- **SQL a plan cannot say: `query(source, sql)`** in the source's own SQL (joins, CTEs); in the sandbox it is
  translated to DuckDB (today's sandbox_dialects, kept as that backend's), so an endpoint deploys unchanged against
  the real source. Then the per-source mock clients go: endpoints call the adapter (table, read, query, write).
- **Writes next:** Dataverse ($batch), SharePoint lists (Graph) and the lakes (Delta) as the adapter's write for each,
  truncate included (the Write starters' code moves in); then sab.write covers every source.
- **The Catalog lists through the adapter's tables()**, except a connection whose "List the tables" query the user
  edited keeps using theirs.
