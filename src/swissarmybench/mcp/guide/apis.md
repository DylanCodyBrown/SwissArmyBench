# APIs

An API is blades in this computer's library (`~/.swissarmybench/library/apis/<name>/`), never a project's:
its API blade (the made client `API_<name>.py`: base address, sign-in, retries, paging; a secret's
source by name, never its value) and one web call blade per operation (`Orders.list_orders`: that call
alone, its inputs and body its settings, through `sab.blade("Orders")`). The folder also holds
`openapi.json` (the document as read; a form's operations as one) and `source.json` (where it was read
from, when). APIs are not on the Connections page: the APIs page is their home.

## Finding and reading
- `apis_list`: each API: operations, tables, sign-in type, source and when it was read, calls.
- `apis_search(q)`: every API's operations by plain name, method, path, text, tags, parameter and field
  names; `matched` says where each word was found.
- `apis_describe(name, operation?)`: an operation's inputs (parameters: where, type, required, default),
  its body's schema and a made-up example, each status's schema and example, its web call blade, its
  SQL name when it is a table; with no operation, every one and the named schemas (`used_by`).

## Calling
- `apis_call(name, operation, inputs?, body?)`: sent through its web call, after its API blade (the
  sign-in is the blade's, never shown). The answer opens in Structures: you get its status, time,
  headers and `structure` (read it with `structures_show`; `structures_lineage` is the call, its steps,
  the grids made from it; `run_again=true` sends it again). `suggest_table`: the settings Return as table
  would start with; never switched on by itself.
- Making one: `connections_api_add` (an OpenAPI document by address, file or text, or a form).

## Return as table: the one gate to DuckDB SQL
- `apis_save_call(name, operation, inputs?, body?)` saves the web call blade. `as_table=true` makes it one
  of the API's tables: `SELECT * FROM [Orders].list_orders` (a SQL cell on the API, `sab.read`).
- Its settings: `shape` records or header_rows; `records` (where the rows are: `$.items`, `$.data.rows`);
  `header` (its path, or `first_row`); `columns` (DuckDB types; a header's own types win); `flatten`
  (nested objects as columns; a list inside a record stays a LIST); `paging` all or first. Or give
  `structure` (an answer in Structures) and they are found there.
- DuckDB does the converting: `conversion` is its SQL over `response` (one row per page, the JSON in
  `page`), editable.
- A required input with no value: the table lists `(needs <name> (<where>))`; give it in the web call.

## Writing rows
- `apis_write_rows(name, operation, table)`: a dry run (the default): the mapping (matched by name),
  `missing` (required fields nothing fills), the first three requests, the rows and the calls. Nothing is
  sent. `dry_run=false` sends: only after the user said to write, in their own words, in this
  conversation. `mapping` `{"body.customer.name": {"column": "name"}, "query.dry": {"value": true}}`,
  `batch=true` (one call, the body an array), `key_columns`, `response_field`. The results: a structure
  and a grid (status, the answer's field, the error per row); `retry=<results structure>` sends the failed
  rows again. `save=true` keeps it as a web call blade (mode "write rows").

## Managing
- `apis_refresh(name)`: the source read again (an address or a file it was added from): operations
  added, removed and changed (parameters, body and response fields). Nothing is written until
  `apis_apply_refresh`. `apis_rename(name, check=true)`: check for changes when the page opens.
- `apis_rename(name, new_name)`: its blades renamed; the code that named it is listed.
- `apis_delete(name)`: the code that uses it; `confirm=true` deletes it, after the user's Allow.
