# Connections and catalogs

A connection is a saved way to reach data: a database, a file, a Power BI workspace, Dataverse, the user's own
Python, or a key vault (the rail's Connections page: a card each). Every Workbench kernel has each one as
a variable by its name.

## The Connections page
- `connections_overview`: each card: its type, its status (`works`: its last call worked; `ready`: not
  used yet; `needs`: a password is in none of its places, `missing` names it; `failing`: its last call or
  its catalog failed), its calls this session. A cheap check: nothing runs.
- `connections_usage(name)`: a card's detail. `references`: every notebook or script cell (`%%sql`,
  `%%dax`, `sab.sql`, `sab.dax`, `sab.read`, `sab.blade`, `sab.connection`; marked as a table's
  read-only cell), every canvas block on such a cell, every open grid read from it; `configuration`:
  type, settings, sign-in, each password's source (keyring, vault, environment, missing) by name, never
  a value; `calls`: by kind (catalog, query, read, test, connect), the last one. Calls count what runs
  through the app and Workbench kernels, not the user's own Jupyter.
- `app_navigate(to="connection:<name>")` shows that detail to the user; `workbench_window
  file.openCell` opens a reference's cell.

## Making one
- `connections_list`: every connection, its type, its name in code, its catalog's state.
- `connections_types`: each kind's form (fields, passwords, the code they fill). Start from one.
- `connections_test` (saved or not, in a child process), then `connections_create` or
  `connections_update`. `connections_get` shows a saved one as its form.
- Passwords: write `secret("WAREHOUSE_PASSWORD")` in the code and never a value.
  `connections_password_source` points one at the keyring, an environment variable or a vault's entry.
  `blades_secrets` saves values the user gives you; nothing reads one back.
- A missing package: any answer may carry `missing` {feature, packages, python, command} (a form,
  `blades_inspect`, a failed test or refresh, a YAML API document). `python` "app": `blades_install`
  them into the app's own Python, then do it again. The user sees the same as a prompt.

## Reading one
- `connections_open_table(name, table)`: a table as a grid (a database's first rows, 10,000 unless
  the connection says otherwise; `all=true` for every row). `connections_preview_table`: 50 rows, kept
  nowhere.
- In code: `workbench_run(kind="sql", connection=name)` runs a SQL cell in the source's own SQL; files
  and DataFrames are read with DuckDB.

## Power BI workspace
- One connection (the `powerbi` type, dialect dax) reaches every dataset in the workspace, read with DAX.
  Its sign-in: an app registration whose ids come from a key vault, ids typed in, or a browser sign-in.
- `connections_datasets`: its datasets, each named `Finance/Sales model` (connection/dataset).
- DAX: `workbench_dax_add`, or `workbench_run(kind="dax", connection="Finance/Sales model")`.
  At most 100,000 rows or 1,000,000 values a query: summarize in DAX.
- `connections_import_relationships(name, dataset)`: the dataset's joins into the relationship model.

## Dataverse
- One connection (the `dataverse` type, dialect dataverse) reaches an environment's tables: its
  `url` (https://<name>.crm.dynamics.com) and a sign-in (`sign_ins`: as you, managed identity, an app
  registration whose client secret is a vault's entry; a typed secret is refused).
- Its catalog: one schema, dbo; each table's display name is `title` in `catalog_tables`.
- `connections_open_table(name, table)` and `connections_preview_table` read through the Web API (no
  admin setting needed); choice columns arrive as labels. In code: `sab.read(name, table)`,
  `conn.read(table, columns=, filter=, order_by=, limit=)` (OData), `conn.fetch(fetch_xml)`.
- SQL (`workbench_run(kind="sql", connection=name)`) is T-SQL on its read-only SQL endpoint: when that
  is off, the error says so and gives the sab.read line instead.

## Your own Python
- Three boxes: Connect (makes `conn`), List the tables (its catalog), Read a table (rows, or
  `(rows, total)`). `connections_python_variables` finds the environment variables they read;
  `connections_python_save` saves (`test=true` only runs it); `connections_python_tables` lists tables.

## Add API
- An OpenAPI document (`spec_url`, `spec_path` or `spec`) or `form` (base URL, endpoints) becomes
  API_<name>.py (beside data.py: pass the project's `folder`) and a Python connection whose tables are
  the GET operations that answer rows. `connections_api_choices`: auth types, settings, presets (Azure,
  AWS, Google). `connections_api_add(preview=true)` first: operations, the variables it reads, what a
  re-import changes; `try_it=<operation>` reads its first rows before Add (`values`: a key for that
  try only). Then point each variable at a source (`variables`, as connections_python_save).
  A file Add API did not make, or a connection of that name that is not its own, is never replaced.

## Key vaults
- A vault connection sets its secrets as environment variables in every kernel.
  `connections_vault_secrets` lists a vault's secret names (never values), each with a suggested
  variable; `connections_create(kind="vault", vault_all=true)` takes them all, `vault_mapping`
  renames some. `connections_vaults` lists the vaults a password can come from.

## Catalogs (names and types, never values)
- A catalog loads by itself when its connection is saved, at start (not one that signs in with a
  browser window) and on first use; `connections_load_catalog` loads one now.
- `catalog_search` first (`sales.orders` is schema.table or table.column), then `catalog_list`,
  `catalog_schemas`, `catalog_tables`, `catalog_columns` (a first SELECT quoted for the source's dialect).
  `catalog_load` and `catalog_remove` for one you make yourself.
- A source's tables are not in the grid's DuckDB: `steps_run_sql` cannot read them. Open one as a grid,
  or run SQL on the source in a kernel.
