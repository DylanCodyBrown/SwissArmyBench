"""The Desktop extension's use cases, for the user's tray and the agent alike (the golden rule): what the shell
shows (desktop_status) and a page opened in it (desktop_open: the tray menu's Open, Workbench, Blades)."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from swissarmybench_desktop.domain import windows as rules


class ShellPort(Protocol):
    def status(self) -> dict[str, Any]: ...

    def open(self, page: str) -> bool: ...


class AuditPort(Protocol):
    def write(self, actor: str, action: str, dataset: str | None = None, **details: Any) -> None: ...


class Desktop:
    def __init__(self, shell: ShellPort, audit: AuditPort, qt_version: str = "") -> None:
        self._shell = shell
        self._audit = audit
        self._qt = qt_version

    async def status(self) -> dict[str, Any]:
        said = await asyncio.to_thread(self._shell.status)
        windows = [
            {k: str(w.get(k) or "") for k in ("kind", "title", "page")}
            for w in said.get("windows") or []
            if isinstance(w, dict)
        ]
        return {
            "name": "Desktop",
            "running": said.get("running") is True,
            "tray": said.get("tray") is True,
            "windows": windows,
            "qt": self._qt,
        }

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"page": "home" | "workbench" | "blades"}: that page in the shell (started when it is not)."""
        word = body.get("page", "home") if isinstance(body, dict) else None
        page = rules.page_for(word if isinstance(word, str) else "")
        if not await asyncio.to_thread(self._shell.open, page):
            raise rules.ShellError(
                "The Desktop app cannot open here: it needs Qt WebEngine and a desktop to show its windows on."
            )
        self._audit.write(who, "desktop_open", page=word)
        return {"opened": word}
