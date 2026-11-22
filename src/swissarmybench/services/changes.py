"""The change log (domain/changes.py: the rules; Plans/changes.plan.md).

A service that changes something raises one event: it puts the change (rules.change: the object, the
structural difference, the words, the fingerprints) on the audit entry it writes (`change=`), or writes one
of its own (`changed`). The audit as every service writes it (services/session_log.py Heard) hands it here
and to the Session page, so both hear the same event. Here it is stamped (when, who: the user, the agent,
the app itself) and written as it happens, one line, to the open project's .sab/changes.jsonl (Git-ignored,
everything kept: this computer's changes only); with no project open it stays in memory for the session.
Never a value.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import changes as rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain.blades import Blade

CHANGES_FILE = ".sab/changes.jsonl"


class Files(Protocol):
    def read(self, path: str) -> str | None: ...

    def append(self, path: str, text: str) -> None: ...


def raised(
    kind: str,
    name: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    words: str = "",
    by: str = "",
) -> dict[str, Any]:
    """The audit details that carry a change: {"change": ...}, or {} when nothing changed (so a service
    writes `audit.write(who, action, dataset, **raised(...))` whatever happened). `by`: "app" when the app
    itself saw it (an API's drift), whoever's call it was."""
    made = rules.change(kind, name, before, after, words)
    if made is None:
        return {}
    return {"change": made | ({"by": by} if by else {})}


_NOT_SETTINGS = ("code", "path", "created_at", "updated_at", "stamp", "source")


def _connection_shape(blade: Blade | None) -> dict[str, Any] | None:
    """A connection's settings and sign-in: each setting its code names, its header's fields and its code,
    each by name (their values fingerprinted, never kept). None: not a connection (a blade's own code is
    not in the log)."""
    if blade is None or not connection_rules.is_connection(blade.kind, blade.template):
        return None
    header = {k: v for k, v in blade.to_json().items() if k not in _NOT_SETTINGS}
    settings = {s.name: s.value for s in blade_rules.detect_settings(blade.code)}
    return {"settings": settings, "header": header, "code": {"code": blade.code}}


def connection_change(was: Blade | None, now: Blade) -> dict[str, Any]:
    """The audit's change for a saved connection (services/blades.py): {} when nothing it says moved, or
    when it is not a connection."""
    after = _connection_shape(now)
    return raised("connection", now.name, _connection_shape(was), after) if after is not None else {}


class ChangeLog:
    def __init__(self, files: Files, project: Callable[[], str | None], now: Callable[[], str]) -> None:
        self._files = files
        self._project = project
        self._now = now
        self._lock = threading.Lock()
        self._session: list[rules.Change] = []  # with no project open (memory only)

    def heard(self, actor: str, action: str, dataset: str | None, details: Mapping[str, Any]) -> None:
        """An audit entry was written: its change, kept (as it happens)."""
        made = details.get("change")
        if not isinstance(made, dict) or not isinstance(made.get("object"), dict):
            return
        mine = {k: v for k, v in made.items() if k != "by"}
        event = rules.stamped(mine, self._now(), str(made.get("by") or actor))
        project = self._project()
        with self._lock:
            if project:
                self._files.append(f"{project}/{CHANGES_FILE}", rules.line(event))
            else:
                self._session.append(event)

    def events(self) -> list[rules.Change]:
        project = self._project()
        if not project:
            with self._lock:
                return list(self._session)
        return rules.parse(self._files.read(f"{project}/{CHANGES_FILE}") or "")

    def view(self, query: Mapping[str, Any]) -> dict[str, Any]:
        """The agent's changes(action, object, n, since, kind, who, word) (ChangesError for a bad one)."""
        try:
            most = int(query.get("n") or 20)
        except (TypeError, ValueError):
            raise rules.ChangesError("n is a whole number.") from None
        action = str(query.get("action") or "last")
        said = {k: str(query.get(k) or "") for k in ("since", "kind", "who", "word")}
        return {"action": action} | rules.view(
            self.events(), action, str(query.get("object") or ""), most, **said
        )
