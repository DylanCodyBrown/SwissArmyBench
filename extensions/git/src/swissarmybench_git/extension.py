"""The Git extension as the base reads it (swissarmybench/extensions.py): its description, its rail area (the
Source Control page) and the footer's mark as data, its door, its agent commands and its Session page words.
This is the extension's composition root: it builds its adapters and hands them to its service.

The app never runs git: GitHub's web API does the work (adapters/github.py), signed in with the user's GitHub
account (the token in the keyring only). Real GitHub is api.github.com and github.com/login (the device flow);
SWISSARMYBENCH_GITHUB_API and SWISSARMYBENCH_GITHUB_WEB name a stand-in on 127.0.0.1 instead (tests only).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from swissarmybench_git import __version__

ID = "git"
NAME = "Git"
VERSION = __version__
DESCRIPTION = (
    "GitHub sync for the team library and shared projects, and a Source Control page with a commit graph."
)
ADDS = [
    "Sign in to GitHub (a token, or Sign in with GitHub)",
    "Join or start a team: one repository for the team library and shared projects",
    "Pull (three-way merges, conflicts beside the file) and Push, never forced",
    "The Source Control page: changes, staging, Commit, Sync, the graph",
    "Monaco's diff editor for every change and commit",
    "The footer's mark when the open project is out of sync",
]
# The OAuth App's client id for Sign in with GitHub (the device flow): the owner registered the app on GitHub and
# filled it in (2026-11-18). Empty: Use a token only (Settings says so).
CLIENT_ID = "Ov23liqU3fkSNKrLtfQ7"  # public: a device flow needs no client secret
API = "https://api.github.com"
WEB = "https://github.com"
# Its commands' areas (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (
    (
        "github",
        "GitHub sync: sign-in status, clone, connect, pull and push the team library and shared projects",
    ),
    (
        "scm",
        "Source Control: changes, stage, discard, commit, sync, history, a commit's files, diffs, branches",
    ),
)
# The rail's area it adds (the page draws it from this; web/ never names the extension), and the footer's mark.
RAIL = ({"area": "scm", "name": "Source Control", "icon": "source-control", "mark": "/git/mark"},)


def _area(what: str) -> tuple[str, str, dict[str, Any]]:
    return what, "scm", {"place": "area", "area": "scm"}


def _which(x: Any) -> str:
    return "the team library" if x.get("which") == "library" else "the shared projects"


# The Session page's words for each audit entry (names and counts only, never a value or the token).
SESSION_RULES: dict[str, Any] = {
    "github_sign_in": lambda d, x: _area("Signed in to GitHub"),
    "github_sign_out": lambda d, x: _area("Signed out of GitHub"),
    "github_clone": lambda d, x: _area(f"Cloned {x.get('files')} files into {_which(x)} folder"),
    "github_connect": lambda d, x: _area(f"Connected {_which(x)} folder to GitHub"),
    "github_disconnect": lambda d, x: _area(f"Disconnected {_which(x)} folder from GitHub"),
    "github_pull": lambda d, x: _area(
        f"Pulled {_which(x)} ({x.get('files')} files, {x.get('conflicts')} conflicts)"
    ),
    "github_push": lambda d, x: _area(f"Pushed {x.get('files')} files of {_which(x)}"),
    "scm_discard": lambda d, x: _area(f"Discarded the changes in {x.get('files')} files"),
    "scm_checkout": lambda d, x: _area(
        "Made a branch on GitHub" if x.get("create") else "Checked out a branch"
    ),
}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def routes(services: Any) -> list[Any]:
    """Its routes, its service built from the base's (the audit log, the live updates, the agent's approvals,
    the meta store folder, the shared projects folder, the open project) and its own adapters."""
    from swissarmybench_git.adapters import github
    from swissarmybench_git.server import routes as door
    from swissarmybench_git.services.scm import SourceControl

    api = _env("SWISSARMYBENCH_GITHUB_API", API)
    web = _env("SWISSARMYBENCH_GITHUB_WEB", WEB)

    def folders(which: str) -> str | None:
        if which == "library":
            return str(services.library.info()["folder"])
        shared = services.project_explorer.shared_folder()
        return str(shared) if shared else None

    async def use_folder(which: str, folder: str) -> None:
        # A clone made this folder: Settings points at it (the agent's Allow was asked for the clone).
        if which == "library":
            await services.library.set_folder({"folder": folder}, "user")
        else:
            await services.project_explorer.set_folder({"which": "shared", "folder": folder}, "user")

    async def pulled(which: str) -> None:
        # Files changed here: the shared catalog reads the meta store again; the cards are drawn again.
        if which == "library":
            await services.shared_catalog.refresh("user")
        else:
            await services.live.broadcast({"type": "projects_changed"})

    def project() -> str | None:
        found = services.sab_projects.state().get("project") or {}
        return str(found["folder"]) if found.get("folder") else None

    service = SourceControl(
        services.ws,
        lambda token: github.GitHubClient(api, web, token),
        github.GitHubToken(),
        github.SyncLinks(Path(services.settings.state_dir) / "sync.json"),
        github.SyncFolder(),
        services.agent.approvals,
        folders,
        use_folder,
        client_id=_env("SWISSARMYBENCH_GITHUB_CLIENT_ID", CLIENT_ID),
        pulled=pulled,
        known_secrets=lambda: github.known_secrets(services),
        project=project,
    )
    services.git = service  # tests
    # The base's Team box (Settings): one repository for the team library and its projects/.
    from swissarmybench_git.services.team import TeamPort

    services.hooks.team = TeamPort(service, web)

    async def changed(*_: Any) -> None:
        await services.live.broadcast({"type": "sync_changed"})

    # The footer's mark follows a save and an opened project (no polling: it reads the files here).
    services.sab_projects.saved.append(changed)
    services.sab_projects.opened.append(changed)
    return door.routes(service)


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_git.commands import COMMANDS

    return COMMANDS
