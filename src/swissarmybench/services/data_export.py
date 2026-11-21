"""A project's data: data.ipynb -> data.py (docs/ideas.md, projects; rules in domain/projects.py).

The base's: New project and Export data.py write it, and the Streamlit extension's Save as and a page's
tables import from it. data.ipynb is read as it is now: from the Workbench window that holds it (saved or
not: a hook an extension fills, services/hooks.py), else from its file with each open table's read-only
cell as the grid has it now.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import dictionary as data_dictionary
from swissarmybench.domain import notebooks, projects
from swissarmybench.domain.projects import DataCell
from swissarmybench.services.workspace import Conflict


class ProjectFiles(Protocol):
    def read(self, folder: str, name: str) -> str | None: ...

    def path(self, folder: str, name: str) -> str: ...

    def write(self, folder: str, name: str, text: str) -> str: ...


class DataExport:
    def __init__(
        self,
        project_files: ProjectFiles,
        arrange: Callable[[Any], Awaitable[dict[str, Any]]],
        held: Callable[[str], Any],
        edited: Callable[[str], set[str]] = lambda folder: set(),
    ) -> None:
        self._project = project_files
        # The made files the user edited by hand (Scripts IDE: .sab/hand-edited.json): never overwritten
        # silently (the owner, 2026-11-21).
        self._edited = edited
        self._arrange = arrange  # a notebook's cells with its tables' cells as the grid has them now
        self._held = held  # an open document as its window holds it (`every`, `dictionary`), or None

    async def data_cells(self, folder: str) -> list[DataCell] | None:
        """The cells of a project's data.ipynb as they are now. None: the folder has none."""
        held = self._held(self._project.path(folder, projects.DATA_NOTEBOOK))
        if held is not None and getattr(held, "every", None) is not None:
            return list(held.every)
        text = self._project.read(folder, projects.DATA_NOTEBOOK)
        if text is None:
            return None
        cells, following = notebooks.read_document(text)
        tables = [c.table for c in cells if c.role == "transformations" and c.table]
        if tables:
            sent = {"kind": "notebook", "cells": [c.to_json() for c in cells], "tables": tables}
            arranged = await self._arrange(sent | {"next_cell": following, "move": False})
            cells = notebooks.read_cells(arranged["cells"])
        return [DataCell(c.kind, c.source, c.role, c.table, c.number) for c in cells]

    async def data(self, folder: str, title: str, replace: bool = False) -> projects.DataModule | None:
        """data.py written again from the folder's data.ipynb (None: the folder has no data.ipynb). One edited
        by hand is kept (made, not written) unless `replace`."""
        try:
            cells = await self.data_cells(folder)
        except (notebooks.NotebookError, ValueError, OSError):
            return None
        if cells is None:
            return None
        held = self._held(self._project.path(folder, projects.DATA_NOTEBOOK))
        said = getattr(held, "dictionary", None) if held is not None else None
        if said is None:
            said = data_dictionary.of_notebook(self._project.read(folder, projects.DATA_NOTEBOOK))
        made = projects.data_module(title, cells, said)
        if replace or projects.DATA_FILE not in self._edited(folder):
            self._project.write(folder, projects.DATA_FILE, made.text)
        return made

    async def export_data(self, folder: str, title: str, replace: bool = False) -> dict[str, Any]:
        """Export data.py: the project's data.ipynb's code cells in order, as a module. data.py edited by hand
        asks first (Conflict: Keep my edits, Replace or Compare) unless `replace`."""
        if not replace and projects.DATA_FILE in self._edited(folder):
            raise Conflict(
                "data.py was edited by hand: keep your edits, or export again with Replace "
                "(Compare shows both)."
            )
        try:
            made = await self.data(folder, title, replace)
        except PermissionError as error:
            raise Conflict(str(error)) from None
        if made is None:
            return {"path": None, "names": [], "fill_in": [], "skipped": [], "requirements": []}
        return {
            "path": self._project.path(folder, projects.DATA_FILE),
            "names": list(made.names),
            "fill_in": list(made.fill_in),
            "skipped": list(made.skipped),
            "requirements": projects.data_requirements(made.text),
        }
