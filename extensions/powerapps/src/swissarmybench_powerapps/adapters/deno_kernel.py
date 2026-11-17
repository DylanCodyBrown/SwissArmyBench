"""Deno's Jupyter kernel (`deno jupyter --kernel --conn <file>`), driven with jupyter_client as the base's
IPython kernels are (server/kernels.py): one per data notebook, started on its first TypeScript or SQL
run, in the notebook's folder, ended with the notebook, the server or Restart.

Deno's kernel runs its code with every permission (Deno's documentation, 2026-08-26: "a temporary
limitation"): the same trust as a Python kernel, the user's own code on their own computer. Its sockets
listen on 127.0.0.1 with every message signed by the connection file's key (Deno's kernel takes no local
file sockets: 2.9.6 refuses an ipc address).

`execute` yields nbformat's output records as they arrive, then {"done": {...}}; one run at a time.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

import zmq
from jupyter_client.kernelspec import KernelSpec
from jupyter_client.manager import AsyncKernelManager

START_SECONDS = 90.0  # the first start fetches DuckDB's Node package (npm:), a few seconds more
POLL_SECONDS = 0.5
ASK_SECONDS = 8.0


class DenoKernelError(RuntimeError):
    """A kernel that could not start or run (said plainly)."""


def _record(kind: str, content: dict[str, Any]) -> dict[str, Any] | None:
    if kind == "stream":
        return {
            "output_type": "stream",
            "name": content.get("name", "stdout"),
            "text": content.get("text", ""),
        }
    if kind in ("execute_result", "display_data"):
        record: dict[str, Any] = {
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
    if kind == "clear_output":
        return {"clear": True, "wait": bool(content.get("wait"))}
    return None


class DenoKernel:
    def __init__(self, manager: AsyncKernelManager, deno: str, sockets: str | None) -> None:
        self.manager = manager
        self.deno = deno
        self._sockets = sockets
        self.client = self._client()
        self._lock = asyncio.Lock()
        self._shell = asyncio.Lock()
        self._generation = 0

    def _client(self) -> Any:
        client = self.manager.client()
        client.context.setsockopt(zmq.RCVHWM, 0)  # no limit on messages waiting (the base's lesson)
        return client

    async def ready(self, prelude: str) -> None:
        self.client.start_channels()
        try:
            await self.client.wait_for_ready(timeout=START_SECONDS)
        except RuntimeError as error:
            raise DenoKernelError(f"Deno's kernel did not start: {error}") from None
        failed: list[str] = []
        async for item in self.execute(prelude, silent=True):
            if item.get("output_type") == "error":
                failed.append(f"{item.get('ename')}: {item.get('evalue')}")
        if failed:
            raise DenoKernelError("The notebook's DuckDB did not start in Deno's kernel: " + failed[0])

    def busy(self) -> bool:
        return self._lock.locked()

    async def execute(self, code: str, silent: bool = False) -> AsyncIterator[dict[str, Any]]:
        generation = self._generation
        async with self._lock:
            msg_id = self.client.execute(code, silent=silent, store_history=not silent, allow_stdin=False)
            count: int | None = None
            ok = True
            while True:
                if self._generation != generation:
                    yield {"done": {"ok": False, "restarted": True, "execution_count": count}}
                    return
                try:
                    msg = await self.client.get_iopub_msg(timeout=POLL_SECONDS)
                except asyncio.CancelledError:
                    if self._generation == generation:
                        raise
                    yield {"done": {"ok": False, "restarted": True, "execution_count": count}}
                    return
                except Exception:  # nothing yet: still alive?
                    if self._generation == generation and not await self.manager.is_alive():
                        yield {"done": {"ok": False, "dead": True, "execution_count": count}}
                        return
                    continue
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                kind, content = msg["msg_type"], msg["content"]
                if kind == "status" and content.get("execution_state") == "idle":
                    break
                if kind == "execute_input":
                    count = content.get("execution_count")
                    continue
                record = _record(kind, content)
                if record is None:
                    continue
                if record.get("output_type") == "error":
                    ok = False
                yield record
            yield {"done": {"ok": ok, "execution_count": count}}

    async def complete(self, code: str, offset: int) -> dict[str, Any]:
        """Deno's own completions at `offset` (nothing while it runs a cell)."""
        async with self._shell:
            msg_id = self.client.complete(code, offset)
            deadline = asyncio.get_running_loop().time() + ASK_SECONDS
            while (left := deadline - asyncio.get_running_loop().time()) > 0:
                try:
                    msg = await self.client.get_shell_msg(timeout=left)
                except Exception:
                    break
                if msg.get("parent_header", {}).get("msg_id") == msg_id:
                    content = msg["content"]
                    return {
                        "matches": list(content.get("matches", []))[:300],
                        "start": content.get("cursor_start", offset),
                        "end": content.get("cursor_end", offset),
                    }
        return {"matches": [], "start": offset, "end": offset}

    async def interrupt(self) -> None:
        await self.manager.interrupt_kernel()

    async def alive(self) -> bool:
        return bool(await self.manager.is_alive())

    async def restart(self, prelude: str) -> None:
        self._generation += 1
        await self.manager.restart_kernel(now=True)
        self.client.stop_channels()
        self.client = self._client()
        await self.ready(prelude)

    async def shutdown(self) -> None:
        self.client.stop_channels()
        try:
            await self.manager.shutdown_kernel(now=True)
        except Exception:  # noqa: S110 (already gone)
            pass
        if self._sockets:
            shutil.rmtree(self._sockets, ignore_errors=True)


async def start(deno: str, folder: str | None, environ: dict[str, str], prelude: str) -> DenoKernel:
    """Deno's kernel in `folder` (the notebook's), its `sab` and DuckDB ready."""
    manager = AsyncKernelManager()
    manager.ip = "127.0.0.1"
    sockets: str | None = None
    manager._kernel_spec = KernelSpec(
        argv=[deno, "jupyter", "--kernel", "--conn", "{connection_file}"],
        display_name="Deno",
        language="typescript",
        env={},
    )
    cwd = folder if folder and os.path.isdir(folder) else os.path.expanduser("~")
    try:
        # DENO_NO_PACKAGE_JSON: the code app's own package.json and node_modules are the app's, not the
        # kernel's; read, Deno would refuse every npm: specifier they do not list (DuckDB's among them).
        quiet = {"NO_COLOR": "1", "DENO_NO_PACKAGE_JSON": "1"}
        await manager.start_kernel(cwd=cwd, env=dict(os.environ) | environ | quiet)
    except Exception as error:
        if sockets:
            shutil.rmtree(sockets, ignore_errors=True)
        raise DenoKernelError(f"Deno's kernel did not start: {error}") from None
    kernel = DenoKernel(manager, deno, sockets)
    try:
        await kernel.ready(prelude)
    except Exception:
        await kernel.shutdown()
        raise
    return kernel


class Launcher:
    """The notebook service's kernels port."""

    async def start(self, deno: str, folder: str | None, environ: dict[str, str], prelude: str) -> DenoKernel:
        return await start(deno, folder, environ, prelude)
