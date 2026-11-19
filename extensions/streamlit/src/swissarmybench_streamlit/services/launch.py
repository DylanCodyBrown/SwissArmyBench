"""Launch, build history and the Performance Analyzer (the owner, 2026-11-19; domain/builds.py and
domain/perf.py). For the canvas's window and the agent alike (app_launch, app_stop, builds_list,
builds_compare, build_relaunch, build_restore, perf_attach, perf_session, perf_hints).

  launch    Visual Studio's F5: the app's export written as a build (builds/<app>/<n>/ in the project), copied
            into a run folder of its own with the tables' rows (never in the build) and sab_perf.py, run in
            the canvas's Python under /streamlit/launch/<key>/ (the proxy's), its window opened by the page
            (titled "<app> · build <n>"). A launch again replaces the running one; Stop ends it
  builds    newest first, each with what changed in words and its result; Compare two (file by file); a
            build's files read (Open, read-only); Relaunch an old one; Restore its cells' code into the app
            (a plan per cell, made in the open document like typing: Undo takes it back)
  analyzer  records only while it is attached (sab_perf.on in the run folder, the proxy's tap): the timeline
            of reruns (trigger, each block's time), the calls, the caches, the web socket's messages (kinds
            and sizes, never their content), the hints; Save into the build (perf-<time>.json); open saved
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

from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_streamlit.domain import builds as rules
from swissarmybench_streamlit.domain import perf
from swissarmybench_streamlit.domain import streamlit_cells as cells
from swissarmybench_streamlit.domain.streamlit_cells import StreamlitError
from swissarmybench_streamlit.services.streamlit import StreamlitApps
from swissarmybench_streamlit.services.streamlit_ports import Files, Process, ProjectFiles, Runner

LAUNCH_PATH: str = "/streamlit/launch/"
DEFAULT_KEEP: int = rules.MAX_KEEP


@dataclass
class Recording:
    """An analyzer session: attached to a run, recording until paused or closed."""

    started: float
    on: bool = True
    messages: list[perf.Message] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    offset: int = 0
    dropped: int = 0


@dataclass
class Launched:
    app: str  # the canvas's id
    title: str
    number: int
    build: str  # the build's folder
    folder: str  # the run's folder (a temporary one)
    secret: str
    process: Process | None = None
    started: float = 0.0
    recording: Recording | None = None

    @property
    def key(self) -> str:
        return f"{self.app}-{self.secret}"

    @property
    def address(self) -> str:
        return f"{LAUNCH_PATH}{self.key}/"


class Launches:
    def __init__(
        self,
        apps: StreamlitApps,
        files: Files,
        build_files: Any,
        runner: Runner,
        project: ProjectFiles,
        now: Callable[[], float] = clock.time,
        keep: Callable[[], int] = lambda: DEFAULT_KEEP,
    ) -> None:
        self._apps = apps
        self._files = files
        self._builds = build_files
        self._runner = runner
        self._project = project
        self._now = now
        self._keep = keep
        self._running: dict[str, Launched] = {}  # by the canvas's id

    # ===== where an app's builds live =====

    def _folder(self, app_id: str) -> tuple[str, str]:
        """The app's builds folder (builds/<app> at its project's top) and its title."""
        app = self._apps._app(app_id, canvas=True)
        if not app.document:
            raise Conflict("Save the app first: its builds go in its project's folder, beside it.")
        project = self._project.folder_of(app.document)
        name = rules.folder_name(cells.app_title(app.document))
        return self._builds.join(project, rules.BUILDS, name), app.title

    def port_of(self, key: str) -> int | None:
        for launched in self._running.values():
            if launched.process is not None and launched.process.alive() and _same(launched.key, key):
                return launched.process.port
        return None

    # ===== launch, relaunch, stop =====

    async def launch(self, app_id: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Launch: the app built (a new build) and run in a window of its own. {"analyzer": true}: the
        analyzer attached from its first load (F5)."""
        folder, title = self._folder(app_id)
        taken = self._builds.builds(folder)
        number = rules.next_number(taken)
        made = await self._apps.build_parts(app_id, f"{title} · build {number}")
        build = self._builds.join(folder, str(number))
        files = dict(made["files"])
        files[rules.APP_FILE] = made["canvas"]
        kept = [
            rules.CellCode(self._relative(made["document"], d), n, k, name, code)
            for d, n, k, name, code in made["cells"]
        ]
        files[rules.CELLS_FILE] = rules.cells_text(kept)
        before = str(int(taken[-1])) if taken else None
        held_before = (
            self._builds.read_one(self._builds.join(folder, before), rules.CELLS_FILE) if before else None
        )
        canvas_before = (
            self._builds.read_one(self._builds.join(folder, before), rules.APP_FILE) if before else None
        )
        changed = rules.changes(
            rules.read_cells(held_before) if held_before else None, kept, canvas_before, made["canvas"]
        )
        stamp = datetime.fromtimestamp(self._now(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        files[rules.BUILD_FILE] = rules.build_json(
            number, stamp, title, made["canvas"], changed, "starting", None
        )
        await self._apps.ws.workers.run(BACKGROUND, self._builds.write, build, files)
        for gone in rules.trimmed([*taken, str(number)], self._keep()):
            self._builds.remove(self._builds.join(folder, gone))
        self._apps.ws.audit.write(who, "app_launch", f"{title}: build {number}")
        answer = await self._run(
            app_id, title, number, build, made, analyzer=bool(isinstance(body, dict) and body.get("analyzer"))
        )
        return answer | {"changed": changed, "problems": made["problems"]}

    def _relative(self, app_document: str | None, document: str) -> str:
        return cells.relative_link(app_document, document)

    async def _run(
        self, app_id: str, title: str, number: int, build: str, made: dict[str, Any], analyzer: bool
    ) -> dict[str, Any]:
        await self.stop(app_id, quiet=True)
        folder = self._files.folder()
        timed = (
            await self._apps.build_parts(app_id, f"{title} · build {number}", perf=True)
            if made.get("timed") is None
            else made
        )
        run_files = {k: v for k, v in timed["files"].items()}
        run_files[cells.PERF_FILE] = self._builds.perf_helper()
        self._files.write(folder, run_files, set())
        for table in made["tables"]:
            try:
                self._files.write_table(folder, table, await self._apps.table_data(table))
            except Exception:  # noqa: S112 (a table the grid no longer has: the page says so when it reads it)
                continue
        launched = Launched(app_id, title, number, build, folder, secrets.token_urlsafe(16))
        if analyzer:
            self._builds.perf_switch(folder, True)
            launched.recording = Recording(self._now())
        self._running[app_id] = launched
        start = clock.perf_counter()
        python = made["python"]
        result, error, first = "started", None, None
        try:
            found = await self._runner.check(python)
            if found["missing"]:
                raise ValueError(f"{', '.join(found['missing'])} is not installed in {python}.")
            launched.process = await self._runner.start(python, folder, launched.address.rstrip("/"))
            launched.started = self._now()
            first = (clock.perf_counter() - start) * 1000
        except ValueError as error_said:
            result, error = "failed", str(error_said)
        text = self._builds.read_one(build, rules.BUILD_FILE)
        if text is not None:
            self._builds.write(build, {rules.BUILD_FILE: rules.with_result(text, result, first, error)})
        if error:
            raise Conflict(f"Build {number} did not start: {error}")
        return self._said(launched)

    def _said(self, launched: Launched) -> dict[str, Any]:
        return {
            "app": launched.app,
            "build": launched.number,
            "title": f"{launched.title} · build {launched.number}",
            "address": launched.address,
            "running": launched.process is not None and launched.process.alive(),
            "analyzer": launched.recording is not None and launched.recording.on,
        }

    async def relaunch(self, app_id: str, number: Any, who: str = "user") -> dict[str, Any]:
        """Relaunch an old build: its own code, as it was built (the tables as the grid has them now)."""
        folder, title = self._folder(app_id)
        build = self._builds.join(folder, str(_number(number)))
        files = await self._apps.ws.workers.run(BACKGROUND, self._builds.read, build)
        try:
            data = rules.read_build(files[rules.BUILD_FILE])
        except KeyError:
            raise NotFound(f"Build {number} has no {rules.BUILD_FILE}.") from None
        code = {
            k: v
            for k, v in files.items()
            if k.endswith(".py") or k in ("requirements.txt", ".streamlit/config.toml")
        }
        timed = code  # an old build relaunches as it was built (its blocks are not timed)
        tables = sorted({t for v in code.values() for t in re.findall(r'_table\("(\w+)"', v)})
        app = self._apps._app(app_id, canvas=True)
        made = {"files": timed, "tables": tables, "python": self._apps.python_of(app), "timed": True}
        self._apps.ws.audit.write(who, "build_relaunch", f"{title}: build {data['number']}")
        return await self._run(app_id, title, int(data["number"]), build, made, analyzer=False)

    async def stop(self, app_id: str, who: str = "user", quiet: bool = False) -> dict[str, Any]:
        launched = self._running.pop(app_id, None)
        if launched is None:
            if quiet:
                return {}
            return {"app": app_id, "running": False}
        if launched.process is not None:
            await launched.process.stop()
        self._files.remove(launched.folder)
        if not quiet:
            self._apps.ws.audit.write(who, "app_stop", f"{launched.title}: build {launched.number}")
        return {"app": app_id, "running": False, "build": launched.number}

    async def stop_all(self) -> None:
        for app_id in list(self._running):
            await self.stop(app_id, quiet=True)

    def status(self, app_id: str) -> dict[str, Any]:
        launched = self._running.get(app_id)
        return self._said(launched) if launched else {"app": app_id, "running": False}

    # ===== the builds =====

    async def listing(self, app_id: str) -> dict[str, Any]:
        """The builds, newest first: number, time, what changed, result, first load, saved sessions."""
        folder, title = self._folder(app_id)

        def read() -> list[dict[str, Any]]:
            out = []
            for name in reversed(self._builds.builds(folder)):
                text = self._builds.read_one(self._builds.join(folder, name), rules.BUILD_FILE)
                if text is None:
                    continue
                try:
                    out.append(rules.read_build(text))
                except rules.BuildError:
                    continue
            return out

        found = await self._apps.ws.workers.run(BACKGROUND, read)
        running = self._running.get(app_id)
        return {
            "app": app_id,
            "title": title,
            "folder": folder,
            "builds": found,
            "running": running.number if running else None,
        }

    async def files(self, app_id: str, number: Any) -> dict[str, Any]:
        """A build's files (Open: read-only)."""
        folder, _ = self._folder(app_id)
        build = self._builds.join(folder, str(_number(number)))
        try:
            found = await self._apps.ws.workers.run(BACKGROUND, self._builds.read, build)
        except FileNotFoundError:
            raise NotFound(f"There is no build {number}.") from None
        return {"build": _number(number), "files": found}

    async def compare(self, app_id: str, a: Any, b: Any) -> dict[str, Any]:
        """Two builds' code file by file (Monaco's diff editor draws each changed one)."""
        left = (await self.files(app_id, a))["files"]
        right = (await self.files(app_id, b))["files"]
        return {"a": _number(a), "b": _number(b), "files": rules.compare(left, right)}

    async def restore(self, app_id: str, number: Any, who: str = "user") -> dict[str, Any]:
        """Restore a build's code into the app: each linked cell whose code differs now, as a plan the window
        makes in the open document like typing (Undo takes it back), and the canvas's layout as it was."""
        found = (await self.files(app_id, number))["files"]
        app = self._apps._app(app_id, canvas=True)
        kept = [
            rules.CellCode(cells.resolve_link(app.document, c.document), c.cell, c.kind, c.name, c.code)
            for c in rules.read_cells(found.get(rules.CELLS_FILE, "[]"))
        ]
        plans = rules.restore_plans(kept, self._apps.held_cells(app_id))
        if plans and app.window is None:
            raise Refused(
                "This app is open without a Workbench window: open it there (workbench_open) and the build's "
                "code goes back into its cells like typing."
            )
        pages = found.get(rules.APP_FILE)
        if pages:
            restored = cells.read_app(pages, lambda link: cells.resolve_link(app.document, link))
            await self._apps.sync(app_id, {"pages": cells.pages_json(restored)})
        for plan in plans:
            await self._apps.ws.live.broadcast(
                {
                    "type": "streamlit_code",
                    "window": app.window,
                    "plan": plan | {"app": app.id, "where": f"cell {plan['cell']}"},
                }
            )
        self._apps.ws.audit.write(who, "build_restore", f"{app.title}: build {number}")
        return {
            "build": _number(number),
            "cells": [{"document": p["document"], "cell": p["cell"]} for p in plans],
            "layout": bool(pages),
        }

    # ===== the Performance Analyzer =====

    def _launched(self, app_id: str) -> Launched:
        launched = self._running.get(app_id)
        if launched is None or launched.process is None or not launched.process.alive():
            raise Conflict("The app is not launched: Launch it first, then open the analyzer.")
        return launched

    def attach(self, app_id: str, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Attach the analyzer to the running launch ({"on": false}: pause; {"clear": true}: a new one)."""
        launched = self._launched(app_id)
        on = not (isinstance(body, dict) and body.get("on") is False)
        if launched.recording is None or (isinstance(body, dict) and body.get("clear")):
            launched.recording = Recording(self._now(), on)
            self._builds.perf_clear(launched.folder)
        launched.recording.on = on
        self._builds.perf_switch(launched.folder, on)
        self._apps.ws.audit.write(who, "perf_attach", f"{launched.title}: {'recording' if on else 'paused'}")
        return {"app": app_id, "build": launched.number, "recording": on}

    def detach(self, app_id: str) -> dict[str, Any]:
        launched = self._running.get(app_id)
        if launched is not None:
            self._builds.perf_switch(launched.folder, False)
            launched.recording = None
        return {"app": app_id, "recording": False}

    def tap(self, key: str, direction: str, message: bytes | str) -> None:
        """The proxy's tap: each websocket message of a launch the analyzer records (its kind and size)."""
        for launched in self._running.values():
            if not _same(launched.key, key):
                continue
            held = launched.recording
            if held is None or not held.on:
                return
            data = message if isinstance(message, bytes) else message.encode("utf-8")
            at = self._now() - held.started
            read = perf.read_forward(data, at) if direction == "down" else perf.read_back(data, at)
            held.messages.append(read)
            if len(held.messages) > perf.MAX_MESSAGES:
                held.messages.pop(0)
                held.dropped += 1
            return

    def _gather(self, launched: Launched) -> None:
        held = launched.recording
        if held is None:
            return
        lines, held.offset = self._builds.perf_records(launched.folder, held.offset)
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                held.records.append(record)

    def _facts(self, app_id: str) -> perf.Facts:
        app, linked, pieces, _, _ = self._apps.canvas_parts(app_id)
        titles: dict[str, str] = {}
        makes: dict[str, tuple[str, ...]] = {}
        reads: dict[str, tuple[str, ...]] = {}
        keys: dict[str, tuple[str, ...]] = {}
        for page in app.pages:
            for block in page.blocks:
                code = linked.code(block.key)
                if code is None:
                    continue
                titles[block.id] = pieces[block.key].name if block.key in pieces else block.id
                mine = cells.facts(code)
                makes[block.id], reads[block.id] = mine.makes, mine.reads
                links = self._apps._state_links(block.id, code, linked.kind(block.key))
                keys[block.id] = tuple(links["state_keys"])
        return perf.Facts(titles, makes, reads, keys)

    def session(self, app_id: str) -> dict[str, Any]:
        """What the analyzer window draws: the timeline, the calls, the caches, the socket, the hints."""
        launched = self._launched(app_id)
        if launched.recording is None:
            return {"app": app_id, "build": launched.number, "recording": False, "reruns": [], "hints": []}
        self._gather(launched)
        return self._session(app_id, launched.number, launched.recording)

    def _session(self, app_id: str, number: int, held: Recording) -> dict[str, Any]:
        facts = self._facts(app_id)
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
            "app": app_id,
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

    def hints(self, app_id: str) -> dict[str, Any]:
        said = self.session(app_id)
        return {"app": app_id, "build": said["build"], "hints": said["hints"]}

    async def save(self, app_id: str, who: str = "user") -> dict[str, Any]:
        """The session saved into its build (perf-<time>.json, shared like the build; no data in it)."""
        launched = self._launched(app_id)
        if launched.recording is None:
            raise Conflict("The analyzer is not attached: there is no session to save.")
        self._gather(launched)
        said = self._session(app_id, launched.number, launched.recording)
        stamp = datetime.fromtimestamp(self._now(), UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{rules.PERF_PREFIX}{stamp}.json"
        text = self._builds.read_one(launched.build, rules.BUILD_FILE)
        files = {name: rules.stable(said)}
        if text is not None:
            files[rules.BUILD_FILE] = rules.with_session(text, name)
        await self._apps.ws.workers.run(BACKGROUND, self._builds.write, launched.build, files)
        self._apps.ws.audit.write(who, "perf_save", f"{launched.title}: build {launched.number}, {name}")
        return {"build": launched.number, "file": name}

    async def saved(self, app_id: str, number: Any, name: str) -> dict[str, Any]:
        """A saved session, as it was recorded."""
        if not re.fullmatch(rf"{rules.PERF_PREFIX}[0-9TZ]+\.json", name or ""):
            raise StreamlitError("Name a saved session: perf-<time>.json (its build lists them).")
        found = (await self.files(app_id, number))["files"]
        if name not in found:
            raise NotFound(f"Build {number} has no {name}.")
        return dict(json.loads(found[name]))


def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8", "replace"), b.encode("utf-8", "replace"))


def _number(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise StreamlitError("Name a build by its number.") from None
    if number < 1:
        raise StreamlitError("Name a build by its number.")
    return number
