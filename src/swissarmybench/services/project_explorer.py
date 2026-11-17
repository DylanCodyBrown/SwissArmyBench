"""The Project Explorer: the home page (the owner, 2026-11-17: "Yes build it with projects as folders" / "Make
the project page sortable by card with explanations of project types for beginners"; rules in
domain/project_explorer.py). For the page and the agent alike (the golden rule), but Show in folder and
Delete, which are the user's own clicks.

  list      every project in one place: the projects folder's, and every project opened from elsewhere (the
            recent list), each as a card; sorted, filtered by type and words; the types explained
  sort      the chosen sort (remembered), the custom order (dragged, or a card moved left or right)
  folder    Settings' Projects folder (the agent's change waits for the user's Allow); New project makes its
            folder there by default
  rename    a project's folder renamed (not the open one: close it first); the lists follow
  remove    off the list (never a file deleted): from the recent list, and hidden when it is in the projects
            folder
  locate    a moved project found again: its entry follows it
  show      its folder in the system's file manager: the user's click only
  delete    its folder moved to the system's trash, on the user's typed name only: never the agent's
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import project_explorer as rules
from swissarmybench.domain.projects import check_folder_name
from swissarmybench.services.agent import Approvals
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace


class Settings(Protocol):
    def read(self) -> dict[str, Any]: ...

    def write(self, settings: dict[str, Any]) -> None: ...


class Files(Protocol):
    def full(self, path: str) -> str: ...

    def is_folder(self, path: str) -> bool: ...

    def scan(self, folder: str) -> list[str]: ...

    def facts(self, folder: str) -> dict[str, Any] | None: ...

    def rename(self, folder: str, name: str) -> str: ...

    def show(self, folder: str) -> None: ...

    def trash(self, folder: str) -> str: ...


class Recent(Protocol):
    def all(self) -> list[dict[str, Any]]: ...

    def remove(self, path: str) -> bool: ...

    def replace(self, old: str, new: str) -> bool: ...


class ProjectExplorer:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        settings: Settings,
        recent: Recent,
        projects: SabProjects,
        approvals: Approvals,
        default_folder: str,
        modes: Callable[[], list[dict[str, Any]]],
        streamlit: Mapping[str, Any],
        off: Callable[[], dict[str, dict[str, Any]]] = dict,
    ) -> None:
        self.ws = ws
        self._files = files
        self._settings = settings
        self._recent = recent
        self._projects = projects
        self._approvals = approvals
        self._default = default_folder
        self._modes = modes  # every on project type's mode (the base's, each on extension's)
        self._streamlit = streamlit  # the Streamlit app's words, the base's
        self._off = off  # an extension's project type that is not on: {type: {"id", "name"}}

    def folder(self) -> str:
        """The projects folder: Settings' choice, else the default (~/Swiss Army Bench Projects)."""
        return str(self._settings.read()["folder"] or self._default)

    def types(self) -> dict[str, Any]:
        """The project types New project can make, each explained for beginners; where New puts them."""
        return {"types": rules.kinds(self._modes(), self._streamlit), "folder": self.folder()}

    async def _changed(self) -> None:
        await self.ws.live.broadcast({"type": "projects_changed"})

    # ===== the cards =====

    def _cards(self) -> list[dict[str, Any]]:
        settings = self._settings.read()
        folder = self.folder()
        hidden = set(settings["hidden"])
        inside = [p for p in self._files.scan(folder) if p not in hidden]
        recent = {str(r["path"]): r for r in self._recent.all()}
        paths = list(dict.fromkeys([*inside, *recent]))
        kinds = {k["type"]: k for k in rules.kinds(self._modes(), self._streamlit)}
        off = self._off()
        current = self._projects.current.folder if self._projects.current is not None else None
        cards = []
        for path in paths:
            said = recent.get(path)
            facts = self._files.facts(path) if self._files.is_folder(path) else None
            card = rules.card(
                path, facts, kinds, off, float(said["opened"]) if said else None, current, path in inside
            )
            if said and said.get("sab"):
                card["sab"] = True  # an old .sab file: Import… makes it a folder
            cards.append(card)
        return cards

    async def list(self, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """{"by"?, "descending"?, "type"?, "q"?}: the cards, sorted (the remembered sort unless given) and
        filtered; the types explained; the projects folder."""
        query = query or {}
        settings = self._settings.read()
        sort = dict(settings["sort"])
        if query.get("by") is not None:
            sort = rules.check_sort({"by": query.get("by"), "descending": _truthy(query.get("descending"))})
        try:
            cards = await asyncio.to_thread(self._cards)
            shown = rules.filtered(
                rules.sorted_cards(cards, sort, settings["order"]), query.get("type") or None, query.get("q")
            )
        except rules.ExplorerError as error:
            raise ValueError(str(error)) from None
        return {
            "folder": self.folder(),
            "default_folder": self._default,
            "projects": shown,
            "count": len(cards),
            "sort": sort,
            "types": rules.kinds(self._modes(), self._streamlit),
            "explained": settings["explained"],
        }

    # ===== sort, order, the explanations put away =====

    async def sort(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"by", "descending"?}: the sort, remembered. {"order": [folders]}: the custom order (Custom
        chosen). {"move": a folder, "by": -1 or 1}: a card moved left or right in the custom order."""
        if not isinstance(body, dict):
            raise ValueError('Send {"by": "name"}, {"order": [...]} or {"move": a folder, "by": -1}.')
        settings = self._settings.read()
        try:
            if "move" in body:
                cards = rules.sorted_cards(
                    await asyncio.to_thread(self._cards), settings["sort"], settings["order"]
                )
                settings["order"] = rules.moved(
                    settings["order"],
                    [c["path"] for c in cards],
                    str(body["move"]),
                    body["by"] if isinstance(body.get("by"), int) else 0,
                )
                settings["sort"] = {"by": "custom", "descending": False}
            elif "order" in body:
                settings["order"] = rules.check_order(body["order"])
                settings["sort"] = {"by": "custom", "descending": False}
            else:
                settings["sort"] = rules.check_sort(body)
        except rules.ExplorerError as error:
            raise ValueError(str(error)) from None
        self._settings.write(settings)
        self.ws.audit.write(who, "projects_sort", None, by=settings["sort"]["by"])
        await self._changed()
        return await self.list()

    async def explained(self, body: Any) -> dict[str, Any]:
        """{"explained": true}: the types' explanations put away (remembered); false brings them back."""
        if not isinstance(body, dict) or not isinstance(body.get("explained"), bool):
            raise ValueError('Send {"explained": true} or {"explained": false}.')
        settings = self._settings.read()
        settings["explained"] = body["explained"]
        self._settings.write(settings)
        return {"explained": settings["explained"]}

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Settings' Projects folder: {"folder"} or {"default": true}. The agent's waits for the user's
        Allow."""
        if not isinstance(body, dict):
            raise ValueError('Send {"folder": the projects folder} or {"default": true}.')
        settings = self._settings.read()
        if body.get("default") is True:
            chosen: str | None = None
        else:
            raw = body.get("folder")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError('Send {"folder": the projects folder} or {"default": true}.')
            try:
                chosen = self._files.full(raw.strip())
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
        if who == "agent":
            detail = "Make this the projects folder (New project puts new projects there):\n  " + (
                chosen or self._default
            )
            if not await self._approvals.ask("Projects folder", "change the projects folder", detail):
                raise Refused("The user declined (or did not answer): the projects folder stays.")
        settings["folder"] = chosen
        self._settings.write(settings)
        self.ws.audit.write(who, "projects_folder", None, default=chosen is None)
        await self._changed()
        return {"folder": self.folder(), "default_folder": self._default}

    # ===== one project =====

    def _path(self, body: Any, key: str = "path") -> str:
        raw = body.get(key) if isinstance(body, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f'Send {{"{key}": the project\'s folder}}.')
        try:
            return self._files.full(raw.strip())
        except OSError as error:  # not a whole path, or not one this computer can use
            raise NotFound(str(error)[:300]) from None

    def _not_open(self, path: str, doing: str) -> None:
        current = self._projects.current
        if current is not None and current.folder == path:
            raise Conflict(f"{current.name} is open: close it first to {doing} it.")

    async def rename(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path", "name"}: the project's folder renamed (its parent kept)."""
        path = self._path(body)
        name = check_folder_name(str(body.get("name") or ""))
        self._not_open(path, "rename")
        try:
            done = await asyncio.to_thread(self._files.rename, path, name)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except FileExistsError as error:
            raise Conflict(str(error)) from None
        except OSError as error:
            raise Conflict(f"{path} could not be renamed: {error}") from None
        self._follow(path, done)
        self.ws.audit.write(who, "project_rename", done)
        await self._changed()
        return {"path": done, "name": name}

    def _follow(self, old: str, new: str) -> None:
        self._recent.replace(old, new)
        settings = self._settings.read()
        settings["order"] = [new if p == old else p for p in settings["order"]]
        self._settings.write(settings)

    async def remove(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path"}: off the list. No file is touched: a project in the projects folder is hidden."""
        path = self._path(body)
        gone = self._recent.remove(path)
        settings = self._settings.read()
        settings["order"] = [p for p in settings["order"] if p != path]
        if path in await asyncio.to_thread(self._files.scan, self.folder()):
            settings["hidden"] = [*settings["hidden"], path]
            gone = True
        if not gone:
            raise NotFound("That project is not in the list.")
        self._settings.write(settings)
        self.ws.audit.write(who, "project_remove_from_list", None)
        await self._changed()
        return {"removed": path}

    async def locate(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"path": where it was, "to": where it is now}: a moved project found again."""
        path = self._path(body)
        to = self._path(body, "to")
        try:
            found = self._files.full(to)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        facts = await asyncio.to_thread(self._files.facts, found)
        if facts is None:
            raise NotFound(f"{found} is not there.")
        if not self._recent.replace(path, found):
            raise NotFound("That project is not in the list.")
        self._follow(path, found)
        await self._changed()
        return {"path": found}

    async def show(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Show in folder: the system's file manager on the project's folder. The user's click only."""
        if who == "agent":
            raise Refused("Show in folder opens the user's own file manager: it is the user's click.")
        path = self._path(body)
        try:
            await asyncio.to_thread(self._files.show, path)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        return {"shown": path}

    async def delete(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Delete…: {"path", "confirm": the project's name, typed}. Its folder goes to the system's trash. The
        user's only: the agent cannot delete a project."""
        if who == "agent":
            raise Refused("Deleting a project is the user's own: only they can, on the page.")
        path = self._path(body)
        name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if not isinstance(body, dict) or body.get("confirm") != name:
            raise ValueError(f"Type the project's name ({name}) to move its folder to the trash.")
        self._not_open(path, "delete")
        try:
            where = await asyncio.to_thread(self._files.trash, path)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except OSError as error:
            raise Conflict(f"{name} could not be moved to the trash: {error}") from None
        self._recent.remove(path)
        settings = self._settings.read()
        settings["order"] = [p for p in settings["order"] if p != path]
        self._settings.write(settings)
        self.ws.audit.write(who, "project_delete", None)
        await self._changed()
        return {"deleted": path, "to": where}


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() in ("1", "true", "yes"))
