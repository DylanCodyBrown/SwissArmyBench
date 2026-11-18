"""The Desktop extension's agent commands (the golden rule): what the shell shows, and a page opened in it as
the tray's menu opens one. Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Arg, Command, opt

COMMANDS: dict[str, Command] = {}
Run = Callable[[dict[str, Any]], Any]


def command(name: str, summary: str, *args: Arg) -> Callable[[Run], Run]:
    def register(run: Run) -> Run:
        COMMANDS[name] = Command(name, summary, args, run, False, False)
        return run

    return register


@command("desktop_status", "The Desktop app: running, its tray icon, its windows (kind, title, page)")
def desktop_status(a: dict[str, Any]) -> Any:
    return api.call("GET", "/desktop")


@command(
    "desktop_open",
    "Open a page in the Desktop app's own window (started if needed)",
    opt("page", "home (default), workbench or blades."),
)
def desktop_open(a: dict[str, Any]) -> Any:
    return api.call("POST", "/desktop/open", {"page": a.get("page") or "home"})
