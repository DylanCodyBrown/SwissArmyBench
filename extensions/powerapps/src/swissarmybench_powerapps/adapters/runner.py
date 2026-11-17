"""Running the Power Platform tools as child processes: found on the PATH, run with a time limit, their
output read line by line as it comes (each line handed to the caller, who streams it to the page).

Nothing here reads a terminal: stdin is closed, so a command that would prompt fails at once and says what
it needed (every value is passed as an option instead). `NO_COLOR` keeps the output plain. A long-running
process (the app's dev server) is started and kept, its lines read until it ends or is stopped; every one
ends with the server.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

Line = Callable[[str], Awaitable[None] | None]
MAX_KEPT = 400_000  # characters of one run's output kept in memory


@dataclass
class Ran:
    argv: list[str]
    code: int | None
    output: str
    seconds: float
    timed_out: bool = False


@dataclass
class Started:
    """A process left running (the dev server): its lines go to `on_line` until it ends."""

    process: asyncio.subprocess.Process
    argv: list[str]
    reader: asyncio.Task[None] | None = None
    lines: list[str] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.process.returncode is None


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env.pop("CI", None)  # CI=true makes the Power Apps CLI sign in as a service principal
    return env


async def _call(on_line: Line | None, text: str) -> None:
    if on_line is None:
        return
    got = on_line(text)
    if asyncio.iscoroutine(got):
        await got


class Runner:
    def __init__(self, path: str | None = None) -> None:
        # Where tools are looked for: the PATH (a test's recorded fakes come first on it).
        self._path = path

    def which(self, program: str) -> str | None:
        return shutil.which(program, path=self._path or os.environ.get("PATH"))

    def system(self) -> str:
        return sys.platform

    def _resolved(self, argv: list[str]) -> list[str]:
        found = self.which(argv[0])
        if found is None:
            raise FileNotFoundError(argv[0])
        return [found, *argv[1:]]

    async def run(self, argv: list[str], cwd: str | None, timeout: float, on_line: Line | None = None) -> Ran:
        """Run to its end (or the time limit: then it is stopped), each line to `on_line`."""
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *self._resolved(argv),
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=_environment(),
            **_group(),
        )
        kept: list[str] = []
        size = 0

        async def read() -> None:
            nonlocal size
            if process.stdout is None:
                return
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    return
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if size < MAX_KEPT:
                    kept.append(text)
                    size += len(text) + 1
                await _call(on_line, text)

        timed_out = False
        try:
            await asyncio.wait_for(asyncio.gather(read(), process.wait()), timeout)
        except TimeoutError:
            timed_out = True
            await stop(process)
        return Ran(argv, process.returncode, "\n".join(kept), time.monotonic() - started, timed_out)

    async def start(self, argv: list[str], cwd: str | None, on_line: Line | None = None) -> Started:
        process = await asyncio.create_subprocess_exec(
            *self._resolved(argv),
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=_environment(),
            **_group(),
        )
        handle = Started(process, argv)

        async def read() -> None:
            if process.stdout is None:
                return
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    return
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if len(handle.lines) < 2000:
                    handle.lines.append(text)
                await _call(on_line, text)

        handle.reader = asyncio.create_task(read())
        return handle


def free_port() -> int:
    """A port nothing listens on, on 127.0.0.1 (the dev server's)."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _group() -> dict[str, Any]:
    """A child of its own process group, so stopping it stops what it started (npm starts Vite)."""
    if sys.platform.startswith("win"):
        return {"creationflags": 0x00000200}  # CREATE_NEW_PROCESS_GROUP
    return {"start_new_session": True}


async def stop(process: asyncio.subprocess.Process, grace: float = 3.0) -> None:
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        if sys.platform.startswith("win"):
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), grace)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            if sys.platform.startswith("win"):
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), grace)
