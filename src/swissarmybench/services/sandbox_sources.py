"""Where the project's sandbox gets a table from, in the app (services/sandbox.py's Sources): an open grid's
view, a connection's table read once, a file, a structure's records; the grid a sandbox table is shown as; the
client a table's rows are mocked as; Mocked as's choices; a connection's table's key as the shared catalog
knows it. (The craft review, 2026-11-22: these were the composition root's own closures.)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import sandbox as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.table_cells import Origin


class Origins(Protocol):
    def get(self, name: str) -> Origin: ...


class Datasets(Protocol):
    """The open tables (services/datasets.py DatasetService)."""

    @property
    def origins(self) -> Origins: ...

    async def read_file(self, path: str, sheet: str | None) -> Any: ...

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
    ) -> dict[str, Any]: ...


class Connections(Protocol):
    """The saved connections (services/connections.py ConnectionService)."""

    def listing(self) -> dict[str, Any]: ...

    def blade(self, name: str) -> tuple[Blade, str]: ...


class ConnectionTables(Protocol):
    """What a connection's tables are (services/connection_tables.py)."""

    def kind(self, name: str) -> tuple[str, str]: ...

    async def read(self, name: str, place: Place) -> tuple[Any, bool]: ...


class AppSources:
    def __init__(
        self,
        datasets: Datasets,
        connections: Connections,
        connection_tables: ConnectionTables,
        *,
        view: Callable[[str], Awaitable[bytes]],
        to_table: Callable[[bytes], Any],
        structure_table: Callable[[str, str], Awaitable[tuple[Any, str, str]]],
        view_rows: Callable[[str, list[int]], Awaitable[tuple[list[str], list[list[Any] | None]]]],
        catalog_table: Callable[[str, str], Mapping[str, Any]],
    ) -> None:
        self._datasets = datasets
        self._connections = connections
        self._tables = connection_tables
        self._view = view  # an open table as its grid shows it: an Arrow IPC stream (services/table_cells.py)
        self._to_table = to_table  # that stream as a table (adapters/datasets.py)
        self._structure_table = structure_table  # services/structures.py records_table
        self._view_rows = view_rows  # services/grids.py view_rows
        self._catalog_table = catalog_table  # services/shared_catalog.py table

    async def grid_view(self, name: str) -> Any:
        return self._to_table(await self._view(name))

    async def connection_table(self, connection: str, place: Place) -> Any:
        kept, _ = await self._tables.read(connection, place)
        return kept.read.table

    async def file_table(self, path: str, sheet: str | None) -> Any:
        return await self._datasets.read_file(path, sheet)

    async def show(self, name: str, table: Any, follow: bool, words: str = "") -> dict[str, Any]:
        """A sandbox table as a grid. Its origin: the sandbox table (its lineage and its read-only cell's
        load name [Sandbox].<table>)."""
        table_name = name.removeprefix(rules.GRID_PREFIX)
        sql = f"SELECT * FROM [{rules.NAME}].{table_name}"  # noqa: S608 (a checked table name)
        origin = Origin("sandbox", connection=rules.NAME, sql=sql, filename=words)
        return await self._datasets.store_table(
            name, table, "sandbox", False, "user", follow=follow, origin=origin
        )

    def client_of(self, table: str | None, connection: str | None) -> dict[str, Any]:
        """The client a table's rows are mocked as: the connection named, else the open table's own (its
        origin); plain DuckDB with neither, or with a connection that is gone."""
        name = connection
        if name is None and table is not None:
            name = self._datasets.origins.get(table).connection
        if not name:
            return {"kind": rules.PLAIN}
        try:
            blade, _ = self._connections.blade(name)
            saved, tables_kind = self._tables.kind(name)
        except Exception:
            return {"kind": rules.PLAIN, "connection": name}
        return {
            "kind": tables_kind,
            "connection": saved,
            "template": blade.template or "",
            "dialect": blade.dialect or "",
        }

    async def structure_table(self, structure: str, path: str) -> tuple[Any, str, str]:
        return await self._structure_table(structure, path)

    async def view_rows(self, name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]:
        return await self._view_rows(name, rows)

    def connections(self) -> list[str]:
        """Mocked as's choices: the saved connections that have tables."""
        out = []
        for c in self._connections.listing()["connections"]:
            try:
                self._tables.kind(str(c["name"]))
            except Exception:  # noqa: S112 (no tables: not a connection to mock)
                continue
            out.append(str(c["name"]))
        return sorted(out, key=str.casefold)

    def key_of(self, connection: str, place: Place) -> list[str]:
        """A connection's table's primary key as the shared catalog knows it ([]: not known)."""
        for name in (".".join(p for p in (place.schema, place.table) if p), place.table):
            try:
                return [str(c) for c in self._catalog_table(connection, name).get("primary_key") or []]
            except (LookupError, ValueError):
                continue
        return []
