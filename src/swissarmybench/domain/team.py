"""A team (the owner, 2026-11-19: "you have made linking a meta store and shared project folder way too
difficult; the settings menu makes no sense"): ONE GitHub repository holds the team's library (connections,
key vaults, variables, blades, APIs, relationship sets, colours, the shared catalog) at its top and the team's
shared projects in its projects/ folder. Settings' Team box joins one, starts one or leaves it; the screen
calls the shared library the Team library (the code keeps its names: library, shared_folder, sync).

  layout       a new team's repository: README.md (what goes where), .gitignore (local/ and .sab/data/ never
               go), projects/ (its README.md, so the folder exists on GitHub)
  local copy   the app makes it itself, never asking for a path: the state folder's team/<owner>-<repo>/ (the
               library's own default is in the state folder too; the projects are reached from the Projects
               page, so the folder need not be seen)
  steps        Join: sign in, pick the repository, the local copy, Set up this computer;
               Start: sign in, a name, the repository made and the library pushed, Set up (GitHub sync is
               built in: nothing to install first, the owner 2026-11-27)
  pending      Install restarts the app: the step it was at is kept in the state folder's team.json and
               taken up again after the restart (a day at most)
  leave        stops sharing: the library goes back to this computer's own (the folder it was before), the
               shared projects folder to what it was; asked first whether to keep a copy of the team's items
               (a file this computer's library has already, different, stays as it is); the local copy stays
  words        the Joined row's sync words, only when there is something to do (design principle 7.9)

Pure rules: no I/O, no clock (the time is passed in).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from swissarmybench.domain import library as library_rules

PROJECTS: str = "projects"  # the shared projects' folder inside the team's repository
TEAM_FOLDER: str = "team"  # the local copies' folder in the state folder
PENDING_SECONDS: float = 24 * 3600.0  # a step kept over a restart is taken up within a day
ACTIONS: tuple[str, ...] = ("join", "start")
STEPS: dict[str, tuple[str, ...]] = {
    "join": ("sign_in", "pick", "setup"),
    "start": ("sign_in", "name", "setup"),
}
# What a team's library item is (Leave's copy takes these and nothing else: not projects/, not README.md).
ITEM_FOLDERS: tuple[str, ...] = (
    library_rules.CONNECTIONS,
    library_rules.VAULTS,
    library_rules.BLADES,
    library_rules.APIS,
    library_rules.RELATIONSHIP_SETS,
)
ITEM_FILES: tuple[str, ...] = (library_rules.VARIABLES_FILE, library_rules.COLOURS_FILE)
# Never copied into a new team's repository from this computer's library (the layout writes its own).
NOT_COPIED: tuple[str, ...] = ("README.md", ".gitignore")

README: str = """# Team library

Your team's Swiss Army Bench library and shared projects, in one repository. Everyone who joins the team
(Swiss Army Bench: Settings, Team, Join a team...) gets the same connections, key vaults, variables, blades
and APIs, and the projects in projects/.

    connections/        each connection (a .blade.py file: its settings and code)
    vaults/             each key vault
    apis/               each API: its client, its blades, its OpenAPI document
    blades/             functions, analyses, snippets
    relationship-sets/  saved sets of relationships
    catalog/            the shared catalog: each connection's tables and keys (names only)
    variables.toml      each variable's name and where its value comes from
    colours.toml        each connection's colour
    projects/           the team's shared projects, one folder each
    local/              this computer only (never pushed: see .gitignore)

Nothing here holds a password, a secret, a token or a row of data. Secrets stay in each computer's keyring
or in a key vault; Set up this computer lists what a new computer still needs.
"""

GITIGNORE: str = """# This computer only: paths and values that differ per computer.
local/
# A project's kept rows stay on the computer that kept them.
.sab/data/
# Files being written.
*.tmp
*.part
"""

PROJECTS_README: str = """# Shared projects

Each folder here is one of the team's projects. Share a project from the Projects page; Make a local copy
works on one without changing the team's.
"""

NEEDS_WORDS: str = "GitHub sync did not start here, and a team needs it"
_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class TeamError(ValueError):
    """A team request that cannot be done as asked (why, in words)."""


def layout() -> dict[str, bytes]:
    """A new team repository's own files (path -> bytes)."""
    return {
        "README.md": README.encode(),
        ".gitignore": GITIGNORE.encode(),
        f"{PROJECTS}/README.md": PROJECTS_README.encode(),
    }


def check_name(raw: Any) -> str:
    """A new repository's name, as GitHub takes it: letters, digits, '.', '-', '_' (spaces become '-')."""
    text = re.sub(r"\s+", "-", str(raw or "").strip())
    if not _NAME.match(text) or text in (".", "..") or text.endswith(".git"):
        raise TeamError(
            "Name the repository with letters, digits, '-', '_' or '.' (for example team-library)."
        )
    return text


def check_repository(raw: Any) -> str:
    """owner/name (also as copied from the browser: https://github.com/owner/name)."""
    text = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", str(raw or "").strip())
    text = text.removesuffix("/").removesuffix(".git")
    if not _REPOSITORY.match(text) or text.split("/")[1] in (".", ".."):
        raise TeamError("Pick the team's repository (owner/name).")
    return text


def check_owner(raw: Any) -> str | None:
    """The new repository's owner: the signed-in account (None) or one of its organisations."""
    text = str(raw or "").strip()
    if not text:
        return None
    if not _OWNER.match(text):
        raise TeamError(f"{text[:60]!r} is not a GitHub account or organisation.")
    return text


def local_copy(repository: str) -> tuple[str, str]:
    """Where the app keeps a team's local copy, under the state folder: team/<owner>-<repo>, the same every
    time (the parts, joined by the adapter)."""
    owner, _, name = repository.partition("/")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{owner}-{name}").strip(".-") or "team"
    return TEAM_FOLDER, safe


# ===== the steps, and the one kept over a restart =====


def check_action(raw: Any) -> str:
    action = str(raw or "")
    if action not in ACTIONS:
        raise TeamError('action is "join" or "start".')
    return action


def pending(action: str, step: str, now: float) -> dict[str, Any]:
    """team.json's record of a step to take up after the restart."""
    if step not in STEPS[action]:
        raise TeamError(f"{step!r} is not a step of {action}.")
    return {"action": action, "step": step, "since": now}


def next_step(action: str, sync_on: bool, signed_in: bool) -> str:
    """The first step still to do: sign in, then pick (join) or name (start)."""
    if not sync_on or not signed_in:
        return "sign_in"
    return STEPS[action][1]


def resume(record: Any, sync_on: bool, signed_in: bool, now: float) -> dict[str, Any] | None:
    """A step kept over a restart, taken up: {"action", "step"} (the step it is at now), or None (none kept,
    a broken record, or older than a day)."""
    if not isinstance(record, Mapping):
        return None
    action = record.get("action")
    since = record.get("since")
    if action not in ACTIONS or not isinstance(since, int | float) or isinstance(since, bool):
        return None
    if now - float(since) > PENDING_SECONDS or now < float(since) - 60:
        return None
    return {"action": action, "step": next_step(str(action), sync_on, signed_in)}


# ===== the repositories offered =====


def newest_first(repositories: Iterable[Mapping[str, Any]], search: str = "") -> list[dict[str, Any]]:
    """The repositories the account can reach, newest change first, those it can push to only; a search keeps
    the ones whose owner/name holds every word (any case)."""
    words = [w for w in search.casefold().split() if w]
    found = [
        dict(r)
        for r in repositories
        if r.get("can_push", True) and all(w in str(r.get("repository") or "").casefold() for w in words)
    ]
    found.sort(key=lambda r: str(r.get("repository") or "").casefold())
    found.sort(key=lambda r: str(r.get("pushed") or ""), reverse=True)
    return found


# ===== what goes into a new team, what Leave keeps =====


def is_item(path: str) -> bool:
    """A library item's file: under connections/, vaults/, blades/, apis/, relationship-sets/, or
    variables.toml, colours.toml (never local/, catalog/, projects/, README.md, .gitignore)."""
    top = path.split("/", 1)[0]
    return path in ITEM_FILES or ("/" in path and top in ITEM_FOLDERS)


def copied_to_new_team(paths: Iterable[str]) -> list[str]:
    """This computer's library files that go into a new team's repository: everything but .git/ and the
    layout's own README.md and .gitignore (local/ is copied too: .gitignore keeps it here)."""
    return sorted(
        p
        for p in paths
        if p not in NOT_COPIED and p.split("/", 1)[0] != ".git" and p.split("/", 1)[0] != PROJECTS
    )


def leave_plan(team: Mapping[str, str], own: Mapping[str, str], keep: bool) -> dict[str, list[str]]:
    """Leave's copy: path -> content hash on each side. keep: every team item this computer's own library
    lacks is copied; one it has already, the same, is skipped; different, it stays as it is (kept)."""
    if not keep:
        return {"copy": [], "same": [], "kept": []}
    items = sorted(p for p in team if is_item(p))
    return {
        "copy": [p for p in items if p not in own],
        "same": [p for p in items if own.get(p) == team[p]],
        "kept": [p for p in items if p in own and own[p] != team[p]],
    }


def leave_question(repository: str) -> dict[str, Any]:
    """What Leave asks first (the user's answer is its keep)."""
    return {
        "question": f"Leave {repository}? Keep a copy of the team's connections, vaults, variables and "
        "blades in this computer's own library?",
        "choices": [
            {"keep": True, "label": "Keep a copy"},
            {"keep": False, "label": "Leave without a copy"},
        ],
    }


def leave_words(repository: str, folder: str, copied: int, kept: int) -> str:
    said = f"You left {repository}. Its local copy stays in {folder}."
    if copied:
        said += f" {copied} item{'' if copied == 1 else 's'} copied into this computer's library"
        said += f" ({kept} of yours kept as they were)." if kept else "."
    return said


def sync_words(found: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The Joined row's word: what needs doing (Pull, changes to push, conflicts, an error), else None:
    silence means up to date (design principle 7.9)."""
    if not found or not found.get("connected"):
        return None
    if found.get("error"):
        return {"state": "error", "words": "GitHub could not be asked"}
    state = str(found.get("state") or "")
    if state not in ("conflicts", "behind", "changes"):
        return None
    return {"state": state, "words": str(found.get("words") or "")}
