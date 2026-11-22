"""Play follows live data (the owner, 2026-11-22: "yea live changes"). A playing page (a canvas's Play, its
Launch, a widget run alone) reads each table it names from its run's data/ folder; this hears the notices
that say a table changed (a sandbox write: an API's, a grid edit's, a Reset; an open table's steps, reload or
close; data.ipynb's data.py written) and, once a burst of them settles, has server/live_runs.py write the
changed tables again into every running run that reads them (only changed bytes) and stamp it, so its open
pages run again by themselves. Only what a notice names is read again: a sandbox write the sandbox's tables it
touched, a grid's notice the open tables (local DuckDB); another connection's table stays as the session read
it (its Refresh reads it again), so a playing page never queries a source on a timer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from swissarmybench_streamlit.domain.widget_properties import CONNECTION_TABLE, connection_of

SETTLE = 0.15  # seconds: one refresh for a burst of notices (a sandbox write and its grid's follow)
OPEN_TABLES = frozenset(
    {"dataset_updated", "dataset_closed", "dataset_renamed", "grid_updated", "grid_closed", "grid_shown"}
)
SANDBOX = "sandbox"  # the project's sandbox as DuckDB SQL names it: [Sandbox].orders


def _bare(table: str) -> str:
    return table.strip().strip('"').casefold()


class LiveTables:
    def __init__(
        self,
        runs: Any,
        read: Callable[[set[str]], Awaitable[Mapping[str, bytes]]],
        data_py: Callable[[], str | None] = lambda: None,
        is_data_py: Callable[[str], bool] = lambda path: False,
    ) -> None:
        self._runs = runs  # server/live_runs.py LiveRuns
        self._read = read  # services/widgets.py Widgets.tables_for: the tables by their file stems
        self._data_py = data_py  # the open project's data.py's text
        self._is_data_py = is_data_py  # a path the open project's data.py
        self._open = False  # an open table's notice heard
        self._sandbox: set[str] | None = set()  # the sandbox tables touched (None: all of them)
        self._data = False  # data.py written
        self._settling: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    # ===== heard =====

    def heard(self, message: Mapping[str, Any]) -> None:
        """A live notice (adapters/live_updates.py's listeners): what it changed noted, a refresh soon."""
        kind = str(message.get("type") or "")
        if kind in OPEN_TABLES:
            self._open = True
        elif kind == "sandbox_changed":
            tables = message.get("tables")
            if self._sandbox is not None and isinstance(tables, list) and tables:
                self._sandbox |= {_bare(str(t)) for t in tables}
            else:
                self._sandbox = None
        elif (
            kind == "file_changed"
            and isinstance(message.get("path"), str)
            and self._is_data_py(message["path"])
        ):
            self._data = True
        else:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._settling is not None:
            self._settling.cancel()
        self._settling = loop.call_later(SETTLE, self._start)

    def _start(self) -> None:
        self._settling = None
        task = asyncio.ensure_future(self._safely())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _safely(self) -> None:
        try:
            await self.refresh()
        except Exception:  # noqa: S110 (a playing page keeps what it read; the next change tries again)
            pass

    # ===== followed =====

    def wanted(self, opened: bool, sandbox: set[str] | None) -> Callable[[str], bool]:
        """Which of a run's table names a refresh reads again: an open table's after a grid's notice, a
        sandbox table the write touched (every one when the notice did not say)."""

        def wants(name: str) -> bool:
            connection = connection_of(name)
            if connection is None:
                return opened
            if connection.casefold() != SANDBOX:
                return False
            if sandbox is None:
                return True
            found = CONNECTION_TABLE.match(name)
            return found is not None and _bare(found.group("table")) in sandbox

        return wants

    async def refresh(self) -> list[str]:
        """The running runs brought up to date with what was heard since the last refresh: their keys."""
        opened, sandbox, data = self._open, self._sandbox, self._data
        self._open, self._sandbox, self._data = False, set(), False
        if not opened and sandbox == set() and not data:
            return []
        files = {"data.py": self._data_py()} if data else None
        changed: list[str] = await self._runs.follow(self.wanted(opened, sandbox), self._read, files)
        return changed
