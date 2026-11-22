"""Launch, Builds and the Performance Analyzer on the widget Canvas (the owner, 2026-11-19: "think Visual
Studio"; carried over to the Canvas of widgets, 2026-11-21). For the Canvas page and the agent alike
(app_launch with stop; canvas_builds and canvas_perf, each by its action).

  launch    the canvas built by the one builder (domain/canvas_build.py) and kept as a build
            (builds/<app>/<n>/ at the project's top: the code exactly as launched, the canvas's file,
            build.json saying what changed in words), then run from a run folder of its own (LiveRuns, at
            /streamlit/run/launch-<id>-<secret>/) with the tables' rows (never in the build) and sab_perf.py
            beside the pages. {"analyzer": true}: the Performance Analyzer attached from the first load. A
            launch again replaces the running one
  builds    newest first; Compare two (file by file; one with the canvas as it is now); a build's files (Open,
            read-only); Relaunch an old one; Restore its canvas (format 2) as one change Undo takes back: the
            library's widgets stay as they are (their code then is in the build's sab_widgets.py)
  analyzer  records only while attached (sab_perf.on in the run folder, the proxy's tap): the reruns (trigger,
            each widget instance's time), the calls, the caches, the web socket's kinds and sizes (never their
            content), the hints; Save into the build (perf-<time>.json); a saved one opened read-only
"""

from __future__ import annotations

import json
import re
import secrets
import time as clock
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import builds as rules
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import perf
from swissarmybench_streamlit.domain import widget_properties as props_rules

PREFIX = "launch-"


@dataclass
class Recording:
    """An analyzer session: attached to a launch, recording until paused or detached."""

    started: float
    on: bool = True
    messages: list[perf.Message] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    offset: int = 0
    dropped: int = 0


@dataclass
class Launched:
    canvas: str
    title: str
    number: int
    build: str  # the build's folder
    recording: Recording | None = None


class BuildError(ValueError):
    """A build named that is not one (its number, its file)."""


class Launches:
    def __init__(
        self,
        canvases: Any,
        live: Any,
        builds: Any,
        now: Callable[[], float] = clock.time,
        keep: Callable[[], int] = lambda: rules.MAX_KEEP,
    ) -> None:
        self._canvases = canvases  # services/canvas.py Canvases
        self._live = live  # server/live_runs.py LiveRuns
        self._builds = builds  # adapters/build_files.py BuildFiles
        self._now = now
        self._keep = keep
        self._running: dict[str, Launched] = {}

    @property
    def ws(self) -> Any:
        return self._canvases.ws

    # ===== where a canvas's builds live =====

    def _where(self, canvas: str) -> tuple[Any, str, str]:
        """The open canvas, its builds folder (builds/<app> at its project's top) and its name."""
        opened = self._canvases._get(canvas)
        project = opened.path.rsplit("/", 1)[0]
        stem = opened.path.rsplit("/", 1)[-1][: -len(model.SUFFIX)]
        # Its folder by the file's name; its title (the window's, the audit's) by the canvas's own name.
        name = str(opened.canvas.get("name") or stem)
        return opened, self._builds.join(project, rules.BUILDS, rules.folder_name(stem)), name

    @staticmethod
    def _key(canvas: str) -> str:
        return f"{PREFIX}{canvas}"

    # ===== launch, relaunch, stop =====

    async def launch(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """A new build of the canvas, run in a window of its own (analyzer: attached from its first load)."""
        body = body if isinstance(body, dict) else {}
        opened, folder, name = self._where(canvas)
        taken = self._builds.builds(folder)
        number = rules.next_number(taken)
        files, names = self._canvases._app(opened)
        canvas_text = model.write(opened.canvas)
        before = self._builds.join(folder, taken[-1]) if taken else None
        changed = rules.canvas_changes(
            self._builds.read_one(before, rules.CANVAS_FILE) if before else None,
            canvas_text,
            self._builds.read_one(before, rules.WIDGETS_FILE) if before else None,
            files.get(rules.WIDGETS_FILE, ""),
        )
        stamp = datetime.fromtimestamp(self._now(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = dict(files) | {rules.CANVAS_FILE: canvas_text}
        kept[rules.BUILD_FILE] = rules.build_json(number, stamp, name, canvas_text, changed, "starting", None)
        build = self._builds.join(folder, str(number))
        self._builds.write(build, kept)
        for gone in rules.trimmed([*taken, str(number)], self._keep()):
            self._builds.remove(self._builds.join(folder, gone))
        self.ws.audit.write(who, "app_launch", f"{name}: build {number}")
        tables = await self._canvases._widgets.tables_for(names)
        answer = await self._run(
            canvas,
            name,
            number,
            build,
            files,
            tables,
            self._canvases._widgets.python(body),
            analyzer=bool(body.get("analyzer")),
            names=names,
        )
        return answer | {"changed": changed, "folder": build}

    async def _run(
        self,
        canvas: str,
        name: str,
        number: int,
        build: str,
        files: dict[str, str],
        tables: dict[str, bytes],
        python: str,
        analyzer: bool,
        names: set[str] | None = None,
    ) -> dict[str, Any]:
        run_files = dict(files)
        if "app.py" in run_files:
            run_files["app.py"] = rules.titled(run_files["app.py"], name, number)
        run_files[rules.PERF_HELPER] = self._builds.perf_helper()
        key = self._key(canvas)
        started = clock.perf_counter()
        answer: dict[str, Any] = await self._live.run(key, run_files, tables, python, names=names or ())
        first = (clock.perf_counter() - started) * 1000
        problem = answer.get("problem") if not answer.get("ok") else None
        text = self._builds.read_one(build, rules.BUILD_FILE)
        if text is not None:
            error = (problem or {}).get("message") if problem else None
            self._builds.write(
                build,
                {rules.BUILD_FILE: rules.with_result(text, "failed" if problem else "started", first, error)},
            )
        if problem:
            self._running.pop(canvas, None)
            return answer | {"build": number, "title": f"{name} · build {number}", "analyzer": False}
        launched = Launched(canvas, name, number, build)
        run_folder = self._live.folder_of(key)
        if run_folder:
            self._builds.perf_clear(run_folder)
            self._builds.perf_switch(run_folder, analyzer)
        if analyzer:
            launched.recording = Recording(self._now())
        self._running[canvas] = launched
        return answer | {
            "build": number,
            "title": f"{name} · build {number}",
            "analyzer": analyzer,
            "running": True,
        }

    async def relaunch(self, canvas: str, number: Any, body: Any = None, who: str = "user") -> dict[str, Any]:
        """An old build run again: its own code as it was built (the tables as the grid has them now)."""
        _, folder, name = self._where(canvas)
        n = _number(number)
        build = self._builds.join(folder, str(n))
        found = await self._files(build, n)
        code = {k: v for k, v in found.items() if k.endswith(".py") or k == "requirements.txt"}
        if "app.py" not in code:
            raise NotFound(f"Build {n} has no app.py to run.")
        names: set[str] = set()
        held = found.get(rules.CANVAS_FILE)
        if held is not None:
            try:
                widgets = self._canvases._widgets
                names = widgets.named_tables(model.read(held).canvas, widgets.built(), widgets.context())
            except model.CanvasError:
                names = set()
        tables = await self._canvases._widgets.tables_for(names)
        self.ws.audit.write(who, "build_relaunch", f"{name}: build {n}")
        return await self._run(
            canvas,
            name,
            n,
            build,
            code,
            tables,
            self._canvases._widgets.python(body),
            analyzer=False,
            names=names,
        )

    async def stop(self, canvas: str, who: str = "user") -> dict[str, Any]:
        launched = self._running.pop(canvas, None)
        stopped = bool(await self._live.stop(self._key(canvas)))
        if launched is not None:
            self.ws.audit.write(who, "app_stop", f"{launched.title}: build {launched.number}")
        return {"ok": stopped, "running": False, **({"build": launched.number} if launched else {})}

    def recording(self, canvas: str) -> Recording | None:
        """The analyzer's session on a launched canvas as it is held (None: not launched, or not attached)."""
        launched = self._running.get(canvas)
        return launched.recording if launched is not None else None

    def status(self, canvas: str) -> dict[str, Any]:
        launched = self._running.get(canvas)
        if launched is None or not self._live.running(self._key(canvas)):
            return {"canvas": canvas, "running": False}
        return {
            "canvas": canvas,
            "running": True,
            "build": launched.number,
            "title": f"{launched.title} · build {launched.number}",
            "analyzer": launched.recording is not None and launched.recording.on,
        }

    # ===== the builds =====

    async def _files(self, build: str, number: int) -> dict[str, str]:
        try:
            found: dict[str, str] = self._builds.read(build)
        except FileNotFoundError:
            raise NotFound(f"There is no build {number}.") from None
        return found

    async def listing(self, canvas: str) -> dict[str, Any]:
        """The builds, newest first: number, time, what changed, result, first load, saved sessions."""
        _, folder, name = self._where(canvas)
        out = []
        for taken in reversed(self._builds.builds(folder)):
            text = self._builds.read_one(self._builds.join(folder, taken), rules.BUILD_FILE)
            if text is None:
                continue
            try:
                out.append(rules.read_build(text))
            except rules.BuildError:
                continue
        running = self._running.get(canvas)
        return {
            "canvas": canvas,
            "app": name,
            "folder": folder,
            "builds": out,
            "running": running.number if running else None,
        }

    async def files(self, canvas: str, number: Any) -> dict[str, Any]:
        """A build's files (Open: read-only)."""
        _, folder, _ = self._where(canvas)
        n = _number(number)
        return {"build": n, "files": await self._files(self._builds.join(folder, str(n)), n)}

    async def compare(self, canvas: str, a: Any, b: Any = None) -> dict[str, Any]:
        """Two builds' code file by file (Monaco's diff editor draws each changed one); without b, build a
        against the canvas as it is now (what a launch now would build)."""
        left = (await self.files(canvas, a))["files"]
        if b in (None, "", "now"):
            opened, _, _ = self._where(canvas)
            right = dict(self._canvases._app(opened)[0]) | {rules.CANVAS_FILE: model.write(opened.canvas)}
            said: Any = "now"
        else:
            right = (await self.files(canvas, b))["files"]
            said = _number(b)
        return {"a": _number(a), "b": said, "files": rules.compare(left, right)}

    async def restore(self, canvas: str, number: Any, body: Any = None, who: str = "user") -> dict[str, Any]:
        """A build's canvas back as one change (Undo takes it back). The library's widgets are not changed:
        their code then is the build's sab_widgets.py (Compare shows how it differs)."""
        found = (await self.files(canvas, number))["files"]
        text = found.get(rules.CANVAS_FILE)
        if text is None:
            raise Refused(
                f"Build {_number(number)} has no {rules.CANVAS_FILE}: it is from before widgets (an app "
                "notebook's), and cannot be restored onto a canvas."
            )
        try:
            restored = model.read(text, self._canvases._facts())
        except model.CanvasError as error:
            raise Refused(f"Build {_number(number)}'s canvas does not read: {error}") from None
        if restored.read_only:
            raise Refused(restored.read_only)
        window = str(body.get("window", "")) if isinstance(body, dict) else ""
        state: dict[str, Any] = await self._canvases.replace(
            canvas, restored.canvas, who, f"build_restore {_number(number)}", window
        )
        widgets = rules.widget_code(found.get(rules.WIDGETS_FILE, ""))
        now = rules.widget_code(
            self._canvases._app(self._canvases._get(canvas))[0].get(rules.WIDGETS_FILE, "")
        )
        differ = sorted(n for n in widgets if n in now and widgets[n] != now[n])
        return state | {
            "restored": _number(number),
            "notes": [*state.get("notes", []), *restored.notes]
            + (
                [
                    f"The library's {', '.join(differ)} changed since build {_number(number)}: "
                    "their code now runs."
                ]
                if differ
                else []
            ),
        }

    # ===== the Performance Analyzer =====

    def _launched(self, canvas: str) -> Launched:
        launched = self._running.get(canvas)
        if launched is None or not self._live.running(self._key(canvas)):
            raise Conflict("The app is not launched: Launch it first, then open the analyzer.")
        return launched

    def _folder(self, canvas: str) -> str | None:
        folder: str | None = self._live.folder_of(self._key(canvas))
        return folder

    def attach(self, canvas: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Attach the analyzer to the running launch ({"on": false}: pause; {"clear": true}: a new one)."""
        launched = self._launched(canvas)
        on = not (isinstance(body, dict) and body.get("on") is False)
        folder = self._folder(canvas)
        if launched.recording is None or (isinstance(body, dict) and body.get("clear")):
            launched.recording = Recording(self._now(), on)
            if folder:
                self._builds.perf_clear(folder)
        launched.recording.on = on
        if folder:
            self._builds.perf_switch(folder, on)
        self.ws.audit.write(who, "perf_attach", f"{launched.title}: {'recording' if on else 'paused'}")
        return {"canvas": canvas, "build": launched.number, "recording": on}

    def detach(self, canvas: str) -> dict[str, Any]:
        launched = self._running.get(canvas)
        folder = self._folder(canvas)
        if launched is not None:
            if folder:
                self._builds.perf_switch(folder, False)
            launched.recording = None
        return {"canvas": canvas, "recording": False}

    def tap(self, key: str, direction: str, message: bytes | str) -> None:
        """The proxy's tap: each websocket message of a launch the analyzer records (its kind and size)."""
        run, _, _ = key.rpartition("-")
        if not run.startswith(PREFIX):
            return
        launched = self._running.get(run[len(PREFIX) :])
        held = launched.recording if launched is not None else None
        if held is None or not held.on or self._live.port_of(key) is None:
            return
        data = message if isinstance(message, bytes) else message.encode("utf-8")
        at = self._now() - held.started
        read = perf.read_forward(data, at) if direction == "down" else perf.read_back(data, at)
        held.messages.append(read)
        if len(held.messages) > perf.MAX_MESSAGES:
            held.messages.pop(0)
            held.dropped += 1

    def _gather(self, canvas: str, launched: Launched) -> None:
        held = launched.recording
        folder = self._folder(canvas)
        if held is None or not folder:
            return
        lines, held.offset = self._builds.perf_records(folder, held.offset)
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                held.records.append(record)

    def _facts(self, canvas: str) -> perf.Facts:
        """What the hints know of the page's blocks: each widget instance's title and the tables it reads."""
        opened = self._canvases._get(canvas)
        built = self._canvases._widgets.built()
        context = self._canvases._widgets.context()
        titles: dict[str, str] = {}
        reads: dict[str, tuple[str, ...]] = {}
        for _page, node in model.walk(opened.canvas):
            if node["kind"] != "widget":
                continue
            titles[node["id"]] = f"{node['widget']} ({node['id']})"
            widget = built.get(node["widget"])
            if widget is None:
                continue
            values = props_rules.values(list(widget.properties), node["values"], context)
            reads[node["id"]] = tuple(
                str(values[p.name]) for p in widget.properties if p.type == "table" and values.get(p.name)
            )
        return perf.Facts(titles=titles, reads=reads)

    def session(self, canvas: str) -> dict[str, Any]:
        """What the analyzer window draws: the timeline, the calls, the caches, the socket, the hints."""
        launched = self._launched(canvas)
        if launched.recording is None:
            return {"canvas": canvas, "build": launched.number, "recording": False, "reruns": [], "hints": []}
        self._gather(canvas, launched)
        return self._session(canvas, launched.number, launched.recording)

    def _session(self, canvas: str, number: int, held: Recording) -> dict[str, Any]:
        facts = self._facts(canvas)
        socket = perf.socket_reruns(held.messages)
        reruns = perf.reruns_of(held.records, socket)
        caches = perf.caches_of(held.records)
        calls = [c | {"rerun": r.index} for r in reruns for c in r.calls]
        total = sum(m.size for m in held.messages if m.direction == "down")
        elements: dict[str, dict[str, int]] = {}
        for m in held.messages:
            if m.direction == "down" and m.element:
                held_element = elements.setdefault(m.element, {"count": 0, "size": 0})
                held_element["count"] += 1
                held_element["size"] += m.size
        return {
            "canvas": canvas,
            "build": number,
            "recording": held.on,
            "reruns": [r.to_json(facts.titles) for r in reruns],
            "calls": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in c.items()} for c in calls],
            "caches": [{k: v for k, v in c.items() if k != "arguments"} for c in caches],
            "socket": {
                "messages": len(held.messages),
                "dropped": held.dropped,
                "size": total,
                "elements": dict(sorted(elements.items(), key=lambda kv: -kv[1]["size"])),
                "biggest": [m.to_json() for m in sorted(held.messages, key=lambda m: -m.size)[:20]],
                "reruns": [s.to_json() for s in socket],
            },
            "hints": perf.hints(reruns, caches, facts),
        }

    def hints(self, canvas: str) -> dict[str, Any]:
        said = self.session(canvas)
        return {"canvas": canvas, "build": said["build"], "hints": said["hints"]}

    async def save(self, canvas: str, who: str = "user") -> dict[str, Any]:
        """The session saved into its build (perf-<time>.json, shared like the build; no data in it)."""
        launched = self._launched(canvas)
        if launched.recording is None:
            raise Conflict("The analyzer is not attached: there is no session to save.")
        self._gather(canvas, launched)
        said = self._session(canvas, launched.number, launched.recording)
        stamp = datetime.fromtimestamp(self._now(), UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{rules.PERF_PREFIX}{stamp}.json"
        text = self._builds.read_one(launched.build, rules.BUILD_FILE)
        files = {name: rules.stable(said)}
        if text is not None:
            files[rules.BUILD_FILE] = rules.with_session(text, name)
        self._builds.write(launched.build, files)
        self.ws.audit.write(who, "perf_save", f"{launched.title}: build {launched.number}, {name}")
        return {"build": launched.number, "file": name}

    async def saved(self, canvas: str, number: Any, name: str) -> dict[str, Any]:
        """A saved session, as it was recorded."""
        if not re.fullmatch(rf"{rules.PERF_PREFIX}[0-9TZ]+\.json", name or ""):
            raise BuildError("Name a saved session: perf-<time>.json (its build lists them).")
        found = (await self.files(canvas, number))["files"]
        if name not in found:
            raise NotFound(f"Build {number} has no {name}.")
        return dict(json.loads(found[name]))

    async def stop_all(self) -> None:
        for canvas in list(self._running):
            await self.stop(canvas, "app")


def _number(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BuildError("Name a build by its number.") from None
    if number < 1:
        raise BuildError("Name a build by its number.")
    return number


_ = secrets  # (the run's own secret is LiveRuns'; kept for the reader: the tap never trusts a key alone)
