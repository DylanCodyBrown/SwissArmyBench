"""Connection colours (domain/connection_colours.py): every connection's colour for every page and the
agent, a colour chosen (on its card, its detail, or by the agent: connections_colours), a new connection's
next free one, and which connections a document's cells name (the marks the Workbench draws).

A colour is kept in the connection's own record (the blade store: the open project's .sab/blades, or this
computer's), so it travels with the project and holds no secret. Every window follows a change at once
(the `connection_colours_changed` notice); a connection saved, removed or a project opened is the
`blades_changed` and `project_changed` notices the pages already hear.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from swissarmybench.domain import connection_colours as rules
from swissarmybench.domain import connection_usage
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import connection_kind
from swissarmybench.services.blades import BladeService
from swissarmybench.services.workspace import NotFound, Workspace

MAX_CELLS = 2_000
MAX_SOURCE = 200_000


class ConnectionColours:
    def __init__(
        self, ws: Workspace, blades: BladeService, kinds: Callable[[], Mapping[str, str]] = dict
    ) -> None:
        self.ws = ws
        self._blades = blades
        self._kinds = kinds  # the kind colours the user chose (services/kind_colours.py): the rail's

    def _connections(self) -> list[Blade]:
        return [b for b in self._blades.everything() if connection_kind(b.kind, b.template)]

    def get(self) -> dict[str, Any]:
        """Each connection's colour (its kept one, or the next free one in turn), each theme's, and the
        palette."""
        return rules.listing([(b.name, b.colour) for b in self._connections()], self._kinds())

    def for_new(self) -> str:
        """The colour a new connection is given: the palette's next free one."""
        worn = rules.assign([(b.name, b.colour) for b in self._connections()], self._kinds())
        return rules.next_free(worn.values(), self._kinds())

    def check(self, colour: Any) -> str | None:
        """A colour as sent, refused when it is one of the rail's (the message says which)."""
        return rules.check(colour, self._kinds())

    async def set(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Choose a connection's colour: {"colour": "#0e7c7b"} (null: the next free one in turn)."""
        if not isinstance(body, dict) or "colour" not in body:
            raise ValueError('Send {"colour": "#0e7c7b"} (null: the next free one).')
        colour = self.check(body["colour"])
        found = next((b for b in self._connections() if b.name.casefold() == name.casefold()), None)
        if found is None:
            raise NotFound(f"There is no connection called {name}.")
        self._blades.set_colour(found.name, colour)
        self.ws.audit.write(who, "connection_colour", f"{found.name} {colour or 'next free'}")
        listed = self.get()
        await self.ws.live.broadcast({"type": "connection_colours_changed"} | listed)
        return listed

    def uses(self, body: Any) -> dict[str, Any]:
        """The connections each cell names (only connections that exist, by their own spelling):
        {"cells": [{"kind": "code", "source": "..."}, {"kind": "sql", "connection": "Warehouse"}]} ->
        {"cells": [["Warehouse"], ...]}. Nothing runs: Python is read with ast."""
        cells = body.get("cells") if isinstance(body, dict) else None
        if not isinstance(cells, list) or len(cells) > MAX_CELLS:
            raise ValueError(
                f'Send {{"cells": [{{"kind": "code", "source": "..."}}]}} (at most {MAX_CELLS}).'
            )
        names = [b.name for b in self._connections()]
        out: list[list[str]] = []
        for cell in cells:
            if not isinstance(cell, dict):
                out.append([])
                continue
            source = str(cell.get("source") or "")[:MAX_SOURCE]
            named = cell.get("connection") if isinstance(cell.get("connection"), str) else None
            found: list[str] = []
            for said in connection_usage.cell_connections(str(cell.get("kind") or ""), source, named):
                own = next((n for n in names if connection_usage.same_name(n, said)), None)
                if own and own not in found:
                    found.append(own)
            out.append(found)
        return {"cells": out}
