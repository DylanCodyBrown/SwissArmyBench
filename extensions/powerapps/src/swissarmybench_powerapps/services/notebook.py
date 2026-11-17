"""The code app's data notebook (phase 2): TypeScript and SQL cells on Deno's Jupyter kernel with one
DuckDB (domain/ts_notebook.py), the open tables and the connections' tables in it, Open as grid, data.ts
and Use in app (domain/data_ts.py), TSX previews (domain/tsx_preview.py) and Dataverse into grids.

One kernel per notebook (its path), started on its first run, with a temporary folder of its own (the open
tables as Parquet, the connections' reads, a result written for Open as grid, a preview's bundle: never in
the project), stopped when the notebook closes, on Stop, or with the server. Every run is the user's or the
agent's; each is written to the audit log (the cell's number and kind, never its code or a value).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import notebooks
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.datasets import DatasetInfo, quote
from swissarmybench.domain.export import ExportOptions
from swissarmybench.domain.grids import POS, Grid
from swissarmybench.domain.packages import MissingPackagesError
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace
from swissarmybench_powerapps.domain import data_ts, tools, tsx_preview
from swissarmybench_powerapps.domain import ts_notebook as rules

DATA_NOTEBOOK = "data.ipynb"
DATA_TS = "src/data.ts"
BUNDLE_SECONDS = 120.0
_PARQUET = ExportOptions(format="parquet", provenance=False)


class KernelLike(Protocol):
    def execute(self, code: str, silent: bool = False) -> AsyncIterator[dict[str, Any]]: ...

    async def complete(self, code: str, offset: int) -> dict[str, Any]: ...

    async def interrupt(self) -> None: ...

    async def restart(self, prelude: str) -> None: ...

    async def shutdown(self) -> None: ...

    async def alive(self) -> bool: ...


class Launcher(Protocol):
    async def start(
        self, deno: str, folder: str | None, environ: dict[str, str], prelude: str
    ) -> KernelLike: ...


class Files(Protocol):
    def make_folder(self) -> str: ...

    def remove_folder(self, folder: str) -> None: ...

    def join(self, folder: str, *parts: str) -> str: ...

    def write_bytes(self, path: str, data: bytes) -> None: ...

    def write_text(self, path: str, text: str) -> None: ...

    def read_text(self, path: str) -> str | None: ...

    def remove(self, path: str) -> None: ...

    def is_file(self, path: str) -> bool: ...

    def is_dir(self, path: str) -> bool: ...

    def folder_of(self, path: str) -> str: ...

    def resolve(self, path: str) -> str: ...

    def read_parquet(self, path: str) -> Any: ...

    def write_parquet(self, path: str, table: Any) -> None: ...


class Runner(Protocol):
    def which(self, program: str) -> str | None: ...

    def system(self) -> str: ...

    async def run(self, argv: list[str], cwd: str | None, timeout: float, on_line: Any = None) -> Any: ...


class Writer(Protocol):
    def write(
        self, cursor: Any, sql: str, columns: Any, options: ExportOptions, provenance: Any, row_count: int
    ) -> bytes: ...


class Audit(Protocol):
    def write(self, actor: str, action: str, dataset: str | None = None, **details: Any) -> None: ...


class Live(Protocol):
    async def broadcast(self, message: dict[str, Any]) -> None: ...


StoreTable = Callable[[str, Any, str], Awaitable[dict[str, Any]]]
Prepare = Callable[[str], Awaitable[Any]]


class OpenTables:
    """The open tables (a tab in the grid), after their grids' steps, as Parquet: what the kernel's views
    read. Each has a mark: the same mark, the same rows (written again only when it changes)."""

    def __init__(self, ws: Workspace, writer: Writer) -> None:
        self.ws = ws
        self._writer = writer

    def listing(self) -> dict[str, tuple[str, DatasetInfo, Grid]]:
        found: dict[str, tuple[str, DatasetInfo, Grid]] = {}
        for info in self.ws.store.all():
            grid = self.ws.grids.first_for(info.name)
            if grid is None:
                continue
            steps = [[s.kind, s.params] for s in grid.steps if s.enabled and not s.params.get("header")]
            said = json.dumps(
                [info.name, info.version, steps, repr(grid.settings)], sort_keys=True, default=str
            )
            mark = hashlib.sha256(said.encode("utf-8", "replace")).hexdigest()[:16]
            found.setdefault(variable_name(info.name), (mark, info, grid))
        return found

    def _parquet(self, info: DatasetInfo, grid: Grid) -> bytes:
        cursor = self.ws.store.cursor()
        steps = [s for s in grid.steps if not s.params.get("header")]
        positioned, columns = self.ws.views.positioned_sql(cursor, info, steps, grid.settings)
        names = ", ".join(quote(c.name) for c in columns)
        sql = f"SELECT {names} FROM ({positioned}) ORDER BY {POS}"  # noqa: S608 (an open table's quoted names)
        return self._writer.write(self.ws.store.cursor(), sql, columns, _PARQUET, None, 0)

    async def parquet(self, info: DatasetInfo, grid: Grid) -> bytes:
        found: bytes = await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)
        return found


@dataclass
class Notebook:
    path: str
    key: str
    temp: str
    kernel: KernelLike | None = None
    marks: dict[str, str] = field(default_factory=dict)
    starting: asyncio.Lock = field(default_factory=asyncio.Lock)
    runs: int = 0


class TsNotebooks:
    def __init__(
        self,
        launcher: Launcher,
        runner: Runner,
        files: Files,
        tables: OpenTables | None,
        store_table: StoreTable,
        prepare: Prepare,
        code_app: Callable[[], str | None],
        write_app_file: Callable[[str, str, str], str],
        audit: Audit,
        live: Live,
        connections: Callable[[], list[dict[str, Any]]] = lambda: [],
        open_connection_table: Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]] | None = None,
        environments: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
        environment_id: Callable[[], str] = lambda: "",
        sources: Callable[[], list[dict[str, Any]]] = lambda: [],
    ) -> None:
        self._launcher = launcher
        self._runner = runner
        self._files = files
        self._tables = tables
        self._store_table = store_table
        self._prepare = prepare
        self._code_app = code_app
        self._write_app_file = write_app_file
        self._audit = audit
        self._live = live
        self._connections = connections
        self._open_connection_table = open_connection_table
        self._environments = environments
        self._environment_id = environment_id
        self._sources = sources
        self._books: dict[str, Notebook] = {}
        self._origin = ""  # this server's own address, for the kernel's route (set by the first run)

    # ===== the kernel =====

    def deno(self) -> str:
        """Deno's path, or the base's missing-package answer with this system's install command."""
        found = self._runner.which("deno")
        if found:
            return found
        system = tools.system_of(self._runner.system())
        spec = tools.TOOLS["deno"]
        raise MissingPackagesError(
            {
                "feature": tools.FEATURES["typescript"],
                "packages": [spec.name],
                "python": "tool",
                "command": spec.installs[system],
                "tool": "deno",
            }
        )

    def _book(self, path: Any) -> Notebook:
        where = str(path or "").strip()
        if not where.lower().endswith(".ipynb"):
            raise ValueError("Name the notebook: its path (data.ipynb).")
        where = self._files.resolve(where)
        found = self._books.get(where)
        if found is None:
            found = Notebook(where, secrets.token_urlsafe(18), self._files.make_folder())
            self._books[where] = found
        return found

    def by_key(self, key: str) -> Notebook | None:
        for book in self._books.values():
            if secrets.compare_digest(book.key.encode(), key.encode()):
                return book
        return None

    async def _kernel(self, book: Notebook) -> KernelLike:
        async with book.starting:
            if book.kernel is not None and await book.kernel.alive():
                return book.kernel
            deno = self.deno()
            environ = {rules.TEMP_VARIABLE: book.temp}
            if self._origin:
                environ[rules.PREPARE_VARIABLE] = f"{self._origin}/powerapps/notebook/prepare/{book.key}"
            book.marks = {}
            try:
                book.kernel = await self._launcher.start(
                    deno, self._files.folder_of(book.path), environ, rules.PRELUDE
                )
            except FileNotFoundError:
                raise self.deno_missing() from None
            except RuntimeError as error:
                raise Conflict(str(error)) from None
            await self._live.broadcast({"type": "powerapps_notebook", "path": book.path, "state": "idle"})
            return book.kernel

    def deno_missing(self) -> MissingPackagesError:
        try:
            self.deno()
        except MissingPackagesError as error:
            return error
        return MissingPackagesError({"feature": "TypeScript cells", "packages": ["Deno"], "python": "tool"})

    async def _sync(self, book: Notebook, kernel: KernelLike) -> list[str]:
        """The open tables as the kernel's views, written again only when one changed."""
        if self._tables is None:
            return []
        listed = self._tables.listing()
        now = {name: mark for name, (mark, _, _) in listed.items()}
        if now == book.marks:
            return sorted(now)
        views: dict[str, str] = {}
        for name, (mark, info, grid) in listed.items():
            path = self._files.join(book.temp, f"table_{name}.parquet")
            if book.marks.get(name) != mark or not self._files.is_file(path):
                self._files.write_bytes(path, await self._tables.parquet(info, grid))
            views[name] = path
        async for item in kernel.execute(rules.sync_code(views), silent=True):
            if item.get("output_type") == "error":
                raise Conflict(f"The open tables could not be given to the kernel: {item.get('evalue')}")
        book.marks = now
        return sorted(now)

    # ===== a run =====

    async def run(self, body: Any, who: str, origin: str = "") -> AsyncIterator[dict[str, Any]]:
        """A TypeScript or SQL cell run in the notebook's kernel: its outputs as they come (tables as one
        bundle each, colour codes out), an error's detail for the panel, then {"done": ...}."""
        body = body if isinstance(body, dict) else {}
        kind = str(body.get("kind") or "typescript")
        if kind not in ("typescript", "sql"):
            raise ValueError("A run is a TypeScript cell or a SQL cell (kind: typescript or sql).")
        code = rules.check_code(body.get("code"))
        sent = rules.sql_cell(code) if kind == "sql" else code
        cell = body.get("cell") if isinstance(body.get("cell"), int) else None
        if origin and not self._origin:
            self._origin = origin
        book = self._book(body.get("path") or self._data_notebook_path())
        kernel = await self._kernel(book)
        await self._sync(book, kernel)
        book.runs += 1
        ok = True
        async for item in kernel.execute(sent):
            if "done" in item:
                ok = bool(item["done"].get("ok"))
                yield item
                continue
            record = rules.clean(item)
            yield record
            if record.get("output_type") == "error":
                yield {"error_detail": rules.error_detail(record, cell, code, sql=kind == "sql")}
        self._audit.write(who, "powerapps_ts_run", None, cell=cell, kind=kind, ok=ok)

    async def run_all(self, body: Any, who: str, origin: str = "") -> dict[str, Any]:
        """A run as one answer (the agent's): every output, then how it ended."""
        outputs: list[dict[str, Any]] = []
        done: dict[str, Any] = {}
        async for item in self.run(body, who, origin):
            if "done" in item:
                done = item["done"]
            else:
                outputs.append(item)
        return {"outputs": outputs, "done": done}

    async def complete(self, body: Any) -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        book = self._books.get(self._where(body.get("path")))
        offset = body.get("offset")
        if book is None or book.kernel is None or not isinstance(offset, int):
            return {"matches": [], "start": offset or 0, "end": offset or 0}
        return await book.kernel.complete(rules.check_code(body.get("code")), offset)

    def _where(self, path: Any) -> str:
        """A notebook named, else the code app's data notebook (its real path; "" for neither)."""
        named = str(path or "") or self._data_notebook_path() or ""
        return self._files.resolve(named) if named else ""

    async def interrupt(self, path: Any) -> dict[str, Any]:
        book = self._books.get(self._where(path))
        if book is not None and book.kernel is not None:
            await book.kernel.interrupt()
        return {"interrupted": book is not None}

    async def restart(self, path: Any, who: str) -> dict[str, Any]:
        book = self._books.get(self._where(path))
        if book is None or book.kernel is None:
            return {"restarted": False}
        await book.kernel.restart(rules.PRELUDE)
        book.marks = {}
        self._audit.write(who, "powerapps_ts_restart", None)
        return {"restarted": True}

    async def stop(self, path: Any) -> dict[str, Any]:
        where = self._where(path)
        book = self._books.pop(where, None)
        if book is None:
            return {"stopped": False}
        await self._end(book)
        return {"stopped": True}

    async def _end(self, book: Notebook) -> None:
        if book.kernel is not None:
            await book.kernel.shutdown()
            book.kernel = None
        self._files.remove_folder(book.temp)

    async def stop_all(self) -> None:
        books, self._books = list(self._books.values()), {}
        for book in books:
            await self._end(book)

    def state(self) -> dict[str, Any]:
        return {
            "kernels": [
                {"path": b.path, "running": b.kernel is not None, "runs": b.runs}
                for b in self._books.values()
            ],
            "deno": self._runner.which("deno"),
            "data_notebook": self._data_notebook_path(),
        }

    # ===== the kernel's own route: a connection's tables for a query =====

    async def prepare(self, key: str, body: Any) -> dict[str, Any]:
        """A query naming a connection's table (`[Finance Captive].orders`): each table read by the base
        (connection_tables), written as Parquet in the notebook's temporary folder, and the query pointed
        at it. Reached only with the kernel's own key."""
        book = self.by_key(key)
        if book is None:
            raise Refused("That key is not one of this server's notebooks.")
        sql = (body if isinstance(body, dict) else {}).get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError('Send {"sql": "..."}.')
        prepared = await self._prepare(sql)
        tables: dict[str, str] = {}
        for name, table in (getattr(prepared, "tables", None) or {}).items():
            path = self._files.join(book.temp, f"{name}.parquet")
            await asyncio.to_thread(self._files.write_parquet, path, table)
            tables[str(name)] = path
        return {"sql": prepared.sql, "tables": tables, "reads": getattr(prepared, "reads", [])}

    # ===== Open as grid =====

    async def grid(self, body: Any, who: str) -> dict[str, Any]:
        """A table result opened as a grid: written whole by the kernel as Parquet (by its id), read here,
        stored as a table of its own, the file removed."""
        body = body if isinstance(body, dict) else {}
        book = self._books.get(self._where(body.get("path")))
        if book is None or book.kernel is None:
            raise Conflict("The notebook's kernel is not running: run the cell again.")
        name = str(body.get("name") or "").strip() or f"result_{body.get('id')}"
        path = self._files.join(book.temp, f"grid_{secrets.token_hex(4)}.parquet")
        failed = None
        async for item in book.kernel.execute(rules.save_code(body.get("id"), path), silent=True):
            if item.get("output_type") == "error":
                failed = rules.plain(str(item.get("evalue")))
        if failed or not self._files.is_file(path):
            raise Conflict(failed or "The result was not written.")
        try:
            table = await asyncio.to_thread(self._files.read_parquet, path)
        finally:
            self._files.remove(path)
        stored = await self._store_table(name, table, who)
        self._audit.write(who, "powerapps_ts_grid", name)
        return stored

    # ===== data.ts and Use in app =====

    def _data_notebook_path(self) -> str | None:
        folder = self._code_app()
        return self._files.join(folder, DATA_NOTEBOOK) if folder else None

    async def open_data_notebook(self, who: str) -> dict[str, Any]:
        """The code app's data notebook: made the first time (a SQL cell and a TypeScript cell), its path."""
        path = self._data_notebook_path()
        if path is None:
            raise Conflict("No code app is open: New code app makes one, Open code app opens one.")
        if not self._files.is_file(path):
            self._files.write_text(path, starter_notebook())
            self._audit.write(who, "powerapps_data_notebook", None)
        return {"path": path}

    def _cells(self, body: dict[str, Any], path: str) -> list[dict[str, Any]]:
        sent = body.get("cells")
        if sent is not None:
            cells = notebooks.read_cells(sent)
        else:
            text = self._files.read_text(path)
            if text is None:
                raise NotFound(f"There is no notebook {path}.")
            cells = notebooks.read_notebook(text)
        return [{"kind": c.kind, "source": c.source, "number": c.number, "name": c.name} for c in cells]

    async def _results(self, book: Notebook | None, names: list[str]) -> dict[str, dict[str, Any]]:
        """Each name a TypeScript cell made that holds a table result now (its columns and types), asked of
        the kernel when it runs (none: data.ts has no row types)."""
        if book is None or book.kernel is None or not names:
            return {}
        probe = (
            "(() => { const out: Record<string, unknown> = {}; for (const n of "
            + json.dumps(names)
            + ") { try { const v = eval(n); if (v instanceof (globalThis as any).sab.SabTable) "
            "out[n] = { columns: v.columns, types: v.types }; } catch { /* not made yet */ } } "
            'return { [Symbol.for("Jupyter.display")]() { return { "application/json": out }; } }; })()'
        )
        found: dict[str, dict[str, Any]] = {}
        async for item in book.kernel.execute(probe):
            data = item.get("data") if isinstance(item.get("data"), dict) else None
            said = data.get("application/json") if data else None
            if isinstance(said, dict):
                found = {str(k): v for k, v in said.items() if isinstance(v, dict)}
        return found

    async def data_ts(self, body: Any) -> dict[str, Any]:
        """data.ts as it would be written from the notebook (its cells as the window holds them, or its
        file)."""
        body = body if isinstance(body, dict) else {}
        path = str(body.get("path") or self._data_notebook_path() or "")
        if not path:
            raise Conflict("No code app is open, and no notebook was named.")
        cells = self._cells(body, path)
        names = [n for c in cells if c["kind"] == "typescript" for n in data_ts.declared(str(c["source"]))]
        book = self._books.get(self._files.resolve(path))
        built = data_ts.build(cells, await self._results(book, names))
        return built | {"path": path, "target": DATA_TS}

    async def use_in_app(self, body: Any, who: str) -> dict[str, Any]:
        """Use in app: data.ts written into the code app's src/ (the app imports it: `import { ... } from
        "./data"`)."""
        folder = self._code_app()
        if folder is None:
            raise Conflict("No code app is open: Use in app writes data.ts into the open code app.")
        built = await self.data_ts(body)
        written = self._write_app_file(folder, DATA_TS, built["text"])
        self._audit.write(who, "powerapps_use_in_app", None, file="data.ts")
        await self._live.broadcast({"type": "powerapps_project", "open": True})
        return built | {"written": written}

    # ===== TSX previews =====

    async def preview(self, body: Any, who: str, origin: str = "") -> dict[str, Any]:
        """A TSX cell drawn: its props worked out in the notebook's kernel, the component bundled with the
        project's own React, one document for the HTML cells' frame (its policy with it)."""
        body = body if isinstance(body, dict) else {}
        source = tsx_preview.check_component(body.get("source"))
        folder = self._code_app()
        if folder is None:
            raise Conflict("No code app is open: a TSX cell is drawn with the code app's own React.")
        node_modules = self._files.join(folder, "node_modules")
        present = {
            name: self._files.is_file(self._files.join(node_modules, name, "package.json"))
            for name in ("react", "react-dom")
        }
        lacking = tsx_preview.missing_react(present)
        if lacking:
            raise Conflict(lacking)
        if origin and not self._origin:
            self._origin = origin
        book = self._book(body.get("path") or self._data_notebook_path())
        props: Any = {}
        expression = tsx_preview.props_expression(source)
        if expression:
            kernel = await self._kernel(book)
            await self._sync(book, kernel)
            failed = None
            async for item in kernel.execute(tsx_preview.props_code(expression)):
                if item.get("output_type") == "error":
                    failed = f"{rules.plain(str(item.get('ename')))}: {rules.plain(str(item.get('evalue')))}"
                data = item.get("data") if isinstance(item.get("data"), dict) else None
                if data and "application/json" in data:
                    props = data["application/json"]
            if failed:
                raise Conflict(f"The props could not be worked out ({expression}): {failed}")
        deno = self.deno()
        component = self._files.join(book.temp, "component.tsx")
        entry = self._files.join(book.temp, "entry.tsx")
        config = self._files.join(book.temp, "deno.json")
        output = self._files.join(book.temp, "preview.js")
        self._files.write_text(component, source)
        self._files.write_text(entry, tsx_preview.ENTRY)
        self._files.write_text(config, tsx_preview.config(node_modules))
        self._files.remove(output)
        ran = await self._runner.run(
            tsx_preview.bundle_argv(deno, entry, output, config), book.temp, BUNDLE_SECONDS
        )
        bundle = self._files.read_text(output) if ran.code == 0 else None
        if bundle is None:
            raise Conflict(tsx_preview.bundle_error(ran.output))
        cell = body.get("cell") if isinstance(body.get("cell"), int) else None
        self._audit.write(who, "powerapps_tsx_preview", None, cell=cell)
        return {
            "html": tsx_preview.page(bundle, props, str(body.get("title") or "Component")),
            "policy": tsx_preview.POLICY,
            "props": sorted(props) if isinstance(props, dict) else [],
        }

    # ===== Dataverse into grids =====

    def _dataverse_connection(self, environment_url: str) -> str | None:
        wanted = _host(environment_url)
        for found in self._connections():
            if found.get("kind") == "dataverse" and wanted and _host(str(found.get("url") or "")) == wanted:
                return str(found["name"])
        return None

    async def dataverse_grid(self, body: Any, who: str) -> dict[str, Any]:
        """A Dataverse source of the code app (power.config.json) opened as a grid, read through the
        library's Dataverse connection for the app's environment (its SQL endpoint where the connection
        uses it); with none, which connection to add."""
        body = body if isinstance(body, dict) else {}
        name = str(body.get("source") or body.get("table") or "")
        listed = {s["name"]: s for s in self._sources() if s.get("kind") == "dataverse"}
        source = listed.get(name) or next((s for s in listed.values() if s.get("table") == name), None)
        if source is None:
            raise NotFound(f"The code app has no Dataverse source {name} (powerapps_project lists them).")
        environment = self._environment_id()
        reached = await self._environments() if self._environments is not None else []
        url = next(
            (str(e.get("url") or "") for e in reached if str(e.get("id", "")).lower() == environment.lower()),
            "",
        )
        if not url:
            raise Conflict(
                "The code app's environment is not among the environments this sign-in reaches "
                "(pac env list): sign in to it (pac auth create), then open the table again."
            )
        connection = self._dataverse_connection(url)
        if connection is None:
            return {
                "opened": False,
                "needs": {"kind": "dataverse", "url": url.rstrip("/")},
                "message": (
                    f"Add a Dataverse connection for {url.rstrip('/')} (Connections, Add connection, "
                    "Dataverse): the table is read through it."
                ),
            }
        if self._open_connection_table is None:
            raise Conflict("Opening a table needs the connections.")
        opened = await self._open_connection_table(connection, {"table": source["table"]}, who)
        self._audit.write(who, "powerapps_dataverse_grid", None, source=source["name"], connection=connection)
        return {"opened": True, "connection": connection, "table": source["table"]} | opened


def _host(url: str) -> str:
    text = url.strip().lower()
    for prefix in ("https://", "http://"):
        text = text.removeprefix(prefix)
    return text.split("/")[0]


def starter_notebook() -> str:
    """A new data notebook: a note, a SQL cell and a TypeScript cell (made-up data)."""
    cells = [
        notebooks.Cell(
            "markdown",
            "# Data\nSQL and TypeScript cells share one DuckDB. The open tables are views by their names.",
        ),
        notebooks.Cell("sql", "SELECT 'North' AS region, 120 AS total UNION ALL SELECT 'South', 80"),
        notebooks.Cell(
            "typescript",
            "const byRegion = await sab.sql`SELECT 'North' AS region, 120 AS total`;\nbyRegion",
        ),
    ]
    return notebooks.write_notebook(cells)
