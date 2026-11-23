"""Getting around, for the agent (domain/navigation.py): `app_navigate` sends a window Home, Back, Forward
or to a named view, as the user moves it (the mark, the browser's buttons, a tab, a dialog). The window
does the move itself (web/src/nav.ts, the `navigate` notice); the server checks the place and that such a
window is open, and writes the move to the audit log. Nothing is kept."""

from __future__ import annotations

from typing import Any, Protocol

from swissarmybench.domain import navigation as rules
from swissarmybench.services.workspace import Conflict, Workspace

# Said when no window of that kind is open, with how to open one.
NOT_OPEN: dict[str, str] = {
    "home": "No home window is open: the app's launcher, or `swissarmybench open`, opens it.",
    "workbench": "No Notebooks or Scripts page is open: the rail's Notebooks or Scripts opens it.",
    "notebooks": "No Notebooks page is open: the rail's Notebooks opens it.",
    "scripts": "No Scripts page is open: the rail's Scripts opens it.",
}


class Kept(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class _Memory:
    def __init__(self) -> None:
        self.data: Any = None

    def read(self) -> Any:
        return self.data

    def write(self, data: Any) -> None:
        self.data = data


class Navigation:
    def __init__(self, ws: Workspace, kept: Kept | None = None, frontend: Kept | None = None) -> None:
        self.ws = ws
        # The rail's names on or off: this computer's choice (rail.json), shared by every window.
        self._kept: Kept = kept or _Memory()
        self._labels = rules.rail_labels(self._kept.read())
        # Which front end the app opens (frontend.json): blazor (the default since the swap) or classic;
        # SWISSARMYBENCH_FRONTEND wins (the classic pages' tests).
        self._frontend_file: Kept = frontend or _Memory()
        override = ws.settings.frontend_override
        self._frontend = rules.frontend({"frontend": override} if override else self._frontend_file.read())

    def frontend(self) -> dict[str, Any]:
        return {"frontend": self._frontend, "home": rules.HOME_PAGES[self._frontend]}

    async def set_frontend(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The front end the app opens: {"frontend": "classic"} or {"frontend": "blazor"}."""
        self._frontend = rules.frontend_change(body)
        self._frontend_file.write({"frontend": self._frontend})
        self.ws.audit.write(who, "frontend", self._frontend)
        said = self.frontend()
        await self.ws.live.broadcast({"type": "frontend_changed"} | said)
        return said

    def rail(self) -> dict[str, Any]:
        return {"labels": self._labels}

    async def set_rail(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The rail with its names ({"labels": true}) or the icons alone ({"labels": false})."""
        self._labels = rules.rail_change(body)
        self._kept.write({"labels": self._labels})
        self.ws.audit.write(who, "rail", "names on" if self._labels else "names off")
        said = self.rail()
        await self.ws.live.broadcast({"type": "rail_changed"} | said)
        return said

    async def go(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Send a window somewhere: {"to": "analyze"}, {"window": "catalog", "to": "blade:x"}."""
        if not isinstance(body, dict):
            raise rules.NavigationError('Send {"to": "home"} (and "window": home, catalog or workbench).')
        notice = rules.place(body.get("window"), body.get("to"), body.get("new_window"))
        live = self.ws.live
        window = notice["window"]
        # The Notebooks or Scripts page's window (either for "workbench"): the notice says "workbench".
        page = window if window in rules.CODE_WINDOWS else None
        message = {"type": "navigate"} | notice | {"by": who}
        if page is not None or window == "workbench":
            message["window"] = "workbench"
            # The Workbench window the user was last in, as workbench_window's commands are.
            if not live.workbench_open(page) or not await live.tell_workbench(message, page):
                raise Conflict(NOT_OPEN[window])
        else:
            if not live.page_open():
                raise Conflict(NOT_OPEN[window])
            await live.broadcast(message)
        self.ws.audit.write(who, "navigate", rules.said(notice))
        return {"sent": notice}
