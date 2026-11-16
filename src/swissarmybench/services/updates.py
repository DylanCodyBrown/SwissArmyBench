"""Updates: is there a newer release, the Settings switch "Check for updates", and "Update to X".

The check is the one request that leaves the computer, by the owner's call (2026-11-16): at start and
every six hours, PyPI's JSON for `swissarmybench`, then GitHub's latest release if PyPI cannot be read.
Nothing is sent but that request. With the switch off, nothing is sent at all.

"Update to X" (the tray, a page's status bar, the agent): it asks first only when something would be
lost (a notebook's unsaved changes, a running kernel), and the agent's always waits for the user's
Allow (it restarts the app). It saves nothing for the user. The helper (server/updater.py) waits for the
app to stop, installs with uv, and starts the new version; this server stops right after handing over.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import updates as rules
from swissarmybench.domain.updates import Release, UpdateError
from swissarmybench.services.agent import Approvals
from swissarmybench.services.ports import Audit, Notifier
from swissarmybench.services.workspace import Conflict, Refused


class ReleaseFeed(Protocol):
    """One GET of a release list's JSON (adapters/updates.py). Raises when it cannot be had."""

    def fetch(self, url: str) -> Any: ...


class UpdateSwitch(Protocol):
    """Check for updates, kept across restarts (update.json); None: never set (on)."""

    def read(self) -> bool | None: ...

    def write(self, on: bool) -> None: ...


class UpdateHelper(Protocol):
    """Starts the helper that installs `version` once this server has stopped (server/updater.py)."""

    def launch(self, version: str, source: str) -> None: ...


# What is open, for the tray's menu and for the question before an update:
# {"tables": [{"grid", "name"}], "documents": [{"key", "title", "unsaved"}], "unsaved": [titles],
#  "kernels": n}
OpenWork = Callable[[], Awaitable[dict[str, Any]]]

# Long enough for the answer to reach the asker before the server stops.
STOP_AFTER_SECONDS: float = 0.5


class Updates:
    def __init__(
        self,
        *,
        current: str,
        feeds: tuple[str, ...],
        feed: ReleaseFeed,
        switch: UpdateSwitch,
        helper: UpdateHelper,
        open_work: OpenWork,
        approvals: Approvals,
        audit: Audit,
        live: Notifier,
        stop: Callable[[], None],
        failed: dict[str, Any] | None = None,
        every_seconds: float = rules.CHECK_EVERY_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.current = rules.parse_version(current)
        self.feeds = feeds
        self._feed = feed
        self._switch = switch
        self._helper = helper
        self._open_work = open_work
        self._approvals = approvals
        self._audit = audit
        self._live = live
        self._stop = stop
        self._every = every_seconds
        self._clock = clock
        self._offer: Release | None = None
        self._latest: Release | None = None
        self._checked: float | None = None
        self._error: str | None = None
        self._updating: str | None = None
        # The last update's failure (the helper's note), said until the next update or restart.
        self._failed = failed

    # ===== reading =====

    @property
    def on(self) -> bool:
        return self._switch.read() is not False

    def state(self) -> dict[str, Any]:
        offer = self._offer
        said: dict[str, Any] = {
            "current": str(self.current),
            "latest": str(self._latest.version) if self._latest else None,
            "available": offer is not None,
            "version": str(offer.version) if offer else None,
            "url": rules.release_page(str(offer.version)) if offer else None,
            "source": offer.source if offer else None,
            "check": self.on,
            "checked": self._checked,
            "updating": self._updating,
        }
        if self._error:
            said["error"] = self._error
        if self._failed:
            said["failed"] = self._failed
        return said

    async def open_work(self) -> dict[str, Any]:
        return await self._open_work()

    async def tray(self) -> dict[str, Any]:
        """What the tray's menu shows: the update, the open tables and the Workbench's documents."""
        work = await self._open_work()
        return self.state() | {"tables": work.get("tables", []), "documents": work.get("documents", [])}

    # ===== the switch and the check =====

    async def set(self, body: Any, who: str) -> dict[str, Any]:
        on = body.get("check") if isinstance(body, dict) else None
        if not isinstance(on, bool):
            raise ValueError('Send {"check": true} or {"check": false}.')
        self._switch.write(on)
        self._audit.write(who, "update_check", None, on=on)
        if not on and self._offer is not None:
            self._offer = None
            await self._tell()
        elif on:  # turned on: ask now
            await self.check()
        return self.state()

    async def check(self) -> dict[str, Any]:
        """Ask the release lists now (nothing is sent with the switch off, or with no feeds)."""
        if not self.on or not self.feeds:
            return self.state()
        before = self._offer
        releases: list[Release] | None = None
        error = "No release list could be reached."
        for url in self.feeds:
            try:
                document = await asyncio.to_thread(self._feed.fetch, url)
                releases = rules.releases_from(url, document)
                break
            except UpdateError as problem:
                error = str(problem)
            except Exception:  # the network, a refused or slow answer: the next feed
                error = "No release list could be reached."
        self._checked = self._clock()
        if releases is None:
            self._error = error
        else:
            self._error = None
            allowed = [r for r in releases if self.current.is_prerelease or not r.version.is_prerelease]
            self._latest = max(allowed, key=lambda r: r.version._key()) if allowed else None
            self._offer = rules.offered(self.current, releases)
        if (before and str(before.version)) != (self._offer and str(self._offer.version)):
            await self._tell()
        return self.state()

    async def run_forever(self) -> None:
        """At start, then every six hours (the server's lifespan runs it; nothing when there are no feeds)."""
        if not self.feeds:
            return
        while True:
            try:
                await self.check()
            except Exception:  # noqa: S110 (a failed check is tried again at the next turn)
                pass
            await asyncio.sleep(self._every)

    async def _tell(self) -> None:
        await self._live.broadcast({"type": "update_changed", **self.state()})

    # ===== Update to X =====

    async def install(self, body: Any, who: str) -> dict[str, Any]:
        """Update to the offered version: {"version"?, "confirmed"?}. The user's, with unsaved work or a
        running kernel, first answers {"confirm": {...}} (sent again with "confirmed": true); the
        agent's waits for the user's Allow."""
        body = body if isinstance(body, dict) else {}
        if self._updating:
            raise Conflict(f"Updating to {self._updating} already.")
        offer = self._offer
        if offer is None:
            raise Conflict("No update is available.")
        version = str(offer.version)
        asked = body.get("version")
        if asked is not None and (rules.try_version(asked) != offer.version):
            raise Conflict(f"The update available is {version}.")
        work = await self._open_work()
        at_risk = {"unsaved": list(work.get("unsaved", [])), "kernels": int(work.get("kernels", 0))}
        if who == "agent":
            if not await self._approvals.ask(
                version, "update the app to", rules.update_question(version, at_risk)
            ):
                raise Refused(f"The user declined (or did not answer): the app was not updated to {version}.")
        elif (at_risk["unsaved"] or at_risk["kernels"]) and body.get("confirmed") is not True:
            return {"confirm": at_risk, "version": version}
        self._helper.launch(version, offer.source)
        self._updating = version
        self._failed = None
        self._audit.write(who, "update", None, version=version, current=str(self.current))
        await self._live.broadcast({"type": "app_updating", "version": version})
        asyncio.get_running_loop().call_later(STOP_AFTER_SECONDS, self._stop)
        return {"updating": version}
