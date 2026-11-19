"""GitHub sync, the Git extension's (the owner, 2026-11-18: "connect a local GitHub repo and push and pull and fork
projects so you could work a shared project and clone it into a local project"; chosen: "Built-in, signed in to
GitHub"; rules in domain/sync.py; the Source Control page's use cases in services/scm.py). The meta store folder and the shared projects folder, each connected to a GitHub
repository, cloned, pulled and pushed through GitHub's web API: no Git on this computer. "Fork" is Make a local
copy (services/project_explorer.py).

  sign-in   Settings' GitHub: Sign in with GitHub (the device flow, when the app has its client id) or Use a
            token (a fine-grained personal access token pasted once). The token is the keyring's only: never
            in a file, an answer, a log or context.md. The user's own (403 for the agent), and Sign out
  status    each folder: Not connected, Up to date, 3 changes to push, 2 behind: Pull, Conflicts: 2. Here is
            compared with the base by git's blob SHAs; GitHub is asked (one GET of the head, a compare) only when
            the page asks for it (Settings, the Project Explorer), at most once a minute, or by Pull and Push:
            never a background poll. The footer's mark is the open project's (or the meta store's)
  clone     a repository into an empty or new folder, which becomes that folder (the agent's on Allow)
  connect   this folder to a repository: compared, nothing written (the agent's on Allow)
  pull      theirs where only they changed, a three-way merge where both did, a conflict as <name>.theirs
            (the agent's on Allow); the shared catalog reads a pulled meta store again
  push      the changed files as one commit on the head, fast-forward only: Pull first when GitHub moved,
            never forced; refused when a file looks like it holds a secret (the agent's on Allow)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace
from swissarmybench_git.domain import sync as rules

REMOTE_SECONDS: float = 60.0  # GitHub asked about a folder's head at most once a minute


class Client(Protocol):
    """adapters/github_sync.py GitHubClient."""

    def user(self) -> dict[str, Any]: ...

    def repositories(self) -> list[dict[str, Any]]: ...

    def default_branch(self, repository: str) -> str: ...

    def organisations(self) -> list[str]: ...

    def create_repository(self, owner: str | None, name: str, private: bool = True) -> dict[str, Any]: ...

    def head(self, repository: str, branch: str) -> str | None: ...

    def tree_of(self, repository: str, commit: str) -> str: ...

    def tree(self, repository: str, tree: str) -> dict[str, tuple[str, int, str]]: ...

    def blob(self, repository: str, sha: str) -> bytes: ...

    def behind(self, repository: str, base: str, head: str) -> int: ...

    def create_blob(self, repository: str, data: bytes) -> str: ...

    def create_tree(self, repository: str, base_tree: str, entries: list[dict[str, Any]]) -> str: ...

    def create_commit(self, repository: str, words: str, tree: str, parent: str) -> str: ...

    def move_ref(self, repository: str, branch: str, commit: str) -> None: ...

    def commits(
        self, repository: str, branch: str, page: int = 1, per_page: int = 100
    ) -> list[dict[str, Any]]: ...

    def commit(self, repository: str, sha: str) -> dict[str, Any]: ...

    def file_at(self, repository: str, commit: str, path: str) -> bytes | None: ...

    def branches(self, repository: str) -> list[dict[str, str]]: ...

    def create_branch(self, repository: str, branch: str, commit: str) -> None: ...

    def device_code(self, client_id: str) -> dict[str, Any]: ...

    def device_token(self, client_id: str, device_code: str) -> dict[str, Any]: ...


class Token(Protocol):
    def get(self) -> str | None: ...

    def set(self, token: str) -> None: ...

    def delete(self) -> None: ...


class Links(Protocol):
    def read(self) -> dict[str, Any]: ...

    def write(self, data: dict[str, Any]) -> None: ...


class Folder(Protocol):
    def full(self, folder: str) -> Path: ...

    def ignore(self, folder: str) -> rules.Ignore: ...

    def files(self, folder: str) -> tuple[dict[str, str], list[str]]: ...

    def read(self, folder: str, rel: str) -> bytes: ...

    def exists(self, folder: str, rel: str) -> bool: ...

    def write(self, folder: str, rel: str, data: bytes) -> None: ...

    def remove(self, folder: str, rel: str) -> None: ...

    def is_empty(self, folder: str) -> bool: ...

    def is_folder(self, folder: str) -> bool: ...


class Asker(Protocol):
    async def ask(self, dataset: str, action: str, detail: str) -> bool: ...


class GitHubSync:
    def __init__(
        self,
        ws: Workspace,
        client: Callable[[str | None], Client],
        token: Token,
        links: Links,
        folder: Folder,
        approvals: Asker,
        folders: Callable[[str], str | None],
        use_folder: Callable[[str, str], Awaitable[None]],
        client_id: str = "",
        pulled: Callable[[str], Awaitable[None]] | None = None,
        known_secrets: Callable[[], list[str]] = list,
        project: Callable[[], str | None] = lambda: None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ws = ws
        self._client = client
        self._token = token
        self._links = links
        self._files = folder
        self._approvals = approvals
        self._folders = folders  # which -> the folder Settings names (None: none set)
        self._use_folder = use_folder  # a clone made that folder: Settings points at it
        self._client_id = client_id.strip()
        self._pulled = pulled
        self._known = known_secrets
        self._project = project  # the open project's folder
        self._now = now
        self._lock = asyncio.Lock()
        self._remote: dict[
            str, tuple[float, str | None, int | None, str]
        ] = {}  # folder -> when, head, behind, error
        self._device: dict[str, Any] | None = None

    # ===== who is signed in =====

    def _signed_in(self) -> str:
        token = self._token.get()
        if not token:
            raise Refused("Sign in to GitHub first: Settings, Team.")
        return token

    def _account(self) -> str | None:
        found = self._links.read().get("account")
        return str(found) if found else None

    def _set_account(self, login: str | None) -> None:
        data = self._links.read()
        data["account"] = login
        self._links.write(data)

    async def _changed(self) -> None:
        await self.ws.live.broadcast({"type": "sync_changed"})

    @staticmethod
    def _user_only(who: str, doing: str) -> None:
        if who == "agent":
            raise Refused(f"{doing} is the user's own: in Settings, Team.")

    async def sign_in_token(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Use a token: {"token"}: checked with GitHub (who it signs in), then kept in the keyring only."""
        self._user_only(who, "Signing in to GitHub")
        token = str(body.get("token") or "").strip() if isinstance(body, dict) else ""
        if not token or len(token) > 400 or any(c.isspace() for c in token):
            raise rules.SyncError("Paste the token GitHub made (one line).")
        login = await self._login(token)
        self._token.set(token)
        self._set_account(login)
        self._remote.clear()
        self.ws.audit.write(who, "github_sign_in", None, how="token")
        await self._changed()
        return {"signed_in": True, "account": login}

    async def _login(self, token: str) -> str:
        try:
            found = await asyncio.to_thread(lambda: self._client(token).user())
        except Exception as error:
            if getattr(error, "status", None) == 401:
                raise rules.SyncError(
                    "GitHub refused that token: make a new one and paste it again."
                ) from None
            raise rules.SyncError(str(error)) from None
        login = str(found.get("login") or "")
        if not login:
            raise rules.SyncError("GitHub did not say who the token signs in.")
        return login

    async def device_start(self, who: str = "user") -> dict[str, Any]:
        """Sign in with GitHub: the device flow's code to type at github.com/login/device."""
        self._user_only(who, "Signing in to GitHub")
        if not self._client_id:
            raise rules.SyncError(
                "Sign in with GitHub needs the app's registration with GitHub, which this build does not have "
                "yet: use a token instead."
            )
        try:
            found = await asyncio.to_thread(lambda: self._client(None).device_code(self._client_id))
        except Exception as error:
            raise rules.SyncError(str(error)) from None
        self._device = {
            "code": str(found["device_code"]),
            "until": self._now() + float(found.get("expires_in") or 900),
        }
        return {
            "user_code": str(found.get("user_code") or ""),
            "verification_uri": str(found.get("verification_uri") or "https://github.com/login/device"),
            "interval": int(found.get("interval") or 5),
            "expires_in": int(found.get("expires_in") or 900),
        }

    async def device_poll(self, who: str = "user") -> dict[str, Any]:
        """Has the user typed the code? {"state": "pending" (and the seconds to wait), "signed_in",
        "expired", "denied"}."""
        self._user_only(who, "Signing in to GitHub")
        held = self._device
        if held is None:
            raise rules.SyncError("Start Sign in with GitHub first.")
        if self._now() > float(held["until"]):
            self._device = None
            return {"state": "expired", "words": "The code ran out: start again."}
        try:
            found = await asyncio.to_thread(
                lambda: self._client(None).device_token(self._client_id, held["code"])
            )
        except Exception as error:
            raise rules.SyncError(str(error)) from None
        state, value = rules.device_answer(found)
        if state == "pending":
            return {"state": "pending", "interval": value}
        self._device = None
        if state == "token":
            login = await self._login(str(value))
            self._token.set(str(value))
            self._set_account(login)
            self._remote.clear()
            self.ws.audit.write(who, "github_sign_in", None, how="device")
            await self._changed()
            return {"state": "signed_in", "account": login}
        words = {
            "expired": "The code ran out: start again.",
            "denied": "The sign-in was cancelled on GitHub.",
        }.get(state, str(value))
        return {"state": state if state in ("expired", "denied") else "error", "words": words}

    async def sign_out(self, who: str = "user") -> dict[str, Any]:
        self._user_only(who, "Signing out of GitHub")
        self._token.delete()
        self._set_account(None)
        self._device = None
        self._remote.clear()
        self.ws.audit.write(who, "github_sign_out", None)
        await self._changed()
        return {"signed_in": False}

    async def repositories(self, who: str = "user") -> dict[str, Any]:
        """The signed-in user's repositories (Clone a repository's list)."""
        token = self._signed_in()
        try:
            found = await asyncio.to_thread(lambda: self._client(token).repositories())
        except Exception as error:
            raise rules.SyncError(str(error)) from None
        return {"repositories": found, "account": self._account()}

    # ===== the links =====

    def _link(self, folder: str) -> rules.Link | None:
        return rules.Link.from_json(self._links.read()["folders"].get(folder))

    def _save(self, folder: str, link: rules.Link | None) -> None:
        data = self._links.read()
        if link is None:
            data["folders"].pop(folder, None)
        else:
            data["folders"][folder] = link.to_json()
        self._links.write(data)

    def _folder_of(self, which: str) -> str:
        raw = self._folders(which)
        if not raw:
            raise rules.SyncError(f"Set {rules.WHICH_WORDS[which]} in Settings first.")
        return str(self._files.full(raw))

    def _scope(self, folder: str, body: Any) -> tuple[str | None, str | None]:
        """A shared card's project: its subfolder, relative (and its name)."""
        raw = body.get("path") if isinstance(body, dict) else None
        if not raw:
            return None, None
        try:
            rel = self._files.full(str(raw)).relative_to(Path(folder)).as_posix()
        except ValueError:
            raise rules.SyncError(f"{raw} is not inside {folder}.") from None
        if rel in ("", "."):
            return None, None
        return rel, rel.rsplit("/", 1)[-1]

    def _open_conflicts(self, folder: str, link: rules.Link) -> list[str]:
        return [p for p in link.conflicts if self._files.exists(folder, rules.theirs_path(p))]

    async def _allow(self, who: str, which: str, action: str, detail: str) -> None:
        if who == "agent" and not await self._approvals.ask("GitHub", action, detail):
            raise Refused(
                f"The user declined (or did not answer): {rules.WHICH_WORDS[which]} was not changed."
            )

    # ===== status =====

    def _remote_of(
        self, token: str | None, folder: str, link: rules.Link, ask: bool
    ) -> tuple[str | None, int | None, str]:
        """(head, behind, error) of GitHub's side: asked at most once a minute, else the last answer."""
        held = self._remote.get(folder)
        fresh = held is not None and self._now() - held[0] < REMOTE_SECONDS
        if token and ask and not fresh:
            try:
                client = self._client(token)
                head = client.head(link.repository, link.branch)
                behind: int | None = 0
                if head and link.commit and head != link.commit:
                    behind = client.behind(link.repository, link.commit, head)
                elif head and not link.commit:
                    behind = None
                self._remote[folder] = (self._now(), head, behind, "")
            except Exception as error:
                self._remote[folder] = (self._now(), link.commit, 0, str(error)[:300])
            held = self._remote[folder]
        if held is None:
            return link.commit, 0, ""
        return held[1], held[2], held[3]

    def _folder_status(self, which: str, token: str | None, ask: bool) -> dict[str, Any]:
        raw = self._folders(which)
        out: dict[str, Any] = {"which": which, "folder": None, "connected": False}
        if not raw:
            state, words = rules.status_words(False, 0, 0, 0)
            return out | {"state": state, "words": words, "set": False}
        out |= {"folder": str(self._files.full(raw)), "set": True}
        held = self._covering(which)
        if held is None:
            state, words = rules.status_words(False, 0, 0, 0)
            return out | {"state": state, "words": words}
        folder, link, inside = held
        local, large = self._files.files(folder) if self._files.is_folder(folder) else ({}, [])
        changed, deleted = rules.changes(link.files, local, inside)
        conflicts = self._open_conflicts(folder, link)
        if conflicts != link.conflicts:
            link.conflicts = conflicts
            self._save(folder, link)
        conflicts = [p for p in conflicts if rules.in_scope(p, inside)]
        _head, behind, error = self._remote_of(token, folder, link, ask)
        never = link.commit is None
        state, words = rules.status_words(
            True, len(conflicts), behind or 0, len(changed) + len(deleted), never
        )
        projects: dict[str, dict[str, int]] = {}
        if which == "shared":
            cut = len(inside) + 1 if inside else 0
            for path in [*changed, *deleted]:
                if "/" in path[cut:]:
                    projects.setdefault(path[cut:].split("/")[0], {"to_push": 0, "conflicts": 0})[
                        "to_push"
                    ] += 1
            for path in conflicts:
                if "/" in path[cut:]:
                    projects.setdefault(path[cut:].split("/")[0], {"to_push": 0, "conflicts": 0})[
                        "conflicts"
                    ] += 1
        return out | {
            "connected": True,
            "within": inside,
            "repository": link.repository,
            "branch": link.branch,
            "state": state,
            "words": words,
            "to_push": len(changed) + len(deleted),
            "changed": changed[:50],
            "deleted": deleted[:50],
            "behind": behind,
            "pulled": not never,
            "conflicts": conflicts,
            "large": large,
            "error": error,
            "projects": projects,
        }

    def _footer(self, folders: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The footer's mark: the open project's sync (a shared project's own changes and the folder's
        behind), else the meta store's; None when up to date, not connected or no project open."""
        project = self._project()
        if not project:
            return None
        by = {f["which"]: f for f in folders}
        shared = by.get("shared") or {}
        try:
            rel = (
                Path(str(self._files.full(project))).relative_to(Path(shared["folder"])).as_posix()
                if shared.get("connected")
                else None
            )
        except ValueError:
            rel = None
        if rel and rel != ".":
            name = rel.split("/")[0]
            own = (shared.get("projects") or {}).get(name, {"to_push": 0, "conflicts": 0})
            mark = _mark(
                own["conflicts"], shared.get("behind") or 0, own["to_push"], not shared.get("pulled")
            )
            if mark:
                return mark | {"which": "shared", "path": str(Path(shared["folder"]) / name), "name": name}
        library = by.get("library") or {}
        if library.get("connected"):
            mark = _mark(
                len(library.get("conflicts") or []),
                library.get("behind") or 0,
                library.get("to_push") or 0,
                not library.get("pulled"),
            )
            if mark:
                return mark | {"which": "library", "name": "the team library"}
        return None

    async def status(self, remote: bool = False, who: str = "user") -> dict[str, Any]:
        """Signed in or not (the login, never the token), each folder's link and words; remote: GitHub asked
        about each head (at most once a minute)."""
        token = self._token.get()
        folders = await asyncio.to_thread(
            lambda: [self._folder_status(w, token, remote) for w in rules.WHICH]
        )
        return {
            "signed_in": bool(token),
            "account": self._account() if token else None,
            "device": bool(self._client_id),
            "token_steps": list(rules.TOKEN_STEPS),
            "folders": folders,
            "footer": self._footer(folders),
        }

    # ===== clone and connect =====

    async def clone(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "repository", "branch"?, "folder"?: an empty or new folder (default: the one Settings
        names, when empty)}: every file written there, the folder then the meta store's (or the shared
        projects') in Settings."""
        if not isinstance(body, dict):
            raise rules.SyncError('Send {"which", "repository", "folder"?}.')
        which = rules.check_which(body.get("which"))
        repository = rules.check_repository(body.get("repository"))
        branch = rules.check_branch(body.get("branch"))
        raw = body.get("folder") or self._folders(which)
        if not raw:
            raise rules.SyncError("Name the folder to clone into.")
        folder = str(self._files.full(str(raw)))
        if not self._files.is_empty(folder):
            raise Conflict(
                f"{folder} is not empty: pick an empty or new folder, or Connect this folder instead."
            )
        token = self._signed_in()
        await self._allow(
            who,
            which,
            f"clone {repository}",
            f"Clone {repository} into {folder} and use it as {rules.WHICH_WORDS[which]}.",
        )
        async with self._lock:
            done = await asyncio.to_thread(self._clone, token, folder, repository, branch)
        if self._folders(which) is None or str(self._files.full(str(self._folders(which)))) != folder:
            await self._use_folder(which, folder)
        if self._pulled is not None:
            await self._pulled(which)
        self.ws.audit.write(who, "github_clone", None, which=which, files=done["files"])
        await self._changed()
        return done | {"which": which}

    def _clone(self, token: str, folder: str, repository: str, branch: str | None) -> dict[str, Any]:
        client = self._client(token)
        branch = branch or _sync(lambda: client.default_branch(repository))
        head = _sync(lambda: client.head(repository, branch))
        Path(folder).mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        large: list[str] = []
        if head is not None:
            tree = _sync(lambda: client.tree(repository, client.tree_of(repository, head)))
            for path, (sha, size, _mode) in sorted(tree.items()):
                if not rules.safe_path(path) or rules.Ignore().ignored(path):
                    continue
                if size > rules.MAX_FILE_BYTES:
                    large.append(path)
                    continue
                self._files.write(folder, path, _sync(lambda s=sha: client.blob(repository, s)))  # type: ignore[misc]
                files[path] = sha
            ignore = self._files.ignore(folder)
            files = {p: s for p, s in files.items() if not ignore.ignored(p)}
        self._save(folder, rules.Link(repository, branch, head, files, []))
        self._remote[folder] = (self._now(), head, 0, "")
        return {
            "folder": folder,
            "repository": repository,
            "branch": branch,
            "files": len(files),
            "large": large,
        }

    async def connect(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "repository", "branch"?}: this folder linked to the repository. Its files are compared
        with the repository's; nothing is written (Pull brings theirs, a file different on both sides comes
        as a conflict to resolve)."""
        if not isinstance(body, dict):
            raise rules.SyncError('Send {"which", "repository"}.')
        which = rules.check_which(body.get("which"))
        repository = rules.check_repository(body.get("repository"))
        branch = rules.check_branch(body.get("branch"))
        folder = self._folder_of(which)
        if not self._files.is_folder(folder):
            raise NotFound(f"{folder} is not there.")
        token = self._signed_in()
        await self._allow(
            who, which, f"connect to {repository}", f"Connect {folder} to {repository} (nothing written)."
        )
        async with self._lock:
            done = await asyncio.to_thread(self._connect, token, folder, repository, branch)
        self.ws.audit.write(who, "github_connect", None, which=which)
        await self._changed()
        return done | {"which": which}

    def _connect(self, token: str, folder: str, repository: str, branch: str | None) -> dict[str, Any]:
        client = self._client(token)
        branch = branch or _sync(lambda: client.default_branch(repository))
        head = _sync(lambda: client.head(repository, branch))
        ignore = self._files.ignore(folder)
        remote: dict[str, str] = {}
        if head is not None:
            tree = _sync(lambda: client.tree(repository, client.tree_of(repository, head)))
            remote = {
                p: s for p, (s, _size, _m) in tree.items() if rules.safe_path(p) and not ignore.ignored(p)
            }
        local, _large = self._files.files(folder)
        same = {p: s for p, s in local.items() if remote.get(p) == s}
        only_here = sorted(p for p in local if p not in remote)
        only_there = sorted(p for p in remote if p not in local)
        different = sorted(p for p in local if p in remote and remote[p] != local[p])
        commit = head if not only_there and not different else None
        self._save(folder, rules.Link(repository, branch, commit, same, []))
        self._remote.pop(folder, None)
        said = [f"{len(same)} the same"]
        if only_here:
            said.append(f"{len(only_here)} only here (Push sends them)")
        if only_there:
            said.append(f"{len(only_there)} only on GitHub (Pull brings them)")
        if different:
            said.append(f"{len(different)} different in both (Pull shows each as a conflict)")
        return {
            "folder": folder,
            "repository": repository,
            "branch": branch,
            "same": len(same),
            "only_here": only_here[:50],
            "only_there": only_there[:50],
            "different": different[:50],
            "words": f"Connected to {repository}: " + ", ".join(said),
        }

    async def disconnect(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which"}: the folder's link forgotten (no file touched, here or on GitHub)."""
        which = rules.check_which(body.get("which") if isinstance(body, dict) else None)
        folder = self._folder_of(which)
        self._save(folder, None)
        self._remote.pop(folder, None)
        self.ws.audit.write(who, "github_disconnect", None, which=which)
        await self._changed()
        return {"which": which, "folder": folder, "connected": False}

    def _covering(self, which: str) -> tuple[str, rules.Link, str | None] | None:
        """The link that holds which's folder: its own (inside None), or, for a team's one repository (the
        shared projects folder is the team library's projects/), the folder above's link and the subfolder."""
        raw = self._folders(which)
        if not raw:
            return None
        folder = str(self._files.full(raw))
        link = self._link(folder)
        if link is not None:
            return folder, link, None
        for other in rules.WHICH:
            above = self._folders(other) if other != which else None
            if not above:
                continue
            top = str(self._files.full(above))
            try:
                rel = Path(folder).relative_to(Path(top)).as_posix()
            except ValueError:
                continue
            found = self._link(top) if rel not in ("", ".") else None
            if found is not None:
                return top, found, rel
        return None

    def _inside(self, folder: str) -> list[str]:
        """Every folder (which) the link of this folder holds: itself, and a shared projects folder inside."""
        return [w for w in rules.WHICH if (held := self._covering(w)) is not None and held[0] == folder]

    def _connected(self, which: str) -> tuple[str, rules.Link]:
        held = self._covering(which)
        if held is None:
            self._folder_of(which)  # not set: says so
            raise rules.SyncError(
                f"Connect {rules.WHICH_WORDS[which]} to a GitHub repository first: Settings, Team."
            )
        return held[0], held[1]

    # ===== pull =====

    async def pull(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "path"?: a shared card's project (the whole folder is pulled)}."""
        which = rules.check_which(body.get("which") if isinstance(body, dict) else None)
        folder, link = self._connected(which)
        token = self._signed_in()
        await self._allow(
            who, which, "pull from GitHub", f"Pull {link.repository} into {folder}: files here change."
        )
        async with self._lock:
            done = await asyncio.to_thread(self._pull, token, folder, link)
        if done["written"] and self._pulled is not None:
            for each in self._inside(folder) or [which]:
                await self._pulled(each)
        self.ws.audit.write(
            who, "github_pull", None, which=which, files=done["written"], conflicts=len(done["conflicts"])
        )
        await self._changed()
        return done | {"which": which}

    def _pull(self, token: str, folder: str, link: rules.Link) -> dict[str, Any]:
        client = self._client(token)
        repo = link.repository
        head = _sync(lambda: client.head(repo, link.branch))
        taken: list[str] = []
        merged: list[str] = []
        deleted: list[str] = []
        kept: list[str] = []
        conflicts = self._open_conflicts(folder, link)
        large: list[str] = []
        if head is not None and head != link.commit:
            ignore = self._files.ignore(folder)
            tree = _sync(lambda: client.tree(repo, client.tree_of(repo, head)))
            remote = {}
            for path, (sha, size, _mode) in tree.items():
                if not rules.safe_path(path) or ignore.ignored(path):
                    continue
                if size > rules.MAX_FILE_BYTES:
                    large.append(path)
                    continue
                remote[path] = sha
            local, _large = self._files.files(folder)
            base = dict(link.files)
            for step in rules.pull_plan(base, local, remote):
                path = step.path
                if step.action in ("take", "restore"):
                    self._files.write(folder, path, _sync(lambda s=step.theirs: client.blob(repo, s)))  # type: ignore[misc]
                    base[path] = str(step.theirs)
                    taken.append(path)
                elif step.action == "delete":
                    self._files.remove(folder, path)
                    base.pop(path, None)
                    deleted.append(path)
                elif step.action == "kept":
                    base.pop(path, None)
                    kept.append(path)
                else:
                    theirs = _sync(lambda s=step.theirs: client.blob(repo, s))  # type: ignore[misc]
                    was = link.files.get(path)
                    original = _sync(lambda s=was: client.blob(repo, s)) if was else None  # type: ignore[misc]
                    together = rules.merge3(original, self._files.read(folder, path), theirs)
                    if together is None:
                        self._files.write(folder, rules.theirs_path(path), theirs)
                        if path not in conflicts:
                            conflicts.append(path)
                    else:
                        self._files.write(folder, path, together)
                        merged.append(path)
                    base[path] = str(step.theirs)
            link.files = base
            link.commit = head
        link.conflicts = sorted(conflicts)
        self._save(folder, link)
        self._remote[folder] = (self._now(), head, 0, "")
        return {
            "commit": head,
            "updated": taken,
            "merged": merged,
            "deleted": deleted,
            "kept": kept,
            "conflicts": link.conflicts,
            "large": large,
            "written": len(taken) + len(merged) + len(deleted),
            "words": rules.pull_words(len(taken), len(merged), len(deleted), len(link.conflicts), len(kept)),
        }

    # ===== push =====

    async def push(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "message"?, "path"?: a shared card's project: only its files}: one commit on GitHub's
        head, fast-forward only."""
        which = rules.check_which(body.get("which") if isinstance(body, dict) else None)
        folder, link = self._connected(which)
        scope, scope_name = self._scope(folder, body)
        held = self._covering(which)
        if scope is None and held is not None and held[2]:
            scope = held[2]
        only = (
            set(rules.check_paths(body.get("paths")))
            if isinstance(body, dict) and body.get("paths")
            else None
        )
        token = self._signed_in()
        local, large = await asyncio.to_thread(self._files.files, folder)
        changed, deleted = _chosen(link, local, scope, only)
        count = len(changed) + len(deleted)
        words = rules.message(body.get("message") if isinstance(body, dict) else None, count, scope_name)
        if count:
            await self._allow(
                who,
                which,
                "push to GitHub",
                f"Push {rules.plural(count, 'file')} to {link.repository}: {words}",
            )
        async with self._lock:
            done = await asyncio.to_thread(self._push, token, folder, link, scope, only, words)
        if done["pushed"]:
            self.ws.audit.write(who, "github_push", None, which=which, files=done["pushed"])
            await self._changed()
        return done | {"which": which, "large": large}

    def _push(
        self, token: str, folder: str, link: rules.Link, scope: str | None, only: set[str] | None, words: str
    ) -> dict[str, Any]:
        local, _large = self._files.files(folder)
        conflicts = [
            p
            for p in self._open_conflicts(folder, link)
            if rules.in_scope(p, scope) and (only is None or p in only)
        ]
        if conflicts:
            raise Conflict(
                f"{rules.plural(len(conflicts), 'conflict')} to resolve first: keep what you want in each file, "
                f"delete its {rules.THEIRS} beside it, then Push ({', '.join(conflicts[:5])})."
            )
        changed, deleted = _chosen(link, local, scope, only)
        if not changed and not deleted:
            return {"pushed": 0, "commit": link.commit, "words": "Nothing to push"}
        known = [v for v in self._known() if v]
        token_now = self._token.get()
        if token_now:
            known.append(token_now)
        datas: dict[str, bytes] = {}
        for path in changed:
            data = self._files.read(folder, path)
            why = rules.secret_in(data.decode("utf-8", errors="ignore"), known)
            if why:
                raise rules.SyncError(
                    f"Not pushed: {path} looks like it holds {why}. Take it out (a connection names where its "
                    "password comes from) and Push again."
                )
            datas[path] = data
        client = self._client(token)
        repo = link.repository
        head = _sync(lambda: client.head(repo, link.branch))
        if head is None:
            raise rules.SyncError(f"{repo} has no commit yet: add a README on GitHub first, then Pull.")
        if head != link.commit:
            raise Conflict("GitHub has changes this folder does not: Pull first, then Push.")
        modes = {
            p: m for p, (_s, _z, m) in _sync(lambda: client.tree(repo, client.tree_of(repo, head))).items()
        }
        entries: list[dict[str, Any]] = []
        for path, data in datas.items():
            sha = _sync(lambda d=data: client.create_blob(repo, d))  # type: ignore[misc]
            entries.append({"path": path, "mode": modes.get(path, "100644"), "type": "blob", "sha": sha})
        for path in deleted:
            entries.append({"path": path, "mode": modes.get(path, "100644"), "type": "blob", "sha": None})
        tree = _sync(lambda: client.create_tree(repo, client.tree_of(repo, head), entries))
        commit = _sync(lambda: client.create_commit(repo, words, tree, head))
        try:
            client.move_ref(repo, link.branch, commit)
        except Exception as error:
            if getattr(error, "status", None) == 422:
                raise Conflict("GitHub has changes this folder does not: Pull first, then Push.") from None
            raise rules.SyncError(str(error)) from None
        for path in changed:
            link.files[path] = local[path]
        for path in deleted:
            link.files.pop(path, None)
        link.staged = [p for p in link.staged if p not in {*changed, *deleted}]
        link.commit = commit
        self._save(folder, link)
        self._remote[folder] = (self._now(), commit, 0, "")
        return {
            "pushed": len(changed) + len(deleted),
            "commit": commit,
            "message": words,
            "words": f"{rules.plural(len(changed) + len(deleted), 'file')} pushed to {repo}",
        }


def _chosen(
    link: rules.Link, local: dict[str, str], scope: str | None, only: set[str] | None
) -> tuple[list[str], list[str]]:
    """The changed and deleted files a push takes: in the scope, and only the named ones when named."""
    changed, deleted = rules.changes(link.files, local, scope)
    if only is not None:
        changed = [p for p in changed if p in only]
        deleted = [p for p in deleted if p in only]
    return changed, deleted


def _sync(run: Callable[[], Any]) -> Any:
    """A GitHub call: its plain words as a SyncError (409 stays a Conflict, 404 a NotFound)."""
    try:
        return run()
    except (Conflict, NotFound, Refused, rules.SyncError):
        raise
    except Exception as error:
        status = getattr(error, "status", None)
        if status == 404:
            raise NotFound(str(error)) from None
        if status in (409, 422):
            raise Conflict(str(error)) from None
        if status == 401:
            raise Refused(str(error)) from None
        raise rules.SyncError(str(error)) from None


def _mark(conflicts: int, behind: int, to_push: int, never: bool) -> dict[str, Any] | None:
    """The footer's short words: Conflicts: 2, ↓2 behind, ↑3 to push (None: up to date)."""
    if conflicts:
        return {"state": "conflicts", "words": f"Conflicts: {conflicts}"}
    if never:
        return {"state": "behind", "words": "↓ Pull"}
    if behind:
        return {"state": "behind", "words": f"↓{behind} behind" + (f" · ↑{to_push}" if to_push else "")}
    if to_push:
        return {"state": "changes", "words": f"↑{to_push} to push"}
    return None
