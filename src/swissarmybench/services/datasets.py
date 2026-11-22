"""Datasets: the ways data arrives (a push, a file, pasted text, a query over the open tables), and
listing and closing what is open.

Every way in ends in `store_table`: store, pick a grid, tell the pages, write the audit log. A push
reuses the dataset's first grid (that grid hot-reloads in place) unless a new one is asked for. The
first grid on a dataset starts with no steps.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import sample_data, variable_refs
from swissarmybench.domain.datasets import DatasetError, DatasetInfo, Opened, mib, quote, validate_name
from swissarmybench.domain.grids import Grid
from swissarmybench.domain.sql_guard import SqlRefused, guard
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.ports import BACKGROUND, INTERACTIVE, SqlSession
from swissarmybench.services.processes import ProcessRegistry
from swissarmybench.services.table_cells import Origins
from swissarmybench.services.workspace import Conflict, NotFound, Refused, TimedOut, Workspace


class SqlBinder(Protocol):
    async def bind(
        self, sql: str, dialect: str = ..., style: str = ..., where: str = ...
    ) -> tuple[str, Any]: ...

    async def resolve(self, text: str, where: str = ...) -> str: ...


class TableReader(Protocol):
    """Bytes, files and text to a table (adapters/datasets.py: Arrow, CSV, Excel, Parquet, JSON)."""

    def arrow_stream_to_table(self, body: bytes, max_bytes: int) -> Any: ...

    def split_json_to_arrow(self, payload: Any) -> Any: ...

    def rows_to_arrow(
        self, columns: list[str], rows: list[list[Any]], dates: tuple[str, ...] = ()
    ) -> Any: ...

    def load_file(self, path_text: str, max_bytes: int, sheet: str | None = None) -> tuple[Any, str]: ...

    def load_adapted(self, path_text: str, max_bytes: int, sheet: str | None = None) -> tuple[Any, str]: ...

    def excel_sheets(self, path_text: str) -> list[str]: ...

    def load_bytes(
        self, data: bytes, filename: str, max_bytes: int, sheet: str | None = None
    ) -> tuple[Any, str]: ...

    def excel_sheets_bytes(self, data: bytes, filename: str) -> list[str]: ...

    def parse_pasted(self, text: str, max_bytes: int) -> Any: ...

    def query_table(self, cursor: Any, sql: str, params: Any = None) -> Any: ...

    def file_name(self, path_text: str) -> str: ...


class DatasetService:
    def __init__(
        self,
        ws: Workspace,
        reader: TableReader,
        processes: ProcessRegistry,
        own_file: Callable[[str], bool],
        on_shutdown: Callable[[], None],
    ) -> None:
        self.ws = ws
        self._reader = reader
        self._processes = processes
        # True for a path that is one of Swiss Army Bench's own files (adapters/state_files.py).
        self._own_file = own_file
        self._on_shutdown = on_shutdown
        # Who else names tables: each is told of a rename (the relationship model, bootstrap.py).
        self.renamed: list[Callable[[str, str], Awaitable[None]]] = []
        # Where each table came from, for the load its Workbench cell starts with (table_cells.py).
        self.origins = Origins()
        # Who wants to know a table arrived (its name and grid): a project's steps waiting for it.
        self.stored: list[Callable[[str, str], Awaitable[None]]] = []
        # A query's tables named through a connection, read first (services/connection_tables.py).
        self.connection_sql: ConnectionSql | None = None
        # The Variables page (services/variables.py, set once built): a query's ${NAME} as a bound parameter.
        self.variables: SqlBinder | None = None
        # A table read from a file that changed on disk since (services/file_watch.py), and its Not now.
        self.changed_on_disk: Callable[[str], bool] = lambda name: False
        self.not_now: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None

    # ===== the server itself =====

    def stop(self, who: str) -> None:
        self.ws.audit.write(who, "shutdown")
        self._on_shutdown()

    def activity(self, limit: int, actor: str | None) -> list[dict[str, Any]]:
        """The audit log's last entries, for the page's activity list (never cell values)."""
        return self.ws.audit.tail(limit, actor)

    # ===== what is open =====

    def summary(self, info: DatasetInfo) -> dict[str, Any]:
        return {
            "name": info.name,
            "version": info.version,
            "rows": info.row_count,
            "columns": len(info.columns),
            "bytes": info.nbytes,
            "size": mib(info.nbytes),
            "source_kind": info.source_kind,
            "grids": [g.id for g in self.ws.grids.for_dataset(info.name)],
            # Its file changed on disk since it was read (services/file_watch.py): Reload or Not now.
            "changed_on_disk": self.changed_on_disk(info.name),
        }

    def listing(self) -> dict[str, Any]:
        return {"datasets": [self.summary(i) for i in self.ws.store.all()], "budget": self.ws.budget()}

    async def close(self, name: str, who: str) -> dict[str, Any] | None:
        """Close a dataset and its grids, freeing its memory. None when there is no such dataset."""
        ws = self.ws
        info = ws.store.get(name)
        if not await ws.workers.run(INTERACTIVE, ws.store.close, name):
            return None
        ws.views.forget_dataset(name)
        origin = self.origins.get(name)
        for grid in ws.grids.for_dataset(name):
            # Ctrl+Shift+T: the tab comes back, the table read again from its file when it came from one.
            ws.grids.remember_closed(grid, info.serial if info else -1, *(_file_of(origin) or (None, None)))
            ws.grids.close(grid.id)
        self.origins.forget(name)
        await ws.live.broadcast({"type": "dataset_closed", "dataset": name})
        ws.audit.write(who, "close", name)
        return {"closed": name, "budget": ws.budget()}

    async def reload(self, name: str, who: str, not_now: bool = False) -> dict[str, Any]:
        """Reload (tabs_reload): the table read again from its file, in place: its grids and their steps kept.
        `not_now`: kept as it is (said again when the file changes again)."""
        if not_now:
            if self.not_now is None:
                raise NotFound("Files are not watched here.")
            return await self.not_now(name, who)
        origin = self.origins.get(name)
        found = _file_of(origin)
        if self.ws.store.get(name) is None or found is None:
            raise NotFound(f"No table named {name!r} read from a file is open.")
        result = await self.load_file(name, found[0], found[1], False, who, origin.adapted)
        return result | {"reloaded": name}

    async def reopen(self, who: str) -> dict[str, Any]:
        """Ctrl+Shift+T (tabs_reopen): the last closed tab again, its steps and settings with it: a new grid
        on its table while that is open, else the table read again from its file (this session's memory)."""
        ws = self.ws

        def serial_of(name: str) -> int | None:
            info = ws.store.get(name)
            return info.serial if info is not None else None

        tab = ws.grids.take_closed(serial_of)
        if tab is None:
            raise NotFound("No closed table to reopen.")
        if ws.store.get(tab.dataset) is not None:
            grid = ws.grids.create(tab.dataset, list(tab.steps), tab.settings)
            await ws.live.broadcast({"type": "grid_shown", "grid": grid.id, "dataset": tab.dataset})
            shown = ws.live.shown_or_opening(grid.id) or await ws.live.ask_opener(
                ws.addresses.workspace(grid)
            )
        else:
            loaded = await self.load_file(tab.dataset, tab.path or "", tab.sheet, True, who)
            found = ws.grids.get(str(loaded["grid"]))
            if found is None:
                raise NotFound("The table was read again, but its tab closed meanwhile.")
            grid = found
            grid.steps = list(tab.steps)
            grid.settings = tab.settings
            ws.views.forget_dataset(tab.dataset)
            await ws.live.broadcast({"type": "grid_updated", "grid": grid.id, "by": who, "gen": grid.gen})
            shown = bool(loaded.get("watched"))
        ws.audit.write(who, "reopen", tab.dataset, grid=grid.id, steps=len(tab.steps))
        return {
            "grid": grid.id,
            "dataset": tab.dataset,
            "steps": len(tab.steps),
            "grid_url": ws.addresses.grid(grid, with_token=who != "agent"),
            "shown": shown,
        }

    async def rename(self, name: str, to: Any, who: str) -> dict[str, Any]:
        """Call a table by another name everywhere: its grids (steps and settings kept), the model's
        joins, every page's tabs. A Python session following the old name stops following it."""
        ws = self.ws
        if not isinstance(to, str) or not to.strip():
            raise ValueError('Send {"to": "new_name"}.')
        new = to.strip()
        if ws.store.get(name) is None:
            raise NotFound(f"No dataset named {name!r} is open.")
        validate_name(new)
        if new == name:
            return {"dataset": name, "renamed_from": name}
        others = [i.name for i in ws.store.all() if i.name != name]
        clash = next((n for n in others if n.lower() == new.lower()), None)
        if clash is not None:
            raise Conflict(f"A table named {clash!r} is open. Pick another name, or close that one first.")
        ws.views.forget_dataset(name)  # its cached views name the old table
        info: DatasetInfo = await ws.workers.run(INTERACTIVE, ws.store.rename, name, new)
        grids = ws.grids.rename_dataset(name, new)
        self.origins.rename(name, new)
        for renamed in self.renamed:
            await renamed(name, new)
        await ws.live.broadcast(
            {"type": "dataset_renamed", "dataset": name, "to": new, "grids": [g.id for g in grids]}
        )
        ws.audit.write(who, "rename", name, to=new)
        return self.summary(info) | {"dataset": new, "renamed_from": name}

    # ===== the common end of every way in =====

    async def store_table(
        self,
        name: str,
        table: Any,
        source_kind: str,
        new_grid: bool,
        who: str,
        query: str | None = None,
        follow: bool = False,
        opened: Opened | None = None,
        origin: Origin | None = None,
    ) -> dict[str, Any]:
        """The common end of every way data arrives: store, pick a grid, notify, audit.

        `follow` is a Python session keeping an open table current after its variable was assigned
        again. It refreshes the grid where it is: no jump to the front, and no new tab if the user
        closed the old one (the data stays fresh for when they open it again)."""
        ws = self.ws
        info: DatasetInfo = await ws.workers.run(
            BACKGROUND, ws.store.replace, name, table, source_kind, query, opened
        )
        ws.views.forget_dataset(name)
        if origin is not None:
            self.origins.note(name, origin)
        existing = ws.grids.first_for(name)
        if follow and existing is None:
            await ws.live.dataset_updated(name, info.version)
            ws.audit.write(
                who,
                "push",
                name,
                rows=info.row_count,
                source_kind=info.source_kind,
                bytes=info.nbytes,
                follow=True,
            )
            return {
                "grid_url": None,
                "workspace_url": ws.addresses.workspace(with_token=who != "agent"),
                "grid": None,
                "dataset": name,
                "version": info.version,
                "watched": False,
            }
        grid: Grid
        if new_grid or existing is None:
            grid = ws.grids.create(name)
        else:
            grid = existing
        await ws.live.dataset_updated(name, info.version)
        if follow:
            ws.audit.write(
                who,
                "push",
                name,
                rows=info.row_count,
                source_kind=info.source_kind,
                bytes=info.nbytes,
                follow=True,
            )
            watched = True  # the tab is wherever the user left it
        else:
            # An open workspace adds the grid as a tab (if new) and brings it to the front.
            await ws.live.broadcast({"type": "grid_shown", "grid": grid.id, "dataset": name})
            ws.audit.write(
                who, "push", name, rows=info.row_count, source_kind=info.source_kind, bytes=info.nbytes
            )
            # Nothing shows it yet: VS Code opens the workspace (its window the user was last in), else the
            # desktop app (the browser where the app cannot run).
            watched = ws.live.shown_or_opening(grid.id) or await ws.live.ask_opener(
                ws.addresses.workspace(grid)
            )
        for told in self.stored:
            await told(name, grid.id)
        return {
            "grid_url": ws.addresses.grid(grid, with_token=who != "agent"),
            "workspace_url": ws.addresses.workspace(grid, with_token=who != "agent"),
            "grid": grid.id,
            "dataset": name,
            "version": info.version,
            # Whether the grid is on screen, about to be (a window an earlier push had opened), or
            # being opened now (VS Code, else the desktop app or the browser). False when nothing could.
            "watched": watched,
        }

    # ===== a push =====

    def admit_push(self, name: str, follow: bool, process_id: str) -> None:
        """A follow keeps an open table current. If it was closed (or another session took the name)
        while this push was on its way, drop it: a push would quietly reopen the data."""
        if follow and not (self.ws.store.get(name) is not None and self._processes.owns(process_id, name)):
            raise Conflict("That table is no longer open, so it is not kept current.")

    async def push(
        self,
        name: str,
        arrow: bytes | None,
        payload: Any,
        source_kind: str,
        new_grid: bool,
        who: str,
        follow: bool,
        process_id: str,
        kernel: str = "",
    ) -> dict[str, Any]:
        """Store a pushed table: an Arrow stream (`arrow`), or pandas' orient="split" JSON (`payload`).
        `kernel` is the Workbench kernel it came from (its document holds the table's cell)."""
        ws = self.ws
        if arrow is not None:
            table = await ws.workers.run(
                INTERACTIVE, self._reader.arrow_stream_to_table, arrow, ws.settings.max_dataset_bytes
            )
        else:
            table = await ws.workers.run(INTERACTIVE, self._reader.split_json_to_arrow, payload)
        origin = Origin("python", kernel=kernel or None)
        result = await self.store_table(name, table, source_kind, new_grid, who, follow=follow, origin=origin)
        # A Python session's watcher says which session pushed this (X-Process): that session
        # now follows the dataset, and the Open list shows the table as open.
        if process_id and self._processes.note_loaded(process_id, name):
            await ws.live.broadcast({"type": "processes_changed"})
        return result

    async def store_rows(
        self,
        name: str,
        columns: list[str],
        rows: list[list[Any]],
        who: str,
        dates: tuple[str, ...] = (),
        source_kind: str = "analysis",
    ) -> dict[str, Any]:
        """A table of rows the app itself made (an analysis result opened as a grid, a contract's made-up
        sample), in a tab of its own. `name` is taken as given: the caller picks a free one."""
        ws = self.ws
        table = await ws.workers.run(INTERACTIVE, self._reader.rows_to_arrow, columns, rows, dates)
        return await self.store_table(name, table, source_kind, True, who)

    def free_name(self, wanted: str) -> str:
        """`wanted`, or it with a number, so that no open table has the name."""
        taken = {info.name.lower() for info in self.ws.store.all()}
        name, n = wanted, 2
        while name.lower() in taken:
            name, n = f"{wanted}_{n}", n + 1
        return name

    async def open_sample(self, who: str) -> dict[str, Any]:
        """The made-up sample store (domain/sample_data.py) as open tables, each under a free name: the
        empty pages' Try it with sample data."""
        opened: list[dict[str, Any]] = []
        for table in sample_data.store():
            name = self.free_name(table.name)
            rows = [list(row) for row in table.rows]
            stored = await self.store_rows(name, list(table.columns), rows, who, table.dates, "records")
            opened.append({"name": name, "grid": stored["grid"], "rows": len(rows)})
        return {"tables": opened}

    # ===== a file, pasted text =====

    def _refuse_own_file(self, path: str) -> None:
        """Swiss Army Bench's own files are not tables: the connection file (one line of JSON, so it
        loaded as a table, token and all), the audit log: the state folder, except the
        export folder inside it (an export loaded back is a table)."""
        if self._own_file(path):
            raise Refused("That is one of the grid server's own files, not a table.")

    async def load_file(
        self, name: str, path: str, sheet: str | None, new_grid: bool, who: str, adapted: bool = False
    ) -> dict[str, Any]:
        """A file as a table. `adapted`: a file connection's, read through the adapter's Files (DuckDB's own
        types), and read so again (Reload, the project opened again)."""
        ws = self.ws
        used = await self.resolve_text(path, name)  # ${NAME} in a path (12.7); the origin keeps the text
        self._refuse_own_file(used)
        load = self._reader.load_adapted if adapted else self._reader.load_file
        table, kind = await ws.workers.run(BACKGROUND, load, used, ws.settings.max_dataset_bytes, sheet)
        origin = Origin("file", path=path, sheet=sheet, adapted=adapted)
        result = await self.store_table(name, table, kind, new_grid, who, origin=origin)
        ws.audit.write(who, "load_file", name, file=self._reader.file_name(path), sheet=sheet)
        return result

    async def resolve_text(self, text: str, where: str) -> str:
        """Typed text with its ${NAME} put in from this computer's sources (12.7; `$${X}` is the text ${X});
        MissingVariables for one not set here."""
        if "${" not in text:
            return text
        if self.variables is None:
            return variable_refs.resolve(text, lambda name: None, where)
        return await self.variables.resolve(text, where)

    async def peek_file(self, path: str, sheet: str | None, rows: int) -> dict[str, Any]:
        """A file's first rows (the catalog page's preview): nothing is kept."""
        ws = self.ws
        path = await self.resolve_text(path, "the file")
        self._refuse_own_file(path)
        table, _ = await ws.workers.run(
            BACKGROUND, self._reader.load_file, path, ws.settings.max_dataset_bytes, sheet
        )
        first = table.slice(0, rows)
        return {"columns": list(first.column_names), "rows": [list(r.values()) for r in first.to_pylist()]}

    async def read_file(self, path: str, sheet: str | None) -> Any:
        """A file's whole table (a file connection's table named in DuckDB SQL): nothing is kept."""
        ws = self.ws
        self._refuse_own_file(path)
        table, _ = await ws.workers.run(
            BACKGROUND, self._reader.load_file, path, ws.settings.max_dataset_bytes, sheet
        )
        return table

    async def sheets(self, path: str) -> dict[str, Any]:
        """The sheet names of a workbook, so VS Code can ask which to load."""
        self._refuse_own_file(path)
        return {"sheets": await self.ws.workers.run(BACKGROUND, self._reader.excel_sheets, path)}

    async def load_dropped(
        self, name: str, data: bytes, filename: str, sheet: str | None, who: str
    ) -> dict[str, Any]:
        """A file dropped on the page: its bytes (the browser never gives its path), read in memory
        as Open file reads a path; nothing is written to disk."""
        ws = self.ws
        table, kind = await ws.workers.run(
            BACKGROUND, self._reader.load_bytes, data, filename, ws.settings.max_dataset_bytes, sheet
        )
        origin = Origin("dropped", filename=filename)
        result = await self.store_table(name, table, kind, True, who, origin=origin)
        ws.audit.write(who, "load_file", name, file=filename, sheet=sheet)
        return result

    async def dropped_sheets(self, data: bytes, filename: str) -> dict[str, Any]:
        """A dropped workbook's sheet names, so the page can ask which to open."""
        sheets = await self.ws.workers.run(BACKGROUND, self._reader.excel_sheets_bytes, data, filename)
        return {"sheets": sheets}

    async def paste(self, name: str, text: str, who: str) -> dict[str, Any]:
        ws = self.ws
        table = await ws.workers.run(
            INTERACTIVE, self._reader.parse_pasted, text, ws.settings.max_dataset_bytes
        )
        return await self.store_table(name, table, "clipboard", True, who, origin=Origin("paste"))

    # ===== the "+" tab: a table from a query =====

    async def build_from_query(self, name: str, text: str, replace: bool, who: str) -> dict[str, Any]:
        """Dataset `name` from one SELECT over the open tables, each read as its tab shows it.
        `replace` is the tab's Run again; it rebuilds only a table a query made, so a pushed dataset
        (or another tab's table) is never overwritten by a name clash."""
        ws = self.ws
        settings = ws.settings
        existing = ws.store.get(name)
        if existing is not None and not (replace and existing.query is not None):
            raise DatasetError(f"A dataset named {name!r} already exists; pick a new name.")

        def tab_view(cursor: SqlSession, dataset: str) -> str:
            if dataset == name:
                raise SqlRefused(f"This query builds {name}, so it can't read {name}.")
            # Two tabs on one dataset: the name reads the first (oldest) one.
            grid, info = ws.grids.first_for(dataset), ws.store.get(dataset)
            if grid is None or info is None:  # no tab open: its rows as loaded
                return f"SELECT * FROM {quote('ds_' + dataset)}"  # noqa: S608 (a quoted dataset name)
            return ws.compiled(cursor, grid, info).sql()

        bound, params = await self.bind_sql(text, name)
        prepared = await self.prepare_connections(bound)

        def execute(cursor: Any) -> Any:
            datasets = {i.name for i in ws.store.all()}
            for target, table in prepared.tables.items():
                cursor.register(target, table)
            guarded = guard(
                prepared.sql,
                datasets,
                None,
                lambda dataset: tab_view(cursor, dataset),
                grammar=ws.grammar,
                connection_tables=frozenset(prepared.tables),
            )
            if guarded.kind != "select":
                raise SqlRefused(f"Write one SELECT; its result becomes {name}.")
            timer = threading.Timer(settings.query_timeout_seconds, cursor.interrupt)
            timer.start()
            try:
                result = self._reader.query_table(cursor, guarded.sql, params or None)
            finally:
                timer.cancel()
            return result

        try:
            table = await ws.workers.run(BACKGROUND, lambda: execute(ws.store.cursor()))
        except ws.interrupted:
            raise TimedOut(
                f"The query was stopped: it ran past {settings.query_timeout_seconds:.0f} seconds."
            ) from None
        origin = Origin("query", sql=text)
        result = await self.store_table(name, table, "sql_result", False, who, query=text, origin=origin)
        ws.audit.write(who, "sql_query", name, query=text, rows=table.num_rows)
        reads = {"connection_reads": prepared.reads} if prepared.reads else {}
        return result | {"rows": table.num_rows} | reads

    async def bind_sql(self, text: str, where: str) -> tuple[str, list[str]]:
        """A query's ${NAME} (12.7): each outside strings and comments a bound parameter ($1, $2), its value
        from this computer's sources; MissingVariables for one not set here. The text itself never holds a
        value."""
        if "${" not in text:
            return text, []
        if self.variables is None:
            bound = variable_refs.bind_sql(text, "duckdb", "dollar")
            values = bound.params(lambda name: None, where)
            return bound.sql, list(values)
        sql, params = await self.variables.bind(text, "duckdb", "dollar", where)
        return sql, list(params)

    async def prepare_connections(self, text: str) -> Any:
        """The query's connections' tables read (services/connection_tables.py), or the query as it was."""
        if self.connection_sql is None:
            return _Unprepared(text)
        try:
            return await self.connection_sql.prepare(text)
        except ValueError as error:  # a name that is not a connection's table: said as the guard says
            raise SqlRefused(str(error)) from None


class ConnectionSql(Protocol):
    """DuckDB SQL naming a connection's table (services/connection_tables.py)."""

    async def prepare(self, text: str) -> Any: ...


class _Unprepared:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.tables: dict[str, Any] = {}
        self.reads: list[dict[str, Any]] = []


class ConnectionTables:
    """A connection's table as a grid, for services/connections.py (its Tables port): stored as any
    table is, a file loaded as Open file loads it, a file's first rows for the catalog's preview."""

    def __init__(self, datasets: DatasetService) -> None:
        self._datasets = datasets

    async def store(
        self,
        name: str,
        table: Any,
        who: str,
        opened: Opened | None,
        connection: str = "",
        sql: str = "",
        dax: bool = False,
        code: str = "",
        place: tuple[str, str, str] | None = None,
    ) -> dict[str, Any]:
        origin = Origin(
            "connection",
            connection=connection or None,
            sql=sql or None,
            dax=dax,
            code=code or None,
            place=place,
            whole=opened is None,
        )
        result = await self._datasets.store_table(
            name, table, "connection", True, who, opened=opened, origin=origin
        )
        self._datasets.ws.audit.write(who, "open_connection_table", name)
        return result

    async def load_file(self, name: str, path: str, sheet: str | None, who: str) -> dict[str, Any]:
        return await self._datasets.load_file(
            name, path, sheet, True, who, adapted=True
        )  # the adapter's Files

    def opened_from(self, name: str) -> str | None:
        # Names that differ only in case are one table to DuckDB: Invoices is open as invoices too.
        found = next(
            (d.name for d in self._datasets.ws.store.all() if d.name.casefold() == name.casefold()), None
        )
        if found is None:
            return None
        origin = self._datasets.origins.get(found)
        return (origin.connection or "") if origin.kind == "connection" else ""

    async def sheets(self, path: str) -> list[str]:
        return list((await self._datasets.sheets(path))["sheets"])

    async def peek(self, path: str, sheet: str | None, rows: int) -> dict[str, Any]:
        return await self._datasets.peek_file(path, sheet, rows)

    async def read_file(self, path: str, sheet: str | None) -> Any:
        return await self._datasets.read_file(path, sheet)


def _file_of(origin: Origin) -> tuple[str, str | None] | None:
    """The file a table was read from (its path and sheet), when it was read from one on disk."""
    return (origin.path, origin.sheet) if origin.kind == "file" and origin.path else None
