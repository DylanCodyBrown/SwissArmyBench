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
  export           app.py, app_pages/*.py, sab_canvas.py, sab_widgets.py (the library's widgets inlined), the
                   open tables it names as data/*.parquet, data.py when the project has one, requirements.txt;
                   the agent's waits for the user's Allow
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import canvas_build as build_rules
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import widget_properties as props_rules
from swissarmybench_streamlit.domain.canvas_model import WidgetFacts

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


def canvas_id(path: str) -> str:
    return "cv" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]


class Canvases:
    def __init__(
        self,
        ws: Any,
        files: Any,
        widgets: Any,
        live: Any,
        approvals: Any,
        app_files: Any,
        project_folder: Callable[[], str | None] = lambda: None,
        read_data_py: Callable[[str], str | None] = lambda folder: None,
        list_folder: Callable[[str], list[str]] = lambda folder: [],
        real_path: Callable[[str], str] = lambda path: path,
        builds: Any = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.ws = ws
        self._files = files  # adapters/widget_files.py CanvasFiles
        self._widgets = widgets  # services/widgets.py Widgets
        self._live = live  # server/live_runs.py LiveRuns
        self._approvals = approvals
        self._app_files = app_files  # adapters/streamlit_files.py AppFiles (the export's writer)
        self._project_folder = project_folder
        self._read_data_py = read_data_py
        self._list_folder = list_folder
        self._real = real_path
        self._builds = builds  # adapters/build_files.py BuildFiles (Launch's builds/ in the project)
        self._now = now
        self._open: dict[str, Open] = {}
        widgets.renamed = self.rename_widget

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
            own = props_rules.Context(context.tables, context.variables, dict(node["values"]))
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
        }

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
        opened.back.append(opened.canvas)
        del opened.back[:-HISTORY]
        opened.forward.clear()
        await self._keep(opened, after, window)
        self.ws.audit.write(who, f"canvas_{kind}", f"{opened.path} {made or body.get('id') or ''}".strip())
        return self.state(canvas) | {"made": made}

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
        files = build_rules.build(opened.canvas, built, context, first)
        folder = opened.path.rsplit("/", 1)[0]
        data = self._read_data_py(folder)
        if data is not None:
            files["data.py"] = data
        files["requirements.txt"] = "\n".join(build_rules.REQUIREMENTS) + "\n"
        return files, self._widgets.named_tables(opened.canvas, built, context)

    async def play(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        opened = self._get(canvas)
        page = (body or {}).get("page") if isinstance(body, dict) else None
        page_id = page if isinstance(page, str) and page else opened.canvas["pages"][0]["id"]
        model.page_of(opened.canvas, page_id)
        files, names = self._app(opened, page_id)
        tables = await self._widgets.tables_for(names)
        started = time.monotonic()
        # The played page is the app's default (built so): its address is the app's own, never a page's
        # path (a path Streamlit has not yet heard of says "Page not found" before the first run).
        answer: dict[str, Any] = await self._live.run(
            f"canvas-{opened.id}", files, tables, self._widgets.python(body)
        )
        self.ws.audit.write(who, "canvas_play", opened.path)
        return answer | {
            "canvas": opened.id,
            "page": page_id,
            "seconds": round(time.monotonic() - started, 2),
        }

    async def stop(self, canvas: str, body: Any = None) -> dict[str, Any]:
        """Play stopped (run "play", the default), or the launched app (run "launch")."""
        run = (body or {}).get("run") if isinstance(body, dict) else None
        if run not in (None, "play", "launch"):
            raise Refused("run is play or launch.")
        prefix = "launch" if run == "launch" else "canvas"
        return {"ok": await self._live.stop(f"{prefix}-{self._get(canvas).id}")}

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
        files, names = self._app(opened)
        tables = await self._widgets.tables_for(names)
        if who == "agent":
            detail = f"Export the canvas {opened.path} into {chosen}" + (
                f", with the rows of {', '.join(sorted(tables))}" if tables else ""
            )
            if not await self._approvals.ask(opened.path, "export_canvas", detail):
                raise Refused("The user declined (or did not answer): nothing was written.")
        where, written = self._app_files.export(chosen, files, tables)
        self.ws.audit.write(who, "export_canvas", f"{opened.path} -> {where}")
        return {"folder": where, "files": written}

    async def launch(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Launch (the owner, 2026-11-19: "think Visual Studio"): the app built into the project's
        builds/<app>/<n>/ (its files, the canvas, build.json: what changed in words) and run from that build
        in a process of its own, for a window of its own."""
        from datetime import UTC, datetime

        from swissarmybench_streamlit.domain import builds as build_rules_

        opened = self._get(canvas)
        if self._builds is None:
            raise Conflict("Builds are not kept here.")
        project = opened.path.rsplit("/", 1)[0]
        name = opened.path.rsplit("/", 1)[-1][: -len(model.SUFFIX)]
        folder = self._builds.join(project, build_rules_.BUILDS, build_rules_.folder_name(name))
        taken = self._builds.builds(folder)
        number = build_rules_.next_number(taken)
        files, names = self._app(opened)
        canvas_text = model.write(opened.canvas)
        before = (
            self._builds.read_one(self._builds.join(folder, taken[-1]), model.SUFFIX[1:]) if taken else None
        )
        changed = (
            ["The first build."]
            if before is None
            else (
                ["The layout changed."]
                if build_rules_.digest(before) != build_rules_.digest(canvas_text)
                else ["Nothing changed."]
            )
        )
        stamp = datetime.fromtimestamp(self._now(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = dict(files) | {model.SUFFIX[1:]: canvas_text}
        kept[build_rules_.BUILD_FILE] = build_rules_.build_json(
            number, stamp, name, canvas_text, changed, "started", None
        )
        build = self._builds.join(folder, str(number))
        self._builds.write(build, kept)
        tables = await self._widgets.tables_for(names)
        run_files = dict(files) | {"app.py": build_rules_.titled(files["app.py"], name, number)}
        answer: dict[str, Any] = await self._live.run(
            f"launch-{opened.id}", run_files, tables, self._widgets.python(body)
        )
        self.ws.audit.write(who, "app_launch", f"{name}: build {number}")
        return answer | {
            "build": number,
            "folder": build,
            "changed": changed,
            "title": f"{name} · build {number}",
        }

    async def close(self, canvas: str) -> dict[str, Any]:
        opened = self._open.pop(canvas, None)
        if opened is not None:
            await self._live.stop(f"canvas-{opened.id}")
        return {"ok": True}


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
