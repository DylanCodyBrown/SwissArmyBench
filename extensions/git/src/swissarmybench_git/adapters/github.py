"""GitHub sync at the edge (services/github_sync.py): GitHub's web API by urllib, the token in the keyring, the
folders' links in the state folder's sync.json, and a synced folder's files.

  GitHubClient  REST v3 (api.github.com; a stand-in on 127.0.0.1 in tests): the user, their repositories, a
                repository's default branch, refs, commits, trees (recursive), blobs, compare, and the Git Data
                API's writes (blobs, a tree on a base tree, a commit, the ref moved fast-forward only); the
                device flow at github.com/login. The token goes only in the Authorization header: never in an
                error, a log or an answer
  GitHubToken   the keyring's SwissArmyBench / github/token
  SyncLinks     sync.json: {"account": the signed-in login, "folders": {folder path: its link}}
  SyncFolder    a folder's files (walked with its .gitignore files), read, written atomically, removed
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from swissarmybench_git.domain import sync as rules

TIMEOUT_SECONDS: float = 30.0
MAX_ANSWER_BYTES: int = 80 * 1024 * 1024  # a 50 MB blob, base64


class GitHubError(Exception):
    """GitHub's answer, in plain words (never the token, never a header)."""

    def __init__(self, status: int, words: str) -> None:
        super().__init__(words)
        self.status = status


def _allowed(url: str) -> bool:
    return url.startswith(("https://", "http://127.0.0.1:", "http://localhost:"))


class GitHubClient:
    def __init__(self, api: str, web: str, token: str | None) -> None:
        if not _allowed(api) or not _allowed(web):
            raise ValueError("GitHub is reached over https (or on this computer, in tests).")
        self.api = api.rstrip("/")
        self.web = web.rstrip("/")
        self._token = token

    def _send(self, method: str, url: str, body: Any = None, form: bool = False, auth: bool = True) -> Any:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        data = None
        if form:
            headers["Accept"] = "application/json"
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
        try:
            # A fixed GitHub address (or the tests' stand-in on 127.0.0.1): checked in __init__.
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310
                raw = answer.read(MAX_ANSWER_BYTES + 1)
        except urllib.error.HTTPError as error:
            try:
                found = json.loads(error.read(65536) or b"{}")
            except (ValueError, AttributeError):
                found = {}
            found = found if isinstance(found, dict) else {}
            # The API says why in "message"; github.com/login's sign-in addresses in "error" and
            # "error_description" (device_flow_disabled, incorrect_client_credentials): both read.
            code = str(found.get("error") or "")
            if code in SIGN_IN_WORDS:
                raise GitHubError(error.code, SIGN_IN_WORDS[code]) from None
            said = found.get("message") or found.get("error_description") or code
            raise GitHubError(error.code, _words(error.code, str(said))) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise GitHubError(0, f"GitHub could not be reached: {str(reason)[:200]}") from None
        if len(raw) > MAX_ANSWER_BYTES:
            raise GitHubError(0, "GitHub's answer is too large.")
        return json.loads(raw) if raw else {}

    def _get(self, path: str) -> Any:
        return self._send("GET", self.api + path)

    # ===== who, which repositories =====

    def user(self) -> dict[str, Any]:
        found = self._get("/user")
        return {"login": str(found.get("login") or ""), "name": found.get("name")}

    def repositories(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for page in range(1, 6):  # 500 at most
            found = self._get(f"/user/repos?per_page=100&sort=updated&page={page}")
            if not isinstance(found, list):
                break
            out += [
                {
                    "repository": str(r.get("full_name")),
                    "branch": str(r.get("default_branch") or "main"),
                    "private": bool(r.get("private")),
                    "can_push": bool((r.get("permissions") or {}).get("push", True)),
                    "pushed": str(r.get("pushed_at") or r.get("updated_at") or ""),
                }
                for r in found
                if isinstance(r, dict) and r.get("full_name")
            ]
            if len(found) < 100:
                break
        return out

    def organisations(self) -> list[str]:
        """The organisations the signed-in account belongs to (a new team repository's possible owners)."""
        found = self._get("/user/orgs?per_page=100")
        return (
            [str(o["login"]) for o in found if isinstance(o, dict) and o.get("login")]
            if isinstance(found, list)
            else []
        )

    def create_repository(self, owner: str | None, name: str, private: bool = True) -> dict[str, Any]:
        """A new repository with a first commit (GitHub's README), so a push has a head to build on: the
        account's own (owner None) or an organisation's."""
        body = {"name": name, "private": private, "auto_init": True}
        path = f"/orgs/{urllib.parse.quote(owner, safe='')}/repos" if owner else "/user/repos"
        found = self._send("POST", self.api + path, body)
        return {
            "repository": str(found.get("full_name") or ""),
            "branch": str(found.get("default_branch") or "main"),
        }

    def default_branch(self, repository: str) -> str:
        return str(self._get(f"/repos/{repository}").get("default_branch") or "main")

    # ===== reading =====

    def head(self, repository: str, branch: str) -> str | None:
        """The branch's head commit; None for a repository with no commit yet."""
        try:
            found = self._get(f"/repos/{repository}/git/ref/heads/{urllib.parse.quote(branch, safe='/')}")
        except GitHubError as error:
            if error.status in (404, 409):
                try:
                    self._get(f"/repos/{repository}")
                except GitHubError:
                    raise error from None
                if error.status == 409:
                    return None
                raise GitHubError(404, f"{repository} has no branch {branch}.") from None
            raise
        return str(found["object"]["sha"])

    def tree_of(self, repository: str, commit: str) -> str:
        return str(self._get(f"/repos/{repository}/git/commits/{commit}")["tree"]["sha"])

    def tree(self, repository: str, tree: str) -> dict[str, tuple[str, int, str]]:
        """path -> (blob SHA, size, mode) of every file in the tree."""
        found = self._get(f"/repos/{repository}/git/trees/{tree}?recursive=1")
        if found.get("truncated"):
            raise GitHubError(0, f"{repository} has too many files for one read.")
        return {
            str(e["path"]): (str(e["sha"]), int(e.get("size") or 0), str(e.get("mode") or "100644"))
            for e in found.get("tree") or []
            if e.get("type") == "blob"
        }

    def blob(self, repository: str, sha: str) -> bytes:
        found = self._get(f"/repos/{repository}/git/blobs/{sha}")
        content = str(found.get("content") or "")
        if found.get("encoding") == "base64":
            return base64.b64decode(content)
        return content.encode("utf-8")

    def behind(self, repository: str, base: str, head: str) -> int:
        """How many commits the head is ahead of the last synced commit."""
        found = self._get(f"/repos/{repository}/compare/{base}...{head}")
        return int(found.get("ahead_by") or found.get("total_commits") or 0)

    def commits(
        self, repository: str, branch: str, page: int = 1, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """The branch's history, newest first (GitHub's commits list: 100 a page)."""
        ref = urllib.parse.quote(branch, safe="")
        found = self._get(f"/repos/{repository}/commits?sha={ref}&per_page={per_page}&page={page}")
        return [dict(c) for c in found] if isinstance(found, list) else []

    def commit(self, repository: str, sha: str) -> dict[str, Any]:
        """One commit with its files (each one's filename, status, previous_filename)."""
        return dict(self._get(f"/repos/{repository}/commits/{sha}"))

    def file_at(self, repository: str, commit: str, path: str) -> bytes | None:
        """A file as it stood at a commit (None: not there)."""
        tree = self.tree(repository, self.tree_of(repository, commit))
        found = tree.get(path)
        return None if found is None else self.blob(repository, found[0])

    def branches(self, repository: str) -> list[dict[str, str]]:
        found = self._get(f"/repos/{repository}/branches?per_page=100")
        return [
            {"name": str(b.get("name")), "commit": str((b.get("commit") or {}).get("sha") or "")}
            for b in found
            if isinstance(b, dict) and b.get("name")
        ]

    def create_branch(self, repository: str, branch: str, commit: str) -> None:
        self._send(
            "POST", f"{self.api}/repos/{repository}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit}
        )

    # ===== writing (the Git Data API) =====

    def create_blob(self, repository: str, data: bytes) -> str:
        body = {"content": base64.b64encode(data).decode(), "encoding": "base64"}
        return str(self._send("POST", f"{self.api}/repos/{repository}/git/blobs", body)["sha"])

    def create_tree(self, repository: str, base_tree: str, entries: list[dict[str, Any]]) -> str:
        body = {"base_tree": base_tree, "tree": entries}
        return str(self._send("POST", f"{self.api}/repos/{repository}/git/trees", body)["sha"])

    def create_commit(self, repository: str, words: str, tree: str, parent: str) -> str:
        body = {"message": words, "tree": tree, "parents": [parent]}
        return str(self._send("POST", f"{self.api}/repos/{repository}/git/commits", body)["sha"])

    def move_ref(self, repository: str, branch: str, commit: str) -> None:
        """Fast-forward only (force false): GitHub refuses with 422 when the branch moved."""
        url = f"{self.api}/repos/{repository}/git/refs/heads/{urllib.parse.quote(branch, safe='/')}"
        self._send("PATCH", url, {"sha": commit, "force": False})

    # ===== the device flow =====

    def device_code(self, client_id: str) -> dict[str, Any]:
        found = self._send(
            "POST",
            f"{self.web}/login/device/code",
            {"client_id": client_id, "scope": rules.SCOPE},
            form=True,
            auth=False,
        )
        if "device_code" not in found:
            code = str(found.get("error") or "")
            words = SIGN_IN_WORDS.get(code) or str(
                found.get("error_description") or "GitHub did not start the sign-in."
            )
            raise GitHubError(0, words)
        return dict(found)

    def device_token(self, client_id: str, device_code: str) -> dict[str, Any]:
        body = {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        return dict(self._send("POST", f"{self.web}/login/oauth/access_token", body, form=True, auth=False))


# The device flow's refusals in plain words (the owner saw "GitHub answered 400", 2026-11-18).
SIGN_IN_WORDS: dict[str, str] = {
    "device_flow_disabled": (
        "Sign in with GitHub is off for this app on GitHub: on the app's page in GitHub (Settings, Developer "
        "settings, OAuth Apps), tick Enable Device Flow and click Update application. Or use a token."
    ),
    "incorrect_client_credentials": (
        "GitHub does not know this app's Client ID: check it on the app's page in GitHub. Or use a token."
    ),
    "unauthorized_client": "GitHub does not let this app sign in this way. Use a token.",
}


def _words(status: int, said: str) -> str:
    if status == 401:
        return "GitHub refused the sign-in: sign in to GitHub again in Settings."
    if status == 403:
        return f"GitHub refused: {said[:200] or 'this sign-in may not do that'}."
    if status == 404:
        return "GitHub did not find it, or this sign-in cannot see it."
    if status == 409:
        return f"GitHub refused: {said[:200] or 'the repository is empty or in use'}."
    if status == 422:
        return f"GitHub refused: {said[:200] or 'the request did not fit'}."
    return f"GitHub answered {status}: {said[:200]}".rstrip(": ")


class GitHubToken:
    """The token in this computer's keyring only (service SwissArmyBench, user github/token)."""

    @staticmethod
    def _keyring() -> Any:
        from swissarmybench.adapters.blades import BladeStore

        return BladeStore._keyring()

    def get(self) -> str | None:
        try:
            value: str | None = self._keyring().get_password("SwissArmyBench", rules.KEYRING_USER)
        except Exception:  # no vault on this computer: not signed in
            return None
        return value

    def set(self, token: str) -> None:
        self._keyring().set_password("SwissArmyBench", rules.KEYRING_USER, token)

    def delete(self) -> None:
        try:
            self._keyring().delete_password("SwissArmyBench", rules.KEYRING_USER)
        except Exception:  # noqa: S110 (never set, or no vault)
            pass


def known_secrets(services: Any) -> list[str]:
    """Every value this computer keeps in its keyring for the library (connections' passwords, keyring
    variables): a push refuses a file holding one. Read here, held only for the check."""
    from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeStore

    try:
        vault = BladeStore._keyring()
    except Exception:  # no vault on this computer: nothing kept in one
        return []
    users: list[str] = []
    try:
        for blade in services.blades.everything():
            users += [f"blade/{blade.name.casefold()}/{s}" for s in blade.secrets]
    except Exception:  # noqa: S110 (a library that cannot be listed: the shapes still check)
        pass
    try:
        for listed in services.variables.listing()["variables"]:
            if listed.get("from") == "keyring":
                users.append(f"variable/{listed['name']}")
    except Exception:  # noqa: S110 (the same)
        pass
    found = []
    for user in users:
        try:
            value = vault.get_password(KEYRING_SERVICE, user)
        except Exception:  # noqa: S112 (one the vault will not give)
            continue
        if value:
            found.append(str(value))
    return found


class SyncLinks:
    """sync.json in the state folder: the signed-in login and each folder's link (None: kept in memory)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._held: dict[str, Any] = {"account": None, "folders": {}}

    def read(self) -> dict[str, Any]:
        if self.path is None or not self.path.is_file():
            held: dict[str, Any] = json.loads(json.dumps(self._held))
            return held
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "account": data.get("account"),
            "folders": data.get("folders") if isinstance(data.get("folders"), dict) else {},
        }

    def write(self, data: dict[str, Any]) -> None:
        self._held = json.loads(json.dumps(data))
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=1, sort_keys=True) + "\n"
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, self.path)


class SyncFolder:
    """A synced folder's files, by relative slash paths."""

    @staticmethod
    def full(folder: str) -> Path:
        return Path(folder).expanduser().resolve()

    def ignore(self, folder: str) -> rules.Ignore:
        root = self.full(folder)
        found = []
        for path in root.rglob(".gitignore"):
            rel = path.parent.relative_to(root).as_posix()
            rel = "" if rel == "." else rel
            if rel.split("/")[0] in (".git",) or ".git/" in rel + "/":
                continue
            try:
                found.append((rel, path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        return rules.Ignore(found)

    def files(self, folder: str) -> tuple[dict[str, str], list[str]]:
        """(path -> blob SHA) of every synced file, and the paths left out for being over 50 MB."""
        root = self.full(folder)
        if not root.is_dir():
            return {}, []
        ignore = self.ignore(folder)
        out: dict[str, str] = {}
        large: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            base = Path(dirpath).relative_to(root).as_posix()
            base = "" if base == "." else base
            dirnames[:] = sorted(d for d in dirnames if not ignore.ignored(f"{base}/{d}/x".lstrip("/")))
            for name in sorted(filenames):
                rel = f"{base}/{name}".lstrip("/")
                if ignore.ignored(rel):
                    continue
                path = Path(dirpath) / name
                if path.is_symlink() or not path.is_file():
                    continue
                if path.stat().st_size > rules.MAX_FILE_BYTES:
                    large.append(rel)
                    continue
                out[rel] = rules.blob_sha(path.read_bytes())
        return out, large

    def read(self, folder: str, rel: str) -> bytes:
        return (self.full(folder) / rel).read_bytes()

    def exists(self, folder: str, rel: str) -> bool:
        return (self.full(folder) / rel).is_file()

    def write(self, folder: str, rel: str, data: bytes) -> None:
        target = self.full(folder) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".sab-sync-")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def remove(self, folder: str, rel: str) -> None:
        root = self.full(folder)
        path = root / rel
        path.unlink(missing_ok=True)
        parent = path.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

    def is_empty(self, folder: str) -> bool:
        root = self.full(folder)
        return not root.exists() or (root.is_dir() and not any(root.iterdir()))

    def is_folder(self, folder: str) -> bool:
        return self.full(folder).is_dir()
