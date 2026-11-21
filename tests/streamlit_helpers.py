"""Shared by the Streamlit extension's tests: a Python with Streamlit (or none: those tests skip), a stand-in
for the Streamlit process, and the user at the page answering the agent's approval requests. Made-up data."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.renamed import env
from swissarmybench_streamlit.server import streamlit_apps


def _streamlit_python() -> str | None:
    """A Python with Streamlit, pandas and pyarrow, for the tests that run the real thing."""
    # SWISSARMYGRID_STREAMLIT_PYTHON, its name before the rename, is still read (renamed.env).
    for python in (env("SWISSARMYBENCH_STREAMLIT_PYTHON"), sys.executable):
        if not python or not Path(python).is_file():
            continue
        try:
            if not streamlit_apps.check(python)["missing"]:
                return python
        except ValueError:
            continue
    return None


STREAMLIT_PYTHON = _streamlit_python()
needs_streamlit = pytest.mark.skipif(
    STREAMLIT_PYTHON is None,
    reason="no Python with Streamlit here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)",
)


class FakeProcess:
    def __init__(self, python: str) -> None:
        self.port = 1
        self.python = python
        self.up = True

    def alive(self) -> bool:
        return self.up

    async def stop(self) -> None:
        self.up = False


class FakeRunner:
    """Stands in for the Streamlit process: the app's files and tables are still written for real."""

    def __init__(self, missing: list[str] | None = None) -> None:
        self.missing = missing or []
        self.started: list[tuple[str, str, str]] = []
        self.installed: list[tuple[str, list[str]]] = []
        self.processes: list[FakeProcess] = []

    def default_python(self) -> str:
        return "/made/up/python"

    async def check(self, python: str) -> dict[str, Any]:
        return {"python": python, "missing": list(self.missing)}

    async def start(self, python: str, folder: str, base: str) -> FakeProcess:
        self.started.append((python, folder, base))
        self.processes.append(FakeProcess(python))
        return self.processes[-1]

    async def install(self, python: str, packages: list[str]) -> tuple[int | None, str]:
        self.installed.append((python, packages))
        self.missing = []
        return 0, "installed"


@contextmanager
def answering(
    pending: Callable[[], list[dict[str, Any]]], answer: Callable[[str, bool], Any], approve: bool = True
) -> Iterator[list[dict[str, Any]]]:
    """The user at the page while the block runs: each approval request the agent makes is answered
    (Allow, or Deny), and kept, as the page's prompt showed it."""
    asked: list[dict[str, Any]] = []
    done = threading.Event()

    def watch() -> None:
        while not done.is_set():
            # A request answered a moment ago can still be listed until its asker moves on.
            for request in [r for r in pending() if r["id"] not in {a["id"] for a in asked}]:
                asked.append(request)
                answer(request["id"], approve)
            time.sleep(0.02)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield asked
    finally:
        done.set()
        watcher.join(5)
