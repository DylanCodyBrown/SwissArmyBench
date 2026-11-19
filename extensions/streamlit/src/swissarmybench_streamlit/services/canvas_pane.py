"""The canvas's property pane (the owner, 2026-11-19: "a property pane for everything on the app canvas, and
ways to see all things related to the canvas"), for the Workbench window and the agent alike (rules in
domain/widget_code.py and domain/toolbox.py).

  inspect   whatever is selected: a block, a page, or the app. A block's properties (its place, its cell, each
            Streamlit element its cell calls with its arguments as they are written), what it USES (tables,
            variables, connections, the cells that make the names it reads), what it is USED BY, a line of its
            lineage, its STATE (each widget's key, and its value now while the page plays), its CACHE (each
            function st.cache_data or st.cache_resource decorates, in its cell and the cells it calls), and
            the exact code the page runs for it
  table     a table a block uses, to open beside the canvas: its columns and types, its grid's steps in words,
            its first rows
  code      a change to a cell's code (a default, a property, a binding, a handler, a cache), as a PLAN: the
            cell's code before and after, and only the characters that differ. The window that holds the
            document makes the change there, like typing (the editor's Undo takes it back). Nothing is written
            by the server; code that is not a plain value is refused
  new_cell  a Toolbox element's cell, its names free of every name the linked cells make

"Now" (the running app's session state and caches) is services/streamlit.py's `now`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from swissarmybench.domain import connection_usage
from swissarmybench.domain.steps import describe_step
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import streamlit_cells as rules
from swissarmybench_streamlit.domain import toolbox
from swissarmybench_streamlit.domain import widget_code as wc
from swissarmybench_streamlit.domain.streamlit_cells import Block, Key, Page, StreamlitError
from swissarmybench_streamlit.services.streamlit import App, Linked, StreamlitApps, _name, _where

HEAD_ROWS: int = 20
MAX_CELL_TEXT: int = 200
ACTIONS: tuple[str, ...] = ("set", "reset", "bind", "handler", "cache")


def _shown(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= MAX_CELL_TEXT else text[: MAX_CELL_TEXT - 1] + "…"


class CanvasPane:
    def __init__(
        self,
        apps: StreamlitApps,
        variables: Callable[[], dict[str, Any]] | None = None,
        lineage: Callable[[Any], Awaitable[dict[str, Any]]] | None = None,
        is_set: Callable[[str], bool] = lambda name: False,
    ) -> None:
        self._is_set = is_set  # whether this server's environment holds a variable (never its value)
        self._apps = apps
        self._variables = variables  # the Variables page's listing: names, sources, values as it shows them
        self._lineage = lineage

    # ===== the Toolbox =====

    def toolbox(self) -> dict[str, Any]:
        return toolbox.catalog()

    def new_cell(self, app_id: str, body: Any) -> dict[str, Any]:
        """A Toolbox element's cell for this app: {"element": "slider", "title"?}. Its variable and key are
        one name no linked cell makes; a data element shows the first open table."""
        app, _, _, found, _ = self._apps.canvas_parts(app_id)
        if not isinstance(body, dict) or not isinstance(body.get("element"), str):
            raise StreamlitError('Send {"element": "slider"} (the Toolbox lists them).')
        taken = [name for mine in found.values() for name in mine.makes] + self._apps.data_names(app)
        title = body.get("title") if isinstance(body.get("title"), str) else None
        try:
            made = toolbox.cell_code(body["element"], taken, list(self._apps._tables()), title)
        except toolbox.ToolboxError as error:
            raise StreamlitError(str(error)) from None
        return made.to_json() | {"element": body["element"]}

    # ===== inspect =====

    def _find(self, app: App, page_id: str | None, block_id: str | None) -> tuple[Page | None, Block | None]:
        if block_id and not page_id:
            page = next((p for p in app.pages if any(b.id == block_id for b in p.blocks)), None)
            if page is None:
                raise NotFound(f"This app has no block {block_id}.")
        elif page_id:
            page = next((p for p in app.pages if p.id == page_id), None)
            if page is None:
                raise NotFound(f"This app has no page {page_id}.")
        else:
            return None, None
        if not block_id:
            return page, None
        block = next((b for b in page.blocks if b.id == block_id), None)
        if block is None:
            raise NotFound(f"The page {page.name} has no block {block_id}.")
        return page, block

    def _variable_rows(self, names: tuple[str, ...]) -> list[dict[str, Any]]:
        listed: dict[str, dict[str, Any]] = {}
        if self._variables is not None and names:
            try:
                found = self._variables().get("variables") or []
                listed = {str(v.get("name")): v for v in found if isinstance(v, dict)}
            except Exception:  # the Variables page's own trouble is not the pane's: the names still show
                listed = {}
        rows = []
        for name in names:
            known = listed.get(name)
            row: dict[str, Any] = {"name": name, "defined": known is not None, "set": self._is_set(name)}
            if known is not None:
                # As the Variables page shows it: a secret's value is never in an answer.
                row |= {
                    k: known[k] for k in ("source", "source_words", "value", "secret", "shown") if k in known
                }
            rows.append(row)
        return rows

    def _uses(
        self,
        app: App,
        page: Page,
        block: Block,
        code: str,
        read: wc.CellCode,
        found: dict[Key, Any],
        linked: Linked,
    ) -> dict[str, Any]:
        tables = self._apps._tables()
        named = rules.tables_named(code, tables)
        mine = found.get(block.key) or rules.facts(code)
        on_page = {b.key: b.id for b in page.blocks}
        data = set(self._apps.data_names(app))
        cells: list[dict[str, Any]] = []
        for name in mine.reads:
            if name in rules.PROVIDED or name in named:
                continue
            makers = [key for key, facts in found.items() if key != block.key and name in facts.makes]
            makers.sort(key=lambda key: key not in on_page)
            if makers:
                document, cell = makers[0]
                title = rules.cell_title(linked.code(makers[0]) or "", cell, linked.name(makers[0]))
                cells.append(
                    {
                        "name": name,
                        "document": document,
                        "cell": cell,
                        "where": _where(document, cell),
                        "title": title,
                        "block": on_page.get(makers[0]),
                    }
                )
            elif name in data:
                cells.append(
                    {"name": name, "document": None, "cell": None, "where": "data.ipynb", "block": None}
                )
        used_by: list[dict[str, Any]] = []
        makes = set(rules.shown_makes(mine))
        for other_page in app.pages:
            for other in other_page.blocks:
                theirs = found.get(other.key)
                if other is block or theirs is None or other.key == block.key:
                    continue
                shared = [name for name in theirs.reads if name in makes]
                if shared:
                    title = rules.cell_title(linked.code(other.key) or "", other.cell, linked.name(other.key))
                    used_by.append(
                        {
                            "names": shared,
                            "block": other.id,
                            "page": other_page.id,
                            "page_name": other_page.name,
                            "title": title,
                            "where": _where(other.document, other.cell),
                        }
                    )
        return {
            "tables": [
                {
                    "name": name,
                    "dataset": tables[name][0].name,
                    "grid": tables[name][1].id,
                    "rows": tables[name][0].row_count,
                    "columns": len(tables[name][0].columns),
                    "steps": len(
                        [s for s in tables[name][1].steps if s.enabled and not s.params.get("header")]
                    ),
                }
                for name in named
            ],
            "variables": self._variable_rows(read.variables),
            "connections": connection_usage.cell_connections("code", code, None),
            "cells": cells,
            "used_by": used_by,
        }

    def _caches(
        self, block: Block, read: wc.CellCode, found: dict[Key, Any], linked: Linked
    ) -> list[dict[str, Any]]:
        rows = [
            f.to_json() | {"document": block.document, "cell": block.cell, "where": "this cell", "own": True}
            for f in read.functions
        ]
        own = {f.name for f in read.functions}
        for name in read.calls:
            if name in own:
                continue
            maker = next(
                (key for key, facts in found.items() if key != block.key and name in facts.makes), None
            )
            code = linked.code(maker) if maker else None
            if maker is None or code is None or linked.kind(maker) != "code":
                continue
            for f in wc.read(code).functions:
                if f.name == name:
                    rows.append(
                        f.to_json()
                        | {"document": maker[0], "cell": maker[1], "where": _where(*maker), "own": False}
                    )
        return rows

    @staticmethod
    def _path(graph: dict[str, Any]) -> list[dict[str, Any]]:
        """A lineage's graph as one line: the sources first, then each cell on the way, then this block."""
        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        feeds: dict[str, list[str]] = {}
        for edge in graph.get("edges", []):
            feeds.setdefault(edge["target"], []).append(edge["source"])
        depth: dict[str, int] = {}
        waiting: list[tuple[str, int]] = [(str(graph.get("target")), 0)]
        while waiting:
            node_id, far = waiting.pop()
            if node_id not in nodes or depth.get(node_id, -1) >= far or far > 50:
                continue
            depth[node_id] = far
            waiting += [(source, far + 1) for source in feeds.get(node_id, [])]
        ordered = sorted(depth, key=lambda node_id: -depth[node_id])
        return [
            {k: nodes[i].get(k) for k in ("kind", "label", "where", "document", "cell", "target")}
            for i in ordered
            if nodes[i].get("kind") != "step"
        ][:12]

    async def inspect(
        self, app_id: str, page_id: str | None = None, block_id: str | None = None
    ) -> dict[str, Any]:
        """A block, a page (no block) or the app (neither), in the shape the pane draws."""
        app, linked, pieces, found, _ = self._apps.canvas_parts(app_id)
        page, block = self._find(app, page_id, block_id)
        running = app.running()
        said: dict[str, Any] = {"app": app.id, "running": running, "title": app.title}
        if page is None:
            return said | {
                "target": "app",
                "settings": app.settings.to_json(),
                "document": app.document,
                "pages": [{"id": p.id, "name": p.name, "blocks": len(p.blocks)} for p in app.pages],
                "documents": list(dict.fromkeys(b.document for p in app.pages for b in p.blocks)),
            }
        if block is None:
            tables = self._apps._tables()
            used: list[str] = []
            for b in page.blocks:
                code = linked.code(b.key)
                used += [t for t in (rules.tables_named(code, tables) if code else []) if t not in used]
            return said | {
                "target": "page",
                "page": {"id": page.id, "name": page.name, "index": app.pages.index(page)},
                "blocks": [
                    {
                        "id": b.id,
                        "name": pieces[b.key].name if b.key in pieces else None,
                        "where": _where(*b.key),
                    }
                    for b in page.blocks
                ],
                "tables": used,
            }
        code = linked.code(block.key)
        kind = linked.kind(block.key) if code is not None else None
        answer = said | {
            "target": "block",
            "page": {"id": page.id, "name": page.name},
            "block": block.to_json()
            | {
                "name": pieces[block.key].name if block.key in pieces else None,
                "named": bool(linked.name(block.key)),
                "kind": kind,
                "where": _where(block.document, block.cell),
                "file": _name(block.document),
                "missing": self._apps._gone(block, linked),
            },
        }
        if code is None:
            return answer
        read = wc.read(code) if kind == "code" else wc.CellCode()
        rows = {r["key"]: r for r in self._apps.session(app_id)["state"]} if running else {}
        widgets = []
        for widget in read.widgets:
            shown = widget.to_json(block.id)
            element = toolbox.ELEMENTS[widget.call]
            key = shown["state_key"]
            shown |= {
                "title": element.label,
                "params": [p.to_json() for p in element.params],
                "held": key in rows if key else False,
                "now": rows[key]["value"] if key and key in rows else None,
            }
            widgets.append(shown)
        lineage: list[dict[str, Any]] = []
        if self._lineage is not None:
            try:
                graph = await self._lineage(
                    {"app": app.id, "page": page.id, "block": block.id, "values": False}
                )
                lineage = self._path(graph)
            except Exception:  # the overlay says what is wrong with a lineage; the pane just has no line
                lineage = []
        mine = found.get(block.key) or rules.facts(code)
        return answer | {
            "problem": read.problem,
            "editable": kind == "code" and read.problem is None,
            "makes": rules.shown_makes(mine),
            "widgets": widgets,
            "uses": self._uses(app, page, block, code, read, found, linked) | {"lineage": lineage},
            "cache": self._caches(block, read, found, linked),
            # The exact code the page runs for it: its cell, each widget keyed, inside its own slot.
            "code": f"with _slot_{block.id}:\n"
            + rules.indented(rules.keyed(rules.body(code).rstrip("\n"), block.id) or "pass"),
        }

    # ===== a table a block uses, beside the canvas =====

    async def table(self, name: str) -> dict[str, Any]:
        tables = self._apps._tables()
        if name not in tables:
            raise NotFound(f"No open table is called {name}: open it in the grid first.")
        info, grid = tables[name]
        steps = [s for s in grid.steps if s.enabled and not s.params.get("header")]
        ws = self._apps.ws

        def read() -> Any:
            return ws.views.window(ws.store.cursor(), info, steps, grid.settings, 0, HEAD_ROWS, len(steps))

        try:
            window = await ws.workers.run(BACKGROUND, read)
        except ws.engine_error as error:
            raise Conflict(f"{name} could not be read from the grid: {error}") from None
        return {
            "name": name,
            "dataset": info.name,
            "grid": grid.id,
            "rows": window.row_count,
            "columns": [{"name": c.name, "type": c.type} for c in window.columns],
            "steps": [describe_step(s) for s in steps],
            "head": [[_shown(v) for v in row] for row in window.rows],
        }

    # ===== a change to a cell's code, as a plan =====

    async def code(
        self, app_id: str, page_id: str, block_id: str, body: Any, who: str = "user"
    ) -> dict[str, Any]:
        """{"do": "set", "widget": 0, "name": "value", "value": 5} · {"do": "reset", "widget", "name"} ·
        {"do": "bind", "widget", "name", "kind": name|state|variable|expression, "target"} ·
        {"do": "handler", "widget", "event"?, "handler"?} · {"do": "cache", "function", "kind": data|resource|
        null, "settings"?: {"ttl", ...}, "document"?, "cell"?: a function of a cell this one calls}.
        The answer is the plan (the cell's code before and after, the characters that differ). With
        "apply": true the window that holds the app is told to make it in the open document."""
        app, linked, _, _, _ = self._apps.canvas_parts(app_id)
        page, block = self._find(app, page_id, block_id)
        if not isinstance(body, dict) or body.get("do") not in ACTIONS:
            raise StreamlitError(f'Send {{"do": one of {", ".join(ACTIONS)}, ...}}.')
        if block is None or page is None:
            raise StreamlitError("Name the block whose cell changes.")
        key: Key = block.key
        if body["do"] == "cache" and body.get("cell") is not None:
            key = rules.check_link(body.get("document") or block.document, body.get("cell"))
        before = linked.code(key)
        if before is None:
            raise NotFound(
                self._apps._gone(block, linked) or f"{_where(*key)} is not a cell of a linked file."
            )
        if linked.kind(key) != "code":
            raise Conflict(
                "A Markdown or HTML cell has no Streamlit code to change: change its text in its cell."
            )
        do, widget, name = body["do"], body.get("widget", 0), str(body.get("name"))
        if name == "default":  # the widget's own default: value, index or default
            found = [w for w in wc.read(before).widgets if w.index == widget]
            if not found or not found[0].default:
                raise StreamlitError("That element has no default value to set.")
            name = found[0].default
        try:
            if do == "set":
                change = wc.set_argument(before, widget, name, body.get("value"))
            elif do == "reset":
                change = wc.reset_argument(before, widget, name)
            elif do == "bind":
                change = wc.bind(before, widget, name, str(body.get("kind")), body.get("target"))
            elif do == "handler":
                handler = body.get("handler") if isinstance(body.get("handler"), str) else None
                event = body.get("event") if isinstance(body.get("event"), str) else None
                change = wc.add_handler(before, widget, event, handler)
            else:
                change = wc.set_cache(
                    before, str(body.get("function")), body.get("kind"), body.get("settings")
                )
        except wc.NotPlain as error:
            raise Conflict(str(error)) from None
        except wc.CodeError as error:
            raise StreamlitError(str(error)) from None
        plan = {
            "app": app.id,
            "document": key[0],
            "cell": key[1],
            "where": _where(*key),
            "do": do,
            "before": before,
            "changed": bool(change.edits),
        } | change.to_json()
        if body.get("apply") is True and change.edits:
            if app.window is None:
                raise Refused(
                    "This app is open without a Workbench window: open it there (workbench_open) and "
                    "its cell's code is changed in its document, like typing."
                )
            await self._apps.ws.live.broadcast({"type": "streamlit_code", "window": app.window, "plan": plan})
            plan["applied"] = "window"
        self._apps.ws.audit.write(
            who,
            "streamlit_code",
            f"{app.title}: {do} in {plan['where']}",
            app=app.id,
            title=app.title,
            detail=f"{do} in {plan['where']}",
            path=key[0],
        )
        return plan
