"""Files that refresh themselves (the owner, 2026-11-18: "Agreed"): a table read from a file on disk (CSV,
Parquet, Excel, JSON) is watched; when the file changes, the page's tab and the table's title say "Changed on
disk" with Reload (its steps kept) and Not now. Never reloaded by itself.

The server looks (a stat of each file every few seconds, off the event loop), so the browser and the desktop
app see the same. A table loaded or reloaded is stamped with its file as it is then (by the store's version);
a later look that finds another size or modification time says it changed, once, with the `file_changed`
notice. Not now takes the file as it is now as the stamp: said again only when it changes again. A file that
is gone is not said (Reload could not read it).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.workspace import NotFound, Workspace

Stamp = tuple[int, int]  # the file's size and modification time (ns)


class FileWatch:
    def __init__(
        self,
        ws: Workspace,
        origin_of: Callable[[str], Origin],
        stamp: Callable[[str], Stamp | None],
        every: float = 3.0,
    ) -> None:
        self.ws = ws
        self._origin_of = origin_of
        self._stamp = stamp
        self._every = every
        self._seen: dict[str, tuple[int, Stamp | None]] = {}  # table -> (its version, its file's stamp)
        self._changed: set[str] = set()

    def _file(self, name: str) -> str | None:
        origin = self._origin_of(name)
        return origin.path if origin.kind == "file" and origin.path else None

    def changed(self, name: str) -> bool:
        return name in self._changed

    def listing(self) -> dict[str, Any]:
        return {"changed": sorted(self._changed)}

    async def look(self) -> list[str]:
        """One look at every watched file; the tables whose file changed since (said now)."""
        infos = {i.name: i for i in self.ws.store.all()}
        for gone in [n for n in self._seen if n not in infos]:
            self._seen.pop(gone, None)
            self._changed.discard(gone)
        said: list[str] = []
        paths = {name: self._file(name) for name in infos}
        watched = {name: path for name, path in paths.items() if path is not None}
        # Every watched file looked at in one trip off the loop (a thread each was a hop per table).
        stamps = await asyncio.to_thread(lambda: {name: self._stamp(path) for name, path in watched.items()})
        for name, info in infos.items():
            if name not in watched:
                self._seen.pop(name, None)
                self._changed.discard(name)
                continue
            now = stamps[name]
            seen = self._seen.get(name)
            if seen is None or seen[0] != info.version:
                # Loaded or reloaded: the file as it is now.
                self._seen[name] = (info.version, now)
                self._changed.discard(name)
                continue
            if now is not None and now != seen[1] and name not in self._changed:
                self._changed.add(name)
                said.append(name)
                await self.ws.live.broadcast({"type": "file_changed", "dataset": name, "changed": True})
        return said

    async def not_now(self, name: str, who: str) -> dict[str, Any]:
        """Not now: the table stays as it is; said again only when its file changes again."""
        info = self.ws.store.get(name)
        path = self._file(name)
        if info is None or path is None:
            raise NotFound(f"No table named {name!r} read from a file is open.")
        self._seen[name] = (info.version, await asyncio.to_thread(self._stamp, path))
        if name in self._changed:
            self._changed.discard(name)
            await self.ws.live.broadcast({"type": "file_changed", "dataset": name, "changed": False})
        self.ws.audit.write(who, "file_not_now", name)
        return {"dataset": name, "changed": False}

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self._every)
            try:
                await self.look()
            except Exception:  # noqa: S112 (a look that failed: the next one tries again)
                continue
