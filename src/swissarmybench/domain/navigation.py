"""Getting around (the owner, 2026-11-16: "there is no navigation in the app to get back to the home page or
go back anywhere"): the places an agent can send a window to, as `app_navigate` names them.

The pages keep their views in the address (web/src/nav.ts): the home page's tabs, the dialogs over it
(Settings, Connections and its forms), the blades page's catalog and editor. The agent moves them as the
user does: Home (the mark), Back and Forward (the browser's own), or a named view where the page has one.
Pure rules, no I/O: a request read into the notice the window acts on.
"""

from __future__ import annotations

from typing import Any

# The windows that move: the home page (/workspace), the blades page (/catalog), the Workbench.
WINDOWS: tuple[str, ...] = ("home", "catalog", "workbench")

# Every window: Home (the mark: in another window it brings the home window to the front), the
# browser's Back and Forward, and the dialogs every page can open.
EVERYWHERE: tuple[str, ...] = (
    "home",
    "back",
    "forward",
    "settings",
    "connections",
    "add_connection",
    "add_api",
)
# Each window's own views. `grid:<id>`, `catalog:<name>/<schema>/<table>` and `blade:<name>` name one.
OWN: dict[str, tuple[str, ...]] = {
    "home": ("sandbox", "diagram", "query", "grid:<id>"),
    "catalog": ("catalog", "catalog:<name>[/<schema>[/<table>]]", "blade:<name>", "new_blade"),
    "workbench": (),
}
NAMED: tuple[str, ...] = ("grid", "catalog", "blade")
MAX_NAME: int = 512


class NavigationError(ValueError):
    """A window or a place that is not one: what can be said instead."""


def places(window: str) -> tuple[str, ...]:
    """What `window` can be sent to, as the agent writes it."""
    return EVERYWHERE + OWN[window]


def place(window: Any, to: Any) -> dict[str, Any]:
    """The notice for `window` to go `to`: {"window", "to"} and, for a named view, its names."""
    window = "home" if window is None else window
    if window not in WINDOWS:
        raise NavigationError(f"window is one of {', '.join(WINDOWS)}.")
    if not isinstance(to, str) or not to.strip():
        raise NavigationError(f"to is where to go: {', '.join(places(window))}.")
    to = to.strip()
    kind, _, name = to.partition(":")
    wanted = kind if name or kind in NAMED else to
    allowed = {p.partition(":")[0] for p in places(window)}
    if wanted not in allowed or (kind in ("grid", "blade") and not name):
        raise NavigationError(
            f"The {window} window cannot go to {to!r}. It can go to: {', '.join(places(window))}."
        )
    if len(name) > MAX_NAME:
        raise NavigationError(f"That name is longer than {MAX_NAME} characters.")
    notice: dict[str, Any] = {"window": window, "to": kind}
    if kind == "grid":
        notice["grid"] = name
    elif kind == "blade":
        notice["name"] = name
    elif kind == "catalog" and name:
        parts = name.split("/", 2)
        if not all(parts):
            raise NavigationError(
                "A catalog's view is catalog:<name>, catalog:<name>/<schema> or "
                "catalog:<name>/<schema>/<table>."
            )
        notice |= dict(zip(("catalog", "schema", "table"), parts, strict=False))
    return notice


def said(notice: dict[str, Any]) -> str:
    """The move in the audit log's words: "home window to grid g1", never more than the names."""
    named = [str(notice[k]) for k in ("grid", "name", "catalog", "schema", "table") if k in notice]
    return f"{notice['window']} window to {notice['to']}{' ' + '/'.join(named) if named else ''}"
