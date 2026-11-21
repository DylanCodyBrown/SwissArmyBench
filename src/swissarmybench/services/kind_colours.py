"""Kind colours (domain/kind_colours.py): Settings and the agent read and set them; every window follows
at once (the `kind_colours_changed` notice). They last across restarts: a colour is a
choice the user made on purpose, kept in kind_colours.json in the state folder."""

from __future__ import annotations

from typing import Any, Protocol

from swissarmybench.domain import kind_colours as rules
from swissarmybench.services.workspace import Workspace


class Kept(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class KindColours:
    def __init__(self, ws: Workspace, kept: Kept) -> None:
        self.ws = ws
        self._kept = kept
        self._chosen = rules.read_saved(kept.read())

    def chosen(self) -> dict[str, str]:
        """The colours the user chose (a kind not here wears its theme's own)."""
        return dict(self._chosen)

    def get(self) -> dict[str, Any]:
        return rules.listing(self._chosen)

    async def set(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Choose kinds' colours: {"app": "#7b3fc4", "script": null} (null: the theme's own again)."""
        for kind, colour in rules.check(body).items():
            if colour is None:
                self._chosen.pop(kind, None)
            else:
                self._chosen[kind] = colour
        self._kept.write(dict(self._chosen))
        said = ", ".join(f"{kind} {colour}" for kind, colour in self._chosen.items()) or "defaults"
        self.ws.audit.write(who, "kind_colours", said)
        listed = self.get()
        await self.ws.live.broadcast({"type": "kind_colours_changed"} | listed)
        return listed
