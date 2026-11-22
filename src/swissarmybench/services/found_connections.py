"""Find connections on this computer (the Connections page's Find connections on this computer…; the owner,
2026-11-20): the known tools and the hint scan read (the adapter, off the event loop), the list made
(domain/found_connections.py: merged, Already added, kinds we have no connection for), and the ticked rows
imported as library connections from their starters' code, each password a variable named and not set.

On the user's click only (never at start, never on a timer). The agent's scan reads through the user's
folders, so it waits for the user's Allow; so does its import. The last scan is kept in memory only (so an
import names rows by their ids); nothing found is logged or written anywhere until the user imports it (the
audit says counts, then the connections made).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import found_connections as rules
from swissarmybench.domain import portability
from swissarmybench.domain.blades import Template
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, Workspace

STOPPED = {
    "time": "The search stopped after a few seconds: some folders were not looked through.",
    "files": "The search stopped after its limit of files: some folders were not looked through.",
    "cancel": "Cancelled: what was found until then is listed.",
}


class Finder(Protocol):
    def scan(self, cancel: threading.Event | None = None, hints: bool = True) -> Any: ...


class Saved(Protocol):
    def listing(self) -> dict[str, Any]: ...

    def get(self, name: str) -> Any: ...


class Declare(Protocol):
    def taken(self) -> set[str]: ...

    async def declare(self, names: list[str], who: str = "user") -> list[str]: ...


class FoundConnections:
    def __init__(
        self,
        ws: Workspace,
        finder: Finder,
        templates: Sequence[Template],
        blades: Saved,
        save: Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]],
        variables: Declare,
        approvals: Approvals,
    ) -> None:
        self.ws = ws
        self._finder = finder
        self._templates = {t.id: t for t in templates}
        self._blades = blades
        self._save = save
        self._variables = variables
        self._approvals = approvals
        self._last: dict[str, rules.Row] = {}
        self._cancel: threading.Event | None = None
        self._ways: dict[tuple[str, bool], list[dict[str, str]]] = {}

    def _labels(self) -> dict[str, str]:
        return {t.id: t.label for t in self._templates.values()}

    async def _allow(self, who: str, action: str, detail: str) -> None:
        await self._approvals.allowed(
            who, subject="Connections", action=action, detail=detail, otherwise="nothing was read"
        )

    # ===== the library's connections, to say Already added =====

    def _saved(self) -> dict[str, str]:
        """Each library connection's key (its kind's family, server and database; its file or data source)
        -> its name."""
        out: dict[str, str] = {}
        for listed in self._blades.listing()["blades"]:
            if not connection_rules.is_connection(str(listed.get("kind", "")), listed.get("template")):
                continue
            try:
                blade = self._blades.get(str(listed["name"]))
                settings = [s.to_json() for s in blade_rules.detect_settings(blade.code)]
            except Exception:  # noqa: S112 (a connection whose code does not read: it is no match)
                continue
            found = rules.found_from_settings(blade.template, settings)
            if found is not None:
                out.setdefault(rules.key_of(found), blade.name)
        return out

    def _notes(self, row: rules.Row) -> list[dict[str, str]]:
        """What the connection it would become leans on that only this computer has (the amber note)."""
        f = row.found
        template = self._templates.get(f.kind)
        if template is None or not row.supported:
            return []
        way = (f.kind, f.windows)
        if way not in self._ways:
            code = rules.way_code(f, template.to_json())
            self._ways[way] = portability.as_json(portability.check(code, f.kind))
        notes = list(self._ways[way])
        if f.path and not any(n["key"] == "local_file" for n in notes):
            notes.append(portability.LOCAL_FILE.to_json())
        return notes

    # ===== scan =====

    async def scan(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Read the known tools and search the settings folders: `{"hints": false}` reads the tools only.
        The list (each row: name, kind, server, database, user, where from; never a password), the notes (a
        binary file not read, why it stopped early) and how many files were opened."""
        hints = not (isinstance(body, dict) and body.get("hints") is False)
        await self._allow(
            who, "find_connections", "Look through this computer's app settings for connections"
        )
        if self._cancel is not None:
            raise Conflict("A search is running already: wait for it, or Cancel it.")
        cancel = threading.Event()
        self._cancel = cancel
        try:
            scan = await asyncio.to_thread(self._finder.scan, cancel, hints)
        finally:
            self._cancel = None
        listed = rules.rows(scan.found, self._saved())
        listed = [rules.Row(r.id, r.found, r.already, r.supported, self._notes(r)) for r in listed]
        self._last = {r.id: r for r in listed}
        notes = list(scan.notes) + ([STOPPED[scan.stopped]] if scan.stopped in STOPPED else [])
        self.ws.audit.write(who, "find_connections", "", found=len(listed), files=scan.files)
        labels = self._labels()
        return {
            "connections": [r.to_json(labels) for r in listed],
            "notes": notes,
            "files": scan.files,
            "stopped": scan.stopped,
        }

    def cancel(self) -> dict[str, Any]:
        """Stop the running search (what it found until then is listed)."""
        running = self._cancel
        if running is not None:
            running.set()
        return {"cancelled": running is not None}

    # ===== import =====

    async def import_found(self, body: Any, who: str = "user") -> dict[str, Any]:
        """`{"ids": [...]}`: each row of the last search made a library connection of its kind from its
        starter's code, named after its source's name (made unique), its password a variable it names (not
        set on this computer: the To finish step asks once). Rows already added, of a kind we have no
        connection for, or not in the last search are skipped and said."""
        ids = body.get("ids") if isinstance(body, dict) else None
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
            raise ValueError('Send {"ids": ["..."]}: the rows of the last search to import.')
        if not self._last:
            raise Conflict("Search first: Find connections on this computer.")
        picked = [self._last[i] for i in dict.fromkeys(ids) if i in self._last]
        names = [rules.name_for(r.found) for r in picked]
        await self._allow(
            who, "import_found_connections", "Import found connections: " + ", ".join(names[:8])
        )
        taken = {str(b["name"]) for b in self._blades.listing()["blades"]}
        variables = self._variables.taken()
        made: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = [
            {"id": i, "why": "It is not in the last search: search again."}
            for i in ids
            if i not in self._last
        ]
        wanted: list[str] = []
        for row in picked:
            template = self._templates.get(row.found.kind)
            if row.already:
                skipped.append({"id": row.id, "why": f"Already added: {row.already}"})
                continue
            if not row.supported or template is None:
                words = rules.kind_words(row.found.kind, self._labels())
                skipped.append({"id": row.id, "why": f"Swiss Army Bench has no {words} connection yet"})
                continue
            name = rules.unique_name(rules.name_for(row.found), taken)
            variable = rules.unique_variable(name, variables)
            try:
                data, used = rules.connection_body(row.found, template.to_json(), name, variable)
                saved = await self._save(data, who)
            except Exception as error:  # one that cannot be made: said, the others go on
                skipped.append({"id": row.id, "why": str(error)})
                continue
            taken.add(str(saved["name"]))
            if used:
                variables.add(used)
                wanted.append(used)
            made.append({"id": row.id, "name": saved["name"], "kind": template.id, "variable": used})
            self._last[row.id] = rules.Row(row.id, row.found, str(saved["name"]), row.supported, row.notes)
        declared = await self._variables.declare(wanted, who) if wanted else []
        return {"imported": made, "variables": declared, "skipped": skipped}
