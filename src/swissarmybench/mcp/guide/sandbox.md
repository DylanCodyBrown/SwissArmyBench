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
