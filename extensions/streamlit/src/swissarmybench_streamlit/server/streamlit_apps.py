"""A Streamlit process (a widget run alone, a canvas's Play, a launch, a preview): started in the project's
own Python, never this app's dependency.

One process a run: `streamlit run` on the app's temporary folder, bound to 127.0.0.1 on a free
port, headless, usage statistics off. The process is started through a few lines of Python (`_LAUNCH`)
that watch this server: when the server goes, however it goes, the Streamlit process ends too.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_START_SECONDS: float = 60.0
_INSTALL_SECONDS: float = 900.0
PACKAGES: tuple[str, ...] = ("streamlit", "pandas", "pyarrow")
# Installed with them when a Python is set up for Streamlit (the owner, 2026-11-21): the Excel widgets' readers
# and writer (openpyxl; xlrd for old .xls). Not needed to start: a widget that lacks one says so in its place.
EXTRAS: tuple[str, ...] = ("openpyxl", "xlrd")

# Run in the notebook's Python: end with the server that started it, then be `streamlit run`.
_LAUNCH = r"""
import os, sys, threading, time

def _watch(parent):
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE
        if handle:
            ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
            os._exit(0)
        return
    while True:
        time.sleep(1.0)
        if os.getppid() != parent:
            os._exit(0)

threading.Thread(target=_watch, args=(int(sys.argv[1]),), daemon=True).start()
from streamlit.web import cli
sys.argv = ["streamlit", "run", *sys.argv[2:]]
sys.exit(cli.main())
"""


class StreamlitProcessError(ValueError):
    """A Streamlit app that cannot start (the message says why)."""


def check(python: str) -> dict[str, Any]:
    """Whether a Python can run the app: which of Streamlit, pandas and pyarrow it lacks (`missing`), and
    which of the Excel widgets' packages (`extras`)."""
    probe = (
        "import importlib.util as u, json;"
        f"print(json.dumps([p for p in {list(PACKAGES + EXTRAS)!r} if u.find_spec(p) is None]))"
    )
    try:
        done = subprocess.run(  # noqa: S603 (the notebook's own Python, asked one fixed question)
            [python, "-c", probe], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise StreamlitProcessError(f"{python} did not answer: {error}") from None
    if done.returncode != 0:
        raise StreamlitProcessError(f"{python} is not a Python that runs: {done.stderr.strip()[-300:]}")
    import json

    lacking = list(json.loads(done.stdout.strip().splitlines()[-1]))
    return {
        "python": python,
        "missing": [p for p in lacking if p in PACKAGES],
        "extras": [p for p in lacking if p in EXTRAS],
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# The beta log's hook: (event, exit code, seconds, reason) for a Streamlit process's start, crash and end.
Report = Callable[[str, int | None, float | None, str], None]


def _no_report(event: str, code: int | None, seconds: float | None, reason: str = "") -> None:
    return None


class Process:
    def __init__(
        self, process: asyncio.subprocess.Process, port: int, python: str, report: Report = _no_report
    ) -> None:
        self.process = process
        self.port = port
        self.python = python
        self._report = report
        self._started = time.monotonic()
        self._stopping = False
        self._watch: asyncio.Task[None] | None = None
        self.lines: list[str] = []  # what it last said, for a start that fails
        self._reader: asyncio.Task[None] | None = None

    def alive(self) -> bool:
        return self.process.returncode is None

    def read(self) -> None:
        async def lines() -> None:
            stream = self.process.stdout
            if stream is None:
                return
            while line := await stream.readline():
                self.lines.append(line.decode("utf-8", "replace").rstrip())
                del self.lines[:-40]

        self._reader = asyncio.create_task(lines())

    def watch(self) -> None:
        """Say how it ends: an end when the app stopped it, a crash when it stopped by itself."""

        async def ended() -> None:
            code = await self.process.wait()
            event = "end" if self._stopping else "crash"
            self._report(event, code, time.monotonic() - self._started, "")

        self._watch = asyncio.create_task(ended())

    async def stop(self) -> None:
        self._stopping = True
        if self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                await self.process.wait()
        if self._reader is not None:
            self._reader.cancel()


def _answers(port: int, base: str) -> bool:
    import http.client

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", f"{base}/_stcore/health")
        return connection.getresponse().status == 200
    except OSError:
        return False
    finally:
        connection.close()


# A shared run (Share…: the base's services/sharing.py; Microsoft Dev Tunnels to this process's own port,
# never the server's): at the address's root (the tunnel's link is the app); the CORS and XSRF checks forced
# on over whatever the app's .streamlit/config.toml says (the tunnel rewrites Host and Origin to localhost, so
# the browser's web socket is same-origin to Streamlit and passes them); its files not watched (a build's
# copy: nothing rewrites them while it is shared).
SHARED_FLAGS: tuple[str, ...] = (
    "--server.baseUrlPath=",
    "--server.enableCORS=true",
    "--server.enableXsrfProtection=true",
    "--server.fileWatcherType=none",
    "--server.runOnSave=false",
)


async def start(
    python: str, folder: str, base: str, report: Report = _no_report, shared: bool = False
) -> Process:
    """`streamlit run app.py` in `folder`, in `python`, under the path `base` (the proxy's), on a free
    port of 127.0.0.1. Ready to answer when this returns. `shared`: a shared run (SHARED_FLAGS), at the
    root."""
    port = _free_port()
    command = [
        python,
        "-c",
        _LAUNCH,
        str(os.getpid()),
        str(Path(folder) / "app.py"),
        "--server.address=127.0.0.1",  # never anything but this computer
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        f"--server.baseUrlPath={base.strip('/')}",
        # Its pages are files this app rewrites: Streamlit looks at them itself (no extra package),
        # and runs the open pages again when one changes.
        "--server.fileWatcherType=poll",
        "--server.runOnSave=true",
        "--client.toolbarMode=minimal",
        "--global.developmentMode=false",
    ]
    if shared:  # the later flag wins: these take the place of the proxy's path and the file watching
        command = [
            c
            for c in command
            if not c.startswith(("--server.baseUrlPath=", "--server.fileWatcherType=", "--server.runOnSave="))
        ]
        command += list(SHARED_FLAGS)
    environ = dict(os.environ)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=folder,
            env=environ,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as error:
        report("failed", None, 0.0, type(error).__name__)
        raise StreamlitProcessError(f"Streamlit did not start in {python}: {error}") from None
    running = Process(process, port, python, report)
    running.read()
    deadline = asyncio.get_running_loop().time() + _START_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if not running.alive():
            said = "\n".join(running.lines[-8:])
            report("failed", process.returncode, time.monotonic() - running._started, "stopped as it started")
            raise StreamlitProcessError(f"Streamlit stopped as it started:\n{said}"[:2000])
        if await asyncio.to_thread(
            _answers, port, "" if shared or not base.strip("/") else "/" + base.strip("/")
        ):
            report("start", None, time.monotonic() - running._started, "")
            running.watch()
            return running
        await asyncio.sleep(0.2)
    await running.stop()
    report("timeout", None, time.monotonic() - running._started, "")
    raise StreamlitProcessError(f"Streamlit did not answer within {_START_SECONDS:.0f} seconds.")


async def install(python: str, packages: list[str]) -> tuple[int | None, str]:
    """Install packages into the notebook's Python (its environment): with uv when it is here, else
    that Python's own pip. The exit code (None: it took too long and was stopped) and what it said."""
    uv = shutil.which("uv") or next(
        (
            str(p)
            for p in (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv")
            if p.is_file()
        ),
        None,
    )
    command = (
        [uv, "pip", "install", "--python", python, *packages]
        if uv
        else [python, "-m", "pip", "install", *packages]
    )
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), _INSTALL_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return None, ""
    return process.returncode, out.decode("utf-8", "replace")[-4000:]


class Runner:
    """Check a Python, start a Streamlit process, install what it lacks. `report` hears each Streamlit
    process's start, crash and end (the beta log)."""

    def __init__(self, report: Report = _no_report) -> None:
        self._report = report

    def default_python(self) -> str:
        return sys.executable

    async def check(self, python: str) -> dict[str, Any]:
        return await asyncio.to_thread(check, python)

    async def start(self, python: str, folder: str, base: str) -> Process:
        return await start(python, folder, base, self._report)

    async def start_shared(self, python: str, folder: str) -> Process:
        """A second process of a launched app's run folder, at the root, for Share… (SHARED_FLAGS)."""
        return await start(python, folder, "", self._report, shared=True)

    async def install(self, python: str, packages: list[str]) -> tuple[int | None, str]:
        return await install(python, packages)
