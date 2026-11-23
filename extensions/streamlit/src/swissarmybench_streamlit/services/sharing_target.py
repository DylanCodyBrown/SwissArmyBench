"""Share… for a launched canvas app (the base's services/sharing.py ShareTarget; Microsoft Dev Tunnels).

The tunnel goes to the app's own 127.0.0.1 port, never to Swiss Army Bench's: a second Streamlit process of
the launch's own run folder (LiveRuns' `launch-<canvas>` run: the same build, the same tables), in its Python,
at the address's root with the shared flags (server/streamlit_apps.py SHARED_FLAGS). The launch's own window
keeps its proxy address. When the launch ends or is launched again (LiveRuns.ended) the share ends first, then
this process: a link always ends with its app.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.services.hooks import Hooks
from swissarmybench.services.sharing import Opened
from swissarmybench.services.workspace import Conflict

KIND: str = "streamlit"
LAUNCH: str = "launch-"  # the canvas's Launch run's key prefix (services/canvas.py)
NOT_RUNNING: str = "The app is not launched: Launch it first, then share it."


class Process(Protocol):
    port: int

    def alive(self) -> bool: ...

    async def stop(self) -> None: ...


class Runs(Protocol):
    """server/live_runs.py LiveRuns."""

    ended: list[Any]

    def launched(self, key: str) -> tuple[str, str] | None: ...


class SharedRunner(Protocol):
    async def start_shared(self, python: str, folder: str) -> Process: ...


class StreamlitShare:
    def __init__(self, runs: Runs, runner: SharedRunner, title_of: Callable[[str], str]) -> None:
        self._runs = runs
        self._runner = runner
        self._title_of = title_of
        self._processes: dict[str, Process] = {}

    async def open(self, app: str) -> Opened:
        launched = self._runs.launched(LAUNCH + app)
        if launched is None:
            raise Conflict(NOT_RUNNING)
        folder, python = launched
        await self.close(app)
        try:
            process = await self._runner.start_shared(python, folder)
        except ValueError as error:
            raise Conflict(f"The shared run did not start: {error}") from None
        self._processes[app] = process
        return Opened(process.port, self._title_of(app))

    async def close(self, app: str) -> None:
        process = self._processes.pop(app, None)
        if process is not None:
            await process.stop()

    async def close_all(self) -> None:
        for app in list(self._processes):
            await self.close(app)

    def port(self, app: str) -> int | None:
        process = self._processes.get(app)
        return process.port if process is not None and process.alive() else None


def wire(hooks: Hooks, runs: Runs, runner: SharedRunner, title_of: Callable[[str], str]) -> StreamlitShare:
    """The composition root's part: the target registered, and a launch's end ending its share."""
    target = StreamlitShare(runs, runner, title_of)
    hooks.share_targets[KIND] = target

    async def ended(key: str) -> None:
        if not key.startswith(LAUNCH):
            return
        app = key[len(LAUNCH) :]
        sharing = hooks.sharing
        if sharing is not None:
            await sharing.app_stopped(KIND, app)
        await target.close(app)

    runs.ended.append(ended)
    return target
