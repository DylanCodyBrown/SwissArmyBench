"""The panels' switches (domain/panels.py): Settings and the agent read and set them; every window
follows at once (the `panels_changed` notice). Memory only: every panel is on again when
Swiss Army Bench starts."""

from __future__ import annotations

from typing import Any

from swissarmybench.domain import panels as rules
from swissarmybench.services.workspace import Workspace


class Panels:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._state = rules.defaults()

    def get(self) -> dict[str, Any]:
        return {"panels": rules.listing(self._state)}

    async def set(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Turn panels on or off: {"workbench.console": false, ...}."""
        changed = rules.changes(body)
        self._state |= changed
        said = ", ".join(f"{panel} {'on' if on else 'off'}" for panel, on in changed.items())
        self.ws.audit.write(who, "panels", said)
        listed = self.get()
        await self.ws.live.broadcast({"type": "panels_changed"} | listed)
        return listed
