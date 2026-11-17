"""IPython kernels for the Workbench (jupyter_client, approved 2026-11-13): one per open notebook or script,
started on the user's first Run, in the Python they chose. Each kernel runs as its own process on this
computer; jupyter_client tells it this server's process id, so it ends when the server does.

`execute` yields the run's outputs as they arrive, as nbformat's own output records (stream,
execute_result, display_data, error), then a last {"done": ...}. One run at a time per kernel: a second
waits for the first (as Jupyter queues cells).
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import zmq
from jupyter_client.kernelspec import KernelSpec
from jupyter_client.manager import AsyncKernelManager

_START_SECONDS: float = 60.0
# How long a completion or hover waits: the first on a big library (pandas) can take 4 s.
_ASK_SECONDS: float = 8.0
_MAX_MATCHES: int = 300
_MAX_HELP: int = 6_000
_IDLE_POLL_SECONDS: float = 0.5
# Run quietly once a kernel is ready: the package (sab.*, the %%sql cells, tables as grids) when that
# Python has it. A Python without it still runs code; the Workbench says how to add it. `sag` is its old
# alias (before the rename to Swiss Army Bench), kept for one release so an old notebook's cells still run.
_SETUP = (
    "try:\n"
    "    import swissarmybench as sab\n"
    "    sag = sab\n"
    "    from swissarmybench.server.kernel_setup import setup as _sab_setup\n"
    "\n"
    "    _sab_setup()\n"
    "    del _sab_setup\n"
    "except ImportError:\n"
    "    pass\n"
)


class KernelError(ValueError):
    """A kernel that cannot start or run (the message says why and what to do)."""


def check_python(python: str) -> dict[str, Any]:
    """Whether a Python can run a kernel: its version, and whether it has ipykernel and swissarmybench."""
    try:
        path = Path(python).expanduser()
        there = path.is_file()
    except OSError:  # a name too long for this computer
        there = False
    if not there:
        raise KernelError(f"{python[:200]} is not a Python on this computer.")
    probe = (
        "import sys, importlib.util as u;"
        "print(sys.version.split()[0]);"
        "print(bool(u.find_spec('ipykernel')));"
        "print(bool(u.find_spec('swissarmybench')))"
    )
    try:
        done = subprocess.run(  # noqa: S603 (a Python the user chose, asked three fixed questions)
            [str(path), "-c", probe], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise KernelError(f"{python} did not answer: {error}") from None
    lines = done.stdout.split()
    if done.returncode != 0 or len(lines) != 3:
        raise KernelError(f"{python} is not a Python that runs: {done.stderr.strip()[-300:]}")
    return {
        "python": str(path),
        "version": lines[0],
        "ipykernel": lines[1] == "True",
        "swissarmybench": lines[2] == "True",
    }


def candidates(folders: list[str]) -> list[str]:
    """Pythons worth offering: this server's own, then a project's .venv beside recent files."""
    found = [sys.executable]
    for folder in folders:
        for parent in [Path(folder), *Path(folder).parents][:4]:
            for rel in ("Scripts/python.exe", "bin/python"):
                candidate = parent / ".venv" / rel
                if candidate.is_file() and str(candidate) not in found:
                    found.append(str(candidate))
    return found[:12]


def _client(manager: AsyncKernelManager) -> Any:
    """The manager's client, with no limit on the kernel's messages waiting to be read here.
    ZeroMQ keeps 1,000 by default; past that (and the 1,000 the kernel's side keeps, and what a
    local socket holds, which is little) the kernel drops what it prints, without a word. A script
    printing 6,000 lines while this computer was busy lost lines from the middle, and the message
    that ends the run, so the run never ended (found 2026-11-15, the whole suite under load)."""
    client = manager.client()
    client.context.setsockopt(zmq.RCVHWM, 0)  # for the sockets start_channels() makes
    return client


# The beta log's hook (services/beta_log.py): (event, exit code, seconds, reason) for a kernel's start,
# restart, crash and end.
Report = Callable[[str, int | None, float | None, str], None]


def _no_report(event: str, code: int | None, seconds: float | None, reason: str = "") -> None:
    return None


class Kernel:
    def __init__(
        self,
        manager: AsyncKernelManager,
        python: str,
        sockets: str | None = None,
        report: Report = _no_report,
    ) -> None:
        self.manager = manager
        self._report = report
        self._started = time.monotonic()
        self._ended = False
        self.client = _client(manager)
        self.python = python
        self._sockets = sockets  # the private folder of its local sockets, removed when it ends
        self._lock = asyncio.Lock()
        self._shell = asyncio.Lock()  # one completion or hover at a time reads the shell channel's replies
        self._interrupts = 0  # Interrupt counts up: a run queued before it is cancelled
        self._generation = 0  # Restart counts up: a run under way ends
        self._runs: list[str] = []  # recent runs' ids: their late output still comes through
        self._input: asyncio.Queue[str] = asyncio.Queue()
        self._warm: asyncio.Task[Any] | None = None

    async def ready(self) -> None:
        # The client has no limit on messages waiting to be read (_client): set for new and restarted kernels.
        self.client.start_channels()
        try:
            await self.client.wait_for_ready(timeout=_START_SECONDS)
        except RuntimeError as error:
            raise KernelError(f"The kernel did not start: {error}") from None
        async for _ in self.execute(_SETUP, silent=True):
            pass
        # The first completion loads Jedi (about 3 seconds): do it now, so the user's first Tab is quick.
        self._warm = asyncio.create_task(self.complete("im", 2))

    def _record(self, kind: str, content: dict[str, Any]) -> dict[str, Any] | None:
        """An iopub message as nbformat's output record (None: not an output)."""
        if kind == "stream":
            return {"output_type": "stream", "name": content["name"], "text": content["text"]}
        if kind in ("execute_result", "display_data"):
            record = {
                "output_type": kind,
                "data": content.get("data", {}),
                "metadata": content.get("metadata", {}),
            }
            if kind == "execute_result":
                record["execution_count"] = content.get("execution_count")
            return record
        if kind == "error":
            return {
                "output_type": "error",
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback", []),
            }
        if kind == "clear_output":  # wait: clear when the next output comes (no flicker)
            return {"clear": True, "wait": bool(content.get("wait"))}
        return None

    async def execute(
        self, code: str, silent: bool = False, stdin: bool = True
    ) -> AsyncIterator[dict[str, Any]]:
        """Run code; its outputs as they arrive, then {"done": ...}. A run queued behind another is
        cancelled by Interrupt; a Restart ends the run it interrupts; `input()` asks the page
        ({"input_request": ...}, answered by `answer_input`); output a thread prints after its own run
        ended comes through the next run, marked late."""
        ticket, generation = self._interrupts, self._generation
        async with self._lock:
            if self._interrupts != ticket:  # interrupted while it waited its turn
                yield {"done": {"ok": False, "cancelled": True, "execution_count": None}}
                return
            msg_id = self.client.execute(
                code,
                silent=silent,
                store_history=not silent,
                allow_stdin=stdin and not silent,
                stop_on_error=False,
            )
            self._runs.append(msg_id)
            del self._runs[:-50]
            count: int | None = None
            ok = True
            while True:
                if self._generation != generation:  # restarted under it
                    yield {"done": {"ok": False, "restarted": True, "execution_count": count}}
                    return
                try:
                    msg = await self.client.get_iopub_msg(timeout=_IDLE_POLL_SECONDS)
                except asyncio.CancelledError:
                    # A restart closed the channels this was reading (the wait is cancelled, not
                    # failed): the run ends saying so, as it does when it sees the restart first.
                    if self._generation == generation:
                        raise
                    yield {"done": {"ok": False, "restarted": True, "execution_count": count}}
                    return
                except Exception:  # queue.Empty: nothing yet; is it asking for input, or gone?
                    if stdin and not silent and (asked := await self._input_request()) is not None:
                        yield {"input_request": asked}
                        value = await self._wait_for_input(generation)
                        if value is None:
                            continue
                        self.client.input(value)
                        continue
                    if self._generation == generation and not await self.manager.is_alive():
                        self._gone("crash")
                        yield {"done": {"ok": False, "dead": True, "execution_count": count}}
                        return
                    continue
                parent = msg.get("parent_header", {}).get("msg_id")
                kind, content = msg["msg_type"], msg["content"]
                if parent != msg_id:
                    # A thread of an earlier run still printing: hand it on rather than lose it.
                    if (
                        parent in self._runs
                        and (record := self._record(kind, content))
                        and "clear" not in record
                    ):
                        yield record | {"late": True}
                    continue
                if kind == "status" and content.get("execution_state") == "idle":
                    break
                if kind == "execute_input":
                    count = content.get("execution_count")
                    continue
                record = self._record(kind, content)
                if record is None:
                    continue
                if record.get("output_type") == "error":
                    ok = False
                yield record
            if not ok and not silent:
                # The error taken apart for the panel, read before another run can change what it saw.
                detail = await self.error_detail()
                if detail:
                    yield {"error_detail": detail}
            yield {"done": {"ok": ok, "execution_count": count}}

    async def _input_request(self) -> dict[str, Any] | None:
        """The kernel asking for a line of input (input(), getpass, pdb), if it is."""
        try:
            msg = await self.client.get_stdin_msg(timeout=0.01)
        except Exception:  # queue.Empty
            return None
        if msg.get("msg_type") != "input_request":
            return None
        content = msg["content"]
        return {"prompt": str(content.get("prompt", "")), "password": bool(content.get("password"))}

    async def _wait_for_input(self, generation: int) -> str | None:
        """The page's answer; None when the run was interrupted or restarted meanwhile."""
        while True:
            try:
                return await asyncio.wait_for(self._input.get(), timeout=_IDLE_POLL_SECONDS)
            except TimeoutError:
                if self._generation != generation or not await self.manager.is_alive():
                    return None

    def answer_input(self, value: str) -> None:
        """The line the user typed for input(), getpass or pdb."""
        self._input.put_nowait(value)

    async def _ask(self, send: Any) -> dict[str, Any] | None:
        """Send one request (`send()` gives its id) and wait for the shell channel's reply to it (a run's
        own replies are passed over)."""
        async with self._shell:
            return await self._reply(send())

    async def _reply(self, msg_id: str) -> dict[str, Any] | None:
        deadline = asyncio.get_running_loop().time() + _ASK_SECONDS
        while (left := deadline - asyncio.get_running_loop().time()) > 0:
            try:
                msg = await self.client.get_shell_msg(timeout=left)
            except Exception:  # queue.Empty: no answer in time (the kernel is busy running code)
                return None
            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                return dict(msg["content"])
        return None

    async def complete(self, code: str, offset: int) -> dict[str, Any]:
        """What the kernel offers at `offset` (IPython's completer, with Jedi): the matches, the span they
        replace, and each one's kind when the kernel says. Nothing while it is busy running."""
        content = await self._ask(lambda: self.client.complete(code, offset))
        if not content or content.get("status") != "ok":
            return {"matches": [], "start": offset, "end": offset, "types": {}}
        typed = content.get("metadata", {}).get("_jupyter_types_experimental", [])
        return {
            "matches": content.get("matches", [])[:_MAX_MATCHES],
            "start": content.get("cursor_start", offset),
            "end": content.get("cursor_end", offset),
            "types": {t.get("text"): t.get("type") for t in typed if isinstance(t, dict)},
        }

    async def inspect(self, code: str, offset: int) -> str:
        """The signature and help of the name at `offset`, as plain text (empty when there is none)."""
        content = await self._ask(lambda: self.client.inspect(code, offset, detail_level=0))
        if not content or not content.get("found"):
            return ""
        text = str(content.get("data", {}).get("text/plain", ""))
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)[:_MAX_HELP]  # no colour codes in a hover

    async def evaluate(self, expression: str) -> Any:
        """A Python expression's value, worked out in the kernel without printing or entering the history
        (a user expression on an empty run). Its repr, read back as a literal. None when the kernel is
        busy; KernelError when the expression fails."""
        content = await self._ask(
            lambda: self.client.execute(
                "", silent=True, store_history=False, user_expressions={"v": expression}, allow_stdin=False
            )
        )
        if content is None:
            return None
        answer = content.get("user_expressions", {}).get("v", {})
        if answer.get("status") != "ok":
            raise KernelError(f"{answer.get('ename', 'Error')}: {answer.get('evalue', '')}")
        return ast.literal_eval(answer.get("data", {}).get("text/plain", "None"))

    async def variables(self, env_names: list[str]) -> dict[str, Any] | None:
        """The Variables overlay: the user's variables, the connections, the environment's names
        (client/kernel_variables.py). None while the kernel is busy running code."""
        text = await self.evaluate(
            "__import__('swissarmybench.client.kernel_variables', fromlist=['snapshot'])"
            f".snapshot({sorted(env_names)!r})"
        )
        return None if text is None else dict(json.loads(text))

    async def html_marks(self, names: list[str]) -> dict[str, Any] | None:
        """A mark of what each name would draw in an HTML cell now (client/html_cells.py). None while
        the kernel is busy running code, or in a Python without the package."""
        try:
            text = await self.evaluate(
                f"__import__('swissarmybench.client.html_cells', fromlist=['marks']).marks({sorted(names)!r})"
            )
        except KernelError:
            return None
        return dict(json.loads(text)) if isinstance(text, str) else None

    async def lineage_values(self, names: list[str]) -> dict[str, Any] | None:
        """Each name's value, summarised for the lineage overlay (client/lineage_values.py): a table's
        shape and first rows, a value as itself. None while the kernel is busy, or in a Python without
        the package."""
        try:
            text = await self.evaluate(
                "__import__('swissarmybench.client.lineage_values', fromlist=['summaries'])"
                f".summaries({sorted(names)!r})"
            )
        except KernelError:
            return None
        found = json.loads(text) if isinstance(text, str) else None
        return found if isinstance(found, dict) else None

    async def error_detail(self) -> dict[str, Any] | None:
        """The last error, taken apart (client/kernel_errors.py): its chain, frames, the failing
        expression's values. None when the kernel cannot say (busy, or a Python without the helper)."""
        try:
            text = await self.evaluate(
                "__import__('swissarmybench.client.kernel_errors', fromlist=['detail']).detail()"
            )
        except KernelError:
            return None
        found = json.loads(text) if isinstance(text, str) else None
        return found if isinstance(found, dict) and found.get("chain") else None

    async def grid(self, expression: str, name: str) -> str | None:
        """Open a table (a variable, or a cell's result Out[n]) as grid `name` (sent from the kernel);
        its address. A variable is kept current from then on, and has its own read-only cell
        (client/table_cells.py); a result is sent as it is."""
        if expression == name:
            helper = "__import__('swissarmybench.client.table_cells', fromlist=['open_grid'])"
            url = await self.evaluate(f"{helper}.open_grid({name!r})")
        else:
            url = await self.evaluate(f"__import__('swissarmybench').push({expression}, name={name!r})")
        return None if url is None else str(url)

    async def structure(self, name: str) -> Any:
        """A variable opened on the Structures page (sent from the kernel): {"id", "name"}, or None."""
        return await self.evaluate(f"__import__('swissarmybench').show_structure({name}, name={name!r})")

    async def interrupt(self) -> None:
        self._interrupts += 1
        self._input.put_nowait("")  # a run waiting at input() goes on (and is interrupted)
        await self.manager.interrupt_kernel()

    async def alive(self) -> bool:
        alive = bool(await self.manager.is_alive())
        if not alive:
            self._gone("crash")
        return alive

    def _exit_code(self) -> int | None:
        process = getattr(getattr(self.manager, "provisioner", None), "process", None)
        code = getattr(process, "returncode", None)
        return code if isinstance(code, int) else None

    def _gone(self, event: str) -> None:
        """Say once how the kernel ended: a crash (it died by itself) or an end (it was stopped)."""
        if not self._ended:
            self._ended = True
            self._report(event, self._exit_code(), time.monotonic() - self._started, "")

    async def is_complete(self, code: str) -> dict[str, Any]:
        """Whether code is a whole statement yet (the console's Enter), and the indent to go on with."""
        content = await self._ask(lambda: self.client.is_complete(code))
        if not content:
            return {"status": "unknown", "indent": ""}
        return {"status": content.get("status", "unknown"), "indent": content.get("indent", "")}

    async def restart(self) -> None:
        self._generation += 1
        self._interrupts += 1
        await self.manager.restart_kernel(now=True)
        self._report("restart", None, time.monotonic() - self._started, "")
        self.client.stop_channels()
        self.client = _client(self.manager)
        await self.ready()

    async def shutdown(self) -> None:
        self.client.stop_channels()
        try:
            await self.manager.shutdown_kernel(now=True)
        except Exception:  # noqa: S110 (already gone)
            pass
        self._gone("end")
        if self._sockets:
            shutil.rmtree(self._sockets, ignore_errors=True)


async def start(
    python: str, folder: str | None, environ: dict[str, str], report: Report = _no_report
) -> Kernel:
    """A kernel in `python`, its working folder `folder` (the document's), ready to run."""
    began = time.monotonic()
    found = check_python(python)
    if not found["ipykernel"]:
        raise KernelError(
            f"{python} has no ipykernel, which runs the Workbench's code. Install it there: "
            f"uv pip install --python {python} ipykernel"
        )
    manager = AsyncKernelManager()
    sockets: str | None = None
    if sys.platform != "win32":
        # Local files (Unix sockets), not network ports: only this user reaches the kernel. They are
        # named by a full path in a private folder (a relative name would be read from the kernel's
        # working folder, the document's, and the server's own: two places). Windows has no such
        # transport; there its ports listen on 127.0.0.1 and every message is signed.
        sockets = tempfile.mkdtemp(prefix="swissarmybench-kernel-")
        manager.transport = "ipc"
        manager.ip = os.path.join(sockets, "kernel")
    manager._kernel_spec = KernelSpec(  # one kernel's command: this Python, no kernelspec file needed
        argv=[found["python"], "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        display_name="Python",
        language="python",
        env={},
    )
    cwd = folder if folder and os.path.isdir(folder) else str(Path.home())
    if not found["swissarmybench"]:
        # This Python lacks the package: lend it a copy (the plain client) on its import path.
        from swissarmybench.server.environments import client_path

        environ = environ | {
            "PYTHONPATH": os.pathsep.join(p for p in (client_path(), environ.get("PYTHONPATH", "")) if p)
        }
    try:
        await manager.start_kernel(cwd=cwd, env=environ)
    except Exception as error:
        if sockets:
            shutil.rmtree(sockets, ignore_errors=True)
        report("failed", None, time.monotonic() - began, type(error).__name__)
        raise KernelError(f"The kernel did not start: {error}") from None
    kernel = Kernel(manager, found["python"], sockets, report)
    try:
        await kernel.ready()
    except Exception as error:
        kernel._ended = True  # said here, not again by shutdown
        report("failed", kernel._exit_code(), time.monotonic() - began, type(error).__name__)
        await kernel.shutdown()
        raise
    report("start", None, time.monotonic() - began, "")
    return kernel


class Launcher:
    """The Workbench's kernels port (services/workbench.py): kernels, and the environments they run in.
    `report` hears each kernel's start, restart, crash and end (the beta log)."""

    def __init__(self, report: Report = _no_report) -> None:
        self._report = report

    def create_environment(
        self, folder: str, version: str | None, packages: list[str]
    ) -> AsyncIterator[dict[str, Any]]:
        from swissarmybench.server import environments

        return environments.create(folder, version, packages)

    def beside(self, folder: str) -> str | None:
        from swissarmybench.server import environments

        return environments.beside(folder)

    async def start(self, python: str, folder: str | None, environ: dict[str, str]) -> Kernel:
        return await start(python, folder, environ, self._report)

    def check_python(self, python: str) -> dict[str, Any]:
        return check_python(python)

    def candidates(self, folders: list[str]) -> list[str]:
        return candidates(folders)
