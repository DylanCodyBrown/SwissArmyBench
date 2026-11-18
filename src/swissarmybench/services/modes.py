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

from collections.abc import Callable
from typing import Any


class Modes:
    def __init__(
        self,
        modes: Callable[[], list[dict[str, Any]]],
        folder: Callable[[], str | None],
        type_of: Callable[[str | None], str],
        areas: Callable[[], list[dict[str, Any]]] = list,
    ) -> None:
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
