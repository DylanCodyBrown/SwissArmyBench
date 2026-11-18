"""The server's life follows the app (domain/lifecycle.py): it stops once no window of the app is open, after
a grace, unless a client that is not a page (the agent, VS Code, a push, a kernel) was here in the last ten
minutes or something is at work. The same clean stop as `swissarmybench stop`; first the open project's
unsaved changes are saved the way Autosave does, or, with Autosave off, the stop waits (`held`).

The agent reads it with app_lifecycle; the desktop app tells it when its last window closed (POST
/lifecycle/closed), so closing the app stops the server at once when nothing else holds it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from swissarmybench.domain import lifecycle as rules

# Requests that wait for something by design (a Python session's listener, the agent's event wait): they
# count as a client's visit, not as work under way.
WAITING_PATHS: tuple[str, ...] = ("/processes/", "/agent/events", "/agent/inbox", "/ws")


class Lifecycle:
    def __init__(
        self,
        *,
        windows: Callable[[], int],
        busy: Callable[[], list[str]],
        before_stop: Callable[[], Awaitable[str]],
        stop: Callable[[], None] | None,
        clock: Callable[[], float] = time.monotonic,
        grace: float = rules.GRACE_SECONDS,
        idle: float = rules.IDLE_SECONDS,
        start_grace: float = rules.START_GRACE_SECONDS,
    ) -> None:
        self._windows = windows
        self._busy = busy
        self._before_stop = before_stop
        self._stop = stop
        self._clock = clock
        self._grace, self._idle, self._start_grace = grace, idle, start_grace
        self.life = rules.Life(started=clock())
        self._in_flight = 0
        self.stopped = False

    # ----- what the doors report -----

    def request(self, path: str, who: str, by_token: bool, started: bool) -> None:
        """A request through the guard: one with the token is a client's visit (at its start and its end);
        while one is under way (not one that waits by design) the server is at work."""
        if not rules.counts_as_client(path, by_token):
            return
        self.life.client_at = self._clock()
        self.life.client = who
        if any(path.startswith(p) for p in WAITING_PATHS):
            return
        self._in_flight += 1 if started else -1
        self._in_flight = max(0, self._in_flight)

    def closed(self) -> dict[str, Any]:
        """The desktop app closed its last window: stop as soon as nothing else holds the server."""
        self.life.closed_at = self._clock()
        return self.state()

    # ----- working it out -----

    def look(self) -> float | None:
        now = self._clock()
        count = self._windows()
        if count > 0:
            self.life.windows_gone_at = None
        elif self.life.windows > 0 or (self.life.windows_gone_at is None and self.life.closed_at is not None):
            self.life.windows_gone_at = now
        self.life.windows = count
        busy = list(self._busy())
        if self._in_flight:
            busy.append("a request under way")
        if busy:  # a client at work (VS Code connected, a request under way) is a client here now
            self.life.client_at = now
            self.life.client = self.life.client if self._in_flight else busy[0]
        self.life.busy = busy
        return rules.stop_at(self.life, self._grace, self._idle, self._start_grace)

    def state(self) -> dict[str, Any]:
        at = self.look()
        said = rules.state(self.life, self._clock(), at)
        said["rule"] = (
            f"Stops {round(self._grace)} s after the last window closes, or {round(self._idle / 60)} minutes "
            "after the last request of the agent, VS Code or Python, whichever is later."
        )
        return said

    async def tick(self) -> bool:
        """One look: True once the server was told to stop."""
        if self.stopped:
            return True
        at = self.look()
        if at is None or self._clock() < at:
            self.life.held = ""
            return False
        held = await self._before_stop()
        self.life.held = held
        if held or self._stop is None:
            return False
        self.stopped = True
        self._stop()
        return True

    async def run_forever(self, every: float = 1.0) -> None:
        while not await self.tick():
            await asyncio.sleep(every)
