"""Projects: data first (docs/ideas.md, 2026-11-15; rules in domain/projects.py). For the Workbench
window and the agent alike.

  new       a project's folder: data.ipynb (a read-only cell for each open table), data.py (its
            export), a Streamlit app's canvas, any notebooks asked for (each starting with
            `from data import ...`), requirements.txt
  open      the files of a project's folder the Workbench opens as tabs: data.ipynb first, the app's
            canvas, the other notebooks, the scripts
  export    data.py written again from data.ipynb (services/streamlit.py does it: it knows the open
            documents; Play and Save as do it too)

data.py is an export, never edited by hand: the user works in data.ipynb.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmygrid.domain import notebooks, streamlit_cells
from swissarmygrid.domain import projects as rules
from swissarmygrid.domain.projects import ProjectError
from swissarmygrid.services.workspace import Conflict, NotFound, Workspace


class Files(Protocol):
    def make(self, parent: str, name: str) -> str: ...

    def names(self, folder: str) -> list[str]: ...

    def path(self, folder: str, name: str) -> str: ...

    def write(self, folder: str, name: str, text: str) -> str: ...

    def folder_of(self, path: str) -> str: ...


class Projects:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        table_cells: Callable[[list[str] | None], Awaitable[tuple[list[notebooks.Cell], int]]],
        export_data: Callable[[str, str], Awaitable[dict[str, Any]]],
        remember: Callable[[str], None],
    ) -> None:
        self.ws = ws
        self._files = files
        # The open tables (or the ones named) as a notebook's Tables group, and its next cell number.
        self._table_cells = table_cells
        self._export_data = export_data  # data.py from a folder's data.ipynb (services/streamlit.py)
        self._remember = remember  # a file among the Workbench's recent ones

    def _folder(self, body: Any) -> str:
        """The project a call is about: {"folder"}, or {"path"}: a file in it."""
        if isinstance(body, dict) and isinstance(body.get("folder"), str) and body["folder"].strip():
            return str(body["folder"])
        if isinstance(body, dict) and isinstance(body.get("path"), str) and body["path"].strip():
            return self._files.folder_of(body["path"])
        raise ProjectError('Send {"folder": the project\'s folder}.')

    def _listing(self, folder: str) -> dict[str, Any]:
        names = self._files.names(folder)
        whole = self._files.folder_of(self._files.path(folder, rules.DATA_NOTEBOOK))
        return {
            "folder": whole,
            "name": streamlit_cells.app_title(whole),
            "data": self._files.path(folder, rules.DATA_NOTEBOOK) if rules.DATA_NOTEBOOK in names else None,
            "files": [self._files.path(folder, name) for name in rules.project_files(names)],
        }

    async def create(self, body: Any, who: str = "user") -> dict[str, Any]:
        """New project: {"folder": where, "name": its folder's name, "app"?: false for a project
        without a Streamlit app, "notebooks"?: ["analysis", "mockups"], "tables"?: the open tables
        data.ipynb starts with (default: every one)}."""
        if not isinstance(body, dict) or not isinstance(body.get("folder"), str):
            raise ProjectError('Send {"folder": where it goes, "name": the project\'s name}.')
        name = rules.check_folder_name(body.get("name") or "")
        wanted = body.get("notebooks") or []
        if not isinstance(wanted, list) or not all(isinstance(n, str) for n in wanted) or len(wanted) > 20:
            raise ProjectError("notebooks is a list of names.")
        stems = [rules.check_folder_name(raw.removesuffix(".ipynb")) for raw in wanted]
        if any(stem.lower() == "data" for stem in stems):
            raise ProjectError("data.ipynb is the project's own: name the notebook something else.")
        tables = body.get("tables")
        if tables is not None and (
            not isinstance(tables, list) or not all(isinstance(t, str) for t in tables)
        ):
            raise ProjectError("tables is a list of open tables' names.")
        try:
            folder = self._files.make(body["folder"], name)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except FileExistsError as error:
            raise Conflict(str(error)) from None
        cells, following = await self._table_cells(tables)
        try:
            self._files.write(
                folder, rules.DATA_NOTEBOOK, notebooks.write_notebook(cells, next_number=following)
            )
            exported = await self._export_data(folder, name)
            if body.get("app") is not False:
                app = f"{streamlit_cells.slug(name)}{streamlit_cells.APP_SUFFIX}"
                self._files.write(folder, app, streamlit_cells.write_app([]))
            given = exported["names"]
            first = f"from data import {', '.join(given)}" if given else "import data"
            for stem in stems:
                self._files.write(
                    folder, f"{stem}.ipynb", notebooks.write_notebook([notebooks.Cell("code", first)])
                )
            needed = (["streamlit>=1.36"] if body.get("app") is not False else []) + exported["requirements"]
            self._files.write(folder, rules.REQUIREMENTS_FILE, rules.merged_requirements(None, needed))
        except PermissionError as error:
            raise Conflict(str(error)) from None
        self.ws.audit.write(who, "new_project", folder)
        return self._opened(folder)

    def _opened(self, folder: str) -> dict[str, Any]:
        listed = self._listing(folder)
        for path in listed["files"]:
            self._remember(path)
        return listed

    def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A project's folder: the files the Workbench opens as tabs. A folder without a data.ipynb
        is not a project."""
        folder = self._folder(body)
        try:
            listed = self._listing(folder)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        if listed["data"] is None:
            raise NotFound(f"{listed['folder']} is not a project: it has no data.ipynb.")
        self.ws.audit.write(who, "open_project", listed["folder"])
        return self._opened(folder)

    async def export_data(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Export data.py: written again from the project's data.ipynb (the open one, saved or not)."""
        folder = self._folder(body)
        try:
            listed = self._listing(folder)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        done = await self._export_data(folder, listed["name"])
        if done["path"] is None:
            raise NotFound(f"{listed['folder']} is not a project: it has no data.ipynb.")
        self.ws.audit.write(who, "export_data", done["path"])
        return done
