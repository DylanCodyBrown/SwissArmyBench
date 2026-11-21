# One adapter: the simple architecture (the owner, 2026-11-21)

Status: agreed in principle; build after the running `api-approved` branch merges. Nothing here is built yet.

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

## Open questions for the owner

- In a deployed app, when does a grid refresh: at start, on a timer, or when a page asks?
- Should a grid ever be written to disk in an export (a Parquet snapshot for a quick start), or always read fresh?
