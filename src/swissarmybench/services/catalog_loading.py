"""Catalogs that load themselves (the owner, 2026-11-14: "auto load the catalog in a separate thread so it
can background load and feed the autocomplete").

A connection's catalog (its tables and columns, by its catalog command) loads in the background:

  SAVED        when a connection is saved (the user is there: a sign-in window is expected)
  START-UP     every connection once the app's first window is open (or START_WAIT_SECONDS after the
               server started, with none), so the child processes never race the first page's own loading;
               not one that signs in with a browser window or a phone prompt (domain/connections.py
               signs_in_interactively): that one waits
  FIRST USE    a waiting one (or any not loaded) when a SQL cell, the side bar or the agent first asks

Each load is Refresh's own run (a child process of the server's Python, services/blades.py), a few at
once (settings.catalogs_at_once), never twice at the same time for one connection. A catalog that arrives
tells the pages (catalogs_changed), so the SQL cell's completion has it at once. A load that fails is
kept with its reason (shown on the connection); nothing is retried unasked. Catalogs stay in memory only,
as Refresh's do.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from swissarmybench.domain import connections as rules
from swissarmybench.domain.blades import BladeError
from swissarmybench.services.blades import BladeService, NeedsValues
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.workspace import Workspace

# Start-up's loads wait for the app's first window (its page connected), then SETTLE_SECONDS more for the
# page's own first requests; with no window, START_WAIT_SECONDS from the start (a server for the agent).
START_WAIT_SECONDS: float = 15.0
SETTLE_SECONDS: float = 2.0
_POLL_SECONDS: float = 0.25


class CatalogLoading:
    def __init__(
        self,
        ws: Workspace,
        blades: BladeService,
        catalogs: CatalogService,
        enabled: bool,
        at_once: int,
        windows: Callable[[], int] = lambda: 1,
    ) -> None:
        # How many of the app's windows are open (adapters/live_updates.py): start-up waits for the first.
        self._windows = windows
        self.ws = ws
        self._blades = blades
        self._catalogs = catalogs
        self._enabled = enabled
        self._gate = asyncio.Semaphore(max(1, at_once))
        self._running: dict[str, asyncio.Task[None]] = {}  # by name, case folded
        self._state: dict[str, dict[str, str]] = {}  # "waiting", or "failed" with its reason

    def state(self, name: str) -> dict[str, str] | None:
        """loading, waiting (first use), failed (and why), or None: loaded, or never asked."""
        key = name.casefold()
        if key in self._running:
            return {"state": "loading"}
        return self._state.get(key)

    def load(self, name: str, who: str = "app") -> dict[str, Any]:
        """Load a connection's catalog in the background (now, or after the ones already loading)."""
        blade = self._blades.get(name)
        if not rules.has_catalog(rules.connection_kind(blade.kind, blade.template)) or not blade.has_catalog:
            raise BladeError(f"{blade.name} has no catalog to load.")
        key = blade.name.casefold()
        if self._enabled and key not in self._running:
            self._state.pop(key, None)
            task = asyncio.get_running_loop().create_task(self._load(blade.name, who))
            self._running[key] = task
            task.add_done_callback(lambda _: self._running.pop(key, None))
        return {"name": blade.name, **(self.state(blade.name) or {"state": "loaded"})}

    async def ready(self, name: str) -> bool:
        """A connection's catalog loaded, waiting for it when it is not yet (a swap matches its tables
        there): whether it is now."""
        blade = self._blades.get(name)
        if blade.name.casefold() in {n.casefold() for n in self._catalogs.loaded_names()}:
            return True
        if not rules.has_catalog(rules.connection_kind(blade.kind, blade.template)) or not blade.has_catalog:
            return False
        running = self._running.get(blade.name.casefold())
        if running is not None:
            await asyncio.shield(running)
        else:
            await self._load(blade.name, "app")
        return blade.name.casefold() in {n.casefold() for n in self._catalogs.loaded_names()}

    def saved(self, name: str) -> None:
        """A connection was saved: its catalog follows (the user is there, so any sign-in is too)."""
        try:
            self.load(name, "user")
        except BladeError:
            pass  # a vault, or code with no catalog command

    async def at_start_later(
        self, wait: float = START_WAIT_SECONDS, settle: float = SETTLE_SECONDS
    ) -> list[str]:
        """at_start, once the first window is open and its page has settled, or after `wait` seconds."""
        if not self._enabled:
            return []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        while self._windows() == 0 and loop.time() < deadline:
            await asyncio.sleep(_POLL_SECONDS)
        if self._windows():
            await asyncio.sleep(settle)
        return self.at_start()

    def at_start(self) -> list[str]:
        """Every connection's catalog, in the background, but the ones that sign in with a window (they
        wait for first use) and the ones past the catalog limit. The names started."""
        if not self._enabled:
            return []
        started: list[str] = []
        room = self.ws.settings.max_catalogs - len(self._catalogs.loaded_names())
        for listed in self._blades.listing()["blades"]:
            if not rules.has_catalog(listed.get("connection")) or not listed.get("has_catalog"):
                continue
            blade = self._blades.get(str(listed["name"]))
            if rules.signs_in_interactively(blade.code) or len(started) >= room:
                self._state[blade.name.casefold()] = {"state": "waiting"}
                continue
            self.load(blade.name)
            started.append(blade.name)
        return started

    async def rescope(self) -> list[str]:
        """Another project's connections are in use (or this computer's): the catalogs of connections it
        does not have go, and its own load as at start. The names started."""
        names = {str(b["name"]).casefold() for b in self._blades.listing()["blades"]}
        for loaded in self._catalogs.listing()["catalogs"]:
            if loaded.get("source") == "blade" and str(loaded["name"]).casefold() not in names:
                await self._catalogs.remove(str(loaded["name"]), "app")
        self._state.clear()
        return self.at_start()

    async def _load(self, name: str, who: str) -> None:
        async with self._gate:
            await self.ws.live.broadcast({"type": "catalog_loading", "name": name, "state": "loading"})
            try:
                await self._blades.refresh(self._blades.get(name), {}, who)
                state = "loaded"
            except NeedsValues as error:
                state = "failed"
                self._state[name.casefold()] = {"state": state, "error": f"needs {', '.join(error.missing)}"}
            except Exception as error:  # the source's own failure: kept to show, never raised here
                state = "failed"
                self._state[name.casefold()] = {"state": state, "error": str(error)[:500]}
            await self.ws.live.broadcast({"type": "catalog_loading", "name": name, "state": state})
