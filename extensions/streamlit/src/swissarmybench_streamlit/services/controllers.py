"""A canvas page's controllers (docs/ideas.md, "After the beta: controllers", 2026-11-15; the rules in
domain/controllers.py and domain/thin_cells.py), for the Workbench window and the agent alike.

  check     each page's contracts against its blocks: the defaults it uses (a maker that is not on the
            page), a contract its code does not keep, a name made twice, a cycle named. The canvas
            shows the same on its blocks (services/streamlit.py's state)
  test      Test this page: the page written so each block records its error, the tables it reads as
            Parquet, in a temporary folder of its own; then Streamlit's AppTest, in the app's own
            Python, tries each controller's values. Each block's failures show on it, red; the folder
            goes when the test ends. Nothing of the user's is written but data.py, as Play writes it
  move      a thin-cell hint's move: the model work of a block's cell as a named cell for data.ipynb,
            and the cell's code after it (one line that reads it back). The window makes the change in
            the open documents (unsaved, as typing does)
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from swissarmybench.domain import projects
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.packages import missing_packages
from swissarmybench.services.workspace import Conflict, NotFound
from swissarmybench_streamlit.domain import controllers, thin_cells
from swissarmybench_streamlit.domain import streamlit_cells as rules
from swissarmybench_streamlit.domain.streamlit_cells import Page
from swissarmybench_streamlit.services.streamlit import App, StreamlitApps
from swissarmybench_streamlit.services.streamlit_ports import ProjectFiles


class Files(Protocol):
    """A test's temporary folder (adapters/streamlit_files.py, the live app's own)."""

    def folder(self) -> str: ...

    def helper(self) -> str: ...

    def write(self, folder: str, files: dict[str, str], keep: set[str]) -> None: ...

    def write_table(self, folder: str, name: str, data: bytes) -> None: ...

    def remove(self, folder: str) -> None: ...


class Tester(Protocol):
    async def check(self, python: str) -> dict[str, Any]: ...

    async def test(self, python: str, folder: str, plan: str) -> str: ...  # what the runner said


class Controllers:
    def __init__(self, apps: StreamlitApps, files: Files, tester: Tester, project: ProjectFiles) -> None:
        self._apps = apps
        self._files = files
        self._tester = tester
        self._project = project
        self._testing: set[tuple[str, str]] = set()

    @staticmethod
    def _page(app: App, page_id: str | None) -> Page:
        """A canvas's page (its first without an id)."""
        page = (
            next((p for p in app.pages if p.id == page_id), None) if page_id else next(iter(app.pages), None)
        )
        if page is None:
            raise NotFound(f"This app has no page {page_id}." if page_id else "This app has no page yet.")
        return page

    def _tables(self) -> list[str]:
        """The open tables' names as Python variables (a tab in the grid), as a page reads them."""
        ws = self._apps.ws
        return list(
            dict.fromkeys(variable_name(i.name) for i in ws.store.all() if ws.grids.first_for(i.name))
        )

    # ===== the check =====

    def check(self, app_id: str, page_id: str | None = None) -> dict[str, Any]:
        """Each page's check (or one page's): its defaults, contract problems, names made twice, cycles,
        and each block's controller (its role, what it makes with types and defaults)."""
        app, linked, pieces, found, where = self._apps.canvas_parts(app_id)
        pages = [self._page(app, page_id)] if page_id else app.pages
        tables = self._tables()
        out: list[dict[str, Any]] = []
        for page in pages:
            fallen = self._apps.fallbacks(page, linked)
            made = rules.page_code(
                page.name,
                page.blocks,
                pieces,
                tables,
                elsewhere=rules.elsewhere(page, found, where),
                fallbacks=fallen,
                containers=page.containers,
            )
            placed = [controllers.Placed(b.id, linked.code(b.key), linked.kind(b.key)) for b in page.blocks]
            check = controllers.check_page(
                [(p.id, p.code) for p in placed if p.code is not None], made, fallen
            ).to_json()
            check["controllers"] = [
                {"block": p.id, "name": pieces[b.key].name} | controllers.describe(p.code).to_json()
                for p, b in zip(placed, page.blocks, strict=True)
                if p.code is not None and p.kind == "code" and controllers.describe(p.code).role
            ]
            out.append({"page": page.id, "name": page.name, "problems": list(made.problems)} | check)
        return {"app": app.id, "pages": out}

    # ===== Test this page =====

    async def test(self, app_id: str, page_id: str, who: str = "user") -> dict[str, Any]:
        """Test this page: every block runs as the page opens and as each controller's values are tried
        (Streamlit's AppTest, in the app's Python). The failures land on their blocks."""
        app, linked, pieces, found, where = self._apps.canvas_parts(app_id)
        page = self._page(app, page_id)
        if not page.blocks:
            raise Conflict(f"{page.name} has no blocks to test yet.")
        if (app.id, page.id) in self._testing:
            raise Conflict(f"{page.name} is being tested already.")
        python = self._apps.python_of(app)
        missing = (await self._tester.check(python))["missing"]
        if missing:
            return {
                "page": page.id,
                "problem": {"kind": "missing"}
                | missing_packages("Test this page", missing, python, own=False),
            }
        self._testing.add((app.id, page.id))
        await self._apps.ws.live.broadcast({"type": "streamlit_changed", "app": app.id})
        folder: str | None = None
        try:
            tables = self._tables()
            gone = {
                b.id: f"{b.document} has no cell {b.cell} for a page now."
                for b in page.blocks
                if b.key not in pieces
            }
            fallen = self._apps.fallbacks(page, linked)
            files: dict[str, str] = {}
            data = await self._apps.data_module(app)
            if data is not None:
                files[projects.DATA_FILE] = data.text

            def written(record: bool) -> rules.PageCode:
                return rules.page_code(
                    page.name,
                    page.blocks,
                    pieces,
                    tables,
                    elsewhere=rules.elsewhere(page, found, where),
                    gone=gone,
                    imports=data.names if data is not None else (),
                    fallbacks=fallen,
                    record=record,
                    containers=page.containers,
                )

            live, made = written(False), written(True)
            files["page.py"] = made.code
            if any(rules.uses_text_module(pieces[b.key].code) for b in page.blocks if b.key in pieces):
                files[rules.TEXT_FILE] = rules.text_file(self._files.helper())
            keyed = [
                (b.id, pieces[b.key].name, rules.keyed(rules.body(pieces[b.key].code).rstrip("\n"), b.id))
                for b in page.blocks
                if b.key in pieces
            ]
            plan = controllers.test_plan(keyed)
            folder = self._files.folder()
            self._files.write(folder, files, set())
            notes: list[str] = []
            for table in made.tables:
                try:
                    self._files.write_table(folder, table, await self._apps.table_data(table))
                except (self._apps.ws.engine_error, ValueError) as error:
                    notes.append(f"{table} could not be read from the grid: {error}")
            said = await self._tester.test(python, folder, json.dumps(plan))
            result = controllers.read_results(said, plan, [b.id for b in page.blocks])
            result.untried += notes
        finally:
            self._testing.discard((app.id, page.id))
            if folder is not None:
                self._files.remove(folder)
        placed = [controllers.Placed(b.id, linked.code(b.key), linked.kind(b.key)) for b in page.blocks]
        app.tested[page.id] = {"mark": controllers.test_mark(placed, live), "result": result.to_json()}
        self._apps.ws.audit.write(who, "test_streamlit_page", f"{app.title}: {page.name}")
        await self._apps.ws.live.broadcast({"type": "streamlit_changed", "app": app.id})
        return {"page": page.id, "name": page.name, "python": python} | result.to_json()

    def testing(self, app_id: str) -> list[str]:
        return [page for app, page in self._testing if app == app_id]

    # ===== a thin cell's move to data.ipynb =====

    def move_plan(self, app_id: str, page_id: str, block_id: str) -> dict[str, Any]:
        """The move of a block's model work: the named cell for the project's data.ipynb (`notebook`:
        its path; `data_code`, `title`), and the block's cell's code after it (`cell_code`)."""
        app, linked, pieces, _, _ = self._apps.canvas_parts(app_id)
        page = self._page(app, page_id)
        block = next((b for b in page.blocks if b.id == block_id), None)
        if block is None:
            raise NotFound(f"The page {page.name} has no block {block_id}.")
        code = linked.code(block.key)
        if code is None or linked.kind(block.key) != "code":
            raise Conflict("Only a Python cell's model work moves to data.ipynb.")
        inputs = [*self._tables(), *self._apps.data_names(app)]
        file = block.document.replace("\\", "/").rsplit("/", 1)[-1]
        words = f"{pieces[block.key].name}, {file} cell {block.cell}"
        move = thin_cells.model_work(code, inputs, words)
        if move is None:
            raise Conflict(f"{pieces[block.key].name} does no model work to move.")
        folder = self._project.folder_of(app.document or block.document)
        return {
            "document": block.document,
            "cell": block.cell,
            "notebook": self._project.path(folder, projects.DATA_NOTEBOOK),
        } | move.to_json()
