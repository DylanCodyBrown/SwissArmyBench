"""The agent's catalog_* commands: catalog explorer: a source database's tables and columns.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import _q, command, opt, req

CATALOG_NOTE = (
    "Names and types the user loaded from a source database (a blade's Refresh or sab.load), to write SQL "
    "against that source. Never values."
)


@command("catalog_list", "Every loaded catalog: name, SQL dialect, and its schema, table and column counts.")
def catalog_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/catalogs")


@command(
    "catalog_schemas",
    "A catalog's schemas, with how many tables and views each holds. " + CATALOG_NOTE,
    req("catalog", "Catalog name (catalog_list)."),
    values=True,
)
def catalog_schemas(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/catalogs/{_q(a['catalog'])}/schemas")


@command(
    "catalog_tables",
    "The tables and views in one schema of a catalog, with column counts, paged.",
    req("catalog", "Catalog name."),
    req("schema", "Schema name; empty text for a source without schemas."),
    opt("database", "Database, when the catalog spans more than one."),
    opt("offset", "Skip this many tables (paging).", "int"),
    opt("limit", "At most this many tables (default 1000, at most 5000).", "int"),
    values=True,
)
def catalog_tables(a: dict[str, Any]) -> Any:
    return api.call(
        "GET",
        f"/catalogs/{_q(a['catalog'])}/tables",
        params={
            "schema": a["schema"],
            "database": a.get("database"),
            "offset": a.get("offset"),
            "limit": a.get("limit"),
        },
    )


@command(
    "catalog_columns",
    "A table's columns and types in the source, with a first SELECT quoted for the source's SQL dialect.",
    req("catalog", "Catalog name."),
    req("schema", "Schema name; empty text for none."),
    req("table", "Table or view name."),
    opt("database", "Database, when the catalog spans more than one."),
    values=True,
)
def catalog_columns(a: dict[str, Any]) -> Any:
    return api.call(
        "GET",
        f"/catalogs/{_q(a['catalog'])}/columns",
        params={"schema": a["schema"], "table": a["table"], "database": a.get("database")},
    )


@command(
    "catalog_search",
    "Find tables and columns by name. Every word must appear in schema.table.column; `a.b` means "
    "schema.table or table.column. Exact names first, then names that start with the text.",
    req("catalog", "Catalog name."),
    req("text", "What to look for, such as `customer id` or `sales.orders`."),
    opt("limit", "At most this many tables and this many columns (default 50).", "int"),
    values=True,
)
def catalog_search(a: dict[str, Any]) -> Any:
    return api.call(
        "GET", f"/catalogs/{_q(a['catalog'])}/search", params={"q": a["text"], "limit": a.get("limit")}
    )


@command(
    "catalog_shared",
    "The shared catalog (the library's catalog/): each connection's tables, their state and the projects using them",
    opt("search", "Words in a connection's or table's name."),
)
def catalog_shared(a: dict[str, Any]) -> Any:
    query = f"?search={quote(str(a['search']))}" if a.get("search") else ""
    return api.call("GET", "/shared-catalog" + query)


@command(
    "catalog_shared_table",
    "One table of the shared catalog: its columns and types, primary key, relationships, used_by",
    req("connection", "The connection's name."),
    req("table", "The table's key (main.orders) or name."),
)
def catalog_shared_table(a: dict[str, Any]) -> Any:
    query = f"connection={quote(str(a['connection']))}&table={quote(str(a['table']))}"
    return api.call("GET", f"/shared-catalog/table?{query}")


@command(
    "catalog_shared_refresh",
    "Read the library's catalog/ folder again now (what the user's git pull brought); the app never runs git",
)
def catalog_shared_refresh(a: dict[str, Any]) -> Any:
    return api.call("POST", "/shared-catalog/refresh")


@command(
    "catalog_load",
    "Load a source's names and types as a catalog: one row per column (schema, table, column, type)",
    req("name", "The catalog's name."),
    req("columns", "The rows' column names, as TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE.", "list"),
    req("rows", "The rows: one list of values per source column.", "json"),
    opt("dialect", "sqlserver, postgres, mysql, sqlite, duckdb, snowflake, oracle, trino or other."),
)
def catalog_load(a: dict[str, Any]) -> Any:
    return api.call(
        "PUT",
        f"/catalogs/{_q(a['name'])}",
        {"columns": a["columns"], "data": a["rows"]},
        params={"dialect": a.get("dialect")},
    )


@command("catalog_remove", "Remove a loaded catalog", req("name", "The catalog."))
def catalog_remove(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/catalogs/{_q(a['name'])}")
