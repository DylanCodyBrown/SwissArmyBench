"""Where the project's sandbox gets a table from, in the app (services/sandbox_sources.py AppSources), with
stand-ins for the app's services: the rules that were the composition root's closures. Made-up names only."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.sandbox_sources import AppSources


class Origins:
    def get(self, name: str) -> Origin:
        return Origin("connection", connection="Warehouse") if name == "orders" else Origin("file")


class Datasets:
    def __init__(self) -> None:
        self.origins = Origins()
        self.stored: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def read_file(self, path: str, sheet: str | None) -> Any:
        return ("file", path, sheet)

    async def store_table(
        self,
        name: str,
        table: Any,
        source_kind: str,
        new_grid: bool,
        who: str,
        *,
        follow: bool = False,
        origin: Origin | None = None,
    ) -> dict[str, Any]:
        self.stored.append(((name, table, source_kind, new_grid, who), {"follow": follow, "origin": origin}))
        return {"grid": "g1"}


class Connections:
    def listing(self) -> dict[str, Any]:
        return {"connections": [{"name": "warehouse"}, {"name": "Team vault"}, {"name": "Archive"}]}

    def blade(self, name: str) -> tuple[Blade, str]:
        if name.casefold() not in ("warehouse", "archive"):
            raise LookupError(name)
        return Blade(name, "sql", dialect="postgres", template="postgres"), "database"


class Tables:
    def kind(self, name: str) -> tuple[str, str]:
        if name == "Team vault":
            raise ValueError("A key vault has no tables.")
        return name.title(), "database"

    async def read(self, name: str, place: Place) -> tuple[Any, bool]:
        return SimpleNamespace(read=SimpleNamespace(table=("rows of", name, place.table))), False


def sources(datasets: Datasets | None = None, catalog: Any = None) -> AppSources:
    async def view(name: str) -> bytes:
        return name.encode()

    async def structure_table(structure: str, path: str) -> tuple[Any, str, str]:
        return "records", structure, path

    async def view_rows(name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]:
        return ["id"], [[r] for r in rows]

    def no_catalog(connection: str, name: str) -> dict[str, Any]:
        raise LookupError(name)

    return AppSources(
        datasets or Datasets(),
        Connections(),
        Tables(),
        view=view,
        to_table=lambda body: ("table", body),
        structure_table=structure_table,
        view_rows=view_rows,
        catalog_table=catalog or no_catalog,
    )


def test_a_table_is_mocked_as_the_client_of_the_connection_it_came_from() -> None:
    made = sources()
    database = {"kind": "database", "connection": "Warehouse", "template": "postgres", "dialect": "postgres"}
    assert made.client_of("orders", None) == database  # an open table: its origin's connection
    assert made.client_of(None, "warehouse") == database  # a connection named: as it is saved
    assert made.client_of("pasted", None) == {"kind": "duckdb"}  # no connection: plain DuckDB
    assert made.client_of(None, None) == {"kind": "duckdb"}
    # A connection that is gone, or one with no tables: plain, still naming it.
    assert made.client_of(None, "Gone") == {"kind": "duckdb", "connection": "Gone"}
    assert made.client_of(None, "Team vault") == {"kind": "duckdb", "connection": "Team vault"}


def test_mocked_as_offers_the_connections_that_have_tables_sorted_in_any_case() -> None:
    assert sources().connections() == ["Archive", "warehouse"]


def test_a_sandbox_table_is_shown_as_a_grid_with_the_sandbox_as_its_origin() -> None:
    datasets = Datasets()
    words = "orders · sandbox: A sandbox variant of orders"
    answer = asyncio.run(sources(datasets).show("sandbox_orders", "rows", True, words))
    assert answer == {"grid": "g1"}
    (args, more) = datasets.stored[0]
    assert args == ("sandbox_orders", "rows", "sandbox", False, "user") and more["follow"] is True
    origin = more["origin"]
    assert (origin.kind, origin.connection, origin.filename) == ("sandbox", "Sandbox", words)
    assert origin.sql == "SELECT * FROM [Sandbox].orders"


def test_a_key_is_looked_up_by_schema_and_table_then_by_the_table_alone() -> None:
    asked: list[tuple[str, str]] = []

    def catalog(connection: str, name: str) -> dict[str, Any]:
        asked.append((connection, name))
        if name == "orders":
            return {"primary_key": ["order_id", 7]}
        raise LookupError(name)

    made = sources(catalog=catalog)
    assert made.key_of("Warehouse", Place("", "dbo", "orders")) == ["order_id", "7"]
    assert asked == [("Warehouse", "dbo.orders"), ("Warehouse", "orders")]
    assert made.key_of("Warehouse", Place("", "", "customers")) == []  # not known: no key
    assert sources(catalog=lambda c, n: {}).key_of("Warehouse", Place("", "", "orders")) == []


def test_the_reads_go_to_the_services_they_come_from() -> None:
    async def scenario() -> None:
        made = sources()
        assert await made.grid_view("orders") == ("table", b"orders")
        assert await made.connection_table("Warehouse", Place("", "dbo", "orders")) == (
            "rows of",
            "Warehouse",
            "orders",
        )
        assert await made.file_table("/made-up/orders.csv", None) == ("file", "/made-up/orders.csv", None)
        assert await made.structure_table("s1", "$.orders") == ("records", "s1", "$.orders")
        assert await made.view_rows("orders", [0, 2]) == (["id"], [[0], [2]])

    asyncio.run(scenario())
