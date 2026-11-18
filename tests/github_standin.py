"""GitHub stood in for on 127.0.0.1 (the Git extension's tests): the device flow (github.com/login), the REST API's
user, repositories, refs, commits, trees, blobs, compare, branches and the Git Data API's writes, over in-memory
repositories of made-up files. Real GitHub is never reached.

    with GitHubStandin() as hub:
        hub.repository("made-up-team/meta-store", {"README.md": b"# Meta store\\n"})
        hub.teammate("made-up-team/meta-store", {"connections/Warehouse.blade.py": b"..."})   # a teammate pushes
        env: SWISSARMYBENCH_GITHUB_API=hub.url, SWISSARMYBENCH_GITHUB_WEB=hub.url
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import urllib.parse
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TOKEN = "github_pat_made_up_standin_token_000000000000000000000000000000"
LOGIN = "made-up-analyst"


def _sha(kind: str, data: bytes) -> str:
    return hashlib.sha1(b"%s %d\0" % (kind.encode(), len(data)) + data, usedforsecurity=False).hexdigest()


class Repo:
    def __init__(self, name: str, branch: str = "main") -> None:
        self.name = name
        self.default = branch
        self.refs: dict[str, str] = {}


class GitHubStandin:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}  # tree -> {path: blob}
        self.commits: dict[str, dict[str, Any]] = {}
        self.repos: dict[str, Repo] = {}
        self.tokens: set[str] = {TOKEN}
        self.device_ready = False
        self.requests: list[tuple[str, str]] = []  # (method, path): what the app asked
        self.seen_auth: list[str] = []
        self._clock = 0
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self) -> GitHubStandin:
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    # ===== the repositories =====

    def _blob(self, data: bytes) -> str:
        sha = _sha("blob", data)
        self.blobs[sha] = data
        return sha

    def _tree(self, files: Mapping[str, str]) -> str:
        text = json.dumps(sorted(files.items())).encode()
        sha = _sha("tree", text)
        self.trees[sha] = dict(files)
        return sha

    def _commit(self, tree: str, parents: list[str], message: str, author: str = "Made Up Teammate") -> str:
        self._clock += 1
        body = {
            "tree": tree,
            "parents": parents,
            "message": message,
            "author": {
                "name": author,
                "email": "teammate@example.com",
                "date": f"2026-11-18T10:{self._clock:02d}:00Z",
            },
        }
        sha = _sha("commit", json.dumps(body, sort_keys=True).encode())
        self.commits[sha] = body
        return sha

    def repository(
        self, name: str, files: Mapping[str, bytes] | None = None, branch: str = "main"
    ) -> str | None:
        """A repository; with files, its first commit (none: an empty repository)."""
        repo = Repo(name, branch)
        self.repos[name] = repo
        if files is None:
            return None
        tree = self._tree({p: self._blob(d) for p, d in files.items()})
        repo.refs[branch] = self._commit(tree, [], "Initial commit")
        return repo.refs[branch]

    def teammate(
        self,
        name: str,
        files: Mapping[str, bytes | None],
        message: str = "A teammate's change",
        branch: str | None = None,
    ) -> str:
        """A teammate's push: files changed (None: deleted) on the branch's head."""
        with self._lock:
            repo = self.repos[name]
            branch = branch or repo.default
            head = repo.refs[branch]
            current = dict(self.trees[self.commits[head]["tree"]])
            for path, data in files.items():
                if data is None:
                    current.pop(path, None)
                else:
                    current[path] = self._blob(data)
            repo.refs[branch] = self._commit(self._tree(current), [head], message)
            return repo.refs[branch]

    def files(self, name: str, branch: str | None = None) -> dict[str, bytes]:
        repo = self.repos[name]
        head = repo.refs[branch or repo.default]
        return {p: self.blobs[s] for p, s in self.trees[self.commits[head]["tree"]].items()}

    def head(self, name: str, branch: str | None = None) -> str:
        repo = self.repos[name]
        return repo.refs[branch or repo.default]

    # ===== the HTTP side =====

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                return

            def _answer(self, status: int, body: Any) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self) -> Any:
                size = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(size) if size else b""
                if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
                    return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                return json.loads(raw or b"{}")

            def _authorised(self) -> bool:
                auth = self.headers.get("Authorization") or ""
                hub.seen_auth.append(auth)
                return auth.removeprefix("Bearer ").strip() in hub.tokens

            def do_GET(self) -> None:
                self._route("GET")

            def do_POST(self) -> None:
                self._route("POST")

            def do_PATCH(self) -> None:
                self._route("PATCH")

            def _route(self, method: str) -> None:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                hub.requests.append((method, path))
                try:
                    with hub._lock:
                        status, body = hub._serve(method, path, query, self)
                except KeyError:
                    status, body = 404, {"message": "Not Found"}
                self._answer(status, body)

        return Handler

    def _serve(self, method: str, path: str, query: dict[str, str], request: Any) -> tuple[int, Any]:
        # The device flow (github.com/login): no token.
        if path == "/login/device/code" and method == "POST":
            body = request._body()
            if body.get("client_id") != "made-up-client-id":
                return 404, {"error": "Not Found"}
            return 200, {
                "device_code": "made-up-device-code",
                "user_code": "WDJB-MJHT",
                "verification_uri": "https://github.com/login/device",
                "interval": 1,
                "expires_in": 900,
            }
        if path == "/login/oauth/access_token" and method == "POST":
            body = request._body()
            if body.get("device_code") != "made-up-device-code":
                return 200, {"error": "expired_token"}
            if not self.device_ready:
                return 200, {"error": "authorization_pending", "interval": 1}
            return 200, {"access_token": TOKEN, "token_type": "bearer", "scope": "repo"}
        if not request._authorised():
            return 401, {"message": "Bad credentials"}
        if path == "/user":
            return 200, {"login": LOGIN, "name": "Made Up Analyst"}
        if path == "/user/repos":
            return 200, [
                {
                    "full_name": r.name,
                    "default_branch": r.default,
                    "private": True,
                    "permissions": {"push": True},
                }
                for r in self.repos.values()
            ] if query.get("page", "1") == "1" else []
        parts = path.strip("/").split("/")
        if parts[0] != "repos" or len(parts) < 3:
            return 404, {"message": "Not Found"}
        name = f"{parts[1]}/{parts[2]}"
        repo = self.repos[name]
        rest = parts[3:]
        if not rest:
            return 200, {"full_name": name, "default_branch": repo.default, "permissions": {"push": True}}
        if rest[:3] == ["git", "ref", "heads"] and method == "GET":
            branch = "/".join(rest[3:])
            if not repo.refs:
                return 409, {"message": "Git Repository is empty."}
            if branch not in repo.refs:
                return 404, {"message": "Not Found"}
            return 200, {
                "ref": f"refs/heads/{branch}",
                "object": {"sha": repo.refs[branch], "type": "commit"},
            }
        if rest[:3] == ["git", "refs", "heads"] and method == "PATCH":
            branch = "/".join(rest[3:])
            body = request._body()
            new = str(body["sha"])
            if body.get("force"):
                return 422, {"message": "The stand-in refuses a forced update."}
            if self.commits[new]["parents"][:1] != [repo.refs.get(branch)]:
                return 422, {"message": "Update is not a fast forward"}
            repo.refs[branch] = new
            return 200, {"object": {"sha": new}}
        if rest == ["git", "refs"] and method == "POST":
            body = request._body()
            branch = str(body["ref"]).removeprefix("refs/heads/")
            if branch in repo.refs:
                return 422, {"message": "Reference already exists"}
            repo.refs[branch] = str(body["sha"])
            return 201, {"ref": body["ref"], "object": {"sha": body["sha"]}}
        if rest[:2] == ["git", "commits"] and method == "GET":
            commit = self.commits[rest[2]]
            return 200, {
                "sha": rest[2],
                "tree": {"sha": commit["tree"]},
                "parents": [{"sha": p} for p in commit["parents"]],
            }
        if rest[:2] == ["git", "trees"] and method == "GET":
            files = self.trees[rest[2]]
            entries = [
                {"path": p, "mode": "100644", "type": "blob", "sha": s, "size": len(self.blobs[s])}
                for p, s in sorted(files.items())
            ]
            return 200, {"sha": rest[2], "tree": entries, "truncated": False}
        if rest[:2] == ["git", "blobs"] and method == "GET":
            data = self.blobs[rest[2]]
            return 200, {
                "sha": rest[2],
                "content": base64.b64encode(data).decode(),
                "encoding": "base64",
                "size": len(data),
            }
        if rest == ["git", "blobs"] and method == "POST":
            body = request._body()
            data = (
                base64.b64decode(body["content"])
                if body.get("encoding") == "base64"
                else str(body["content"]).encode()
            )
            return 201, {"sha": self._blob(data)}
        if rest == ["git", "trees"] and method == "POST":
            body = request._body()
            files = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                if entry.get("sha") is None:
                    files.pop(entry["path"], None)
                else:
                    files[entry["path"]] = entry["sha"]
            return 201, {"sha": self._tree(files)}
        if rest == ["git", "commits"] and method == "POST":
            body = request._body()
            return 201, {"sha": self._commit(body["tree"], list(body["parents"]), body["message"], LOGIN)}
        if rest[0] == "compare":
            base, head = rest[1].split("...")
            return 200, {"ahead_by": self._distance(base, head), "behind_by": 0}
        if rest == ["commits"]:
            start = repo.refs[query.get("sha") or repo.default]
            rows = self._history(start)
            per = int(query.get("per_page") or 30)
            page = int(query.get("page") or 1)
            return 200, [self._row(s) for s in rows[(page - 1) * per : page * per]]
        if rest[0] == "commits" and len(rest) == 2:
            sha = rest[1]
            commit = self.commits[sha]
            before = self.trees[self.commits[commit["parents"][0]]["tree"]] if commit["parents"] else {}
            after = self.trees[commit["tree"]]
            changed: list[dict[str, str]] = []
            for p in sorted({*before, *after}):
                if before.get(p) == after.get(p):
                    continue
                status = "added" if p not in before else "removed" if p not in after else "modified"
                changed.append({"filename": p, "status": status})
            return 200, self._row(sha) | {"files": changed}
        if rest == ["branches"]:
            return 200, [{"name": b, "commit": {"sha": s}} for b, s in sorted(repo.refs.items())]
        return 404, {"message": "Not Found"}

    def _history(self, start: str) -> list[str]:
        """Every commit reachable from start, newest first (by the stand-in's clock)."""
        seen: dict[str, None] = {}
        stack = [start]
        while stack:
            sha = stack.pop()
            if sha in seen:
                continue
            seen[sha] = None
            stack += self.commits[sha]["parents"]
        return sorted(seen, key=lambda s: self.commits[s]["author"]["date"], reverse=True)

    def _distance(self, base: str, head: str) -> int:
        return sum(1 for s in self._history(head) if s not in set(self._history(base)))

    def _row(self, sha: str) -> dict[str, Any]:
        commit = self.commits[sha]
        return {
            "sha": sha,
            "commit": {"message": commit["message"], "author": commit["author"]},
            "parents": [{"sha": p} for p in commit["parents"]],
        }
