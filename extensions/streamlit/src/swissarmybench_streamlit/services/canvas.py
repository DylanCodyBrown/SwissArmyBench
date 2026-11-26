"""The Canvas (the owner, 2026-11-21): `<app>.canvas.json` files of the project, edited by commands that never
lose work or leave a broken page.

  open / listing   a canvas file read and validated (domain/canvas_layouts.py read: its two layouts): a newer
                   format opens read-only; a file that does not read is reported with its line, a copy kept
                   beside it, and never written over; an instance whose widget is gone stays as a placeholder
                   (Replace or Remove); overrides of properties a widget's code no longer has are dropped and
  said once command          one rule-checked change (add_container, insert_widget, move, set_container,
                   set_values, replace_widget, delete, sizing, add_page, change_page, remove_page), kept for
                   Undo and Redo, the file written atomically only when its bytes change (every change is
                   saved: a crash or a closed window loses nothing)
  undo / redo      every change, back and forward
  versions         each change gives the canvas a new version; a command sent for an older one is refused
                   with the canvas as it is now (two windows never write over each other), and a file changed
                   on disk (a pull, another app) is read again before anything is written
  play / check     the canvas's pages built (domain/canvas_build.py, the one builder) and run live, or
                   headless with AppTest
  export           the fewest files (canvas_build.folded): app.py (the pages, the layout, the wiring and
                   the runtime), widgets.py (the widgets inlined), data.py when the project has one,
                   adapter.py and connections.py when a widget reads a connection's table, requirements.txt,
                   README.md; the open tables it names as data/*.parquet; the agent's waits for Allow
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.services.changes import raised
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import canvas_build as build_rules
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain.canvas_model import WidgetFacts
from swissarmybench_streamlit.domain.widget_contract import ContractError

HISTORY = 200


@dataclass
class Open:
    id: str
    path: str
    canvas: dict[str, Any]
    stamp: str | None
    version: int = 1
    back: list[dict[str, Any]] = field(default_factory=list)
    forward: list[dict[str, Any]] = field(default_factory=list)
    read_only: str | None = None
    broken: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    # Each Out[Table]'s columns as Play last ran them (the column pickers of a property wired from it).
    seen: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class CanvasProject:
    """The open project as the Canvas reads it (the root's port): its folder, its data.py's text, a folder's
    names, a path as it really is, and the base's scaffold's adapter.py and connections.py for an export."""

    folder: Callable[[], str | None] = lambda: None
    read_data_py: Callable[[str], str | None] = lambda folder: None
    list_folder: Callable[[str], list[str]] = lambda folder: []
    real_path: Callable[[str], str] = lambda path: path
    core_files: Callable[[list[str]], Awaitable[dict[str, Any]]] | None = None


def canvas_id(path: str) -> str:
    return "cv" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]


class Canvases:
    def __init__(
        self,
        ws: Any,
        files: Any,
        widgets: Any,
        live: Any,
        approvals: Approvals,
        app_files: Any,
        project: CanvasProject | None = None,
        builds: Any = None,
        now: Callable[[], float] = time.time,
        paired: Callable[[], list[dict[str, Any]]] = lambda: [],
    ) -> None:
        project = project or CanvasProject()
        self.ws = ws
        self._files = files  # adapters/widget_files.py CanvasFiles
        self._widgets = widgets  # services/widgets.py Widgets
        self._live = live  # server/live_runs.py LiveRuns
        self._approvals = approvals
        self._app_files = app_files  # adapters/streamlit_files.py AppFiles (the export's writer)
        self._project_folder = project.folder
        self._read_data_py = project.read_data_py
        self._list_folder = project.list_folder
        self._real = project.real_path
        # Each endpoint a wizard's pattern made, with the widget that pairs with it (the base's
        # local_api.paired; nothing without a local sandbox API): what a dropped widget wires itself to.
        self.paired = paired
        self._builds = builds  # adapters/build_files.py BuildFiles (Launch's builds/ in the project)
        # The base's project scaffold (services/scaffold.py export_core): adapter.py and connections.py for an
        # export whose widgets read a connection's table.
        self._core_files = project.core_files
        self._now = now
        self._open: dict[str, Open] = {}
        self.launches: Any = (
            None  # services/launch.py Launches (Launch, Builds, the analyzer), set by the root
        )
        widgets.renamed = self.rename_widget

    # ===== what the base asks of the canvases (its hooks) =====

    def api_uses(self) -> list[dict[str, Any]]:
        """Each canvas widget instance of the open project whose endpoint property names one of API.py's, and
        each Event wired to call one (the local sandbox API's Payload shapes: the base's hooks.api_uses)."""
        folder = self._project_folder()
        if folder is None:
            return []
        canvases = []
        for name, text in self._files.in_folder(folder):
            try:
                canvases.append((name, json.loads(text)))
            except ValueError:
                continue
        return wiring.api_uses(canvases)

    def code_placed(self, folder: str) -> list[tuple[str, str]]:
        """What a project folder's canvases need installed, as (why, code): Streamlit for each canvas, and the
        code of each widget it places (the base's hooks.project_code: what the project needs as it opens)."""
        out: list[tuple[str, str]] = []
        for name, text in self._files.in_folder(folder):
            try:
                canvas = json.loads(text)
            except ValueError:
                continue
            out.append((f"the canvas {name}", "import streamlit"))
            for widget in sorted(_placed(canvas)):
                code = self._widgets.code_of(widget)
                if code:
                    out.append((f"the canvas {name} (widget {widget})", code))
        return out

    async def put(self, body: dict[str, Any], who: str) -> dict[str, Any]:
        """Build's widget (the APIs page; the base's hooks.canvas_put): put on the named canvas's page (else
        the project's first canvas and its first page), its values set, its In wired."""
        listed = {c["name"]: c["path"] for c in self.listing()["canvases"]}
        wanted = str(body.get("canvas") or next(iter(listed), ""))
        if wanted not in listed:
            raise ValueError("The project has no canvas yet: New canvas on the Canvas page makes one.")
        name = (await self.open({"path": listed[wanted]}, who))["canvas"]
        insert = {"kind": "insert_widget", "widget": body["widget"]} | (
            {"page": body["page"]} if body.get("page") else {}
        )
        made = (await self.command(name, insert, who))["made"]
        if body.get("values"):
            await self.command(name, {"kind": "set_values", "id": made, "values": body["values"]}, who)
        if body.get("wire"):
            await self.wire(name, {"id": made, **body["wire"]}, who)
        return {"canvas": wanted, "canvas_id": name, "id": made}

    # ===== open =====

    def listing(self, folder: str | None = None) -> dict[str, Any]:
        folder = folder or self._project_folder()
        names = sorted(n for n in self._list_folder(folder) if n.endswith(model.SUFFIX)) if folder else []
        old = sorted(n for n in self._list_folder(folder) if n.endswith(model.OLD_SUFFIX)) if folder else []
        return {
            "folder": folder,
            "canvases": [{"name": n[: -len(model.SUFFIX)], "path": f"{folder}/{n}"} for n in names],
            "old": [{"name": n, "said": model.OLD_SAID} for n in old],
        }

    def _facts(self) -> dict[str, WidgetFacts]:
        facts: dict[str, WidgetFacts] = self._widgets.facts()
        return facts

    def _read(self, path: str) -> Open:
        made = self._open.get(canvas_id(path))
        text, stamp = self._files.read(path)
        try:
            found = model.read(text, self._facts())
        except model.CanvasError as error:
            copy = self._files.keep_copy(path)
            broken = {"error": str(error), "line": error.line, "copy": copy}
            empty = model.new_canvas("Broken canvas")
            opened = Open(
                canvas_id(path), path, empty, stamp, broken=broken, read_only=f"{error} (line {error.line})"
            )
            return opened if made is None else _keep(made, opened)
        canvas, said = found.canvas, list(found.notes)
        if found.read_only is None:
            canvas, dropped = model.prune(canvas, self._facts())
            if dropped:
                said += dropped
                stamp = self._files.write(path, model.write(canvas))
        opened = Open(canvas_id(path), path, canvas, stamp, read_only=found.read_only, notes=said)
        return opened if made is None else _keep(made, opened)

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        path = body.get("path")
        if not isinstance(path, str) or not path:
            folder = body.get("folder") or self._project_folder()
            name = str(body.get("name") or "App").strip() or "App"
            if not folder:
                raise ValueError("Open a project first, or send the canvas's path.")
            path = f"{folder}/{build_rules.slug(name)}{model.SUFFIX}"
            if not self._files.exists(path):
                self._files.write(path, model.write(model.new_canvas(name)))
                self.ws.audit.write(who, "new_canvas", path)
        path = self._real(path)
        if path.endswith(model.OLD_SUFFIX):
            raise ValueError(model.OLD_SAID)
        if not path.endswith(model.SUFFIX):
            raise ValueError(f"A canvas's file ends in {model.SUFFIX}.")
        if not self._files.exists(path):
            if not body.get("create"):
                raise NotFound(f"There is no canvas at {path}.")
            self._files.write(
                path, model.write(model.new_canvas(path.rsplit("/", 1)[-1][: -len(model.SUFFIX)]))
            )
        opened = self._read(path)
        self._open[opened.id] = opened
        return self.state(opened.id)

    def title_of(self, canvas: str) -> str:
        """An open canvas's name, as the user knows it (its file's, without .canvas.json)."""
        opened = self._open.get(canvas)
        if opened is None:
            return canvas
        return opened.path.replace("\\", "/").rsplit("/", 1)[-1][: -len(model.SUFFIX)] or canvas

    def _get(self, canvas: str) -> Open:
        found = self._open.get(canvas)
        if found is None:
            raise NotFound("That canvas is not open (the server restarted): open its file again.")
        return found

    def state(self, canvas: str) -> dict[str, Any]:
        opened = self._get(canvas)
        facts = self._facts()
        built = self._widgets.built()
        marks: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        context = self._widgets.context()
        for _page, node in model.walk(opened.canvas):
            if node["kind"] != "widget":
                continue
            if node["widget"] not in facts:
                missing.append(node["id"])
                continue
            props = {p.name: p for p in built[node["widget"]].properties}
            own = dataclasses.replace(context, values=dict(node["values"]))
            for key, value in node["values"].items():
                if key in props:
                    try:
                        props_rules.check(props[key], value, own)
                    except props_rules.PropertyError as error:
                        marks.setdefault(node["id"], {})[key] = f"{error} {error.fix}".strip()
        notes, opened.notes = opened.notes, []  # said once
        return {
            "canvas": opened.id,
            "path": opened.path,
            "name": opened.path.rsplit("/", 1)[-1][: -len(model.SUFFIX)],
            "version": opened.version,
            "model": opened.canvas,
            "read_only": opened.read_only,
            "broken": opened.broken,
            "missing": missing,
            "marks": marks,
            "notes": notes,
            "undo": len(opened.back),
            "redo": len(opened.forward),
            "pages": build_rules.page_files(opened.canvas),
            # Each page's items in pixels at each layout's design width (what the Canvas page draws).
            "views": model.views(opened.canvas) if not opened.read_only else {},
            "design": model.DESIGN,
            "wiring": self.wiring(opened.canvas, built, self._seen(opened)),
        }

    def _seen(self, opened: Open) -> dict[str, list[str]]:
        """The columns Play or Launch last saw for each Out[Table] (names only; kept after the run stops). A
        launched app records them as Play does (the owner approved, 2026-11-21); a shared run never does."""
        seen = getattr(self._live, "seen_columns", None)
        if seen is not None:
            for key in (f"canvas-{opened.id}", f"launch-{opened.id}"):  # services/launch.py PREFIX
                opened.seen |= seen(key)
        return opened.seen

    def wiring(
        self,
        canvas: dict[str, Any],
        built: dict[str, Any] | None = None,
        seen: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """The canvas's wiring: each instance's contract, sources, each Out's readers, the wires to draw and
        the broken ones (both ends), each Out[Table]'s columns."""
        built = built if built is not None else self._widgets.built()
        contracts = build_rules.contracts(built)
        context = self._widgets.context()
        found = wiring.analyse(
            canvas,
            contracts,
            context.endpoints,
            context.variables,
            set(context.tables) if context.tables is not None else None,
            seen,
        )
        every = found["outs"]
        found["ports"] = {
            node["id"]: {
                "page": page["id"],
                "widget": node["widget"],
                # Each In with what its picker offers (wiring.sources: the one rule, the page draws it).
                "ins": [
                    p.to_json() | {"sources": wiring.sources(p, node["id"], every)}
                    for p in contracts.get(node["widget"], [])
                    if p.direction == "in"
                ],
                "outs": [p.to_json() for p in contracts.get(node["widget"], []) if p.direction == "out"],
                "events": [p.to_json() for p in contracts.get(node["widget"], []) if p.direction == "event"],
            }
            for page, node in model.walk(canvas)
            if node["kind"] == "widget"
        }
        return found

    async def wire(self, canvas: str, body: Any, who: str = "user") -> dict[str, Any]:
        """An instance's In given a source, or its Event its actions (None: unwired): checked against its
        contract and its page (a type that does not fit is refused with the reason), kept for Undo,
        written."""
        body = dict(body) if isinstance(body, dict) else {}
        opened = self._get(canvas)
        self._writable(opened)
        await self._fresh(opened)
        sent = body.pop("version", None)
        if sent is not None and sent != opened.version:
            raise Conflict("The canvas changed in another window: it is shown as it is now. Do it again.")
        _page, _parent, node = model.find(opened.canvas, str(body.get("id")))
        built = self._widgets.built()
        ports = {p.name: p for p in build_rules.contracts(built).get(node.get("widget", ""), [])}
        name = str(body.get("port") or "")
        port = ports.get(name)
        if node["kind"] != "widget" or port is None or port.direction == "out":
            raise ValueError(f"{node.get('widget', node['id'])} has no In or Event {name[:40]}.")
        wire = body.get("wire")
        if wire is not None:
            context = self._widgets.context()
            # Any page's Outs (an app-wide value) and the app's own (app.viewer), never its own instance's.
            outs = wiring.every_out(opened.canvas, build_rules.contracts(built))
            check = wiring.Context(
                {k: v["type"] for k, v in outs.items() if v["instance"] != node["id"]},
                context.endpoints,
                context.variables,
                set(context.tables) if context.tables is not None else None,
            )
            try:
                if port.direction == "event":
                    wiring.check_event(port, wire, context.endpoints)
                else:
                    wiring.check_in(port, wire, check)
            except ContractError as error:
                raise ValueError(f"{error} {error.fix}".strip()) from None
        after = wiring.set_wire(opened.canvas, {"id": node["id"], "port": name, "wire": wire})
        if after != opened.canvas:
            opened.back.append(opened.canvas)
            del opened.back[:-HISTORY]
            opened.forward.clear()
            await self._keep(opened, after, str(body.get("window", "")))
            self.ws.audit.write(who, "canvas_wire", f"{opened.path} {node['id']}.{name}")
        return self.state(canvas)

    # ===== changes =====

    async def _fresh(self, opened: Open) -> None:
        """A file changed on disk since it was read (a pull, another app): read again, the change refused."""
        if self._files.stamp(opened.path) == opened.stamp:
            return
        again = self._read(opened.path)
        opened.canvas, opened.stamp, opened.read_only, opened.broken = (
            again.canvas,
            again.stamp,
            again.read_only,
            again.broken,
        )
        opened.version += 1
        await self._tell(opened, "")
        raise Conflict("The canvas's file changed on disk: it is shown as it is now. Do it again.")

    def _writable(self, opened: Open) -> None:
        if opened.broken:
            raise Refused(
                f"The canvas's file does not read ({opened.broken['error']}): fix it in the file; "
                f"a copy is kept at "
                f"{opened.broken['copy']}."
            )
        if opened.read_only:
            raise Refused(opened.read_only)

    async def command(self, canvas: str, body: Any, who: str = "user") -> dict[str, Any]:
        body = dict(body) if isinstance(body, dict) else {}
        if body.get("kind") == "wire":  # an In's source or an Event's actions (services' own check)
            return await self.wire(canvas, {k: v for k, v in body.items() if k != "kind"}, who)
        opened = self._get(canvas)
        self._writable(opened)
        await self._fresh(opened)
        sent = body.pop("version", None)
        if sent is not None and sent != opened.version:
            raise Conflict(
                "The canvas changed in another window: it is shown as it is now. Do it again.",
                details=f"version {sent}, now {opened.version}",
            )
        kind = str(body.pop("kind", ""))
        window = str(body.pop("window", ""))
        try:
            after, made = model.apply(opened.canvas, kind, body, self._facts())
        except model.CanvasError as error:
            raise ValueError(str(error)) from None
        if after == opened.canvas:
            return self.state(canvas) | {"made": made}
        wired = self._pair(after, made) if kind == "insert_widget" and made else None
        if wired is not None:  # near a matching endpoint: wired as part of the same change (one Undo)
            after = wired.pop("canvas")
            opened.notes.append(wired["words"])
        opened.back.append(opened.canvas)
        del opened.back[:-HISTORY]
        opened.forward.clear()
        before = opened.canvas
        await self._keep(opened, after, window)
        self.ws.audit.write(who, f"canvas_{kind}", f"{opened.path} {made or body.get('id') or ''}".strip())
        self._pages_changed(who, str(after.get("name") or canvas), before, after)
        return self.state(canvas) | {"made": made} | ({"wired": wired} if wired else {})

    def _pair(self, canvas: dict[str, Any], made: str) -> dict[str, Any] | None:
        """A widget just inserted, wired to the endpoint a wizard's pattern made for its kind (the pairing
        is the pattern's data: the base's local_api.paired), when one is near: its endpoint property set, or
        its In given the endpoint as its source. None: nothing pairs, or it is the user's to pick."""
        try:
            pairings = list(self.paired())
        except Exception:  # API.py's own trouble: nothing to pair
            return None
        if not pairings:
            return None
        _page, _parent, node = model.find(canvas, made)
        known = self._facts().get(node.get("widget", ""))
        if known is None:
            return None
        found = wiring.pair_for(canvas, made, pairings, list(known.properties), list(dict(known.ins)))
        if found is None:
            return None
        try:
            if found["as"] == "property":
                body = {"id": made, "values": {"endpoint": found["endpoint"]}}
                after = model.apply(canvas, "set_values", body, self._facts())[0]
            else:
                wire = {"endpoint": found["endpoint"]}
                after = wiring.set_wire(canvas, {"id": made, "port": found["port"], "wire": wire})
            if found.get("sets"):  # what the pairing also sets (a select's column of options: the label)
                body = {"id": made, "values": dict(found["sets"])}
                after = model.apply(after, "set_values", body, self._facts())[0]
        except (model.CanvasError, ValueError):
            return None
        return found | {"canvas": after}

    def _pages_changed(self, who: str, name: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        """The change log (the base's services/changes.py): each canvas page that changed, one event each
        (its containers and widget instances by id: their places and values fingerprinted, never kept)."""
        was, now = _pages(before), _pages(after)
        for page in sorted(set(was) | set(now)):
            change = raised("canvas", f"{name} / {page}", was.get(page), now.get(page))
            if change:
                self.ws.audit.write(who, "changed", name, **change)

    async def _keep(self, opened: Open, canvas: dict[str, Any], window: str) -> None:
        opened.canvas = canvas
        opened.stamp = self._files.write(opened.path, model.write(canvas))
        opened.version += 1
        await self._tell(opened, window)

    async def _tell(self, opened: Open, window: str) -> None:
        await self.ws.live.broadcast(
            {"type": "canvas_changed", "canvas": opened.id, "version": opened.version, "window": window}
        )

    async def undo(
        self, canvas: str, body: Any = None, who: str = "user", redo: bool = False
    ) -> dict[str, Any]:
        opened = self._get(canvas)
        self._writable(opened)
        await self._fresh(opened)
        source, target = (opened.forward, opened.back) if redo else (opened.back, opened.forward)
        if not source:
            return self.state(canvas)
        target.append(opened.canvas)
        window = str((body or {}).get("window", "")) if isinstance(body, dict) else ""
        await self._keep(opened, source.pop(), window)
        self.ws.audit.write(who, "canvas_redo" if redo else "canvas_undo", opened.path)
        return self.state(canvas)

    async def replace(
        self,
        canvas: str,
        after: dict[str, Any],
        who: str = "user",
        why: str = "canvas_replace",
        window: str = "",
    ) -> dict[str, Any]:
        """The whole canvas replaced by another as ONE change (a build's Restore): its rules checked first,
        kept for Undo, written atomically only when its bytes change."""
        opened = self._get(canvas)
        self._writable(opened)
        await self._fresh(opened)
        found = model.problems(after, self._facts())
        if found:
            raise Refused(f"It does not fit the canvas's rules: {found[0]}")
        if after != opened.canvas:
            opened.back.append(opened.canvas)
            del opened.back[:-HISTORY]
            opened.forward.clear()
            await self._keep(opened, after, window)
            self.ws.audit.write(who, why.split(" ", 1)[0], f"{opened.path} {why.partition(' ')[2]}".strip())
        return self.state(canvas)

    async def rename_widget(self, old: str, new: str) -> int:
        """A widget renamed: every instance of it, in the open canvases and the project's canvas files."""
        count = 0
        paths = {o.path for o in self._open.values()}
        folder = self._project_folder()
        if folder:
            paths |= {c["path"] for c in self.listing(folder)["canvases"]}
        for path in sorted(paths):
            opened = self._open.get(canvas_id(path))
            if opened is not None and (opened.broken or opened.read_only):
                continue
            try:
                canvas = opened.canvas if opened else model.read(self._files.read(path)[0]).canvas
            except (OSError, model.CanvasError):
                continue
            after, changed = model.rename_widget(canvas, old, new)
            if not changed:
                continue
            count += changed
            if opened is not None:
                opened.back.append(opened.canvas)
                await self._keep(opened, after, "")
            else:
                self._files.write(path, model.write(after))
        return count

    # ===== play, check, export =====

    def _app(self, opened: Open, first: str | None = None) -> tuple[dict[str, str], set[str]]:
        built = self._widgets.built()
        context = self._widgets.context()
        used = {n: built[n] for n in build_rules.used(opened.canvas) if n in built}
        carried = self._widgets.carried(opened.canvas, used)
        files = build_rules.build(opened.canvas, built, context, first, carried)
        folder = opened.path.rsplit("/", 1)[0]
        data = self._read_data_py(folder)
        if data is not None:
            files["data.py"] = data
        # What the Excel widgets' adapter.py and sab_excel.py (carried where the code imports them) need.
        excel = ("openpyxl", "duckdb") if {"adapter.py", "sab_excel.py"} & set(carried) else ()
        files["requirements.txt"] = "\n".join([*build_rules.REQUIREMENTS, *excel]) + "\n"
        return files, self._widgets.named_tables(opened.canvas, built, context)

    async def play(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        opened = self._get(canvas)
        page = (body or {}).get("page") if isinstance(body, dict) else None
        page_id = page if isinstance(page, str) and page else opened.canvas["pages"][0]["id"]
        model.page_of(opened.canvas, page_id)
        files, names = self._app(opened, page_id)
        tables = await self._widgets.tables_for(names)
        broken = self.wiring(opened.canvas)["broken"]
        started = time.monotonic()
        # The played page is the app's default (built so): its address is the app's own, never a page's
        # path (a path Streamlit has not yet heard of says "Page not found" before the first run).
        answer: dict[str, Any] = await self._live.run(
            f"canvas-{opened.id}", files, tables, self._widgets.python(body), names=names
        )
        self.ws.audit.write(who, "canvas_play", opened.path)
        return answer | {
            "canvas": opened.id,
            "page": page_id,
            "seconds": round(time.monotonic() - started, 2),
            "broken": broken,
        }

    async def full_screen(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """The Canvas page holding this canvas full screen or back (the owner, 2026-11-26): on true or false,
        none the other way. The page's own state, told (`canvas_full_screen`); nothing is written."""
        opened = self._get(canvas)
        on = (body or {}).get("on") if isinstance(body, dict) else None
        if on is not None and not isinstance(on, bool):
            raise ValueError("on is true or false (none: the other way).")
        await self.ws.live.broadcast({"type": "canvas_full_screen", "canvas": opened.id, "on": on})
        self.ws.audit.write(who, "canvas_full_screen", opened.path)
        return {"canvas": opened.id, "on": on, "told": True}

    async def stop(self, canvas: str, body: Any = None) -> dict[str, Any]:
        """Play stopped (run "play", the default), or the launched app (run "launch")."""
        run = (body or {}).get("run") if isinstance(body, dict) else None
        if run not in (None, "play", "launch"):
            raise Refused("run is play or launch.")
        opened = self._get(canvas)
        if run == "launch" and self.launches is not None:
            return {"ok": (await self.launches.stop(opened.id))["ok"]}
        prefix = "launch" if run == "launch" else "canvas"
        return {"ok": await self._live.stop(f"{prefix}-{opened.id}")}

    async def check(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        opened = self._get(canvas)
        files, names = self._app(opened)
        tables = await self._widgets.tables_for(names)
        pages = [f"{build_rules.PAGES}/{slug}.py" for slug in build_rules.page_files(opened.canvas).values()]
        answer: dict[str, Any] = await self._live.check(
            f"check-{opened.id}", files, tables, self._widgets.python(body), pages
        )
        self.ws.audit.write(who, "canvas_check", opened.path)
        return answer | {"canvas": opened.id}

    def build_files(self, canvas: str) -> dict[str, str]:
        """The app's files as Play, Launch and Export write them (the one builder)."""
        return self._app(self._get(canvas))[0]

    async def export(self, canvas: str, body: Any, who: str = "user") -> dict[str, Any]:
        opened = self._get(canvas)
        folder = (body or {}).get("folder") if isinstance(body, dict) else None
        if not isinstance(folder, str) or not folder:
            raise ValueError('Send the folder to export into: {"folder": "..."}.')
        chosen = self._app_files.export_target(folder)
        built, names = self._app(opened)
        # The fewest files (Plans/adapter.plan.md): app.py (pages, layout, wiring, runtime), widgets.py,
        # data.py, requirements.txt, README.md; adapter.py and connections.py when a widget reads a
        # connection's table (read there on first use, never a copy of its rows); never a sandbox file.
        named, in_code = _api_use(opened.canvas, built)
        if not named and not in_code:  # it calls no API: api_adapter.py and the actions stay behind
            built = {n: t for n, t in built.items() if n not in ("api_adapter.py", "sab_actions.json")}
        files = build_rules.folded(opened.canvas, built)
        read_live = sorted({n.split("]", 1)[0][1:] for n in names if n.startswith("[") and "]" in n})
        core: dict[str, Any] = {"files": {}, "requirements": [], "variables": []}
        if read_live and self._core_files is not None:
            core = await self._core_files(read_live)
        if core["files"]:
            files |= core["files"]
            # (The sandbox's tables stay the export's own copies: connections.py never names the sandbox, so
            # a canvas reading both a connection's table and a sandbox one lost the sandbox's.)
            names = {n for n in names if not n.startswith("[") or n.casefold().startswith("[sandbox]")}
            wanted = [*build_rules.REQUIREMENTS, *core["requirements"]]
            files["requirements.txt"] = "\n".join(dict.fromkeys(wanted)) + "\n"
        tables = await self._widgets.tables_for(names)
        await self._approvals.allowed(
            who,
            subject=opened.path,
            action="export_canvas",
            detail=f"Export the canvas {opened.path} into {chosen}"
            + (f", with the rows of {', '.join(sorted(tables))}" if tables else ""),
            otherwise="nothing was written",
        )
        # An app that calls the local sandbox API reads its address from these where it is deployed.
        # (sab_canvas.py always holds action and api_call: only a widget's, a page's or the wiring's use
        # counts; a wire that names only another API's action does not call the local one.)
        local = any(not c.startswith("[") for c in named) or (in_code and not named)
        variables = list(API_VARIABLES) if local else []
        warnings = [f"Set {v} where it runs: {API_VARIABLES[v]}." for v in variables]
        lines = [f"- `{v}`: {API_VARIABLES[v]}\n" for v in variables]
        for variable in core["variables"]:  # what connections.py reads (names only)
            variables.append(variable)
            warnings.append(f"Set {variable} where it runs: connections.py reads it.")
            lines.append(f"- `{variable}`: connections.py reads it\n")
        # Another API's own client travels with the app (API_<name>.py): its sign-in's variables are named.
        for name in sorted(n for n in files if _client(n)):
            for variable in dict.fromkeys(_ENVIRON.findall(files[name])):
                if variable in variables:
                    continue  # connections.py reads it too: said once
                variables.append(variable)
                warnings.append(f"Set {variable} where it runs: {name} reads it.")
                lines.append(f"- `{variable}`: {name} reads it (its API's address or sign-in)\n")
        if variables:
            calls = bool(named) or in_code
            files["README.md"] = (API_README if calls else APP_README) + "".join(lines)
        # The project's own widgets the canvas uses are in widgets.py, with the library's (never a sandbox
        # file).
        files = {n: t for n, t in files.items() if not n.startswith("sandbox")}
        where, written = self._app_files.export(chosen, files, tables)
        self.ws.audit.write(who, "export_canvas", f"{opened.path} -> {where}")
        return {"folder": where, "files": written, "variables": variables, "warnings": warnings}

    async def close(self, canvas: str) -> dict[str, Any]:
        opened = self._open.pop(canvas, None)
        if opened is not None:
            await self._live.stop(f"canvas-{opened.id}")
        return {"ok": True}


# The variables an exported app that calls the local sandbox API needs where it runs (Play and Launch set them
# here; services/local_api.py env_for_app): the approved "Export names the API variables" (2026-11-21).
API_VARIABLES: dict[str, str] = {
    "SAB_API_URL": "the deployed API's address (https://…)",
    "SAB_API_KEY": "the key the deployed API takes (Authorization: Bearer)",
    "SAB_API_BASE": "the API's base path, as /api (empty when it has none)",
}
_CALLS = re.compile(r"\b(?:api_call|action)\(|SAB_API_URL")
_ENVIRON = re.compile(r"os\.environ\.get\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\"")


def _api_use(canvas: Mapping[str, Any], built: Mapping[str, str]) -> tuple[list[str], bool]:
    """The API actions an app names (its wiring, its widgets' endpoint values), and whether its own code calls
    one (sab_canvas.py always holds action and api_call: only a widget's, a page's or the wiring's use
    counts)."""
    named = [*wiring.api_calls(canvas), *_endpoint_values(canvas)]
    in_code = any(
        _CALLS.search(t)
        for n, t in built.items()
        if n.endswith(".py") and n not in ("sab_canvas.py", "api_adapter.py") and not _client(n)
    )
    return named, in_code


def _client(name: str) -> bool:
    """A library API's own client file among an app's files (API_<name>.py, Add API's made file)."""
    return name.startswith("API_") and name.endswith(".py") and "/" not in name


def _endpoint_values(canvas: Mapping[str, Any]) -> list[str]:
    """Each action a widget instance's endpoint property names."""
    found = [(n.get("values") or {}).get("endpoint") for _, n in model.walk(canvas) if n["kind"] == "widget"]
    return [v for v in found if isinstance(v, str) and v]


APP_README = (
    "# The app\n\nRun it with `streamlit run app.py`.\n\n## Variables to set where it runs\n\nIts "
    "connections are read through adapter.py and connections.py beside it: set these, never in a file.\n\n"
)
API_README = (
    "# The app\n\nRun it with `streamlit run app.py`.\n\n## Variables to set where it runs\n\nIt calls an "
    "API through api_adapter.py (the local sandbox API as it is deployed, or another API by its own client "
    "file): set these, never in a file.\n\n"
)


def _keep(made: Open, fresh: Open) -> Open:
    """A canvas opened again: its history and version kept, its contents as the file has them now."""
    made.canvas, made.stamp, made.read_only, made.broken = (
        fresh.canvas,
        fresh.stamp,
        fresh.read_only,
        fresh.broken,
    )
    made.notes = fresh.notes
    made.version += 1
    return made


Hook = Callable[[str, str], Awaitable[int]]


def _pages(canvas: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each page by name: its containers and widget instances by id (a widget's name beside its id), as
    the change log names them."""
    out: dict[str, dict[str, Any]] = {}
    for page in canvas.get("pages") or []:
        items: dict[str, Any] = {}
        waiting = list(page.get("children") or [])
        while waiting:
            node = waiting.pop()
            waiting += list(node.get("children") or [])
            label = f"{node.get('id')} {node.get('widget') or node.get('kind') or ''}".strip()
            items[label] = {k: v for k, v in node.items() if k != "children"}
        out[str(page.get("name") or page.get("id"))] = {"items": items}
    return out


def _placed(node: Any) -> set[str]:
    """The widgets a canvas file places, read loosely (any layout's format): every node of kind widget."""
    found: set[str] = set()
    if isinstance(node, dict):
        if node.get("kind") == "widget" and isinstance(node.get("widget"), str):
            found.add(node["widget"])
        for value in node.values():
            found |= _placed(value)
    elif isinstance(node, list):
        for value in node:
            found |= _placed(value)
    return found
