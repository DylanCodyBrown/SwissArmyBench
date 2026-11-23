"""A widget preview's photographer (the Streamlit extension's server/previews.py) never outlives the server
that asked for it. Found building test app two (2026-11-22): after a browser test's server was stopped, its
photographer (Qt WebEngine off screen) kept running for hours at a quarter of a core: its print to the closed
pipe raised inside Qt's slot, so app.quit() never ran, and the server's stop did not end it either."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_streamlit.server import previews


def test_the_server_stopping_ends_a_photographer_at_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(previews, "SHOOTER", "import time\ntime.sleep(120)\n")
    shooter = previews.Previewer(widgets=None, live=None)

    class Live:
        async def stop(self, _name: str) -> None:
            return None

    shooter._live = Live()

    async def go() -> Any:
        task = asyncio.create_task(shooter._shoot("http://127.0.0.1:9/", str(tmp_path / "x.png")))
        for _ in range(100):
            if shooter._shooters:
                break
            await asyncio.sleep(0.05)
        (process,) = shooter._shooters
        started = time.monotonic()
        await shooter.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(process.wait(), 10)
        return process.returncode, time.monotonic() - started

    code, took = asyncio.run(go())
    assert code is not None and code != 0 and took < 10 and not shooter._shooters


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="Qt WebEngine is the desktop app's")
def test_a_photographer_whose_pipe_closed_still_ends(tmp_path: Path) -> None:
    environ = dict(os.environ) | {
        "QT_QPA_PLATFORM": "offscreen",
        "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-gpu --disable-logging",
    }
    process = subprocess.Popen(  # noqa: S603 (this Python and the app's own script)
        [sys.executable, "-c", previews.SHOOTER, "http://127.0.0.1:9/", str(tmp_path / "x.png"), "480", "3"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environ,
    )
    assert process.stdout is not None
    process.stdout.close()  # the server that asked is gone: nobody reads what it says
    try:
        process.wait(timeout=60)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
            pytest.fail("the photographer kept running with nobody to answer")


# ===== Canvas previews, 2026-11-22: the owner's "The pre-built widgets are not rendering on my machine" =====


class FakeWidgets:
    """The Widgets service as the previewer reads it: a picture per key once made, nothing on disk."""

    def __init__(self, project: bool = True) -> None:
        self.made: dict[str, bytes] = {}
        self.project = project

    def preview_key(self, name: str, theme: str) -> str:
        return f"{name}-hash-{theme}"

    def preview(self, name: str, theme: str) -> dict[str, Any]:
        key = self.preview_key(name, theme)
        if key in self.made:
            return {"state": "ready", "url": f"/x/{key}", "key": key}
        return {"state": "coming", "key": key}

    def preview_made(self, key: str, data: bytes) -> None:
        self.made[key] = data

    def install_place(self) -> str:
        return "project" if self.project else "app"

    def app_of(self, name: str, body: Any) -> tuple[dict[str, str], dict[str, Any]]:
        return {"app.py": "x"}, {}

    async def tables_for(self, names: set[str]) -> dict[str, bytes]:
        return {}

    def named_tables(self, canvas: Any, built: Any) -> set[str]:
        return set()

    def built(self) -> Any:
        return None

    def python(self) -> str:
        return "/project/.venv/bin/python"


MISSING = {
    "kind": "missing",
    "feature": "Streamlit widgets",
    "packages": ["streamlit"],
    "python": "/project/.venv/bin/python",
    "command": "uv pip install streamlit",
}


class FakeLive:
    """LiveRuns: the project's Python lacks Streamlit until `has` says it is there."""

    def __init__(self) -> None:
        self.has = False
        self.runs = 0

    async def run(self, key: str, files: Any, tables: Any, python: str) -> dict[str, Any]:
        self.runs += 1
        if not self.has:
            return {"ok": False, "problem": dict(MISSING)}
        return {"ok": True, "base": "/streamlit/run/preview-light-s"}

    def port_of(self, key: str) -> int:
        return 9

    async def stop(self, key: str) -> None:
        return None


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def _settle(previewer: previews.Previewer) -> None:
    for _ in range(50):
        await asyncio.sleep(0)
        if previewer._worker is None or previewer._worker.done():
            return


async def _made_shot(url: str, out: str) -> dict[str, Any]:
    Path(out).write_bytes(b"PNG")
    return {"ok": True, "said": ""}


def test_a_failed_preview_is_tried_again_when_its_cause_can_have_changed() -> None:
    """Before: a preview asked while the project's `.venv` lacked Streamlit failed for good (kept on disk,
    never asked again). Now: in memory, with a back-off, tried again on the project's Python ready, on the
    page's Try again (retry), and on an ask after the back-off."""
    told: list[dict[str, Any]] = []

    async def notify(message: dict[str, Any]) -> None:
        told.append(message)

    async def go() -> None:
        widgets, live, clock = FakeWidgets(), FakeLive(), Clock()
        previewer = previews.Previewer(widgets, live, notify=notify, clock=clock)
        previewer._photograph = _made_shot  # type: ignore[method-assign]
        assert previewer.state("kpi", "light", first=True)["state"] == "coming"
        await _settle(previewer)
        failed = previewer.state("kpi", "light")
        assert failed["state"] == "failed" and failed["kind"] == "setup"
        assert failed["missing"]["packages"] == ["streamlit"] and failed["install"] == "project"
        assert failed["said"] == "Previews need streamlit in the project's Python."
        assert 1 <= failed["retry_in"] <= 15
        await asyncio.sleep(0)  # the notice goes out on its own task
        assert {"type": "widget_preview", "name": "kpi", "theme": "light", "state": "failed"} in told
        # Asked again within its back-off: no new run (never a busy loop).
        for _ in range(5):
            assert previewer.state("kpi", "light")["state"] == "failed"
        await _settle(previewer)
        assert live.runs == 1
        # The back-off over: an ask tries it again (still missing: the next back-off is longer).
        clock.now += 16
        assert previewer.state("kpi", "light")["state"] == "coming"
        await _settle(previewer)
        again = previewer.state("kpi", "light")
        assert live.runs == 2 and again["state"] == "failed" and again["retry_in"] > 15
        # The project's Python made (its notice): due at once, the pages told to ask.
        live.has = True
        previewer.heard({"type": "project_python", "status": "making"})
        assert previewer.state("kpi", "light")["state"] == "failed"  # making is no reason yet
        previewer.heard({"type": "project_python", "status": "ready"})
        await asyncio.sleep(0)
        assert {"type": "widget_previews", "retry": True} in told
        assert previewer.state("kpi", "light")["state"] == "coming"
        await _settle(previewer)
        assert previewer.state("kpi", "light")["state"] == "ready" and live.runs == 3
        await asyncio.sleep(0)
        assert {"type": "widget_preview", "name": "kpi", "theme": "light", "state": "ready"} in told
        # Try again (retry) skips the back-off: a widget whose own code failed, asked again now.
        previewer._fail("other-hash-dark", "other", "dark", "other failed: NameError", "widget")
        assert previewer.state("other", "dark")["state"] == "failed"
        assert previewer.state("other", "dark", retry=True)["state"] == "coming"
        await previewer.stop()

    asyncio.run(go())


def test_the_boards_widgets_are_made_before_the_gallerys() -> None:
    async def go() -> list[str]:
        live = FakeLive()
        live.has = True
        previewer = previews.Previewer(FakeWidgets(), live)
        order: list[str] = []

        async def make(name: str, theme: str) -> dict[str, Any]:
            order.append(name)
            await asyncio.sleep(0)
            return {"ok": True}

        previewer.make = make  # type: ignore[method-assign]
        for n in range(10):  # the gallery's cards, asked first
            previewer.state(f"card{n}", "light")
        previewer.state("board_a", "light", first=True)
        previewer.state("card5", "light", first=True)  # one already queued moves to the front
        await _settle(previewer)
        for _ in range(30):
            await asyncio.sleep(0)
        return order

    order = asyncio.run(go())
    # The worker had not started yet: the board's come first, the newest asked first.
    assert order[:2] == ["card5", "board_a"] and len(order) == 11 and order.count("card5") == 1


def test_an_older_failure_on_disk_is_never_read_and_goes_with_the_picture(tmp_path: Path) -> None:
    from swissarmybench_streamlit.adapters.widget_files import PreviewFiles

    files = PreviewFiles(tmp_path)
    (tmp_path / "kpi-abc-light.failed").write_text("Streamlit is not in this Python.", encoding="utf-8")
    assert not hasattr(files, "failed")  # the previewer keeps failures in memory only
    files.put("kpi-abc-light", b"PNG")
    assert files.get("kpi-abc-light") == b"PNG" and not (tmp_path / "kpi-abc-light.failed").exists()


def test_the_photographer_is_chosen_per_system() -> None:
    assert previews.shooter_ways("linux", {}) == ["offscreen"]
    assert previews.shooter_ways("linux", {"DISPLAY": ":0"}) == ["offscreen", "hidden"]
    assert previews.shooter_ways("win32", {}) == ["hidden", "offscreen"]
    assert previews.shooter_ways("darwin", {}) == ["hidden", "offscreen"]
    base = {"PATH": "/bin", "QT_QPA_PLATFORM": "xcb"}
    off = previews.shooter_environment("offscreen", base)
    assert off["QT_QPA_PLATFORM"] == "offscreen" and "--disable-gpu" in off["QTWEBENGINE_CHROMIUM_FLAGS"]
    hidden = previews.shooter_environment("hidden", base)
    assert "QT_QPA_PLATFORM" not in hidden and hidden["PATH"] == "/bin"  # the system's own platform
    command = previews.shooter_command("py", "http://127.0.0.1:9/", "out.png", "hidden")
    assert command[0] == "py" and command[-1] == "hidden" and command[-2] == str(previews.SHOT_SECONDS)
    assert previews.SHOT_SECONDS >= 90  # a first Streamlit page on a slow machine
    assert "Qt.Tool" in previews.SHOOTER and "WA_ShowWithoutActivating" in previews.SHOOTER


def test_a_blank_picture_or_a_browser_that_did_not_start_tries_the_next_way() -> None:
    async def go() -> tuple[list[str], dict[str, Any], list[str], dict[str, Any]]:
        previewer = previews.Previewer(None, None, system="win32")
        tried: list[str] = []
        answers = {
            "hidden": {"ok": False, "said": "The picture came out blank.", "kind": "setup", "blank": True},
            "offscreen": {"ok": True, "said": ""},
        }

        async def shoot(url: str, out: str, way: str = "offscreen") -> dict[str, Any]:
            tried.append(way)
            return dict(answers[way])

        previewer._shoot = shoot  # type: ignore[method-assign]
        first = await previewer._photograph("u", "o")
        await previewer._photograph("u", "o")  # the way that worked is kept: straight to it
        other = previews.Previewer(None, None, system="win32")
        tried2: list[str] = []

        async def failing(url: str, out: str, way: str = "offscreen") -> dict[str, Any]:
            tried2.append(way)
            return {"ok": False, "said": "kpi failed: NameError", "kind": "widget"}

        other._shoot = failing  # type: ignore[method-assign]
        second = await other._photograph("u", "o")  # a widget's own failure: never another way
        return tried, first, tried2, second

    tried, first, tried2, second = asyncio.run(go())
    assert tried == ["hidden", "offscreen", "offscreen"] and first["ok"]
    assert tried2 == ["hidden"] and second["kind"] == "widget"


@pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="Qt WebEngine is the desktop app's")
def test_the_photographer_takes_a_drawn_widget_and_calls_a_blank_one_a_failure(tmp_path: Path) -> None:
    """The real photographer (offscreen here) over a made-up page shaped like a preview run's: a widget
    that shows its words is photographed; one whose box shows words but whose picture comes out all one
    colour (its text the page's colour) is a failure, never a preview."""
    import http.server
    import threading

    pages = {
        "/drawn/": '<div class="st-key-sab-w1" style="width:300px;height:80px;background:#3060c0;'
        'color:white;font:20px sans-serif">Revenue 1,234</div>',
        "/blank/": '<div class="st-key-sab-w1" style="width:300px;height:80px;background:#fff;'
        'color:#fff">Revenue 1,234</div>',
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            page = pages[self.path]
            body = f"<!doctype html><body style='margin:0;background:#fff'>{page}</body>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: Any) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        previewer = previews.Previewer(None, None, system="linux")
        out = str(tmp_path / "drawn.png")
        drawn = asyncio.run(previewer._shoot(f"http://127.0.0.1:{port}/drawn/", out, "offscreen"))
        if drawn.get("kind") == "setup" and not drawn.get("started"):
            # PySide6 is installed but Qt WebEngine cannot start a browser on this machine (the release
            # machine's build job lacks the graphics libraries the install job adds): as without PySide6.
            pytest.skip(f"Qt WebEngine cannot start here: {drawn.get('said')}")
        assert drawn["ok"], drawn
        assert Path(out).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        blank = asyncio.run(previewer._shoot(f"http://127.0.0.1:{port}/blank/", str(tmp_path / "b.png")))
        assert not blank["ok"] and blank.get("blank") and blank["kind"] == "setup", blank
    finally:
        server.shutdown()
