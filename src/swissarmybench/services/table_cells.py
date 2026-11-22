"""Every table has a read-only cell (docs/ideas.md, 2026-11-14; rules in domain/table_cells.py).

Two use cases, for the Workbench window and the agent alike:

  listing   every open table as its cell's text: the grid's steps as one DuckDB query whose result is
            the table's own name, and (for a table no code made) the load that goes before it
  arrange   a document's cells with its Tables group as it should be: a notebook's cells, or a
            script's text with its region; each of the user's cells with its uses line
  view      an open table's grid view (its steps applied) as an Arrow stream, read when a kernel's DuckDB
            SQL names it and that Python has no table of the name (feel-a, 2026-11-19): read-only, read
            again each time, never kept

Where each table came from is remembered here (`Origins`): the Workbench kernel that pushed it, the
file it was read from, the connection and query. Memory only; nothing is written.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swissarmybench.domain import notebooks
from swissarmybench.domain import table_cells as rules
from swissarmybench.domain.codegen import variable_name, view_query
from swissarmybench.domain.connection_usage import connection_named
from swissarmybench.domain.datasets import DatasetInfo, quote
from swissarmybench.domain.grids import Grid
from swissarmybench.domain.steps import ViewSettings, describe_step
from swissarmybench.domain.table_cells import Origin, PlanCell, TableSpec
from swissarmybench.services.ports import BACKGROUND, SqlSession
from swissarmybench.services.workspace import Workspace

MAX_SCRIPT_CHARS: int = notebooks.MAX_CELL_CHARS * 5


class Origins:
    """Where each open table came from. Used from the event loop only."""

    def __init__(self) -> None:
        self._known: dict[str, Origin] = {}

    def note(self, name: str, origin: Origin) -> None:
        self._known[name] = origin

    def get(self, name: str) -> Origin:
        return self._known.get(name) or Origin()

    def rename(self, old: str, new: str) -> None:
        if old in self._known:
            self._known[new] = self._known.pop(old)

    def forget(self, name: str) -> None:
        self._known.pop(name, None)


class TableCells:
    def __init__(
        self,
        ws: Workspace,
        origins: Origins,
        view_bytes: Callable[[SqlSession, str], bytes] | None = None,
        planned_bytes: Callable[[SqlSession, str, Any], tuple[bytes, tuple[str, ...]]] | None = None,
    ) -> None:
        self.ws = ws
        # A query's result as an Arrow IPC stream (adapters/datasets.py's query_table and its stream).
        self._view_bytes = view_bytes
        # The adapter's plan over a relation, as an Arrow IPC stream, and what it folded (all of it: DuckDB).
        self._planned_bytes = planned_bytes
        self._origins = origins

    # ===== every open table as its cell's text =====

    def _table(self, cursor: SqlSession, info: DatasetInfo, grid: Grid | None) -> dict[str, Any]:
        ws = self.ws
        origin = self._origins.get(info.name)
        # A sort made by clicking a header is a way of looking, not a transformation: it stays out.
        steps = [s for s in (grid.steps if grid is not None else []) if not s.params.get("header")]
        on = [s for s in steps if s.enabled]
        problem: str | None = None
        query: str | None = None
        if grid is not None and on:
            compiled = ws.views.compile(cursor, info, steps, grid.settings)
            if compiled.error is not None:
                problem = f"Step {(compiled.error.index or 0) + 1}: {compiled.error.message}"
            else:
                query = view_query(info, compiled, steps, grid.settings, ws.grammar.keywords)
        if problem is not None:
            change: tuple[list[str], str] = (
                [],
                f"# {variable_name(info.name)}: a step in the grid cannot run ({problem}).\n"
                "# Fix it in the grid, and this cell follows.",
            )
        else:
            change = rules.transformations_code(info.name, info.source_kind, query)
        pasted: str | None = None
        if origin.kind == "paste" and info.row_count <= rules.PASTE_MAX_ROWS:
            names = ", ".join(quote(c.name) for c in info.columns)
            cursor.execute(f"SELECT {names} FROM {info.table}")  # noqa: S608 (quoted names of an open table)
            pasted = rules.pasted_query(info.columns, [list(row) for row in cursor.fetchall()])
        load = rules.load_code(info.name, origin, info.source_kind, pasted, info.row_count)
        return {
            "name": info.name,
            "variable": variable_name(info.name),
            "grid": grid.id if grid is not None else None,
            "source_kind": info.source_kind,
            "origin": origin.kind,
            "source": origin.label(),  # the file's or connection's name, for the Data panel
            # The connection it was read from (its colour on the Data panel; None: not a connection's).
            "connection": (
                connection_named(origin.connection)
                if origin.kind == "connection" and origin.connection
                else None
            ),
            "rows": info.row_count,
            "kernel": origin.kernel,  # the Workbench kernel that sent it (None: no kernel did)
            "steps": len(on),
            "step_list": [s.to_json() for s in steps],
            # Each transformation in plain words (the Scripts and Notebooks pages' cards).
            "step_words": [describe_step(s) for s in on],
            "problem": problem,
            "query": query,  # the steps as one DuckDB query (None: no steps): the project's outline
            "code": rules.cell_text([change]),
            "loaded": rules.cell_text([load, change]),
        }

    async def group_cells(self, names: list[str] | None = None) -> tuple[list[notebooks.Cell], int]:
        """The open tables (or the ones named) as a new notebook's Tables group: each table's
        read-only cell, with its load. The cells, and the number the next new cell gets. This is how
        a project's data.ipynb starts."""
        listed = (await self.listing(names))["tables"]
        specs = [
            TableSpec(t["name"], t["code"], t["loaded"], t["steps"], tuple(t["step_list"])) for t in listed
        ]
        arrangement = rules.arrange([], specs, 1, True)
        steps = {spec.name: list(spec.step_list) for spec in specs}
        cells = [
            notebooks.Cell(
                c.kind,
                c.source if c.uses is None else f"{c.uses}\n{rules.split_uses(c.source)[1]}",
                number=c.number,
                role=c.role,
                table=c.table,
                grouped=c.grouped,
                steps=steps.get(c.table or "") if c.role == "transformations" else None,
            )
            for c in arrangement.cells
        ]
        return cells, arrangement.next_number

    async def listing(self, names: list[str] | None = None) -> dict[str, Any]:
        """Every open table (or the ones named) as its cell's text. Open means it has a tab in the grid:
        a table whose last tab was closed (its data is kept for a while) has no steps to follow."""
        ws = self.ws
        wanted = [i for i in ws.store.all() if names is None or i.name in names]
        pairs = [(info, grid) for info in wanted if (grid := ws.grids.first_for(info.name)) is not None]

        def read() -> list[dict[str, Any]]:
            cursor = ws.store.cursor()
            return [self._table(cursor, info, grid) for info, grid in pairs]

        return {"tables": await ws.workers.run(BACKGROUND, read) if pairs else []}

    def _open(self, name: str) -> tuple[DatasetInfo, Grid | None]:
        """The table `name` (any case, as DuckDB reads a name) and the grid that shows it. A table is shared
        at once (the owner, 2026-11-21: every table in the Environment is read by name): one no grid
        shows yet is read as it is (None: no steps to apply), never opened as a grid first."""
        ws = self.ws
        infos = list(ws.store.all())
        info = next((i for i in infos if i.name == name), None) or next(
            (i for i in infos if i.name.lower() == name.lower()), None
        )
        if info is None:
            raise LookupError(f"No table named {name} is in the Environment.")
        return info, ws.grids.first_for(info.name)

    async def _read(self, info: DatasetInfo, grid: Grid | None, fn: Callable[[SqlSession, str], Any]) -> Any:
        """`fn(cursor, rows)` over a table as its grid shows it (its steps applied), or as it is when no
        grid shows it."""
        ws = self.ws
        steps, settings = (grid.steps, grid.settings) if grid is not None else ([], ViewSettings())

        def read(cursor: SqlSession) -> Any:
            with ws.views.reading(cursor, info, steps, settings, ordered=True) as rows:
                return fn(cursor, rows)

        if grid is not None:
            return await ws.grid_query(grid, None, BACKGROUND, read)
        return await ws.workers.run(BACKGROUND, lambda: read(ws.views.adapted(ws.store.cursor())))

    # ===== the open tables as a source of the adapter (Plans/adapter.plan.md, Order 3) =====

    async def adapter_tables(self) -> dict[str, Any]:
        """The Environment's tables as the adapter lists a source's: each one's name and its grid view's
        columns (its steps applied) with their DuckDB types; a table no grid shows yet, its own columns."""
        ws = self.ws
        pairs = [(i, ws.grids.first_for(i.name)) for i in ws.store.all()]

        def listed() -> list[dict[str, Any]]:
            cursor = ws.store.cursor()
            out = []
            for info, grid in pairs:
                if grid is None:
                    columns = [{"name": c.name, "type": c.type} for c in info.columns]
                else:
                    compiled = ws.views.compile(cursor, info, grid.steps, grid.settings)
                    columns = [{"name": c.name, "type": c.type} for c in compiled.columns_at(None)]
                out.append({"name": info.name, "columns": columns})
            return out

        return {"tables": await ws.workers.run(BACKGROUND, listed) if pairs else []}

    async def adapter_read(self, name: str, plan: Any) -> tuple[bytes, tuple[str, ...]]:
        """An open table read with the adapter's plan (its JSON) over its grid's view, its steps applied: the
        answer as an Arrow IPC stream, and the parts folded (DuckDB folds them all); nothing kept."""
        info, grid = self._open(name)
        if self._planned_bytes is None:
            raise LookupError(f"No table named {name} is in the Environment.")
        planned = self._planned_bytes
        ws = self.ws
        found: tuple[bytes, tuple[str, ...]] = await self._read(
            info, grid, lambda cursor, rows: planned(cursor, rows, plan)
        )
        ws.audit.write("app", "table_read_by_adapter", info.name, rows=None)
        return found

    async def view(self, name: str) -> bytes:
        """The open table `name` (any case, as DuckDB reads a name) as its grid shows it, every row, its
        steps applied, as an Arrow IPC stream. LookupError: no table of that name is open in Grids."""
        ws = self.ws
        info, grid = self._open(name)
        if self._view_bytes is None:
            raise LookupError(f"No table named {name} is in the Environment.")
        found: bytes = await self._read(info, grid, self._view_bytes)
        ws.audit.write("app", "table_read_by_sql", info.name, rows=None)
        return found

    # ===== a document's Tables group =====

    async def arrange(self, body: Any) -> dict[str, Any]:
        """A notebook's cells or a script's text with its Tables group as it should be.

        {"kind": "notebook", "cells": [...], "tables": [names], "next_cell": n, "move": true}
        {"kind": "script", "text": "...", "tables": [names], "move": true}

        `tables` are the open tables that belong to the document. `move` false: nothing is added or
        moved (the user is typing); the tables' cells follow the grid and the uses lines are worked out.
        """
        if not isinstance(body, dict) or body.get("kind") not in ("notebook", "script"):
            raise ValueError(
                'Send {"kind": "notebook", "cells": [...]} or {"kind": "script", "text": "..."}.'
            )
        names = body.get("tables") or []
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names) or len(names) > 500:
            raise ValueError("tables is a list of table names.")
        move = body.get("move") is not False
        listed = (await self.listing(names))["tables"] if names else []
        by_name = {t["name"]: t for t in listed}
        specs = [
            TableSpec(t["name"], t["code"], t["loaded"], t["steps"], tuple(t["step_list"]))
            for t in (by_name[n] for n in names if n in by_name)
        ]
        if body["kind"] == "script":
            text = body.get("text")
            if not isinstance(text, str) or len(text) > MAX_SCRIPT_CHARS:
                raise ValueError("Send the script's text (at most five million characters).")
            new_text, arrangement = rules.arrange_script(text, specs, move)
            return {
                "text": new_text,
                "tables": [line.to_json() for line in arrangement.tables],
                "outline": rules.outline(new_text),
            }
        cells = notebooks.read_cells(body.get("cells"))
        following = body.get("next_cell")
        plan = [PlanCell(c.number, c.kind, c.source, c.role, c.table, c.grouped) for c in cells]
        arrangement = rules.arrange(
            plan, specs, following if isinstance(following, int) and following > 0 else 1, move
        )
        steps = {spec.name: list(spec.step_list) for spec in specs}
        return {
            "cells": [
                c.to_json()
                | ({"steps": steps[c.table]} if c.role == "transformations" and c.table in steps else {})
                for c in arrangement.cells
            ],
            "tables": [line.to_json() for line in arrangement.tables],
            "next_cell": arrangement.next_number,
        }
