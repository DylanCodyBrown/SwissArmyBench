"""Share… for a launched Streamlit app (the base's services/sharing.py ShareTarget; Microsoft Dev Tunnels).

The tunnel goes to the app's own 127.0.0.1 port, never to Swiss Army Bench's: a second Streamlit process of
the launch's own run folder (the same build, the same tables), in the canvas's Python, at the address's root
with the shared flags (server/streamlit_apps.py SHARED_FLAGS). The launch's own window keeps its proxy
address. When the launch ends (Stop, a launch again, the server's stop) the share ends first
(Launches.stopped), then this process: a link always ends with its app.
"""

from __future__ import annotations

from typing import Any, Protocol

from swissarmybench.services.sharing import Opened
from swissarmybench.services.workspace import Conflict
from swissarmybench_streamlit.services.launch import Launches
from swissarmybench_streamlit.services.streamlit_ports import Process

KIND: str = "streamlit"
NOT_RUNNING: str = "The app is not launched: Launch it first, then share it."


class SharedRunner(Protocol):
    async def start_shared(self, python: str, folder: str) -> Process: ...


class StreamlitShare:
    def __init__(self, launches: Launches, runner: SharedRunner) -> None:
        self._launches = launches
        self._runner = runner
        self._processes: dict[str, Process] = {}

    async def open(self, app: str) -> Opened:
        launched = self._launches.running(app)
        if launched is None:
            raise Conflict(NOT_RUNNING)
        await self.close(app)
        try:
            process = await self._runner.start_shared(launched.python, launched.folder)
        except ValueError as error:
            raise Conflict(f"The shared run did not start: {error}") from None
        self._processes[app] = process
        return Opened(process.port, f"{launched.title} · build {launched.number}")

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


def wire(services: Any, launches: Launches, runner: SharedRunner) -> StreamlitShare:
    """The composition root's part: the target registered, and a launch's end ending its share."""
    target = StreamlitShare(launches, runner)
    services.hooks.share_targets[KIND] = target

    async def stopped(app: str) -> None:
        sharing = services.hooks.sharing
        if sharing is not None:
            await sharing.app_stopped(KIND, app)
        await target.close(app)

    launches.stopped.append(stopped)
    return target
