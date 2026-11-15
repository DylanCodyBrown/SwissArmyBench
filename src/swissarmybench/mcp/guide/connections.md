# Connections and catalogs

A connection is a saved way to reach data: a database, a file, a Power BI workspace, the user's own
Python, or a key vault (Connections in the Application row). Every Workbench kernel has each one as a
variable by its name.

## Making one
- `connections_list`: every connection, its type, its name in code, its catalog's state.
- `connections_types`: each kind's form (fields, passwords, the code they fill). Start from one.
- `connections_test` (saved or not, in a child process), then `connections_create` or
  `connections_update`. `connections_get` shows a saved one as its form.
- Passwords: write `secret("WAREHOUSE_PASSWORD")` in the code and never a value.
  `connections_password_source` points one at the keyring, an environment variable or a vault's entry.
  `blades_secrets` saves values the user gives you; nothing reads one back.
- A missing driver: the test says so; `blades_install` installs it into the app's own Python.

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

## Your own Python
- Three boxes: Connect (makes `conn`), List the tables (its catalog), Read a table (rows, or
  `(rows, total)`). `connections_python_variables` finds the environment variables they read;
  `connections_python_save` saves (`test=true` only runs it); `connections_python_tables` lists tables.

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
