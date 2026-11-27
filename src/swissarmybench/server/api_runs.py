"""A project's local sandbox API as a process of its own (`python -I server/api_host.py`, the app's own
Python:
Starlette and uvicorn).

Its environment is made from nothing (domain/local_api.py runner_env): the system's few (PATH, the temporary
folder), an empty home and state folder of its own, and its four SAB_ values; never the server's, so no
connection's variable or secret, no token. 127.0.0.1 on a port the system gives; its first stdout line says
the
port, or API.py's error and line. Ended with the server, Stop, or a restart.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from swissarmybench.domain import local_api as rules
from swissarmybench.server import api_host
from swissarmybench.services import background
from swissarmybench.services.local_api import StartFailed

START_SECONDS = 30.0
OUTPUT_LINES = 200  # the last lines API.py printed, kept for the page's Output
OUTPUT_WIDTH = 2000


class ApiProcess:
    def __init__(
        self,
        process: asyncio.subprocess.Process,
        port: int,
        endpoints: list[dict[str, Any]],
        key: str,
        home: str,
    ) -> None:
        self.process = process
        self.port = port
        self.endpoints = endpoints
        self._key = key
        self._home = home
        # What API.py prints and its process's errors, the last lines (memory only). Both pipes are read to
        # their end: one left unread fills, and the endpoint that prints into it would wait for ever.
        self.lines: deque[str] = deque(maxlen=OUTPUT_LINES)
        self._drains = [
            background.keep(self._read(stream), "a local sandbox API's output")
            for stream in (self.process.stdout, self.process.stderr)
            if stream is not None
        ]

    async def _read(self, stream: asyncio.StreamReader) -> None:
        while True:
            try:
                line = await stream.readline()
            except ValueError:  # a line longer than the reader's limit: its rest is read as the next
                continue
            if not line:
                return
            self.lines.append(line.decode("utf-8", "replace").rstrip()[:OUTPUT_WIDTH])

    def output(self) -> list[str]:
        return list(self.lines)

    def alive(self) -> bool:
        return self.process.returncode is None

    async def stop(self) -> None:
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        for drain in self._drains:
            drain.cancel()
        shutil.rmtree(self._home, ignore_errors=True)

    def _send(
        self, method: str, path: str, query: dict[str, Any], body: bytes | None
    ) -> tuple[int, bytes, dict[str, str]]:
        address = f"http://127.0.0.1:{self.port}{urllib.parse.quote(path, safe='/{}')}"
        if query:
            address += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        request = urllib.request.Request(  # noqa: S310 (127.0.0.1, the API's own port)
            address,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as answer:  # noqa: S310
                return int(answer.status), answer.read(), dict(answer.headers.items())
        except urllib.error.HTTPError as failed:
            return int(failed.code), failed.read(), dict(failed.headers.items())

    async def request(
        self, method: str, path: str, query: dict[str, Any], body: bytes | None
    ) -> tuple[int, bytes, dict[str, str]]:
        return await asyncio.to_thread(self._send, method, path, query, body)

    async def log(self) -> list[dict[str, Any]]:
        status, body, _ = await self.request("GET", "/__sab/log", {}, None)
        return list(json.loads(body).get("log") or []) if status == 200 else []


async def start(file: str, base: str, key: str, data_url: str) -> ApiProcess:
    """The API hosted: its process started and its first line read (StartFailed: API.py's words and line)."""
    home = tempfile.mkdtemp(prefix="sab-api-")
    env = rules.runner_env(
        os.environ,
        {
            "SAB_API_FILE": file,
            "SAB_API_KEY": key,
            "SAB_API_BASE": base,
            "SAB_SANDBOX_DATA": data_url,
        },
        home,
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-u",  # a print shows in the page's Output as it happens (-I takes no PYTHONUNBUFFERED)
        str(Path(api_host.__file__)),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(Path(file).parent),
    )
    try:
        line = await asyncio.wait_for(process.stdout.readline(), START_SECONDS) if process.stdout else b""
    except TimeoutError:
        process.kill()
        shutil.rmtree(home, ignore_errors=True)
        raise StartFailed("The local sandbox API did not start within 30 seconds.") from None
    try:
        said = json.loads(line or b"{}")
    except ValueError:
        said = {}
    if "port" not in said:
        errors = b""
        if process.stderr is not None:
            try:
                errors = await asyncio.wait_for(process.stderr.read(), 5)
            except TimeoutError:
                pass
        await process.wait()
        shutil.rmtree(home, ignore_errors=True)
        words = (
            said.get("error") or errors.decode("utf-8", "replace").strip().splitlines()[-1:] or ["it ended"]
        )
        raise StartFailed(words if isinstance(words, str) else words[0], said.get("line"))
    return ApiProcess(process, int(said["port"]), list(said.get("endpoints") or []), key, home)
