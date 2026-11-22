"""The Copilot Language Server as a child process, spoken to over its stdin and stdout (domain/lsp.py's
framing), and the tools around it: Node.js and npm found on the PATH, the pinned package installed with
`npm install --prefix` into the state folder's copilot/.

Its stderr and its `window/logMessage` notifications are dropped, never logged: the server's own logs are
its business and may name its account. The token the sign-in gets is the server's, kept in its own folder
(GitHub's apps.json); nothing here reads or holds it.

SWISSARMYBENCH_COPILOT_STANDIN names a Python script that stands in for the server (tests/copilot_standin.py):
it is run with this Python and counts as installed. The real server is never run by the tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import os
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from swissarmybench_copilot.domain import lsp, tools
from swissarmybench_copilot.domain.lsp import LspError, ServerGone

STANDIN = "SWISSARMYBENCH_COPILOT_STANDIN"
OnRequest = Callable[[str, Any], Awaitable[Any]]
OnNotice = Callable[[str, Any], None]


class Connection:
    """One running server: requests with their answers, notifications both ways, the server's own requests
    answered by `on_request`."""

    def __init__(
        self, process: asyncio.subprocess.Process, on_request: OnRequest, on_notice: OnNotice
    ) -> None:
        self._process = process
        self._on_request = on_request
        self._on_notice = on_notice
        self._ids = itertools.count(1)
        self._waiting: dict[int, asyncio.Future[Any]] = {}
        self._reader = asyncio.create_task(self._read())
        self._write_lock = asyncio.Lock()
        self._answering: set[asyncio.Task[None]] = set()  # the server's own requests being answered

    @property
    def running(self) -> bool:
        return self._process.returncode is None and not self._reader.done()

    async def _send(self, message: dict[str, Any]) -> None:
        stdin = self._process.stdin
        if stdin is None or not self.running:
            raise ServerGone("The language server is not running.")
        async with self._write_lock:
            try:
                stdin.write(lsp.encode(message))
                await stdin.drain()
            except (ConnectionError, RuntimeError) as error:
                raise ServerGone("The language server stopped.") from error

    def next_id(self) -> int:
        return next(self._ids)

    async def request(self, method: str, params: Any, timeout: float = 30.0, ident: int | None = None) -> Any:
        ident = self.next_id() if ident is None else ident
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._waiting[ident] = future
        try:
            await self._send(lsp.request(ident, method, params))
            return await asyncio.wait_for(future, timeout)
        finally:
            self._waiting.pop(ident, None)

    async def notify(self, method: str, params: Any) -> None:
        await self._send(lsp.notification(method, params))

    async def cancel(self, ident: int) -> None:
        if ident in self._waiting:
            await self.notify(lsp.CANCEL, {"id": ident})

    async def _read(self) -> None:
        reader = lsp.Reader()
        stdout = self._process.stdout
        if stdout is None:
            return
        try:
            while True:
                data = await stdout.read(65536)
                if not data:
                    break
                for message in reader.feed(data):
                    self._take(message)
        except lsp.FramingError:
            pass  # not the protocol: the connection ends
        finally:
            for future in self._waiting.values():
                if not future.done():
                    future.set_exception(ServerGone("The language server stopped."))

    def _take(self, message: dict[str, Any]) -> None:
        kind = lsp.kind_of(message)
        if kind == "response":
            future = self._waiting.get(message.get("id"))  # type: ignore[arg-type]
            if future is None or future.done():
                return
            failed = message.get("error")
            if isinstance(failed, dict):
                future.set_exception(LspError(int(failed.get("code") or 0), str(failed.get("message") or "")))
            else:
                future.set_result(message.get("result"))
        elif kind == "request":
            task = asyncio.create_task(self._answer(message))
            self._answering.add(task)
            task.add_done_callback(self._answering.discard)
        else:
            with contextlib.suppress(Exception):
                self._on_notice(str(message.get("method")), message.get("params"))

    async def _answer(self, message: dict[str, Any]) -> None:
        ident = message.get("id")
        try:
            result = await self._on_request(str(message.get("method")), message.get("params"))
            answer = lsp.response(ident, result)
        except LookupError:
            answer = lsp.error(ident, lsp.METHOD_NOT_FOUND, "Not handled by this client.")
        with contextlib.suppress(ServerGone):
            await self._send(answer)

    async def close(self) -> None:
        """shutdown, then exit; killed when it does not go within a few seconds."""
        if self.running:
            with contextlib.suppress(Exception):
                await self.request("shutdown", None, timeout=3.0)
                await self.notify("exit", None)
        try:
            await asyncio.wait_for(self._process.wait(), 3.0)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
            with contextlib.suppress(Exception):
                await self._process.wait()
        self._reader.cancel()


class Machine:
    """This computer's side: the tools on the PATH, the install, and the server started."""

    def __init__(self, folder: Path, path: str | None = None) -> None:
        self.folder = folder  # the state folder's copilot/
        self._path = path

    def system(self) -> str:
        return sys.platform

    def which(self, program: str) -> str | None:
        return shutil.which(program, path=self._path or os.environ.get("PATH"))

    def standin(self) -> str | None:
        found = os.environ.get(STANDIN, "").strip()
        return found if found and Path(found).is_file() else None

    def script(self) -> Path:
        return self.folder.joinpath(*tools.SCRIPT)

    def installed(self) -> bool:
        return self.standin() is not None or self.script().is_file()

    async def version(self, program: str) -> str | None:
        found = self.which(program)
        if found is None:
            return None
        try:
            process = await asyncio.create_subprocess_exec(
                found,
                "--version",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(process.communicate(), 20.0)
        except (OSError, TimeoutError):
            return None
        return tools.parse_version(out.decode("utf-8", "replace"))

    async def install(self) -> tuple[int, str]:
        """npm install --prefix <copilot/> the pinned package; (exit code, the last lines it printed)."""
        npm = self.which("npm")
        if npm is None:
            return 127, "npm was not found."
        self.folder.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            *tools.install_argv(npm, str(self.folder)),
            cwd=str(self.folder),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(process.communicate(), 600.0)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            return 124, "npm did not finish within ten minutes."
        lines = out.decode("utf-8", "replace").strip().splitlines()
        return int(process.returncode or 0), "\n".join(lines[-6:])[:1200]

    async def start(self, on_request: OnRequest, on_notice: OnNotice) -> Connection:
        standin = self.standin()
        if standin is not None:
            argv = [sys.executable, "-I", standin, "--stdio"]
        else:
            node = self.which("node")
            if node is None or not self.script().is_file():
                raise ServerGone("The language server is not installed.")
            argv = [node, str(self.script()), "--stdio"]
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.folder) if self.folder.is_dir() else None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return Connection(process, on_request, on_notice)
