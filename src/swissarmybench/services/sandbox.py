"""A project's sandbox (domain/sandbox.py): the data a local sandbox API reads and writes, and nothing else.

  list        the tables (rows, columns, where each came from), the baseline, the checkpoints, the change log
  add         a table in, on the user's action: an open grid's view (after its steps), a connection's table
  (read
              once through the connection, its row limit applying), a file, or an empty table by its columns
  remove      a table out
  reset       every table back to the baseline in one step (the agent's on the user's Allow)
  baseline    the sandbox as it is now made the baseline
  checkpoint  save, restore and delete named copies
  data        an API's reads and writes (data.query, data.table, data.insert, data.update, data.delete,
              data.transaction): counted in the change log, an open grid of the table following at once
  open        a sandbox table in Grids (sandbox_<table>: follows every write)

Every change is told to the pages (`sandbox_changed`) and audited (names and counts, never a value). DuckDB
SQL
names a sandbox table as `[Sandbox].orders` (alias: a dataset connection name, services/hooks.py). A sandbox
lives in the open project's folder: with none open, it is refused in one sentence.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import sandbox as rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.connection_swap import Place, place_of
from swissarmybench.domain.sandbox import SandboxError
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Workspace


class Files(Protocol):
    """adapters/sandbox.py SandboxFiles."""

    def exists(self) -> bool: ...

    def close(self) -> None: ...

    def read_meta(self) -> rules.Meta: ...

    def write_meta(self, meta: rules.Meta) -> None: ...

    def tables(self) -> list[dict[str, Any]]: ...

    def columns(self, table: str) -> list[dict[str, Any]]: ...

    def table_name(self, wanted: str) -> str | None: ...

    def table_names(self) -> list[str]: ...

    def put_table(self, name: str, table: Any, replace: bool) -> int: ...

    def create_empty(self, name: str, columns: Any, replace: bool) -> None: ...

    def drop(self, name: str) -> None: ...

    def kind_of(self, name: str) -> str | None: ...

    def keys(self, name: str) -> list[str]: ...

    def set_key(self, name: str, key: Any) -> None: ...

    def define(self, sql: str, params: Any = ()) -> None: ...

    def arrow(self, name: str) -> Any: ...

    # the adapter's read (a reader and the parts folded) and write (an Arrow IPC stream's rows: the counts)
    def read(self, name: str, plan: Any) -> tuple[Any, tuple[str, ...]]: ...

    def write_arrow(self, name: str, data: bytes, key: Any, mode: str) -> dict[str, int]: ...

    # several of those in one transaction, all or none: each one's counts
    def write_all_arrow(self, writes: Any) -> list[dict[str, int]]: ...

    def query(
        self, statement: rules.Statement, limit: int
    ) -> tuple[list[str], list[str], list[list[Any]], bool]: ...

    # the adapter's query: a read's batches; a write's answer (its RETURNING rows, else its count) and count
    def query_arrow(self, sql: str, params: Any) -> Any: ...

    def change_arrow(self, sql: str, params: Any) -> tuple[Any, int]: ...

    def counted(self, rows: int) -> Any: ...

    def write(self, groups: Any) -> list[int]: ...

    def set_baseline(self) -> None: ...

    def reset(self) -> bool: ...

    def drop_all(self) -> list[str]: ...

    def reset_table(self, name: str) -> bool: ...

    def save_checkpoint(self, name: str) -> None: ...

    def restore_checkpoint(self, name: str) -> bool: ...

    def delete_checkpoint(self, name: str) -> None: ...

    def copy_to(self, target: Any) -> None: ...


class Sources(Protocol):
    """Where a table comes from (bootstrap.py wires them)."""

    async def grid_view(self, name: str) -> Any: ...  # an open table's view after its steps (Arrow)

    async def connection_table(self, connection: str, place: Place) -> Any: ...

    async def file_table(self, path: str, sheet: str | None) -> Any: ...

    # A grid of it; `words`: its designation and origin ("orders · sandbox: A sandbox variant of orders").
    async def show(self, name: str, table: Any, follow: bool, words: str = "") -> dict[str, Any]: ...

    def client_of(self, table: str | None, connection: str | None) -> dict[str, Any]: ...

    # A structure's records as a table (Structures' Open as grid's): (its Arrow, its name, the path read).
    async def structure_table(self, structure: str, path: str) -> tuple[Any, str, str]: ...

    # An open grid's view rows at these positions: (its columns, each row's values; None past its end).
    async def view_rows(self, name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]: ...

    def connections(self) -> list[str]: ...  # the saved connections with tables (Mocked as's choices)

    def key_of(self, connection: str, place: Place) -> list[str]: ...  # its primary key in the shared catalog


async def _no_structure(structure: str, path: str) -> tuple[Any, str, str]:
    raise LookupError("Structures are not here.")


async def _no_rows(name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]:
    raise LookupError("That table is not open on the Tables page.")


@dataclass
class SourcesFrom:
    """Sources made of the composition root's callables."""

    grid_view_fn: Callable[[str], Awaitable[Any]]
    connection_fn: Callable[[str, Place], Awaitable[Any]]
    file_fn: Callable[[str, str | None], Awaitable[Any]]
    show_fn: Callable[[str, Any, bool, str], Awaitable[dict[str, Any]]]
    # The client a table's rows are mocked as: an open table's connection (its origin), or a connection named.
    client_fn: Callable[[str | None, str | None], dict[str, Any]] = field(
        default=lambda table, connection: {"kind": rules.PLAIN}
    )
    structure_fn: Callable[[str, str], Awaitable[tuple[Any, str, str]]] = _no_structure
    view_rows_fn: Callable[[str, list[int]], Awaitable[tuple[list[str], list[list[Any] | None]]]] = _no_rows
    connections_fn: Callable[[], list[str]] = field(default=lambda: [])
    key_fn: Callable[[str, Place], list[str]] = field(default=lambda connection, place: [])

    async def grid_view(self, name: str) -> Any:
        return await self.grid_view_fn(name)

    def key_of(self, connection: str, place: Place) -> list[str]:
        return self.key_fn(connection, place)

    async def connection_table(self, connection: str, place: Place) -> Any:
        return await self.connection_fn(connection, place)

    async def file_table(self, path: str, sheet: str | None) -> Any:
        return await self.file_fn(path, sheet)

    async def show(self, name: str, table: Any, follow: bool, words: str = "") -> dict[str, Any]:
        return await self.show_fn(name, table, follow, words)

    def client_of(self, table: str | None, connection: str | None) -> dict[str, Any]:
        return self.client_fn(table, connection)

    async def structure_table(self, structure: str, path: str) -> tuple[Any, str, str]:
        return await self.structure_fn(structure, path)

    async def view_rows(self, name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]:
        return await self.view_rows_fn(name, rows)

    def connections(self) -> list[str]:
        return self.connections_fn()


def _stamp(now: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))


def _plain(value: Any) -> Any:
    """A value DuckDB answered, as JSON carries it (dates as ISO text, decimals as numbers)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):  # a LIST: a list, as a real driver gives it
        return [_plain(v) for v in value]
    if isinstance(value, dict):  # a STRUCT or a MAP: an object
        return {str(k): _plain(v) for k, v in value.items()}
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


class Sandbox:
    def __init__(
        self,
        ws: Workspace,
        project: Callable[[], str | None],
        files: Callable[[str], Files],
        sources: Sources,
        approvals: Approvals,
        parse: Callable[[str], dict[str, Any]],
        ignore: Callable[[str], Any] = lambda folder: None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.ws = ws
        self._project = project
        self._files_for = files
        self._sources = sources
        self._approvals = approvals
        self._parse = parse
        self._ignore = ignore  # the project's .gitignore line for sandbox/ (written once)
        self._moved = ""  # an older project's .sab/sandbox/ moved to sandbox/: said once (listing's notice)
        self._now = now
        self._open: tuple[str, Files] | None = None
        self._lock = asyncio.Lock()
        self.version = 0  # every change: [Sandbox]'s reads in DuckDB SQL are read again
        self.changed: list[Callable[[list[str]], Awaitable[None]]] = []  # tables a write touched
        self._key_note = ""  # why a table came in without its key (add's answer)
        # The adapter's door: a local sandbox API's reads, queries and writes (DataDoor, below).
        self.door = DataDoor(self)

    # ===== which sandbox =====

    def folder(self) -> str | None:
        return self._project()

    def _files(self, create: bool = False) -> Files:
        folder = self._project()
        if folder is None:
            raise Conflict("Open a project first: its sandbox lives in its folder.")
        if self._open is None or self._open[0] != folder:
            if self._open is not None:
                self._open[1].close()
            self._open = (folder, self._files_for(folder))
            if getattr(self._open[1], "moved", False):
                self._moved = rules.MOVED
                self.ws.audit.write("app", "sandbox_moved", rules.FOLDER)
        files = self._open[1]
        if create and not files.exists():
            self._ignore(folder)
        return files

    def close(self) -> None:
        if self._open is not None:
            self._open[1].close()
            self._open = None

    async def _run(self, fn: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.to_thread(fn, *args)

    async def _told(self, tables: list[str], who: str, action: str, **facts: Any) -> None:
        self.version += 1
        if action:
            self.ws.audit.write(who, action, ", ".join(tables) or rules.NAME, **facts)
        await self.ws.live.broadcast({"type": "sandbox_changed", "tables": tables, "version": self.version})
        for told in self.changed:
            await told(tables)
        await self._follow(tables)

    async def _follow(self, tables: list[str]) -> None:
        """Each open grid of a changed table gets its rows again, where it is (its steps kept)."""
        files = self._open[1] if self._open else None
        if files is None:
            return
        for table in tables:
            if self.ws.grids.first_for(rules.grid_name(table)) is None:
                continue
            try:
                arrow = await self._run(files.arrow, table)
            except Exception:  # noqa: S112 (a dropped table: its grid keeps what it had)
                continue
            await self._sources.show(rules.grid_name(table), arrow, True, self._designation(files, table))

    # ===== list =====

    async def listing(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The sandbox: its tables (sorted as asked: {"sort": name | rows | source | created | changed,
        "order": asc | desc}), the baseline, the checkpoints, the change log."""
        given = body if isinstance(body, dict) else {}
        by, descending = rules.check_sort(given.get("sort"), given.get("order"))
        folder = self._project()
        if folder is None:
            return {"project": None, "tables": [], "checkpoints": [], "log": {}, "baseline_at": None}
        files = self._files()
        tables = await self._run(files.tables)
        meta = files.read_meta()
        for t in tables:
            info = meta.tables.get(t["name"], {})
            source = info.get("source", {})
            t["type"] = rules.CONNECTION_TYPE
            t["source"] = source
            t["source_words"] = rules.source_words(source)
            t["client"] = info.get("client") or {"kind": rules.PLAIN}
            t["mocked"] = bool(info.get("mocked"))
            t["mockable"] = self._mockable(info)
            t["variant"] = info.get("variant")
            t["title"] = (info.get("variant") or {}).get("title") or t["name"]
            t["origin_words"] = rules.origin_words(info.get("variant"))
            t["added_at"] = info.get("added_at")
            t["changed_at"] = info.get("changed_at")
            t["sql"] = f"[{rules.NAME}].{t['name']}"
            t["grid"] = rules.grid_name(t["name"])
            t["open"] = self.ws.grids.first_for(rules.grid_name(t["name"])) is not None
            t["changes"] = meta.log.get(t["name"], rules.Counts()).to_json()
        return {
            "project": folder,
            "type": rules.CONNECTION_TYPE,
            "tables": rules.sort_tables(tables, by, descending),
            "sort": {"by": by, "order": "desc" if descending else "asc", "choices": rules.SORTS},
            "baseline_at": meta.baseline_at,
            "checkpoints": [{"name": c.name, "at": c.at} for c in meta.checkpoints],
            "log": rules.log_json(meta.log),
            "log_words": rules.log_words(meta.log),
            "version": self.version,
            "mock_choices": self._mock_choices(),
            **({"notice": self._said_moved()} if self._moved else {}),
        }

    async def mirror(self) -> dict[str, Any] | None:
        """What the sandbox mirror's files are made of (services/scaffold.py): each table's record (its
        source, the client it is mocked as, its key), the baseline's time, the checkpoints' names. None: no
        project, or it has no sandbox (nothing is made for one that was never used). An older project's
        .sab/sandbox/ is
        moved here first (once)."""
        if self._project() is None:
            return None
        files = self._files()
        if not files.exists():
            return None
        meta = files.read_meta()
        names = set(await self._run(files.table_names))
        return {
            "tables": {n: r for n, r in meta.tables.items() if n in names},
            "baseline_at": meta.baseline_at,
            "checkpoints": [c.name for c in meta.checkpoints],
        }

    def _said_moved(self) -> str:
        said, self._moved = self._moved, ""
        return said

    async def drop(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Remove the sandbox: sandbox/ (its rows, baseline, checkpoints) and its two files, sandbox_data.py
        and sandbox_connections.py, and nothing else (the app's files never name it). The agent's waits for
        Allow."""
        files = self._files()
        tables = await self._run(files.table_names) if files.exists() else []
        await self._approvals.allowed(
            who,
            subject=rules.NAME,
            action="remove the sandbox",
            detail=f"Remove the project's sandbox: {len(tables)} table{'s' if len(tables) != 1 else ''}, its "
            f"baseline and checkpoints ({rules.FOLDER}/, {rules.DATA_FILE}, {rules.CONNECTIONS_FILE})",
            otherwise="the sandbox stays",
        )
        async with self._lock:
            removed = await self._run(files.drop_all)
        await self._told(list(tables), who, "sandbox_drop", removed=len(removed))
        return {"removed": removed, "tables": list(tables)}

    @staticmethod
    def _mockable(info: dict[str, Any]) -> bool:
        """A table that answered as no connection when it came in (a file, its columns, a grid of no
        connection's): it may be Mocked as one."""
        first = info.get("origin_client")
        if first is None:  # added before Mocked as existed: its client then was its own
            first = {} if info.get("mocked") else info.get("client") or {}
        return not first.get("connection")

    def _mock_choices(self) -> list[str]:
        try:
            return [c for c in self._sources.connections() if not rules.is_sandbox(c)]
        except Exception:  # the connections' own trouble: no choices to offer
            return []

    async def names(self) -> list[str]:
        if self._project() is None:
            return []
        return [str(t["name"]) for t in await self._run(self._files().tables)]

    def table_columns(self) -> list[tuple[str, list[str]]]:
        """Each sandbox table and its columns (API.py's SQL completion; off the loop is not needed: small)."""
        if self._project() is None:
            return []
        files = self._files()
        if not files.exists():
            return []
        return [(str(t["name"]), [str(c["name"]) for c in t["columns"]]) for t in files.tables()]

    def mock_dialects(self) -> dict[str, tuple[str, list[str]]]:
        """Each name connection("…") takes in API.py, with its mock's dialect and the sandbox tables it reads
        (API.py's squiggles: the SQL the mock would refuse). From sandbox.json and the file's names."""
        if self._project() is None:
            return {}
        files = self._files()
        if not files.exists():
            return {}
        meta = files.read_meta()
        names = files.table_names()
        out: dict[str, tuple[str, list[str]]] = {rules.NAME: ("duckdb", names)}
        for table, info in meta.tables.items():
            client = info.get("client") or {}
            connection = str(client.get("connection") or "")
            if connection and not rules.is_sandbox(connection):
                dialect, mine = out.get(connection, (str(client.get("dialect") or "duckdb"), []))
                out[connection] = (dialect, [*mine, table])
        return out

    def mock_names(self) -> list[tuple[str, str]]:
        """The names connection("…") takes in API.py: Sandbox, and each connection a sandbox table came
        from, with the client it is mocked as (read from sandbox.json: no query)."""
        if self._project() is None:
            return []
        meta = self._files().read_meta()
        out = {rules.NAME: "the sandbox (plain DuckDB)"}
        for info in meta.tables.values():
            client = info.get("client") or {}
            if client.get("connection"):
                what = client.get("template") or client.get("dialect") or client.get("kind")
                out.setdefault(str(client["connection"]), f"mock of its client ({what})")
        return sorted(out.items(), key=lambda kv: (kv[0] != rules.NAME, kv[0].casefold()))

    async def names_and_columns(self) -> list[dict[str, Any]]:
        """The Catalog's Sandbox section: each table as the listing has it (rows, columns, designation,
        source, created, last changed)."""
        if self._project() is None or not self._files().exists():
            return []
        return list((await self.listing())["tables"])

    # ===== add, remove =====

    async def add(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"from": "grid"|"connection"|"file"|"columns", "name"?, "replace"?, ...}: a table in.
        grid: {"table"}; connection: {"connection", "table", "schema"?, "database"?};
        file: {"path", "sheet"?};
        columns: {"columns": [{name, type, key?}]}."""
        given = body if isinstance(body, dict) else {}
        kind = str(given.get("from") or "grid")
        replace = bool(given.get("replace"))
        source: dict[str, Any]
        if kind == "grid":
            grid_table = str(given.get("table") or "").strip()
            if not grid_table:
                raise SandboxError("Name the open table to add.")
            name = rules.check_table_name(given.get("name") or grid_table)
            source = {"kind": "grid", "table": grid_table}
            try:
                arrow = await self._sources.grid_view(grid_table)
            except LookupError as error:
                raise NotFound(str(error)) from error
        elif kind == "connection":
            connection, table = str(given.get("connection") or ""), str(given.get("table") or "")
            if not connection or not table:
                raise SandboxError("Name the connection and its table.")
            name = rules.check_table_name(given.get("name") or table.split(".")[-1])
            place = Place(str(given.get("database") or ""), str(given.get("schema") or ""), table)
            source = {"kind": "connection", "connection": connection, "place": place.to_json()}
            arrow = await self._sources.connection_table(connection, place)
        elif kind == "file":
            path = str(given.get("path") or "")
            if not path:
                raise SandboxError("Name the file to add.")
            stem = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            name = rules.check_table_name(given.get("name") or stem)
            source = {"kind": "file", "file": stem}
            sheet = given.get("sheet")
            arrow = await self._sources.file_table(path, str(sheet) if sheet else None)
        elif kind == "structure":
            wanted = str(given.get("structure") or "").strip()
            if not wanted:
                raise SandboxError("Name the structure to add.")
            try:
                arrow, structure, path = await self._sources.structure_table(
                    wanted, str(given.get("path") or "$")
                )
            except LookupError as error:
                raise NotFound(str(error)) from error
            name = rules.check_table_name(given.get("name") or rules.ident_of(structure))
            source = {"kind": "structure", "structure": structure, "path": path}
        elif kind == "columns":
            name = rules.check_table_name(given.get("name"))
            columns = rules.columns_spec(given.get("columns"))
            source = {"kind": "columns"}
            arrow = None
        else:
            raise SandboxError("Add from grid, connection, file, structure or columns.")
        client = self._sources.client_of(
            source.get("table") if kind == "grid" else None, source.get("connection")
        )
        if kind == "grid" and client.get("connection"):
            source["connection"] = client["connection"]  # the open table's own (its origin's words)
        title = str(given.get("title") or name)[:80]
        async with self._lock:
            files = self._files(create=True)
            existing = await self._run(files.table_name, name)
            if existing is not None and not replace:
                raise Conflict(f"The sandbox has a table named {existing} already: replace it, or name it.")
            if arrow is None:
                await self._run(files.create_empty, name, columns, replace)
                rows = 0
            else:
                rows = await self._run(files.put_table, name, arrow, replace)
            meta = files.read_meta()
            at = _stamp(self._now())
            meta.tables[name] = {
                "type": rules.CONNECTION_TYPE,
                "source": source,
                "client": client,
                "origin_client": client,
                "added_at": at,
            }
            if kind in rules.VARIANT_SOURCES:
                meta.tables[name]["variant"] = rules.variant_record(source, title, at)
            key = await self._first_key(files, name, given, columns if kind == "columns" else None, source)
            if key:
                meta.tables[name]["key"] = key
            meta.log.pop(name, None)
            # A table added is part of the baseline: Reset gives it back as it came in.
            await self._run(files.set_baseline)
            meta.baseline_at = _stamp(self._now())
            files.write_meta(meta)
        await self._told([name], who, "sandbox_add", rows=rows, source=kind)
        added: dict[str, Any] = {"added": name, "rows": rows, "sql": f"[{rules.NAME}].{name}"}
        if meta.tables[name].get("key"):
            added["key"] = meta.tables[name]["key"]
        if self._key_note:
            added["note"], self._key_note = self._key_note, ""
        return added

    async def _first_key(
        self, files: Files, name: str, given: dict[str, Any], columns: Any, source: dict[str, Any]
    ) -> list[str]:
        """A table's primary key as it comes in: the one asked for, a column list's, else its connection's in
        the shared catalog. Rows that repeat or blank it: no key, and why in `note`."""
        named = [c["name"] for c in await self._run(files.columns, name)]
        if given.get("key"):
            key = rules.check_key(given["key"], named)
        elif columns is not None:
            key = [c.name for c in columns if c.key]
        elif source.get("kind") == "connection":
            place = place_of(source.get("place")) or Place("", "", name)
            try:
                key = rules.check_key(self._sources.key_of(str(source["connection"]), place), named)
            except SandboxError:
                key = []
        else:
            key = []
        if key and not await self._run(files.keys, name):
            try:
                await self._run(files.set_key, name, key)
            except Exception as error:  # rows that repeat or blank it
                self._key_note = f"{name} came in without its key ({', '.join(key)}): {rules.db_words(error)}"
                return []
        return key

    async def set_key(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"table", "key"}: the table's primary key (a column or a list of them), kept by Reset; a write that
        repeats or blanks it is refused from then on, as the real database would."""
        given = body if isinstance(body, dict) else {}
        async with self._lock:
            files = self._files()
            table, columns = await self._table(files, given.get("table"))
            key = rules.check_key(given.get("key"), columns)
            have = await self._run(files.keys, table)
            if have and [k.casefold() for k in have] != [k.casefold() for k in key]:
                raise Conflict(f"{table}'s key is {', '.join(have)} already.")
            try:
                await self._run(files.set_key, table, key)
            except Exception as error:
                raise SandboxError(rules.db_words(error)) from error
            meta = files.read_meta()
            if table in meta.tables:
                meta.tables[table]["key"] = key
                files.write_meta(meta)
        await self._told([table], who, "sandbox_key", key=", ".join(key))
        return {"table": table, "key": key}

    async def _keys_back(self, files: Files, meta: rules.Meta) -> None:
        """After Reset or Restore: each kept key put back where the file put back has none (an older
        checkpoint's copy)."""
        for table, record in meta.tables.items():
            key = record.get("key")
            if (
                key
                and await self._run(files.kind_of, table) == "table"
                and not await self._run(files.keys, table)
            ):
                try:
                    await self._run(files.set_key, table, list(key))
                except Exception:  # noqa: S112 (rows the checkpoint holds repeat it: it stays without)
                    continue

    async def variant(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Make a sandbox variant: {"from": "grid" (default) | "structure", "table" | "structure", "path"?,
        "name"?}: a copy of an open table's view (after its steps) or a structure's records, with its own
        designation ("orders · sandbox", or the name given) and its origin kept. Several of one origin are
        named apart; a variant never writes back to its origin."""
        given = dict(body) if isinstance(body, dict) else {}
        kind = str(given.get("from") or "grid")
        if kind not in ("grid", "structure"):
            raise SandboxError("A sandbox variant is made from an open table (grid) or a structure.")
        origin = str(given.get("table") if kind == "grid" else given.get("structure") or "").strip()
        if not origin:
            raise SandboxError(
                "Name the open table to make a variant of." if kind == "grid" else "Name the structure."
            )
        if kind == "structure":  # its own name (it was asked for by name or id)
            try:
                _, origin, _ = await self._sources.structure_table(origin, str(given.get("path") or "$"))
            except LookupError as error:
                raise NotFound(str(error)) from error
        taken = await self.names()
        name, title = rules.variant_name(origin, taken, given.get("name"))
        made = await self.add(given | {"from": kind, "name": name, "title": title, "replace": False}, who)
        return made | {"title": title, "variant": True}

    async def mock(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Mocked as: {"table", "connection"}: a table from a file, its columns or a grid of no connection's
        answers as that connection (its kind and dialect); {"connection": null}: plain DuckDB again."""
        given = body if isinstance(body, dict) else {}
        wanted = given.get("connection")
        async with self._lock:
            files = self._files()
            table, _ = await self._table(files, given.get("table"))
            meta = files.read_meta()
            info = meta.tables.setdefault(table, {"source": {}, "client": {"kind": rules.PLAIN}})
            if not self._mockable(info):
                said = (info.get("client") or {}).get("connection")
                raise Conflict(f"{table} was read from {said}: it answers as {said} already.")
            info.setdefault("origin_client", {"kind": rules.PLAIN})
            if wanted is None or str(wanted).strip() == "":
                info["client"] = {"kind": rules.PLAIN}
                info.pop("mocked", None)
            else:
                name = str(wanted).strip()
                if rules.is_sandbox(name):
                    raise SandboxError("A table is mocked as one of your connections, not as the Sandbox.")
                client = self._sources.client_of(None, name)
                if client.get("kind") == rules.PLAIN:
                    raise NotFound(f"There is no connection called {name} with tables to mock.")
                info["client"] = client
                info["mocked"] = True
            files.write_meta(meta)
        await self._told([table], who, "sandbox_mock", connection=str(wanted or ""))
        return {"table": table, "client": info["client"], "mocked": bool(info.get("mocked"))}

    async def remove(self, body: Any, who: str = "user") -> dict[str, Any]:
        name = rules.check_table_name((body or {}).get("table") if isinstance(body, dict) else body)
        async with self._lock:
            files = self._files()
            real = await self._run(files.table_name, name)
            if real is None:
                raise NotFound(f"The sandbox has no table named {name}.")
            await self._run(files.drop, real)
            meta = files.read_meta()
            meta.tables.pop(real, None)
            meta.log.pop(real, None)
            await self._run(files.set_baseline)
            files.write_meta(meta)
        await self._told([real], who, "sandbox_remove")
        return {"removed": real}

    # ===== baseline, reset, checkpoints =====

    async def reset(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Every table back to the baseline (or {"table"}: that one alone): what the change log counted is
        undone."""
        files = self._files()
        meta = files.read_meta()
        one = body.get("table") if isinstance(body, dict) else None
        if one:
            return await self._reset_one(files, meta, str(one), who)
        await self._approvals.allowed(
            who,
            subject=rules.NAME,
            action="reset the sandbox",
            detail=f"Put every sandbox table back to the baseline ({rules.log_words(meta.log)})",
            otherwise="the sandbox is as it was",
        )
        async with self._lock:
            if not await self._run(files.reset):
                raise Conflict("The sandbox has no baseline yet: add a table first.")
            rules.unmade(meta, await self._run(files.table_names))
            await self._keys_back(files, meta)
            undone = rules.log_json(meta.log)
            rules.touched(meta, [t for t in meta.log if meta.log[t].any], _stamp(self._now()))
            meta.log = {}
            files.write_meta(meta)
        await self._told(sorted(meta.tables), who, "sandbox_reset")
        return {"reset": True, "undone": undone}

    async def _reset_one(self, files: Files, meta: rules.Meta, wanted: str, who: str) -> dict[str, Any]:
        table, _ = await self._table(files, wanted)
        counts = meta.log.get(table, rules.Counts())
        await self._approvals.allowed(
            who,
            subject=rules.NAME,
            action="reset a sandbox table",
            detail=f"Put {table} back to the baseline ({rules.log_words({table: counts})})",
            otherwise="the table is as it was",
        )
        async with self._lock:
            if not await self._run(files.reset_table, table):
                raise Conflict(f"{table} is not in the baseline: Set as baseline first.")
            meta = files.read_meta()
            await self._keys_back(files, meta)  # its rows were put back as a new table: its key again
            undone = rules.log_json({table: meta.log.pop(table, rules.Counts())})
            if undone:
                rules.touched(meta, [table], _stamp(self._now()))
            files.write_meta(meta)
        await self._told([table], who, "sandbox_reset")
        return {"reset": True, "table": table, "undone": undone}

    async def set_baseline(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        async with self._lock:
            files = self._files(create=True)
            await self._run(files.set_baseline)
            meta = files.read_meta()
            meta.baseline_at = _stamp(self._now())
            meta.log = {}
            files.write_meta(meta)
        await self._told([], who, "sandbox_baseline")
        return {"baseline_at": meta.baseline_at}

    async def checkpoint(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "action": "save" (default) | "delete"}."""
        given = body if isinstance(body, dict) else {}
        name = rules.check_checkpoint_name(given.get("name"))
        action = str(given.get("action") or "save")
        async with self._lock:
            files = self._files()
            meta = files.read_meta()
            found = meta.checkpoint(name)
            if action == "delete":
                if found is None:
                    raise NotFound(f"No checkpoint is named {name}.")
                await self._run(files.delete_checkpoint, found.name)
                meta.checkpoints.remove(found)
            elif action == "save":
                if not files.exists():
                    raise Conflict("The sandbox is empty: add a table first.")
                await self._run(files.save_checkpoint, name)
                if found is not None:
                    meta.checkpoints.remove(found)
                meta.checkpoints.append(
                    rules.Checkpoint(name, _stamp(self._now()), rules.copied_log(meta.log))
                )
            else:
                raise SandboxError("A checkpoint is saved or deleted.")
            files.write_meta(meta)
        await self._told([], who, f"sandbox_checkpoint_{action}")
        return {"checkpoints": [c.to_json() for c in meta.checkpoints]}

    async def restore(self, body: Any, who: str = "user") -> dict[str, Any]:
        given = body if isinstance(body, dict) else {}
        name = rules.check_checkpoint_name(given.get("name"))
        async with self._lock:
            files = self._files()
            meta = files.read_meta()
            found = meta.checkpoint(name)
            if found is None or not await self._run(files.restore_checkpoint, found.name):
                raise NotFound(f"No checkpoint is named {name}.")
            rules.unmade(meta, await self._run(files.table_names))
            await self._keys_back(files, meta)
            meta.log = rules.copied_log(found.log)
            files.write_meta(meta)
        await self._told(sorted(meta.tables), who, "sandbox_restore")
        return {"restored": found.name, "log": rules.log_json(meta.log)}

    # ===== Grids, and DuckDB SQL =====

    async def open_grid(self, body: Any, who: str = "user") -> dict[str, Any]:
        name = rules.check_table_name((body or {}).get("table") if isinstance(body, dict) else body)
        files = self._files()
        real = await self._run(files.table_name, name)
        if real is None:
            raise NotFound(f"The sandbox has no table named {name}.")
        arrow = await self._run(files.arrow, real)
        shown = await self._sources.show(rules.grid_name(real), arrow, False, self._designation(files, real))
        return shown | {"table": real}

    @staticmethod
    def _designation(files: Files, table: str) -> str:
        """A sandbox table's designation and origin, for its grid's lineage: "orders · sandbox: A sandbox
        variant of orders (Warehouse), copied 2026-11-21 14:02", or "orders in the Sandbox"."""
        info = files.read_meta().tables.get(table, {})
        variant = info.get("variant")
        if not variant:
            return f"{table} in the {rules.NAME}"
        return f"{variant.get('title') or table}: {rules.origin_words(variant)}"

    def copy_now(self, target: Any) -> None:
        """The sandbox as it is now, copied whole (a local sandbox API's export, on the user's tick; called
        off
        the loop: the file's own lock keeps it whole)."""
        self._files().copy_to(target)

    async def read_table(self, name: str) -> Any:
        """A sandbox table whole, as Arrow ([Sandbox].orders in DuckDB SQL)."""
        files = self._files()
        real = await self._run(files.table_name, name)
        if real is None:
            raise LookupError(f"The sandbox has no table named {name}.")
        return await self._run(files.arrow, real)

    # ===== the API's data door (DataDoor, below), and what it asks of the sandbox =====

    def open_files(self) -> Files:
        """The open project's sandbox file (Conflict: no project open)."""
        return self._files()

    async def run(self, fn: Callable[..., Any], *args: Any) -> Any:
        """One call on the sandbox's file, off the loop."""
        return await self._run(fn, *args)

    @property
    def lock(self) -> asyncio.Lock:
        """Held while a write changes the file and its sandbox.json together."""
        return self._lock

    def stamp(self) -> str:
        return _stamp(self._now())

    async def wrote(self, tables: list[str]) -> None:
        """Tables a write through the door changed: the pages, the listeners and their open grids told."""
        await self._told(tables, "", "")

    # ===== edited in its grid (the owner approved "Edit sandbox rows in a grid", 2026-11-21) =====

    async def edit(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A sandbox table changed from its grid, a sandbox write like an API's (counted in the change log;
        Reset undoes it):
          {"table", "op": "update", "row": n, "column", "value"}   the cell at row n of its open grid's view
          {"table", "op": "update", "where": {...}, "values": {...}}
          {"table", "op": "insert", "values": {column: value}}     a new row (the rest blank)
          {"table", "op": "delete", "rows": [n, ...]} | {"where": {...}}
        Each value is checked against its column's type first: a bad one is refused in one sentence and
        nothing is written."""
        given = body if isinstance(body, dict) else {}
        op = str(given.get("op") or "update")
        files = self._files()
        table, _ = await self._table(files, given.get("table"))
        types = {str(c["name"]): str(c["type"]) for c in await self._run(files.columns, table)}
        columns = list(types)
        statements: list[rules.Statement] = []
        if op == "update" and given.get("where") is not None:
            values = await self._typed(files, types, given.get("values"))
            statements = [rules.edit_update_where(table, columns, values, given.get("where"))]
        elif op == "update":
            column = self._column(types, given.get("column"))
            [(value, cast)] = (await self._typed(files, types, {column: given.get("value")})).values()
            [row] = await self._shown(table, columns, [given.get("row")])
            statements = [rules.edit_update(table, columns, row, column, value, cast)]
        elif op == "insert":
            statements = [
                rules.edit_insert(table, await self._typed(files, types, given.get("values") or {}))
            ]
        elif op == "delete" and given.get("where") is not None:
            statements = [rules.delete_statement(table, columns, given.get("where"))]
        elif op == "delete":
            wanted = given.get("rows", given.get("row"))
            shown = await self._shown(table, columns, wanted if isinstance(wanted, list) else [wanted])
            statements = [rules.edit_delete(table, columns, row) for row in shown]
        else:
            raise SandboxError("An edit is update, insert or delete.")
        async with self._lock:
            try:
                [changed] = await self._run(files.write, [statements])
            except Exception as error:  # DuckDB's own words (a key taken, a blank key): nothing was written
                raise SandboxError(rules.db_words(error)) from error
            if op == "insert":
                changed = max(changed, 1)
            meta = files.read_meta()
            if changed:
                rules.noted(meta.log, table, op, changed)
                rules.touched(meta, [table], _stamp(self._now()))
                files.write_meta(meta)
        if not changed:
            await self._follow([table])
            raise Conflict(f"That row of {table} changed since it was shown: it is shown again.")
        await self._told([table], who, "sandbox_edit", rows=changed, op=op)
        return {"table": table, "op": op, "rows": changed, "log": rules.log_json(meta.log)}

    @staticmethod
    def _column(types: dict[str, str], wanted: Any) -> str:
        by_case = {c.casefold(): c for c in types}
        found = by_case.get(str(wanted or "").casefold())
        if found is None:
            raise SandboxError(f"There is no column named {wanted}.")
        return found

    async def _typed(self, files: Files, types: dict[str, str], raw: Any) -> dict[str, tuple[Any, str]]:
        """Each value sent, checked against its column's type (DuckDB's TRY_CAST): (value, its CAST)."""
        if not isinstance(raw, dict):
            raise SandboxError("values is a dict of column to value.")
        out: dict[str, tuple[Any, str]] = {}
        for wanted, sent in raw.items():
            column = self._column(types, wanted)
            cast = rules.editable_type(column, types[column])
            value = rules.cell_value(sent, types[column])
            if value is not None and rules.is_nested(cast):  # a wrong shape: DuckDB's cast refuses it
                check = rules.Statement(f"SELECT {rules.cast_mark(cast)} IS NULL AS bad", [value])
                try:
                    await self._run(files.query, check, 1)
                except Exception as error:
                    said = str(error).split("\n")[0].split(": ", 1)[-1]
                    raise SandboxError(f"{rules.not_a(column, sent, types[column])} ({said})") from None
            elif value is not None:
                check = rules.Statement(f"SELECT TRY_CAST(? AS {cast}) IS NULL AS bad", [value])
                try:
                    _, _, found, _ = await self._run(files.query, check, 1)
                except Exception:  # a value DuckDB cannot even bind
                    found = [[True]]
                if found and found[0][0]:
                    raise SandboxError(rules.not_a(column, sent, types[column]))
            out[column] = (value, cast)
        return out

    async def _shown(self, table: str, columns: list[str], wanted: list[Any]) -> list[list[Any]]:
        """The rows at these places in the table's open grid's view, each in the table's column order."""
        grid = rules.grid_name(table)
        if self.ws.grids.first_for(grid) is None:
            raise NotFound(
                f"Open {table} on the Tables page first (Open in Tables), or say which rows with where."
            )
        places: list[int] = []
        for w in wanted[:500]:
            if isinstance(w, bool) or not isinstance(w, int) or w < 0:
                raise SandboxError("A row is its place in the table as shown: 0 for the first.")
            places.append(w)
        if not places:
            raise SandboxError("Say which rows.")
        shown, rows = await self._sources.view_rows(grid, places)
        if sorted(c.casefold() for c in shown) != sorted(c.casefold() for c in columns):
            raise SandboxError(
                f"{table}'s tab has steps that change its columns: turn them off to edit it there, or say "
                "which rows with where."
            )
        at = {c.casefold(): i for i, c in enumerate(shown)}
        out = []
        for place, row in zip(places, rows, strict=True):
            if row is None:
                raise NotFound(f"{table}'s tab has no row {place + 1}.")
            out.append([row[at[c.casefold()]] for c in columns])
        return out

    # ===== the Sandbox's card on the Connections page =====

    def heard(self, message: Mapping[str, Any]) -> None:
        """A live notice. A project closed: its sandbox's file let go (one process at a time holds a
        DuckDB file, so sandbox_connections.py can run on it outside the app)."""
        if message.get("type") == "project_changed" and self.folder() is None:
            self.close()

    def cards(self) -> list[dict[str, Any]]:
        """The Connections page's extra cards: the Sandbox's, while a project is open."""
        card = self.card()
        return [card] if card is not None else []

    def colours(self) -> list[tuple[str, str]]:
        """The Sandbox's fixed colour (its own indigo, none of the palette's), while a project is open."""
        return [(rules.NAME, rules.COLOUR)] if self.folder() else []

    def card(self) -> dict[str, Any] | None:
        """The project's Sandbox as a connection's card (None with no project open): its tables, the change
        log, local test data never live. From sandbox.json alone: no query."""
        if self._project() is None:
            return None
        meta = self._files().read_meta()
        return {
            "name": rules.NAME,
            "connection": rules.CONNECTION_TYPE,
            "type": "Sandbox",
            "tables_kind": rules.CONNECTION_TYPE,
            "status": "works",
            "words": rules.CARD_WORDS,
            "tables": len(meta.tables),
            "log_words": rules.log_words(meta.log),
            "colour": rules.COLOUR,
            "calls": {},
            "local": [],
        }

    # ===== a mock client's: its connection's tables, its own SQL, OData, FetchXML, a list's filters =====

    async def client(self, connection: Any) -> dict[str, Any]:
        """What `connection(name)` is mocked as: the connection's kind, template and dialect, and the
        sandbox's tables read from it (a plain DuckDB client: every table, for "Sandbox" or none)."""
        files = self._files()
        meta = files.read_meta()
        tables = await self._run(files.table_names)
        name = str(connection or "").strip()
        if not name or name.casefold() == rules.NAME.casefold():
            return {"kind": rules.PLAIN, "connection": rules.NAME, "dialect": "duckdb", "tables": tables}

        def source(t: str) -> str:
            return str((meta.tables.get(t, {}).get("client") or {}).get("connection") or "")

        mine = [t for t in tables if source(t).casefold() == name.casefold()]
        if not mine:
            raise NotFound(
                f"The sandbox has no table read from {name}: Add to sandbox one of its tables first "
                "(its Table row's Add to sandbox, or the sandbox's Add table…)."
            )
        client = dict(meta.tables[mine[0]].get("client") or {})
        return client | {"tables": mine, "dialect": client.get("dialect") or "duckdb"}

    async def _table(self, files: Files, wanted: Any) -> tuple[str, list[str]]:
        name = rules.check_table_name(wanted)
        real = await self._run(files.table_name, name)
        if real is None:
            raise NotFound(f"The sandbox has no table named {name}.")
        return real, [c["name"] for c in await self._run(files.columns, real)]


class SandboxCore(Protocol):
    """What the data door asks of the sandbox (Sandbox): its connection's mock, its file, a call off the loop,
    the write lock, a stamp, the pages told of a write, the audit log."""

    ws: Any

    async def client(self, connection: Any) -> dict[str, Any]: ...

    def open_files(self) -> Files: ...

    async def run(self, fn: Callable[..., Any], *args: Any) -> Any: ...

    @property
    def lock(self) -> asyncio.Lock: ...

    def stamp(self) -> str: ...

    async def wrote(self, tables: list[str]) -> None: ...


class DataDoor:
    """The adapter's door into the project's sandbox (Plans/adapter.plan.md): what a local sandbox API's
    adapter.Remote reads, queries and writes through /sandbox/data/<key>/ (tables, read, query, write,
    write_all), each table one a connection is mocked over; every write counted in the change log as any API
    write is (Reset undoes it). Split from Sandbox (craft review 2026-11-22), which keeps the tables, Reset,
    checkpoints and the grid."""

    def __init__(self, sandbox: SandboxCore) -> None:
        self._sandbox = sandbox

    async def _one_of(self, connection: Any, wanted: Any) -> str:
        """The sandbox table `wanted` (any case) among those `connection` is mocked over."""
        client = await self._sandbox.client(connection)
        listed: list[str] = list(client["tables"])
        by_case = {t.casefold(): t for t in listed}
        asked = str(wanted or "").casefold()
        # a name in its source's schema (dbo.orders) is the sandbox table read from it (orders)
        table = by_case.get(asked) or by_case.get(asked.rpartition(".")[2])
        if table is None:
            has = ", ".join(client["tables"][:12]) or "none"
            raise NotFound(
                f"The sandbox has no table {wanted} from {client.get('connection')} (it has: {has})."
            )
        return table

    async def source_tables(self, body: Any) -> dict[str, Any]:
        """The adapter's tables(source) for one connection: each table's columns, types and key."""
        given = body if isinstance(body, dict) else {}
        client = await self._sandbox.client(given.get("connection"))
        files = self._sandbox.open_files()
        return {
            "tables": [
                {"name": t, "columns": await self._sandbox.run(files.columns, t)} for t in client["tables"]
            ]
        }

    async def read_arrow(self, body: Any) -> tuple[Any, tuple[str, ...]]:
        """The adapter's read: {"connection", "table", "plan"}; the batches as DuckDB makes them (a reader the
        route streams), and the plan's parts folded."""
        given = body if isinstance(body, dict) else {}
        table = await self._one_of(given.get("connection"), given.get("table"))
        files = self._sandbox.open_files()
        try:
            found: tuple[Any, tuple[str, ...]] = await self._sandbox.run(files.read, table, given.get("plan"))
        except ValueError:
            raise
        except Exception as error:  # DuckDB's own words (a type a filter's value does not cast to)
            raise SandboxError(rules.db_words(error)) from error
        return found

    async def write_arrow(self, given: dict[str, str], data: bytes, who: str = "api") -> dict[str, int]:
        """The adapter's write: an Arrow IPC stream's rows into one table ({"connection", "table", "key",
        "mode"}), counted in the change log as any API write is (Reset undoes it)."""
        table = await self._one_of(given.get("connection"), given.get("table"))
        key = [k for k in str(given.get("key") or "").split(",") if k]
        mode = str(given.get("mode") or "insert")
        files = self._sandbox.open_files()
        async with self._sandbox.lock:
            try:
                counts: dict[str, int] = await self._sandbox.run(files.write_arrow, table, data, key, mode)
            except ValueError:
                raise
            except Exception as error:  # DuckDB's own words (a key taken, a type): nothing was written
                raise SandboxError(rules.db_words(error)) from error
            meta = files.read_meta()
            for op, counted in (("insert", "inserted"), ("update", "updated"), ("delete", "deleted")):
                rules.noted(meta.log, table, op, counts[counted])
            rows = sum(counts.values())
            rules.touched(meta, [table] if rows else [], self._sandbox.stamp())
            files.write_meta(meta)
        await self._sandbox.wrote([table])
        self._sandbox.ws.audit.write(who, "sandbox_write", table, rows=rows)
        return counts

    async def write_all_arrow(
        self, connection: Any, writes: list[dict[str, Any]], who: str = "api"
    ) -> list[dict[str, int]]:
        """The adapter's write_all: several writes ({"table", "key", "mode", "data": an Arrow IPC stream's
        bytes}) in one transaction, all or none; each counted in the change log as any API write is."""
        planned = []
        for given in writes:
            table = await self._one_of(connection, given.get("table"))
            key = [str(k) for k in given.get("key") or []]
            planned.append((table, given["data"], key, str(given.get("mode") or "insert")))
        files = self._sandbox.open_files()
        async with self._sandbox.lock:
            try:
                done: list[dict[str, int]] = await self._sandbox.run(files.write_all_arrow, planned)
            except ValueError:
                raise
            except Exception as error:  # DuckDB's own words (a key taken, a type): nothing was written
                raise SandboxError(rules.db_words(error)) from error
            meta = files.read_meta()
            for (table, _, _, _), counts in zip(planned, done, strict=True):
                for op, counted in (("insert", "inserted"), ("update", "updated"), ("delete", "deleted")):
                    rules.noted(meta.log, table, op, counts[counted])
            changed = [t for (t, _, _, _), c in zip(planned, done, strict=True) if sum(c.values())]
            rules.touched(meta, list(dict.fromkeys(changed)), self._sandbox.stamp())
            files.write_meta(meta)
        await self._sandbox.wrote(list(dict.fromkeys(t for t, _, _, _ in planned)))
        for (table, _, _, _), counts in zip(planned, done, strict=True):
            self._sandbox.ws.audit.write(who, "sandbox_write", table, rows=sum(counts.values()))
        return done

    async def query_arrow(self, body: Any, who: str = "api") -> Any:
        """The adapter's query: {"connection", "sql", "params"}: the connection's own SQL and marks made
        DuckDB SQL over the sandbox's tables it is mocked over (domain/sandbox_dialects.py, this backend's
        half of the adapter); a read streamed as DuckDB makes it, a write counted in the change log as any
        API write is (Reset undoes it), a view, a query's table or a sequence made or dropped as before. What
        cannot be emulated is refused in one sentence with its line."""
        given = body if isinstance(body, dict) else {}
        client = await self._sandbox.client(given.get("connection"))
        dialect = str(client.get("dialect") or "duckdb")
        params = given.get("params") or []
        if not isinstance(params, (list, dict)):
            raise SandboxError("params is a list (for its marks) or a dict (for its names).")
        made = dialects.to_duckdb(given.get("sql"), dialect, params, client["tables"])
        if str(client.get("kind") or "") in ("dataverse", "dataverse_web") and made.kind != "select":
            raise SandboxError("Dataverse's SQL endpoint is read-only: SELECT only.")
        files = self._sandbox.open_files()
        if dialects.is_definition(made.kind):
            await self._define(files, made, client)
            return files.counted(0)
        if made.kind == "select":
            try:
                return await self._sandbox.run(files.query_arrow, made.sql, made.params)
            except Exception as error:  # DuckDB's own words (a missing column, a type)
                raise SandboxError(rules.db_words(error)) from error
        async with self._sandbox.lock:
            try:
                answer, count = await self._sandbox.run(files.change_arrow, made.sql, made.params)
            except Exception as error:  # DuckDB's own words: nothing was written
                raise SandboxError(rules.db_words(error)) from error
            meta = files.read_meta()
            rules.noted(meta.log, made.table or "", made.kind, count)
            if count and made.table:
                rules.touched(meta, [made.table], self._sandbox.stamp())
            files.write_meta(meta)
        touched = [made.table] if made.table else []
        await self._sandbox.wrote(touched)
        self._sandbox.ws.audit.write(who, "sandbox_write", ", ".join(touched), rows=count)
        return answer.to_reader()

    async def _define(
        self, files: Files, made: dialects.Translated, client: dict[str, Any]
    ) -> dict[str, Any]:
        """A view, a query's table or a sequence made or dropped through a mock (the test app's gap 8): never
        over a table the user added (only what an API made is replaced or dropped); a view or table made is
        that connection's table from then on (sandbox.json: source "made"); Reset and Restore undo it."""
        verb, what = made.kind.split(" ", 1)
        name = str(made.table)
        async with self._sandbox.lock:
            meta = files.read_meta()
            mine = next((t for t in meta.tables if t.casefold() == name.casefold()), None)
            by_api = mine is not None and (meta.tables[mine].get("source") or {}).get("kind") == "made"
            there = await self._sandbox.run(files.kind_of, name)
            if there in ("table", "view") and not by_api:
                raise SandboxError(rules.not_made(name, verb))
            try:
                await self._sandbox.run(files.define, made.sql, made.params)
            except Exception as error:  # DuckDB's own words (it is there already, or not there)
                raise SandboxError(rules.db_words(error)) from error
            if mine is not None and (verb == "drop" or mine != name):
                meta.tables.pop(mine, None)
                meta.log.pop(mine, None)
            if verb == "create" and what in ("view", "table"):
                kept = {k: v for k, v in client.items() if k != "tables"}
                meta.tables[name] = rules.made_record(what, kept, self._sandbox.stamp())
            files.write_meta(meta)
        await self._sandbox.wrote([name] if what != "sequence" else [])
        self._sandbox.ws.audit.write("api", "sandbox_define", name, what=made.kind)
        return {"kind": made.kind, "table": name}


class SandboxAlias:
    """[Sandbox] in DuckDB SQL: the open project's sandbox as a dataset connection name (services/hooks.py
    DatasetAlias). Its words carry the sandbox's version, so a read after a write is read again."""

    tables_kind = rules.CONNECTION_TYPE  # a real connection kind (domain/connection_tables.py TABLE_KINDS)

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def words(self) -> str:
        return f"the project's sandbox, version {self._sandbox.version}"

    async def tables(self) -> list[str]:
        return await self._sandbox.names()

    async def read(self, table: str) -> Any:
        return await self._sandbox.read_table(table)

    async def dax(self, query: str) -> Any:
        raise LookupError("The sandbox is DuckDB: query it with SQL, not DAX.")
