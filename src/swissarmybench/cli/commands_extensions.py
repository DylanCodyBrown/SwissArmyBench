"""The agent's extensions_* commands: extensions: what plugs into the base (Streamlit, Accounting, Power Apps).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "extensions_list",
    "The Extensions page: each extension, its status (preinstalled, available, installed, coming)",
)
def extensions_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/extensions")


@command(
    "extensions_install",
    "Install an available extension (waits for the user's Allow; the app stops, installs it, restarts)",
    req("id", "The extension's id, from extensions_list."),
)
def extensions_install(a: dict[str, Any]) -> Any:
    return api.call("POST", "/extensions/install", {"id": a["id"]}, timeout=200)


@command(
    "extensions_remove",
    "Remove an installed extension (waits for the user's Allow; the app stops, removes it, restarts)",
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
