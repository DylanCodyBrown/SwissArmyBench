"""Notebooks and Scripts, two pages (the owner, 2026-11-21: "notebooks and scripts should not reuse the same
page they are seperate things" / "right now they all open tabbed beside each other").

A notebook (.ipynb) opens only on the Notebooks page (/notebooks, the window named sab-notebooks), a .py
script only on the Scripts page (/scripts, sab-scripts), from anywhere. A Streamlit app's canvas and a
workbook design stay beside the notebooks, as before. A structure's file (.json, .yaml, .yml, .xml, .toml:
2026-11-22, the owner: "I want it beside the ide so you can search and explore") opens as a tab on either
page, the one it was opened from; from outside (the desktop app, an address, the agent with no page) on the
Scripts page. An app's canvas (*.canvas.json), a workbook design, an old .stapp.json and the app's own state
(.sab/) are never a structure's tab. The pages hold no copy of these rules: they read them as data
(rules(), GET /app/rules; web/src/pageRules.ts applies the tables it is given).
Pure rules, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PAGES: tuple[str, ...] = ("notebooks", "scripts")
WINDOW_NAMES: dict[str, str] = {"notebooks": "sab-notebooks", "scripts": "sab-scripts"}
WORDS: dict[str, str] = {"notebooks": "Notebooks", "scripts": "Scripts"}
_KIND_PAGE: dict[str, str] = {"notebook": "notebooks", "app": "notebooks", "script": "scripts"}
# A structure's tab opens on either page (the one it was opened from): it has no page of its own.
_KIND_WORDS: dict[str, str] = {"notebook": "A notebook", "app": "A Streamlit app", "script": "A script"}


# A file's page by its name's ending, the first that matches: .py the Scripts page; .ipynb, an old app's
# .stapp.json and a workbook's .design.json the Notebooks page.
_PATH_PAGES: tuple[tuple[str, str], ...] = (
    (".py", "scripts"),
    (".ipynb", "notebooks"),
    (".stapp.json", "notebooks"),
    (".design.json", "notebooks"),
)
# A document's kind by its file's ending (the landing pages, the Session page's links, a tab's colour).
_PATH_KINDS: tuple[tuple[str, str], ...] = ((".stapp.json", "app"), (".ipynb", "notebook"), (".py", "script"))
_WRONG_PAGE: str = "{kind} opens on the {page} page, not here."
_STATE_FOLDER: str = ".sab"


def page_of_path(path: Any) -> str | None:
    """The page a file opens on: .py the Scripts page; .ipynb, an app's .stapp.json and a workbook's
    .design.json the Notebooks page; anything else none."""
    if not isinstance(path, str) or not path.strip():
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return next((page for ending, page in _PATH_PAGES if name.endswith(ending)), None)


def kind_of_path(path: Any) -> str | None:
    """A document's kind by its file's ending (notebook, script; an old app's canvas "app"); else none."""
    if not isinstance(path, str):
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return next((kind for ending, kind in _PATH_KINDS if name.endswith(ending)), None)


STRUCTURE_SUFFIXES: tuple[str, ...] = (".json", ".yaml", ".yml", ".xml", ".toml")
# Files with a suffix of theirs that keep their own owners (the Canvas page, the Excel canvas, the old app).
_NOT_STRUCTURES: tuple[str, ...] = (".canvas.json", ".design.json", ".stapp.json")


def is_structure_path(path: Any) -> bool:
    """A file that opens as a structure's tab beside the code: a .json, .yaml, .yml, .xml or .toml file, but
    not an app's canvas, a workbook design, an old app canvas, nor anything in a project's .sab/ folder."""
    if not isinstance(path, str) or not path.strip():
        return False
    parts = path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    if _STATE_FOLDER in parts[:-1] or not name.endswith(STRUCTURE_SUFFIXES) or name.endswith(_NOT_STRUCTURES):
        return False
    return not name.startswith(".")


def home_of_path(path: Any) -> str | None:
    """The page a file opens on when nothing says which: its kind's page, and a structure's the Scripts
    page."""
    return page_of_path(path) or ("scripts" if is_structure_path(path) else None)  # rules(): structures.home


def page_of_kind(kind: Any) -> str | None:
    """A document kind's page (notebook, app: Notebooks; script: Scripts); none for any other."""
    return _KIND_PAGE.get(kind) if isinstance(kind, str) else None


def wrong_page(kind: Any, page: str) -> str | None:
    """The one line a document of `kind` dropped on `page` is refused with; None when it belongs there
    (or moves anywhere: the Data Explorer)."""
    home = page_of_kind(kind)
    if home is None or home == page:
        return None
    return _WRONG_PAGE.format(kind=_KIND_WORDS[str(kind)], page=WORDS[home])


def rules() -> dict[str, Any]:
    """These rules as data, for the pages (GET /app/rules): they apply the tables and keep no copy. The
    endings are matched in order against a file's lower-cased name; `wrong_page` is the one sentence, its
    {kind} and {page} filled from kind_words and words."""
    return {
        "pages": list(PAGES),
        "windows": dict(WINDOW_NAMES),
        "words": dict(WORDS),
        "path_pages": [list(pair) for pair in _PATH_PAGES],
        "path_kinds": [list(pair) for pair in _PATH_KINDS],
        "kind_pages": dict(_KIND_PAGE),
        "kind_words": dict(_KIND_WORDS),
        "wrong_page": _WRONG_PAGE,
        "structures": {
            "suffixes": list(STRUCTURE_SUFFIXES),
            "not": list(_NOT_STRUCTURES),
            "state_folder": _STATE_FOLDER,
            "home": "scripts",
        },
    }


def url_of(page: str) -> str:
    return f"/{page}"


def old_address(query: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """An old /workbench address: the page it goes to (by its kind=, else its file's), the query kept."""
    kept = dict(query)
    page = page_of_kind(kept.get("kind")) or home_of_path(kept.get("file")) or home_of_path(kept.get("open"))
    return page or "notebooks", kept


# The commands that make one kind: that kind's page.
_COMMAND_PAGES: dict[str, str] = {
    "file.newScript": "scripts",
    "file.newNotebook": "notebooks",
    "file.newApp": "notebooks",
}


def page_for_command(page: Any, args: Mapping[str, Any], command: str = "") -> str | None:
    """The page a workbench command goes to: the one named, else its file's (args.path) or the kind it makes,
    else any (the window the user was last in). A structure's file has no page of its own: the window the
    user was last in, and its command "structure.open" with no page the Scripts page."""
    if page is not None:
        if page not in PAGES:
            raise ValueError("page is notebooks or scripts.")
        return str(page)
    if command == "structure.open":
        return home_of_path(args.get("path")) or "scripts"
    return page_of_path(args.get("path")) or _COMMAND_PAGES.get(command)
