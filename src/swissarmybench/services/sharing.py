"""Share a running app with your organization (domain/sharing.py's rules; adapters/tunnels.py's program).

status    devtunnel installed or not, the sign-in (whom, a work account or not), each app's share (its
          state, its link while shared, who can open it); `sharing_status`
install   devtunnel downloaded and checked once (the user's Install now; the agent's on Allow)
sign in   `devtunnel user login --entra`, in the browser or with a device code shown in the dialog: the
          user's only (403 for the agent)
start     the app's target opens its own 127.0.0.1 port (an extension's: hooks.share_targets[kind]); a
          tunnel made (no anonymous access), the tenant's entry added, the access read back (no anonymous
          entry, the tenant's there, else deleted and refused), the port added, hosted, the link read from
          its words; the agent's on Allow (it publishes outward)
stop      the host stopped, the tunnel deleted, the target's port closed; on Stop sharing (the agent's on
          Allow), when the app stops (app_stopped: a link always ends with its app), when the host ends by
          itself (failed, said), and every share when the server stops (stop_all)
audit     share_start and share_stop (which app, by whom): never the link, a tunnel id or a token
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import sharing as rules
from swissarmybench.domain.sharing import SharingError
from swissarmybench.services import background
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

START_SECONDS: float = 90.0  # for host to say the address
SIGN_IN_SECONDS: float = 900.0
USER_SECONDS: float = 30.0  # how long a read sign-in holds


class Lines(Protocol):
    lines: list[str]

    def alive(self) -> bool: ...

    async def line(self, timeout: float) -> str | None: ...

    async def stop(self) -> None: ...


class Program(Protocol):
    def installed(self) -> bool: ...

    def checks(self) -> str: ...

    async def install(self) -> None: ...

    async def run(self, args: list[str], timeout: float = 60.0) -> tuple[int, str]: ...

    async def start(self, args: list[str]) -> Lines: ...


@dataclass(frozen=True)
class Opened:
    """What a target opened for the tunnel: the app's own 127.0.0.1 port and its title."""

    port: int
    title: str


class ShareTarget(Protocol):
    """An app kind that can be shared (the Streamlit extension's launched apps): a port of the app's own."""

    async def open(self, app: str) -> Opened: ...

    async def close(self, app: str) -> None: ...


@dataclass
class Share:
    kind: str
    app: str
    title: str = ""
    state: str = "starting"
    url: str | None = None
    error: str | None = None
    port: int | None = None
    tunnel: str | None = None
    started: float | None = None
    host: Lines | None = None
    watch: asyncio.Task[None] | None = field(default=None, repr=False)

    def said(self, tenant: str | None) -> dict[str, Any]:
        sharing = self.state == "sharing"
        return {
            "kind": self.kind,
            "app": self.app,
            "title": self.title,
            "state": self.state,
            "words": rules.state_words(self.state),
            "url": self.url if sharing else None,
            "who": rules.who_can_open(tenant) if sharing else None,
            "note": rules.NOTE if sharing else None,
            "error": self.error,
            "started": self.started,
        }


class Sharing:
    def __init__(
        self,
        ws: Workspace,
        program: Program,
        targets: Callable[[], dict[str, ShareTarget]],
        approvals: Approvals,
        server_port: int,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.ws = ws
        self._program = program
        self._targets = targets
        self._approvals = approvals
        self._server_port = server_port
        self._now = now
        self._shares: dict[tuple[str, str], Share] = {}
        self._user: rules.User | None = None
        self._user_at = 0.0
        self._installing = False
        self._sign_in: Lines | None = None
        self._device: rules.DeviceCode | None = None
        self._sign_in_error: str | None = None
        self._lock = asyncio.Lock()

    # ===== what is said =====

    async def _changed(self) -> None:
        await self.ws.live.broadcast({"type": "sharing_changed"})

    async def _read_user(self, fresh: bool = False) -> rules.User:
        if not self._program.installed():
            return rules.User(False)
        if not fresh and self._user is not None and time.monotonic() - self._user_at < USER_SECONDS:
            return self._user
        try:
            _, out = await self._program.run(rules.user_show(), 30)
            self._user = rules.read_user(out)
        except SharingError:
            self._user = rules.User(False)
        self._user_at = time.monotonic()
        return self._user

    async def status(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        wanted = body if isinstance(body, dict) else {}
        user = await self._read_user(bool(wanted.get("fresh")))
        tenant = None  # the tenant's display name: the CLI does not say it (the id is not shown)
        shares = [s.said(tenant) for s in self._shares.values() if s.state != "stopped"]
        kind, app = wanted.get("kind"), wanted.get("app")
        if kind and app:
            shares = [s for s in shares if s["kind"] == kind and s["app"] == app]
        signing = self._sign_in is not None and self._sign_in.alive()
        return {
            "installed": self._program.installed(),
            "installing": self._installing,
            "checks": self._program.checks(),
            "needs": rules.NEEDS,
            "sentence": rules.SENTENCE,
            "signed_in": user.signed_in,
            "work_account": user.work,
            "account": user.account if who == "user" else None,
            "signing_in": signing,
            "device": {"url": self._device.url, "code": self._device.code}
            if signing and self._device
            else None,
            "sign_in_error": self._sign_in_error,
            "kinds": sorted(self._targets()),
            "shares": shares,
        }

    # ===== install and sign in =====

    async def _allow(self, who: str, action: str, detail: str) -> None:
        await self._approvals.allowed(
            who, subject="Sharing", action=action, detail=detail, otherwise="nothing changed"
        )

    async def install(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        if self._program.installed():
            return {"installed": True}
        await self._allow(
            who, "share_install", "Download Microsoft's devtunnel command line (for sharing an app)"
        )
        if self._installing:
            raise Conflict("devtunnel is being installed already.")
        self._installing = True
        await self._changed()
        try:
            await self._program.install()
        except SharingError as error:
            raise Conflict(str(error)) from None
        except OSError as error:
            raise Conflict(f"devtunnel could not be downloaded: {error}") from None
        finally:
            self._installing = False
            await self._changed()
        self.ws.audit.write(who, "share_install", None)
        return {"installed": True}

    async def sign_in(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Sign in with your work account (Microsoft Entra): the user's own, never the agent's."""
        if who == "agent":
            raise Refused("Signing in is the user's own: Share…, Sign in.")
        if not self._program.installed():
            raise Conflict(f"{rules.NEEDS}: Install now first.")
        device = bool(body.get("device")) if isinstance(body, dict) else False
        if self._sign_in is not None and self._sign_in.alive():
            await self._sign_in.stop()
        self._device, self._sign_in_error = None, None
        running = await self._program.start(rules.login(device))
        self._sign_in = running
        background.keep(self._signing(running), "the sharing sign-in")
        # The device code's line comes first: wait a little for it so the dialog can show it at once.
        for _ in range(30):
            if self._device is not None or not running.alive():
                break
            await asyncio.sleep(0.1)
        await self._changed()
        return {
            "signing_in": running.alive(),
            "device": {"url": self._device.url, "code": self._device.code} if self._device else None,
        }

    async def _signing(self, running: Lines) -> None:
        deadline = time.monotonic() + SIGN_IN_SECONDS
        try:
            while time.monotonic() < deadline:
                try:
                    line = await running.line(max(1.0, deadline - time.monotonic()))
                except TimeoutError:
                    break
                if line is None:
                    break
                found = rules.read_device_code(line)
                if found is not None:
                    self._device = found
                    await self._changed()
        finally:
            if running.alive():
                await running.stop()
            user = await self._read_user(fresh=True)
            if not user.signed_in:
                self._sign_in_error = rules.failure("\n".join(running.lines)) if running.lines else None
            elif not user.work:
                self._sign_in_error = rules.NOT_WORK_ACCOUNT
            else:
                self.ws.audit.write("user", "share_sign_in", None)
            if self._sign_in is running:
                self._sign_in, self._device = None, None
            await self._changed()

    # ===== share and stop =====

    def _target(self, kind: Any) -> ShareTarget:
        target = self._targets().get(kind) if isinstance(kind, str) else None
        if target is None:
            raise NotFound("That kind of app cannot be shared here.")
        return target

    @staticmethod
    def _named(body: Any) -> tuple[str, str]:
        if not isinstance(body, dict) or not isinstance(body.get("app"), str) or not body["app"]:
            raise ValueError('Name the app: {"kind": "streamlit", "app": "<its id>"}.')
        return str(body.get("kind") or "streamlit"), str(body["app"])

    async def _devtunnel(self, args: list[str], timeout: float = 60.0) -> str:
        code, out = await self._program.run(args, timeout)
        if code != 0:
            raise SharingError(rules.failure(out))
        return out

    async def start(self, body: Any, who: str = "user") -> dict[str, Any]:
        kind, app = self._named(body)
        target = self._target(kind)
        held = self._shares.get((kind, app))
        if held is not None and held.state in ("starting", "sharing"):
            return held.said(None)
        await self._allow(
            who,
            "share_start",
            "Share a running app with your organization (anyone in it with the link can use it)",
        )
        if not self._program.installed():
            if who == "agent":
                await self.install(None, "user")  # Allowed once above: the download is part of the share
            else:
                raise Conflict(f"{rules.NEEDS}: Install now.")
        user = await self._read_user(fresh=True)
        if not user.signed_in:
            raise Conflict(rules.NOT_SIGNED_IN)
        if not user.work:
            raise Conflict(rules.NOT_WORK_ACCOUNT)
        share = Share(kind, app)
        self._shares[(kind, app)] = share
        await self._changed()
        async with self._lock:
            try:
                opened = await target.open(app)
                share.title = opened.title
                share.port = rules.check_port(opened.port, self._server_port)
                await self._clear_stale()
                share.tunnel = rules.read_tunnel_id(await self._devtunnel(rules.create()))
                await self._check_access(share.tunnel, before=True)
                await self._devtunnel(rules.access_tenant(share.tunnel))
                await self._check_access(share.tunnel, before=False)
                await self._devtunnel(rules.port_create(share.tunnel, share.port, self._server_port))
                share.host = await self._program.start(rules.host(share.tunnel))
                share.url = await self._address(share.host, share.port)
            except (SharingError, Conflict, NotFound, Refused) as error:
                share.state, share.error = "failed", str(error)
                await self._end(share, target)
                await self._changed()
                raise Conflict(str(error)) from None
            except Exception:
                share.state, share.error = "failed", "The share did not start."
                await self._end(share, target)
                await self._changed()
                raise
        share.state, share.started = "sharing", self._now()
        share.watch = background.keep(self._hosting(share), "a shared app's tunnel")
        self.ws.audit.write(who, "share_start", share.title or app, kind=kind)
        await self._changed()
        return share.said(None)

    async def _clear_stale(self) -> None:
        """A tunnel of this app's left by a crash (by its label, none of the shares running now): deleted."""
        with contextlib.suppress(SharingError):
            found = rules.read_tunnel_ids(await self._devtunnel(rules.listing()))
            running = {s.tunnel for s in self._shares.values() if s.tunnel}
            for tunnel in found:
                if tunnel not in running:
                    with contextlib.suppress(SharingError):
                        await self._devtunnel(rules.delete(tunnel))

    async def _check_access(self, tunnel: str, before: bool) -> None:
        access = rules.read_access(await self._devtunnel(rules.access_list(tunnel)))
        if access.anonymous:
            raise SharingError(rules.ANONYMOUS_FOUND)
        if not before and not access.tenant:
            raise SharingError(rules.NO_TENANT_ENTRY)

    async def _address(self, host: Lines, port: int) -> str:
        deadline = time.monotonic() + START_SECONDS
        url: str | None = None
        while time.monotonic() < deadline:
            try:
                line = await host.line(max(0.5, deadline - time.monotonic()))
            except TimeoutError:
                break
            if line is None:
                raise SharingError(rules.failure("\n".join(host.lines)))
            url = url or rules.read_address(line, port)
            if url and rules.ready(line):
                return url
            if rules.blocked_by_policy(line):
                raise SharingError(rules.POLICY)
        if url:
            return url
        raise SharingError("The tunnel did not say its address in time: nothing was shared.")

    async def _hosting(self, share: Share) -> None:
        """While shared: the host's words read; if it ends by itself the share is said failed and closed."""
        host = share.host
        if host is None:
            return
        while True:
            try:
                line = await host.line(3600.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            if line is None:
                break
        if share.state == "sharing":
            share.state, share.error = "failed", rules.failure("\n".join(host.lines))
            await self._end(share, self._targets().get(share.kind))
            self.ws.audit.write("user", "share_stop", share.title or share.app, kind=share.kind, why="ended")
            await self._changed()

    async def _end(self, share: Share, target: ShareTarget | None) -> None:
        if share.watch is not None and share.watch is not asyncio.current_task():
            share.watch.cancel()
        if share.host is not None:
            with contextlib.suppress(Exception):
                await share.host.stop()
        if share.tunnel:
            with contextlib.suppress(Exception):
                await self._program.run(rules.delete(share.tunnel), 30)
        if target is not None:
            with contextlib.suppress(Exception):
                await target.close(share.app)

    async def stop(self, body: Any, who: str = "user", why: str = "stopped") -> dict[str, Any]:
        kind, app = self._named(body)
        share = self._shares.get((kind, app))
        if share is None or share.state in ("stopped", "failed"):
            self._shares.pop((kind, app), None)
            return {"kind": kind, "app": app, "state": "stopped"}
        if who == "agent":
            await self._allow(who, "share_stop", f"Stop sharing {share.title or app}")
        share.state = "stopped"
        await self._end(share, self._targets().get(kind))
        self._shares.pop((kind, app), None)
        self.ws.audit.write(who, "share_stop", share.title or app, kind=kind, why=why)
        await self._changed()
        return {"kind": kind, "app": app, "state": "stopped"}

    async def app_stopped(self, kind: str, app: str) -> None:
        """The app stopped (its Stop, a new launch, its window gone): its link ends with it."""
        if (kind, app) in self._shares:
            await self.stop({"kind": kind, "app": app}, "user", why="the app stopped")

    async def stop_all(self) -> None:
        """The server is stopping: no share outlives it."""
        for kind, app in list(self._shares):
            with contextlib.suppress(Exception):
                await self.stop({"kind": kind, "app": app}, "user", why="Swiss Army Bench closed")
        if self._sign_in is not None:
            with contextlib.suppress(Exception):
                await self._sign_in.stop()

    def shared(self, kind: str, app: str) -> bool:
        share = self._shares.get((kind, app))
        return share is not None and share.state == "sharing"
