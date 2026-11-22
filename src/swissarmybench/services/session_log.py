"""The Session page (domain/session_log.py): this session's log of what the agent (and the user) made or
changed, live, and Follow the agent.

The log hears the audit log: the composition root hands every service an audit that writes the file
(as before) and then tells this log (Heard). Each entry the rules keep gets a number and a time, is
kept in memory (this session only: the audit log is the record on disk) and goes to every page as a
`session_entry` notice, so the Session page fills in as the agent works and a page that follows the
agent moves to the object.

Follow the agent is the user's switch (the Session page, Settings): the agent reads it and is refused
the change (an agent that could turn it off could work unseen). Kept across restarts in follow.json.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import deque
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import session_log as rules
from swissarmybench.services.ports import Audit, Notifier
from swissarmybench.services.workspace import Refused

AGENT_REFUSED = (
    "Follow the agent is the user's switch: the agent reads it (app_session) but does not turn it on or off."
)


class Kept(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class SessionLog:
    def __init__(self, live: Notifier, kept: Kept, limit: int = rules.MAX_ENTRIES) -> None:
        self._live = live
        self._kept = kept
        self._entries: deque[rules.Entry] = deque(maxlen=limit)
        self._serial = itertools.count(1)
        self._follow = rules.read_saved(kept.read())
        self._tasks: set[asyncio.Task[None]] = set()

    def heard(self, actor: str, action: str, dataset: str | None, details: dict[str, Any]) -> None:
        """An audit entry was written: the Session page's entry, if the action made something."""
        made = rules.entry(actor, action, dataset, details)
        if made is None:
            return
        made = {"id": next(self._serial), "time": datetime.now(UTC).isoformat(timespec="seconds")} | made
        self._entries.append(made)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # written off the event loop: the page reads it on its next open
        task = loop.create_task(self._live.broadcast({"type": "session_entry", "entry": made}))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def listing(self, who: Any = None, limit: Any = None, changes: Any = None) -> dict[str, Any]:
        """This session's entries, newest first, by the filter (`changes`: only those that changed
        something, the change log's events); and the Follow switch."""
        shown = rules.check_filter(who)
        try:
            most = int(limit) if limit not in (None, "") else 200
        except (TypeError, ValueError):
            raise rules.SessionLogError("limit is a whole number.") from None
        entries = list(self._entries)
        if changes in (True, "1", "true", "yes"):
            entries = [e for e in entries if e.get("change")]
        return {
            "entries": rules.shown(entries, shown, min(most, rules.MAX_ENTRIES)),
            "who": shown,
            "follow": self._follow,
            "counts": {actor: sum(1 for e in entries if e["actor"] == actor) for actor in rules.ACTORS},
        }

    def follow(self) -> dict[str, Any]:
        return {"follow": self._follow}

    async def set_follow(self, body: Any, who: str) -> dict[str, Any]:
        if who == "agent":
            raise Refused(AGENT_REFUSED)
        self._follow = rules.check_follow(body)
        self._kept.write({"follow": self._follow})
        await self._live.broadcast({"type": "session_follow", "follow": self._follow})
        return self.follow()


class Changes(Protocol):
    def heard(self, actor: str, action: str, dataset: str | None, details: dict[str, Any]) -> None: ...


class Heard:
    """The audit as every service writes it: the audit log's file first, then the Session page's log, then
    the change log (services/changes.py: an entry's `change`, the same event the Session page shows)."""

    def __init__(self, inner: Audit, log: SessionLog, changes: Changes | None = None) -> None:
        self._inner = inner
        self._log = log
        self.changes = changes  # set once made (bootstrap), so every service's audit carries it

    def write(
        self,
        actor: str,
        action: str,
        dataset: str | None = None,
        query: str | None = None,
        rows: int | None = None,
        **details: Any,
    ) -> None:
        self._inner.write(actor, action, dataset, query, rows, **details)
        # Never the query's text: the Session page's entries are names and counts only.
        self._log.heard(actor, action, dataset, details | ({"rows": rows} if rows is not None else {}))
        if self.changes is not None and details.get("change"):
            self.changes.heard(actor, action, dataset, details)

    def tail(self, limit: int = 200, actor: str | None = None) -> list[dict[str, Any]]:
        return self._inner.tail(limit, actor)
