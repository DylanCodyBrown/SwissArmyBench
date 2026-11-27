"""Lineage with values (docs/ideas.md, lineage with values and approved outputs, 2026-11-15; rules in
domain/lineage.py). For the Workbench window and the agent alike.

From a canvas block or any cell of a notebook or script, back through every cell to the data, and each
step's value beside it:

  the graph   the documents as they are now: the one asked about as its window holds it (unsaved
              too), the open documents as their windows told the Streamlit service, else their files;
              a canvas page's blocks; the project's data.ipynb; the open tables, their grid steps and
              where each came from
  the values  summarised, never whole (a table's shape and first rows): a block on a playing page
              from what the page noted when it last ran (a filter changed on the page runs it again);
              a cell from its document's kernel; a table and each of its grid steps from the grid.
              Each table's row change from the step before it. A kernel that is busy says so; ask
              again

Memory only; nothing is written. Values are the user's data: the agent's answer marks them so.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import lineage as rules
from swissarmybench.domain import notebooks, table_cells
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.datasets import DatasetInfo
from swissarmybench.domain.grids import Grid
from swissarmybench.domain.lineage import DocCell, Document, Graph, Key, TableFacts
from swissarmybench.domain.steps import describe_step
from swissarmybench.services.hooks import Hooks
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.table_cells import Origins
from swissarmybench.services.workspace import NotFound, Workspace

HEAD_ROWS: int = 5
HEAD_COLUMNS: int = 12
CELL_CHARS: int = 60
MAX_STEPS: int = 30  # a table's grid steps drawn one by one
SHORT_CHARS: int = 24


class ProjectFiles(Protocol):
    def folder_of(self, path: str) -> str: ...

    def read(self, folder: str, name: str) -> str | None: ...

    def path(self, folder: str, name: str) -> str: ...


# The kernel's summaries of some names (client/lineage_values.py); None while it is busy.
KernelValues = Callable[[str, list[str]], Awaitable[dict[str, Any] | None]]


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value if not isinstance(value, float) or value == value else None
    text = str(value)
    return text if len(text) <= CELL_CHARS else text[: CELL_CHARS - 1] + "…"


def _table_summary(names: list[str], rows: list[list[Any]], total: int) -> dict[str, Any]:
    shown = names[:HEAD_COLUMNS]
    head = [[_plain(v) for v in row[: len(shown)]] for row in rows[:HEAD_ROWS]]
    return {"kind": "table", "rows": total, "columns": len(names), "names": shown, "head": head}


def short_value(value: Mapping[str, Any]) -> str:
    """A node's value in a word or two, for its Mermaid label."""
    if value.get("error"):
        return "error"
    if value.get("busy"):
        return ""
    items = value.get("items") or []
    if not items:
        return ""
    first = items[0]
    kind = first.get("kind")
    if kind == "table":
        return f"{first['rows']:,} rows"
    if kind == "missing":
        return "not run yet"
    if kind in ("picture", "chart"):
        return "a chart"
    text = str(first.get("text", ""))
    return text if len(text) <= SHORT_CHARS else text[: SHORT_CHARS - 1] + "…"


def _cells_of(path: str, text: str) -> tuple[DocCell, ...]:
    """A notebook's or script's file as the cells a lineage walks."""
    if notebooks.kind_of(path) == "notebook":
        cells, _ = notebooks.read_document(text)
        return tuple(
            DocCell(c.number, c.kind, c.source, c.name, c.role, c.table, c.connection)
            for c in cells
            if c.number is not None
        )
    found: list[DocCell] = []
    for s in table_cells.parse_script(text).cells:
        if s.number is None or s.fixed:
            continue
        kind = "html" if s.html else "code"
        found.append(DocCell(s.number, kind, s.source, table_cells.marker_name(s.title), s.role, s.table))
    return tuple(found)


document_cells = _cells_of  # the project's outline reads a document's cells the same way


def _sent_cells(sent: Any) -> tuple[DocCell, ...]:
    """A notebook's cells as its window sends them: {number, kind, source, name?, role?, table?,
    connection?}."""
    cells = notebooks.read_cells(sent)
    return tuple(
        DocCell(c.number, c.kind, c.source, c.name, c.role, c.table, c.connection)
        for c in cells
        if c.number is not None
    )


class Lineage:
    def __init__(
        self,
        ws: Workspace,
        hooks: Hooks,
        origins: Origins,
        read_document: Callable[[str], tuple[str, str, float]],
        project_files: ProjectFiles,
        kernel_values: KernelValues,
        kernel_for: Callable[[str], str | None] = lambda path: None,
    ) -> None:
        self.ws = ws
        # The open documents as their windows hold them, a canvas, a playing page's notes: the extension
        # that makes apps hands them over (services/hooks.py); with none on, the files.
        self._hooks = hooks
        self._origins = origins
        self._read = read_document  # a file's text and full path (the Workbench's documents)
        self._project = project_files
        self._kernel_values = kernel_values
        self._kernel_for = kernel_for  # the Workbench's kernel started for a document

    # ===== the documents, as they are now =====

    def _held_cells(self, held: Any, from_file: tuple[DocCell, ...]) -> tuple[DocCell, ...]:
        """An open document's cells: its window's code over the file's cells (roles, table cells)."""
        if held.every is not None:  # a project's data.ipynb sends every cell
            return tuple(
                DocCell(c.number, c.kind, c.source, held.names.get(c.number), c.role, c.table)
                for c in held.every
                if c.number is not None
            )
        known = {c.number: c for c in from_file}
        out: list[DocCell] = []
        for c in from_file:
            code = held.codes.get(c.number)
            if code is not None and c.number not in held.kinds and c.kind == "code":
                c = DocCell(
                    c.number,
                    c.kind,
                    table_cells.split_uses(code)[1],
                    held.names.get(c.number) or c.name,
                    c.role,
                    c.table,
                )
            out.append(c)
        out += [
            DocCell(number, held.kinds.get(number, "code"), held.codes[number], held.names.get(number))
            for number in held.order
            if number not in known and number not in held.kinds
        ]
        return tuple(out)

    def _document(self, path: str, sent: Mapping[str, Any] | None = None) -> Document:
        """A document as it is now: as the request sends it, else as its open window holds it, else its
        file."""
        data = rules.file_name(path).lower() == rules.DATA_NAME
        if sent is not None and isinstance(sent.get("cells"), list):
            return Document(path, _sent_cells(sent["cells"]), data)
        if sent is not None and isinstance(sent.get("text"), str):
            return Document(
                path, _cells_of(path if path.lower().endswith(".py") else f"{path}.py", sent["text"]), data
            )
        try:
            text, full, _ = self._read(path)
            from_file = _cells_of(full, text)
        except FileNotFoundError:
            from_file = ()
        except (notebooks.NotebookError, ValueError, OSError) as error:
            raise rules.LineageError(f"{rules.file_name(path)} cannot be read ({error}).") from None
        held = self._hooks.held(path)
        if held is not None:
            return Document(path, self._held_cells(held, from_file), data)
        if not from_file:
            raise NotFound(f"{rules.file_name(path)} is not open and is not on this computer.")
        return Document(path, from_file, data)

    def _data_path(self, path: str | None) -> str | None:
        """The project's data.ipynb beside a document (None: it is not in a project)."""
        if not path:
            return None
        try:
            folder = self._project.folder_of(path)
            if self._project.read(folder, rules.DATA_NAME) is None:
                return None
            return self._project.path(folder, rules.DATA_NAME)
        except (OSError, ValueError):
            return None

    def _open_tables(self) -> dict[str, tuple[DatasetInfo, Grid]]:
        found: dict[str, tuple[DatasetInfo, Grid]] = {}
        for info in self.ws.store.all():
            grid = self.ws.grids.first_for(info.name)
            if grid is not None:
                found.setdefault(variable_name(info.name), (info, grid))
        return found

    @staticmethod
    def _steps(grid: Grid) -> list[Any]:
        """A grid's steps as a table's cell holds them: enabled, a header's sort left out."""
        return [s for s in grid.steps if s.enabled and not s.params.get("header")][:MAX_STEPS]

    def _table_facts(self, tables: Mapping[str, tuple[DatasetInfo, Grid]]) -> dict[str, TableFacts]:
        out: dict[str, TableFacts] = {}
        for variable, (info, grid) in tables.items():
            origin = self._origins.get(info.name)
            steps = tuple(describe_step(s) for s in self._steps(grid))
            out[variable] = TableFacts(info.name, variable, origin.kind, origin.label() or origin.kind, steps)
        return out

    # ===== the graph =====

    def _target(self, body: Mapping[str, Any]) -> tuple[Key, dict[str, Document]]:
        """What the lineage starts from: the cell and its document."""
        if isinstance(body.get("app"), str):  # an old app canvas's block (app notebooks went, 2026-11-21)
            raise NotFound("An app canvas's blocks went with app notebooks: a canvas holds widgets now.")
        path: Any = body.get("document")
        cell: Any = body.get("cell")
        if not isinstance(path, str) or not path or isinstance(cell, bool) or not isinstance(cell, int):
            raise rules.LineageError(
                'Send {"document": a notebook or script, "cell": its own number}, '
                'or {"app", "page", "block"}.'
            )
        return (path, cell), {path: self._document(path, body)}

    async def trace(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The lineage of a cell, with each node's value (unless "values": false).

        {"document", "cell", "cells"?|"text"?, "kernel"?, "errors"?: {number: "KeyError: 'x'"}}."""
        if not isinstance(body, dict):
            raise rules.LineageError('Send {"document", "cell"} or {"app", "page", "block"}.')
        target, docs = self._target(body)
        data = self._data_path(target[0])
        if data is not None and data not in docs:
            try:
                docs[data] = self._document(data)
            except (NotFound, rules.LineageError):
                data = None
        if data is not None:
            docs[data] = Document(data, docs[data].cells, True)
        tables = self._open_tables()
        graph = rules.trace(target, docs, self._table_facts(tables), data)
        self.ws.audit.write(who, "lineage", f"{rules.file_name(target[0])} @cell{target[1]}")
        if body.get("values") is False:
            return graph.to_json()
        kernels: dict[str, str] = {}
        for path in docs:
            held = self._hooks.held(path)
            if held is not None and held.kernel:
                kernels[path] = held.kernel
            elif (found := self._kernel_for(path)) is not None:
                kernels[path] = found
        if isinstance(body.get("kernel"), str) and body["kernel"]:
            kernels[target[0]] = body["kernel"]
        errors = self._errors(body.get("errors"), target[0])
        values, busy = await self._values(graph, kernels, tables, errors)
        short = {node_id: short_value(value) for node_id, value in values.items()}
        said = graph.to_json(short)
        mark = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()[:16]
        return said | {"values": values, "busy": busy, "mark": mark, "playing": False}

    @staticmethod
    def _errors(sent: Any, path: str) -> dict[Key, str]:
        if not isinstance(sent, dict):
            return {}
        out: dict[Key, str] = {}
        for number, text in list(sent.items())[:500]:
            if isinstance(text, str) and re.fullmatch(r"\d{1,9}", str(number)):
                out[(path, int(number))] = text[:400]
        return out

    # ===== the values =====

    async def _values(
        self,
        graph: Graph,
        kernels: Mapping[str, str],
        tables: Mapping[str, tuple[DatasetInfo, Grid]],
        errors: Mapping[Key, str],
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        values: dict[str, dict[str, Any]] = {}
        wanted: dict[str, set[str]] = {}  # kernel -> names
        asks: list[tuple[str, str, list[str]]] = []  # (node, kernel, names)
        for node in graph.nodes:
            if node.document is None or node.cell is None:
                continue
            key = (node.document, node.cell)
            names = list(node.makes) or ([node.table] if node.table else [])
            if key in errors:
                values[node.id] = {"items": [], "error": errors[key], "from": "kernel"}
                continue
            kernel = kernels.get(node.document)
            if kernel and names:
                wanted.setdefault(kernel, set()).update(names)
                asks.append((node.id, kernel, names))
        busy = False
        answers: dict[str, dict[str, Any] | None] = {}
        for kernel, asked in wanted.items():
            answers[kernel] = await self._kernel_values(kernel, sorted(asked))
        for node_id, kernel, names in asks:
            found = answers.get(kernel)
            if found is None:
                busy = True
                values[node_id] = {"items": [], "error": None, "from": "kernel", "busy": True}
                continue
            values[node_id] = {
                "items": [{"name": n} | found[n] for n in names if isinstance(found.get(n), dict)],
                "error": None,
                "from": "kernel",
            }
        grid = await self._grid_values(graph, tables)
        for node in graph.nodes:
            have = values.get(node.id)
            from_grid = grid.get(node.id)
            if from_grid is None:
                continue
            # A table's cell that has not run in a kernel shows what the grid holds.
            if have is None or not have["items"] or all(i.get("kind") == "missing" for i in have["items"]):
                values[node.id] = from_grid
        self._changes(graph, values)
        return values, busy

    async def _grid_values(
        self, graph: Graph, tables: Mapping[str, tuple[DatasetInfo, Grid]]
    ) -> dict[str, dict[str, Any]]:
        """Each table node, its grid steps and its source, from the grid: rows after each step."""
        wanted: dict[str, list[tuple[str, int, bool]]] = {}  # variable -> (node, steps applied, a step's)
        for node in graph.nodes:
            variable = node.table
            if node.kind == "source":
                variable = next(
                    (n.table for n in graph.nodes if n.table and self._fed_by(graph, node.id, n.id)), None
                )
            if variable is None or variable not in tables:
                continue
            steps = len(self._steps(tables[variable][1]))
            upto = node.step if node.kind == "step" else 0 if node.kind == "source" else steps
            wanted.setdefault(variable, []).append((node.id, upto or 0, node.kind == "step"))
        if not wanted:
            return {}

        def read() -> dict[str, dict[str, Any]]:
            out: dict[str, dict[str, Any]] = {}
            cursor = self.ws.store.cursor()
            for variable, asks in wanted.items():
                info, grid = tables[variable]
                steps = self._steps(grid)
                for node_id, upto, step in asks:
                    try:
                        window = self.ws.views.window(cursor, info, steps, grid.settings, 0, HEAD_ROWS, upto)
                    except Exception as error:
                        out[node_id] = {"items": [], "error": str(error)[:400], "from": "grid"}
                        continue
                    names = [c.name for c in window.columns]
                    summary = _table_summary(names, window.rows, window.row_count)
                    if step:  # a grid step: its row change from the step before it
                        summary["change"] = window.row_count - self.ws.views.row_count(
                            cursor, info, steps, grid.settings, upto - 1
                        )
                    out[node_id] = {"items": [{"name": variable} | summary], "error": None, "from": "grid"}
            return out

        return await self.ws.workers.run(BACKGROUND, read)

    @staticmethod
    def _fed_by(graph: Graph, source: str, target: str) -> bool:
        return any(e.source == source and e.target == target for e in graph.edges)

    @staticmethod
    def _changes(graph: Graph, values: dict[str, dict[str, Any]]) -> None:
        """Each table's row change from the table before it in the flow."""
        rows: dict[str, int] = {}
        into: dict[str, list[str]] = {}
        for edge in graph.edges:
            into.setdefault(edge.target, []).append(edge.source)
        for node in graph.nodes:  # in flow order: the ones before are done first
            value = values.get(node.id)
            first = (value or {}).get("items", [None])[0] if value and value.get("items") else None
            if not first or first.get("kind") != "table":
                continue
            before = next((rows[s] for s in into.get(node.id, []) if s in rows), None)
            if before is not None:
                first["change"] = first["rows"] - before
            rows[node.id] = int(first["rows"])
