# The sandbox and local sandbox APIs

The project's sandbox is its own DuckDB file (`.sab/sandbox/`, Git-ignored): the only data a local sandbox API
reads and writes. A real connection is never reached from one ("No never run against live data ever").

## The sandbox: `sandbox(action, args)`
- `list`: its tables (rows, columns, where each came from, `client`: the connection its rows are mocked as), the
  baseline, the checkpoints, the change log (inserted, updated, deleted per table since the baseline).
- `add`: `{"from": "grid", "table": "orders"}` (an open table's view, after its steps), `{"from": "connection",
  "connection": "Warehouse", "table": "orders", "schema": "dbo"}` (read once, its row limit applying),
  `{"from": "file", "path": ...}`, `{"from": "columns", "name": "notes", "columns": [{"name": "id", "type":
  "integer", "key": true}]}`; `"name"` names it, `"replace": true` replaces one.
- `remove` `{"table"}`, `open` `{"table"}` (in Grids as `sandbox_<table>`, following every write).
- `reset`: every table back to the baseline (waits for the user's Allow). `baseline`: the sandbox now is the
  baseline. `checkpoint` `{"name", "action": "save"|"delete"}`, `restore` `{"name"}`.
- DuckDB SQL names a sandbox table `[Sandbox].orders` (`steps_run_sql`); the Catalog has a Sandbox section.
- `reset` with `{"table": "orders"}` puts that one table back alone.

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
        db = connection("Warehouse")       # a mock with Warehouse's own client's shape
        with db.cursor() as cursor:        # T-SQL, as the real SQL Server would take it
            cursor.execute("SELECT TOP (?) * FROM dbo.orders WHERE region = ?", limit, region)
            return records(cursor)

- A path's `{name}` is its parameter; a TypedDict, dataclass, dict or list parameter is the JSON body; the rest
  are the query's. `raise ApiError(404, "No order 7.")` answers that status. `status=201` on the decorator.
- `connection(name)` is a mock of that connection's client over the sandbox's tables read from it (SQL Server's
  SqlServer, Dataverse's Dataverse, SharePoint lists, any DB-API database, `connection("Sandbox")` a plain
  DuckDB client). Its SQL is the source's own dialect and marks; what the mock cannot emulate (MERGE, EXEC,
  temporary tables, system views, a Web API call) is refused with its line. It never reaches the real one.
- `state`: settings, endpoints (each one's `data`: "Mock of Warehouse (sqlserver)"), models, problems with their
  lines, the OpenAPI document, whether it runs. `settings` `{name, description, target, base_path}`.
- `run` (127.0.0.1, a key of its own; started again when API.py changes), `stop`, `log` (method, path, status,
  ms, rows), `openapi`, `address` (its URL and key, for this computer's callers).
- `call` `{"method": "POST", "path": "/orders", "body": {...}}`: a write waits for the user's Allow.
- From a kernel: `sab.api().get("/orders/West")`, `.post(path, json=...)`, `.put`, `.patch`, `.delete`.

## Export for a framework target
- `targets`: FastAPI, Azure Functions (Linux, Python v2), AWS Lambda (Linux, Python); extensions add theirs.
- `export` `{"target"?, "folder"?, "rows"?, "replace"?: [files]}`: `exports/api/<target>/` in the project (a made
  folder): API.py as it is, sab_api.py, connections.py (each connection's own portable code: its variables read
  where it runs, nothing here runs it), the target's files (main.py; function_app.py, host.json,
  local.settings.json; lambda_function.py, template.yaml), requirements.txt, README.md (deploy steps, the
  checklist, `variables` to set). No secret in any file. A file edited by hand is `kept` until `replace` names it.
  `rows`: bundle the sandbox for `connection("Sandbox")` (the agent's waits for Allow).

## New endpoint from a table
- `scaffold` `{"table": "orders", "key": "order_id"}`: the CRUD set appended to API.py (list with `limit` and
  `offset`, get, create, update, delete by the key; a TypedDict of the columns), written in the source's own
  style: DuckDB SQL for `Sandbox`, T-SQL through SQL Server's cursor, the driver's SQL and marks for another
  database, OData reads for Dataverse (its writes go through the Write starters), list calls for SharePoint.
