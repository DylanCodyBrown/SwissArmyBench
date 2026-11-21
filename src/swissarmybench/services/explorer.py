"""The Data Explorer's search (domain/explorer.py): one search over everything that holds data, for the
Workbench's pane, the grid page's Find data dialog and the agent (explorer_search) alike.

Each source is a provider: an async function given the search, answering its results (and the
connections it offers to load). The built-in ones:

  connections   the library's connections (never a key vault: it has no tables), by name and type; their
                tables and columns from the loaded catalogs (the catalog's own search), each table with its
                name in DuckDB SQL; a connection whose catalog is not loaded is offered (Load its catalog)
  grids         the open tables and their columns (types), with where each came from
  variables     this computer's variables by name, with their source (never a value)
  blades        the blades that are not connections, by name, with their call

  structures    Structures: the open documents and saved files by name, an open one's keys by their paths
  apis          an API's web calls with Return as table on, by their DuckDB SQL names, and their columns

Another source joins with `register(name, provider)`; a provider that fails is skipped.
Names only: no provider answers a value, a row or a secret.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as table_rules
from swissarmybench.domain import explorer as rules
from swissarmybench.domain import web_calls
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.explorer import Query, Result
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.workspace import Workspace

CATALOG_ROWS: int = 500  # tables and columns asked of each catalog (the catalog's own most)


@dataclass
class Found:
    results: list[Result] = field(default_factory=list)
    offers: list[dict[str, Any]] = field(default_factory=list)


Provider = Callable[[Query], Awaitable[Found]]


class CatalogSearch(Protocol):
    """The loaded catalogs (services/catalogs.py)."""

    def loaded_names(self) -> set[str]: ...

    def listing(self) -> dict[str, Any]: ...

    async def search(self, name: str, text: str, limit: int) -> dict[str, Any]: ...

    async def shared_tables(self, name: str) -> set[str]: ...


@dataclass
class BrowseSources:
    """What the Data page's browse reads besides the providers: the connections (the Connections page's
    listing), a connection's tree (services/connection_tables.py, never loading it: Load does), and a
    catalog table's columns with its DuckDB SQL name."""

    connections: Callable[[], list[dict[str, Any]]]
    tree: Callable[[str], Awaitable[dict[str, Any]]]
    describe: Callable[[str, Place], Awaitable[dict[str, Any]]]


class Explorer:
    def __init__(self, ws: Workspace, sources: BrowseSources | None = None) -> None:
        self.ws = ws
        self._providers: dict[str, Provider] = {}
        self.sources = sources

    async def browse(self, params: Any) -> dict[str, Any]:
        """The Data page with nothing typed: every connection (its status, its tables in its tree's groups),
        then the open tables, Structures, the APIs' tables and the blades whose result is a table, each with
        its children. {"kinds", "connection"} as the search's. Names only."""
        given = params if isinstance(params, dict) else {}
        query = rules.browse_query(given.get("kinds"), given.get("connection"))
        connections: list[dict[str, Any]] = []
        if self.sources is not None and rules.shows("connections", query):
            listed = [c for c in self.sources.connections() if c.get("tables_kind")]  # never a key vault
            if query.connection is not None:
                listed = [c for c in listed if rules.same_name(str(c["name"]), query.connection)]
            trees = await asyncio.gather(
                *(self.sources.tree(str(c["name"])) for c in listed), return_exceptions=True
            )
            for c, tree in zip(listed, trees, strict=True):
                if isinstance(tree, BaseException):
                    connections.append(rules.connection_node(c, None, str(tree) or type(tree).__name__))
                else:
                    connections.append(rules.connection_node(c, tree))
        sections = [p for p in self._providers if p != "connections"]
        answers = await asyncio.gather(*(self._providers[p](query) for p in sections), return_exceptions=True)
        results = [r for a in answers if not isinstance(a, BaseException) for r in a.results]
        return {
            "query": {"kinds": [k for k in rules.KINDS if k in query.kinds], "connection": query.connection},
            "connections": connections,
            "sections": rules.browse_sections(results, query),
        }

    async def table(self, params: Any) -> dict[str, Any]:
        """A connection's table for the detail side: its columns (name, type, nulls), where it comes from,
        its DuckDB SQL name, and the code that reads it (a SQL cell's and a Python cell's)."""
        given = params if isinstance(params, dict) else {}
        connection = str(given.get("connection") or "").strip()
        table = str(given.get("table") or "").strip()
        if not connection or not table:
            raise ValueError(
                "Name the connection and the table (and its schema, and database if it has one)."
            )
        if self.sources is None:
            raise LookupError("The Data page's tables are not in this build.")
        place = Place(str(given.get("database") or ""), str(given.get("schema") or ""), table)
        described = await self.sources.describe(connection, place)
        sql = str(described["sql"])
        saved = str(described.get("connection", connection))
        listed = next((c for c in self.sources.connections() if rules.same_name(str(c["name"]), saved)), {})
        return {
            "connection": saved,
            "place": place.to_json(),
            "where": [p for p in (saved, place.database, place.schema) if p],
            "sql": sql,
            "columns": described.get("columns", []),
            "code": rules.table_code(sql),
            "insert": rules.table_insert(sql),
            "relationships": rules.imports_relationships(listed.get("tables_kind"), listed.get("dialect")),
        }

    def register(self, name: str, provider: Provider) -> None:
        """A source of results (a later one under the same name replaces it)."""
        self._providers[name] = provider

    def providers(self) -> list[str]:
        return list(self._providers)

    async def search(self, params: Any) -> dict[str, Any]:
        """{"q", "kinds", "connection", "column", "limit"}: the results grouped and counted."""
        given = params if isinstance(params, dict) else {}
        query = rules.parse(
            given.get("q", given.get("text", "")),
            given.get("kinds"),
            given.get("connection"),
            given.get("column"),
            given.get("limit"),
        )
        answers = await asyncio.gather(
            *(provider(query) for provider in self._providers.values()), return_exceptions=True
        )
        results: list[Result] = []
        offers: list[dict[str, Any]] = []
        for answer in answers:
            if isinstance(answer, BaseException):
                continue  # one source failing leaves the others' results
            results += answer.results
            offers += answer.offers
        if query.connection is not None:
            offers = [o for o in offers if rules.same_name(str(o["connection"]), query.connection)]
        return rules.grouped(rules.ranked(results, query), query, offers)


# ===== the built-in providers =====


def connections_provider(
    listing: Callable[[], list[dict[str, Any]]],
    catalogs: CatalogSearch,
    catalog_state: Callable[[str], dict[str, str] | None],
) -> Provider:
    """The library's connections, and their loaded catalogs' tables and columns."""

    async def provide(query: Query) -> Found:
        found = Found()
        loaded = catalogs.loaded_names()
        named: set[str] = set()
        wants_names = query.wants("tables") or query.wants("columns")
        for c in listing():
            name = str(c["name"])
            kind = c.get("tables_kind")
            if not kind:
                continue  # a key vault: no tables, so not a connection here
            named.add(name.casefold())
            words = str(c.get("type") or c.get("connection") or "")
            found.results.append(
                Result(
                    "connections",
                    name,
                    connection=name,
                    detail=words,
                    icon="sql",
                    more={"tables_kind": kind, "loaded": name.casefold() in loaded},
                )
            )
            if not wants_names or query.empty:
                continue
            if name.casefold() in loaded:
                found.results += await _catalog_results(catalogs, name, name, str(kind), query)
            elif c.get("has_catalog"):
                state = catalog_state(name) or {"state": "none"}
                found.offers.append({"connection": name, **state})
        # Catalogs loaded with sab.load (no connection of that name): their tables are named as they are.
        if wants_names and not query.empty:
            for info in catalogs.listing()["catalogs"]:
                if str(info["name"]).casefold() not in named:
                    found.results += await _catalog_results(catalogs, str(info["name"]), None, None, query)
        return found

    return provide


async def _catalog_results(
    catalogs: CatalogSearch, catalog: str, connection: str | None, kind: str | None, query: Query
) -> list[Result]:
    text = query.column if query.column is not None else " ".join(query.words)
    hits = await catalogs.search(catalog, text, CATALOG_ROWS)
    shared = await catalogs.shared_tables(catalog) if connection else set()
    out: list[Result] = []

    def sql_of(place: Place) -> str:
        if connection and kind:
            return table_rules.copy_name(connection, place, kind, shared)
        return ".".join(rules.sql_identifier(p) for p in (place.schema, place.table) if p)

    def where(place: Place) -> list[str]:
        return [p for p in (connection or catalog, place.database, place.schema) if p]

    if query.column is None:
        for t in hits["tables"]:
            place = Place(t.get("database") or "", t.get("schema") or "", t["table"])
            sql = sql_of(place)
            out.append(
                Result(
                    "tables",
                    place.table,
                    where(place),
                    connection=connection,
                    sql=sql,
                    detail=f"{t.get('columns', 0)} columns" + (" · view" if t.get("kind") == "view" else ""),
                    icon="rows",
                    insert=rules.table_insert(sql),
                    more={"place": place.to_json(), "catalog": catalog, "source": "catalog"},
                )
            )
    for col in hits["columns"]:
        place = Place(col.get("database") or "", col.get("schema") or "", col["table"])
        sql = sql_of(place)
        out.append(
            Result(
                "columns",
                col["column"],
                [*where(place), place.table],
                connection=connection,
                sql=sql,
                type=col.get("type"),
                icon="columns",
                insert=rules.column_insert(col["column"]),
                more={
                    "place": place.to_json(),
                    "catalog": catalog,
                    "source": "catalog",
                    "table": place.table,
                },
            )
        )
    return out


@dataclass
class OpenTable:
    """An open table as the grids provider reads it."""

    name: str
    rows: int
    columns: list[tuple[str, str]]  # (name, type)
    grid: str | None
    origin: Origin


def shared_catalog_provider(
    tables: Callable[[], Any], loaded: Callable[[], set[str]], connections: Callable[[], set[str]]
) -> Provider:
    """The shared catalog's tables and columns (the library's catalog/, services/shared_catalog.py) of the
    connections whose catalog is not loaded here: a teammate's tables found before anything is loaded. A
    connection this computer does not have is "From the shared catalog: not connected here"; one it has
    (its connection file came with the library) offers Set up this connection."""

    async def provide(query: Query) -> Found:
        found = Found()
        if not (query.wants("tables") or query.wants("columns")) or (query.empty and not query.browse):
            return found
        done, here = loaded(), connections()
        for catalog, table in tables():
            name = catalog.connection
            if name.casefold() in done:
                continue  # its own catalog is loaded: the connections provider has it
            has = name.casefold() in here
            detail = "From the shared catalog" + ("" if has else ": not connected here")
            more = {
                "source": "shared",
                "shared": True,
                "here": has,
                "setup": has,
                "key": f"{name}/{table.key}",
                "place": {"database": table.database, "schema": table.schema, "table": table.name},
                "used_by": list(table.used_by),
            }
            where = [p for p in (name, table.database, table.schema) if p]
            sql = table_rules.copy_name(
                name, Place(table.database, table.schema, table.name), catalog.kind or "database"
            )
            found.results.append(
                Result(
                    "tables",
                    table.name,
                    where,
                    connection=name,
                    sql=sql,
                    detail=f"{len(table.columns)} columns · {detail}",
                    icon="rows",
                    insert=rules.table_insert(sql),
                    more=more,
                )
            )
            for column in table.columns:
                found.results.append(
                    Result(
                        "columns",
                        column.name,
                        [*where, table.name],
                        connection=name,
                        sql=sql,
                        type=column.type,
                        icon="columns",
                        insert=rules.column_insert(column.name),
                        more=more | {"table": f"{name}/{table.key}"},
                    )
                )
        return found

    return provide


def sandbox_provider(
    tables: Callable[[], Awaitable[list[tuple[str, int, list[tuple[str, str]]]]]],
) -> Provider:
    """The open project's sandbox: its tables ([Sandbox].orders in DuckDB SQL) and their columns."""

    async def provide(query: Query) -> Found:
        found = Found()
        for name, rows, columns in await tables():
            sql = f"[Sandbox].{name}"
            more = {"source": "sandbox", "table": name, "rows": rows}
            found.results.append(
                Result(
                    "tables",
                    name,
                    ["Sandbox"],
                    connection="Sandbox",
                    sql=sql,
                    detail=f"{rows:,} rows",
                    icon="rows",
                    insert=rules.table_insert(sql),
                    more=more,
                )
            )
            if query.empty and not query.browse:
                continue
            for column, typed in columns:
                found.results.append(
                    Result(
                        "columns",
                        column,
                        ["Sandbox", name],
                        connection="Sandbox",
                        sql=sql,
                        type=typed,
                        icon="columns",
                        insert=rules.column_insert(column),
                        more=more,
                    )
                )
        return found

    return provide


def grids_provider(tables: Callable[[], list[OpenTable]]) -> Provider:
    """The open tables (grids) and their columns."""

    async def provide(query: Query) -> Found:
        found = Found()
        for t in tables():
            variable = variable_name(t.name)
            connection = t.origin.connection if t.origin.kind == "connection" else None
            source = t.origin.label()
            more = {
                "source": "grid",
                "grid": t.grid,
                "dataset": t.name,
                "variable": variable,
                "origin": t.origin.kind,
                "from": source,
                "rows": t.rows,
            }
            words = f"{t.rows:,} rows" + (f" · {source}" if source else "")
            found.results.append(
                Result(
                    "tables",
                    t.name,
                    ["Open tables"],
                    connection=connection,
                    detail=words,
                    icon="grid",
                    insert=rules.grid_insert(variable),
                    more=more,
                )
            )
            if query.empty and not query.browse:
                continue
            for column, typed in t.columns:
                found.results.append(
                    Result(
                        "columns",
                        column,
                        ["Open tables", t.name],
                        connection=connection,
                        type=typed,
                        icon="columns",
                        insert=rules.column_insert(column, variable),
                        more=more | {"table": t.name},
                    )
                )
        return found

    return provide


def variables_provider(listing: Callable[[], list[dict[str, Any]]]) -> Provider:
    """This computer's variables: names and sources (a value never leaves the Variables page)."""

    async def provide(query: Query) -> Found:
        found = Found()
        for v in listing():
            found.results.append(
                Result(
                    "variables",
                    str(v["name"]),
                    detail=str(v.get("words") or v.get("from") or ""),
                    icon="key",
                    insert=rules.variable_insert(str(v["name"])),
                    more={"from": v.get("from"), "uses": len(v.get("uses") or [])},
                )
            )
        return found

    return provide


def blades_provider(listing: Callable[[], list[dict[str, Any]]]) -> Provider:
    """The blades that are not connections, each with its call."""

    async def provide(query: Query) -> Found:
        found = Found()
        for b in listing():
            if b.get("connection") or b.get("kind") == "snippet":
                continue  # connections are the connections' group; a snippet is a cell's text
            name = str(b["name"])
            signature = b.get("signature") if isinstance(b.get("signature"), str) else None
            found.results.append(
                Result(
                    "blades",
                    name,
                    detail=str(b.get("description") or b.get("kind") or ""),
                    icon="bolt",
                    insert=rules.blade_insert(name, b.get("variable"), str(b.get("kind")), signature),
                    more={
                        "blade_kind": b.get("kind"),
                        "table": b.get("table"),
                        "web_call": bool(b.get("web_call")),
                    },
                )
            )
            table = b.get("table") if b.get("names_table") else None
            if isinstance(table, str) and table:
                # Its table by its own name (domain/blade_tables.py): `sab.blade` makes it that variable.
                found.results.append(
                    Result(
                        "blades",
                        table,
                        path=[name],
                        detail=f"{name}'s table",
                        icon="rows",
                        sql=rules.sql_identifier(table),
                        insert=rules.blade_table_insert(name, str(b.get("variable") or ""), table),
                        more={"blade_kind": b.get("kind"), "blade": name},
                    )
                )
        return found

    return provide


def structures_provider(listing: Callable[[], dict[str, Any]], value_of: Callable[[str], Any]) -> Provider:
    """Structures: each open structure and saved structure file by name; an open one's keys by their paths
    (`$.orders[].customer.id`), each with the parts of a place that has it (Open at this node). A saved
    file that is not open is found by its name (its text is not read for a search)."""

    async def provide(query: Query) -> Found:
        found = Found()
        if not query.wants("structures"):
            return found
        listed = listing()
        open_files = {str(s.get("path") or "") for s in listed.get("open", [])}
        for s in listed.get("open", []):
            sid, name = str(s["id"]), str(s["name"])
            whole = {"structure": sid, "file": s.get("path"), "pointer": "$", "parts": []}
            found.results.append(
                Result("structures", name, detail=str(s.get("format") or "").upper(), icon="json", more=whole)
            )
            if (query.empty and not query.browse) or s.get("error"):
                continue
            try:
                value = value_of(sid)
            except Exception:  # noqa: S112 (a structure whose steps fail: its name only)
                continue
            for p in rules.structure_paths(value):
                parent = rules.parent_pointer(p.pointer)
                found.results.append(
                    Result(
                        "structures",
                        p.key,
                        [name, parent],
                        detail=p.type,
                        icon="json",
                        more={
                            "structure": sid,
                            "file": s.get("path"),
                            "pointer": p.pointer,
                            "parts": list(p.parts),
                        },
                    )
                )
        for f in listed.get("files", []):
            if f.get("open") or str(f.get("path") or "") in open_files:
                continue
            saved = {"structure": None, "file": f.get("path"), "pointer": "$", "parts": []}
            fmt = str(f.get("format") or "").upper()
            found.results.append(
                Result("structures", str(f["name"]), ["Saved"], detail=fmt, icon="json", more=saved)
            )
        return found

    return provide


def apis_provider(blades: Callable[[], list[dict[str, Any]]]) -> Provider:
    """APIs: their web calls with Return as table on (an API's tables: web_calls' one gate), each with its
    DuckDB SQL name (`[Orders API].listOrders`), and their columns."""

    async def provide(query: Query) -> Found:
        found = Found()
        for b in blades():
            if not web_calls.is_table(b):
                continue
            call = b.get("web_call") or {}
            api, operation = str(call.get("api") or ""), str(call.get("operation") or "")
            if not api or not operation:
                continue
            place = Place("", "", operation)
            sql = table_rules.copy_name(api, place, "api")
            more = {"source": "api", "api": api, "blade": b.get("name"), "place": place.to_json()}
            found.results.append(
                Result(
                    "apis",
                    operation,
                    [api],
                    connection=api,
                    sql=sql,
                    detail=f"{call.get('method', '')} {call.get('path', '')}".strip(),
                    icon="link",
                    insert=rules.table_insert(sql),
                    more=more,
                )
            )
            if query.empty and not query.browse:
                continue
            for column, typed in dict(call.get("columns") or {}).items():
                found.results.append(
                    Result(
                        "columns",
                        str(column),
                        [api, operation],
                        connection=api,
                        sql=sql,
                        type=str(typed) or None,
                        icon="columns",
                        insert=rules.column_insert(str(column)),
                        more=more | {"table": operation},
                    )
                )
        return found

    return provide
