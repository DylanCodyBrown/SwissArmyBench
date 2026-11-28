"""The Git extension's agent commands (the golden rule: every action on its pages is one of these but the
GitHub sign-in and sign-out, the user's own). The base's registry (swissarmybench/cli/commands.py) takes them when
the extension is on, so each is an MCP tool too. What changes files here or on GitHub waits for the user's Allow.
Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar, opt, req

COMMANDS: dict[str, Command] = {}
LONG = 600.0  # a pull or a push of many files, or the Allow it waits for
WHICH = opt("which", "library (the team library folder, default) or shared (the shared projects folder).")


command = Registrar(COMMANDS)


def _which(a: dict[str, Any]) -> str:
    return str(a.get("which") or "library")


def _q(a: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: a[k] for k in keys if a.get(k) not in (None, "")}


@command(
    "github_status",
    "GitHub sync: who is signed in (never the token), each folder's repository, branch and status words "
    "(Up to date, 3 changes to push, 2 behind: Pull, Conflicts: 2), the footer's mark",
    opt("remote", "true: ask GitHub about each head now (at most once a minute).", "bool"),
)
def github_status(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git?remote=1" if a.get("remote") else "/git")


@command("github_repositories", "The signed-in user's GitHub repositories (owner/name, default branch)")
def github_repositories(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git/repositories")


@command(
    "github_clone",
    "Clone a GitHub repository into an empty or new folder, which becomes the team library or the shared projects "
    "folder; waits for Allow",
    req("repository", "owner/name."),
    WHICH,
    opt("branch", "The branch (default: the repository's default)."),
    opt("folder", "An empty or new folder (default: the one Settings names, when empty)."),
)
def github_clone(a: dict[str, Any]) -> Any:
    body = {"which": _which(a)} | _q(a, "repository", "branch", "folder")
    return api.call("POST", "/git/clone", body, timeout=LONG)


@command(
    "github_connect",
    "Connect the team library or shared projects folder to a GitHub repository (compared, nothing written); "
    "waits for Allow",
    req("repository", "owner/name."),
    WHICH,
    opt("branch", "The branch (default: the repository's default)."),
)
def github_connect(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/git/connect", {"which": _which(a)} | _q(a, "repository", "branch"), timeout=LONG
    )


@command("github_disconnect", "Forget a folder's GitHub link (no file touched)", WHICH)
def github_disconnect(a: dict[str, Any]) -> Any:
    return api.call("POST", "/git/disconnect", {"which": _which(a)})


@command(
    "github_pull",
    "Pull a folder from GitHub: theirs where only they changed, three-way merges, conflicts as <name>.theirs; "
    "waits for Allow",
    WHICH,
)
def github_pull(a: dict[str, Any]) -> Any:
    return api.call("POST", "/git/pull", {"which": _which(a)}, timeout=LONG)


@command(
    "github_push",
    "Push a folder's changes to GitHub as one commit (fast-forward only; refused when behind or a file holds a "
    "secret); waits for Allow",
    WHICH,
    opt("message", "The commit message (default: Update from Swiss Army Bench: N files)."),
    opt("path", "A shared project's folder: only its files."),
)
def github_push(a: dict[str, Any]) -> Any:
    return api.call("POST", "/git/push", {"which": _which(a)} | _q(a, "message", "path"), timeout=LONG)


@command(
    "scm_changes",
    "The Source Control page: each connected folder's Merge Changes, Staged Changes and Changes (letters A M D "
    "U !), branch, ahead and behind",
    WHICH,
)
def scm_changes(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git/changes", params=_q(a, "which"))


@command(
    "scm_stage",
    "Stage Changes (or unstage): the files the next commit takes",
    req("paths", "The files' paths in the folder.", "list"),
    WHICH,
    opt("unstage", "true: Unstage Changes.", "bool"),
)
def scm_stage(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/git/stage", {"which": _which(a), "paths": a["paths"], "unstage": bool(a.get("unstage"))}
    )


@command(
    "scm_discard",
    "Discard Changes: files back to their last synced version (a new file deleted); waits for Allow",
    req("paths", "The files' paths in the folder.", "list"),
    WHICH,
)
def scm_discard(a: dict[str, Any]) -> Any:
    return api.call("POST", "/git/discard", {"which": _which(a), "paths": a["paths"]}, timeout=LONG)


@command(
    "scm_commit",
    "Commit: the named files (else the staged, else every change) as one commit on GitHub; sync pulls first; "
    "waits for Allow",
    req("message", "The commit message."),
    WHICH,
    opt("paths", "The files to commit.", "list"),
    opt("sync", "true: Commit & Sync (Pull first).", "bool"),
)
def scm_commit(a: dict[str, Any]) -> Any:
    body = {"which": _which(a), "message": a["message"], "paths": a.get("paths"), "sync": bool(a.get("sync"))}
    return api.call("POST", "/git/commit", body, timeout=LONG)


@command("scm_sync", "Sync Changes: Pull, then Push; waits for Allow", WHICH)
def scm_sync(a: dict[str, Any]) -> Any:
    return api.call("POST", "/git/sync", {"which": _which(a)}, timeout=LONG)


@command(
    "scm_history",
    "The graph's history: the branch's commits from GitHub (100 a page; id, parents, subject, author, date), "
    "the refs and the uncommitted count",
    WHICH,
    opt("page", "The page (1: the newest 100).", "int"),
)
def scm_history(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git/history", params={"which": _which(a), "page": a.get("page") or 1})


@command(
    "scm_commit_files",
    "One commit's files (each with its letter) and its parent",
    req("commit", "The commit's SHA."),
    WHICH,
)
def scm_commit_files(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git/commit-files", params={"which": _which(a), "commit": a["commit"]})


@command(
    "scm_diff",
    "A file's change as unified diff text: since the last sync, in a commit (against its parent), or a "
    "conflict (yours against theirs)",
    req("path", "The file's path in the folder."),
    WHICH,
    opt("commit", "A commit's SHA."),
    opt("conflict", "true: the conflict's two sides.", "bool"),
)
def scm_diff(a: dict[str, Any]) -> Any:
    params = {"which": _which(a), "path": a["path"], "unified": "1"} | _q(a, "commit")
    if a.get("conflict"):
        params["conflict"] = "1"
    return api.call("GET", "/git/diff", params=params)


@command("scm_branches", "The repository's branches and the current one", WHICH)
def scm_branches(a: dict[str, Any]) -> Any:
    return api.call("GET", "/git/branches", params={"which": _which(a)})


@command(
    "scm_checkout",
    "Checkout to... another branch (refused while files here have changes), or create one on GitHub from the "
    "last synced commit; waits for Allow",
    req("branch", "The branch's name."),
    WHICH,
    opt("create", "true: Create Branch... first.", "bool"),
)
def scm_checkout(a: dict[str, Any]) -> Any:
    body = {"which": _which(a), "branch": a["branch"], "create": bool(a.get("create"))}
    return api.call("POST", "/git/checkout", body, timeout=LONG)
