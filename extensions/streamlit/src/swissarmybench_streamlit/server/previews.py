"""Widget previews (the owner, 2026-11-21: "a pane on the right that shows available widgets with a small
preview of it rendered with its name and description"): each widget rendered once, headless, with its defaults
and the made-up sample data, through Play's own builder and run (server/live_runs.py), and photographed by Qt
WebEngine (the desktop app's own engine, already the app's dependency) off screen in a child process. The
picture (480 px wide; the gallery shows it small, the hover large) is kept in the state folder's
widget-previews/ by the widget file's hash and the theme, so it is made again only when the widget changes.

One widget at a time, in the background: the pane never waits (it shows a placeholder until the picture is
there, and a failing widget's mark).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SHOT_SECONDS = 60.0
WIDTH = 480

# Run in this app's Python (it has PySide6): the page loaded off screen, waited for until Streamlit has drawn
# the widget, its box photographed. Prints one line: SAB-SHOT {"ok": ..., "said": ...}.
SHOOTER = r"""
import json, sys
from PySide6.QtCore import QRect, QSize, QTimer, QUrl, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

url, out, width = sys.argv[1], sys.argv[2], int(sys.argv[3])
app = QApplication([sys.argv[0]])
view = QWebEngineView()
view.resize(QSize(1240, 900))
view.show()
tries = {"n": 0}
PROBE = '''(() => {
  const box = document.querySelector('.st-key-sab-w1');
  const running = document.querySelector('[data-testid="stStatusWidget"]');
  if (!box || running) return null;
  const alerts = [...document.querySelectorAll('[data-testid="stAlertContentError"]')];
  const failed = alerts.map(e => e.innerText).find(t => / failed: /.test(t));
  const r = box.getBoundingClientRect();
  return JSON.stringify({x: r.left, y: r.top, w: r.width, h: r.height, failed: failed || null});
})()'''

def done(said):
    try:  # the server that asked may be gone (its end of the pipe closed): end all the same
        print("SAB-SHOT " + json.dumps(said), flush=True)
    except Exception:
        pass
    app.quit()

def probe():
    tries["n"] += 1
    if tries["n"] > 120:
        return done({"ok": False, "said": "The widget did not finish drawing."})
    view.page().runJavaScript(PROBE, 0, got)

def got(found):
    if not found:
        return QTimer.singleShot(250, probe)
    box = json.loads(found)
    if box["failed"]:
        return done({"ok": False, "said": box["failed"][:500]})
    def shoot():
        image = view.grab(QRect(int(box["x"]), int(box["y"]), max(1, int(box["w"])), max(1, int(box["h"]))))
        image = image.scaledToWidth(width, Qt.SmoothTransformation)
        done({"ok": bool(image.save(out, "PNG")), "said": ""})
    QTimer.singleShot(900, shoot)

view.loadFinished.connect(lambda ok: QTimer.singleShot(400, probe))
view.load(QUrl(url))
late = {"ok": False, "said": "The preview took too long."}
QTimer.singleShot(int(float(sys.argv[4]) * 1000), lambda: done(late))
app.exec()
import os
os._exit(0)  # never held up by the engine's own teardown
"""

DARK = '[theme]\nbase = "dark"\n'
LIGHT = '[theme]\nbase = "light"\n'


class Previewer:
    def __init__(self, widgets: Any, live: Any, python: str = sys.executable) -> None:
        self._widgets = widgets  # services/widgets.py Widgets
        self._live = live  # server/live_runs.py LiveRuns
        self._python = python  # this app's own Python (PySide6)
        self._queue: asyncio.Queue[tuple[str, str]] | None = None
        self._wanted: set[str] = set()
        self._worker: asyncio.Task[None] | None = None
        self._shooters: set[asyncio.subprocess.Process] = set()  # the photographers running now

    def want(self, name: str, theme: str) -> None:
        """A preview asked for: made in the background when it is not made (or failed) yet."""
        try:
            key = self._widgets.preview_key(name, theme)
        except Exception:
            return
        if key in self._wanted:
            return
        self._wanted.add(key)
        if self._queue is None:
            self._queue = asyncio.Queue()
        self._queue.put_nowait((name, theme))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._work())

    async def _work(self) -> None:
        assert self._queue is not None  # noqa: S101 (made by want)
        while not self._queue.empty():
            name, theme = await self._queue.get()
            try:
                await self.make(name, theme)
            except Exception as error:  # one widget's trouble is its own mark, never the queue's end
                with contextlib.suppress(Exception):
                    self._widgets.preview_failed(name, theme, f"The preview could not be made: {error}")

    async def make(self, name: str, theme: str) -> dict[str, Any]:
        """One preview: the widget run with its defaults, photographed, kept by its file's hash and theme."""
        key = self._widgets.preview_key(name, theme)
        files, canvas = self._widgets.app_of(name, {})
        files = dict(files) | {".streamlit/config.toml": DARK if theme == "dark" else LIGHT}
        tables = await self._widgets.tables_for(self._widgets.named_tables(canvas, self._widgets.built()))
        run = await self._live.run(f"preview-{theme}", files, tables, self._widgets.python())
        if not run.get("ok"):
            said = (run.get("problem") or {}).get("message") or "Streamlit is not in this Python."
            self._widgets.preview_failed(name, theme, said)
            return {"ok": False, "said": said}
        port = self._live.port_of(run["base"].rsplit("/", 1)[-1])
        url = f"http://127.0.0.1:{port}{run['base']}/"
        handle, out = tempfile.mkstemp(suffix=".png", prefix="sab-preview-")
        os.close(handle)
        try:
            said = await self._shoot(url, out)
            if said.get("ok"):
                self._widgets.preview_made(key, Path(out).read_bytes())
            else:
                self._widgets.preview_failed(
                    name, theme, str(said.get("said") or "The preview could not be made.")
                )
            return said
        finally:
            Path(out).unlink(missing_ok=True)

    async def _shoot(self, url: str, out: str) -> dict[str, Any]:
        environ = dict(os.environ) | {
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-gpu --disable-logging",
        }
        process = await asyncio.create_subprocess_exec(
            self._python,
            "-c",
            SHOOTER,
            url,
            out,
            str(WIDTH),
            str(SHOT_SECONDS),
            env=environ,
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
            return {"ok": False, "said": "The preview took too long."}
        finally:
            self._shooters.discard(process)
            if process.returncode is None:  # cancelled (the server stopping): it never outlives the server
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
        line = next(
            (x for x in found.decode("utf-8", "replace").splitlines() if x.startswith("SAB-SHOT ")), None
        )
        if line is None:
            return {"ok": False, "said": "The preview's browser did not start here."}
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
