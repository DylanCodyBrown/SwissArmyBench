"""The panels Settings can turn off (the owner, 2026-11-15: "add app level settings with a option to
hide or turn panels off if wanted by the user they default on every time sab is opened").

Each panel has a switch, on unless the user turns it off. A panel turned off is gone (not folded).
The switches are the server's, in memory: shared by every window, kept through a reload, and every
one on again when Swiss Army Bench starts. Pure rules, no I/O.
"""

from __future__ import annotations

from typing import Any

# Each panel: its id (the page's and the agent's), the page it is on, and its name in Settings.
PANELS: tuple[tuple[str, str, str], ...] = (
    ("workbench.data", "Workbench", "Data panel"),
    ("workbench.tables", "Workbench", "Tables"),
    ("workbench.blades", "Workbench", "Blade variables"),
    ("workbench.streamlit", "Workbench", "Streamlit cells"),
    ("workbench.console", "Workbench", "Console"),
    ("workbench.variables", "Workbench", "Variables"),
    ("workbench.status", "Workbench", "Status bar"),
    # The Workbench's modes (2026-11-15): each document's own panels.
    ("workbench.properties", "Workbench", "Properties"),
    ("workbench.state", "Workbench", "State"),
    ("workbench.starters", "Workbench", "Starters"),
    ("workbench.outline", "Workbench", "Outline"),
    ("workbench.runSettings", "Workbench", "Run settings"),
    ("workbench.runHistory", "Workbench", "Run history"),
    ("grid.ribbon", "Grid page", "Ribbon"),
    ("grid.steps", "Grid page", "Steps strip"),
    ("grid.status", "Grid page", "Status bar"),
    # The rail (2026-11-16): the areas down the left of every page and window (web/src/rail.ts).
    ("app.rail", "Every page", "Navigation rail"),
)
IDS: tuple[str, ...] = tuple(panel for panel, _, _ in PANELS)


class PanelError(ValueError):
    """A switch that is not a panel's, or not on or off."""


def defaults() -> dict[str, bool]:
    """Every panel on: how Swiss Army Bench starts."""
    return dict.fromkeys(IDS, True)


def changes(sent: Any) -> dict[str, bool]:
    """Switches as sent: {"workbench.console": false, ...}, each a known panel's, true or false."""
    if not isinstance(sent, dict) or not sent:
        raise PanelError('Send the switches: {"workbench.console": false}.')
    unknown = [key for key in sent if key not in IDS]
    if unknown:
        raise PanelError(f"No panel is called {unknown[0]!r}. The panels: {', '.join(IDS)}.")
    if not all(isinstance(value, bool) for value in sent.values()):
        raise PanelError("A panel's switch is true (on) or false (off).")
    return {str(key): bool(value) for key, value in sent.items()}


def listing(state: dict[str, bool]) -> list[dict[str, Any]]:
    """The panels in Settings' order: id, page, name, on."""
    return [{"id": panel, "page": page, "name": name, "on": state[panel]} for panel, page, name in PANELS]
