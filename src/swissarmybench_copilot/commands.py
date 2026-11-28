"""The GitHub Copilot extension's agent commands (the golden rule). Signing in and out are the user's own;
the agent has its own model, so completions are left to the editor (workbench_complete is the agent's).
Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar, req

COMMANDS: dict[str, Command] = {}


command = Registrar(COMMANDS)


@command(
    "copilot_status",
    "Copilot: installed, on, signed in, ready. "
    "Copilot's state: installed, on, signed-in login, private project, ready",
)
def copilot_status(a: dict[str, Any]) -> Any:
    return {"status": api.call("GET", "/copilot"), "panel": api.call("GET", "/copilot/panel")}


@command(
    "copilot_toggle", "GitHub Copilot on or off (off: nothing is sent)", req("on", "true or false.", "bool")
)
def copilot_toggle(a: dict[str, Any]) -> Any:
    return api.call("POST", "/copilot/toggle", {"on": a["on"]})


@command(
    "copilot_install",
    "Install Copilot's language server (on Allow). "
    "Install Copilot's language server (waits for the user's Allow)",
)
def copilot_install(a: dict[str, Any]) -> Any:
    return api.call("POST", "/copilot/install", {}, timeout=900.0)
