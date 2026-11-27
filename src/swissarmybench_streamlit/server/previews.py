"""Widget previews (the owner, 2026-11-21: "a pane on the right that shows available widgets with a small
preview of it rendered with its name and description"): each widget rendered once, headless, with its defaults
and the made-up sample data, through Play's own builder and run (server/live_runs.py), and photographed by Qt
WebEngine (the desktop app's own engine, already the app's dependency) in a child process. The picture (480
px wide; the gallery shows it small, the hover large) is kept in the state folder's widget-previews/ by the
widget file's hash and the theme, so it is made again only when the widget changes.

One widget at a time, in the background: the pane never waits (it shows a card with the widget's name until
the picture is there, and a failure's one line with Try again). The Canvas board's own widgets go first
(`first`); the gallery's cards are asked for as they scroll into view, after them.

A failure is kept in memory only (the owner, 2026-11-22: "The pre-built widgets are not rendering on my
machine": a failure kept on disk, made while the project's `.venv` was still being made, held a preview back
for good). It is tried again when its cause can have changed: the project's Python ready or another project
opened (the `project_python` notice), Streamlit installed (the page's Try again after its install), the theme
(another key), or the page asking again once its back-off is over (`retry_in`; never a busy loop).

The photographer, per system (shooter_ways): on Linux Qt's offscreen platform (no display needed); on Windows
and macOS a hidden window first (a frameless tool window placed off every screen, never activated: Qt
WebEngine draws there as in any window), the offscreen platform only after it; the way that worked kept for
the session. A picture all of one colour of a widget that shows something is a failure (blank), never a
preview.

Notices: `widget_preview` {name, theme, state} when one is made or fails; `widget_previews` {retry} when the
failures of the machine's may be tried again.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import tempfile
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHOT_SECONDS = 90.0  # a first Streamlit page on a slow machine: the engine's start, the page, the script
WIDTH = 480
FLAGS = "--no-sandbox --disable-gpu --disable-logging"

# Run in this app's Python (it has PySide6): the page loaded in the chosen way, waited for until Streamlit has
# drawn the widget, its box photographed. Prints one line: SAB-SHOT {"ok": ..., "said": ..., ...}.
SHOOTER = r"""
import json, os, sys, time
from PySide6.QtCore import QRect, QSize, QTimer, QUrl, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

url, out, width, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
way = sys.argv[5] if len(sys.argv) > 5 else "offscreen"
app = QApplication([sys.argv[0]])
view = QWebEngineView()
view.resize(QSize(1240, 900))
if way == "hidden":  # a window of the system's own platform, never on a screen and never activated
    view.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
    view.setAttribute(Qt.WA_ShowWithoutActivating, True)
    desk = app.primaryScreen().virtualGeometry()
    view.move(desk.left() - 1240 - 400, desk.top())
view.show()
started = time.monotonic()
PROBE = '''(() => {
  const box = document.querySelector('.st-key-sab-w1');
  const running = document.querySelector('[data-testid="stStatusWidget"]');
  if (!box || running) return null;
  const alerts = [...document.querySelectorAll('[data-testid="stAlertContentError"]')];
  const failed = alerts.map(e => e.innerText).find(t => / failed: /.test(t));
  const r = box.getBoundingClientRect();
  const shown = 'canvas,img,svg,iframe,input,button,textarea,select,video';
  const inked = !!(box.innerText.trim() || box.querySelector(shown));
  return JSON.stringify({x: r.left, y: r.top, w: r.width, h: r.height, failed: failed || null, inked: inked});
})()'''

def done(said):
    try:  # the server that asked may be gone (its end of the pipe closed): end all the same
        print("SAB-SHOT " + json.dumps(said), flush=True)
    except Exception:
        pass
    app.quit()

def probe():
    if time.monotonic() - started > limit - 3:
        return done({"ok": False, "said": "The widget did not finish drawing.", "kind": "setup"})
    view.page().runJavaScript(PROBE, 0, got)

def uniform(image):
    # One colour all over (sampled on a grid): nothing was drawn.
    picture = image.toImage()
    w, h = picture.width(), picture.height()
    if w == 0 or h == 0:
        return True
    first = picture.pixel(0, 0)
    step = max(1, min(w, h) // 40)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if picture.pixel(x, y) != first:
                return False
    return True

def got(found):
    if not found:
        return QTimer.singleShot(250, probe)
    box = json.loads(found)
    if box["failed"]:
        return done({"ok": False, "said": box["failed"][:500], "kind": "widget"})
    left = {"n": 5}
    def shoot():
        rect = QRect(int(box["x"]), int(box["y"]), max(1, int(box["w"])), max(1, int(box["h"])))
        image = view.grab(rect)
        if box["inked"] and uniform(image):  # the page shows something, the picture nothing: not drawn yet
            left["n"] -= 1
            if left["n"] > 0:
                return QTimer.singleShot(1000, shoot)
            return done({"ok": False, "said": "The picture came out blank.", "kind": "setup", "blank": True})
        image = image.scaledToWidth(width, Qt.SmoothTransformation)
        done({"ok": bool(image.save(out, "PNG")), "said": "", "way": way})
    QTimer.singleShot(900, shoot)

view.loadFinished.connect(lambda ok: QTimer.singleShot(400, probe))
view.load(QUrl(url))
late = {"ok": False, "said": "The preview took too long.", "kind": "setup"}
QTimer.singleShot(int(limit * 1000), lambda: done(late))
app.exec()
os._exit(0)  # never held up by the engine's own teardown
"""

DARK = '[theme]\nbase = "dark"\n'
LIGHT = '[theme]\nbase = "light"\n'

# A failure is tried again once this long has passed since it (seconds), by its kind, doubling with each
# failure up to the most: the machine's ("setup": the Python, Streamlit, the photographer) soon, the widget's
# own later.
BACKOFF: dict[str, tuple[float, float]] = {"setup": (15.0, 300.0), "widget": (60.0, 1800.0)}


def backoff(kind: str, tries: int) -> float:
    first, most = BACKOFF.get(kind, BACKOFF["setup"])
    return float(min(most, first * 2 ** max(0, tries - 1)))


def shooter_ways(system: str = sys.platform, environ: Mapping[str, str] | None = None) -> list[str]:
    """How the photographer opens its page, in the order tried: on Linux Qt's offscreen platform (it needs
    no display; a hidden window after it only where there is one), on Windows and macOS a hidden window of
    the system's own platform first (offscreen there may draw nothing), offscreen after it."""
    environ = os.environ if environ is None else environ
    if system.startswith("linux"):
        shown = bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))
        return ["offscreen", "hidden"] if shown else ["offscreen"]
    return ["hidden", "offscreen"]


def shooter_environment(way: str, environ: Mapping[str, str]) -> dict[str, str]:
    """The photographer's environment for a way: offscreen names Qt's platform; hidden leaves the system's
    own (a QT_QPA_PLATFORM the app was started with taken away)."""
    out = dict(environ) | {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}
    if way == "offscreen":
        out["QT_QPA_PLATFORM"] = "offscreen"
    else:
        out.pop("QT_QPA_PLATFORM", None)
    return out


def shooter_command(python: str, url: str, out: str, way: str) -> list[str]:
    return [python, "-c", SHOOTER, url, out, str(WIDTH), str(SHOT_SECONDS), way]


@dataclass
class Failure:
    said: str
    kind: str  # "setup" (the machine's) or "widget" (its own)
    at: float
    tries: int = 1
    missing: dict[str, Any] | None = None  # the one missing-package answer (domain/packages.py)


Notify = Callable[[dict[str, Any]], Awaitable[Any]]
MISSING_KEYS = ("feature", "packages", "python", "command")


class Previewer:
    def __init__(
        self,
        widgets: Any,
        live: Any,
        python: str = sys.executable,
        *,
        notify: Notify | None = None,
        clock: Callable[[], float] = time.monotonic,
        system: str = sys.platform,
    ) -> None:
        self._widgets = widgets  # services/widgets.py Widgets
        self._live = live  # server/live_runs.py LiveRuns
        self._python = python  # this app's own Python (PySide6)
        self._notify = notify  # the pages told (the live notices' broadcast)
        self._clock = clock
        self._system = system
        self._queue: deque[tuple[str, str, str]] = deque()  # (name, theme, key), the next first
        self._working: str | None = None
        self._failed: dict[str, Failure] = {}  # by key: memory only
        self._way: str | None = None  # the photographer's way that worked, this session
        self._worker: asyncio.Task[None] | None = None
        self._shooters: set[asyncio.subprocess.Process] = set()  # the photographers running now
        self._told: set[asyncio.Future[Any]] = set()

    # ===== what the pages ask =====

    def state(self, name: str, theme: str, first: bool = False, retry: bool = False) -> dict[str, Any]:
        """The preview's state, and the asking: ready (its address), coming (queued or being made; `first`
        puts it at the front: the board's), failed (why, `retry_in` seconds until an ask tries it again;
        `retry`: now)."""
        said = dict(self._widgets.preview(name, theme))
        if said.get("state") != "coming":
            return said
        key = str(said["key"])
        if key == self._working:
            return said
        if any(k == key for _n, _t, k in self._queue):
            if first:
                self._queue = deque([(name, theme, key), *(q for q in self._queue if q[2] != key)])
            return said
        failure = self._failed.get(key)
        if failure is not None and not retry:
            left = backoff(failure.kind, failure.tries) - (self._clock() - failure.at)
            if left > 0:
                return said | self._failed_answer(failure, left)
        self._enqueue(name, theme, key, first)
        return said

    def want(self, name: str, theme: str) -> None:
        """A preview asked for: made in the background when it is not made yet."""
        with contextlib.suppress(Exception):
            self.state(name, theme)

    def _failed_answer(self, failure: Failure, left: float) -> dict[str, Any]:
        answer: dict[str, Any] = {
            "state": "failed",
            "said": failure.said,
            "kind": failure.kind,
            "retry_in": max(1, round(left)),
        }
        if failure.missing:
            answer["missing"] = failure.missing
            answer["install"] = self._widgets.install_place()
        return answer

    def _enqueue(self, name: str, theme: str, key: str, first: bool) -> None:
        if first:
            self._queue.appendleft((name, theme, key))
        else:
            self._queue.append((name, theme, key))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._work())

    def heard(self, message: Mapping[str, Any]) -> None:
        """A live notice: the project's Python ready, or another project opened, is a reason for every
        failure of the machine's to be tried again at the next ask (the pages told to ask)."""
        kind = str(message.get("type") or "")
        if kind == "project_python" and message.get("status") not in ("ready", "none"):
            return
        if kind not in ("project_python", "project_changed"):
            return
        if self.retry_setup():
            self._tell({"type": "widget_previews", "retry": True})

    def retry_setup(self) -> int:
        """Every failure of the machine's due now (its back-off over); how many."""
        due = [f for f in self._failed.values() if f.kind == "setup"]
        for failure in due:
            failure.at = float("-inf")
        return len(due)

    def _tell(self, message: dict[str, Any]) -> None:
        if self._notify is None:
            return
        try:
            task = asyncio.ensure_future(self._notify(message))
        except RuntimeError:  # no loop (a plain call): nobody to tell
            return
        self._told.add(task)
        task.add_done_callback(self._told.discard)

    # ===== the work =====

    async def _work(self) -> None:
        while self._queue:
            name, theme, key = self._queue.popleft()
            self._working = key
            try:
                await self.make(name, theme)
            except Exception as error:  # one widget's trouble is its own mark, never the queue's end
                with contextlib.suppress(Exception):
                    self._fail(key, name, theme, f"The preview could not be made: {error}", "setup")
            finally:
                self._working = None

    def _fail(
        self, key: str, name: str, theme: str, said: str, kind: str, missing: dict[str, Any] | None = None
    ) -> None:
        was = self._failed.get(key)
        tries = was.tries + 1 if was is not None else 1
        self._failed[key] = Failure(said[:2000], kind, self._clock(), tries, missing)
        self._tell({"type": "widget_preview", "name": name, "theme": theme, "state": "failed"})

    async def make(self, name: str, theme: str) -> dict[str, Any]:
        """One preview: the widget run with its defaults, photographed, kept by its file's hash and theme."""
        key = self._widgets.preview_key(name, theme)
        files, canvas = self._widgets.app_of(name, {})
        files = dict(files) | {".streamlit/config.toml": DARK if theme == "dark" else LIGHT}
        tables = await self._widgets.tables_for(self._widgets.named_tables(canvas, self._widgets.built()))
        run = await self._live.run(f"preview-{theme}", files, tables, self._widgets.python())
        if not run.get("ok"):
            problem = run.get("problem") or {}
            missing = (
                {k: problem[k] for k in MISSING_KEYS if k in problem}
                if problem.get("kind") == "missing" and problem.get("packages")
                else None
            )
            said = str(problem.get("message") or "")
            if not said and missing:
                packages = ", ".join(str(p) for p in missing.get("packages") or [])
                said = f"Previews need {packages} in the project's Python."
            said = said or "Streamlit is not in this Python."
            self._fail(key, name, theme, said, "setup", missing)
            return {"ok": False, "said": said}
        port = self._live.port_of(run["base"].rsplit("/", 1)[-1])
        url = f"http://127.0.0.1:{port}{run['base']}/"
        handle, out = tempfile.mkstemp(suffix=".png", prefix="sab-preview-")
        os.close(handle)
        try:
            shot = await self._photograph(url, out)
            if shot.get("ok"):
                self._widgets.preview_made(key, Path(out).read_bytes())
                self._failed.pop(key, None)
                self._tell({"type": "widget_preview", "name": name, "theme": theme, "state": "ready"})
            else:
                said = str(shot.get("said") or "The preview could not be made.")
                self._fail(key, name, theme, said, str(shot.get("kind") or "setup"))
            return shot
        finally:
            Path(out).unlink(missing_ok=True)

    async def _photograph(self, url: str, out: str) -> dict[str, Any]:
        """The page photographed: the way that worked this session, else each of this system's in turn
        while the trouble is the photographer's own (it did not start, or drew nothing)."""
        ways = [self._way] if self._way else shooter_ways(self._system)
        shot: dict[str, Any] = {"ok": False, "said": "The preview could not be made.", "kind": "setup"}
        for way in ways:
            shot = await self._shoot(url, out, way)
            if shot.get("ok"):
                self._way = way
                return shot
            if not (shot.get("blank") or shot.get("started") is False):
                return shot
        return shot

    async def _shoot(self, url: str, out: str, way: str = "offscreen") -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            *shooter_command(self._python, url, out, way),
            env=shooter_environment(way, os.environ),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._shooters.add(process)
        try:
            found, _ = await asyncio.wait_for(process.communicate(), SHOT_SECONDS + 15)
        except TimeoutError:
            process.kill()
            await process.wait()
            return {"ok": False, "said": "The preview took too long.", "kind": "setup"}
        finally:
            self._shooters.discard(process)
            if process.returncode is None:  # cancelled (the server stopping): it never outlives the server
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
        line = next(
            (x for x in found.decode("utf-8", "replace").splitlines() if x.startswith("SAB-SHOT ")), None
        )
        if line is None:
            return {
                "ok": False,
                "said": "The preview's browser did not start here.",
                "kind": "setup",
                "started": False,
            }
        said: dict[str, Any] = json.loads(line[len("SAB-SHOT ") :])
        return said

    async def stop(self) -> None:
        for process in list(self._shooters):  # a photographer still at work ends with the server
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        if self._worker is not None:
            self._worker.cancel()
        for theme in ("light", "dark"):
            with contextlib.suppress(Exception):
                await self._live.stop(f"preview-{theme}")
