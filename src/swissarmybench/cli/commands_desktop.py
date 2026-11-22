"""The agent's desktop_* commands: the desktop app: its windows, a page opened in one.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt


@command("desktop_status", "The desktop app: running, its windows (kind, title, page)")
def desktop_status(a: dict[str, Any]) -> Any:
    return api.call("GET", "/desktop")


@command(
    "desktop_open",
    "Open a page in a desktop app window (the app started if needed)",
    opt("page", "home (default), workbench or blades."),
)
def desktop_open(a: dict[str, Any]) -> Any:
    return api.call("POST", "/desktop/open", {"page": a.get("page") or "home"})
