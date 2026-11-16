"""Streamlit in the Workbench (docs/ideas.md, the Streamlit canvas, 2026-11-15; rules in
domain/streamlit_cells.py, domain/streamlit_use.py and domain/projects.py). For the Workbench window
and the agent alike. There is no Streamlit kind of cell and no page designer window. Two kinds of app:

  a document's   each open notebook or script tells this service its Python cells as they are typed.
                 The ones that call Streamlit are shown live in their own cells (each alone, with the
                 live cells that make the names it reads)
  a canvas       a Streamlit app: a document of its own (sales.stapp.json) of pages and blocks. A
                 block is a LINK to a Python cell of a notebook or script and its place on a 12-column
                 grid. The canvas holds no code: Play reads each linked cell as it is now, from the
                 open document when one holds the file (saved or not), else from the file

  run       write the app into its own temporary folder (a canvas: each page as ONE Streamlit page; a
            document: each live cell alone), the tables it names as Parquet, and start its Streamlit
            process: one process an app, in the document's own Python (a canvas: its first linked
            file's)
  state     each block's (or live cell's) state: missing, not run, out of date (its code changed, a
            table it names did, or the page's layout did), or current. Nothing runs by itself
  export    the pages as a folder that runs alone (app.py, the data as Parquet)
  save as   the project as one zip: data.py, pages/*.py (written into the project, each importing
            from data.py), requirements.txt, README.txt, the canvas's file and the linked files. No
            rows and no secrets

The agent's export (and a Save as that would first write a data.ipynb holding a pasted table's rows)
waits for the user's Allow, as the grid's export does (the owner, 2026-11-15): the same approval
request and the same prompt in the page (services/agent.py Approvals), naming the app, the folder
and the tables whose rows go. It asks and writes in one request, so what is written is what the
user allowed: that folder, those tables. The user's own click asks nothing.

Memory only, but for an app's temporary folder (removed when the app stops), an export, and Save as.
The canvas's file is saved by the Workbench window (services/workbench.py), on the user's click.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import app_settings as page_settings
from swissarmybench.domain import approvals, controllers, notebooks, projects
from swissarmybench.domain import dictionary as data_dictionary
from swissarmybench.domain import streamlit_cells as rules
from swissarmybench.domain.app_settings import AppSettings
from swissarmybench.domain.blades import install_command
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.datasets import DatasetInfo, quote
from swissarmybench.domain.export import ExportOptions
from swissarmybench.domain.grids import POS, Grid
from swissarmybench.domain.projects import DataCell
from swissarmybench.domain.streamlit_cells import (
    Block,
    Facts,
    Fallback,
    Key,
    Page,
    PieceCode,
    StreamlitError,
    export_detail,
    save_as_detail,
)
from swissarmybench.services.agent import Approvals
from swissarmybench.services.export import ExportWriter
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.streamlit_documents import file_cells, sent_cells
from swissarmybench.services.streamlit_ports import Files, Process, ProjectFiles, Runner
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

MAX_APPS: int = 80
# How long an app outlives the Workbench window that opened it (a reload keeps it a minute).
ORPHAN_SECONDS: float = 60.0
LIVE_PATH: str = "/streamlit/live/"
_PARQUET = ExportOptions(format="parquet", provenance=False)
_UNSET: Any = object()


@dataclass
class App:
    id: str
    secret: str
    title: str
    canvas: bool = False
    # A document's app: the notebook's or script's path. A canvas: its own file's (None: not saved yet).
    document: str | None = None
    python: str | None = None
    window: str | None = None  # the Workbench window that opened it (None: the agent did)
    kernel: str | None = None  # the document's kernel, when it has one
    unsaved: bool = False  # a document's: the window holds changes its file does not
    # A document's Python cells (their numbers in order, their code) and the ones that call Streamlit.
    order: list[int] = field(default_factory=list)
    codes: dict[int, str] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)  # the cells that have a name of their own
    # Its Markdown and HTML cells (their code is the page's: rules.text_code), by number.
    kinds: dict[int, str] = field(default_factory=dict)
    live: list[int] = field(default_factory=list)
    # Every cell of the document, as the window holds it (only a project's data.ipynb sends them).
    every: list[DataCell] | None = None
    dictionary: dict[str, Any] | None = None  # a project's data.ipynb: its descriptions, as held
    pages: list[Page] = field(default_factory=list)  # a canvas's
    settings: AppSettings = field(default_factory=AppSettings)  # a canvas's page settings
    # What was last written: each cell's code (None: it was missing), each page's layout, each
    # table's mark, the files' names.
    ran: dict[Key, str | None] = field(default_factory=dict)
    laid: dict[str, str] = field(default_factory=dict)
    marks: dict[str, str] = field(default_factory=dict)
    written: set[str] = field(default_factory=set)
    ran_at: float | None = None
    folder: str | None = None
    process: Process | None = None
    generation: int = 0
    problem: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)  # what the last run could not do
    # Each page's last test (services/controllers.py): the page's code then, and what it found.
    tested: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def key(self) -> str:
        return f"{self.id}-{self.secret}"

    @property
    def base(self) -> str:
        return f"{LIVE_PATH}{self.key}"

    def running(self) -> bool:
        return self.process is not None and self.process.alive()


@dataclass
class Linked:
    """A canvas's linked cells as they are now."""

    cells: dict[str, dict[int, str]] = field(default_factory=dict)  # by file: its cells' code (a page's)
    names: dict[str, dict[int, str]] = field(default_factory=dict)  # by file: its cells' own names
    kinds: dict[str, dict[int, str]] = field(default_factory=dict)  # by file: its Markdown and HTML cells
    missing: dict[str, str] = field(default_factory=dict)  # a file that cannot be read, and why
    unsaved: list[str] = field(default_factory=list)  # the files an open document holds changes of
    python: str | None = None  # the first linked file's own Python

    def code(self, key: Key) -> str | None:
        return self.cells.get(key[0], {}).get(key[1])

    def name(self, key: Key) -> str | None:
        return self.names.get(key[0], {}).get(key[1])

    def kind(self, key: Key) -> str:
        return self.kinds.get(key[0], {}).get(key[1], "code")


def _name(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _called(app: App) -> str:
    """An app as the approval prompt names it: its file, or its title while it has none."""
    return _name(app.document) if app.document else f'"{app.title}" (not saved yet)'


def _where(document: str, cell: int) -> str:
    return f"{_name(document)} @cell{cell}"


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
        project_files: ProjectFiles,
        table_cells: Callable[[list[str] | None], Awaitable[tuple[list[notebooks.Cell], int]]],
        arrange: Callable[[Any], Awaitable[dict[str, Any]]],
        approvals: Approvals,
    ) -> None:
        self.ws = ws
        self._files = files
        # The user's Allow for what the agent writes to disk with table rows in it (the export).
        self._approvals = approvals
        self._runner = runner
        self._writer = writer
        self._now = now
        self._read = read_document  # a file's text and full path (the Workbench's documents)
        self._environment_of = environment_of  # the Python remembered for a document
        self._project = project_files
        # The open tables named as a new notebook's Tables group (services/table_cells.py).
        self._table_cells = table_cells
        self._arrange = arrange  # a notebook's cells with its tables' cells as the grid has them now
        self._apps: dict[str, App] = {}
        self._gone_since: dict[str, float] = {}

    # ===== apps =====

    def _app(self, app_id: str, canvas: bool | None = None) -> App:
        app = self._apps.get(app_id)
        if app is None:
            raise NotFound(
                "That Streamlit app is not open (its document was closed, or the server restarted)."
            )
        if canvas is True and not app.canvas:
            raise StreamlitError(
                "That is a notebook's or script's own app: it has no pages. Open a Streamlit app."
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
        """Open an app.

        A document's, as the Workbench window holds it: {"title", "document", "python", "window",
        "kernel", "cells"}. A canvas: {"canvas": true, "title", "document"?, "window", "pages"}.
        Or from a file: {"path"}: a Streamlit app's file (a canvas), a notebook or a script."""
        if not isinstance(body, dict):
            raise StreamlitError('Send {"path": a file}, {"title", "cells"}, or {"canvas": true, "pages"}.')
        if len(self._apps) >= MAX_APPS:
            raise Conflict(f"{MAX_APPS} documents are open: close one first.")
        app = App(
            secrets.token_hex(4), secrets.token_hex(16), "Streamlit app", canvas=body.get("canvas") is True
        )
        path = body.get("path")
        if isinstance(path, str) and path and "cells" not in body and "pages" not in body:
            try:
                text, full, _ = self._read(path)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            app.document = full
            if rules.is_app(full):
                app.canvas = True
                app.title = rules.app_title(full)
                app.pages = rules.read_app(text, lambda link: rules.resolve_link(full, link))
                app.settings = page_settings.read_app_settings(text)
            else:
                app.title = _name(full)
                app.python = self._environment_of(full)
                try:
                    self._take(app, *file_cells(full, text))
                except notebooks.NotebookError as error:
                    raise StreamlitError(str(error)) from None
        self._apps[app.id] = app
        try:
            self._update(app, body)
        except StreamlitError:
            del self._apps[app.id]
            raise
        self.ws.audit.write(who, "open_streamlit_app", app.title)
        # Its live cells, or its Markdown and HTML cells; a canvas: the documents it links to.
        if app.canvas or self._shown(app):
            await self._cells_changed()
        return self._state(app)

    @staticmethod
    def _take(app: App, cells: list[tuple[int, str]], names: dict[int, str], kinds: dict[int, str]) -> bool:
        """A document's cells as they are now: its Python cells, and its Markdown and HTML cells as a
        page writes them (true: a cell's code or name changed)."""
        codes = dict(cells)
        changed = codes != app.codes or names != app.names or kinds != app.kinds
        app.order = [cell for cell, _ in cells]
        app.codes = codes
        app.names = names
        app.kinds = kinds
        app.live = rules.live_cells(cells, kinds)
        return changed

    def _update(self, app: App, body: dict[str, Any]) -> bool:
        """What the window knows about the document, as it stands now (true: a cell's code changed)."""
        if isinstance(body.get("title"), str) and body["title"].strip():
            app.title = body["title"].strip()[:200]
        if "document" in body and (body["document"] is None or isinstance(body["document"], str)):
            app.document = body["document"] or None
        if "python" in body and (body["python"] is None or isinstance(body["python"], str)):
            app.python = body["python"] or None
        if isinstance(body.get("window"), str) and 0 < len(body["window"]) <= 64:
            app.window = body["window"]
        if "kernel" in body and (body["kernel"] is None or isinstance(body["kernel"], str)):
            app.kernel = body["kernel"]
        if "unsaved" in body:
            app.unsaved = body["unsaved"] is True
        if app.canvas:
            if "settings" in body:
                app.settings = page_settings.read_settings(body["settings"])
            if "pages" in body:
                app.pages = rules.read_pages(body["pages"])
                for page in app.pages:
                    for block in page.blocks:
                        block.document = rules.resolve_link(app.document, block.document)
            return False
        if isinstance(body.get("dictionary"), dict):
            app.dictionary = data_dictionary.read(body["dictionary"])
        if isinstance(body.get("every"), list):
            app.every = [
                DataCell(
                    str(raw.get("kind") or "code"),
                    str(raw.get("source") or ""),
                    str(raw.get("role") or ""),
                    raw.get("table") if isinstance(raw.get("table"), str) else None,
                    raw.get("number") if isinstance(raw.get("number"), int) else None,
                )
                for raw in body["every"][: notebooks.MAX_CELLS]
                if isinstance(raw, dict)
            ]
        return self._take(app, *sent_cells(body["cells"])) if "cells" in body else False

    async def _tell_canvases(self, document: App) -> None:
        """A document's cells changed: each canvas that links to it may be out of date now."""
        if document.canvas or not document.document:
            return
        for app in self._apps.values():
            if app.canvas and any(
                rules.same_file(b.document, document.document) for p in app.pages for b in p.blocks
            ):
                await self._changed(app)

    def unsaved(self) -> list[str]:
        """The open documents whose windows hold changes their files do not (asked before an update)."""
        return [app.title for app in self._apps.values() if app.unsaved]

    def documents(self) -> list[str]:
        """The files the documents open in a Workbench window hold (saved ones: notebooks, scripts, apps)."""
        return [app.document for app in self._apps.values() if app.document]

    def listing(self) -> dict[str, Any]:
        return {"apps": [self._summary(app) for app in self._apps.values()]}

    def _summary(self, app: App) -> dict[str, Any]:
        said: dict[str, Any] = {
            "app": app.id,
            "kind": "canvas" if app.canvas else "document",
            "title": app.title,
            "document": app.document,
            "running": app.running(),
        }
        if app.canvas:
            return said | {
                "pages": [{"id": p.id, "name": p.name, "blocks": len(p.blocks)} for p in app.pages]
            }
        return said | {"cells": len(app.order), "live": list(app.live)}

    def state(self, app_id: str) -> dict[str, Any]:
        return self._state(self._app(app_id))

    async def sync(self, app_id: str, body: Any) -> dict[str, Any]:
        """The document as the Workbench window holds it now: a notebook's or script's Python cells;
        a canvas's title and file. Nothing runs."""
        app = self._app(app_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"cells": [{"cell": 4, "code": "..."}]}.')
        before = self._pane_mark(app)
        if self._update(app, body):
            await self._tell_canvases(app)
        if self._pane_mark(app) != before:
            await self._cells_changed()
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

    # ===== a canvas's linked cells =====

    def _open_document(self, path: str) -> App | None:
        """The open notebook or script that holds a file (its text as the window has it, saved or not)."""
        for app in self._apps.values():
            if not app.canvas and app.document and rules.same_file(app.document, path):
                return app
        return None

    def _linked(self, app: App) -> Linked:
        """Each file the canvas links to, as it is now: from the open document that holds it, else
        from the file."""
        found = Linked()
        for document in dict.fromkeys(b.document for p in app.pages for b in p.blocks):
            held = self._open_document(document)
            if held is not None:
                found.cells[document] = dict(held.codes)
                found.names[document] = dict(held.names)
                found.kinds[document] = dict(held.kinds)
                if held.unsaved:
                    found.unsaved.append(document)
                python = held.python
            else:
                try:
                    text, full, _ = self._read(document)
                    cells, names, kinds = file_cells(full, text)
                    found.cells[document] = dict(cells)
                    found.names[document] = names
                    found.kinds[document] = kinds
                except FileNotFoundError:
                    found.missing[document] = f"{document} is missing"
                    continue
                except (notebooks.NotebookError, ValueError, OSError) as error:
                    found.missing[document] = f"{document} cannot be read ({error})"
                    continue
                python = self._environment_of(document)
            found.python = found.python or python
        return found

    def _gone(self, block: Block, linked: Linked) -> str | None:
        """What to say for a block whose cell is not there (None: it is)."""
        if block.document in linked.missing:
            return f"{linked.missing[block.document]}: this block links to its cell {block.cell}."
        if linked.code(block.key) is None:
            return f"{_name(block.document)} has no cell {block.cell} for a page now ({block.document})."
        return None

    def _canvas_pieces(
        self, app: App, linked: Linked
    ) -> tuple[dict[Key, PieceCode], dict[Key, Facts], dict[Key, str]]:
        """The placed cells' code, every linked file's cells' facts, and the words for where each is."""
        pieces: dict[Key, PieceCode] = {}
        for page in app.pages:
            for block in page.blocks:
                code = linked.code(block.key)
                if code is not None and block.key not in pieces:
                    where = _where(block.document, block.cell)
                    name = rules.cell_title(code, block.cell, linked.name(block.key))
                    pieces[block.key] = PieceCode(block.cell, name, code, where)
        found = {
            (doc, cell): rules.facts(code)
            for doc, cells in linked.cells.items()
            for cell, code in cells.items()
        }
        return pieces, found, {key: _where(*key) for key in found}

    @staticmethod
    def fallbacks(page: Page, linked: Linked) -> dict[str, Fallback]:
        """The defaults a page can use: the contracts of the linked cells that are not on it."""
        codes = {(d, c): code for d, held in linked.cells.items() for c, code in held.items()}
        titles = {key: rules.cell_title(code, key[1], linked.name(key)) for key, code in codes.items()}
        where = {key: _where(*key) for key in codes}
        return controllers.fallbacks([b.key for b in page.blocks], codes, titles, where)

    @staticmethod
    def _layout(page: Page) -> str:
        return json.dumps([[b.id, b.document, b.cell, b.row, b.column, b.w, b.h] for b in page.blocks])

    # ===== state =====

    def _piece_codes(self, app: App) -> dict[int, PieceCode]:
        return {
            cell: PieceCode(
                cell, rules.cell_title(app.codes[cell], cell, app.names.get(cell)), app.codes[cell]
            )
            for cell in app.live
        }

    def _stale(self, app: App, key: Key, code: str | None, changed: list[str], running: bool) -> str:
        if code is None:
            return "missing"
        ran = app.ran.get(key, _UNSET)
        if not running or ran is _UNSET:
            return "notRun"
        return "outOfDate" if ran is None or rules.body(code) != ran or changed else "current"

    def _common(self, app: App, running: bool) -> dict[str, Any]:
        return {
            "app": app.id,
            "kind": "canvas" if app.canvas else "document",
            "title": app.title,
            "document": app.document,
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
        }

    def _state(self, app: App) -> dict[str, Any]:
        tables = self._tables()
        now = {name: self._mark(info, grid) for name, (info, grid) in tables.items()}
        running = app.running()
        if app.canvas:
            return self._canvas_state(app, tables, now, running)
        found = rules.makers(app.codes, app.live)
        pieces: list[dict[str, Any]] = []
        for cell in app.live:
            code = app.codes[cell]
            mine = found[cell]
            named = rules.tables_named(code, tables)
            changed = [t for t in named if app.marks.get(t) != now[t]]
            state = self._stale(app, ("", cell), code, changed, running)
            pieces.append(
                {
                    "cell": cell,
                    "name": rules.cell_title(code, cell, app.names.get(cell)),
                    "makes": rules.shown_makes(mine),
                    "reads": [n for n in mine.reads if n not in rules.PROVIDED and n not in named],
                    "tables": named,
                    "inputs": [c for c, _ in rules.inputs_of(cell, found, app.live)],
                    "problem": mine.problem,
                    "state": state,
                    # The tables it names that changed in the grid since the app last ran.
                    "changed": changed if state == "outOfDate" else [],
                    "code_changed": state == "outOfDate" and rules.body(code) != app.ran[("", cell)],
                    "preview": f"{app.base}/piece-{cell}" if running and ("", cell) in app.ran else None,
                }
            )
        return self._common(app, running) | {
            "python": app.python or self._runner.default_python(),
            # The Python cells that call Streamlit: each is shown live in its own cell.
            "pieces": pieces,
        }

    def _canvas_state(
        self, app: App, tables: dict[str, tuple[DatasetInfo, Grid]], now: dict[str, str], running: bool
    ) -> dict[str, Any]:
        linked = self._linked(app)
        pieces, found, where = self._canvas_pieces(app, linked)
        pages: list[dict[str, Any]] = []
        for page in app.pages:
            gone = {b.id: said for b in page.blocks if (said := self._gone(b, linked))}
            fallen = self.fallbacks(page, linked)
            made = rules.page_code(
                page.name,
                page.blocks,
                pieces,
                tables,
                elsewhere=rules.elsewhere(page, found, where),
                gone=gone,
                fallbacks=fallen,
            )
            placed = [
                controllers.Placed(
                    b.id,
                    linked.code(b.key),
                    linked.kind(b.key),
                    f"{pieces[b.key].name}, {_name(b.document)} cell {b.cell}" if b.key in pieces else "",
                    _name(b.document).lower() == projects.DATA_NOTEBOOK,
                )
                for b in page.blocks
            ]
            tested = app.tested.get(page.id)
            fresh = (
                tested["result"] if tested and tested["mark"] == controllers.test_mark(placed, made) else None
            )
            notes, noted = controllers.page_notes(
                placed, made, fallen, [*tables, *self.data_names(app)], fresh
            )
            blocks: list[dict[str, Any]] = []
            stale = running and app.laid.get(page.id) != self._layout(page)
            for block in page.blocks:
                code = linked.code(block.key)
                mine = found.get(block.key, Facts()) if code is not None else Facts()
                named = rules.tables_named(code, tables) if code is not None else []
                changed = [t for t in named if app.marks.get(t) != now[t]]
                state = self._stale(app, block.key, code, changed, running)
                stale = stale or (
                    running
                    and state != "current"
                    and not (state == "missing" and app.ran.get(block.key, _UNSET) is None)
                )
                blocks.append(
                    block.to_json()
                    | {
                        "name": pieces[block.key].name if code is not None else None,
                        # code, markdown or html: a text block is marked T on the canvas
                        "kind": linked.kind(block.key) if code is not None else None,
                        "where": _where(block.document, block.cell),
                        "makes": rules.shown_makes(mine),
                        "reads": [n for n in mine.reads if n not in rules.PROVIDED and n not in named],
                        "tables": named,
                        "problem": mine.problem,
                        # In red on the block: the cell is gone, or its file is.
                        "missing": gone.get(block.id),
                        "state": state,
                        "changed": changed if state == "outOfDate" else [],
                    }
                    | notes[block.id]
                )
            pages.append(
                {
                    "id": page.id,
                    "name": page.name,
                    "blocks": blocks,
                    "order": list(made.order),
                    "tables": list(made.tables),
                    "problems": list(made.problems),
                    "rows": [[b.id for b in row] for row in rules.rows(page.blocks)],
                    "out_of_date": stale,
                    "address": f"{app.base}/page-{page.id}" if running and page.id in app.laid else None,
                }
                | noted
            )
        return self._common(app, running) | {
            "python": linked.python or self._runner.default_python(),
            "unsaved": [_name(d) for d in linked.unsaved],
            "pages": pages,
            "settings": app.settings.to_json(),
        }

    # ===== what a lineage reads (services/lineage.py) =====

    def held(self, path: str) -> App | None:
        """The open notebook or script that holds a file: its cells as its window has them now."""
        return self._open_document(path)

    def canvas(self, app_id: str) -> App:
        return self._app(app_id, canvas=True)

    # ===== App mode: the page settings, and the live page's state =====

    def _logo(self, app: App) -> str | None:
        """The logo's whole path (the settings hold it relative to the app's file)."""
        logo = app.settings.logo
        if not logo or rules.is_absolute(logo) or not app.document:
            return logo or None
        return self._project.path(self._project.folder_of(app.document), logo)

    async def set_settings(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """The page settings: {"title", "icon", "layout", "logo", "colours": {...}} (a part is enough)."""
        app = self._app(app_id, canvas=True)
        app.settings = page_settings.changed(app.settings, body)
        self.ws.audit.write(who, "streamlit_page_settings", app.title)
        await self._changed(app)
        return self._state(app)

    def session(self, app_id: str) -> dict[str, Any]:
        """What the live page's session holds (st.session_state), each key with its block's name."""
        app = self._app(app_id, canvas=True)
        raw = self._files.read(app.folder, page_settings.STATE_FILE) if app.folder and app.running() else None
        try:
            held = json.loads(raw) if raw else {}
        except ValueError:
            held = {}
        linked = self._linked(app)
        pieces = self._canvas_pieces(app, linked)[0]
        blocks = [
            (b.id, pieces[b.key].name, pieces[b.key].code)
            for p in app.pages
            for b in p.blocks
            if b.key in pieces
        ]
        return {"app": app.id, "running": app.running(), "state": page_settings.state_rows(held, blocks)}

    async def _changed(self, app: App) -> None:
        await self.ws.live.broadcast({"type": "streamlit_changed", "app": app.id})

    # ===== the Streamlit cells pane: every cell that calls Streamlit, by document =====

    @staticmethod
    def _shown(app: App) -> list[int]:
        """The cells the pane lists of a document: its live cells, then its Markdown and HTML cells
        that show something (under their own heading, Text). A project's data.ipynb adds its named
        cells (the model a page reads: 2026-11-16, "a person building a page always sees the cells
        they can place")."""
        texts = [c for c in app.order if c in app.kinds and rules.runs_something(app.codes[c])]
        named: list[int] = []
        if _name(app.document or app.title).lower() == projects.DATA_NOTEBOOK:
            named = [c for c in app.order if c in app.names and c not in app.live and c not in app.kinds]
        return [*app.live, *named, *texts]

    @classmethod
    def _pane_mark(cls, app: App) -> str:
        """What the pane shows of a document: its live and text cells' names and code."""
        return json.dumps(
            [app.title, app.document, [[c, app.names.get(c), app.codes[c]] for c in cls._shown(app)]],
            default=str,
        )

    async def _cells_changed(self) -> None:
        await self.ws.live.broadcast({"type": "streamlit_cells"})

    def _pane_entry(
        self, document: str | None, cell: int, code: str, name: str | None, kind: str = "code"
    ) -> dict[str, Any]:
        mine = rules.facts(code)
        tables = rules.tables_named(code, self._tables())
        return {
            "cell": cell,
            "name": rules.cell_title(code, cell, name),
            "named": bool(name),
            # code, markdown or html: the pane lists a document's Markdown and HTML cells under Text
            "kind": kind,
            "where": f"{_name(document)} @cell{cell}" if document else f"@cell{cell}",
            "makes": rules.shown_makes(mine),
            "reads": [n for n in mine.reads if n not in rules.PROVIDED and n not in tables],
            "tables": tables,
        }

    def pane(self, folder: str | None = None) -> dict[str, Any]:
        """The Streamlit cells pane: every Python cell that calls Streamlit, and every Markdown and HTML
        cell (they go on a page too), grouped by document. From each open notebook and script (as its
        window holds it, saved or not); from every notebook and script an open canvas links to, read
        from its file when no window holds it (as the canvas reads it); and, with `folder` (an open
        project's), from the project's notebooks and scripts on disk that no window holds."""
        documents: list[dict[str, Any]] = []
        seen: list[str] = []
        for app in self._apps.values():
            shown = self._shown(app)
            if app.canvas or not shown:
                continue
            if app.document:
                if any(rules.same_file(app.document, d) for d in seen):
                    continue
                seen.append(app.document)
            cells = [
                self._pane_entry(app.document, c, app.codes[c], app.names.get(c), app.kinds.get(c, "code"))
                for c in shown
            ]
            documents.append({"document": app.document, "title": app.title, "open": True, "cells": cells})
        on_disk: dict[str, str] = {}  # each file to read: its path, the title it is listed by
        for app in self._apps.values():
            if app.canvas:
                on_disk |= {b.document: _name(b.document) for p in app.pages for b in p.blocks}
        if folder:
            try:
                names = self._project.names(folder)
            except (FileNotFoundError, OSError):
                names = []
            for name in projects.project_files(names):
                if not rules.is_app(name):
                    on_disk.setdefault(self._project.path(folder, name), name)
        for path, title in on_disk.items():
            if any(rules.same_file(path, d) for d in seen):
                continue
            entry = self._file_entry(path, title)
            if entry is not None:
                seen.append(entry["document"])
                documents.append(entry)
        return {"documents": documents}

    def _file_entry(self, path: str, title: str) -> dict[str, Any] | None:
        """A notebook's or script's pane entry read from its file (None: nothing to list, or no file)."""
        try:
            text, full, _ = self._read(path)
            codes, named, kinds = file_cells(full, text)
        except (FileNotFoundError, OSError, ValueError, notebooks.NotebookError):
            return None  # a file that cannot be read has nothing to list
        held = App("", "", title, document=full, order=[c for c, _ in codes], codes=dict(codes))
        held.names, held.kinds = named, kinds
        held.live = rules.live_cells(codes, kinds)
        cells = [
            self._pane_entry(full, c, held.codes[c], named.get(c), kinds.get(c, "code"))
            for c in self._shown(held)
        ]
        return {"document": full, "title": title, "open": False, "cells": cells} if cells else None

    # ===== a canvas's pages and blocks =====

    def _page(self, app: App, page_id: str) -> Page:
        page = next((p for p in app.pages if p.id == page_id), None)
        if page is None:
            raise NotFound(f"This app has no page {page_id}.")
        return page

    async def _laid_out(self, app: App, who: str, what: str, detail: str) -> dict[str, Any]:
        """A page changed. Nothing runs: a page that is showing live is out of date until Play."""
        self.ws.audit.write(who, what, f"{app.title}: {detail}")
        await self._changed(app)
        return self._state(app)

    def _moved(self, page: Page, block: Block, body: dict[str, Any]) -> None:
        """A block's place as asked: {"row", "column"}; with "insert" a new row is made at `row` (the
        rows from there move down). Then the grid settles."""
        if "column" in body:
            block.column = rules.check_column(body["column"])
        if "row" in body:
            row = rules.check_row(body["row"])
            if body.get("insert") is True:
                for other in page.blocks:
                    if other is not block and other.row >= row:
                        other.row += 1
            block.row = row
        # The moved block keeps the place it was given: a neighbour it would lie on goes below.
        rules.settle(page.blocks, block)

    def _place(self, app: App, page: Page, body: dict[str, Any]) -> Block:
        document, cell = rules.check_link(body.get("document"), body.get("cell"))
        document = rules.resolve_link(app.document, document)
        if not rules.is_absolute(document):
            raise StreamlitError("A block links to a saved notebook or script: send its whole path.")
        if len(page.blocks) >= rules.MAX_PLACED:
            raise Conflict(f"A page holds at most {rules.MAX_PLACED} blocks.")
        probe = App("", "", "", canvas=True, pages=[Page("", "", [Block("", document, cell)])])
        linked = self._linked(probe)
        if document in linked.missing:
            raise NotFound(f"{linked.missing[document]}.")
        if linked.code((document, cell)) is None:
            raise StreamlitError(
                f"{_name(document)} has no cell {cell} for a page: a page takes a Python, Markdown "
                "or HTML cell."
            )
        width = rules.check_width(body.get("w", rules.DEFAULT_WIDTH))
        row, column = rules.free_place(page.blocks, width)
        taken = [b.id for p in app.pages for b in p.blocks]
        block = Block(
            rules.next_id("b", taken), document, cell, row, column, width, rules.check_rows(body.get("h"))
        )
        page.blocks.append(block)
        if "row" in body or "column" in body:
            self._moved(page, block, body if "row" in body else body | {"row": row})
        else:
            rules.settle(page.blocks)
        return block

    async def add_page(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """A new page {"name"?}; with {"document", "cell"} that cell is placed on it at once."""
        app = self._app(app_id, canvas=True)
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
        app = self._app(app_id, canvas=True)
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
        app = self._app(app_id, canvas=True)
        page = self._page(app, page_id)
        app.pages.remove(page)
        return await self._laid_out(app, who, "streamlit_remove_page", page.name)

    async def place(self, app_id: str, page_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Place a cell's link on a page: {"document": the notebook's or script's path, "cell": the
        cell's own number, "row"?, "column"?, "insert"?, "w"?, "h"?}. Without a place it goes beside
        the last block when the row has room, else below; six columns wide."""
        app = self._app(app_id, canvas=True)
        page = self._page(app, page_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"document": the file\'s path, "cell": the cell\'s number}.')
        block = self._place(app, page, body)
        done = await self._laid_out(
            app, who, "streamlit_place_block", f"{_where(block.document, block.cell)} on {page.name}"
        )
        return done | {"page": page.id, "block": block.id}

    def _block(self, page: Page, block_id: str) -> Block:
        block = next((b for b in page.blocks if b.id == block_id), None)
        if block is None:
            raise NotFound(f"The page {page.name} has no block {block_id}.")
        return block

    async def change_block(
        self, app_id: str, page_id: str, block_id: str, body: Any, who: str = "user"
    ) -> dict[str, Any]:
        """Move a block {"row", "column", "insert"?} (insert: a new row at `row`), resize it
        {"w": columns of 12, "h": rows of 40 pixels or null}, or send it to another page {"page"}."""
        app = self._app(app_id, canvas=True)
        page = self._page(app, page_id)
        block = self._block(page, block_id)
        if not isinstance(body, dict):
            raise StreamlitError('Send {"row", "column"}, {"w", "h"} or {"page"}.')
        if "w" in body:
            block.w = rules.check_width(body["w"])
        if "h" in body:
            block.h = rules.check_rows(body["h"])
        target = page
        if isinstance(body.get("page"), str) and body["page"] != page.id:
            target = self._page(app, body["page"])
            page.blocks.remove(block)
            rules.settle(page.blocks)
            block.row, block.column = rules.free_place(target.blocks, block.w)
            target.blocks.append(block)
        self._moved(target, block, body)
        return await self._laid_out(app, who, "streamlit_change_block", f"{block_id} on {target.name}")

    async def remove_block(
        self, app_id: str, page_id: str, block_id: str, who: str = "user"
    ) -> dict[str, Any]:
        app = self._app(app_id, canvas=True)
        page = self._page(app, page_id)
        page.blocks.remove(self._block(page, block_id))
        rules.settle(page.blocks)
        return await self._laid_out(app, who, "streamlit_remove_block", f"{block_id} from {page.name}")

    # ===== run =====

    async def _write(self, app: App) -> None:
        """The app's files as they should be now (a canvas: every page; a document: every live cell
        alone) and the tables they name. After this everything is current."""
        if app.folder is None:
            app.folder = self._files.folder()
        folder = app.folder
        tables = self._tables()
        app.generation += 1
        stamp = app.generation
        # The entry's own text changes with every run (its last line): Streamlit runs the open pages
        # again when a file's content changes, not when only its time does.
        files: dict[str, str] = {"app.py": f"{rules.ENTRY}# run {stamp}\n", "home.py": rules.HOME}
        listed: list[dict[str, Any]] = [
            {"kind": "home", "file": "home.py", "title": app.title, "path": "home", "default": True}
        ]
        used: list[str] = []
        ran: dict[Key, str | None] = {}
        notes: list[str] = []
        if app.canvas:
            linked = self._linked(app)
            pieces, found, where = self._canvas_pieces(app, linked)
            # A project's data.py is written again from its data.ipynb; the names it gives beside
            # the tables (the tables come from the grid) are imported from a copy of it.
            given: tuple[str, ...] = ()
            if app.document:
                try:
                    exported = await self._data(self._project.folder_of(app.document), app.title)
                except OSError as error:  # data.py cannot be written (read-only): the page runs without it
                    exported = None
                    notes.append(f"data.py was not written: {error}")
                if exported is not None:
                    given = exported.names
                    files["data.py"] = exported.text
                    notes += [f"data.ipynb, {said}" for said in exported.skipped]
            for page in app.pages:
                gone = {b.id: said for b in page.blocks if (said := self._gone(b, linked))}
                made = rules.page_code(
                    page.name,
                    page.blocks,
                    pieces,
                    tables,
                    elsewhere=rules.elsewhere(page, found, where),
                    gone=gone,
                    imports=given,
                    fallbacks=self.fallbacks(page, linked),
                    trace=page.id,
                )
                name = f"page_{page.id}_{stamp}.py"
                files[name] = made.code + page_settings.STATE_TAIL  # what the session holds: the State panel
                used += [t for t in made.tables if t not in used]
                entry = {"kind": "page", "file": name, "title": page.name, "path": f"page-{page.id}"}
                listed.append(entry | {"default": False})
                for block in page.blocks:
                    code = linked.code(block.key)
                    ran[block.key] = None if code is None else rules.body(code)
            files[rules.TRACE_FILE] = self._files.lineage_helper()
            if any(rules.uses_text_module(piece.code) for piece in pieces.values()):
                # A Markdown or HTML block names a value: the rules that fill it, beside the pages.
                files[rules.TEXT_FILE] = rules.text_file(self._files.helper())
            app.laid = {page.id: self._layout(page) for page in app.pages}
        else:
            codes = self._piece_codes(app)
            for cell in app.live:
                made = rules.preview_code(cell, codes, app.live, tables)
                name = f"piece_{cell}_{stamp}.py"
                files[name] = made.code
                used += [t for t in made.tables if t not in used]
                entry = {"kind": "piece", "file": name, "title": codes[cell].name, "path": f"piece-{cell}"}
                listed.append(entry | {"default": False})
                ran[("", cell)] = rules.body(app.codes[cell])
        # The manifest last: the pages it names are already there.
        shown = page_settings.manifest(app.settings, app.title, self._logo(app) if app.canvas else None)
        files["manifest.json"] = json.dumps(shown | {"pages": listed}, indent=1)
        theme = page_settings.config_toml(app.settings, app.title) if app.canvas else None
        if theme:  # Streamlit reads the theme from the folder it runs in (read when it starts)
            files[page_settings.CONFIG_FILE] = theme
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
        app.ran = ran
        app.ran_at = self._now()
        app.notes = notes

    def _python(self, app: App) -> str:
        if app.canvas:
            return self._linked(app).python or self._runner.default_python()
        return app.python or self._runner.default_python()

    async def run(self, app_id: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Play: run the app, or refresh it. Its pages (a document: its live cells) are written from
        the cells' code as it is now, the tables they name read from the grid again, its Streamlit
        process started when it is not running. A body may carry the document as the window holds it."""
        app = self._app(app_id)
        if isinstance(body, dict) and self._update(app, body):
            await self._tell_canvases(app)
        async with app.lock:
            python = self._python(app)
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
        """Install what the app needs (Streamlit, pandas, pyarrow) into the Python it runs in."""
        app = self._app(app_id)
        python = self._python(app)
        missing = (await self._runner.check(python))["missing"]
        if not missing:
            return {"ok": True, "output": "", "python": python, "packages": []}
        code, output = await self._runner.install(python, missing)
        self.ws.audit.write(who, "install_packages", f"{', '.join(missing)} into {python}")
        if code == 0:
            app.problem = None
        said = output if code is not None else "The install took too long and was stopped."
        return {"ok": code == 0, "output": said, "python": python, "packages": missing}

    # ===== for a page's controllers (services/controllers.py) =====

    def data_names(self, app: App) -> list[str]:
        """The names the canvas's project's data.ipynb makes (its open document's, else its file's)."""
        folder = self._project.folder_of(app.document) if app.document else None
        held = self._open_document(self._project.path(folder, projects.DATA_NOTEBOOK)) if folder else None
        every: list[Any] | None = held.every if held is not None else None
        try:
            if every is None and folder:
                every = notebooks.read_document(self._project.read(folder, projects.DATA_NOTEBOOK) or "{}")[0]
        except (notebooks.NotebookError, ValueError, OSError):
            return []
        return [n for c in every or [] if c.kind == "code" for n in rules.facts(c.source).makes]

    def canvas_parts(
        self, app_id: str
    ) -> tuple[App, Linked, dict[Key, PieceCode], dict[Key, Facts], dict[Key, str]]:
        """A canvas, its linked cells as they are now, its blocks' code, the cells' facts, their words."""
        app = self._app(app_id, canvas=True)
        linked = self._linked(app)
        return (app, linked, *self._canvas_pieces(app, linked))

    def python_of(self, app: App) -> str:
        return self._python(app)

    async def data_module(self, app: App) -> projects.DataModule | None:
        """data.py written again from the project's data.ipynb, as Play writes it (None: none)."""
        return await self._data(self._project.folder_of(app.document), app.title) if app.document else None

    async def table_data(self, table: str) -> bytes:
        """An open table (by its name as a Python variable) after its grid's steps, as Parquet."""
        info, grid = self._tables()[table]
        return await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)

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
            app.laid = {}
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
            if app.canvas or self._shown(app):
                await self._cells_changed()

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

    # ===== the user's Allow, for what the agent writes with rows in it =====

    async def _allowed(self, action: str, subject: str, detail: str) -> None:
        """Wait for the user's answer to the agent's request (the page's approval prompt); refused
        when they decline or do not answer, and then nothing is written."""
        if not await self._approvals.ask(subject, action, detail):
            raise Refused(f"The user declined (or did not answer): {action} {subject} was not done.")

    # ===== export: a folder that runs alone =====

    async def export(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Export the pages as a Streamlit app that runs alone, into {"folder"}: app.py, a module for
        each page, data/ (each table the pages name, as Parquet, after its steps: a copy of the
        rows), requirements.txt and README.txt."""
        app = self._app(app_id, canvas=True)
        folder = body.get("folder") if isinstance(body, dict) else None
        if not isinstance(folder, str) or not folder.strip():
            raise StreamlitError('Send {"folder": "where the app goes"}.')
        tables = self._tables()
        linked = self._linked(app)
        pieces, found, where = self._canvas_pieces(app, linked)
        gone = {b.id: said for p in app.pages for b in p.blocks if (said := self._gone(b, linked))}
        fallen = {page.id: self.fallbacks(page, linked) for page in app.pages}
        made = rules.export(
            app.title,
            app.pages,
            pieces,
            tables,
            found,
            where,
            gone,
            self._files.helper(),
            fallbacks=fallen,
            head=page_settings.page_head(app.settings, app.title),
            config=page_settings.config_toml(app.settings, app.title),
        )
        try:
            target = self._files.export_target(folder)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        if who == "agent":
            # The rows leave the app: only on the user's Allow, for this folder and these tables.
            await self._allowed(
                "export the Streamlit app",
                _called(app),
                export_detail(target, [p.name for p in app.pages], [tables[t][0] for t in made.tables]),
            )
        data: dict[str, bytes] = {}
        for table in made.tables:
            info, grid = tables[table]
            data[table] = await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)
        try:
            target, written = self._files.export(target, made.files, data)
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

    # ===== a project's data: data.ipynb -> data.py =====

    async def _data_cells(self, folder: str) -> list[DataCell] | None:
        """The cells of a project's data.ipynb as they are now: from the open document (saved or
        not: its tables' cells follow the grid there), else from the file, with each open table's
        read-only cell as the grid has it now. None: the folder has none."""
        path = self._project.path(folder, projects.DATA_NOTEBOOK)
        held = self._open_document(path)
        if held is not None and held.every is not None:
            return held.every
        text = self._project.read(folder, projects.DATA_NOTEBOOK)
        if text is None:
            return None
        cells, following = notebooks.read_document(text)
        tables = [c.table for c in cells if c.role == "transformations" and c.table]
        if tables:
            sent = {"kind": "notebook", "cells": [c.to_json() for c in cells], "tables": tables}
            arranged = await self._arrange(sent | {"next_cell": following, "move": False})
            cells = notebooks.read_cells(arranged["cells"])
        return [DataCell(c.kind, c.source, c.role, c.table, c.number) for c in cells]

    async def _data(self, folder: str, title: str) -> projects.DataModule | None:
        """data.py written again from the folder's data.ipynb (None: the folder has no data.ipynb)."""
        try:
            cells = await self._data_cells(folder)
        except (notebooks.NotebookError, ValueError, OSError):
            return None
        if cells is None:
            return None
        held = self._open_document(self._project.path(folder, projects.DATA_NOTEBOOK))
        if held is not None and held.dictionary is not None:
            said = held.dictionary
        else:
            said = data_dictionary.of_notebook(self._project.read(folder, projects.DATA_NOTEBOOK))
        made = projects.data_module(title, cells, said)
        self._project.write(folder, projects.DATA_FILE, made.text)
        return made

    async def export_data(self, folder: str, title: str) -> dict[str, Any]:
        """Export data.py: the project's data.ipynb's code cells in order, as a module."""
        try:
            made = await self._data(folder, title)
        except PermissionError as error:
            raise Conflict(str(error)) from None
        if made is None:
            return {"path": None, "names": [], "fill_in": [], "skipped": [], "requirements": []}
        return {
            "path": self._project.path(folder, projects.DATA_FILE),
            "names": list(made.names),
            "fill_in": list(made.fill_in),
            "skipped": list(made.skipped),
            "requirements": projects.data_requirements(made.text),
        }

    @staticmethod
    def _for_zip(path: str, text: str) -> str:
        """A notebook or script as it goes into a zip: a pasted table's rows taken out, a notebook's
        outputs dropped and its approvals kept as their marks and shapes only (no rows leave)."""
        if notebooks.kind_of(path) != "notebook":
            return projects.script_without_rows(text)
        cells, following = notebooks.read_document(text)
        kept = projects.without_rows([DataCell(c.kind, c.source, c.role, c.table, c.number) for c in cells])
        for cell, data in zip(cells, kept, strict=True):
            cell.source = data.source
            cell.outputs = []
            cell.execution_count = None
            if cell.approved is not None:
                cell.approved = approvals.without_rows(cell.approved)
        return notebooks.write_notebook(cells, next_number=following)

    # ===== save as: the project as one zip =====

    async def save_as(self, app_id: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Save as: the finished app's project as one zip, at {"path": ...zip}.

        The project is the folder of the app's file. Its two exports are written again: data.py from
        data.ipynb (a folder with no data.ipynb gets one first: a read-only cell for each table the
        pages name) and pages/*.py from the canvas (each page a module to drop into a Streamlit app,
        starting with `from data import ...`); requirements.txt gets the lines it lacks. The zip
        holds data.ipynb, data.py, pages/, requirements.txt, README.txt, the app's file and the
        notebooks and scripts it links to. No rows (outputs dropped, a pasted table a stub), no secrets.
        """
        app = self._app(app_id, canvas=True)
        target = body.get("path") if isinstance(body, dict) else None
        if not isinstance(target, str) or not target.strip():
            raise StreamlitError('Send {"path": "where the zip goes"}.')
        if not app.document:
            raise Conflict("Save the app first: its folder is the project that is zipped.")
        folder = self._project.folder_of(app.document)
        linked = self._linked(app)
        pieces, found, where = self._canvas_pieces(app, linked)
        gone = {b.id: said for p in app.pages for b in p.blocks if (said := self._gone(b, linked))}
        tables = self._tables()
        named = list(
            dict.fromkeys(t for piece in pieces.values() for t in rules.tables_named(piece.code, tables))
        )
        try:
            if await self._data_cells(folder) is None:
                names = [tables[t][0].name for t in named]
                cells, following = await self._table_cells(names)
                pasted = projects.tables_with_rows(
                    [DataCell(c.kind, c.source, c.role, c.table, c.number) for c in cells]
                )
                if who == "agent" and pasted:
                    # data.ipynb would hold a pasted table's rows: only on the user's Allow.
                    await self._allowed(
                        "zip the Streamlit app",
                        _called(app),
                        save_as_detail(
                            target,
                            self._project.path(folder, projects.DATA_NOTEBOOK),
                            [i for i in (self.ws.store.get(n) for n in pasted) if i is not None],
                        ),
                    )
                text = notebooks.write_notebook(cells, next_number=following)
                self._project.write(folder, projects.DATA_NOTEBOOK, text)
            data = await self._data(folder, app.title)
            if data is None:
                raise Conflict(f"{folder}'s data.ipynb cannot be read: data.py was not written.")
            app_name = _name(app.document)
            fallen = {page.id: self.fallbacks(page, linked) for page in app.pages}
            made = rules.saved_pages(
                app.pages,
                pieces,
                data.names,
                found,
                where,
                gone,
                app_name,
                fallbacks=fallen,
                head=page_settings.page_head(app.settings, app.title),
            )
            # The theme's colours: .streamlit/config.toml, never over one of the user's own.
            theme = page_settings.config_toml(app.settings, app_name)
            if theme and page_settings.is_own_config(self._project.read(folder, page_settings.CONFIG_FILE)):
                self._project.write(folder, page_settings.CONFIG_FILE, theme)
            problems = list(made.problems)
            lacking = [t for t in named if t not in data.names]
            if lacking:
                problems.append(
                    f"{', '.join(lacking)} is open in the grid but data.ipynb does not make it: the pages "
                    "that read it will not run. Give it a cell in data.ipynb."
                )
            if data.fill_in:
                problems.append(
                    f"data.py cannot read {', '.join(data.fill_in)} again (pasted, dropped, or sent from "
                    "Python): add the code that reads it to data.ipynb."
                )
            # Only this app's own saved pages are written over or taken away: one of the user's
            # (or of another app in the folder) stays as it is.
            kept = self._project.replace_pages(
                folder, made.files, lambda text: rules.is_saved_page(text, app_name)
            )
            problems += [
                f"{name} is not a page this app saved: it was left as it is, and the zip has this app's."
                for name in kept
            ]
            needed = [*made.requirements, *projects.data_requirements(data.text)]
            requirements = projects.merged_requirements(
                self._project.read(folder, projects.REQUIREMENTS_FILE), list(dict.fromkeys(needed))
            )
            self._project.write(folder, projects.REQUIREMENTS_FILE, requirements)
            # A Markdown or HTML block names a value: the rules that fill it go beside data.py.
            helper = rules.text_file(self._files.helper()) if made.texts else None
            if helper is not None:
                self._project.write(folder, rules.TEXT_FILE, helper)
        except PermissionError as error:
            raise Conflict(str(error)) from None
        # The linked files: one inside the project keeps its place; one outside comes along at the
        # zip's top under its own name, and the zip's copy of the app's file links to it there.
        documents = list(dict.fromkeys(b.document for p in app.pages for b in p.blocks))
        inside = {d: self._project.relative(folder, d) for d in documents}
        own = [
            projects.DATA_FILE,
            projects.DATA_NOTEBOOK,
            projects.REQUIREMENTS_FILE,
            "README.txt",
            rules.TEXT_FILE,
            app_name,
            *made.files,
            *(name for name in inside.values() if name),
        ]
        outside = rules.bundle_names([d for d in documents if inside[d] is None], own)
        placed = {d: inside[d] or outside[d] for d in documents}
        files: dict[str, str] = {
            projects.DATA_FILE: data.text,
            projects.REQUIREMENTS_FILE: requirements,
            **made.files,
        }
        if helper is not None:
            files[rules.TEXT_FILE] = helper
        notebook = self._project.read(folder, projects.DATA_NOTEBOOK)
        if notebook is not None:
            files[projects.DATA_NOTEBOOK] = self._for_zip(projects.DATA_NOTEBOOK, notebook)
        for document in documents:
            if document in linked.missing:
                continue
            try:
                files[placed[document]] = self._for_zip(document, self._read(document)[0])
            except (FileNotFoundError, OSError, ValueError):
                problems.append(f"{document} could not be read: it is not in the zip.")
        unsaved = list(linked.unsaved)
        held = self._open_document(self._project.path(folder, projects.DATA_NOTEBOOK))
        if held is not None and held.unsaved:
            unsaved.append(projects.DATA_NOTEBOOK)
        for document in unsaved:
            problems.append(
                f"{_name(document)} has changes that are not saved: the exports have them, the zip's copy "
                "of the file does not."
            )
        files[app_name] = rules.write_app(
            app.pages, lambda d: placed.get(d, d), page_settings.file_line(app.settings)
        )
        if theme:
            files[page_settings.CONFIG_FILE] = theme
        files["README.txt"] = projects.readme(
            app.title,
            [p.name for p in app.pages],
            app_name,
            data.fill_in,
            [placed[d] for d in documents],
            texts=helper is not None,
        )
        try:
            path, written = self._project.zip(target, files)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except PermissionError as error:
            raise Conflict(str(error)) from None
        self.ws.audit.write(who, "save_streamlit_app_as", path, files=len(written))
        return {
            "path": path,
            "project": folder,
            "files": written,
            "pages": [p.name for p in app.pages],
            "data": list(made.tables),
            "fill_in": list(data.fill_in),
            "problems": problems,
        }
