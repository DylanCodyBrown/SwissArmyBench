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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import sandbox as rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.sandbox import SandboxError
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace


class Files(Protocol):
    """adapters/sandbox.py SandboxFiles."""

    def exists(self) -> bool: ...

    def close(self) -> None: ...

    def read_meta(self) -> rules.Meta: ...

    def write_meta(self, meta: rules.Meta) -> None: ...

    def tables(self) -> list[dict[str, Any]]: ...

    def columns(self, table: str) -> list[dict[str, Any]]: ...

    def table_name(self, wanted: str) -> str | None: ...

    def put_table(self, name: str, table: Any, replace: bool) -> int: ...

    def create_empty(self, name: str, columns: Any, replace: bool) -> None: ...

    def drop(self, name: str) -> None: ...

    def arrow(self, name: str) -> Any: ...

    def query(
        self, statement: rules.Statement, limit: int
    ) -> tuple[list[str], list[str], list[list[Any]], bool]: ...

    def change(self, statement: rules.Statement) -> tuple[list[str], list[str], list[list[Any]]]: ...

    def write(self, groups: Any) -> list[int]: ...

    def set_baseline(self) -> None: ...

    def reset(self) -> bool: ...

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


async def _no_structure(structure: str, path: str) -> tuple[Any, str, str]:
    raise LookupError("Structures are not here.")


async def _no_rows(name: str, rows: list[int]) -> tuple[list[str], list[list[Any] | None]]:
    raise LookupError("That table is not open in Grids.")


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

    async def grid_view(self, name: str) -> Any:
        return await self.grid_view_fn(name)

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
        approvals: Any,
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
        self._ignore = ignore  # the project's .gitignore lines for .sab/sandbox/ (written once)
        self._now = now
        self._open: tuple[str, Files] | None = None
        self._lock = asyncio.Lock()
        self.version = 0  # every change: [Sandbox]'s reads in DuckDB SQL are read again
        self.changed: list[Callable[[list[str]], Awaitable[None]]] = []  # tables a write touched

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
        }

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
            meta.log.pop(name, None)
            # A table added is part of the baseline: Reset gives it back as it came in.
            await self._run(files.set_baseline)
            meta.baseline_at = _stamp(self._now())
            files.write_meta(meta)
        await self._told([name], who, "sandbox_add", rows=rows, source=kind)
        return {"added": name, "rows": rows, "sql": f"[{rules.NAME}].{name}"}

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
        if who == "agent" and not await self._approvals.ask(
            rules.NAME,
            "reset the sandbox",
            f"Put every sandbox table back to the baseline ({rules.log_words(meta.log)})",
        ):
            raise Refused("The user declined (or did not answer): the sandbox is as it was.")
        async with self._lock:
            if not await self._run(files.reset):
                raise Conflict("The sandbox has no baseline yet: add a table first.")
            undone = rules.log_json(meta.log)
            rules.touched(meta, [t for t in meta.log if meta.log[t].any], _stamp(self._now()))
            meta.log = {}
            files.write_meta(meta)
        await self._told(sorted(meta.tables), who, "sandbox_reset")
        return {"reset": True, "undone": undone}

    async def _reset_one(self, files: Files, meta: rules.Meta, wanted: str, who: str) -> dict[str, Any]:
        table, _ = await self._table(files, wanted)
        counts = meta.log.get(table, rules.Counts())
        if who == "agent" and not await self._approvals.ask(
            rules.NAME,
            "reset a sandbox table",
            f"Put {table} back to the baseline ({rules.log_words({table: counts})})",
        ):
            raise Refused("The user declined (or did not answer): the table is as it was.")
        async with self._lock:
            if not await self._run(files.reset_table, table):
                raise Conflict(f"{table} is not in the baseline: Set as baseline first.")
            meta = files.read_meta()
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

    # ===== an API's reads and writes =====

    async def data(self, body: Any, who: str = "api") -> dict[str, Any]:
        """One call of a mock client's: {"op": "query", "sql", "params"} | {"op": "table", "table",
        "where"?, "limit"?, "offset"?} | {"op": "insert"|"update"|"delete", "table", ...} |
        {"op": "batch", "ops": [...]}
        (the writes of data.transaction(), all or none). Rows answer as records."""
        given = body if isinstance(body, dict) else {}
        op = str(given.get("op") or "")
        files = self._files()
        if op == "query":
            sql = rules.check_read(given.get("sql"), self._parse)
            params = given.get("params") or []
            if not isinstance(params, (list, dict)):
                raise SandboxError("params is a list (for ?) or a dict (for $name).")
            return await self._read(files, rules.Statement(sql, params))  # type: ignore[arg-type]
        if op == "table":
            table, columns = await self._table(files, given.get("table"))
            return await self._read(
                files,
                rules.table_read(table, columns, given.get("where"), given.get("limit"), given.get("offset")),
            )
        if op == "columns":
            table, _ = await self._table(files, given.get("table"))
            return {"table": table, "columns": await self._run(files.columns, table)}
        if op == "tables":
            return {"tables": [t["name"] for t in await self._run(files.tables)]}
        if op == "client":
            return await self.client(given.get("connection"))
        if op == "sql":
            return await self._sql(files, given)
        if op in ("odata", "fetchxml", "list"):
            return await self._shaped(files, op, given)
        ops = given.get("ops") if op == "batch" else [given]
        if not isinstance(ops, list) or not ops or len(ops) > 500:
            raise SandboxError("A transaction holds 1 to 500 writes.")
        planned: list[tuple[str, str, list[rules.Statement]]] = []
        for one in ops:
            if not isinstance(one, dict):
                raise SandboxError("Each write is {op, table, ...}.")
            planned.append(await self._plan(files, one))
        async with self._lock:
            try:
                counts = await self._run(files.write, [p[2] for p in planned])
            except Exception as error:  # DuckDB's own words (a key taken, a type): nothing was written
                raise SandboxError(str(error).split("\n")[0]) from error
            meta = files.read_meta()
            for (kind, table, _), n in zip(planned, counts, strict=True):
                rules.noted(meta.log, table, kind, n)
            rules.touched(
                meta, [p[1] for p, n in zip(planned, counts, strict=True) if n], _stamp(self._now())
            )
            files.write_meta(meta)
        touched = sorted({p[1] for p in planned})
        await self._told(touched, "", "")
        self.ws.audit.write(who, "sandbox_write", ", ".join(touched), rows=sum(counts))
        return {"counts": counts, "rows": sum(counts)}

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
            plain = {c: v for c, (v, _) in values.items()}
            statements = [rules.update_statement(table, columns, plain, given.get("where"))]
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
                raise SandboxError(str(error).split("\n")[0]) from error
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
            if value is not None:
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
            raise NotFound(f"Open {table} in Grids first (Open in Grids), or say which rows with where.")
        places: list[int] = []
        for w in wanted[:500]:
            if isinstance(w, bool) or not isinstance(w, int) or w < 0:
                raise SandboxError("A row is its place in the grid: 0 for the first.")
            places.append(w)
        if not places:
            raise SandboxError("Say which rows.")
        shown, rows = await self._sources.view_rows(grid, places)
        if sorted(c.casefold() for c in shown) != sorted(c.casefold() for c in columns):
            raise SandboxError(
                f"{table}'s grid has steps that change its columns: turn them off to edit it there, or say "
                "which rows with where."
            )
        at = {c.casefold(): i for i, c in enumerate(shown)}
        out = []
        for place, row in zip(places, rows, strict=True):
            if row is None:
                raise NotFound(f"{table}'s grid has no row {place + 1}.")
            out.append([row[at[c.casefold()]] for c in columns])
        return out

    # ===== the Sandbox's card on the Connections page =====

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
        tables = [t["name"] for t in await self._run(files.tables)]
        name = str(connection or "").strip()
        if not name or name.casefold() == rules.NAME.casefold():
            return {"kind": rules.PLAIN, "connection": rules.NAME, "dialect": "duckdb", "tables": tables}

        def source(t: str) -> str:
            return str((meta.tables.get(t, {}).get("client") or {}).get("connection") or "")

        mine = [t for t in tables if source(t).casefold() == name.casefold()]
        if not mine:
            raise NotFound(
                f"The sandbox has no table read from {name}: Add to sandbox one of its tables first "
                "(its grid's Add to sandbox, or the sandbox's Add table…)."
            )
        client = dict(meta.tables[mine[0]].get("client") or {})
        return client | {"tables": mine, "dialect": client.get("dialect") or "duckdb"}

    async def _sql(self, files: Files, given: dict[str, Any]) -> dict[str, Any]:
        client = await self.client(given.get("connection"))
        dialect = str(given.get("dialect") or client.get("dialect") or "duckdb")
        made = dialects.to_duckdb(given.get("sql"), dialect, given.get("params"), client["tables"])
        statement = rules.Statement(made.sql, made.params)
        if made.kind == "select":
            return await self._read(files, statement, records=False) | {"kind": "select"}
        async with self._lock:
            try:
                columns, types, rows = await self._run(files.change, statement)
            except Exception as error:  # DuckDB's own words: nothing was written
                raise SandboxError(str(error).split("\n")[0]) from error
            count = len(rows) if columns and columns[0].lower() != "count" else int(rows[0][0]) if rows else 0
            meta = files.read_meta()
            rules.noted(meta.log, made.table or "", made.kind, count)
            if count and made.table:
                rules.touched(meta, [made.table], _stamp(self._now()))
            files.write_meta(meta)
        touched = [made.table] if made.table else []
        await self._told(touched, "", "")
        self.ws.audit.write("api", "sandbox_write", ", ".join(touched), rows=count)
        returned = columns and columns[0].lower() != "count"
        return {
            "kind": made.kind,
            "rowcount": count,
            "columns": columns if returned else [],
            "types": types if returned else [],
            "rows": [[_plain(v) for v in r] for r in rows] if returned else [],
        }

    async def _shaped(self, files: Files, op: str, given: dict[str, Any]) -> dict[str, Any]:
        client = await self.client(given.get("connection"))
        tables = client["tables"]
        if op == "fetchxml":
            columns_of: dict[str, list[str]] = {}
            for t in tables:
                columns_of[t] = [c["name"] for c in await self._run(files.columns, t)]
            fetch = dialects.fetchxml(given.get("fetch_xml"), tables, lambda t: columns_of[t])
            return await self._read(files, rules.Statement(fetch.sql, fetch.params)) | {"table": fetch.table}
        wanted = str(given.get("table") or "")
        known = {t.casefold(): t for t in tables}
        table = known.get(wanted.casefold())
        if table is None:
            has = ", ".join(tables[:12]) or "none"
            raise NotFound(
                f"The sandbox has no table {wanted} from {client.get('connection')} (it has: {has})."
            )
        columns = [c["name"] for c in await self._run(files.columns, table)]
        if op == "odata":
            where, params = dialects.odata_where(given.get("filter"), columns)
            order = dialects.order_by(given.get("order_by"), columns)
        else:
            where, params = dialects.list_where(given.get("filters"), columns)
            order = ""
        by_case = {c.casefold(): c for c in columns}
        picked = []
        for c in given.get("columns") or []:
            real = by_case.get(str(c).casefold())
            if real is None:
                raise SandboxError(f"{table} has no column {c!r}.")
            picked.append(real)
        listed = ", ".join(rules.quote(c) for c in picked) if picked else "*"
        clause = f" WHERE {where}" if where else ""
        count_sql = f"SELECT count(*) AS n FROM {rules.quote(table)}{clause}"  # noqa: S608 (checked names)
        total = (await self._read(files, rules.Statement(count_sql, params)))["rows"][0]["n"]
        sql = f"SELECT {listed} FROM {rules.quote(table)}{clause}"  # noqa: S608 (checked names, bound values)
        if order:
            sql += f" ORDER BY {order}"
        limit = given.get("limit")
        if limit is not None:
            sql += f" LIMIT {max(0, int(limit))}"
        return await self._read(files, rules.Statement(sql, params)) | {"total": total, "table": table}

    async def _table(self, files: Files, wanted: Any) -> tuple[str, list[str]]:
        name = rules.check_table_name(wanted)
        real = await self._run(files.table_name, name)
        if real is None:
            raise NotFound(f"The sandbox has no table named {name}.")
        return real, [c["name"] for c in await self._run(files.columns, real)]

    async def _plan(self, files: Files, one: dict[str, Any]) -> tuple[str, str, list[rules.Statement]]:
        kind = str(one.get("op") or "")
        table, columns = await self._table(files, one.get("table"))
        every = bool(one.get("all"))
        if kind == "insert":
            return kind, table, rules.insert_statements(table, columns, one.get("rows", one.get("row")))
        if kind == "update":
            return (
                kind,
                table,
                [rules.update_statement(table, columns, one.get("values"), one.get("where"), every)],
            )
        if kind == "delete":
            return kind, table, [rules.delete_statement(table, columns, one.get("where"), every)]
        raise SandboxError("A write is insert, update or delete.")

    async def _read(self, files: Files, statement: rules.Statement, records: bool = True) -> dict[str, Any]:
        try:
            columns, types, rows, cut = await self._run(files.query, statement, rules.MAX_ROWS_ANSWERED)
        except SandboxError:
            raise
        except Exception as error:  # DuckDB's own words (a missing column, a type)
            raise SandboxError(str(error).split("\n")[0]) from error
        return {
            "columns": columns,
            "types": types,
            "rows": [{c: _plain(v) for c, v in zip(columns, r, strict=True)} for r in rows]
            if records
            else [[_plain(v) for v in r] for r in rows],
            "cut": cut,
        }


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
