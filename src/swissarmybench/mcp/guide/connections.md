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
- `connections_colours`: each connection's colour (this computer's: the same in every project) and the
  palette; `connections_colours(name, colour)` sets one (`#rrggbb`; null: the next free one). The rail's
  colours (the kind colours, the red accent) and amber are refused. Its grid tabs, cells, canvas blocks
  and Session entries wear it as a stripe; the home page's tabs are grouped by connection.
- `app_navigate(to="connection:<name>")` shows that detail to the user; `workbench_window
  file.openCell` opens a reference's cell.

## Variables (the rail's Variables page)
- This computer's, whether or not a project is open; never in a project. Connections, notebooks, scripts
  and Workbench kernels read them as environment variables (a running kernel: at its next start).
- `variables_list(search, source)`: each variable's source (`vault`: the vault and secret name; `value`:
  a plain value, shown; `keyring`; `env`: this computer's environment, its value shown unless it reads
  as a secret; `missing`), and its `uses` (connections by setting, notebook and script cells, Run
  settings). Never a keyring's, a secret's or a vault's value: Show is the user's only.
- `variables_set(name, value)`: a plain value; `local=true` keeps it on this computer only (a path).
  `kept="keyring"` saves a secret in the keyring: you may set one, never read it back.
- `variables_rename(name, to)`: connections' code and Run settings follow; `still_reading` lists the
  notebook and script cells to change. `variables_remove(name)` answers what still uses it.

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
- Ways to sign in: a type's `sign_ins` each carry their own code. Trino: a password, or a client
  certificate from a keystore file (PKCS#12, JKS, JCEKS; `keystore`, `keystore_alias`,
  `secret("TRINO_KEYSTORE_PASSWORD")`; JKS needs the pyjks package).
- A certificate or keystore file setting (a setting whose `env` key is present) may come from an
  environment variable, this computer's path its default: `blades_fill` with
  `{"<id>": {"value": path, "env": "TRINO_KEYSTORE_PATH"}}`; `env: null` makes it a plain path again.
  An export and a script's run settings then list the variable.

## Lakes and SharePoint
- Five kinds (`connections_types`, group "Lakes and SharePoint"): `onelake`, `datalake`, `delta`,
  `sharepoint` (lists), `sharepoint_docs` (libraries). Their own code lists and reads their tables; the
  same connection commands make, test and read them.
- Names in DuckDB SQL: the table's folders, then its name (`[Lake].sales.orders`, `[Fabric].Files.raw.
  regions`, `[Team Docs].Documents.Finance."Budget 2026.xlsx".Summary`); the last parts are enough when
  they name one table. A Delta table's version or time: `"orders@v12"`, `"orders@2026-11-01"`.
- Every setting may come from an environment variable (`blades_fill` with `{"<id>": {"value": v, "env":
  "SHAREPOINT_TENANT_ID"}}`; a setting's `suggested_env` is the form's name). SharePoint signs in by
  username and password (ROPC) first; ROPC cannot do MFA (the error says so).
- Writes are Write starters (dry run first); SharePoint documents' files are the SharePoint starters.

## Reading one
- `connections_open_table(name, table)`: a table as a grid (a database's first rows, 10,000 unless
  the connection says otherwise; `all=true` for every row). `connections_preview_table`: 50 rows, kept
  nowhere.
- In code: `workbench_run(kind="sql", connection=name)` runs a SQL cell in the source's own SQL; files
  and DataFrames are read with DuckDB.

## A connection's tables in DuckDB SQL
A connection is something that exposes tables (a key vault is not one). Name one in any DuckDB SQL as
`[Finance Captive].Sales` (or `"Finance Captive".Sales`): `tabs_new_query`, `steps_run_sql`, a `%%sql`
cell with no connection, `sab.sql(query)`. Joins across connections work.
- Database: `[C].table`, `[C].schema.table`, `[C].database.schema.table`, any case. Power BI:
  `[C].table` when one dataset has it, else `[C]."Sales model".table` (the error names the datasets).
  Files and folders: `[C].<sheet or file>`. Python and API connections: their List the tables names.
- Every row the query needs is read (never Rows to open): its columns and plain filters go to a SQL
  source, a LIMIT only when safe; the count is asked first, and past SWISSARMYBENCH_MAX_QUERY_ROWS
  (5,000,000) it is refused: add a WHERE. Each answer's `connection_reads`: rows, `read_at`, `sent`.
- Reads are kept for the session: `connections_sql_reads`; `connections_sql_refresh` reads again.
- `connections_tables(name)`: the tree (datasets or schemas, each table's `sql` name).
  `connections_open_dataset(name, dataset)`: every table of one as its own grid.
- Dataverse lists and reads its tables on its SQL endpoint; one saved for the Web API:
  `connections_dataverse_sql_endpoint`.

## Swapping a table's connection (the Table row's Connection…)
- `table_connection(table)`: its connection (`exists` false: deleted, or not on this computer), how it
  is read (`table`: a catalog table, its `place`; `query`: its `sql`), the `others`, `undo`.
- `table_swap_connection(table, to)`: read again from `to`, the grid's steps kept (the tab stays). A
  catalog table is matched by name in any case (schema, then database, breaks a tie; an ODBC database
  may be Trino's catalog). Answers `swapped` (its steps problems: a step that no longer works), or `pick`
  (`candidates`, `schemas`, a suggested `sql`: send `place` or `sql`), or `review` (a query: look it
  over, names may differ between ODBC and native Trino, then send `sql`). `table_swap_undo` puts back
  its rows and origin.
- `connections_move_tables(name, to)`: every table read from `name` (a deleted connection's waiting
  tables too) moved at once; queries come back in `review` unless `run_as_is`.
- `connections_repoint(name)` lists the cells that name it (`pickable`: a table's read-only cell and
  a canvas block follow on their own); with `to` (and `picks` [{document, cell}]) the name changes in
  those cells only: inside the client's call or a `%%sql`/`%%dax` line, never another string. An open
  document changes in the Workbench window, unsaved until Save; another's file is written.

## Power BI workspace
- One connection (the `powerbi` type, dialect dax) reaches every dataset in the workspace, read with DAX.
  Its sign-in: an app registration whose ids come from a key vault, ids typed in, or a browser sign-in.
- `connections_datasets`: its datasets, each named `Finance/Sales model` (connection/dataset).
- DAX: `workbench_dax_add`, or `workbench_run(kind="dax", connection="Finance/Sales model")`.
  At most 100,000 rows or 1,000,000 values a query: summarize in DAX.
- `connections_import_relationships(name, dataset)`: the dataset's joins into the relationship model.

## SQL Server and Azure SQL
- Types `sqlserver` and `azuresql` (dialect sqlserver). The code makes a `SqlServer` object: eight
  sign-ins (`sign_ins`: Windows, SQL login, Microsoft Entra as you, Entra password, the driver's Entra
  default, managed identity, an app registration with a vault's secret or a certificate); the driver
  found (ODBC Driver 18, then 17, else mssql-python; none: the install command); Options: encryption
  (mandatory, optional, strict), Trust server certificate, host name in certificate, port or instance,
  read-only intent (on for reads; the Write starters take the primary), multi-subnet failover, timeouts.
- Server, database, user, client id and tenant may come from an environment variable: send
  `{"value": "...", "env": "NAME"}` for that setting (`/blades/fill`).
- Errors come in plain words with the fix (login failed 18456, the Azure firewall 40615 with the address,
  a paused serverless database 40613: waited for up to 60 s, the card says Resuming). Passing errors are
  tried again on connect and on reads. Test says the driver, sign-in, version and collation (the card).
- `connections_import_relationships(name)`: the database's foreign keys into the relationship model.

## Dataverse
- One connection (the `dataverse` type, dialect dataverse) reaches an environment's tables: its
  `url` (https://<name>.crm.dynamics.com) and a sign-in (`sign_ins`: as you, managed identity, an app
  registration whose client secret is a vault's entry; a typed secret is refused).
- Its catalog: one schema, dbo; each table's display name is `title` in `catalog_tables`.
- Its tables are listed and read on its read-only SQL endpoint (TDS; the owner's choice). One saved
  for the Web API still reads through it; `connections_dataverse_sql_endpoint` moves it. When the
  endpoint is off, its administrator turns it on in the Power Platform admin center. In code: `sab.read(name, table)`,
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

## Finding data (the Data Explorer)
- `explorer_search(text)` searches everything that holds data at once: connections, their loaded catalogs'
  tables and columns (each table with its DuckDB SQL name), the open tables and their columns, variables
  (names and sources) and blades. Any case, by parts: `cust` finds `customer_id` and `CustomerKey`.
- `kinds=["columns"]`, `connection="Shop"` narrow it; `column="customer_id"` lists every table with that
  column in every connection (a join's hint). `offers` are connections whose catalog is not loaded:
  `connections_load_catalog`, then search again.
- The user's pane (Ctrl+Shift+E in the Workbench, Ctrl+K on the grid page) shows the same results; its
  actions are tools you have: `connections_open_table`, `connections_preview_table`, `workbench_window`
  (`explorer.insert`, `explorer.popOut`, `explorer.moveBack`).
