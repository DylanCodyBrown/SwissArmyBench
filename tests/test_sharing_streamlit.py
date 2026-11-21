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


class FakeLaunches:
    def __init__(self) -> None:
        self.stopped: list[Any] = []
        self.launched: dict[str, Any] = {}

    def running(self, app: str) -> Any:
        return self.launched.get(app)


def test_the_shared_run_is_the_launchs_own_folder_on_a_port_of_its_own() -> None:
    async def run() -> None:
        launches, runner = FakeLaunches(), FakeRunner()
        target = StreamlitShare(launches, runner)  # type: ignore[arg-type]
        with pytest.raises(Conflict, match="Launch it first"):
            await target.open("sales")
        launches.launched["sales"] = SimpleNamespace(
            python="/made/up/python", folder="/made/up/run", title="Sales POC", number=3
        )
        opened = await target.open("sales")
        assert opened.port == 8611 and opened.title == "Sales POC · build 3"
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
        launches, runner = FakeLaunches(), FakeRunner()
        target = sharing_target.wire(SimpleNamespace(hooks=hooks), launches, runner)  # type: ignore[arg-type]
        assert hooks.share_targets["streamlit"] is target
        launches.launched["sales"] = SimpleNamespace(python="p", folder="f", title="Sales POC", number=1)
        await target.open("sales")
        for stopped in launches.stopped:
            await stopped("sales")
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
