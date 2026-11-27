"""The screen state kept: what each window shows, the latest report per window, for the agent to read on
demand (the owner, 2026-11-27; domain/screen.py has the shape and the rule: names only, never a value).

    page  --its report, over its live socket, when what it shows changes-->  server (memory)
    agent --app_screen / swissarmybench://screen-->  server  (from memory: no page is asked, nothing waits)

In memory only, never written to disk, never in the prompt hook nor context.md. A window is known from the
moment its socket connects (said as not reported until its first report) and dropped as its socket closes.
Each entry is stamped with when what it shows last changed. `app_snapshot` stays for when a picture is needed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from swissarmybench.domain import screen
from swissarmybench.services.workspace import NotFound

REPORT_TYPE = "screen"


@dataclass
class Window:
    """One window: its id for the agent, what it last reported and when that last changed."""

    id: str
    changed: datetime
    state: dict[str, Any] = field(default_factory=dict)
    reported: bool = False


class Screens:
    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._windows: dict[Hashable, Window] = {}
        self._made = 0

    def opened(self, key: Hashable) -> str:
        """A window connected (`key`: its socket): known at once, not reported yet. Its id."""
        if key not in self._windows:
            self._made += 1
            self._windows[key] = Window(f"w{self._made}", self._now())
        return self._windows[key].id

    def closed(self, key: Hashable) -> None:
        """A window's socket closed: what it showed is dropped."""
        self._windows.pop(key, None)

    def heard(self, key: Hashable, text: str) -> bool:
        """A message a window's socket sent: its report, when it is one. True when what it shows changed."""
        if key not in self._windows or len(text) > screen.MAX_REPORT_BYTES:
            return False
        try:
            message = json.loads(text)
        except ValueError:
            return False
        if not isinstance(message, dict) or message.get("type") != REPORT_TYPE:
            return False
        return self.report(key, message.get("state"))

    def report(self, key: Hashable, raw: object) -> bool:
        """What a window shows now. The stamp moves only when it differs from what it showed before."""
        window = self._windows.get(key)
        if window is None:
            return False
        state = screen.clean(raw)
        if window.reported and state == window.state:
            return False
        window.state, window.reported, window.changed = state, True, self._now()
        return True

    def _ordered(self) -> list[Window]:
        # The focused window first, then the one that changed last.
        latest = sorted(self._windows.values(), key=lambda w: w.changed, reverse=True)
        return sorted(latest, key=lambda w: not w.state.get("focused", False))

    def _stamp(self, window: Window) -> dict[str, Any]:
        seconds = max(0, round((self._now() - window.changed).total_seconds()))
        return {"changed": window.changed.isoformat(timespec="seconds"), "seconds_ago": seconds}

    def _full(self, window: Window) -> dict[str, Any]:
        if not window.reported:
            return {"id": window.id, "reported": False, "note": screen.NOT_REPORTED} | self._stamp(window)
        return {"id": window.id, "reported": True} | self._stamp(window) | window.state

    def _brief(self, window: Window) -> dict[str, Any]:
        if not window.reported:
            return self._full(window)
        return {"id": window.id, "reported": True} | self._stamp(window) | screen.brief(window.state)

    def read(self, window: str | None = None) -> dict[str, Any]:
        """Every window in brief (the focused one first), or one in full: by its id, `focused`, or its kind
        (tables, scripts...). Answered from memory: no page is asked."""
        ordered = self._ordered()
        if window is None or window == "":
            answer: dict[str, Any] = {"windows": [self._brief(w) for w in ordered]}
            focused = next((w.id for w in ordered if w.state.get("focused")), None)
            return (
                answer
                | ({"focused": focused} if focused else {})
                | ({} if ordered else {"note": screen.NO_WINDOWS})
            )
        wanted = window.strip().lower()
        for candidate in ordered:
            if wanted in (candidate.id, candidate.state.get("kind")) or (
                wanted == "focused" and candidate is ordered[0]
            ):
                return self._full(candidate)
        open_now = ", ".join(f"{w.id} ({w.state.get('kind', 'not reported yet')})" for w in ordered) or "none"
        raise NotFound(f"No window {window} is open. Open now: {open_now}.")
