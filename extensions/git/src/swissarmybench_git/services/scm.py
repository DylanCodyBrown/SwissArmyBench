"""The Source Control page (the owner, 2026-11-18: "literally steal VS Code's panel for git with the graph and commit
and show it with a diff navigator on a new rail icon"): VS Code's Source Control view and its graph, over the
GitHub sync of services/sync.py. No local Git: what needs one (stash, local commits, rebase, hunks) is not here.

  changes    each connected folder a repository (the shared projects folder's scoped to the open project):
             Merge Changes (a pull's conflicts), Staged Changes and Changes, with VS Code's letters
  stage      Stage Changes and Unstage Changes: what the next commit takes (kept with the folder's link)
  discard    Discard Changes: a file back to its last synced version, a new one deleted (the agent's on Allow)
  commit     Commit: the staged files (or the ones named) as one commit on GitHub (services/sync.py push)
  sync       Sync Changes: Pull, then Push
  history    the branch's commits from GitHub (100 a page), the refs to label, the uncommitted count
  commit     a commit's files; a file's two sides for the diff editor (last synced and here, a commit's parent
  files      and itself, yours and theirs for a conflict), or the agent's unified text
  branches   the repository's branches; Checkout to... and Create Branch... (on GitHub; the agent's on Allow)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from swissarmybench.services.workspace import Conflict
from swissarmybench_git.domain import sync as rules
from swissarmybench_git.services.sync import GitHubSync, _sync


class SourceControl(GitHubSync):
    def _repositories(self) -> list[tuple[str, str, rules.Link, str | None]]:
        """Each connected folder: (which, folder, link, the open project's subfolder of the shared one)."""
        out = []
        for which in rules.WHICH:
            raw = self._folders(which)
            if not raw:
                continue
            folder = str(self._files.full(raw))
            link = self._link(folder)
            if link is None:
                continue
            scope = None
            project = self._project() if which == "shared" else None
            if project:
                try:
                    rel = self._files.full(project).relative_to(Path(folder)).as_posix()
                    scope = None if rel == "." else rel
                except ValueError:
                    scope = None
            out.append((which, folder, link, scope))
        return out

    def _changes_of(self, which: str, folder: str, link: rules.Link, scope: str | None) -> dict[str, Any]:
        local, large = self._files.files(folder) if self._files.is_folder(folder) else ({}, [])
        conflicts = self._open_conflicts(folder, link)
        staged = [p for p in link.staged if p in local or p in link.files]
        found = rules.groups(link.files, local, staged, conflicts, scope)
        held = self._remote.get(folder)
        name = link.repository.split("/")[-1]
        return {
            "which": which,
            "name": f"{name}/{scope}" if scope else name,
            "repository": link.repository,
            "folder": folder,
            "scope": scope,
            "branch": link.branch,
            "commit": link.commit,
            "groups": found,
            "count": sum(len(v) for v in found.values()),
            "behind": (held[2] if held else 0) or 0,
            "pulled": link.commit is not None,
            "large": large,
        }

    async def changes(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Every connected folder's groups (or {"which"}: one)."""
        want = body.get("which") if isinstance(body, dict) else None
        found = await asyncio.to_thread(
            lambda: [
                self._changes_of(w, f, link, s)
                for w, f, link, s in self._repositories()
                if not want or w == want
            ]
        )
        token = self._token.get()
        return {
            "signed_in": bool(token),
            "account": self._account() if token else None,
            "repositories": found,
        }

    def _one(self, body: Any) -> tuple[str, str, rules.Link]:
        which = rules.check_which(body.get("which") if isinstance(body, dict) else None)
        folder, link = self._connected(which)
        return which, folder, link

    async def stage(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "paths", "unstage"?}: Stage Changes, or Unstage Changes."""
        which, folder, link = self._one(body)
        paths = rules.check_paths(body.get("paths"))
        if body.get("unstage"):
            link.staged = [p for p in link.staged if p not in set(paths)]
        else:
            link.staged = sorted({*link.staged, *paths})
        self._save(folder, link)
        await self._changed()
        return {"which": which, "staged": sorted(link.staged)}

    async def discard(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "paths"}: each file back to its last synced version (a new one deleted). The page asks
        the user first, as VS Code does; the agent's waits for the user's Allow."""
        which, folder, link = self._one(body)
        paths = rules.check_paths(body.get("paths"))
        if not paths:
            raise rules.SyncError("Name the files to discard.")
        detail = (
            f"Discard the changes in {rules.plural(len(paths), 'file')} in {folder}: {', '.join(paths[:5])}"
        )
        await self._allow(who, which, "discard changes", detail)
        token = self._signed_in()
        async with self._lock:
            done = await asyncio.to_thread(self._discard, token, folder, link, paths)
        self.ws.audit.write(who, "scm_discard", None, which=which, files=len(done))
        await self._changed()
        return {"which": which, "discarded": done}

    def _discard(self, token: str, folder: str, link: rules.Link, paths: list[str]) -> list[str]:
        client = self._client(token)
        for path in paths:
            sha = link.files.get(path)
            if sha is None:
                self._files.remove(folder, path)
            else:
                data = _sync(lambda s=sha: client.blob(link.repository, s))  # type: ignore[misc]
                self._files.write(folder, path, data)
            if path in link.conflicts:
                self._files.remove(folder, rules.theirs_path(path))
        link.staged = [p for p in link.staged if p not in set(paths)]
        link.conflicts = [p for p in link.conflicts if p not in set(paths)]
        self._save(folder, link)
        return paths

    async def commit(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "message", "paths"?, "sync"?}: Commit: the named files (else the staged ones, else every
        change) as one commit on GitHub. sync: Pull first (Commit & Sync)."""
        which, folder, link = self._one(body)
        if not str(body.get("message") or "").strip():
            raise rules.SyncError("Type a message to commit.")
        paths = rules.check_paths(body.get("paths")) or [
            p for p in link.staged if self._files.exists(folder, p) or p in link.files
        ]
        if body.get("sync"):
            await self.pull({"which": which}, who)
        return await self.push({"which": which, "message": body.get("message"), "paths": paths or None}, who)

    async def sync(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Sync Changes: Pull, then Push."""
        pulled = await self.pull(body, who)
        if pulled["conflicts"]:
            return {"pulled": pulled, "pushed": None, "words": pulled["words"]}
        pushed = await self.push(body, who)
        return {"pulled": pulled, "pushed": pushed, "words": f"{pulled['words']}. {pushed['words']}"}

    async def history(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "page"?}: the branch's commits, newest first, and the refs the graph labels."""
        which, folder, link = self._one(body)
        page = max(1, int(body.get("page") or 1))
        token = self._signed_in()

        def read() -> tuple[list[dict[str, Any]], str | None]:
            client = self._client(token)
            rows = [
                rules.history_row(c)
                for c in _sync(lambda: client.commits(link.repository, link.branch, page))
            ]
            return rows, _sync(lambda: client.head(link.repository, link.branch))

        rows, head = await asyncio.to_thread(read)
        local, _ = await asyncio.to_thread(self._files.files, folder)
        changed, deleted = rules.changes(link.files, local)
        refs = []
        if link.commit:
            refs.append(
                {
                    "id": f"refs/heads/{link.branch}",
                    "name": link.branch,
                    "commit": link.commit,
                    "kind": "local",
                }
            )
        if head:
            refs.append(
                {
                    "id": f"refs/remotes/origin/{link.branch}",
                    "name": f"origin/{link.branch}",
                    "commit": head,
                    "kind": "remote",
                }
            )
        return {
            "which": which,
            "repository": link.repository,
            "branch": link.branch,
            "page": page,
            "more": len(rows) == 100,
            "rows": rows,
            "refs": refs,
            "uncommitted": len(changed) + len(deleted),
        }

    async def commit_files(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "commit"}: one commit's files, each with VS Code's letter, and its parent."""
        which, _folder, link = self._one(body)
        sha = str(body.get("commit") or "")
        if not sha:
            raise rules.SyncError("Name the commit.")
        token = self._signed_in()
        found = await asyncio.to_thread(
            lambda: _sync(lambda: self._client(token).commit(link.repository, sha))
        )
        files = [
            rules.resource(
                str(f.get("filename")), rules.COMMIT_FILE.get(str(f.get("status")), "index_modified")
            )
            | {"previous": f.get("previous_filename")}
            for f in found.get("files") or []
        ]
        row = rules.history_row(found)
        return {"which": which, "commit": row, "files": files, "parent": (row["parents"] or [None])[0]}

    async def diff(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "path", "commit"?, "conflict"?, "unified"?}: the diff editor's two sides."""
        which, folder, link = self._one(body)
        found = rules.check_paths(body.get("path"))
        if len(found) != 1:
            raise rules.SyncError("Name one file.")
        rel = found[0]
        token = self._signed_in()
        commit = str(body.get("commit") or "")
        conflict = bool(body.get("conflict"))

        def here(path: str) -> bytes | None:
            return self._files.read(folder, path) if self._files.exists(folder, path) else None

        def sides() -> tuple[bytes | None, bytes | None, str, str]:
            client = self._client(token)
            if commit:
                one = _sync(lambda: client.commit(link.repository, commit))
                parents = [str(p.get("sha")) for p in one.get("parents") or []]
                before = _sync(lambda: client.file_at(link.repository, parents[0], rel)) if parents else None
                after = _sync(lambda: client.file_at(link.repository, commit, rel))
                left = f"{rel} ({parents[0][:8]})" if parents else rel
                return before, after, left, f"{rel} ({commit[:8]})"
            if conflict:
                return here(rel), here(rules.theirs_path(rel)), f"{rel} (Yours)", f"{rel} (Theirs)"
            sha = link.files.get(rel)
            before = _sync(lambda: client.blob(link.repository, str(sha))) if sha else None
            return before, here(rel), f"{rel} (HEAD)", f"{rel} (Working Tree)"

        before, after, left, right = await asyncio.to_thread(sides)
        binary = any(side is not None and not rules.is_text(side) for side in (before, after))
        original = "" if before is None or binary else before.decode("utf-8")
        modified = "" if after is None or binary else after.decode("utf-8")
        facts = {
            "which": which,
            "path": rel,
            "binary": binary,
            "added": before is None,
            "deleted": after is None,
        }
        if body.get("unified"):
            return facts | {
                "diff": "Binary files differ\n" if binary else rules.unified(original, modified, rel)
            }
        return facts | {
            "original": original,
            "modified": modified,
            "original_label": left,
            "modified_label": right,
        }

    async def branches(self, body: Any, who: str = "user") -> dict[str, Any]:
        which, _folder, link = self._one(body)
        token = self._signed_in()
        found = await asyncio.to_thread(lambda: _sync(lambda: self._client(token).branches(link.repository)))
        return {"which": which, "current": link.branch, "branches": found}

    async def checkout(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"which", "branch", "create"?}: Checkout to... (refused while files here have changes, as git is), or
        Create Branch... on GitHub from the last synced commit (then the folder is on it)."""
        which, folder, link = self._one(body)
        branch = rules.check_branch_name(body.get("branch"))
        create = bool(body.get("create"))
        token = self._signed_in()
        local, _ = await asyncio.to_thread(self._files.files, folder)
        changed, deleted = rules.changes(link.files, local)
        if not create and (changed or deleted):
            raise Conflict(
                f"Your local changes to {rules.plural(len(changed) + len(deleted), 'file')} would be overwritten "
                "by checkout. Please commit your changes or discard them before you switch branches."
            )
        doing = "create the branch" if create else "check out the branch"
        await self._allow(
            who, which, doing, f"{doing.capitalize()} {branch} of {link.repository} in {folder}."
        )
        async with self._lock:
            client = self._client(token)
            if create:
                if not link.commit:
                    raise rules.SyncError("Pull first: the branch starts from the last synced commit.")
                start = str(link.commit)
                await asyncio.to_thread(
                    lambda: _sync(lambda: client.create_branch(link.repository, branch, start))
                )
                link.branch = branch
                self._save(folder, link)
                done: dict[str, Any] = {"words": f"Made {branch} on GitHub"}
            else:
                link.branch = branch
                link.staged = []
                link.commit = link.commit  # the pull below brings the branch's files (a three-way plan)
                done = await asyncio.to_thread(self._pull, token, folder, link)
        self._remote.pop(folder, None)
        self.ws.audit.write(who, "scm_checkout", None, which=which, create=create)
        await self._changed()
        if self._pulled is not None and not create:
            await self._pulled(which)
        return done | {"which": which, "branch": branch}
