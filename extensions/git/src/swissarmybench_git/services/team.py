"""What the Git extension hands the base's Team box (swissarmybench/services/team.py, through services/hooks.py's
`team`): a team is ONE GitHub repository (the team library at its top, the shared projects in projects/), so the
base asks for its local copy, its new repository, its pull and push, and its words here. The base asks the
agent's Allow once for Join, Start and Leave; Pull and Push ask their own (services/sync.py).

  signed_in     who is signed in (never the token), whether Sign in with GitHub works, the token's steps
  repositories  the account's repositories (owner/name, private, can push, the last push)
  owners        the account and its organisations: who a new team repository can belong to
  create        a new private repository with a first commit (GitHub's README)
  copy          the local copy: cloned into an empty or new folder; already linked to the same repository:
                pulled instead
  push_all      every change of the local copy as one commit (Start a team's first push)
  status        the local copy's words (Pull, 2 changes to push, Conflicts), GitHub asked at most once a minute
  pull, push    the team library's (which "library"), as the Source Control page's
"""

from __future__ import annotations

import asyncio
from typing import Any

from swissarmybench.services.workspace import Conflict
from swissarmybench_git.domain import sync as rules
from swissarmybench_git.services.sync import GitHubSync, _sync


class TeamPort:
    def __init__(self, sync: GitHubSync, web: str) -> None:
        self._sync = sync
        self._web = web.rstrip("/")

    def signed_in(self) -> dict[str, Any]:
        token = self._sync._token.get()
        return {
            "signed_in": bool(token),
            "account": self._sync._account() if token else None,
            "device": bool(self._sync._client_id),
            "token_steps": list(rules.TOKEN_STEPS),
        }

    def url(self, repository: str) -> str:
        return f"{self._web}/{repository}"

    async def repositories(self) -> list[dict[str, Any]]:
        return list((await self._sync.repositories())["repositories"])

    async def owners(self) -> list[str]:
        token = self._sync._signed_in()
        client = self._sync._client(token)
        found = await asyncio.to_thread(lambda: _sync(client.organisations))
        account = self._sync._account()
        return [*([account] if account else []), *found]

    async def create(self, owner: str | None, name: str, private: bool = True) -> str:
        token = self._sync._signed_in()
        client = self._sync._client(token)
        account = self._sync._account()
        made = await asyncio.to_thread(
            lambda: _sync(
                lambda: client.create_repository(None if owner == account else owner, name, private)
            )
        )
        repository = str(made["repository"])
        if not repository:
            raise rules.SyncError("GitHub did not say which repository it made.")
        return repository

    async def copy(self, repository: str, folder: str) -> dict[str, Any]:
        """The local copy of the team's repository in `folder`: cloned (an empty or new folder), or pulled when
        the folder is that repository's already (a second Join)."""
        repository = rules.check_repository(repository)
        token = self._sync._signed_in()
        folder = str(self._sync._files.full(folder))
        link = self._sync._link(folder)
        async with self._sync._lock:
            if link is not None and link.repository.casefold() == repository.casefold():
                done = await asyncio.to_thread(self._sync._pull, token, folder, link)
                done |= {"folder": folder, "repository": link.repository, "files": done["written"]}
            elif self._sync._files.is_empty(folder):
                done = await asyncio.to_thread(self._sync._clone, token, folder, repository, None)
            else:
                raise Conflict(f"{folder} holds other files: move them away, then Join again.")
        await self._sync._changed()
        return done

    async def push_all(self, folder: str, message: str) -> dict[str, Any]:
        token = self._sync._signed_in()
        folder = str(self._sync._files.full(folder))
        link = self._sync._link(folder)
        if link is None:
            raise rules.SyncError(f"{folder} is not linked to GitHub.")
        async with self._sync._lock:
            done = await asyncio.to_thread(self._sync._push, token, folder, link, None, None, message)
        await self._sync._changed()
        return dict(done)

    async def status(self, remote: bool = False) -> dict[str, Any] | None:
        """The team library folder's sync (the link that holds it), or None when it has none."""
        found = await self._sync.status(remote)
        return next((f for f in found["folders"] if f["which"] == "library"), None)

    def linked(self, folder: str) -> str | None:
        """The repository a folder is linked to (None: none)."""
        link = self._sync._link(str(self._sync._files.full(folder)))
        return link.repository if link else None

    async def pull(self, who: str) -> dict[str, Any]:
        return await self._sync.pull({"which": "library"}, who)

    async def push(self, who: str) -> dict[str, Any]:
        return await self._sync.push({"which": "library"}, who)
