# The sandbox and local sandbox APIs

The project's sandbox is its own DuckDB file (`.sab/sandbox/`, Git-ignored): the only data a local sandbox API
reads and writes. A real connection is never reached from one ("No never run against live data ever").

## The sandbox: `sandbox(action, args)`
- `list`: its tables (rows, columns, where each came from, `client`: the connection its rows are mocked as), the
  baseline, the checkpoints, the change log (inserted, updated, deleted per table since the baseline).
- `add`: `{"from": "grid", "table": "orders"}` (an open table's view, after its steps), `{"from": "connection",
  "connection": "Warehouse", "table": "orders", "schema": "dbo"}` (read once, its row limit applying),
  `{"from": "file", "path": ...}`, `{"from": "columns", "name": "notes", "columns": [{"name": "id", "type":
  "integer", "key": true}]}`; `"name"` names it, `"replace": true` replaces one, `"key": "id"` (or a list) its
  primary key (a connection's table takes its key from the shared catalog by itself).
- `key` `{"table": "stock", "key": "sku"}`: a table's primary key, as the real database has it: a write that
  repeats or blanks it is refused in one sentence ("Duplicate key: a row with sku: A-1 is there already").
  Reset and Restore keep it. New endpoint (a pattern that writes by a key) sets its key when the table has none.
- `remove` `{"table"}`, `open` `{"table"}` (in Grids as `sandbox_<table>`, following every write).
- `reset`: every table back to the baseline (waits for the user's Allow). `baseline`: the sandbox now is the
  baseline. `checkpoint` `{"name", "action": "save"|"delete"}`, `restore` `{"name"}`.
- DuckDB SQL names a sandbox table `[Sandbox].orders` (`steps_run_sql`); the Catalog has a Sandbox section,
  and `explorer_browse` / `explorer_search` take its Sort: `sort` (name, rows, source, created, changed), `order`.
- `reset` with `{"table": "orders"}` puts that one table back alone.
- `list` `{"sort": "name"|"rows"|"source"|"created"|"changed", "order": "asc"|"desc"}`: every list of sandbox
  tables sorts the same way. Each table says `type: "sandbox"`, `title` (its designation), `variant` and
  `origin_words`, `added_at`, `changed_at`, `mockable`, `mocked`.
- `variant` `{"from": "grid"|"structure", "table": "orders"}` or `{"from": "structure", "structure": "shop",
  "path": "$.orders"}`, `"name"?`: a sandbox variant: a copy with its own designation ("orders · sandbox" as
  `orders_sandbox`, then "orders · sandbox 2"; or the name given), its origin kept (which table, connection or
  structure, when copied). It never writes back to its origin.
- `mock` `{"table": "notes", "connection": "Warehouse"}`: a table from a file, its columns or a grid of no
  connection's answers as Warehouse (its kind and dialect); `"connection": null` back to plain DuckDB.
- `edit`: its grid's edits, sandbox writes counted in the change log (Reset undoes them), each value checked
  against its column's type first: `{"table", "op": "update", "row": 0, "column": "amount", "value": "9.5"}` (the
  row's place in its open grid's view, its steps applied), `{"op": "update", "where": {...}, "values": {...}}`,
  `{"op": "insert", "values": {...}}`, `{"op": "delete", "rows": [0, 3]}` or `{"where": {...}}`. A LIST, STRUCT
  or MAP column takes JSON (`["a", "b"]`, `{"x": 1}`, as text or as the value), checked against its type.
- A saved connection may not be called `Sandbox` (any case): it is the project's sandbox's name.

## The Sandbox is a connection
The open project's **Sandbox** is a connection kind of its own (`sandbox`): its card on the Connections page
(`connections_usage`: local test data, never live), its tables through the one tables contract (`[Sandbox].x`,
its tree), its own indigo colour (never the palette's; it cannot be changed). It is never exported as a
connection: an export names the real connection a table is mocked as, or none.

## API.py: the project's local sandbox API: `api(action, args)`
Every project has `API.py` at its top (New project makes it; `api(new)` for an older one), the user's own file
(never regenerated). Its settings are its header (`# /// swissarmybench-api`: name, description, target, base_path).

    from typing import TypedDict
    from sab_api import ApiError, connection, endpoint, records

    class Order(TypedDict):
        order_id: int
        region: str

    @endpoint("GET", "/orders/{region}")
    def orders_in(region: str, limit: int = 100) -> list[Order]:
        db = connection("Warehouse")       # the adapter's calls on Warehouse (here: its sandbox tables)
        return records(db.read("dbo.orders", filters=[["region", "=", region]], limit=limit))

- A path's `{name}` is its parameter; a TypedDict, dataclass, dict or list parameter is the JSON body; the rest
  are the query's. `raise ApiError(404, "No order 7.")` answers that status. `status=201` on the decorator.
- `connection(name)` is the adapter's calls on that connection (the same in an export, against the real one;
  here over the sandbox's tables read from it, never the real one): `tables()`, `columns(table)` (`name`,
  `type`, `key`), `read(table, columns=, filters=[[column, op, value]], sort=[[column, "asc"|"desc"]],
  limit=, offset=)` (a plan: the real source folds it into its own query), `query(sql, params)` (SQL a plan
  cannot say, joins and CTEs, in the connection's OWN dialect and driver marks: T-SQL for SQL Server and
  Dataverse's SQL endpoint, the driver's for a database, DuckDB's for `Sandbox`; a statement that returns no
  rows answers one `count`), `write(table, rows, key=[...], mode=insert|update|merge|delete|truncate)` (rows: a
  list of dicts or Arrow; all or none; the counts). Each answers Arrow; `records(x)` makes it dicts, and an
  endpoint may return the Arrow as it is. What the sandbox cannot emulate in a query (MERGE, EXEC, temporary
  tables, system views) is refused with its line. Dataverse's SQL is read-only (SELECT only). The old client
  calls (`cursor()`, `execute`, `rows()`, `fetch`...) went with the mock clients (2026-11-22): said in one line.
- Through `query` an API may make `CREATE [OR REPLACE] VIEW v AS SELECT ...`, `CREATE TABLE t AS SELECT ...`
  (T-SQL's `SELECT ... INTO t`), `CREATE SEQUENCE s` (`nextval('s')`, T-SQL's `NEXT VALUE FOR s`) and drop them;
  never over a table the user added. A view or table made is that connection's table from then on (its source
  "Made by the API"); Reset and Restore undo all of it. A view cannot hold a bound value (write it in its SQL).
- Load many rows with one `write(table, rows)` (one Arrow call, all or none), not a loop of queries. A read
  streams every row: ask for less with `limit` and `offset` when that is all needed.
- The body is checked against its model (a TypedDict's or a dataclass's fields, nested ones, `list[Model]`)
  before the endpoint runs: a wrong type, a missing required field or an unknown one is a 422, its `error` naming
  the field and `field` its path (`order.lines[0].quantity`). Numbers as FastAPI takes them: 3.0 or "3" for an
  int, "12.5" for a float (converted); never True for a number.
- `state` (brief): settings, endpoints (each one's `data`: "Mock of Warehouse (sqlserver)"), models, problems
  with their lines, whether it runs, the `targets`, whether the agent may write this session; `{"full": true}` adds the OpenAPI document
  (or `openapi`). Each endpoint's `fields` (its body model's, with
  `type` and `required`) and `try` (a made-up request: `path`, `query`, `body`, filled from the endpoint's
  learned shape: the fields it was last sent, made-up values by their types; `learned` says whether): the one
  definition Try it, the Canvas's Event mapping and Payload shapes read. `settings` `{name, description, target, base_path}`.
- `run` (127.0.0.1, a key of its own; started again when API.py changes), `stop`, `log` (method, path, status,
  ms, rows; a refusal's `error` and its API.py `line`; `output`: the last lines API.py printed), `openapi`, `address` (its URL and key, for this computer's callers).
- `call` `{"method": "POST", "path": "/orders", "body": {...}}`: the first write waits for the user's Allow, and
  that Allow covers the rest of the session (the project's sandbox only; `state` says whether).
  `writes` with `{"allow": false}` stops it (each write asks again); `{"allow": true}` asks for it. A refusal
  (400 and up) also has `error` (its sentence) and, when the endpoint itself failed, `line` and `where`
  ("API.py line 45"). A path no endpoint answers is the API's own 404 (`{"error"}`).
- `example` is gone (2026-11-22): no request's or answer's value is ever kept; `try` is made up from types.
- From a kernel: `sab.api().get("/orders/West")`, `.post(path, json=...)`, `.put`, `.patch`, `.delete`.
- In its editor (the Scripts page) API.py's own problems are squiggles (the same rules, a `connection("X")` with no
  sandbox table, SQL in a `query` the sandbox would refuse: `workbench_problems`); `sab_api`'s names and the sandbox's tables
  and columns complete. Its Endpoints panel (the status bar's toggle) has each endpoint's Try it beside the code.
- Payloads through the adapter: an endpoint may return an Arrow table (`from adapter import read, Plan`);
  it is answered as JSON records (or an Arrow IPC stream to a caller sending `Accept:
  application/vnd.apache.arrow.stream`). A body typed `Annotated[pa.Table, Order]` is checked against Order
  (422 naming the field), then given as an Arrow table; OpenAPI and Try it show it as `list[Order]`.

## Export for a framework target
- `targets`: FastAPI, Azure Functions (Linux, Python v2), AWS Lambda (Linux, Python); extensions add theirs.
- The target is API.py's own (asked at New, changed in Properties: `settings`); Export never asks again.
- `export` `{"target"?, "folder"?, "rows"?, "replace"?: [files]}`: `exports/api/<target>/` in the project (a made
  folder): API.py as it is, sab_api.py, adapter.py (the adapter: duckdb and pyarrow in its requirements),
  connections.py (each connection's own portable code: its variables read
  where it runs, nothing here runs it), the target's files (main.py; function_app.py, host.json,
  local.settings.json; lambda_function.py, template.yaml), requirements.txt, README.md (deploy steps, the
  checklist, `variables` to set). No secret in any file. A file edited by hand is `kept` until `replace` names it.
  `rows`: bundle the sandbox for `connection("Sandbox")` (the agent's waits for Allow); without it the answer's
  `warnings` say those endpoints answer an error there.

## New endpoint: the wizard's patterns
One wizard on the page (New endpoint…), one command for you: nine patterns, each with its own steps.
- `patterns`: the nine as data (`steps`: what each asks; `widgets`: the canvas widgets that pair with it).
  table (list, get, create, update, delete by a key), choices (a dropdown's value and label), search (a text
  search, a filter per column, sort, page), summary (totals per group; by day, month, quarter or year), bulk
  (many rows: checked, `?dry_run=true` lists the problems, then all or none), action (a named change to the rows
  whose keys are sent, all or none), versions (a thing's versions, its current one, a new one), reconcile (two
  tables by a key: matched, missing each side, differing), export (a CSV file or an Excel workbook).
- `plan` `{"table": "orders"}`: every pattern `ranked` by the table's shape, each with `why` in one sentence
  (`fits: false` says what it needs). With `"pattern": "summary"` too: that pattern's `plan.steps` (each one's
  `options`: the columns that fit; its `value`: what the shape suggests, or what you sent in `fields`), and the
  `code` it would add, or `problem`: the one thing still missing. Writes nothing.
- `scaffold` `{"table": "orders", "pattern": "summary", "fields": {"group": ["region"], "totals": [{"fn": "sum",
  "column": "amount"}]}}`: its endpoints appended to API.py (`added`), `paired`: the widget for each
  (a bar chart's table In for `GET /orders/summary/region`). `"dry_run": true`:
  the `code` and `imports` only. Reconcile takes `"other"`: its second table. Fields left out take the plan's
  values. The older `{"table", "key"}` is the table pattern.
- The code is one style for every source: `connection(name).read(...)` (filters, columns, sort, page and keys in
  its plan), `.query(...)` in the source's own SQL where one statement does it (a summary by period, a
  reconcile), `.write(...)` (one write: all or none). Where a source cannot do a part (Dataverse's Web API,
  SharePoint, two connections), only the columns needed are read and DuckDB does it over the stream: the
  endpoint's `data` says so. One comment marks the block (`# pattern: summary of orders`): `state`'s endpoints
  carry `pattern` {id, label, of, role}. The code is the user's from then on: change it in API.py.
- A widget inserted on a canvas wires itself to the endpoint its pattern pairs with (`canvas_insert_widget`'s answer
  has `wired`): the one match, else the one over the table its nearest neighbour uses; never a guess.

## Widgets that use it, and their shapes
- Prebuilt widgets: API table (a GET's rows, paged by `limit` and `offset`), API form (a POST or PUT from its body
  model's fields), API button, API metric. Their `endpoint` property is "GET /orders" (one of API.py's: the
  endpoint mask); `path_values` is one box per `{name}` of that endpoint's path, each a value, `${NAME}` (a
  variable) or `{{ name }}` (a page value: the page's st.session_state). Play and Launch reach the API while it
  runs (SAB_API_URL, SAB_API_KEY, SAB_API_BASE in the app's environment); a canvas Export that calls it lists the
  three as variables to set (its answer's `variables` and `warnings`, and its README).
- `shapes`: each canvas widget using an endpoint, and each Event wired to call one (`event`), what it expects or
  sends beside the endpoint's own definition, each mismatch (a field the body lacks, a required one not sent, a
  path value not given).
- `check` (Will this work for real?): each endpoint's SQL against its connection's catalog as loaded here, never a
  query on the source; an unloaded catalog is said ("load it on the Connections page").
