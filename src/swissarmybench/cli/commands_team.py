"""The agent's team_* commands: settings' Team box: join, start or leave a team (one GitHub repository, its projects/).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "team_status",
    "The Team box: none or joined, sync words, folders. "
    "The Team box: none or joined (owner/repo, sync words), signed in, a kept step, the folders",
    opt("remote", "true: ask GitHub now.", "bool"),
    opt("repositories", "true: the repositories to join, newest first.", "bool"),
    opt("search", "Words in owner/name."),
    opt("owners", "true: a new team's possible owners.", "bool"),
)
def team_status(a: dict[str, Any]) -> Any:
    found: dict[str, Any] = api.call("GET", "/team?remote=1" if a.get("remote") else "/team")
    if a.get("repositories"):
        query = f"?search={quote(str(a['search']))}" if a.get("search") else ""
        found["repositories"] = api.call("GET", "/team/repositories" + query)["repositories"]
    if a.get("owners"):
        found["owners"] = api.call("GET", "/team/owners")["owners"]
    return found


@command(
    "team_join",
    "Join a team's repository (on Allow). "
    "Join a team: its repository copied here, the library and shared projects folder pointed at it, the "
    "checklist; waits for Allow",
    req("repository", "owner/name."),
)
def team_join(a: dict[str, Any]) -> Any:
    return api.call("POST", "/team/join", {"repository": a["repository"]}, timeout=600)


@command(
    "team_start",
    "Start a team: a new private repository (on Allow). "
    "Start a team: a new private repository, this library pushed to it, then joined; waits for Allow",
    req("name", "The new repository's name."),
    opt("owner", "One of the account's organisations (default: the account)."),
    opt("private", "false: a public repository.", "bool"),
)
def team_start(a: dict[str, Any]) -> Any:
    body = {"name": a["name"], "owner": a.get("owner"), "private": a.get("private") is not False}
    return api.call("POST", "/team/start", body, timeout=600)


@command(
    "team_leave",
    "Leave the team; the folders go back (on Allow). "
    "Leave the team: both folders back as they were (the copy stays); no keep: the question; waits for Allow",
    opt("keep", "true: copy the team's items into this library first.", "bool"),
)
def team_leave(a: dict[str, Any]) -> Any:
    body = {} if a.get("keep") is None else {"keep": bool(a["keep"])}
    return api.call("POST", "/team/leave", body, timeout=200)
