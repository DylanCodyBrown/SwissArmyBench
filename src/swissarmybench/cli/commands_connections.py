"""The agent's connections_* commands: connections: the user's databases and files (Application row's Connections).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req


#
# The name's prefix is the area, in the order the app shows them: the tab bar, the datasets, the
# ribbon's Table and Column rows, a cell's right-click menu, the Table Transformations panel, the Key Finder, the
# Relationships dialog and ERD tab, compare, Analyze, then what only an agent sees.
# The catalog groups by area, and so does the MCP's tool list.
@command(
    "connections_list",
    "Every connection: database or file, its type, its name in Workbench code, its catalog, and what it "
    "writes (writes.words: 'Writes: <the Write starters>' or 'Read-only: <why>'; never write a read-only one)",
)
def connections_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections")


@command(
    "connections_types", "The kinds of connection and each one's form: fields, passwords, the code they fill"
)
def connections_types(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections/types")


@command(
    "connections_get",
    "A saved connection as its form: fields, passwords (saved or not), code",
    req("name", "The connection."),
)
def connections_get(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/connections/{_q(a['name'])}")


@command(
    "connections_overview",
    "The Connections page's cards: each connection's status, calls this session and writes ('Writes: ...' "
    "or 'Read-only: <why>')",
)
def connections_overview(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections/usage")


@command(
    "connections_usage",
    "One connection's detail: cells and blocks that use it, its configuration (no values), its calls",
    req("name", "The connection."),
)
def connections_usage(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/connections/{_q(a['name'])}/usage")


@command(
    "connections_colours",
    "Each connection's colour (this computer's, every project) and the palette; name and colour set one",
    opt("name", "A connection, to set its colour."),
    opt("colour", "#rrggbb, never a rail colour; null: the next free one."),
)
def connections_colours(a: dict[str, Any]) -> Any:
    if a.get("name"):
        return api.call("PUT", f"/connection-colours/{_q(a['name'])}", {"colour": a.get("colour")})
    return api.call("GET", "/connection-colours")


# ----- each connection's slots: queries at once, the agent's share, the line (2026-11-21) -----
@command(
    "connections_slots",
    "Each connection's running and waiting query counts and limits (default 8 at once, 4 the agent's)",
)
def connections_slots(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections/slots")


@command(
    "connections_queries",
    "Running, waiting and finished queries (who, what, tables, place, time); no SQL",
    opt("connection", "One connection's (default: every one's)."),
    opt("clear", "true: empty the finished list first.", "bool"),
)
def connections_queries(a: dict[str, Any]) -> Any:
    if a.get("clear"):
        api.call("POST", "/connections/queries/clear", {})
    query = "?connection=" + _q(a["connection"]) if a.get("connection") else ""
    return api.call("GET", "/connections/queries" + query)


@command(
    "connections_cancel_query",
    "Cancel a query by its id: yours at once, the user's on their Allow",
    req("id", "The query's id."),
)
def connections_cancel_query(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/queries/{_q(a['id'])}/cancel", {})


@command(
    "connections_set_limits",
    "Set a connection's queries at once (1-64), the agent's share and the wait in seconds",
    req("name", "The connection."),
    opt("total", "Queries at once.", "int"),
    opt("agent", "The agent's share.", "int"),
    opt("wait", "Seconds a query waits in line before it gives up.", "int"),
)
def connections_set_limits(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("total", "agent", "wait") if a.get(k) is not None}
    return api.call("PUT", f"/connections/{_q(a['name'])}/limits", body)


@command(
    "connections_move_tables",
    "Move every table read from a connection (a deleted one too) to another, as table_swap_connection",
    req("name", "The old connection."),
    req("to", "The new one."),
    opt("run_as_is", "Run queries unreviewed.", "bool"),
)
def connections_move_tables(a: dict[str, Any]) -> Any:
    body = {"to": a["to"], "run_as_is": a.get("run_as_is") is True}
    return api.call("POST", f"/connections/{_q(a['name'])}/move", body)


@command(
    "connections_repoint",
    "Cells naming a connection (a deleted one too): list them (no to), or point them at another",
    req("name", "The old connection."),
    opt("to", "The new one."),
    opt("picks", "[{document, cell}] (default: all).", "json"),
)
def connections_repoint(a: dict[str, Any]) -> Any:
    if not a.get("to"):
        return api.call("GET", f"/connections/{_q(a['name'])}/references")
    body = {"to": a["to"]} | ({"picks": a["picks"]} if a.get("picks") is not None else {})
    return api.call("POST", f"/connections/{_q(a['name'])}/repoint", body)


_CONNECTION_ARGS = (
    req(
        "kind",
        "sql for a database, other for a file (with template csv, excel, parquet, json or folder), vault "
        "for a key vault (with vault_mapping, vault_all or both).",
    ),
    req("code", "The connection's Python (a type's code from connections_types, filled in)."),
    opt("template", "The type it came from (connections_types id)."),
    opt("dialect", "For a database: its SQL dialect."),
    opt("variable", "The variable the code makes (default: the last one assigned)."),
    opt("description", "What it is for."),
    opt("catalog", '{"language", "command"}: lists the source\'s columns (the type gives one).', "json"),
    opt("secrets", '{"password": "value"}: saved in the system keyring, never shown back.', "json"),
    opt(
        "row_limit",
        "A database: how many rows a table opens with on the Tables page (10,000 unless set; 0: every row).",
        "int",
    ),
    opt(
        "vault_mapping",
        'A vault\'s entries: [{"env": "WAREHOUSE_PASSWORD", "secret": "warehouse-password"}] (each secret '
        "in the vault becomes that environment variable in every Workbench kernel). With vault_all, only "
        "the renamed ones.",
        "json",
    ),
    opt(
        "vault_all",
        "A vault: every secret it holds (its names(), read each time), each a variable under its own name "
        "(SqlPassword, Sql--Password -> Sql__Password).",
        "bool",
    ),
)


_CONNECTION_KEYS = (
    "name",
    "kind",
    "code",
    "template",
    "dialect",
    "variable",
    "description",
    "catalog",
    "secrets",
    "vault_mapping",
    "vault_all",
    "row_limit",
)


@command("connections_create", "Save a new connection", req("name", "A new name."), *_CONNECTION_ARGS)
def connections_create(a: dict[str, Any]) -> Any:
    return api.call("POST", "/connections", {k: a[k] for k in _CONNECTION_KEYS if a.get(k) is not None})


@command(
    "connections_update",
    "Change a connection (a new name renames it)",
    req("name", "Its name now."),
    req("new_name", "Its name after."),
    *_CONNECTION_ARGS,
)
def connections_update(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in _CONNECTION_KEYS if k != "name" and a.get(k) is not None} | {
        "name": a["new_name"]
    }
    return api.call("PUT", f"/connections/{_q(a['name'])}", body)


@command(
    "connections_test",
    "Run a connection's code, saved or not, in a child process: does it connect? (a file: is it there?) "
    "With code for a file type, the answer also has the file's columns and first rows (preview), and the "
    "name it would take from its file when none is given.",
    req("name", "Its name (a saved one is tested as saved unless code is given)."),
    opt("kind", "With code: sql or other."),
    opt("code", "Test this code instead of the saved."),
    opt("template", "With code: its type."),
    opt("secrets", '{"password": "value"}: typed for this test only.', "json"),
)
def connections_test(a: dict[str, Any]) -> Any:
    if not a.get("code"):
        return api.call("POST", f"/blades/{_q(a['name'])}/test", {"env": {}})
    body = {k: a[k] for k in ("name", "kind", "code", "template", "secrets") if a.get(k) is not None}
    return api.call("POST", "/connections/test", body)


# ----- Find connections on this computer: the known tools (DBeaver, SSMS, ODBC...) and the hint scan -----
@command(
    "connections_find",
    "Find connections on this computer (DBeaver, SSMS, ODBC, Azure Data Studio, VS Code, JetBrains, pgAdmin, "
    "MySQL Workbench, HeidiSQL, Office .odc/.udl, then a search of the app settings folders): waits for the "
    "user's Allow. Rows: id, name, kind, server, database, user, from, already, supported (never a password)",
    opt("hints", "false: the known tools only (no search).", "bool"),
    opt("cancel", "Stop the running search.", "bool"),
)
def connections_find(a: dict[str, Any]) -> Any:
    if a.get("cancel"):
        return api.call("POST", "/connections/found/cancel", {})
    body = {"hints": False} if a.get("hints") is False else {}
    return api.call("POST", "/connections/found", body)


@command(
    "connections_import_found",
    "Import rows of the last connections_find as library connections (each password a variable not set on "
    "this computer): on the user's Allow",
    req("ids", "The rows' ids.", "json"),
)
def connections_import_found(a: dict[str, Any]) -> Any:
    return api.call("POST", "/connections/found/import", {"ids": a["ids"]})


# ----- a connection from your own Python: three boxes and where its variables come from -----
_PYTHON_ARGS = (
    req("connect", "Connect: Python that makes `conn`, any object."),
    opt(
        "tables",
        "List the tables: Python returning conn's catalog, a list of dicts or a DataFrame with table, "
        "column, and optionally schema, type, description. Empty: no catalog.",
    ),
    opt(
        "read",
        "Read a table: Python returning a table's rows given conn, schema, table, limit (None: all): a "
        "DataFrame, Arrow table or list of dicts; or (rows, total).",
    ),
    opt(
        "variables",
        'Each environment variable\'s source: [{"name", "from": "env" | "keyring" | "vault" | "value", '
        '"vault", "secret", "value"}]. env: this computer\'s (the default); keyring: saved here (its '
        "value in secrets); vault: a key vault's secret; value: plain text, not a secret.",
        "json",
    ),
    opt("secrets", '{"NAME": "value"} for keyring variables; never shown back.', "json"),
    opt("description", "What it is for."),
    opt("row_limit", "Rows a table opens with on the Tables page (default 10,000; 0: every row).", "int"),
)


def _python_body(a: dict[str, Any], name: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "kind": "other",
        "template": "python",
        "variable": "conn",
        "code": a["connect"],
        "catalog": {"language": "python", "command": a["tables"]} if a.get("tables") else None,
        "read": {"command": a["read"]} if a.get("read") else None,
        "variables": a.get("variables") or [],
        "row_limit": a.get("row_limit"),
    }
    return body | {k: a[k] for k in ("secrets", "description") if a.get(k) is not None}


@command(
    "connections_python_variables",
    "The environment variables a Python connection's boxes read (os.environ, os.getenv, secret): "
    "names, whether needed, whether set on this computer",
    opt("connect", "The Connect box."),
    opt("tables", "The List the tables box."),
    opt("read", "The Read a table box."),
)
def connections_python_variables(a: dict[str, Any]) -> Any:
    body = {"code": a.get("connect"), "tables": a.get("tables"), "read": a.get("read")}
    return api.call("POST", "/connections/variables", body)


@command(
    "connections_python_save",
    "Save a connection made of your own Python (its three boxes and its variables' sources), new or "
    "changed; test=true only runs it (Connect, the tables, the first table's first rows), saving nothing",
    req("name", "Its name."),
    opt("previous", "To change a saved one: its name now."),
    opt("test", "Only test it.", "bool"),
    *_PYTHON_ARGS,
)
def connections_python_save(a: dict[str, Any]) -> Any:
    body = _python_body(a, a["name"])
    if a.get("test"):
        return api.call("POST", "/connections/test", body)
    if a.get("previous"):
        return api.call("PUT", f"/connections/{_q(a['previous'])}", body)
    return api.call("POST", "/connections", body)


@command(
    "connections_python_tables",
    "Run a Python connection's List the tables now: its tables and their columns (its catalog loads too)",
    req("name", "The connection's name."),
)
def connections_python_tables(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/{_q(a['name'])}/tables", {})


# ----- Add API: an OpenAPI document or a form, made into API_<name>.py and a Python connection -----
@command(
    "connections_api_choices",
    "Add API's auth types with their settings, and its presets (Azure Function App, AWS Lambda, Google)",
)
def connections_api_choices(a: dict[str, Any]) -> Any:
    return api.call("GET", "/apis/choices")


_API_KEYS = ("spec_url", "spec_path", "spec", "form", "name", "base_url", "auth", "folder")


@command(
    "connections_api_add",
    "Add API: write API_<name>.py (one method per operation) and save its Python connection; "
    "preview=true writes nothing (operations, variables, what changes); try_it=<operation> reads its first "
    "rows before Add (nothing written)",
    opt("preview", "Only say what it would do.", "bool"),
    opt("try_it", "An operation's name (list_orders): its first rows, written nowhere."),
    opt("values", '{"NAME": "value"} for that try only (else this computer\'s environment).', "json"),
    opt("spec_url", "The OpenAPI document's address (2.0 or 3.x)."),
    opt("spec_path", "Its file."),
    opt("spec", "Its text."),
    opt(
        "form",
        'Instead: {"base_url", "endpoints": [{"method", "path", "parameters": "status, id*", "table": true}]}.',
        "json",
    ),
    opt("name", "Default: the document's title."),
    opt("base_url", "Over the document's."),
    opt("auth", '{"type": "api_key", "in": "header", "name": "x-functions-key"}.', "json"),
    opt("folder", "The project's (beside data.py); default: the Workbench's."),
    opt("variables", "Sources, as connections_python_save.", "json"),
    opt("secrets", '{"NAME": "value"}: keyring values.', "json"),
    opt("row_limit", "Rows to open.", "int"),
)
def connections_api_add(a: dict[str, Any]) -> Any:
    if a.get("try_it"):
        body = {k: a[k] for k in (*_API_KEYS, "values") if a.get(k) is not None}
        return api.call("POST", "/apis/try", body | {"try": a["try_it"]})
    keys = _API_KEYS if a.get("preview") else (*_API_KEYS, "variables", "secrets", "row_limit")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", "/apis/preview" if a.get("preview") else "/apis", body)


@command("connections_vaults", "The vault blades a password can come from, with their entries (names only)")
def connections_vaults(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections/vaults")


_TABLE_ARGS = (
    req("name", "The connection's name."),
    opt("table", "The table (a database's table; a workbook's sheet; a file in a folder connection)."),
    opt("schema", "The table's schema (as the catalog shows it); a Power BI workspace's: the dataset."),
    opt("database", "The table's database, when the catalog spans more than one."),
    opt("dataset", "A Power BI workspace's dataset holding the table (the same as schema)."),
)


@command(
    "connections_open_table",
    "Open a connection's table on the Tables page: a database table's first rows (the connection's Rows to open, "
    "10,000 unless set; all=true for every row), the table told how many the source holds; a file "
    "connection's file whole; a Python connection's by its Read a table. A workbook with several sheets "
    "and no table named answers its sheets.",
    *_TABLE_ARGS,
    opt("all", "Every row, not the first Rows to open.", "bool"),
)
def connections_open_table(a: dict[str, Any]) -> Any:
    keys = ("table", "schema", "database", "dataset", "all")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", f"/connections/{_q(a['name'])}/open", body)


@command(
    "connections_write",
    "Write rows to a connection's table through the adapter (sab.write): insert, update, merge, delete (by "
    "key) or truncate. dry_run=true counts and writes nothing; a write waits for the user's Allow.",
    req("name", "The connection's name."),
    req("table", "The table to write (schema.table; a file connection's file, orders.parquet)."),
    opt("rows", "The rows: a list of records.", "json"),
    opt("from_table", "Or an open table's name: its rows as shown."),
    opt("mode", "insert (default), update, merge, delete or truncate."),
    opt("key", "The key column(s) a row is matched by (update, merge, delete).", "list"),
    opt("dry_run", "Count only; nothing written.", "bool"),
)
def connections_write(a: dict[str, Any]) -> Any:
    keys = ("table", "rows", "from_table", "mode", "key", "dry_run")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", f"/connections/{_q(a['name'])}/write", body)


@command(
    "connections_tables",
    "A connection's tables as the Connections page's tree: its datasets (Power BI) or schemas, each table "
    "with its name for DuckDB SQL ([Finance Captive].Sales). Loads the catalog first when needed.",
    req("name", "The connection's name."),
)
def connections_tables(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/connections/{_q(a['name'])}/tree")


@command(
    "connections_open_dataset",
    "Open every table of one dataset (Power BI) or schema of a connection, each in its own tab",
    req("name", "The connection's name."),
    req("dataset", "The dataset or schema."),
)
def connections_open_dataset(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/{_q(a['name'])}/open-dataset", {"dataset": a["dataset"]})


@command(
    "connections_dataverse_sql_endpoint",
    "Move a Dataverse connection saved for its Web API to its SQL endpoint: its tables listed and read there",
    req("name", "The Dataverse connection's name."),
)
def connections_dataverse_sql_endpoint(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/{_q(a['name'])}/sql-endpoint")


@command(
    "connections_update_driver",
    "Update a SQL Server or Azure SQL connection from the app's earlier pyodbc code to mssql-python (no ODBC "
    "driver), its settings kept; the user's own code is never rewritten",
    req("name", "The connection's name (its card says update_driver)."),
)
def connections_update_driver(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/{_q(a['name'])}/update-driver")


@command(
    "connections_sql_reads",
    "The connections' tables DuckDB SQL read this session: connection, table, rows, when read",
)
def connections_sql_reads(a: dict[str, Any]) -> Any:
    return api.call("GET", "/connections/sql/reads")


@command(
    "connections_sql_refresh",
    "Drop this session's reads of connections' tables (one connection's, or all): the next query reads again",
    opt("connection", "Only this connection's reads."),
)
def connections_sql_refresh(a: dict[str, Any]) -> Any:
    body = {"connection": a["connection"]} if a.get("connection") else {}
    return api.call("POST", "/connections/sql/refresh", body)


@command(
    "connections_preview_table",
    "A connection's table's first 50 rows (nothing is kept)",
    *_TABLE_ARGS,
)
def connections_preview_table(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("table", "schema", "database", "dataset") if a.get(k) is not None}
    return api.call("POST", f"/connections/{_q(a['name'])}/preview", body)


@command(
    "connections_datasets",
    "A Power BI workspace connection's datasets (semantic models), asked of Power BI: each one's name, "
    "id, and its name for a DAX cell (`Finance/Sales model`). Its tables: catalog_tables with the dataset "
    "as the schema. To run DAX on one: workbench_run with kind dax and that name as the connection, or "
    'sab.dax("Finance/Sales model", "EVALUATE ...").',
    req("name", "The Power BI workspace connection's name."),
)
def connections_datasets(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/connections/{_q(a['name'])}/datasets?live=1")


@command(
    "connections_import_relationships",
    "Import one Power BI dataset's own relationships, or a SQL Server / Azure SQL database's foreign keys "
    "(composite keys whole), into the current relationship model (merged: the source's wins for a join "
    "both name). Tables are named as they open on the Tables page; an inactive relationship (a disabled foreign key) "
    "stays inactive. Answers the model, what the merge changed, and what was imported.",
    req("name", "The Power BI workspace's or SQL Server connection's name."),
    opt(
        "dataset", "The dataset, by name or id (connections_datasets lists them); needed when it has several."
    ),
)
def connections_import_relationships(a: dict[str, Any]) -> Any:
    body = {"dataset": a["dataset"]} if a.get("dataset") else {}
    return api.call("POST", f"/connections/{_q(a['name'])}/relationships", body)


@command(
    "connections_load_catalog",
    "Load a connection's catalog (its tables and columns) in the background now; it arrives for completion "
    "and catalog_* tools. Catalogs also load themselves when a connection is saved and when the app starts.",
    req("name", "The connection's name."),
)
def connections_load_catalog(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/connections/{_q(a['name'])}/catalog")


@command(
    "connections_vault_secrets",
    "The secrets' names in a key vault, each with a variable name to map it to (names only, no value)",
    opt("name", "A saved vault's name."),
    opt("code", "Or a vault not saved yet: its code (a vault type's from connections_types, filled in)."),
    opt("template", "With code: its type."),
    opt("variable", "With code: the function that reads a secret (the type's: get)."),
    opt(
        "secrets", '{"name": "value"}: passwords the vault\'s own code asks for, for this read only.', "json"
    ),
)
def connections_vault_secrets(a: dict[str, Any]) -> Any:
    keys = ("name", "code", "template", "variable", "secrets")
    body = {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", "/connections/vaults/secrets", body)


@command(
    "connections_password_source",
    "Point a password at the keyring, an environment variable, or a key vault's entry; the code it gives",
    req("code", "The connection's code."),
    req("secret", 'The password\'s name in the code (secret("...")).'),
    req("source", "keyring, env or vault."),
    opt("env", "env: the variable's name; vault: an existing entry's variable."),
    opt("vault", "vault: the vault blade."),
    opt("vault_secret", "vault, a new entry: the secret's name in the vault."),
    opt("connection", "The connection's name (names a new vault entry's variable)."),
)
def connections_password_source(a: dict[str, Any]) -> Any:
    body = {"code": a["code"], "secret": a["secret"], "from": a["source"]}
    body |= {k: a[k] for k in ("env", "vault", "vault_secret", "connection") if a.get(k)}
    return api.call("POST", "/connections/source", body)
