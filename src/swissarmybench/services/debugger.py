"""The Scripts page's debugger (the owner's brief, 2026-11-21): breakpoints (plain, conditional, log points),
Start debugging, step over, into and out, continue, the call stack, each frame's variables and watch
expressions, a debug console evaluating in the frame; for the page and the agent alike.

The kernel's own debugger (ipykernel ships debugpy; no new dependency), spoken to with the Jupyter debug
protocol (server/kernels.py debug, debug_event): initialize and attach once per kernel, the script's text
dumped to the kernel's file for it, the breakpoints set there, configurationDone, then the text runs as a cell
in the document's kernel. A watcher reads the debugger's events while it runs: a stop reads the call stack.
Each change is said with the `debug_state` notice (the page follows; the agent reads `state`). Memory only.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from swissarmybench.domain import debugger as rules
from swissarmybench.services import background
from swissarmybench.services.workspace import Conflict, NotFound, Workspace

_EVENT_POLL = 0.5


class DebugKernel(Protocol):
    def execute(
        self, code: str, silent: bool = False, stdin: bool = True
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def debug(self, command: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def debug_event(self, timeout: float) -> dict[str, Any] | None: ...

    async def interrupt(self) -> None: ...

    def idle(self) -> bool: ...


def _body(reply: dict[str, Any], what: str) -> dict[str, Any]:
    if not reply.get("success", False):
        raise rules.DebugError(f"The debugger could not {what}: {reply.get('message') or 'no reason given'}.")
    return dict(reply.get("body") or {})


class Debugger:
    def __init__(
        self,
        ws: Workspace,
        kernel_of: Callable[[str], DebugKernel | None],
        kernel_for: Callable[[str], str | None],
        document_of: Callable[[str], str | None],
    ) -> None:
        self.ws = ws
        self._kernel_of = kernel_of  # a running kernel by its id (services/workbench.py)
        self._kernel_for = kernel_for  # the kernel a document's own (the agent names the document)
        self._document_of = document_of
        self._sessions: dict[str, rules.Session] = {}
        self._attached: set[str] = set()
        self._tasks: dict[str, list[asyncio.Task[Any]]] = {}

    # ===== which kernel =====

    def _which(self, body: Any) -> tuple[str, DebugKernel]:
        body = body if isinstance(body, dict) else {}
        kernel_id = body.get("kernel")
        if not isinstance(kernel_id, str) and isinstance(body.get("document"), str):
            kernel_id = self._kernel_for(body["document"])
        if not isinstance(kernel_id, str) or not kernel_id:
            raise NotFound(
                "Name the script's kernel (or its document, with its kernel running): run it once first."
            )
        kernel = self._kernel_of(kernel_id)
        if kernel is None:
            raise NotFound("That kernel is not running: run the script once (or open it) first.")
        return kernel_id, kernel

    def _session(self, kernel_id: str) -> rules.Session:
        return self._sessions.setdefault(kernel_id, rules.Session(kernel_id, self._document_of(kernel_id)))

    async def _said(self, session: rules.Session) -> dict[str, Any]:
        state = session.to_json()
        await self.ws.live.broadcast(
            {"type": "debug_state"} | {k: v for k, v in state.items() if k != "output"}
        )
        return state

    # ===== breakpoints, start =====

    def state(self, body: Any) -> dict[str, Any]:
        kernel_id, _ = self._which(body)
        return self._session(kernel_id).to_json()

    async def breakpoints(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{kernel | document, breakpoints}: the script's breakpoints; set in the kernel at once while it is
        being debugged (its file the dumped one)."""
        kernel_id, kernel = self._which(body)
        session = self._session(kernel_id)
        session.breakpoints = rules.breakpoints_of(body.get("breakpoints"))
        if session.source and session.state in ("running", "paused"):
            await self._set_breakpoints(kernel, session)
        self.ws.audit.write(who, "debug_breakpoints", session.document, count=len(session.breakpoints))
        return await self._said(session)

    async def _set_breakpoints(self, kernel: DebugKernel, session: rules.Session) -> None:
        arguments = {
            "source": {"path": session.source},
            "breakpoints": [b.protocol() for b in session.breakpoints],
            "sourceModified": False,
        }
        _body(await kernel.debug("setBreakpoints", arguments), "set the breakpoints")

    async def start(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{kernel | document, code, breakpoints?}: debug the script: its text runs in its kernel under the
        debugger, stopping at a breakpoint (a log point prints instead). Its outputs are the session's."""
        kernel_id, kernel = self._which(body)
        code = body.get("code") if isinstance(body, dict) else None
        if not isinstance(code, str) or not code.strip():
            raise rules.DebugError("Send the script's text: code.")
        session = self._session(kernel_id)
        if session.state in ("running", "paused"):
            raise Conflict("It is being debugged already: continue, or stop it first.")
        if not kernel.idle():
            raise Conflict("The script's kernel is busy: wait for its run, or interrupt it.")
        if "breakpoints" in body:
            session.breakpoints = rules.breakpoints_of(body.get("breakpoints"))
        if isinstance(body.get("document"), str):
            session.document = body["document"]
        if kernel_id not in self._attached:
            _body(await kernel.debug("initialize", rules.INITIALIZE), "start")
            _body(await kernel.debug("attach"), "attach to the kernel")
            self._attached.add(kernel_id)
            first = True
        else:
            first = False
        session.source = str(
            _body(await kernel.debug("dumpCell", {"code": code}), "read the script")["sourcePath"]
        )
        await self._set_breakpoints(kernel, session)
        if first:
            _body(await kernel.debug("configurationDone"), "start")
        session.state, session.frames, session.reason = "running", [], ""
        session.output, session.ok, session.error = "", None, ""
        self._tasks[kernel_id] = [
            background.keep(self._run(kernel, session, code), "a debug run"),
            background.keep(self._watch(kernel, session), "a debug run's events"),
        ]
        self.ws.audit.write(who, "debug_start", session.document, breakpoints=len(session.breakpoints))
        return await self._said(session)

    async def _run(self, kernel: DebugKernel, session: rules.Session, code: str) -> None:
        try:
            async for item in kernel.execute(code, stdin=False):
                if item.get("output_type") == "stream":
                    session.heard(str(item.get("text") or ""))
                elif item.get("output_type") == "error":
                    session.error = f"{item.get('ename')}: {item.get('evalue')}"
                    session.heard(session.error + "\n")
                elif "done" in item:
                    session.ok = bool(item["done"].get("ok"))
        finally:
            session.state, session.frames, session.thread = "ended", [], None
            await self._said(session)

    async def _watch(self, kernel: DebugKernel, session: rules.Session) -> None:
        while session.state != "ended":
            event = await kernel.debug_event(_EVENT_POLL)
            if event is None:
                continue
            kind, body = event.get("event"), event.get("body") or {}
            if kind == "stopped":
                session.thread = int(body.get("threadId") or 1)
                session.reason = str(body.get("reason") or "")
                stack = _body(
                    await kernel.debug("stackTrace", {"threadId": session.thread}), "read the stack"
                )
                session.frames = rules.frames_of(
                    stack.get("stackFrames") or [], session.source, session.document
                )
                session.state = "paused"
                await self._said(session)
            elif kind == "continued" and session.state == "paused":
                session.state, session.frames = "running", []
                await self._said(session)
            elif kind == "output" and body.get("category") in ("stdout", "console", "stderr"):
                session.heard(str(body.get("output") or ""))  # a log point's line
                await self._said(session)

    # ===== paused: steps, frames, variables, the debug console =====

    def _paused(self, body: Any) -> tuple[DebugKernel, rules.Session]:
        kernel_id, kernel = self._which(body)
        session = self._session(kernel_id)
        if session.state != "paused" or session.thread is None:
            raise Conflict("Not paused: it stops at a breakpoint first.")
        return kernel, session

    async def step(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{kernel | document, action}: over, into, out or continue; the next stop is said by debug_state."""
        kernel, session = self._paused(body)
        command = rules.step_command(body.get("action"))
        # Running from now: the run may end before the step's own answer comes (then it says ended).
        session.state, session.frames = "running", []
        try:
            _body(await kernel.debug(command, {"threadId": session.thread}), "step")
        except Exception:
            if session.state == "running":
                session.state = "paused"
            raise
        self.ws.audit.write(who, "debug_step", session.document, step=str(body.get("action")))
        return await self._said(session)

    async def variables(self, body: Any) -> dict[str, Any]:
        """{kernel | document, frame | reference}: a frame's scopes and their variables (Locals first), or one
        variable's own (its `reference`, to unfold it)."""
        kernel, session = self._paused(body)
        reference = body.get("reference")
        if isinstance(reference, int) and reference > 0:
            found = _body(await kernel.debug("variables", {"variablesReference": reference}), "read it")
            return {"variables": rules.variables_of(found.get("variables") or [])}
        frame = (
            body.get("frame") if isinstance(body.get("frame"), int) else (session.frames or [{}])[0].get("id")
        )
        if frame is None:
            raise rules.DebugError("Name the frame (its id from the call stack).")
        scopes = _body(await kernel.debug("scopes", {"frameId": frame}), "read the frame").get("scopes") or []
        out = []
        for scope in scopes[:3]:
            found = _body(
                await kernel.debug("variables", {"variablesReference": scope["variablesReference"]}),
                "read it",
            )
            out.append(
                {
                    "scope": str(scope.get("name")),
                    "variables": rules.variables_of(found.get("variables") or []),
                }
            )
        return {"frame": frame, "scopes": out}

    async def evaluate(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{kernel | document, expression, frame?}: the debug console and the watch expressions: evaluated in
        the frame (the top one by default)."""
        kernel, session = self._paused(body)
        expression = body.get("expression")
        if not isinstance(expression, str) or not expression.strip() or len(expression) > rules.MAX_TEXT * 4:
            raise rules.DebugError("Send the expression (one line of Python).")
        frame = (
            body.get("frame") if isinstance(body.get("frame"), int) else (session.frames or [{}])[0].get("id")
        )
        reply = await kernel.debug(
            "evaluate", {"expression": expression, "frameId": frame, "context": "repl"}
        )
        if not reply.get("success", False):
            return {"expression": expression, "error": str(reply.get("message") or "It did not evaluate.")}
        found = dict(reply.get("body") or {})
        self.ws.audit.write(who, "debug_evaluate", session.document)
        return {
            "expression": expression,
            "value": str(found.get("result") or ""),
            "type": str(found.get("type") or ""),
            "reference": int(found.get("variablesReference") or 0),
        }

    async def stop(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{kernel | document}: stop debugging: no more breakpoints, the run let go and interrupted."""
        kernel_id, kernel = self._which(body)
        session = self._session(kernel_id)
        if session.state not in ("running", "paused"):
            return session.to_json()
        kept = session.breakpoints
        session.breakpoints = []
        with contextlib.suppress(rules.DebugError, Exception):
            await self._set_breakpoints(kernel, session)
            if session.state == "paused" and session.thread is not None:
                await kernel.debug("continue", {"threadId": session.thread})
        session.breakpoints = kept
        await kernel.interrupt()
        self.ws.audit.write(who, "debug_stop", session.document)
        for _ in range(40):  # the run ends (interrupted): said by _run
            if session.state == "ended":
                break
            await asyncio.sleep(0.1)
        return session.to_json()
