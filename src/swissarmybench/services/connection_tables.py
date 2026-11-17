"""A connection's tables (domain/connection_tables.py: what a connection is): the contract's two calls,
`places` (list its tables) and `read` (read one), for every kind of connection, and on them DuckDB SQL
that names a table by its connection (`SELECT * FROM [Finance Captive].model_Report`), the Connections
page's tree, and Open all of a dataset's tables.

Listing is the connection's loaded catalog (catalog_loading loads it on first use, its state visible);
reading is the same path as Open as grid (services/connections.py read_place: the connection's own query,
DAX on Power BI, T-SQL on Dataverse's SQL endpoint, a Python connection's Read a table, a file's reader),
with the connection's Rows to open. Each read is kept for the session by (connection, place, limit), with
when it was read; Refresh drops them. Nothing is written to disk; no secret is in a query or an answer.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as rules
from swissarmybench.domain.blades import BladeError
from swissarmybench.domain.connection_swap import Place
from swissarmybench.services.connections import ConnectionService, TableRead
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import Workspace

MAX_KEPT: int = 64  # reads kept for the session (the oldest goes first)
MAX_OPEN_ALL: int = 200  # tables Open all opens at once


class Places(Protocol):
    """The loaded catalogs (services/catalogs.py)."""

    async def places(self, name: str) -> list[tuple[str, str, str]] | None: ...

    async def shared_tables(self, name: str) -> set[str]: ...


class Loading(Protocol):
    """Catalogs that load themselves (services/catalog_loading.py)."""

    async def ready(self, name: str) -> bool: ...

    def state(self, name: str) -> dict[str, str] | None: ...


@dataclass
class Kept:
    id: str
    connection: str
    place: Place
    read: TableRead
    read_at: float
    uses: int = 0

    def to_json(self, cached: bool) -> dict[str, Any]:
        return {
            "id": self.id,
            "connection": self.connection,
            "place": self.place.to_json(),
            "rows": self.read.shown,
            "total": self.read.total,
            "cut": isinstance(self.read.total, int) and self.read.total > self.read.shown,
            "read_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.read_at)),
            "cached": cached,
        }


@dataclass
class Prepared:
    """A query with its connections' tables read: the SQL to run (each named as `__sab_conn_<n>`), the
    tables by those names, and what was read (for the answer: rows, read at, from the session's reads)."""

    sql: str
    tables: dict[str, Any] = field(default_factory=dict)
    reads: list[dict[str, Any]] = field(default_factory=list)


class ConnectionTables:
    def __init__(
        self,
        ws: Workspace,
        connections: ConnectionService,
        catalogs: Places,
        loading: Loading,
        to_bytes: Callable[[Any], bytes] = lambda table: b"",
    ) -> None:
        self.ws = ws
        self._to_bytes = to_bytes  # a table as an Arrow IPC stream (adapters/datasets.py)
        self._connections = connections
        self._catalogs = catalogs
        self._loading = loading
        self._kept: OrderedDict[tuple[str, str, str, str, bool], Kept] = OrderedDict()
        self._by_id: dict[str, Kept] = {}
        self._lock = asyncio.Lock()
        self._next = 0

    # ===== which connections, and what kind =====

    def names(self) -> list[str]:
        """Every saved connection's name (a key vault's too, so naming one in SQL says it has no tables)."""
        return [str(c["name"]) for c in self._connections.listing()["connections"]]

    def kind(self, name: str) -> tuple[str, str]:
        """A connection's saved name and its tables kind (domain/connection_tables.py TABLE_KINDS)."""
        blade, _ = self._connections.blade(name)
        found = rules.tables_kind(
            blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.tags, blade.code
        )
        if found is None:
            reason = rules.no_tables_reason(blade.kind, blade.template)
            raise rules.ConnectionSqlError(f"{blade.name} has no tables: {reason}.")
        return blade.name, found

    # ===== the contract: list, read =====

    async def places(self, name: str) -> list[Place]:
        """A connection's tables (its catalog, loaded now when it is not yet)."""
        saved, _ = self.kind(name)
        found = await self._catalogs.places(saved)
        if found is None:
            await self._loading.ready(saved)
            found = await self._catalogs.places(saved)
        if found is None:
            state = self._loading.state(saved) or {}
            why = f": {state['error']}" if state.get("error") else ""
            raise rules.ConnectionSqlError(
                f"{saved}'s tables could not be listed (its catalog did not load{why})."
            )
        return [Place(*p) for p in found]

    async def read(self, name: str, place: Place, every: bool = False) -> tuple[Kept, bool]:
        """One table read (the connection's Rows to open; `every`: all its rows), or the session's read of
        it: the read, and whether it was kept from before."""
        saved, _ = self.kind(name)
        key = (
            saved.casefold(),
            place.database.casefold(),
            place.schema.casefold(),
            place.table.casefold(),
            every,
        )
        async with self._lock:
            kept = self._kept.get(key)
            if kept is not None:
                self._kept.move_to_end(key)
                return kept, True
        read = await self._connections.read_place(saved, place.to_json(), every)
        async with self._lock:
            self._next += 1
            kept = Kept(f"r{self._next}", saved, place, read, time.time())
            self._kept[key] = kept
            self._by_id[kept.id] = kept
            while len(self._kept) > MAX_KEPT:
                _, old = self._kept.popitem(last=False)
                self._by_id.pop(old.id, None)
        self.ws.audit.write("app", "connection_table_read", saved, rows=read.shown)
        return kept, False

    def kept(self, read_id: str) -> Kept:
        found = self._by_id.get(read_id)
        if found is None:
            raise LookupError("That read is no longer kept: run the query again.")
        return found

    async def arrow(self, read_id: str) -> bytes:
        """A kept read as an Arrow IPC stream, for a Workbench kernel's DuckDB (client/sql_cell.py)."""
        table = self.kept(read_id).read.table
        found: bytes = await self.ws.workers.run(BACKGROUND, self._to_bytes, table)
        return found

    def reads(self) -> dict[str, Any]:
        """The session's reads, newest first (what Refresh would drop)."""
        return {"reads": [k.to_json(True) for k in reversed(self._kept.values())]}

    async def refresh(self, name: str | None = None) -> dict[str, Any]:
        """Drop the session's reads (one connection's, or every one): the next query reads again."""
        async with self._lock:
            dropped = [
                k for k, v in self._kept.items() if name is None or v.connection.casefold() == name.casefold()
            ]
            for key in dropped:
                self._by_id.pop(self._kept.pop(key).id, None)
        return {"dropped": len(dropped)}

    # ===== DuckDB SQL naming a connection's table =====

    async def prepare(self, text: str) -> Prepared:
        """Each connection's table the query names read (or kept from before), and the query pointed at
        them. A query naming none comes back as it was."""
        names = self.names()
        if not names or not rules.might_name(text, names):
            return Prepared(text)
        quoted = rules.quote_brackets(text, names)
        found = rules.references(quoted, names)
        if not found:
            return Prepared(text)
        targets: dict[tuple[str, ...], str] = {}
        prepared = Prepared("")
        for number, ref in enumerate(found):
            _, kind = self.kind(ref.connection)
            place = rules.resolve(ref.connection, kind, ref.parts, await self.places(ref.connection))
            kept, cached = await self.read(ref.connection, place)
            target = rules.target_name(number)
            targets[ref.key] = target
            prepared.tables[target] = kept.read.table
            prepared.reads.append(
                kept.to_json(cached)
                | {"name": target, "as": "[" + ref.connection + "]." + ".".join(ref.parts)}
            )
        prepared.sql = rules.rewrite(quoted, names, targets)
        return prepared

    # ===== the Connections page's tree =====

    async def tree(self, name: str, load: bool = True) -> dict[str, Any]:
        """A connection's tables as a tree: groups (a Power BI workspace's datasets, a database's schemas)
        and their tables, each with its name for SQL. `load`: load the catalog when it is not (the state
        is said while it loads)."""
        saved, kind = self.kind(name)
        found = await self._catalogs.places(saved)
        if found is None and load:
            try:
                await self._loading.ready(saved)
            except BladeError:
                pass
            found = await self._catalogs.places(saved)
        state = self._loading.state(saved) or (
            {"state": "loaded"} if found is not None else {"state": "none"}
        )
        shared = await self._catalogs.shared_tables(saved) if found else set()
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for database, schema, table in found or []:
            place = Place(database, schema, table)
            groups.setdefault((database, schema), []).append(
                place.to_json() | {"sql": rules.copy_name(saved, place, kind, shared)}
            )
        word = {"powerbi": "dataset"}.get(kind, "schema")
        return {
            "connection": saved,
            "kind": kind,
            "group": word,
            "state": state,
            "groups": [
                {"database": d, "schema": s, "tables": tables, "count": len(tables)}
                for (d, s), tables in groups.items()
            ],
        }

    async def open_dataset(self, name: str, dataset: str, who: str) -> dict[str, Any]:
        """Every table of one of a connection's datasets (or schemas) as its own grid."""
        saved, _ = self.kind(name)
        if not dataset.strip():
            raise ValueError("Name the dataset (or schema) whose tables to open.")
        tables = [p for p in await self.places(saved) if p.schema.casefold() == dataset.strip().casefold()]
        if not tables:
            raise rules.ConnectionSqlError(f"{saved} has no dataset or schema {dataset!r} with tables.")
        if len(tables) > MAX_OPEN_ALL:
            raise rules.ConnectionSqlError(
                f"{dataset} has {len(tables)} tables: Open all opens at most {MAX_OPEN_ALL} at once."
            )
        opened: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        for place in tables:
            body = place.to_json()
            try:
                got = await self._connections.open_table(saved, body, who)
                opened.append({"table": place.table, "dataset": got.get("dataset"), "grid": got.get("grid")})
            except Exception as error:  # one table's refusal is said beside the others
                failed.append({"table": place.table, "error": str(error)[:300]})
        return {"connection": saved, "dataset": tables[0].schema, "opened": opened, "failed": failed}
