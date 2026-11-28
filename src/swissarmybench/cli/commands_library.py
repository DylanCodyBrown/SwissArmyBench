"""The agent's library_* commands: the library: the folder of connections, APIs, vaults, blades and variables (a Git repository).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "library_info",
    "The library: its folder and what is in it. "
    "The library: its folder (a Git repository's working copy), what is in it, what stays on this computer",
)
def library_info(a: dict[str, Any]) -> Any:
    return api.call("GET", "/library")


@command(
    "library_set_folder",
    "Point the library at another folder (on Allow). "
    "Point the library folder at a local copy of the team's repository, or the default; waits for Allow",
    opt("folder", "The folder's whole path; none: the default (~/.swissarmybench/library)."),
)
def library_set_folder(a: dict[str, Any]) -> Any:
    return api.call("PUT", "/library", {"folder": a.get("folder")}, timeout=200)


@command(
    "library_setup",
    "Set up this computer: the team library's checklist. "
    "Set up this computer (a team library): vault sign-ins, values to type once, each connection's status, shared projects",
    opt("check", "true: check every key vault again now.", "bool"),
)
def library_setup(a: dict[str, Any]) -> Any:
    return api.call("GET", "/library/setup?check=1" if a.get("check") else "/library/setup", timeout=120)


@command(
    "library_setup_move_to_vault",
    "Move a connection's keyring password to a key vault. "
    "Move a connection's keyring password to a key vault's secret, so the next person needs nothing",
    req("connection", "The connection."),
    req("secret", 'Its password\'s name in the code (secret("...")).'),
    req("vault", "The key vault."),
    opt("vault_secret", "The secret's name in the vault (a new entry)."),
    opt("env", "An entry the vault has already: its variable."),
)
def library_setup_move_to_vault(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("connection", "secret", "vault", "vault_secret", "env") if a.get(k)}
    return api.call("POST", "/library/setup/move-to-vault", body)
