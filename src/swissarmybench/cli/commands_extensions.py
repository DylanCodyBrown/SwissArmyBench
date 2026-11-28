"""The agent's extensions_* commands: the user's own folder extensions in the library (the packaged ones are
built in, the owner 2026-11-27: installing or removing one answers in one sentence that it is built in).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "extensions_list",
    "The Extensions page: the library's folder extensions (and a built-in feature's own panel)",
)
def extensions_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/extensions")


@command(
    "extensions_install",
    "A folder extension's missing packages installed, then loaded again (waits for the user's Allow)",
    req("id", "The extension's id, from extensions_list."),
)
def extensions_install(a: dict[str, Any]) -> Any:
    return api.call("POST", "/extensions/install", {"id": a["id"]}, timeout=200)


@command(
    "extensions_remove",
    "Remove a folder extension: its folder to the trash (waits for the user's Allow)",
    req("id", "The extension's id, from extensions_list."),
)
def extensions_remove(a: dict[str, Any]) -> Any:
    return api.call("POST", "/extensions/remove", {"id": a["id"]}, timeout=200)


@command(
    "extensions_new",
    "New folder extension in the library (extensions/<id>/: one route, one command; waits for Allow)",
    req("id", "Its id: lower case, digits, _ (its routes /<id>/, commands <id>_...)."),
    opt("name", "Its name."),
    opt("project_type", "A project type it adds (contract.json)."),
)
def extensions_new(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("id", "name", "project_type") if a.get(k)}
    return api.call("POST", "/extensions/new", body, timeout=200)
