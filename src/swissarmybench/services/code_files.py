"""Code files that update themselves everywhere (the owner, 2026-11-21: "and scripts autoupdate when they are
touched anywhere in the app").

One source of truth, the file: whatever changes a code file (a save in any window, the agent's edit, a rename,
an export of data.py, a team Pull, an editor outside the app) the server says so once with the `file_changed`
notice {"type", "path" (whole), "hash" (its text's, or null when it is gone), "by"}. Every page that holds the
file reloads it (an unchanged editor in place, keeping its cursor; one with unsaved edits asks: Reload, Keep
mine, Compare). The app's own writes are said at once (`touched`); anything else within a few seconds: the
open
project's .py and .ipynb files and the library's code files are looked at (a stat each, off the event loop),
and a changed one is read and hashed. Generic: the Blades IDE and any page subscribes to the same notice.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

from swissarmybench.services.workspace import Workspace

Stamp = tuple[int, int]


class CodeFiles:
    def __init__(
        self,
        ws: Workspace,
        folders: Callable[[], Iterable[str | None]],
        stamp: Callable[[str], Stamp | None],
        hash_of: Callable[[str], str | None],
        listing: Callable[[str | None], list[str]],
        resolve: Callable[[str], str],
        every: float = 3.0,
    ) -> None:
        self.ws = ws
        self._folders = folders  # the open project's folder, the library's
        self._every = every
        self._stamp = stamp
        self._hash_of = hash_of
        self._listing = listing
        self._resolve = resolve
        self._seen: dict[str, tuple[Stamp | None, str | None]] = {}
        # Told of each write of the app's (a made file saved by hand: services/project_scope.py saw).
        self.listeners: list[Callable[[str, str], None]] = []

    async def touched(self, path: str, who: str = "user") -> str | None:
        """The app wrote `path` (or took it away): said now, to every window. Its new hash."""
        full = self._resolve(path)
        for listener in self.listeners:
            listener(full, who)
        stamp, digest = await asyncio.to_thread(lambda: (self._stamp(full), self._hash_of(full)))
        before = self._seen.get(full)
        self._seen[full] = (stamp, digest)
        if before is None or before[1] != digest or who != "outside":
            await self.ws.live.broadcast({"type": "file_changed", "path": full, "hash": digest, "by": who})
        return digest

    async def hash_now(self, path: str) -> str | None:
        """The file's hash as it is now (an open's answer carries it: the page compares a notice with it)."""
        return await asyncio.to_thread(self._hash_of, self._resolve(path))

    async def look(self) -> list[str]:
        """One look at the watched files: those changed since the last look (each said once)."""

        def scan() -> dict[str, Stamp | None]:
            paths: set[str] = set()
            for folder in self._folders():
                paths.update(self._listing(folder))
            paths.update(p for p in self._seen if p not in paths)  # one that was there: gone now?
            return {p: self._stamp(p) for p in paths}

        stamps = await asyncio.to_thread(scan)
        said: list[str] = []
        first = not self._seen
        for path, stamp in stamps.items():
            before = self._seen.get(path)
            if before is not None and before[0] == stamp:
                continue
            if stamp is None and before is None:
                continue
            digest = None if stamp is None else await asyncio.to_thread(self._hash_of, path)
            self._seen[path] = (stamp, digest)
            if stamp is None:
                self._seen.pop(path, None)
            if before is None and first:
                continue  # the first look only learns what is there
            if before is not None and before[1] == digest:
                continue  # touched, the same text
            said.append(path)
            await self.ws.live.broadcast(
                {"type": "file_changed", "path": path, "hash": digest, "by": "outside"}
            )
        return said

    async def run_forever(self) -> None:
        while True:
            try:
                await self.look()
            except Exception:  # noqa: S110 (a folder that went away: the next look again)
                pass
            await asyncio.sleep(self._every)
