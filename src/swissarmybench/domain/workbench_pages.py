"""Notebooks and Scripts, two pages (the owner, 2026-11-21: "notebooks and scripts should not reuse the same
page they are seperate things" / "right now they all open tabbed beside each other").

A notebook (.ipynb) opens only on the Notebooks page (/notebooks, the window named sab-notebooks), a .py
script only on the Scripts page (/scripts, sab-scripts), from anywhere. A Streamlit app's canvas and a
workbook design stay beside the notebooks, as before. web/src/workbenchPages.ts holds the same rule.
Pure rules, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PAGES: tuple[str, ...] = ("notebooks", "scripts")
WINDOW_NAMES: dict[str, str] = {"notebooks": "sab-notebooks", "scripts": "sab-scripts"}
WORDS: dict[str, str] = {"notebooks": "Notebooks", "scripts": "Scripts"}
_KIND_PAGE: dict[str, str] = {"notebook": "notebooks", "app": "notebooks", "script": "scripts"}
_KIND_WORDS: dict[str, str] = {"notebook": "A notebook", "app": "A Streamlit app", "script": "A script"}


def page_of_path(path: Any) -> str | None:
    """The page a file opens on: .py the Scripts page; .ipynb, an app's .stapp.json and a workbook's
    .design.json the Notebooks page; anything else none."""
    if not isinstance(path, str) or not path.strip():
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".py"):
        return "scripts"
    if name.endswith((".ipynb", ".stapp.json", ".design.json")):
        return "notebooks"
    return None


def page_of_kind(kind: Any) -> str | None:
    """A document kind's page (notebook, app: Notebooks; script: Scripts); none for any other."""
    return _KIND_PAGE.get(kind) if isinstance(kind, str) else None


def wrong_page(kind: Any, page: str) -> str | None:
    """The one line a document of `kind` dropped on `page` is refused with; None when it belongs there
    (or moves anywhere: the Data Explorer)."""
    home = page_of_kind(kind)
    if home is None or home == page:
        return None
    return f"{_KIND_WORDS[str(kind)]} opens on the {WORDS[home]} page, not here."


def url_of(page: str) -> str:
    return f"/{page}"


def old_address(query: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """An old /workbench address: the page it goes to (by its kind=, else its file's), the query kept."""
    kept = dict(query)
    page = page_of_kind(kept.get("kind")) or page_of_path(kept.get("file")) or page_of_path(kept.get("open"))
    return page or "notebooks", kept


# The commands that make one kind: that kind's page.
_COMMAND_PAGES: dict[str, str] = {
    "file.newScript": "scripts",
    "file.newNotebook": "notebooks",
    "file.newApp": "notebooks",
}


def page_for_command(page: Any, args: Mapping[str, Any], command: str = "") -> str | None:
    """The page a workbench command goes to: the one named, else its file's (args.path) or the kind it makes,
    else any (the window the user was last in)."""
    if page is not None:
        if page not in PAGES:
            raise ValueError("page is notebooks or scripts.")
        return str(page)
    return page_of_path(args.get("path")) or _COMMAND_PAGES.get(command)
