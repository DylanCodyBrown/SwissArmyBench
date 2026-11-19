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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as rules
from swissarmybench.domain import lakes
from swissarmybench.domain.blades import BladeError
from swissarmybench.domain.catalogs import normalize_dialect
from swissarmybench.domain.connection_swap import Place
from swissarmybench.services.connections import ConnectionService, TableRead
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import Workspace

MAX_KEPT: int = 64  # reads kept for the session (the oldest goes first)
MAX_OPEN_ALL: int = 200  # tables Open all opens at once
ALIAS = "alias"  # a project's dataset connection name, resolved through its setting (services/hooks.py)


class Places(Protocol):
    """The loaded catalogs (services/catalogs.py)."""

    async def places(self, name: str) -> list[tuple[str, str, str]] | None: ...

    async def shared_tables(self, name: str) -> set[str]: ...

    async def titles(self, name: str) -> dict[tuple[str, str, str], str]: ...

    async def columns(
        self, name: str, schema: str, table: str | None, database: str | None
    ) -> dict[str, Any]: ...


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
    pushed: rules.Pushed = field(default_factory=rules.Pushed)

    def to_json(self, cached: bool) -> dict[str, Any]:
        return {
            "id": self.id,
            "connection": self.connection,
            "place": self.place.to_json(),
            "sent": self.pushed.to_json(),  # its columns, filters and LIMIT, as the source was asked
            "rows": self.read.shown,
            "total": self.read.total,
            "cut": isinstance(self.read.total, int) and self.read.total > self.read.shown,
            "read_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.read_at)),
            "cached": cached,
        } | ({"read_with": lakes.read_with(self.read.how)} if self.read.how else {})


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
        aliases: Callable[[], Mapping[str, Any]] = lambda: {},
    ) -> None:
        self.ws = ws
        self._to_bytes = to_bytes  # a table as an Arrow IPC stream (adapters/datasets.py)
        # A project's dataset connection names resolving through its own setting (services/hooks.py).
        self._aliases = aliases
        self._connections = connections
        self._catalogs = catalogs
        self._loading = loading
        self._kept: OrderedDict[tuple[str, str, str, str, str], Kept] = OrderedDict()
        self._by_id: dict[str, Kept] = {}
        self._lock = asyncio.Lock()
        self._next = 0

    # ===== which connections, and what kind =====

    def names(self) -> list[str]:
        """Every saved connection's name (a key vault's too, so naming one in SQL says it has no tables),
        and the open project's dataset connection names (an alias resolving through its setting)."""
        saved = [str(c["name"]) for c in self._connections.listing()["connections"]]
        taken = {n.casefold() for n in saved}
        return saved + [a for a in self._aliases() if a.casefold() not in taken]

    def alias(self, name: str) -> tuple[str, Any] | None:
        """A dataset connection name that resolves through the open project's setting (not a saved one)."""
        if any(
            str(c["name"]).casefold() == name.casefold() for c in self._connections.listing()["connections"]
        ):
            return None
        for key, value in self._aliases().items():
            if key.casefold() == name.casefold():
                return key, value
        return None

    async def alias_dax(self, name: str, query: str) -> tuple[Any, str]:
        """DAX on the project's dataset connection, through what it reads now: the rows and its words."""
        found = self.alias(name)
        if found is None:
            raise LookupError(f"No dataset connection is named {name!r} in the open project.")
        key, alias = found
        table = await alias.dax(query)
        self.ws.audit.write("app", "dataset_alias_dax", key, rows=int(table.num_rows))
        return table, str(alias.words())

    def kind(self, name: str) -> tuple[str, str]:
        """A connection's saved name and its tables kind (domain/connection_tables.py TABLE_KINDS)."""
        aliased = self.alias(name)
        if aliased is not None:
            return aliased[0], ALIAS
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
        saved, kind = self.kind(name)
        alias = self.alias(saved) if kind == ALIAS else None
        if alias is not None:
            return [Place("", "", t) for t in await alias[1].tables()]
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

    async def read(self, name: str, place: Place, pushed: rules.Pushed | None = None) -> tuple[Kept, bool]:
        """One table read for a query: every row it needs, with what was sent to the source (`pushed`: its
        columns, filters, a safe LIMIT), or the session's read of it by the same request to the source:
        the read, and whether it was kept from before. Never the connection's first rows only: past the
        query limit (settings) it is refused, with how to narrow it."""
        saved, kind = self.kind(name)
        sent = pushed or rules.Pushed()
        alias = self.alias(saved) if kind == ALIAS else None
        key = (
            (saved + (" · " + str(alias[1].words()) if alias else "")).casefold(),
            place.database.casefold(),
            place.schema.casefold(),
            place.table.casefold(),
            sent.key(),
        )
        async with self._lock:
            kept = self._kept.get(key)
            if kept is not None:
                self._kept.move_to_end(key)
                return kept, True
        most = self.ws.settings.max_connection_query_rows
        if alias is not None:  # read whole, through what the alias reads now
            table = await alias[1].read(place.table)
            shown = int(table.num_rows)
            if shown > most:
                raise BladeError(rules.too_many(saved, place.table, shown, most, False))
            read = TableRead(place.table, table, None, shown, shown, saved, dax=True)
        else:
            read = await self._connections.read_for_query(saved, place.to_json(), sent, most)
        async with self._lock:
            self._next += 1
            kept = Kept(f"r{self._next}", saved, place, read, time.time(), sent)
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

    async def to_arrow(self, table: Any) -> bytes:
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
            known = await self._known(ref.connection, place)
            # Columns and filters go to a SQL source, and to the lake and SharePoint kinds' own reads
            # (DuckDB's pushdown, Graph's $select and $filter); DAX, Python, files and the Web API read whole.
            sql_source = kind in ("database", "dataverse") or lakes.is_kind(kind)
            pushed = (
                rules.pushdown(quoted, names, ref, known, self._dialect(ref.connection))
                if sql_source
                else rules.Pushed()
            )
            kept, cached = await self.read(ref.connection, place, pushed)
            target = rules.target_name(number)
            targets[ref.key] = target
            prepared.tables[target] = kept.read.table
            prepared.reads.append(
                kept.to_json(cached)
                | {"name": target, "as": "[" + ref.connection + "]." + ".".join(ref.parts)}
            )
        prepared.sql = rules.rewrite(quoted, names, targets)
        return prepared

    async def _known(self, name: str, place: Place) -> list[str]:
        """The table's columns as its catalog spells them (none known: every column is read)."""
        try:
            found = await self._catalogs.columns(name, place.schema, place.table, place.database or None)
        except (KeyError, LookupError, ValueError):
            return []
        return [
            str(c["column"])
            for c in found.get("columns", [])
            if c.get("column") and "measure" not in str(c.get("type") or "")
        ]

    def _dialect(self, name: str) -> str:
        blade, _ = self._connections.blade(name)
        return normalize_dialect(blade.dialect)

    # ===== the Connections page's tree =====

    async def describe(self, name: str, place: Place) -> dict[str, Any]:
        """One table of a loaded catalog for the Data page's detail side: its name in DuckDB SQL and its
        columns (name, type, nulls, description), as the catalog has them. Names only."""
        saved, kind = self.kind(name)
        if await self._catalogs.places(saved) is None:
            raise LookupError(f"{saved}'s catalog is not loaded yet: load it (connections_load_catalog).")
        shared = await self._catalogs.shared_tables(saved)
        found = await self._catalogs.columns(saved, place.schema, place.table, place.database or None)
        return {
            "connection": saved,
            "kind": kind,
            "sql": rules.copy_name(saved, place, kind, shared),
            "columns": [
                {
                    "name": c["column"],
                    "type": c.get("type"),
                    "nullable": c.get("nullable"),
                    "description": c.get("description"),
                }
                for c in found["columns"]
            ],
        }

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
        # What the source says of each table (a Delta table's version, size and partitions; a sheet).
        titles = await self._catalogs.titles(saved) if found else {}
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for database, schema, table in found or []:
            place = Place(database, schema, table)
            words = titles.get((database, schema, table))
            groups.setdefault((database, schema), []).append(
                place.to_json()
                | {"sql": rules.copy_name(saved, place, kind, shared)}
                | ({"title": words} if words else {})
            )
        word = {"powerbi": "dataset", "sharepoint": "list"}.get(
            kind, "folder" if kind in rules.PATH_KINDS else "schema"
        )
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
