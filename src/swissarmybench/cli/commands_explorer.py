"""The agent's explorer_* commands: data Explorer: one search over connections, catalogs, open tables, variables, blades.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req

SANDBOX_SORT = "The Sandbox section's order, as the Catalog's Sort: name, rows, source, created, changed."


@command(
    "explorer_search",
    "The Data Explorer: find data by name in connections (their loaded catalogs' tables and columns, with "
    "DuckDB SQL names), open tables, variables, blades. Any case, by parts (cust: customer_id). Names and "
    "types only; offers: catalogs not loaded (connections_load_catalog)",
    opt("text", "What to look for: `cust`, `orders customer`."),
    opt("kinds", "Only these: connections, tables, columns, structures, apis, variables, blades.", "list"),
    opt("connection", "Only what belongs to this connection."),
    opt("column", "A column's exact name: every table that has it, in every connection (for joins)."),
    opt("limit", "Results per group (default 25).", "int"),
    opt("sort", SANDBOX_SORT),
    opt("order", "asc or desc (with sort)."),
)
def explorer_search(a: dict[str, Any]) -> Any:
    kinds = a.get("kinds")
    params = {
        "q": a.get("text") or "",
        "kinds": ",".join(str(k) for k in kinds) if isinstance(kinds, list) else kinds,
        "connection": a.get("connection"),
        "column": a.get("column"),
        "limit": a.get("limit"),
        "sort": a.get("sort"),
        "order": a.get("order"),
    }
    return api.call(
        "GET", "/explorer/search", params={k: v for k, v in params.items() if v not in (None, "")}
    )


@command(
    "explorer_browse",
    "The Data page with nothing typed (the one place to browse tables): every connection with its status "
    "(its catalog: loaded, loading, none: connections_load_catalog) and its tables by database and schema "
    "(a Power BI workspace's datasets), each with its DuckDB SQL name; then the open tables with their "
    "columns, Structures' documents and paths, APIs' table-returning calls and the blades whose result is "
    "a table. Names only; a table's columns: explorer_table",
    opt("kinds", "Only these parts: connections, tables, columns, structures, apis, blades.", "list"),
    opt("connection", "Only this connection (and what belongs to it)."),
    opt("sort", SANDBOX_SORT),
    opt("order", "asc or desc (with sort)."),
)
def explorer_browse(a: dict[str, Any]) -> Any:
    kinds = a.get("kinds")
    params = {
        "kinds": ",".join(str(k) for k in kinds) if isinstance(kinds, list) else kinds,
        "connection": a.get("connection"),
        "sort": a.get("sort"),
        "order": a.get("order"),
    }
    return api.call(
        "GET", "/explorer/browse", params={k: v for k, v in params.items() if v not in (None, "")}
    )


@command(
    "explorer_table",
    "A connection's table as the Data page's detail side shows it: its columns (name, type, nulls), where "
    "it comes from, its DuckDB SQL name, the code that reads it (a %%sql cell's, a Python cell's) and "
    "whether its relationships import (connections_import_relationships). Its catalog must be loaded.",
    req("connection", "The connection's name."),
    req("table", "The table's name."),
    opt("schema", "Its schema (a Power BI workspace's dataset), as explorer_browse names it."),
    opt("database", "Its database, when the connection has several."),
)
def explorer_table(a: dict[str, Any]) -> Any:
    params = {k: a.get(k) for k in ("connection", "database", "schema", "table")}
    return api.call("GET", "/explorer/table", params={k: v for k, v in params.items() if v not in (None, "")})
