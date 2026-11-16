"""Getting around, for the agent (domain/navigation.py): `app_navigate` sends a window Home, Back, Forward
or to a named view, as the user moves it (the mark, the browser's buttons, a tab, a dialog). The window
does the move itself (web/src/nav.ts, the `navigate` notice); the server checks the place and that such a
window is open, and writes the move to the audit log. Nothing is kept."""

from __future__ import annotations

from typing import Any

from swissarmybench.domain import navigation as rules
from swissarmybench.services.workspace import Conflict, Workspace

# Said when no window of that kind is open, with how to open one.
NOT_OPEN: dict[str, str] = {
    "home": "No home window is open: the tray's Open, or `swissarmybench open`, opens it.",
    "catalog": "No blades page is open: the home page's Blades and catalog opens it.",
    "workbench": "No Workbench window is open: the home page's Workbench tab opens it.",
}


class Navigation:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws

    async def go(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Send a window somewhere: {"to": "visualizations"}, {"window": "catalog", "to": "blade:x"}."""
        if not isinstance(body, dict):
            raise rules.NavigationError('Send {"to": "home"} (and "window": home, catalog or workbench).')
        notice = rules.place(body.get("window"), body.get("to"), body.get("new_window"))
        live = self.ws.live
        window = notice["window"]
        message = {"type": "navigate"} | notice | {"by": who}
        if window == "workbench":
            # The Workbench window the user was last in, as workbench_window's commands are.
            if not live.workbench_open() or not await live.tell_workbench(message):
                raise Conflict(NOT_OPEN[window])
        else:
            if not (live.page_open() if window == "home" else live.catalog_open()):
                raise Conflict(NOT_OPEN[window])
            await live.broadcast(message)
        self.ws.audit.write(who, "navigate", rules.said(notice))
        return {"sent": notice}
