"""The agent's files_* commands: folders and files on this computer (the file chooser).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "files_list",
    "A folder's subfolders and files on this computer (names, sizes, dates; nothing read)",
    opt("path", "The folder (default: the home folder)."),
    opt("suffixes", "Only files ending so, as .csv,.xlsx."),
    opt("hidden", "Hidden files and folders too.", "bool"),
)
def files_list(a: dict[str, Any]) -> Any:
    params = {
        "path": a.get("path"),
        "suffixes": a.get("suffixes"),
        "hidden": "1" if a.get("hidden") else None,
    }
    return api.call("GET", "/folders", params=params)


@command(
    "files_new_folder",
    "Make a new folder inside a folder (the file picker's New folder)",
    req("path", "The folder it goes in."),
    req("name", "The new folder's name."),
)
def files_new_folder(a: dict[str, Any]) -> Any:
    return api.call("POST", "/folders/new", {"path": a["path"], "name": a["name"]})
