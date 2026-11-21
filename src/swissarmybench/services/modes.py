"""Project modes (Plans/editions.plan.md, "Project modes", the owner 2026-11-17): the open project's type
sets a mode, and the mode decides the working set: the canvas kinds offered, the blade and function families
shown first, the languages, the extra cell kinds, the agent's tool group, the export.

A mode is declared, never coded: the base's and each extension's are data (swissarmybench/extensions.py
reads them, the composition root hands them in), and the page and the agent read `active()`. One mode at a
time, from the open project; no project open: the base's.

  active   the open project's type and its mode; `needs`: the extension a project's type names that is not
           on here (the project opens with what the base can)
  modes    every type this app can make (the base's, then each on extension's): New project lists them
  areas    the rail's areas the on extensions add (their RAIL), and the footer's mark each may answer
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar


class Modes:
    def __init__(
        self,
        modes: Callable[[], list[dict[str, Any]]],
        folder: Callable[[], str | None],
        type_of: Callable[[str | None], str],
        areas: Callable[[], list[dict[str, Any]]] = list,
        setting: Callable[[str], Any] = lambda _key: None,
        set_setting: Callable[[str, Any, str], Awaitable[Any]] | None = None,
    ) -> None:
        self._setting = setting  # a field of the open project's .sab/project.json
        self._set_setting = set_setting
        self._modes = modes
        self._areas = areas  # the rail's areas the on extensions add (each one's RAIL, as data)
        self._folder = folder  # the open project's folder (None: no project)
        self._type_of = type_of  # a project folder's type (.sab/project.json)

    def all(self) -> list[dict[str, Any]]:
        return self._modes()

    def areas(self) -> list[dict[str, Any]]:
        """The rail's areas the on extensions add: {area, name, icon, mark?: a route answering the footer's
        mark ({"mark": null or {"words", "state", "title"}})}. The page draws them; it never names one."""
        return self._areas()

    def active(self) -> dict[str, Any]:
        folder = self._folder()
        kind = self._type_of(folder)
        found = self._modes()
        mode = next((m for m in found if m["type"] == kind), found[0])
        out = {"project": folder, "project_type": kind, "mode": mode}
        if mode["type"] != kind:
            out["needs"] = kind  # the type's extension is not on: the base's mode, and what to add
        return out

    # ===== gates: the features a project type keeps closed (its mode's `areas`) =====

    AREA_NAMES: ClassVar[dict[str, str]] = {
        "projects": "Projects", "connections": "Connections", "apis": "APIs", "variables": "Variables",
        "data": "Data", "grids": "Grids", "erd": "ERD", "structures": "Structures", "blades": "Blades",
        "notebooks": "Notebooks", "scripts": "Scripts", "canvas": "Canvas", "widgets": "Widgets",
        "analyze": "Analyze",
        "session": "Session", "extensions": "Extensions", "settings": "Settings",
    }  # fmt: skip

    def gates(self) -> dict[str, Any]:
        """{open: the areas open (None: all), closed: [{area, name}], every: Settings' Open every feature in
        this
        project, first_open: the pop-up's words until seen once (None after), line: the one line a closed
        feature's way in shows ({feature} filled by the page), tour}. The agent's tools stay open."""
        mode = self.active()["mode"]
        wanted = [str(a) for a in mode.get("areas") or []]
        every = self._setting("open_every_feature") is True
        added = {a["area"]: a.get("name") or a["area"] for a in self._areas()}
        names = self.AREA_NAMES | added
        known = list(names)
        closed = [] if not wanted or every else [a for a in known if a not in wanted]
        words = ", ".join(names[a] for a in closed)
        first = str(mode.get("first_open") or "")
        seen = self._setting("first_open_seen") is True
        return {
            "open": None if not closed else [a for a in known if a not in closed],
            "closed": [{"area": a, "name": names[a]} for a in closed],
            "gated": bool(wanted),
            "every": every,
            "first_open": first.replace("{closed}", words) if first and closed and not seen else None,
            "line": f"This {mode.get('name') or 'project'} project keeps {{feature}} closed."
            if wanted
            else "",
            "tour": mode.get("tour") or [],
        }

    async def set_gates(self, body: Any, who: str) -> dict[str, Any]:
        """{"every": true|false}: Settings' Open every feature in this project; {"seen": true}: the first-open
        pop-up shown once. Kept in .sab/project.json."""
        if self._set_setting is None or self._folder() is None:
            raise ValueError("No project is open.")
        body = body if isinstance(body, dict) else {}
        if isinstance(body.get("every"), bool):
            await self._set_setting("open_every_feature", True if body["every"] else None, who)
        if body.get("seen") is True:
            await self._set_setting("first_open_seen", True, who)
        return self.gates()
