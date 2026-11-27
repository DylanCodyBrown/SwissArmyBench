"""Pages and tables in windows of their own (domain/pop_outs.py; the owner, 2026-11-27): which window holds
each one, kept in memory only and told to every window over the live socket.

    a page  --POST /pop-outs, then window.open-->  its own window, which says its key on its socket
    every other window shows the placeholder where the page or table was: Reattach, Show window
    Reattach (either side), the popped-out window closed, or one that never connected: the entry goes,
    every window hears it, the old place shows the page or table again and the popped-out window closes

One owner at a time: popping out twice brings the window there is to the front. A popped-out window that
reloads says its key again as its socket opens (within RELOAD_SECONDS it never counted as closed). With no
main window open the popped-out window works on by itself (`mains` is 0: its Reattach opens a main window).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Hashable
from typing import Any

from swissarmybench.domain import pop_outs as rules
from swissarmybench.services.background import keep
from swissarmybench.services.workspace import Conflict, NotFound, Workspace

Send = Callable[[dict[str, Any]], Awaitable[None]]
NO_MAIN = "No main window is open to pop it out of: open Swiss Army Bench first."


class PopOuts:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._entries: dict[str, rules.Entry] = {}
        self._holder: dict[str, Hashable] = {}  # the window that shows each entry, once it said so
        self._windows: dict[Hashable, Send] = {}  # the app's windows, the one last in front at the end
        self._waits: dict[str, int] = {}  # each entry's latest wait: an older one that wakes does nothing

    # The windows (server/app.py's live socket).

    async def opened(self, window: Hashable, send: Send) -> None:
        self._windows[window] = send
        await self._changed_mains()

    async def closed(self, window: Hashable) -> None:
        """A window's socket closed. One that held a page or table has RELOAD_SECONDS to come back (a
        reload); after that its page or table shows in its old place again."""
        if self._windows.pop(window, None) is None:
            return
        for key in [k for k, holder in self._holder.items() if holder is window]:
            del self._holder[key]
            self._entries[key].connected = False
            self._wait(key, rules.RELOAD_SECONDS)
        await self._changed_mains()

    def focused(self, window: Hashable) -> None:
        if window in self._windows:
            self._windows[window] = self._windows.pop(window)

    async def heard(self, window: Hashable, text: str) -> bool:
        """A window's message: a popped-out window saying what it holds and where it is now. A window that
        says so with no entry (it was reloaded after its wait ran out) holds it again."""
        said = rules.read_said(text)
        if said is None or window not in self._windows:
            return False
        entry = self._entries.setdefault(said.key, said)
        before = (entry.connected, entry.address, self._holder.get(said.key))
        entry.address, entry.connected, entry.seen = said.address, True, True
        self._holder[said.key] = window
        self._waits.pop(said.key, None)
        if before != (True, entry.address, window):
            await self._tell()
        return True

    def _mains(self) -> list[Hashable]:
        holders = set(self._holder.values())
        return [w for w in self._windows if w not in holders]

    async def _changed_mains(self) -> None:
        if self._entries:  # a popped-out window's Reattach follows whether a main window is open
            await self._tell()

    # The entries.

    def listing(self) -> dict[str, Any]:
        return {"popped": [e.said() for e in self._entries.values()], "mains": len(self._mains())}

    async def _tell(self, reattached: rules.Entry | None = None) -> None:
        extra = {"reattached": reattached.said()} if reattached else {}
        await self.ws.live.broadcast({"type": rules.NOTICE} | self.listing() | extra)

    async def _tell_main(self, message: dict[str, Any]) -> bool:
        """One main window told (the one last in front): True when one took it."""
        for window in reversed(self._mains()):
            with contextlib.suppress(Exception):  # a window closed mid-send: the one before it
                await self._windows[window](message)
                return True
        return False

    def _named(self, body: Any) -> rules.Entry:
        """The entry a request names: a page's own {"key", "name", "address"}, or the agent's
        {"page": "connections"} and {"table": "<grid id>"}."""
        if isinstance(body, dict) and body.get("table") is not None:
            try:
                grid, _ = self.ws.grid_and_info(str(body["table"]))
            except LookupError as error:
                raise NotFound(str(error)) from error
            return rules.table_entry(grid.id, grid.dataset)
        if isinstance(body, dict) and body.get("page") is not None:
            return rules.page_entry(body["page"])
        return rules.read_entry(body)

    def _key(self, body: Any) -> str:
        if isinstance(body, dict) and body.get("key") is not None:
            return rules.read_key(body["key"])
        return self._named(body).key

    def _popped(self, body: Any) -> rules.Entry:
        key = self._key(body)
        if key not in self._entries:
            raise NotFound(f"{key} is not in a window of its own.")
        return self._entries[key]

    async def pop(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Pop a page or a table out. The page that asks opens the window itself ({"open": false}: a click
        may open a window); anyone else's is opened by the main window last in front. Already popped out:
        its window comes to the front."""
        entry = self._named(body)
        if entry.key in self._entries:
            await self.ws.live.broadcast({"type": rules.SHOW_NOTICE, "key": entry.key})
            return self._entries[entry.key].said() | {"existing": True}
        by_page = isinstance(body, dict) and body.get("open") is False
        opening = {"type": rules.OPEN_NOTICE} | entry.said()
        if not by_page and not await self._tell_main(opening):
            raise Conflict(NO_MAIN)
        self._entries[entry.key] = entry
        self._wait(entry.key, rules.CONNECT_SECONDS)
        self.ws.audit.write(who, "pop_out", rules.audit_words(entry))
        await self._tell()
        return entry.said() | {"existing": False}

    async def reattach(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Bring a page or table back to its old place: its window closes itself, every other shows it again
        where it is now. {"front": true} (the popped-out window's own Reattach): the main window last in
        front goes to it. {"closed": true}: the window that opened it saw it close."""
        entry = self._popped(body)
        if isinstance(body, dict) and body.get("closed") is True and (entry.connected or not entry.seen):
            # The page that opened a window saw it close, but this entry's window is there (popped out again
            # since) or still on its way: the old window's news. One that never comes has its own wait.
            return entry.said() | {"reattached": False}
        self._drop(entry.key)
        self.ws.audit.write(who, "reattach", rules.audit_words(entry))
        await self._tell(entry)
        if isinstance(body, dict) and body.get("front") is True:
            await self._tell_main({"type": rules.FRONT_NOTICE} | entry.said())
        return entry.said() | {"reattached": True}

    async def show(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Bring a popped-out window to the front."""
        entry = self._popped(body)
        await self.ws.live.broadcast({"type": rules.SHOW_NOTICE, "key": entry.key})
        return entry.said()

    async def front(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A link followed in a popped-out window that leaves what it holds: the main window last in front
        goes there ({"shown": false} with none open: the asking window opens one)."""
        address = rules.read_address(body.get("address") if isinstance(body, dict) else None)
        return {"shown": await self._tell_main({"type": rules.FRONT_NOTICE, "address": address})}

    def _drop(self, key: str) -> None:
        self._entries.pop(key, None)
        self._holder.pop(key, None)
        self._waits.pop(key, None)

    def _wait(self, key: str, seconds: float) -> None:
        turn = self._waits[key] = self._waits.get(key, 0) + 1
        keep(self._expire(key, turn, seconds), f"pop-out wait {key}")

    async def _expire(self, key: str, turn: int, seconds: float) -> None:
        await asyncio.sleep(seconds)
        entry = self._entries.get(key)
        if entry is None or entry.connected or self._waits.get(key) != turn:
            return
        self._drop(key)
        await self._tell(entry)
