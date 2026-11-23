"""Getting around (the owner, 2026-11-16: "there is no navigation in the app to get back to the home page or
go back anywhere"): the places an agent can send a window to, as `app_navigate` names them.

The rail (web/src/rail.ts) names the areas, the same from every window; each is a page (the owner,
2026-11-16: "clicking the rail should land on a page not open a form"). The pages keep their views in
the address (web/src/nav.ts): the home page's tabs, the Settings and Connections pages over any page
(open=settings, open=connections: a connection's detail and its forms), the blades page's blade screen
(its catalog panel went, the owner 2026-11-17: a connection's tables are on the Connections page), the
Workbench's landing page for a kind (?kind=notebook&view=list). The agent moves them as the user does:
Home (the mark), Back and Forward (the browser's own), or a named view where the page has one.
Pure rules, no I/O: a request read into the notice the window acts on.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

# The windows that move: the home page (/workspace), the Notebooks and Scripts pages. "catalog", the old
# blades page's (it went 2026-11-21: the Scripts page's Blades pane), is read as "scripts" for one release.
WINDOWS: tuple[str, ...] = ("home", "catalog", "workbench", "notebooks", "scripts")
OLD_WINDOWS: dict[str, str] = {"catalog": "scripts"}
# The Notebooks and Scripts pages are two Workbench windows (the owner, 2026-11-21: "notebooks and scripts
# should not reuse the same page"); "workbench" is either, the one the user was last in.
CODE_WINDOWS: tuple[str, ...] = ("notebooks", "scripts")

# The rail's areas (the owner, 2026-11-16: "this app needs a navigation pane somehow"; a slim icon
# rail down the left of every page and window), in its order: each is a place from every window, as a
# rail click goes there (web/src/rail.ts). A window that does not show the area brings forward the one
# that does (the home window for the grids, Analyze and the ERD; the Workbench for notebooks,
# scripts and apps, each its kind's mode; the blades page). Grids is the home page's tabbed grids, only the
# grids; projects (the mark, the rail's first item: the owner, 2026-11-18) is the Projects page over the
# home page (the Project Explorer and the tour), and home goes there too.
AREAS: tuple[str, ...] = (
    "projects",
    # In the order of the work (the owner, 2026-11-17): where data comes from, getting and shaping it, web
    # data, tools, building, presenting, the log; Settings at the bottom.
    "connections",
    "apis",
    # The Environment (the owner, 2026-11-21/22): everything the project holds, in the Structures and
    # Variables places (Structures stays a place: the viewer its rows open into; variables goes here).
    "environment",
    "data",  # the one place to browse tables (the owner, 2026-11-17: "a standalone DATA rail icon")
    "grids",
    "erd",
    "scripts",  # Blades are its pane on the right (the owner, 2026-11-22: "remove blades rail icon")
    "notebooks",
    "canvas",  # 2026-11-21: the Apps area is the Canvas (its own page)
    "widgets",  # 2026-11-21: the Widgets window (its own, no rail)
    "analyze",
    "session",
    "extensions",
    "settings",
)
# The old names, one release (2026-11-18: the Start view is the Projects page).
SAME: dict[str, str] = {
    "start": "projects",
    "apps": "canvas",  # 2026-11-21: Apps is the Canvas
    "catalog": "data",  # 2026-11-21: the Data Catalog is the Catalog
    "variables": "environment",  # 2026-11-22: the settings are the Environment's Settings and secrets tab
}
# The code areas: each may open in a Workbench window of its own (the owner's "external tab").
CODE: tuple[str, ...] = ("notebooks", "scripts")
# Every window: home (the mark), the rail's areas, the browser's Back and Forward, a connection's
# detail on the Connections page, and the forms inside Connections.
EVERYWHERE: tuple[str, ...] = (
    "home",
    *AREAS,
    "structures",  # the Structures viewer (a structure's row opens into it)
    "blades",  # no rail icon (2026-11-22): the Scripts page with its Blades pane shown
    "back",
    "forward",
    "connection:<name>",
    "add_connection",
    "add_api",
)
# Each window's own views. `grid:<id>` and `blade:<name>` name one. The home page's New query page (the "+",
# the grids with none open: the owner, 2026-11-20) is new_query; query is its draft, query:<connection> the
# draft with Query from set to that connection (a click on the page).
OWN: dict[str, tuple[str, ...]] = {
    "home": ("new_query", "query", "query:<connection>", "grid:<id>"),
    "workbench": (),
    "notebooks": (),
    "scripts": ("blade:<name>", "new_blade"),  # a blade's tab on the Scripts page, New blade
}
NAMED: tuple[str, ...] = ("grid", "blade", "connection")
MAX_NAME: int = 512


class NavigationError(ValueError):
    """A window or a place that is not one: what can be said instead."""


def places(window: str) -> tuple[str, ...]:
    """What `window` can be sent to, as the agent writes it."""
    return EVERYWHERE + OWN[OLD_WINDOWS.get(window, window)]


def place(window: Any, to: Any, new_window: Any = None) -> dict[str, Any]:
    """The notice for `window` to go `to`: {"window", "to"} and, for a named view, its names;
    `new_window` (notebooks, scripts, apps): in a Workbench window of its own."""
    window = "home" if window is None else window
    if window not in WINDOWS:
        raise NavigationError(f"window is one of {', '.join(w for w in WINDOWS if w not in OLD_WINDOWS)}.")
    window = OLD_WINDOWS.get(window, window)
    if not isinstance(to, str) or not to.strip():
        raise NavigationError(f"to is where to go: {', '.join(places(window))}.")
    to = SAME.get(to.strip(), to.strip())
    kind, _, name = to.partition(":")
    wanted = kind if name or kind in NAMED else to
    allowed = {p.partition(":")[0] for p in places(window)}
    if wanted not in allowed or (kind in ("grid", "blade", "connection") and not name):
        raise NavigationError(
            f"The {window} window cannot go to {to!r}. It can go to: {', '.join(places(window))}."
        )
    if len(name) > MAX_NAME:
        raise NavigationError(f"That name is longer than {MAX_NAME} characters.")
    if new_window not in (None, False):
        if new_window is not True:
            raise NavigationError("new_window is true or false.")
        if to not in CODE:
            raise NavigationError(f"Only {', '.join(CODE)} open in a new window.")
    notice: dict[str, Any] = {"window": window, "to": kind}
    if new_window is True:
        notice["new_window"] = True
    if kind == "grid":
        notice["grid"] = name
    elif kind in ("blade", "connection") or (kind == "query" and name):
        notice["name"] = name
    return notice


def said(notice: dict[str, Any]) -> str:
    """The move in the audit log's words: "home window to grid g1", never more than the names."""
    named = [str(notice[k]) for k in ("grid", "name") if k in notice]
    where = f"{notice['window']} window to {notice['to']}{' ' + '/'.join(named) if named else ''}"
    return where + (", in a new window" if notice.get("new_window") else "")


# ===== the rail's names (the owner, 2026-11-19) =====
# The rail shows each area's name beside its icon (a wider rail) or the icons alone. The names are on until
# the user turns them off, so a first run sees the words; the choice is this computer's (rail.json).


def rail_labels(saved: Any) -> bool:
    """Whether the rail shows its names: what rail.json kept, else on."""
    if isinstance(saved, dict) and isinstance(saved.get("labels"), bool):
        return bool(saved["labels"])
    return True


def rail_change(sent: Any) -> bool:
    """The switch as sent: {"labels": true} (the rail with its names) or {"labels": false} (icons only)."""
    if not isinstance(sent, dict) or not isinstance(sent.get("labels"), bool):
        raise NavigationError('Send {"labels": true} (the rail with its names) or {"labels": false}.')
    return bool(sent["labels"])


# ===== the front end (the owner, 2026-11-23: "blazor has my approval, do the swap") =====
# Which front end the app opens: the Blazor one (blazor/, at /blazor/), the default since the swap, or the
# classic one (web/, at /workspace), kept one release as the fallback ("Swap now, delete next release").
# This computer's choice is frontend.json; none kept: the Blazor one.

FRONTENDS: tuple[str, ...] = ("blazor", "classic")
DEFAULT_FRONTEND: str = "blazor"
HOME_PAGES: dict[str, str] = {"classic": "/workspace", "blazor": "/blazor/"}


def frontend(saved: Any) -> str:
    """The front end frontend.json kept, else the Blazor one."""
    if isinstance(saved, dict) and saved.get("frontend") in FRONTENDS:
        return str(saved["frontend"])
    return DEFAULT_FRONTEND


def frontend_change(sent: Any) -> str:
    """The switch as sent: {"frontend": "blazor"} or {"frontend": "classic"}."""
    if not isinstance(sent, dict) or sent.get("frontend") not in FRONTENDS:
        raise NavigationError('Send {"frontend": "blazor"} or {"frontend": "classic"} (the old pages).')
    return str(sent["frontend"])


def home_page(saved: Any, blazor_built: bool = True) -> str:
    """The home page of the front end frontend.json names; the classic one where the Blazor one is not built
    (a checkout without `python blazor/publish.py`)."""
    chosen = frontend(saved)
    return HOME_PAGES["classic" if chosen == "blazor" and not blazor_built else chosen]


# A classic page's address, and the Blazor page that shows the same thing (the swap: every way in that names a
# classic page, a bookmark, the desktop app, a pushed grid, an agent's window, lands on the Blazor page). The
# address's own words go with it: the Blazor pages read the same ones (?path=, ?grid=, ?name=, ?at=...).
# The classic pages the server serves (their shells), each with the Blazor page it is now.
CLASSIC_PAGES: dict[str, str] = {
    "/workspace": "",
    "/notebooks": "notebooks",
    "/scripts": "scripts",
    "/streamlit/canvas": "canvas",
    "/streamlit/widget": "widgets",
    "/streamlit/perf": "perf",
}
# The home page's ?open= layers and ?view= views, each a Blazor page (an extension's area, unnamed here,
# is the Blazor page of its own name: its panel's page).
OPEN_PAGES: dict[str, str] = {"projects": "", "data": "catalog", "variables": "environment", "scm": "x-scm"}
VIEW_PAGES: dict[str, str] = {
    "erd": "erd",
    "analyze": "analyze",
    "grids": "grids",
    "new": "grids",
    "start": "",
}
# The words the classic page reads and the Blazor page does not (said by the path now).
CLASSIC_ONLY: frozenset[str] = frozenset({"open", "view", "kind"})


def is_classic_page(path: str) -> bool:
    """A classic page's shell (/workspace, /g/<grid>, /notebooks...): the swap sends it to its Blazor page."""
    return path in CLASSIC_PAGES or (path.startswith("/g/") and len(path) > 3)


def blazor_address(path: str, query: dict[str, str]) -> str:
    """The Blazor page for a classic page's address: /workspace?open=connections is /blazor/connections,
    /g/<id> is /blazor/grids?grid=<id>, /notebooks?path=x is /blazor/notebooks?path=x. The rest of the
    address's words kept; ?panel= (a grid's pop-out panel) is the Blazor panel page."""
    words = {k: v for k, v in query.items() if k not in CLASSIC_ONLY}
    if path.startswith("/g/"):
        page, words = "grids", {"grid": path[3:]} | words
    elif path == "/workspace":
        opened, view = query.get("open", ""), query.get("view", "")
        page = OPEN_PAGES.get(opened, opened) if opened else VIEW_PAGES.get(view, "")
    else:
        page = CLASSIC_PAGES.get(path, "")
    if "panel" in words:
        page = "panel"
    text = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in words.items())
    return f"/blazor/{page}" + (f"?{text}" if text else "")
