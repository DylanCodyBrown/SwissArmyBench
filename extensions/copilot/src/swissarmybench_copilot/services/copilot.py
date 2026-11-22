"""GitHub Copilot's code completion for the Workbench's editors (the owner, 2026-11-18: "Wanted to GitHub
Copilot repo code completion anyway"; chosen: an extension, off until installed).

One language server for the app, started when it is needed and on; the editors' documents mirrored into it
as they are sent (domain/documents.py), an inline completion asked at the cursor, the shown, accepted and
partly accepted items told back as the README asks.

Nothing is sent while: the language server is not installed, the switch is off, the account is not signed
in, or the open project is marked private (then not even a didOpen: what was open is closed). Telemetry is
off (domain/lsp.py SETTINGS).

The sign-in is the language server's own device flow: signIn gives a code; the page shows it and opens
github.com/login/device on the user's click; then github.copilot.finishDeviceFlow waits for GitHub. The
user's only (the agent gets 403), as is signing out. No token passes through here.

  state(who)          the agent's and the status bar's picture (installed, on, account, private, ready)
  panel(who) / act    the Extensions card's and Settings' panel as data (lines, switches, actions, the code)
  install(who)        npm install of the pinned server (the agent's on Allow)
  toggle(on, who)     the On switch (off: the server stops)
  sign_in / finish / sign_out (the user's)
  complete(body)      ghost text at the cursor; cancel(body); event(body): shown, accepted, partial
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain.packages import MissingPackagesError
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused
from swissarmybench_copilot.domain import lsp, tools
from swissarmybench_copilot.domain.documents import DocumentError, Mirror
from swissarmybench_copilot.domain.lsp import LspError, ServerGone

NAME = "GitHub Copilot"
NOTICE = "inline_completion_changed"
PANEL_NOTICE = "extension_panel_changed"
MAX_ITEMS_KEPT = 60
COMPLETION_SECONDS = 20.0
SIGN_IN_SECONDS = 900.0


class Connection(Protocol):
    """One running language server, as this service uses it (adapters/language_server.py's Connection)."""

    @property
    def running(self) -> bool: ...
    def next_id(self) -> int: ...
    async def request(
        self, method: str, params: Any, timeout: float = 30.0, ident: int | None = None
    ) -> Any: ...
    async def notify(self, method: str, params: Any) -> None: ...
    async def cancel(self, ident: int) -> None: ...
    async def close(self) -> None: ...


class Machine(Protocol):
    def system(self) -> str: ...
    def which(self, program: str) -> str | None: ...
    def installed(self) -> bool: ...
    def standin(self) -> str | None: ...
    async def version(self, program: str) -> str | None: ...
    async def install(self) -> tuple[int, str]: ...
    async def start(self, on_request: Any, on_notice: Any) -> Connection: ...


class Record(Protocol):
    def read(self) -> Any: ...
    def write(self, data: Any) -> None: ...


class Audit(Protocol):
    def write(self, who: str, action: str, dataset: str | None, **detail: Any) -> None: ...


class Notifier(Protocol):
    async def broadcast(self, message: dict[str, Any]) -> None: ...


class Copilot:
    def __init__(
        self,
        *,
        machine: Machine,
        record: Record,
        approvals: Approvals,
        audit: Audit,
        live: Notifier,
        private: Callable[[], bool],
        app_version: str,
        plugin_version: str,
        process_id: int = 0,  # this app's, for the server's initialize (the root hands it in)
    ) -> None:
        self._machine = machine
        self._record = record
        self._approvals = approvals
        self._audit = audit
        self._live = live
        self._private = private
        self._app_version = app_version
        self._plugin_version = plugin_version
        self._process_id = process_id
        self._conn: Connection | None = None
        self._starting = asyncio.Lock()
        self._account: dict[str, Any] | None = None  # what the server last said; None: not asked
        self._device: dict[str, Any] | None = None  # the device flow's code and link, while it waits
        self._finishing: asyncio.Task[None] | None = None
        self._installing = False
        self._said: str | None = None  # the last install's or sign-in's failure, in words
        self._server_status: dict[str, str] = {}
        self._message: str | None = None  # the server's last showMessage(Request) words
        self._mirror = Mirror()
        self._focused: str | None = None
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._item_ids = itertools.count(1)
        self._pending: dict[str, int] = {}  # the page's request id -> the server's request id
        self._tools: dict[str, dict[str, Any]] | None = None

    # ===== what is kept: copilot.json (the switch, the login's name; never a token) =====

    def _kept(self) -> dict[str, Any]:
        said = self._record.read()
        return said if isinstance(said, dict) else {}

    def _keep(self, **change: Any) -> None:
        self._record.write(self._kept() | change)

    @property
    def on(self) -> bool:
        return self._kept().get("on") is True

    def _login(self) -> str | None:
        if self._account is not None:
            return self._account.get("user") if self._account["state"] != "not_signed_in" else None
        login = self._kept().get("login")
        return str(login) if isinstance(login, str) and login else None

    def _account_state(self) -> str:
        if self._account is not None:
            return str(self._account["state"])
        return "signed_in" if self._login() else "not_signed_in"

    # ===== tools =====

    async def tools_state(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        if self._tools is None or refresh:
            system = tools.system_of(self._machine.system())
            found = {}
            for tool in ("node", "npm"):
                path = self._machine.which(tool)
                version = await self._machine.version(tool) if path else None
                found[tool] = tools.tool_state(tool, path, version, system)
            self._tools = found
        return self._tools

    async def _missing(self, action: str) -> dict[str, Any] | None:
        if action == "run" and self._machine.standin() is not None:
            return None
        return tools.missing(action, await self.tools_state(), tools.system_of(self._machine.system()))

    # ===== the picture =====

    def ready(self) -> bool:
        return (
            self._machine.installed()
            and self.on
            and self._account_state() == "signed_in"
            and not self._private()
        )

    def words(self) -> str:
        """The status bar's word: on, off, private, sign in, not installed."""
        if not self._machine.installed():
            return "not installed"
        if not self.on:
            return "off"
        if self._private():
            return "private"
        if self._account_state() == "no_subscription":
            return "no plan"
        if self._account_state() != "signed_in":
            return "sign in"
        return "on"

    async def _look(self) -> None:
        """While on (and installed), the server is asked who is signed in, once."""
        if self._account is None and self.on and self._machine.installed() and not self._private():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._ensure(), 20.0)

    async def state(self, who: str = "user") -> dict[str, Any]:
        await self._look()
        return {
            "name": NAME,
            "installed": True,  # this extension: it answers
            "server_installed": self._machine.installed(),
            "server_version": lsp.PINNED,
            "running": self._conn is not None and self._conn.running,
            "on": self.on,
            "account": {"state": self._account_state(), "user": self._login()},
            "private": self._private(),
            "ready": self.ready(),
            "words": self.words(),
            "signing_in": self._device is not None,
            "telemetry": "off",
        }

    async def inline_status(self) -> dict[str, Any]:
        """The editors' status bar item: the provider's name, on or off, and its word."""
        await self._look()
        return {"name": NAME, "on": self.on, "ready": self.ready(), "words": self.words()}

    # ===== the language server =====

    async def _ensure(self) -> Connection:
        async with self._starting:
            if self._conn is not None and self._conn.running:
                return self._conn
            self._mirror.clear()
            self._focused = None
            missing = await self._missing("run")
            if missing is not None:
                raise MissingPackagesError(missing["missing"])
            try:
                conn = await self._machine.start(self._server_asks, self._server_says)
            except (OSError, ServerGone) as error:
                raise Conflict(f"The language server did not start: {error}") from None
            try:
                await conn.request(
                    "initialize",
                    lsp.initialize_params(self._process_id, self._app_version, self._plugin_version),
                    timeout=60.0,
                )
                await conn.notify("initialized", {})
                await conn.notify("workspace/didChangeConfiguration", lsp.configuration())
                self._conn = conn
                self._account = lsp.account_of(await conn.request(lsp.CHECK_STATUS, {}, timeout=30.0))
            except (LspError, ServerGone, TimeoutError) as error:
                await conn.close()
                self._conn = None
                raise Conflict(f"The language server did not answer: {error}") from None
            self._keep(login=self._login())
            return conn

    async def _server_asks(self, method: str, params: Any) -> Any:
        if method == "workspace/configuration":
            return lsp.configuration_answer(params)
        if method == "window/showDocument":
            # The device page: the page opened it on the user's click (the link the code came with).
            return {"success": True}
        if method == "window/showMessageRequest":
            self._message = _words(params)
            self._notify_soon()
            return None
        if method in (
            "window/workDoneProgress/create",
            "client/registerCapability",
            "client/unregisterCapability",
        ):
            return None
        raise LookupError(method)

    def _server_says(self, method: str, params: Any) -> None:
        if method == "didChangeStatus" and isinstance(params, dict):
            now = {"kind": str(params.get("kind") or ""), "message": str(params.get("message") or "")[:300]}
            if now != self._server_status:
                self._server_status = now
                self._notify_soon()
        elif method == "window/showMessage":
            self._message = _words(params)
            self._notify_soon()
        # window/logMessage and the rest: dropped (never logged)

    def _notify_soon(self) -> None:
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(self._notify())

    async def _notify(self) -> None:
        await self._live.broadcast({"type": NOTICE})
        await self._live.broadcast({"type": PANEL_NOTICE, "id": "copilot"})

    async def _stop(self) -> None:
        conn, self._conn = self._conn, None
        self._mirror.clear()
        self._focused = None
        self._items.clear()
        if conn is not None:
            await conn.close()

    async def stop(self) -> None:
        if self._finishing is not None:
            self._finishing.cancel()
        await self._stop()

    # ===== install, the switch =====

    async def install(self, who: str) -> dict[str, Any]:
        if self._installing:
            raise Conflict("The language server is being installed.")
        missing = await self._missing("install")
        if missing is not None:
            raise MissingPackagesError(missing["missing"])
        await self._approvals.allowed(
            who,
            subject="copilot",
            action="install",
            detail=f"Install GitHub's Copilot Language Server {lsp.PINNED} with npm into the app's folder",
            otherwise="the language server was not installed",
        )
        self._installing = True
        self._said = None
        await self._notify()
        try:
            code, printed = await self._machine.install()
        finally:
            self._installing = False
        self._audit.write(who, "copilot_install", None, version=lsp.PINNED, ok=code == 0)
        if code != 0 or not self._machine.installed():
            self._said = (
                "npm could not install the language server: " + (printed.splitlines() or ["no words"])[-1]
            )
            await self._notify()
            raise Conflict(self._said)
        await self._notify()
        return await self.state(who)

    async def toggle(self, body: Any, who: str) -> dict[str, Any]:
        if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
            raise ValueError('Send {"on": true} or {"on": false}.')
        self._keep(on=body["on"])
        if not body["on"]:
            await self._stop()  # off: nothing is sent, and nothing runs
        self._audit.write(who, "copilot_toggle", None, on=body["on"])
        await self._notify()
        return await self.state(who)

    # ===== signing in (the user's) =====

    def _users(self, who: str, what: str) -> None:
        if who == "agent":
            raise Refused(f"{what} is the user's own: they do it on the Extensions page.")

    async def sign_in(self, who: str) -> dict[str, Any]:
        self._users(who, "Signing in to GitHub Copilot")
        if not self._machine.installed():
            raise Conflict("Install the language server first.")
        conn = await self._ensure()
        try:
            answer = await conn.request(lsp.SIGN_IN, {}, timeout=60.0)
        except (LspError, ServerGone, TimeoutError) as error:
            raise Conflict(f"GitHub did not start the sign-in: {error}") from None
        self._said = None
        flow = lsp.device_flow_of(answer)
        if flow is None:
            self._account = lsp.account_of(answer)
            if self._account["state"] == "signed_in":
                self._keep(on=True, login=self._login())
        else:
            self._device = flow
        self._audit.write(who, "copilot_sign_in", None, started=flow is not None)
        await self._notify()
        return self.panel(who)

    async def finish(self, who: str) -> dict[str, Any]:
        """The user opened GitHub's page: wait for the sign-in there (in the background)."""
        self._users(who, "Signing in to GitHub Copilot")
        if self._device is None or self._conn is None:
            raise Conflict("Sign in first: no code is waiting.")
        if self._finishing is None or self._finishing.done():
            self._finishing = asyncio.create_task(self._wait_for_github(self._conn))
        self._device = self._device | {"waiting": True}
        await self._notify()
        return self.panel(who)

    async def _wait_for_github(self, conn: Connection) -> None:
        try:
            params = {"command": lsp.FINISH_DEVICE_FLOW, "arguments": []}
            answer = await conn.request(lsp.EXECUTE, params, timeout=SIGN_IN_SECONDS)
            self._account = lsp.account_of(answer)
            if self._account["state"] == "not_signed_in":
                self._account = lsp.account_of(await conn.request(lsp.CHECK_STATUS, {}, timeout=30.0))
            if self._account["state"] == "signed_in":
                self._keep(on=True, login=self._login())
            else:
                self._keep(login=self._login())
        except (LspError, ServerGone, TimeoutError) as error:
            self._said = f"The sign-in did not finish: {error}"[:300]
        finally:
            self._device = None
            self._audit.write("user", "copilot_signed_in", None, state=self._account_state())
            await self._notify()

    async def cancel_sign_in(self, who: str) -> dict[str, Any]:
        self._users(who, "Signing in to GitHub Copilot")
        if self._finishing is not None:
            self._finishing.cancel()
        self._device = None
        await self._notify()
        return self.panel(who)

    async def sign_out(self, who: str) -> dict[str, Any]:
        self._users(who, "Signing out of GitHub Copilot")
        conn = await self._ensure()
        with contextlib.suppress(LspError, TimeoutError):
            await conn.request(lsp.SIGN_OUT, {}, timeout=30.0)
        self._account = {"state": "not_signed_in", "user": None}
        self._keep(login=None)
        await self._stop()
        self._audit.write(who, "copilot_sign_out", None)
        await self._notify()
        return self.panel(who)

    # ===== the panel, as data (the Extensions card and Settings draw it) =====

    def panel(self, who: str = "user") -> dict[str, Any]:
        lines: list[dict[str, str]] = []
        actions: list[dict[str, Any]] = []
        installed = self._machine.installed()
        state = self._account_state()
        node = (self._tools or {}).get("node")
        if not installed:
            lines.append(
                {"text": f"GitHub's Copilot Language Server {lsp.PINNED} is not installed.", "tone": ""}
            )
            if node is not None and not node["ok"]:
                lines.append({"text": f"It needs Node.js 20.8 or later: {node['install']}", "tone": "warn"})
            actions.append(
                {
                    "id": "install",
                    "label": "Install the language server",
                    "primary": True,
                    "disabled": self._installing,
                }
            )
        elif state == "signed_in":
            lines.append({"text": f"Signed in as {self._login() or 'your GitHub account'}.", "tone": "ok"})
            actions.append({"id": "sign_out", "label": "Sign out"})
        elif state == "no_subscription":
            lines.append(
                {
                    "text": f"Signed in as {self._login() or 'a GitHub account'}, which has no"
                    " GitHub Copilot plan (Copilot Free counts).",
                    "tone": "warn",
                }
            )
            actions.append({"id": "sign_out", "label": "Sign out"})
        elif self._device is None:
            lines.append(
                {"text": "Not signed in. A GitHub Copilot plan is needed (Copilot Free counts).", "tone": ""}
            )
            actions.append({"id": "sign_in", "label": "Sign in to GitHub", "primary": True})
        if self._private():
            lines.append({"text": "This project is private: nothing of it is sent.", "tone": "warn"})
        if self._server_status.get("kind") in ("Error", "Warning") and state == "signed_in":
            lines.append({"text": self._server_status["message"], "tone": "warn"})
        if self._message:
            lines.append({"text": self._message, "tone": ""})
        if self._said:
            lines.append({"text": self._said, "tone": "error"})
        code = None
        if self._device is not None and who == "user":
            code = {
                "label": "Enter this code at GitHub",
                "text": self._device["code"],
                "link": self._device["link"],
                "link_label": "Open github.com/login/device",
                "then": "finish",
                "waiting": bool(self._device.get("waiting")),
            }
            actions.append({"id": "cancel_sign_in", "label": "Cancel"})
        busy = "Installing the language server…" if self._installing else None
        if self._device is not None and self._device.get("waiting"):
            busy = "Waiting for GitHub…"
        return {
            "title": NAME,
            "lines": lines,
            "switches": [{"id": "on", "label": "On", "on": self.on, "disabled": not installed}],
            "actions": actions,
            "code": code,
            "busy": busy,
        }

    async def panel_now(self, who: str) -> dict[str, Any]:
        await self.tools_state()
        await self._look()
        return self.panel(who)

    async def act(self, body: Any, who: str) -> dict[str, Any]:
        """The panel's click: {"action": id} or {"switch": "on", "on": bool}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"action": "<id>"} or {"switch": "on", "on": true}.')
        if body.get("switch") == "on":
            await self.toggle({"on": body.get("on")}, who)
            return self.panel(who)
        action = body.get("action")
        if action == "install":
            await self.install(who)
            return self.panel(who)
        if action == "sign_in":
            return await self.sign_in(who)
        if action == "finish":
            return await self.finish(who)
        if action == "cancel_sign_in":
            return await self.cancel_sign_in(who)
        if action == "sign_out":
            return await self.sign_out(who)
        raise NotFound(f"{action!r} is not one of this panel's actions.")

    # ===== completions =====

    def _off_reason(self) -> str | None:
        if not self.ready():
            return self.words()
        return None

    async def complete(self, body: Any) -> dict[str, Any]:
        """{"request", "document": {"key", "name", "kind": "script"|"notebook", "language", "text"} or, for a
        notebook, {"key", "name", "kind": "notebook", "cells": [{"id", "text", "language"}], "cell"},
        "position": {"line", "character"}, "tab_size"?, "insert_spaces"?}
        -> {"items": [{id, text, range}]}."""
        if self._private() and self._conn is not None and (self._mirror.texts or self._mirror.notebooks):
            with contextlib.suppress(ServerGone):
                for message in self._mirror.close_all():
                    await self._conn.notify(message["method"], message["params"])
        off = self._off_reason()
        if off is not None:
            return {"items": [], "off": off}
        if not isinstance(body, dict) or not isinstance(body.get("document"), dict):
            raise ValueError("Send the document and the cursor's position.")
        doc, position = body["document"], body.get("position")
        if not isinstance(position, dict) or not all(
            isinstance(position.get(k), int) for k in ("line", "character")
        ):
            raise ValueError("The position is {line, character}, both numbers from 0.")
        conn = await self._ensure()
        try:
            if doc.get("kind") == "notebook":
                uri, version, messages = self._mirror.notebook(
                    doc.get("key"), doc.get("name"), doc.get("cells"), doc.get("cell")
                )
            else:
                uri, version, messages = self._mirror.text(
                    doc.get("key"), doc.get("name"), doc.get("language"), doc.get("text")
                )
        except DocumentError as error:
            raise ValueError(str(error)) from None
        ident = conn.next_id()
        request = str(body.get("request") or ident)[:60]
        self._pending[request] = ident
        try:
            for message in messages:
                await conn.notify(message["method"], message["params"])
            if uri != self._focused:
                await conn.notify(lsp.DID_FOCUS, {"textDocument": {"uri": uri}})
                self._focused = uri
            params = lsp.inline_params(
                uri,
                version,
                {"line": position["line"], "character": position["character"]},
                int(body.get("tab_size") or 4),
                body.get("insert_spaces") is not False,
            )
            result = await conn.request(lsp.INLINE, params, timeout=COMPLETION_SECONDS, ident=ident)
        except LspError as error:
            if error.code in (lsp.REQUEST_CANCELLED, lsp.SERVER_CANCELLED):
                return {"items": [], "cancelled": True}
            return {"items": [], "error": str(error)[:300]}
        except (ServerGone, TimeoutError):
            self._mirror.clear()
            return {"items": [], "error": "The language server did not answer."}
        finally:
            self._pending.pop(request, None)
        out = []
        for item in lsp.items_of(result):
            key = f"c{next(self._item_ids)}"
            self._items[key] = {"raw": item["raw"], "command": item["command"]}
            while len(self._items) > MAX_ITEMS_KEPT:
                self._items.popitem(last=False)
            out.append({"id": key, "text": item["text"], "range": item["range"]})
        return {"items": out}

    async def cancel(self, body: Any) -> dict[str, Any]:
        request = str(body.get("request") or "") if isinstance(body, dict) else ""
        ident = self._pending.get(request)
        if ident is not None and self._conn is not None:
            with contextlib.suppress(ServerGone):
                await self._conn.cancel(ident)
        return {"cancelled": ident is not None}

    async def event(self, body: Any) -> dict[str, Any]:
        """What the editor did with an item: {"id", "kind": "shown"|"accepted"|"partial", "length"?}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"id", "kind"}.')
        item = self._items.get(str(body.get("id") or ""))
        kind = body.get("kind")
        if item is None or self._conn is None or not self.ready():
            return {"sent": False}
        try:
            if kind == "shown":
                await self._conn.notify(lsp.DID_SHOW, {"item": item["raw"]})
            elif kind == "partial":
                length = body.get("length")
                if not isinstance(length, int) or length < 0:
                    raise ValueError("A partial accept says its length (UTF-16 units from the item's start).")
                await self._conn.notify(
                    lsp.DID_PARTIALLY_ACCEPT, {"item": item["raw"], "acceptedLength": length}
                )
            elif kind == "accepted":
                command = item["command"]
                if command is not None:
                    params = {"command": command["command"], "arguments": command.get("arguments") or []}
                    with contextlib.suppress(LspError, TimeoutError):
                        await self._conn.request(lsp.EXECUTE, params, timeout=10.0)
                self._items.pop(str(body.get("id")), None)
            else:
                raise ValueError("kind is shown, accepted or partial.")
        except ServerGone:
            return {"sent": False}
        return {"sent": True}


def _words(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    text = params.get("message")
    return str(text)[:300] if isinstance(text, str) and text.strip() else None
