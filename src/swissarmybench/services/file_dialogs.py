"""The system's own file dialog on the user's click, and the page picker's quick places and recent folders
(domain/file_dialogs.py's rules; server/dialog_runner.py opens the dialog). A system dialog is the user's own,
like Show in folder: the agent is refused (403) and passes paths to every command directly.

  status    GET /dialogs: whether this computer's dialogs open (the page knows up front; else its own)
  choose    POST /dialogs/choose: the dialog, its path or a cancel; its folder remembered for the kind
  remember  POST /dialogs/recent: a pick made in the page's own picker, remembered the same way
  places    the page picker's side: Home, Desktop, Documents, Downloads, the projects and library folders, and
            the recent folders of this kind of pick (dialogs.json: paths only)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import file_dialogs as rules
from swissarmybench.services.workspace import Refused


class DialogPort(Protocol):
    def status(self) -> dict[str, Any]: ...

    def choose(self, request: rules.DialogRequest) -> dict[str, Any]: ...


class StateFile(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class FileDialogs:
    def __init__(
        self,
        runner: DialogPort,
        state: StateFile,
        places: Callable[[], list[dict[str, str]]] = list,
        exists: Callable[[str], bool] = lambda path: True,
    ) -> None:
        self._runner, self._state, self._places, self._exists = runner, state, places, exists

    async def status(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._runner.status)

    async def choose(self, body: Any, who: str = "user") -> dict[str, Any]:
        if who == "agent":
            raise Refused(
                "A file dialog is the user's own click: pass the path to the command instead "
                "(files_list finds one)."
            )
        request = rules.read_request(body)
        status = await self.status()
        if not status.get("system"):
            return {"unavailable": status.get("reason") or "No system dialog here."}
        try:
            answer = await asyncio.to_thread(self._runner.choose, request)
        except rules.DialogFailed as error:
            return {"unavailable": str(error)}
        if answer.get("path"):
            self._remember(request.kind, rules.folder_of(answer["path"], request.mode))
        return answer

    def remember(self, body: Any, who: str = "user") -> dict[str, Any]:
        if not isinstance(body, dict) or not isinstance(body.get("kind"), str):
            raise ValueError('Send {"kind", "path", "mode"}.')
        path, mode = body.get("path"), body.get("mode", "folder")
        if not isinstance(path, str) or mode not in rules.MODES:
            raise ValueError('Send {"kind", "path", "mode"}.')
        folder = rules.folder_of(path, mode)
        self._remember(body["kind"], folder)
        return {"remembered": folder}

    def _remember(self, kind: str, folder: str) -> None:
        self._state.write(rules.remember(self._state.read(), kind, folder))

    def places(self, kind: str | None) -> list[dict[str, str]]:
        found = list(self._places())
        if kind:
            shown = {p["path"] for p in found}
            for folder in rules.recent(self._state.read(), kind):
                if folder not in shown and self._exists(folder):
                    found.append({"name": folder, "path": folder, "kind": "recent"})
                    shown.add(folder)
        return found
