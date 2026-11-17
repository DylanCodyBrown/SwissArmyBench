"""Connection colours (domain/connection_colours.py): every connection's colour for every page and the
agent, a colour chosen (on its card, its detail, or by the agent: connections_colours), a new connection's
next free one, and which connections a document's cells name (the marks the Workbench draws).

A colour is this computer's, the same in every project (the owner, 2026-11-17: connections are a library
outside any project): colours.toml, keyed by the connection's name (adapters/connection_colours.py; the
library's colours.toml later, by a path). No secret is in it. Every window follows a change at once
(the `connection_colours_changed` notice); a connection saved, removed or a project opened is the
`blades_changed` and `project_changed` notices the pages already hear.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import connection_colours as rules
from swissarmybench.domain import connection_usage
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import connection_kind
from swissarmybench.services.blades import BladeService
from swissarmybench.services.workspace import NotFound, Workspace

MAX_CELLS = 2_000
MAX_SOURCE = 200_000


class Kept(Protocol):
    """colours.toml's text (adapters/connection_colours.py)."""

    def read(self) -> str: ...

    def write(self, text: str) -> None: ...


class ConnectionColours:
    def __init__(
        self,
        ws: Workspace,
        blades: BladeService,
        kept: Kept,
        kinds: Callable[[], Mapping[str, str]] = dict,
    ) -> None:
        self.ws = ws
        self._blades = blades
        self._kept = kept
        self._kinds = kinds  # the kind colours the user chose (services/kind_colours.py): the rail's

    def _chosen(self) -> dict[str, str]:
        return rules.from_toml(self._kept.read())

    def _own(self, name: str) -> str | None:
        """The colour kept for a connection (its name's spelling may differ in case)."""
        chosen = self._chosen()
        return chosen.get(name) or next(
            (c for n, c in chosen.items() if n.casefold() == name.casefold()), None
        )

    def _keep(self, name: str, colour: str | None, old: str | None = None) -> None:
        chosen = {
            n: c
            for n, c in self._chosen().items()
            if n.casefold() not in {name.casefold(), (old or "").casefold()}
        }
        if colour:
            chosen[name] = colour
        self._kept.write(rules.to_toml(chosen))

    def _pairs(self) -> list[tuple[str, str | None]]:
        chosen = {n.casefold(): c for n, c in self._chosen().items()}
        return [(b.name, chosen.get(b.name.casefold())) for b in self._connections()]

    def _connections(self) -> list[Blade]:
        return [b for b in self._blades.everything() if connection_kind(b.kind, b.template)]

    def get(self) -> dict[str, Any]:
        """Each connection's colour (its kept one, or the next free one in turn), each theme's, and the
        palette."""
        return rules.listing(self._pairs(), self._kinds())

    def for_new(self) -> str:
        """The colour a new connection is given: the palette's next free one."""
        worn = rules.assign(self._pairs(), self._kinds())
        return rules.next_free(worn.values(), self._kinds())

    def saved(self, name: str, previous: str | None, sent: str | None) -> None:
        """A connection was saved from its form (ConnectionService): a colour sent with it is kept; a new
        one is given the palette's next free colour; a renamed one keeps its colour under its new name."""
        if sent is not None:
            self._keep(name, sent, previous)
        elif previous is None:
            if self._own(name) is None:
                free = rules.next_free(
                    [c for n, c in rules.assign(self._pairs(), self._kinds()).items() if n != name],
                    self._kinds(),
                )
                self._keep(name, free)
        elif previous != name:
            colour = self._own(previous)
            if colour:
                self._keep(name, colour, previous)

    def colour_of(self, name: str) -> str | None:
        """The colour a connection wears now (kept, else the next free one in its turn)."""
        return rules.assign(self._pairs(), self._kinds()).get(name)

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
        self._keep(found.name, colour)
        self.ws.audit.write(who, "connection_colour", found.name, colour=colour or "")
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
