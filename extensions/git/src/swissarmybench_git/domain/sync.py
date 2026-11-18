"""The Git extension's rules: GitHub sync and the Source Control page (the owner, 2026-11-18: "connect a local GitHub repo and push and pull and fork projects so
you could work a shared project and clone it into a local project"; chosen: "Built-in, signed in to GitHub").
The app never runs git: it talks to GitHub's web API (adapters/github.py) and these rules decide what moves.

  link         a folder's link to a repository (owner/name, branch, the last synced commit, each synced file's
               blob SHA: the base of a three-way merge, the conflicts left), kept in the state folder's
               sync.json by the folder's path, never in the repository
  what syncs   the folder's files minus its .gitignore files' patterns (a small matcher), and always minus
               .git/, local/ at the top, .sab/data/ anywhere and <name>.theirs; never a file over 50 MB
  blob SHA     git's own: sha1 of "blob <length>\\0" and the bytes, so a file here is compared with GitHub's
               without downloading it
  pull         each path's base, here and there: theirs taken where only they changed, a line-based three-way
               merge (diff3 on difflib) where both did; a true conflict leaves this file, saves theirs beside
               it as <name>.theirs and is listed; deleted there and unchanged here goes, changed here stays
  push         the files changed since the base (in a project's subfolder, for a shared card), refused when one
               looks like it holds a secret (and which is said), refused while a conflict waits
  words        each folder's status: Not connected, Up to date, 3 changes to push, 2 behind: Pull, Conflicts: 2
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_FILE_BYTES: int = 50 * 1024 * 1024  # GitHub refuses a file larger than 50 MB through its API
THEIRS: str = ".theirs"
WHICH: tuple[str, ...] = ("library", "shared")  # the meta store folder, the shared projects folder
WHICH_WORDS: dict[str, str] = {"library": "the meta store folder", "shared": "the shared projects folder"}
DEFAULT_MESSAGE: str = "Update from Swiss Army Bench"
SCOPE: str = "repo"  # the device flow's scope: a classic OAuth App reads and writes the user's repositories
KEYRING_USER: str = "github/token"


class SyncError(ValueError):
    """A request GitHub sync cannot do, in plain words."""


# ===== git's blob hash =====


def blob_sha(data: bytes) -> str:
    """git's blob SHA: sha1 over "blob <length>\\0" and the bytes (what GitHub's trees list)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


# ===== repositories and paths =====

_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def check_repository(raw: Any) -> str:
    """owner/name, also from https://github.com/owner/name(.git) as copied from the browser."""
    text = str(raw or "").strip()
    text = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", text).removesuffix("/").removesuffix(".git")
    if (
        not _REPO.match(text)
        or text.endswith((".", "/"))
        or ("/." in text and text.split("/")[1] in (".", ".."))
    ):
        raise SyncError("Name the repository as owner/name (for example made-up-team/meta-store).")
    return text


def check_branch(raw: Any) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    if (
        not _BRANCH.match(text)
        or ".." in text
        or text.startswith(("/", "-"))
        or text.endswith((".", "/", ".lock"))
    ):
        raise SyncError(f"{text!r} is not a branch name.")
    return text


def check_which(raw: Any) -> str:
    which = str(raw or "library")
    if which not in WHICH:
        raise SyncError(
            'which is "library" (the meta store folder) or "shared" (the shared projects folder).'
        )
    return which


def safe_path(path: str) -> bool:
    """A path from GitHub's tree that may be written inside the folder: relative, no .., no .git, no drive."""
    if not path or path.startswith(("/", "\\")) or "\\" in path or ":" in path or "\0" in path:
        return False
    parts = path.split("/")
    return all(p not in ("", ".", "..") for p in parts) and ".git" not in (p.casefold() for p in parts)


# ===== what syncs: .gitignore's patterns and the app's own exclusions =====


def _pattern(text: str) -> re.Pattern[str]:
    """A .gitignore glob as a regular expression over a slash path: * and ? within a part, ** across parts."""
    out = []
    i = 0
    while i < len(text):
        c = text[i]
        if text.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if text.startswith("/**", i) and i + 3 == len(text):
            out.append("/.*")
            i += 3
            continue
        if text.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            end = text.find("]", i + 1)
            if end == -1:
                out.append(re.escape(c))
            else:
                inside = text[i + 1 : end].replace("\\", "\\\\")
                if inside.startswith("!"):
                    inside = "^" + inside[1:]
                out.append(f"[{inside}]")
                i = end
        elif c == "\\" and i + 1 < len(text):
            i += 1
            out.append(re.escape(text[i]))
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out) + r"\Z")


@dataclass(frozen=True)
class Rule:
    base: str  # the .gitignore's folder, relative ("" at the top)
    regex: re.Pattern[str]
    anchored: bool  # a slash before its end: matched from its folder, not by a part's name
    folder_only: bool
    negated: bool


def rules_of(base: str, text: str) -> list[Rule]:
    found = []
    for line in text.splitlines():
        line = line.rstrip()
        if line.endswith("\\ "):
            line = line[:-2] + " "
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        negated = line.startswith("!")
        line = line[1:] if negated else line
        if line.startswith("\\"):
            line = line[1:]
        folder_only = line.endswith("/")
        line = line.rstrip("/")
        if not line:
            continue
        anchored = "/" in line
        line = line.lstrip("/")
        found.append(Rule(base.strip("/"), _pattern(line), anchored, folder_only, negated))
    return found


ALWAYS: list[Rule] = [
    *rules_of("", "/local/\n.git/\n**/.sab/data/\n*.theirs\n"),
]


class Ignore:
    """The folder's .gitignore files (each at its own folder) and the app's own exclusions, which win."""

    def __init__(self, gitignores: Iterable[tuple[str, str]] = ()) -> None:
        self.rules: list[Rule] = []
        for base, text in sorted(gitignores, key=lambda b: b[0].count("/") if b[0] else -1):
            self.rules += rules_of(base, text)

    @staticmethod
    def _hits(rule: Rule, path: str, is_folder: bool) -> bool:
        if rule.folder_only and not is_folder:
            return False
        if rule.base:
            if not path.startswith(rule.base + "/"):
                return False
            path = path[len(rule.base) + 1 :]
        if rule.anchored:
            return bool(rule.regex.match(path))
        return bool(rule.regex.match(path.rsplit("/", 1)[-1]))

    def _ignored_alone(self, path: str, is_folder: bool, rules: list[Rule]) -> bool:
        ignored = False
        for rule in rules:
            if self._hits(rule, path, is_folder):
                ignored = not rule.negated
        return ignored

    def ignored(self, path: str) -> bool:
        """A file's relative path (slashes) left out: itself or a folder above it ignored."""
        parts = path.split("/")
        for rules in (ALWAYS, self.rules):
            for i in range(1, len(parts) + 1):
                if self._ignored_alone("/".join(parts[:i]), i < len(parts), rules):
                    return True
        return False


# ===== a folder's link =====


@dataclass
class Link:
    repository: str  # owner/name
    branch: str
    commit: str | None = None  # the last synced commit (None: connected, not pulled yet)
    files: dict[str, str] = field(default_factory=dict)  # path -> the blob SHA last synced: the base
    conflicts: list[str] = field(default_factory=list)  # paths whose <name>.theirs waits
    staged: list[str] = field(default_factory=list)  # Stage Changes: the paths the next commit takes

    def to_json(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "branch": self.branch,
            "commit": self.commit,
            "files": dict(sorted(self.files.items())),
            "conflicts": sorted(self.conflicts),
            "staged": sorted(set(self.staged)),
        }

    @staticmethod
    def from_json(data: Any) -> Link | None:
        if not isinstance(data, dict) or not isinstance(data.get("repository"), str):
            return None
        files: dict[str, Any] = data["files"] if isinstance(data.get("files"), dict) else {}
        return Link(
            str(data["repository"]),
            str(data.get("branch") or "main"),
            data["commit"] if isinstance(data.get("commit"), str) else None,
            {str(k): str(v) for k, v in files.items()},
            [str(p) for p in data.get("conflicts") or [] if isinstance(p, str)],
            [str(p) for p in data.get("staged") or [] if isinstance(p, str)],
        )


def in_scope(path: str, scope: str | None) -> bool:
    return not scope or path == scope or path.startswith(scope.rstrip("/") + "/")


def changes(
    base: Mapping[str, str], local: Mapping[str, str], scope: str | None = None
) -> tuple[list[str], list[str]]:
    """The paths changed or added here since the base, and those deleted here."""
    changed = sorted(p for p, sha in local.items() if base.get(p) != sha and in_scope(p, scope))
    deleted = sorted(p for p in base if p not in local and in_scope(p, scope))
    return changed, deleted


# ===== pull =====


@dataclass(frozen=True)
class Step:
    path: str
    action: str  # take (theirs written), delete (gone here too), merge (both changed), kept (deleted there,
    # changed here: stays), restore (deleted here, changed there: theirs written back)
    theirs: str | None  # their blob SHA


def pull_plan(base: Mapping[str, str], local: Mapping[str, str], remote: Mapping[str, str]) -> list[Step]:
    """What a pull does to each path, from its base (the last sync), here and there."""
    steps = []
    for path in sorted({*base, *local, *remote}):
        b, here, there = base.get(path), local.get(path), remote.get(path)
        if there == b or here == there:
            continue  # nothing new there (a change here stays to push), or the same on both sides
        if here == b:
            steps.append(Step(path, "delete" if there is None else "take", there))
        elif there is None:
            steps.append(Step(path, "kept", None))
        elif here is None:
            steps.append(Step(path, "restore", there))
        else:
            steps.append(Step(path, "merge", there))
    return steps


def _hunks(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
    return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def _apply(base: list[str], start: int, end: int, hunks: list[tuple[int, int, list[str]]]) -> list[str]:
    out: list[str] = []
    at = start
    for i1, i2, lines in hunks:
        out += base[at:i1] + lines
        at = i2
    return out + base[at:end]


def merge3(base: bytes | None, ours: bytes, theirs: bytes) -> bytes | None:
    """A line-based three-way merge (diff3): each side's changes against the base applied together; None when
    both change the same lines (or lines that touch) differently, or the file is not text."""
    try:
        b = (base or b"").decode("utf-8").splitlines(keepends=True)
        o = ours.decode("utf-8").splitlines(keepends=True)
        t = theirs.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None
    if ours == theirs:
        return ours
    tagged = sorted(
        [(i1, i2, lines, 0) for i1, i2, lines in _hunks(b, o)]
        + [(i1, i2, lines, 1) for i1, i2, lines in _hunks(b, t)],
        key=lambda h: (h[0], h[1]),
    )
    out: list[str] = []
    at = 0
    k = 0
    while k < len(tagged):
        group = [tagged[k]]
        start, end = tagged[k][0], tagged[k][1]
        k += 1
        while (
            k < len(tagged)
            and tagged[k][0] <= end
            and (tagged[k][0] < end or tagged[k][3] != group[-1][3] or start == end)
        ):
            end = max(end, tagged[k][1])
            group.append(tagged[k])
            k += 1
        sides = {h[3] for h in group}
        mine = _apply(b, start, end, [(h[0], h[1], h[2]) for h in group if h[3] == 0])
        yours = _apply(b, start, end, [(h[0], h[1], h[2]) for h in group if h[3] == 1])
        if len(sides) == 2 and mine != yours:
            return None
        out += b[at:start] + (mine if 0 in sides else yours)
        at = end
    out += b[at:]
    return "".join(out).encode("utf-8")


def theirs_path(path: str) -> str:
    return path + THEIRS


# ===== push: what may never leave =====

_KEYED_LITERAL = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|account[_-]?key)"
    r"\w*\s*[=:]\s*[\"']([^\"'\s${}<>]{8,})[\"']"
)
_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("a storage account key", re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{20,}")),
    ("a shared access signature", re.compile(r"(?i)\bsig=[A-Za-z0-9%+/=]{20,}")),
    ("a bearer token", re.compile(r"(?i)\b(?:bearer)\s+[A-Za-z0-9+/=._\-]{20,}")),
)
_PLACEHOLDER = re.compile(r"(?i)^(?:x+|\*+|changeme|your[_-].*|example.*|made[_-]?up.*|placeholder.*)$")


def secret_in(text: str, known: Iterable[str] = ()) -> str | None:
    """Why a file's text looks like it holds a secret (None: it does not): a value kept in the keyring here,
    a token's shape, or a password written as a literal."""
    for value in known:
        if value and len(value) >= 6 and value in text:
            return "a value this computer keeps in its keyring"
    for words, shape in _SHAPES:
        if shape.search(text):
            return words
    for match in _KEYED_LITERAL.finditer(text):
        if not _PLACEHOLDER.match(match.group(2)):
            return f"a {match.group(1).lower()} written into it"
    return None


def message(raw: Any, count: int, scope_name: str | None = None) -> str:
    """The commit message: the user's, else "Update from Swiss Army Bench: 3 files" (a project's name for a
    shared card's push)."""
    text = str(raw or "").strip()
    if text:
        return text[:2000]
    files = f"{count} file{'' if count == 1 else 's'}"
    return (
        f"Update {scope_name} from Swiss Army Bench: {files}" if scope_name else f"{DEFAULT_MESSAGE}: {files}"
    )


# ===== words =====


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def status_words(
    connected: bool, conflicts: int, behind: int | None, to_push: int, never_pulled: bool = False
) -> tuple[str, str]:
    """(state, words): not_connected, conflicts, behind, changes, up_to_date (behind None: not asked)."""
    if not connected:
        return "not_connected", "Not connected"
    if conflicts:
        return "conflicts", f"Conflicts: {conflicts}"
    if never_pulled:
        return "behind", "Not pulled yet: Pull"
    if behind:
        return "behind", f"{behind} behind: Pull"
    if to_push:
        return "changes", f"{plural(to_push, 'change')} to push"
    return "up_to_date", "Up to date"


def pull_words(taken: int, merged: int, deleted: int, conflicts: int, kept: int) -> str:
    said = []
    if taken:
        said.append(f"{plural(taken, 'file')} updated")
    if merged:
        said.append(f"{merged} merged")
    if deleted:
        said.append(f"{deleted} deleted")
    if kept:
        said.append(f"{plural(kept, 'file')} deleted on GitHub kept here (changed here)")
    text = ", ".join(said)
    if conflicts:
        return (f"{text}. " if text else "") + f"{plural(conflicts, 'conflict')}: resolve and Push"
    return text or "Up to date"


def device_answer(answer: Mapping[str, Any]) -> tuple[str, Any]:
    """The device flow's poll answer: ("token", it), ("pending", seconds to wait), ("expired", None),
    ("denied", None), or ("error", its words)."""
    token = answer.get("access_token")
    if isinstance(token, str) and token:
        return "token", token
    error = str(answer.get("error") or "")
    if error == "authorization_pending":
        return "pending", int(answer.get("interval") or 5)
    if error == "slow_down":
        return "pending", int(answer.get("interval") or 10)
    if error == "expired_token":
        return "expired", None
    if error == "access_denied":
        return "denied", None
    return "error", str(answer.get("error_description") or error or "GitHub did not answer the sign-in.")[
        :300
    ]


TOKEN_STEPS: tuple[str, ...] = (
    "On GitHub: your picture, Settings, Developer settings, Personal access tokens, Fine-grained tokens, "
    "Generate new token.",
    "Name it (Swiss Army Bench), pick an expiry, and under Repository access choose Only select repositories: "
    "the meta store's and the shared projects'.",
    "Under Permissions, Repository permissions: Contents, Read and write (Metadata, Read-only, comes with it).",
    "Generate token, copy it, and paste it here once: it is kept in this computer's keyring only.",
)


# ===== the Source Control page's groups (VS Code's: Merge Changes, Staged Changes, Changes) =====

# VS Code's git decorations (Code - OSS, extensions/git/src/repository.ts, MIT licence, Copyright (c)
# Microsoft Corporation): each status's letter, its words and its theme colour's key.
STATUS: dict[str, tuple[str, str, str]] = {
    "index_modified": ("M", "Index Modified", "gitDecoration.stageModifiedResourceForeground"),
    "index_added": ("A", "Index Added", "gitDecoration.addedResourceForeground"),
    "index_deleted": ("D", "Index Deleted", "gitDecoration.stageDeletedResourceForeground"),
    "modified": ("M", "Modified", "gitDecoration.modifiedResourceForeground"),
    "deleted": ("D", "Deleted", "gitDecoration.deletedResourceForeground"),
    "untracked": ("U", "Untracked", "gitDecoration.untrackedResourceForeground"),
    "both_modified": ("!", "Conflict: Both Modified", "gitDecoration.conflictingResourceForeground"),
}


def resource(path: str, status: str) -> dict[str, Any]:
    letter, words, colour = STATUS[status]
    return {"path": path, "status": status, "letter": letter, "tooltip": words, "colour": colour}


def groups(
    base: Mapping[str, str],
    local: Mapping[str, str],
    staged: Iterable[str],
    conflicts: Iterable[str],
    scope: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """The page's three groups: merge (a pull's conflicts), index (staged), workingTree (the rest)."""
    changed, deleted = changes(base, local, scope)
    marked = set(staged)
    clashing = {p for p in conflicts if in_scope(p, scope)}
    merge = [resource(p, "both_modified") for p in sorted(clashing)]
    index: list[dict[str, Any]] = []
    working: list[dict[str, Any]] = []
    for path in sorted([*changed, *deleted]):
        if path in clashing:
            continue
        new = path not in base
        gone = path not in local
        if path in marked:
            index.append(
                resource(path, "index_deleted" if gone else "index_added" if new else "index_modified")
            )
        else:
            working.append(resource(path, "deleted" if gone else "untracked" if new else "modified"))
    return {"merge": merge, "index": index, "workingTree": working}


def unified(original: str, modified: str, path: str, old: str = "a", new: str = "b") -> str:
    """A file's change as unified diff text (the agent's read of what the diff editor shows)."""
    lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        f"{old}/{path}",
        f"{new}/{path}",
    )
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )


def is_text(data: bytes) -> bool:
    if b"\0" in data[:8000]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def check_branch_name(raw: Any) -> str:
    name = check_branch(raw)
    if name is None:
        raise SyncError("Name the branch.")
    return name


def check_paths(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        raise SyncError('Send "paths" as a list of the files\' paths in the folder.')
    found = [p.replace("\\", "/").strip("/") for p in raw]
    bad = [p for p in found if not safe_path(p)]
    if bad:
        raise SyncError(f"{bad[0]!r} is not a path inside the folder.")
    return found


def history_row(item: Mapping[str, Any]) -> dict[str, Any]:
    """A commit from GitHub's commits list as the graph's row."""
    commit = item.get("commit") or {}
    author = commit.get("author") or {}
    text = str(commit.get("message") or "")
    subject, _, body = text.partition("\n")
    return {
        "id": str(item.get("sha") or ""),
        "parents": [str(p.get("sha")) for p in item.get("parents") or [] if isinstance(p, dict)],
        "subject": subject,
        "message": text,
        "body": body.strip(),
        "author": str(author.get("name") or ""),
        "email": str(author.get("email") or ""),
        "date": str(author.get("date") or ""),
    }


# GitHub's file statuses on a commit, as VS Code's.
COMMIT_FILE: dict[str, str] = {
    "added": "index_added",
    "modified": "index_modified",
    "changed": "index_modified",
    "removed": "index_deleted",
    "renamed": "index_modified",
    "copied": "index_added",
}
