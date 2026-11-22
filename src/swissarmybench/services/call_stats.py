"""The statistics of every call (domain/call_stats.py: the rules; Plans/stats.plan.md).

Three ears, one record each:
  adapter    adapter.observe's hook in this process (the sandbox, a file connection, an open table's read):
             the caller from the request (services/connection_slots.py CURRENT); the app's own session (a
             grid's window, the open tables) is not a call
  finished   a connection's call through its slots (ConnectionSlots.on_finished: the Queries window's
             finished entry, with the adapter's facts its child process sent back)
  api        an API action's envelope (services/actions.py, its `where`) and api_adapter.observe's hook for
             any other run in this process (a run inside own() is said by its caller instead)

The calls are kept in memory for this session (the last few thousand); the running figures per table,
connection and endpoint go with the open project in .sab/stats.json (Git-ignored), written only when they
change, a few seconds after a call settles, and when the project changes. Never a value. A hook runs on any
thread, so the state is under one lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextvars import ContextVar
from typing import Any, Protocol

from swissarmybench.domain import call_stats as rules
from swissarmybench.services.connection_slots import CURRENT

KEPT_CALLS = 3000
FLUSH_SECONDS = 3.0
OWN_SOURCES = frozenset({"DuckDB", "the open tables"})  # the app's own engine session: not a call
STATS_FILE = ".sab/stats.json"

_OWN: ContextVar[bool] = ContextVar("sab_stats_own", default=False)


class Files(Protocol):
    def read(self, path: str) -> str | None: ...

    def write(self, path: str, text: str) -> None: ...  # atomically, only when the bytes change


class CallStats:
    def __init__(self, files: Files, project: Callable[[], str | None], now: Callable[[], str]) -> None:
        self._files = files
        self._project = project
        self._now = now
        self._lock = threading.Lock()
        self._calls: deque[rules.Call] = deque(maxlen=KEPT_CALLS)
        self._figures: rules.Figures = {}
        self._at: str | None = None  # the project the figures belong to
        self._dirty = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending = False

    # ===== the ears =====

    def adapter(self, facts: dict[str, Any]) -> None:
        """adapter.observe's hook: a call in this process, its caller from the request."""
        if str(facts.get("source") or "") in OWN_SOURCES:
            return
        caller = CURRENT.get()
        who = caller.role if caller is not None else "user"
        self._keep(rules.from_adapter(facts, caller.source if caller is not None else {}, who, self._now()))

    def finished(self, done: dict[str, Any], facts: list[Any]) -> None:
        """A connection's call through its slots, finished (the Queries window's entry)."""
        self._keep(rules.from_ticket(done, [f for f in facts if isinstance(f, dict)], self._now()))

    def api(self, answer: Mapping[str, Any], where: Mapping[str, Any] | None = None) -> None:
        """An API action's envelope: its facts and its shape's fingerprint."""
        facts = answer.get("facts")
        if not isinstance(facts, dict):
            return
        shape = answer.get("shape")
        said = shape.get("fingerprint") if isinstance(shape, dict) else ""
        self._keep(rules.from_api(facts, str(said or ""), where or {}, self._now()))

    def api_observed(self, facts: dict[str, Any]) -> None:
        """api_adapter.observe's hook: a run in this process that no caller says itself."""
        if not _OWN.get():
            self._keep(rules.from_api(facts, "", {}, self._now()))

    @contextlib.contextmanager
    def own(self) -> Iterator[None]:
        """Runs whose caller says them itself (services/actions.py): the observe hook leaves them."""
        token = _OWN.set(True)
        try:
            yield
        finally:
            _OWN.reset(token)

    # ===== kept =====

    def _keep(self, call: rules.Call) -> None:
        with self._lock:
            self._follow_project()
            self._calls.append(call)
            rules.fold(self._figures, call)
            self._dirty = True
        self._soon()

    def _follow_project(self) -> None:
        """The figures of the open project (read when it opens; the last one's written first)."""
        now = self._project()
        if now == self._at:
            return
        self._write_locked()
        self._at = now
        said = self._files.read(f"{now}/{STATS_FILE}") if now else None
        self._figures = rules.read(said) if said else {}
        self._dirty = False

    def _write_locked(self) -> None:
        if self._dirty and self._at:
            self._files.write(f"{self._at}/{STATS_FILE}", rules.text(self._figures))
        self._dirty = False

    def flush(self) -> None:
        with self._lock:
            self._pending = False
            self._write_locked()

    def _soon(self) -> None:
        """A write a few seconds after the calls settle (once per wait), on the server's loop."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass  # a hook on a worker thread: the loop known from an earlier call, if any
        loop = self._loop
        if loop is None or self._pending or loop.is_closed():
            return
        self._pending = True
        loop.call_soon_threadsafe(loop.call_later, FLUSH_SECONDS, self.flush)

    # ===== read =====

    def view(self, action: str = "summary", name: str = "", n: Any = 20) -> dict[str, Any]:
        """The agent's stats(action) and the pages' figures (StatsError for a view that is not one)."""
        try:
            most = int(n) if n not in (None, "") else 20
        except (TypeError, ValueError):
            raise rules.StatsError("n is a whole number.") from None
        with self._lock:
            self._follow_project()
            calls, figures = list(self._calls), {k: dict(v) for k, v in self._figures.items()}
        return {"action": action} | rules.view(calls, figures, action or "summary", name, most)

    def figures_of(self, kind: str, names: list[str]) -> dict[str, dict[str, Any]]:
        """The figures of each named object (the Connections and APIs pages: small, out of the way)."""
        with self._lock:
            self._follow_project()
            found = {k.casefold(): v for k, v in self._figures.items()}
        out: dict[str, dict[str, Any]] = {}
        for name in names:
            one = found.get(f"{kind}:{name}".casefold())
            if one is not None:
                out[name] = rules.figure(one)
        return out
