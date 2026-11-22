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
