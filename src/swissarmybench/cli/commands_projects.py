"""The agent's projects_* commands: the Project Explorer: every project as a card, sorted; the project types explained.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt


@command(
    "projects_list",
    "Every project as a card. Type, counts, Git branch, times; the projects folder's and opened ones",
    opt("by", "opened, name, type, changed, created or custom (default: the remembered sort)."),
    opt("descending", "true: largest first.", "bool"),
    opt("type", "Only this type."),
    opt("q", "Words in a name, folder or notebook."),
)
def projects_list(a: dict[str, Any]) -> Any:
    query = {k: str(a[k]).lower() if isinstance(a[k], bool) else a[k] for k in ("by", "descending", "type", "q")
             if a.get(k) is not None}  # fmt: skip
    return api.call("GET", "/projects/explorer" + (f"?{urlencode(query)}" if query else ""))


@command(
    "projects_sort",
    "The Project Explorer's sort, or its custom order. "
    "The Project Explorer's sort (remembered), or its custom order: order, or move a card left/right",
    opt("by", "opened, name, type, changed, created or custom."),
    opt("descending", "true: largest first.", "bool"),
    opt("order", "Custom: the projects' folders in order.", "json"),
    opt("move", "A project's folder to move."),
    opt("step", "-1 left, 1 right.", "int"),
)
def projects_sort(a: dict[str, Any]) -> Any:
    if a.get("move"):
        return api.call("POST", "/projects/sort", {"move": a["move"], "by": a.get("step") or 1})
    if a.get("order") is not None:
        return api.call("POST", "/projects/sort", {"order": a["order"]})
    return api.call(
        "POST", "/projects/sort", {"by": a.get("by") or "opened", "descending": a.get("descending") is True}
    )


@command(
    "projects_folders",
    "The Local and Shared projects folders (set: on Allow). "
    "Settings' Local and Shared projects folders: read both; set one (waits for the user's Allow)",
    opt("which", "local (default) or shared."),
    opt("folder", "The folder to set."),
    opt("default", "true: local back to the default; shared: none.", "bool"),
)
def projects_folders(a: dict[str, Any]) -> Any:
    if not a.get("folder") and not a.get("default"):
        return api.call("GET", "/projects/folder")
    body = {"default": True} if a.get("default") else {"folder": a.get("folder") or ""}
    return api.call("POST", "/projects/folder", body | {"which": a.get("which") or "local"})
