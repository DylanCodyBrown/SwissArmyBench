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
