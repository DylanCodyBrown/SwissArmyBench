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

SEAM (trees-apis): `register("structures", ...)` and `register("apis", ...)`: a Structures document's
names and paths, an API's web calls that return a table and their columns, once that branch merges.
Names only: no provider answers a value, a row or a secret.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as table_rules
from swissarmybench.domain import explorer as rules
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


class Explorer:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._providers: dict[str, Provider] = {}

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
            if query.empty:
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
                    more={"blade_kind": b.get("kind")},
                )
            )
        return found

    return provide
