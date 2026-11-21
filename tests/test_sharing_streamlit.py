"""Share… for a launched Streamlit app: the tunnel goes to a shared run's own 127.0.0.1 port (never the
server's, nor the proxy's path), started with the shared flags; the share ends when the launch ends. Made-up
names."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench.services.hooks import Hooks
from swissarmybench.services.workspace import Conflict
from swissarmybench_streamlit.server import streamlit_apps
from swissarmybench_streamlit.services import sharing_target
from swissarmybench_streamlit.services.sharing_target import StreamlitShare


class FakeProcess:
    def __init__(self, port: int) -> None:
        self.port = port
        self.python = "python"
        self.stopped = False

    def alive(self) -> bool:
        return not self.stopped

    async def stop(self) -> None:
        self.stopped = True


class FakeRunner:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []

    async def start_shared(self, python: str, folder: str) -> FakeProcess:
        self.started.append((python, folder))
        return FakeProcess(8611)


class FakeRuns:
    def __init__(self) -> None:
        self.ended: list[Any] = []
        self.running: dict[str, tuple[str, str]] = {}

    def launched(self, key: str) -> tuple[str, str] | None:
        return self.running.get(key)


def test_the_shared_run_is_the_launchs_own_folder_on_a_port_of_its_own() -> None:
    async def run() -> None:
        runs, runner = FakeRuns(), FakeRunner()
        target = StreamlitShare(runs, runner, lambda app: "Sales POC")
        with pytest.raises(Conflict, match="Launch it first"):
            await target.open("sales")
        runs.running["canvas-sales"] = ("/made/up/play", "/made/up/python")  # Play is not a launch
        with pytest.raises(Conflict, match="Launch it first"):
            await target.open("sales")
        runs.running["launch-sales"] = ("/made/up/run", "/made/up/python")
        opened = await target.open("sales")
        assert opened.port == 8611 and opened.title == "Sales POC"
        assert runner.started == [("/made/up/python", "/made/up/run")]
        assert target.port("sales") == 8611
        await target.close("sales")
        assert target.port("sales") is None

    asyncio.run(run())


def test_a_launchs_end_ends_its_share() -> None:
    async def run() -> None:
        told: list[tuple[str, str]] = []

        class Sharing:
            async def app_stopped(self, kind: str, app: str) -> None:
                told.append((kind, app))

        hooks = Hooks()
        hooks.sharing = Sharing()
        runs, runner = FakeRuns(), FakeRunner()
        target = sharing_target.wire(SimpleNamespace(hooks=hooks), runs, runner, lambda app: app)
        assert hooks.share_targets["streamlit"] is target
        runs.running["launch-sales"] = ("f", "p")
        await target.open("sales")
        for ended in runs.ended:
            await ended("canvas-sales")  # Play's run: not the launch
        assert told == [] and target.port("sales") == 8611
        for ended in runs.ended:
            await ended("launch-sales")
        assert told == [("streamlit", "sales")] and target.port("sales") is None

    asyncio.run(run())


def test_the_shared_flags_are_set_only_for_a_shared_run(monkeypatch: pytest.MonkeyPatch) -> None:
    lines: list[list[str]] = []

    async def capture(*command: str, **_: Any) -> Any:
        lines.append(list(command))
        raise OSError("made-up: not started")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    for shared in (False, True):
        with pytest.raises(streamlit_apps.StreamlitProcessError):
            asyncio.run(
                streamlit_apps.start("python", "/made/up", "/streamlit/launch/sales-x", shared=shared)
            )
    plain, shared_line = lines
    assert "--server.baseUrlPath=streamlit/launch/sales-x" in plain
    assert not set(streamlit_apps.SHARED_FLAGS) & set(plain)
    assert "--server.baseUrlPath=" in shared_line
    assert not any(c.startswith("--server.baseUrlPath=streamlit") for c in shared_line)
    assert "--server.enableCORS=true" in shared_line and "--server.enableXsrfProtection=true" in shared_line
    assert "--server.address=127.0.0.1" in shared_line  # never anything but this computer
    assert "--server.runOnSave=true" not in shared_line


def test_live_runs_say_when_a_run_ends_or_is_written_again(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench_streamlit.server.live_runs import LiveRuns

    class Files:
        def folder(self) -> str:
            return str(tmp_path)

        def touch(self, folder: str, name: str) -> None:
            return None

        def write_table(self, folder: str, name: str, data: bytes) -> None:
            return None

        def remove(self, folder: str) -> None:
            return None

    class Runner:
        async def check(self, python: str) -> dict[str, Any]:
            return {"missing": []}

        async def start(self, python: str, folder: str, base: str) -> FakeProcess:
            return FakeProcess(8622)

    async def run() -> None:
        runs = LiveRuns(Files(), Runner())
        heard: list[str] = []

        async def ended(key: str) -> None:
            heard.append(key)

        runs.ended.append(ended)
        await runs.run("launch-sales", {"app.py": "import streamlit"}, {}, "python")
        assert heard == [] and runs.launched("launch-sales") == (str(tmp_path), "python")
        await runs.run("launch-sales", {"app.py": "import streamlit as st"}, {}, "python")  # launched again
        assert heard == ["launch-sales"]
        await runs.stop("launch-sales")
        assert heard == ["launch-sales", "launch-sales"] and runs.launched("launch-sales") is None

    asyncio.run(run())
