"""What's New (the owner, 2026-11-25: "a what's new page that opens and closes as an overlay when a user
update"): the package's WHATSNEW.md read through domain/whats_new.py, and the version last seen on this
computer (whats_new.json, the version only).

  state     what the main window asks as it opens: every release newer than the one last seen (the newest
            first), and `open` when the running version is newer than that (the first start after an
            update). A brand new install (nothing seen yet) records the running version and opens nothing.
            `all` (Help's What's new, the status bar's version) or `since` (the agent) choose the releases
  seen      the window closed (X, Esc, outside, Got it): the running version is the one last seen. The user's
            own: the agent opens the window, the user closes it
  show      every main window opens the window (`whats_new_open`): the agent's app_whats_new, on the screen
"""

from __future__ import annotations

from typing import Any, Protocol

from swissarmybench.domain import whats_new as rules
from swissarmybench.services.ports import Audit, Notifier
from swissarmybench.services.workspace import Refused

AGENT_CLOSES = (
    "Closing What's New, which marks it seen, is the user's own: the agent opens it, the user closes it."
)


class WhatsNewPort(Protocol):
    """adapters/updates.py WhatsNewFiles."""

    def text(self) -> str: ...

    def seen(self) -> str | None: ...

    def write_seen(self, version: str) -> None: ...


class WhatsNew:
    def __init__(self, current: str, files: WhatsNewPort, live: Notifier, audit: Audit) -> None:
        self.current = current
        self._files = files
        self._live = live
        self._audit = audit

    def releases(self) -> list[rules.Release]:
        try:
            return rules.parse(self._files.text())
        except rules.WhatsNewError:
            return []  # a file out of shape (the tests stop one shipping): the window has nothing to say

    def state(self, since: str | None = None, every: bool = False) -> dict[str, Any]:
        seen = self._files.seen()
        if seen is None:
            self._files.write_seen(self.current)  # a brand new install: recorded, nothing to show
        opens = rules.should_open(self.current, seen)
        found = self.releases()
        if every:
            shown = found
        elif since:
            shown = rules.newer_than(found, since)
        else:
            shown = rules.newer_than(found, seen, self.current) if opens else []
        return {
            "version": self.current,
            "seen": seen or self.current,
            "open": opens,
            "releases": [r.to_json() for r in shown],
        }

    async def seen(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        if who == "agent":
            raise Refused(AGENT_CLOSES)
        self._files.write_seen(self.current)
        return {"version": self.current, "seen": self.current, "open": False}

    async def show(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        await self._live.broadcast({"type": "whats_new_open"})
        self._audit.write(who, "whats_new_open", None)
        return {"shown": True}
