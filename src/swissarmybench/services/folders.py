"""The page's own file picker (adapters/folders.py): a folder's contents, its quick places and New folder. The
page uses it when no system dialog opens (services/file_dialogs.py); the agent lists folders and makes one too
(files_list, files_new_folder: the golden rule)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swissarmybench.domain.file_dialogs import check_folder_name

_MAX_SUFFIXES: int = 20


class Folders:
    def __init__(
        self,
        listing: Callable[..., dict[str, Any]],
        ensure_own: Callable[[str], None] = lambda where: None,
        places: Callable[[str | None], list[dict[str, str]]] = lambda kind: [],
        make_folder: Callable[[str, str], str] | None = None,
    ) -> None:
        self._listing = listing
        # Makes the app's own folder (SwissArmyBench in the home folder) when `where` is that folder and
        # it is not there yet: the first Save or Open of the Workbench starts in it. No other folder.
        self._ensure_own = ensure_own
        self._places = places
        self._make_folder = make_folder

    def browse(
        self, where: str | None, suffixes: str | None, kind: str | None = None, hidden: bool = False
    ) -> dict[str, Any]:
        """`suffixes` as the page sends them: ".csv,.xlsx" (empty: every file). With `kind` (the kind of
        pick), the quick places too, its recent folders among them."""
        wanted = {s.strip().lower() for s in (suffixes or "").split(",") if s.strip()}
        if len(wanted) > _MAX_SUFFIXES or any(not s.startswith(".") or len(s) > 12 for s in wanted):
            raise ValueError("Name the file kinds as .csv,.xlsx (at most 20).")
        if where:
            self._ensure_own(where)
        found = self._listing(where or None, wanted, hidden)
        if kind is not None:
            found["places"] = self._places(kind or None)
        return found

    def new_folder(self, body: Any, who: str = "user") -> dict[str, Any]:
        """New folder: {"path": the folder it goes in, "name"}."""
        if not isinstance(body, dict) or not isinstance(body.get("path"), str) or not body["path"]:
            raise ValueError('Send {"path": the folder it goes in, "name"}.')
        if self._make_folder is None:
            raise ValueError("New folder is not available here.")
        return {"path": self._make_folder(body["path"], check_folder_name(body.get("name")))}
