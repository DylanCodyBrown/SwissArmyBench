"""Streamlit pieces and the page designer (docs/ideas.md, 2026-11-15; rules in
domain/streamlit_cells.py). For the Workbench window, the page designer's window and the agent alike.

An app here is one notebook's (or script's) Streamlit app while that document is open:

  pieces    its Streamlit cells, each a piece, as the Workbench window sends them while they are typed
  pages     the pages the pieces are placed on (the page designer's): add, rename, remove; push a
            piece to a page, move it, resize it, take it off
  run       write the app into its own temporary folder (each page as ONE Streamlit page, each piece
            alone as a page of its own for its cell), the tables it names as Parquet, and start its
            Streamlit process in the notebook's own Python. One process a notebook
  state     each piece's state: not run, out of date (its code changed, or a table it names did),
            or current; what is missing from the notebook's Python
  export    the designed pages as a folder that runs without this app

Memory only, but for the app's temporary folder (removed when the app stops) and an export. The pages
are saved by the Workbench window, inside the notebook's file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmygrid.domain import notebooks
from swissarmygrid.domain import streamlit_cells as rules
from swissarmygrid.domain.blades import install_command
from swissarmygrid.domain.codegen import variable_name
from swissarmygrid.domain.datasets import DatasetInfo, quote
from swissarmygrid.domain.export import ExportOptions
from swissarmygrid.domain.grids import POS, Grid
from swissarmygrid.domain.streamlit_cells import Page, PieceCode, Placed, StreamlitError
from swissarmygrid.services.export import ExportWriter
from swissarmygrid.services.ports import BACKGROUND
from swissarmygrid.services.workspace import Conflict, NotFound, Workspace

MAX_APPS: int = 12
# How long an app outlives the Workbench window that opened it (a reload keeps it a minute).
ORPHAN_SECONDS: float = 60.0
LIVE_PATH: str = "/streamlit/live/"
_PARQUET = ExportOptions(format="parquet", provenance=False)


class Files(Protocol):
    def folder(self) -> str: ...

    def write(self, folder: str, files: dict[str, str], keep: set[str]) -> None: ...

    def touch(self, folder: str, name: str) -> None: ...

    def write_table(self, folder: str, name: str, data: bytes) -> None: ...

    def has_table(self, folder: str, name: str) -> bool: ...

    def remove(self, folder: str) -> None: ...

    def export(
        self, folder: str, files: dict[str, str], tables: dict[str, bytes]
    ) -> tuple[str, list[str]]: ...


class Process(Protocol):
    port: int
    python: str

    def alive(self) -> bool: ...

    async def stop(self) -> None: ...


class Runner(Protocol):
    def default_python(self) -> str: ...

    async def check(self, python: str) -> dict[str, Any]: ...

    async def start(self, python: str, folder: str, base: str) -> Process: ...

    async def install(self, python: str, packages: list[str]) -> tuple[int | None, str]: ...


@dataclass
class App:
    id: str
    secret: str
    title: str
    document: str | None = None
    python: str | None = None
    window: str | None = None  # the Workbench window that opened it (None: the agent did)
    kernel: str | None = None  # the document's kernel, when it has one
    order: list[int] = field(default_factory=list)  # its pieces' cells, in the document's order
    codes: dict[int, str] = field(default_factory=dict)
    pages: list[Page] = field(default_factory=list)
    # What was last written: each piece's code, each table's mark, the files' names.
    ran: dict[int, str] = field(default_factory=dict)
    marks: dict[str, str] = field(default_factory=dict)
    written: set[str] = field(default_factory=set)
    ran_at: float | None = None
    folder: str | None = None
    process: Process | None = None
    generation: int = 0
    problem: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)  # what the last run could not do
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def key(self) -> str:
        return f"{self.id}-{self.secret}"

    @property
    def base(self) -> str:
        return f"{LIVE_PATH}{self.key}"

    def running(self) -> bool:
        return self.process is not None and self.process.alive()


def _pieces(sent: Any) -> list[tuple[int, str]]:
    if not isinstance(sent, list) or len(sent) > rules.MAX_PIECES:
        raise StreamlitError('Send the pieces as a list: [{"cell": 4, "code": "..."}].')
    found: list[tuple[int, str]] = []
    seen: set[int] = set()
    for raw in sent:
        cell = raw.get("cell") if isinstance(raw, dict) else None
        code = raw.get("code") if isinstance(raw, dict) else None
        if isinstance(cell, bool) or not isinstance(cell, int) or cell < 1 or cell in seen:
            raise StreamlitError("Each piece names its cell by the cell's own number, once.")
        if not isinstance(code, str) or len(code) > notebooks.MAX_CELL_CHARS:
            raise StreamlitError("A piece's code is text of at most a million characters.")
        seen.add(cell)
        found.append((cell, code))
    return found


class StreamlitApps:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        runner: Runner,
        writer: ExportWriter,
        now: Callable[[], float],
        read_document: Callable[[str], tuple[str, str, float]],
        environment_of: Callable[[str], str | None],
    ) -> None:
        self.ws = ws
        self._files = files
        self._runner = runner
        self._writer = writer
        self._now = now
        self._read = read_document  # a file's text and full path (the Workbench's documents)
        self._environment_of = environment_of  # the Python remembered for a document
        self._apps: dict[str, App] = {}
        self._gone_since: dict[str, float] = {}

    # ===== apps =====

    def _app(self, app_id: str) -> App:
        app = self._apps.get(app_id)
        if app is None:
            raise NotFound(
                "That Streamlit app is not open (its notebook was closed, or the server restarted)."
            )
        return app

    def port_of(self, key: str) -> int | None:
        """The port a proxied address goes to: only for a running app, named with its own secret."""
        app_id, _, secret = key.partition("-")
        app = self._apps.get(app_id)
        if app is None or not secret or not secrets.compare_digest(secret.encode(), app.secret.encode()):
            return None
        return app.process.port if app.process is not None and app.running() else None

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Open a document's app: {"title", "document", "python", "window", "pieces", "pages"} as the
        Workbench window holds them, or {"path"}: a saved notebook or script, read from its file."""
        if not isinstance(body, dict):
            raise StreamlitError('Send {"title", "pieces", "pages"}, or {"path": a notebook or script}.')
        if len(self._apps) >= MAX_APPS:
            raise Conflict(f"{MAX_APPS} Streamlit apps are open: close a notebook first.")
        app = App(secrets.token_hex(4), secrets.token_hex(16), "Streamlit app")
        path = body.get("path")
        if isinstance(path, str) and path and "pieces" not in body:
            try:
                text, full, _ = self._read(path)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            app.document = full
            app.title = full.replace("\\", "/").rsplit("/", 1)[-1]
            app.python = self._environment_of(full)
            if notebooks.kind_of(full) == "notebook":
                cells, _ = notebooks.read_document(text)
                pieces = [(c.number or 0, c.source) for c in cells if c.kind == "streamlit"]
                app.pages = rules.read_pages(notebooks.document_pages(text))
            else:
                found = rules.script_pieces(text)
                if any(number is None for number, _ in found):
                    raise StreamlitError(
                        "This script's Streamlit cells have no numbers yet: open and save it in the "
                        "Workbench once."
                    )
                pieces = [(number or 0, code) for number, code in found]
                app.pages = rules.script_pages(text)
            app.order = [cell for cell, _ in pieces]
            app.codes = dict(pieces)
        self._apps[app.id] = app
        self._update(app, body)
        self.ws.audit.write(who, "open_streamlit_app", app.title)
        return self._state(app)

    def _update(self, app: App, body: dict[str, Any]) -> None:
        """What the window knows about the document, as it stands now."""
        if isinstance(body.get("title"), str) and body["title"].strip():
            app.title = body["title"].strip()[:200]
        if isinstance(body.get("document"), str):
            app.document = body["document"]
        if "python" in body and (body["python"] is None or isinstance(body["python"], str)):
            app.python = body["python"] or None
        if isinstance(body.get("window"), str) and 0 < len(body["window"]) <= 64:
            app.window = body["window"]
        if "kernel" in body and (body["kernel"] is None or isinstance(body["kernel"], str)):
            app.kernel = body["kernel"]
        if "pieces" in body:
            pieces = _pieces(body["pieces"])
            app.order = [cell for cell, _ in pieces]
            app.codes = dict(pieces)
        if "pages" in body:
            app.pages = rules.read_pages(body["pages"])

    def listing(self) -> dict[str, Any]:
        return {"apps": [self._summary(app) for app in self._apps.values()]}

    def _summary(self, app: App) -> dict[str, Any]:
        return {
            "app": app.id,
            "title": app.title,
            "document": app.document,
            "running": app.running(),
            "pages": [{"id": p.id, "name": p.name, "pieces": len(p.pieces)} for p in app.pages],
            "pieces": len(app.order),
        }

    def state(self, app_id: str) -> dict[str, Any]:
        return self._state(self._app(app_id))

    async def sync(self, app_id: str, body: Any) -> dict[str, Any]:
        """The document as the Workbench window holds it now: its pieces (and, when the file was
        just opened, its pages). Nothing runs."""
        app = self._app(app_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"pieces": [{"cell": 4, "code": "..."}]}.')
        self._update(app, body)
        return self._state(app)

    # ===== tables =====

    def _tables(self) -> dict[str, tuple[DatasetInfo, Grid]]:
        """The open tables (a tab in the grid), by their names as Python variables."""
        found: dict[str, tuple[DatasetInfo, Grid]] = {}
        for info in self.ws.store.all():
            grid = self.ws.grids.first_for(info.name)
            if grid is not None:
                found.setdefault(variable_name(info.name), (info, grid))
        return found

    @staticmethod
    def _mark(info: DatasetInfo, grid: Grid) -> str:
        """A short mark of what a table holds after its grid's steps: the same mark, the same rows.
        A sort made by clicking a header is a way of looking, not a step (as in a table's cell)."""
        steps = [[s.kind, s.params] for s in grid.steps if s.enabled and not s.params.get("header")]
        said = json.dumps([info.name, info.version, steps, repr(grid.settings)], sort_keys=True, default=str)
        return hashlib.sha256(said.encode("utf-8", "replace")).hexdigest()[:16]

    def _parquet(self, info: DatasetInfo, grid: Grid) -> bytes:
        """The table after its grid's steps, as a Parquet file's bytes (run on a worker)."""
        cursor = self.ws.store.cursor()
        steps = [s for s in grid.steps if not s.params.get("header")]
        positioned, columns = self.ws.views.positioned_sql(cursor, info, steps, grid.settings)
        names = ", ".join(quote(c.name) for c in columns)
        sql = f"SELECT {names} FROM ({positioned}) ORDER BY {POS}"  # noqa: S608 (quoted names of an open table)
        # A cursor of its own: the one above may still hold what a step's check asked.
        return self._writer.write(self.ws.store.cursor(), sql, columns, _PARQUET, None, 0)

    # ===== state =====

    def _piece_codes(self, app: App) -> dict[int, PieceCode]:
        return {
            cell: PieceCode(cell, rules.piece_name(app.codes[cell], cell), app.codes[cell])
            for cell in app.order
        }

    def _state(self, app: App) -> dict[str, Any]:
        tables = self._tables()
        now = {name: self._mark(info, grid) for name, (info, grid) in tables.items()}
        found = rules.makers(app.codes, app.order)
        running = app.running()
        pieces: list[dict[str, Any]] = []
        stale: dict[int, bool] = {}
        for cell in app.order:
            code = app.codes[cell]
            mine = found[cell]
            named = rules.tables_named(code, tables)
            changed = [t for t in named if app.marks.get(t) != now[t]]
            if not running or cell not in app.ran:
                state = "notRun"
            elif rules.body(code) != app.ran[cell] or changed:
                state = "outOfDate"
            else:
                state = "current"
            stale[cell] = state != "current"
            pieces.append(
                {
                    "cell": cell,
                    "name": rules.piece_name(code, cell),
                    "makes": list(mine.makes),
                    "reads": [n for n in mine.reads if n not in rules.PROVIDED and n not in named],
                    "tables": named,
                    "inputs": [c for c, _ in rules.inputs_of(cell, found, app.order)],
                    "problem": mine.problem,
                    "state": state,
                    # The tables it names that changed in the grid since the app last ran.
                    "changed": changed if state == "outOfDate" else [],
                    "code_changed": state == "outOfDate" and rules.body(code) != app.ran[cell],
                    "preview": f"{app.base}/piece-{cell}" if running and cell in app.ran else None,
                    "pages": [p.id for p in app.pages if any(s.cell == cell for s in p.pieces)],
                }
            )
        pages: list[dict[str, Any]] = []
        codes = self._piece_codes(app)
        for page in app.pages:
            made = rules.page_code(
                page.name, page.pieces, codes, tables, elsewhere=rules.elsewhere(page, found)
            )
            pages.append(
                page.to_json()
                | {
                    "order": list(made.order),
                    "tables": list(made.tables),
                    "problems": list(made.problems),
                    "rows": [[p.id for p in row] for row in rules.rows(page.pieces)],
                    "out_of_date": running and any(stale.get(p.cell, False) for p in page.pieces),
                    "address": f"{app.base}/page-{page.id}" if running else None,
                }
            )
        return {
            "app": app.id,
            "title": app.title,
            "document": app.document,
            "python": app.python or self._runner.default_python(),
            "running": running,
            # Where the app is shown: through this server, under the app's own secret.
            "path": f"{app.base}/" if running else None,
            "address": f"http://127.0.0.1:{self.ws.addresses.port}{app.base}/" if running else None,
            # Its temporary folder while it runs (the app's own: removed when the app stops).
            "folder": app.folder,
            "generation": app.generation,
            "ran_at": app.ran_at,
            "problem": app.problem,
            "notes": list(app.notes),
            "pieces": pieces,
            "pages": pages,
        }

    async def _changed(self, app: App) -> None:
        await self.ws.live.broadcast({"type": "streamlit_changed", "app": app.id})

    # ===== pages =====

    def _page(self, app: App, page_id: str) -> Page:
        page = next((p for p in app.pages if p.id == page_id), None)
        if page is None:
            raise NotFound(f"This app has no page {page_id}.")
        return page

    async def _laid_out(self, app: App, who: str, what: str, detail: str) -> dict[str, Any]:
        """A page changed: the live app follows at once (when it is running), and the windows hear."""
        self.ws.audit.write(who, what, f"{app.title}: {detail}")
        if app.running():
            async with app.lock:
                await self._write(app)
        await self._changed(app)
        return self._state(app)

    def _place(self, app: App, page: Page, body: dict[str, Any]) -> Placed:
        cell = body.get("cell")
        if isinstance(cell, bool) or not isinstance(cell, int) or cell not in app.codes:
            raise StreamlitError("cell is the number of one of this document's Streamlit cells.")
        if len(page.pieces) >= rules.MAX_PLACED:
            raise Conflict(f"A page holds at most {rules.MAX_PLACED} pieces.")
        taken = [s.id for p in app.pages for s in p.pieces]
        placed = Placed(
            rules.next_id("s", taken),
            cell,
            rules.check_width(body.get("w", rules.DEFAULT_WIDTH)),
            rules.check_rows(body.get("h")),
        )
        index = body.get("index")
        at = len(page.pieces) if not isinstance(index, int) or isinstance(index, bool) else index
        page.pieces.insert(max(0, min(at, len(page.pieces))), placed)
        return placed

    async def add_page(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """A new page {"name"?}; with {"cell"} the piece is pushed to it at once."""
        app = self._app(app_id)
        body = body if isinstance(body, dict) else {}
        if len(app.pages) >= rules.MAX_PAGES:
            raise Conflict(f"An app holds at most {rules.MAX_PAGES} pages.")
        names = [p.name for p in app.pages]
        name = rules.check_name(body["name"]) if body.get("name") else rules.page_title(len(names) + 1, names)
        page = Page(rules.next_id("p", [p.id for p in app.pages]), name)
        if body.get("cell") is not None:
            self._place(app, page, body)
        app.pages.append(page)
        return await self._laid_out(app, who, "streamlit_add_page", name) | {"page": page.id}

    async def change_page(self, app_id: str, page_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Rename a page {"name"}, or move it among the pages {"index"}."""
        app = self._app(app_id)
        page = self._page(app, page_id)
        body = body if isinstance(body, dict) else {}
        if "name" in body:
            page.name = rules.check_name(body["name"])
        index = body.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            app.pages.remove(page)
            app.pages.insert(max(0, min(index, len(app.pages))), page)
        return await self._laid_out(app, who, "streamlit_change_page", page.name)

    async def remove_page(self, app_id: str, page_id: str, who: str = "user") -> dict[str, Any]:
        app = self._app(app_id)
        page = self._page(app, page_id)
        app.pages.remove(page)
        return await self._laid_out(app, who, "streamlit_remove_page", page.name)

    async def push(self, app_id: str, page_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Push a piece to a page: {"cell", "index"?, "w"?, "h"?} (at the end, six columns wide)."""
        app = self._app(app_id)
        page = self._page(app, page_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"cell": the Streamlit cell\'s number}.')
        placed = self._place(app, page, body)
        done = await self._laid_out(app, who, "streamlit_push_piece", f"cell {placed.cell} to {page.name}")
        return done | {"page": page.id, "piece": placed.id}

    def _placed(self, page: Page, piece_id: str) -> Placed:
        placed = next((s for s in page.pieces if s.id == piece_id), None)
        if placed is None:
            raise NotFound(f"The page {page.name} has no piece {piece_id}.")
        return placed

    async def change_piece(
        self, app_id: str, page_id: str, piece_id: str, body: Any, who: str = "user"
    ) -> dict[str, Any]:
        """Move a placed piece {"index"} (its place among the page's pieces, from 0), resize it
        {"w": columns of 12, "h": rows or null}, or send it to another page {"page"}."""
        app = self._app(app_id)
        page = self._page(app, page_id)
        placed = self._placed(page, piece_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"index"}, {"w", "h"} or {"page"}.')
        if "w" in body:
            placed.w = rules.check_width(body["w"])
        if "h" in body:
            placed.h = rules.check_rows(body["h"])
        target = page
        if isinstance(body.get("page"), str) and body["page"] != page.id:
            target = self._page(app, body["page"])
            page.pieces.remove(placed)
            target.pieces.append(placed)
        index = body.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            target.pieces.remove(placed)
            target.pieces.insert(max(0, min(index, len(target.pieces))), placed)
        return await self._laid_out(app, who, "streamlit_place_piece", f"{piece_id} on {target.name}")

    async def remove_piece(
        self, app_id: str, page_id: str, piece_id: str, who: str = "user"
    ) -> dict[str, Any]:
        app = self._app(app_id)
        page = self._page(app, page_id)
        page.pieces.remove(self._placed(page, piece_id))
        return await self._laid_out(app, who, "streamlit_remove_piece", f"{piece_id} from {page.name}")

    # ===== run =====

    async def _write(self, app: App) -> None:
        """The app's files as they should be now: every piece alone, every page, the tables they name.
        After this every piece is current."""
        if app.folder is None:
            app.folder = self._files.folder()
        folder = app.folder
        tables = self._tables()
        codes = self._piece_codes(app)
        found = rules.makers(app.codes, app.order)
        app.generation += 1
        stamp = app.generation
        # The entry's own text changes with every run (its last line): Streamlit runs the open pages
        # again when a file's content changes, not when only its time does.
        files: dict[str, str] = {"app.py": f"{rules.ENTRY}# run {stamp}\n", "home.py": rules.HOME}
        listed: list[dict[str, Any]] = [
            {"kind": "home", "file": "home.py", "title": app.title, "path": "home", "default": True}
        ]
        used: list[str] = []
        for cell in app.order:
            made = rules.preview_code(cell, codes, app.order, tables)
            name = f"piece_{cell}_{stamp}.py"
            files[name] = made.code
            used += [t for t in made.tables if t not in used]
            entry = {"kind": "piece", "file": name, "title": codes[cell].name, "path": f"piece-{cell}"}
            listed.append(entry | {"default": False})
        for page in app.pages:
            made = rules.page_code(
                page.name, page.pieces, codes, tables, elsewhere=rules.elsewhere(page, found)
            )
            name = f"page_{page.id}_{stamp}.py"
            files[name] = made.code
            used += [t for t in made.tables if t not in used]
            entry = {"kind": "page", "file": name, "title": page.name, "path": f"page-{page.id}"}
            listed.append(entry | {"default": False})
        # The manifest last: the pages it names are already there.
        files["manifest.json"] = json.dumps({"title": app.title, "pages": listed}, indent=1)
        notes: list[str] = []
        for table in used:
            info, grid = tables[table]
            mark = self._mark(info, grid)
            if app.marks.get(table) == mark and self._files.has_table(folder, table):
                continue
            try:
                data = await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)
            except self.ws.engine_error as error:
                notes.append(f"{table} could not be read from the grid: {error}")
                continue
            except ValueError as error:  # a step that cannot run
                notes.append(f"{table}: {error}")
                continue
            self._files.write_table(folder, table, data)
            app.marks[table] = mark
        self._files.write(folder, files, set(app.written))
        app.written = {name for name in files if name.endswith(".py")}
        self._files.touch(folder, "app.py")  # the open pages run again
        app.ran = {cell: rules.body(app.codes[cell]) for cell in app.order}
        app.ran_at = self._now()
        app.notes = notes

    async def run(self, app_id: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Run the app, or refresh it: its pieces and pages written as they stand, the tables they
        name read from the grid again, its Streamlit process started when it is not running. A body
        may carry the document as the window holds it ({"pieces", "pages", "python", "kernel"})."""
        app = self._app(app_id)
        if isinstance(body, dict):
            self._update(app, body)
        async with app.lock:
            python = app.python or self._runner.default_python()
            if app.process is not None and (not app.process.alive() or app.process.python != python):
                await app.process.stop()  # another Python was chosen for the notebook
                app.process = None
            if app.process is None:
                try:
                    found = await self._runner.check(python)
                except ValueError as error:
                    app.problem = {"kind": "failed", "message": str(error)}
                    return self._state(app)
                if found["missing"]:
                    app.problem = {
                        "kind": "missing",
                        "packages": found["missing"],
                        "python": python,
                        "command": install_command(found["missing"], python),
                    }
                    return self._state(app)
            app.problem = None
            await self._write(app)
            if app.process is None:
                try:
                    app.process = await self._runner.start(python, app.folder or "", app.base)
                except ValueError as error:
                    app.problem = {"kind": "failed", "message": str(error)}
                    return self._state(app)
                self.ws.audit.write(who, "start_streamlit", f"{app.title} ({python})")
        self.ws.audit.write(who, "run_streamlit_app", app.title)
        await self._changed(app)
        return self._state(app)

    async def install(self, app_id: str, who: str = "user") -> dict[str, Any]:
        """Install what the app needs (Streamlit, pandas, pyarrow) into the notebook's own Python."""
        app = self._app(app_id)
        python = app.python or self._runner.default_python()
        missing = (await self._runner.check(python))["missing"]
        if not missing:
            return {"ok": True, "output": "", "python": python, "packages": []}
        code, output = await self._runner.install(python, missing)
        self.ws.audit.write(who, "install_packages", f"{', '.join(missing)} into {python}")
        if code == 0:
            app.problem = None
        said = output if code is not None else "The install took too long and was stopped."
        return {"ok": code == 0, "output": said, "python": python, "packages": missing}

    # ===== stop =====

    async def _stop(self, app: App) -> None:
        async with app.lock:
            if app.process is not None:
                await app.process.stop()
                app.process = None
            if app.folder is not None:
                self._files.remove(app.folder)
                app.folder = None
            app.ran = {}
            app.marks = {}
            app.written = set()

    async def stop(self, app_id: str, who: str = "user") -> dict[str, Any]:
        """Stop the app's Streamlit process and remove its temporary folder; its pages stay."""
        app = self._app(app_id)
        await self._stop(app)
        self.ws.audit.write(who, "stop_streamlit", app.title)
        await self._changed(app)
        return self._state(app)

    async def close(self, app_id: str) -> None:
        """The document was closed: its app goes."""
        app = self._apps.pop(app_id, None)
        self._gone_since.pop(app_id, None)
        if app is not None:
            await self._stop(app)
            await self._changed(app)

    async def kernel_stopped(self, kernel_id: str) -> None:
        """A document's kernel stopped: its Streamlit process stops with it."""
        for app in list(self._apps.values()):
            if app.kernel == kernel_id and (app.process is not None or app.folder is not None):
                await self._stop(app)
                await self._changed(app)

    async def stop_orphans(self, open_windows: set[str]) -> list[str]:
        """Close each app whose Workbench window has been gone for ORPHAN_SECONDS (a reload or a slip
        keeps it a minute). An app no window opened (the agent's) is left alone."""
        closed: list[str] = []
        now = self._now()
        for app in list(self._apps.values()):
            if app.window is None or app.window in open_windows:
                self._gone_since.pop(app.id, None)
            elif now - self._gone_since.setdefault(app.id, now) >= ORPHAN_SECONDS:
                await self.close(app.id)
                closed.append(app.id)
        return closed

    async def stop_all(self) -> None:
        for app_id in list(self._apps):
            await self.close(app_id)

    # ===== export =====

    async def export(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Export the designed pages as a Streamlit app, into {"folder"}: app.py, a module for each
        page, data/ (each table the pages name, as Parquet, after its steps), requirements.txt and
        README.txt. It runs without this app."""
        app = self._app(app_id)
        folder = body.get("folder") if isinstance(body, dict) else None
        if not isinstance(folder, str) or not folder.strip():
            raise StreamlitError('Send {"folder": "where the app goes"}.')
        if isinstance(body, dict) and ("pieces" in body or "pages" in body):
            self._update(app, body)
        tables = self._tables()
        title = app.title.rsplit(".", 1)[0] or "Streamlit app"
        made = rules.export(title, app.pages, self._piece_codes(app), tables)
        data: dict[str, bytes] = {}
        for table in made.tables:
            info, grid = tables[table]
            data[table] = await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)
        try:
            target, written = self._files.export(folder, made.files, data)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except PermissionError as error:
            raise Conflict(str(error)) from None
        self.ws.audit.write(who, "export_streamlit_app", target, files=len(written))
        return {
            "folder": target,
            "files": written,
            "pages": [p.name for p in app.pages],
            "tables": list(made.tables),
            "problems": list(made.problems),
            "run": "streamlit run app.py",
        }


KernelStopped = Callable[[str], Awaitable[None]]
