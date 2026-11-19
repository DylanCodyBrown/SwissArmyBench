"""Settings' Team box (domain/team.py has the rules; the owner, 2026-11-19: "you have made linking a
meta store and shared project folder way too difficult; the settings menu makes no sense"): ONE GitHub
repository holds the team library (at its top) and the team's shared projects (its projects/). The GitHub
work is the extension's that fills services/hooks.py's `team` (none on here: the Team box offers its
Install); this service points the library folder and the shared projects folder, keeps team.json and gives
the steps' words.

  status      no team (Join a team…, Start a team…) or joined (owner/repo, its sync words when something is to
              do); the step kept over Install's restart, taken up; the local projects folder; the two folders
              for Advanced
  join        the repository's local copy made in the state folder's team/<owner>-<repo>/ (no path asked),
              the library pointed at it, the shared projects folder at its projects/ (made), then Set up this
              computer's checklist (the agent's on Allow)
  start       a new private repository on GitHub with the layout (README.md, .gitignore, projects/), this
              computer's library copied in (it holds no secret), pushed; then as Join (the agent's on Allow)
  leave       asked first: keep a copy of the team's items? The library and the shared projects folder go back
              to what they were before joining; the local copy stays on disk, said where (the agent's on
              Allow)
  pull, push  the team library's (the extension asks the agent's Allow)
  show        Show its folder: the user's own (403 for the agent), as a project's Show in folder
  pending     Install of GitHub sync restarts the app: the step is kept in team.json, never in the page
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import team as rules
from swissarmybench.services.hooks import Hooks
from swissarmybench.services.workspace import Conflict, Refused, Workspace


class TeamSync(Protocol):
    """What the extension that syncs with GitHub hands over (hooks.team)."""

    def signed_in(self) -> dict[str, Any]: ...

    def url(self, repository: str) -> str: ...

    def linked(self, folder: str) -> str | None: ...

    async def repositories(self) -> list[dict[str, Any]]: ...

    async def owners(self) -> list[str]: ...

    async def create(self, owner: str | None, name: str, private: bool = True) -> str: ...

    async def copy(self, repository: str, folder: str) -> dict[str, Any]: ...

    async def push_all(self, folder: str, message: str) -> dict[str, Any]: ...

    async def status(self, remote: bool = False) -> dict[str, Any] | None: ...

    async def pull(self, who: str) -> dict[str, Any]: ...

    async def push(self, who: str) -> dict[str, Any]: ...


class Files(Protocol):
    """adapters/team.py TeamFiles."""

    def hashes(self, folder: str) -> dict[str, str]: ...

    def copy(self, source: str, target: str, paths: list[str]) -> None: ...

    def write(self, folder: str, files: dict[str, bytes]) -> None: ...

    def make(self, folder: str) -> None: ...

    def show(self, folder: str) -> None: ...

    def under(self, folder: str, *parts: str) -> str: ...

    def same(self, one: str, other: str) -> bool: ...


class Record(Protocol):
    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class LibraryPort(Protocol):
    def info(self) -> dict[str, Any]: ...

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]: ...


class ExplorerPort(Protocol):
    def folders(self) -> dict[str, Any]: ...

    def shared_folder(self) -> str | None: ...

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]: ...


class SetupPort(Protocol):
    async def checklist(self, check: bool = False, who: str = "user") -> dict[str, Any]: ...


class Asker(Protocol):
    async def ask(self, dataset: str, action: str, detail: str) -> bool: ...


class Team:
    def __init__(
        self,
        ws: Workspace,
        hooks: Hooks,
        library: LibraryPort,
        explorer: ExplorerPort,
        setup: SetupPort,
        record: Record,
        files: Files,
        state_dir: str,
        approvals: Asker,
        needs: Callable[[], dict[str, Any]],
        now: Callable[[], float] = time.time,
    ) -> None:
        self.ws = ws
        self._hooks = hooks
        self._library = library
        self._explorer = explorer
        self._setup = setup
        self._record = record
        self._files = files
        self._state = state_dir
        self._approvals = approvals
        self._needs = needs  # the extension that syncs with GitHub: its id, name, the words, installable
        self._now = now

    # ===== what is kept =====

    def _read(self) -> dict[str, Any]:
        found = self._record.read()
        return dict(found) if isinstance(found, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self._record.write({k: v for k, v in sorted(data.items()) if v is not None})

    def _sync(self) -> TeamSync | None:
        found: TeamSync | None = getattr(self._hooks, "team", None)
        return found

    def _needed(self) -> TeamSync:
        sync = self._sync()
        if sync is None:
            raise Conflict(
                f"{rules.NEEDS_WORDS}: Install it on the Extensions page ({self._needs()['name']})."
            )
        return sync

    def _joined(self) -> dict[str, Any] | None:
        """The team this computer is in: team.json's, while the library folder is still its local copy."""
        team = self._read().get("team")
        if not isinstance(team, dict) or not team.get("repository") or not team.get("folder"):
            return None
        return team if self._files.same(str(team["folder"]), str(self._library.info()["folder"])) else None

    async def _changed(self) -> None:
        await self.ws.live.broadcast({"type": "team_changed"})

    async def _allow(self, who: str, action: str, detail: str) -> None:
        if who == "agent" and not await self._approvals.ask("Team", action, detail):
            raise Refused("The user declined (or did not answer): nothing changed.")

    def _signed(self, sync: TeamSync) -> None:
        if not sync.signed_in().get("signed_in"):
            raise Refused("Sign in to GitHub first: Settings, Team (the user's own).")

    # ===== status =====

    async def status(self, remote: bool = False, who: str = "user") -> dict[str, Any]:
        sync = self._sync()
        signed = (
            sync.signed_in()
            if sync
            else {"signed_in": False, "account": None, "device": False, "token_steps": []}
        )
        library = self._library.info()
        folders = self._explorer.folders()
        team = self._joined()
        out: dict[str, Any] = {
            "state": "joined" if team else "none",
            "sync_on": sync is not None,
            "needs": None if sync else self._needs() | {"words": rules.NEEDS_WORDS},
            **signed,
            "pending": rules.resume(
                self._read().get("pending"), sync is not None, bool(signed.get("signed_in")), self._now()
            ),
            "local_projects": folders["local_folder"],
            "local_projects_default": folders["local_folder"] == folders["default_folder"],
            "library_folder": library["folder"],
            "library_default": library["is_default"],
            "shared_folder": folders["shared_folder"],
        }
        if team:
            found = await sync.status(remote) if sync else None
            out["team"] = {
                "repository": team["repository"],
                "folder": team["folder"],
                "projects": self._files.under(str(team["folder"]), rules.PROJECTS),
                "url": sync.url(team["repository"]) if sync else None,
                "sync": rules.sync_words(found),
            }
        return out

    async def set_pending(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"action": "join" | "start", "step"?}: kept over Install's restart; {"action": null}: gone."""
        data = self._read()
        action = body.get("action") if isinstance(body, dict) else None
        if action is None:
            data.pop("pending", None)
        else:
            step = str(body.get("step") or "install")
            data["pending"] = rules.pending(rules.check_action(action), step, self._now())
        self._write(data)
        return {"pending": data.get("pending")}

    async def repositories(self, search: str = "", who: str = "user") -> dict[str, Any]:
        sync = self._needed()
        self._signed(sync)
        found = await sync.repositories()
        return {"repositories": rules.newest_first(found, search), "account": sync.signed_in().get("account")}

    async def owners(self, who: str = "user") -> dict[str, Any]:
        sync = self._needed()
        self._signed(sync)
        return {"owners": await sync.owners()}

    # ===== join, start =====

    async def join(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"repository": "owner/name"}: its local copy made (or pulled), the folders pointed, the
        checklist."""
        sync = self._needed()
        repository = rules.check_repository(body.get("repository") if isinstance(body, dict) else None)
        self._signed(sync)
        await self._allow(
            who,
            "join a team",
            f"Join {repository}: its library becomes this computer's library and its projects/ the shared "
            "projects folder.",
        )
        folder = self._files.under(self._state, *rules.local_copy(repository))
        done = await sync.copy(repository, folder)
        await self._use(str(done.get("repository") or repository), folder, who)
        self.ws.audit.write(who, "team_join", None, files=int(done.get("files") or 0))
        return await self._answer(who) | {"joined": repository, "files": int(done.get("files") or 0)}

    async def start(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "owner"? (an organisation; default the account), "private"? (default true)}: the
        repository made with the layout, this computer's library copied in and pushed; then joined."""
        sync = self._needed()
        if not isinstance(body, dict):
            raise rules.TeamError('Send {"name": the new repository\'s name, "owner"?}.')
        name = rules.check_name(body.get("name"))
        owner = rules.check_owner(body.get("owner"))
        private = body.get("private") is not False
        self._signed(sync)
        account = sync.signed_in().get("account")
        await self._allow(
            who,
            "start a team",
            f"Make the {'private' if private else 'public'} repository {owner or account}/{name} on GitHub "
            "and copy this computer's library into it (it holds no password, token or row).",
        )
        repository = await sync.create(owner, name, private)
        folder = self._files.under(self._state, *rules.local_copy(repository))
        await sync.copy(repository, folder)
        own = str(self._library.info()["folder"])
        self._files.copy(own, folder, rules.copied_to_new_team(self._files.hashes(own)))
        self._files.write(folder, rules.layout())
        pushed = await sync.push_all(folder, "Start the team library")
        await self._use(repository, folder, who)
        self.ws.audit.write(who, "team_start", None, files=int(pushed.get("pushed") or 0))
        return await self._answer(who) | {"started": repository, "pushed": int(pushed.get("pushed") or 0)}

    async def _use(self, repository: str, folder: str, who: str) -> None:
        """The library folder pointed at the local copy and the shared projects folder at its projects/
        (made when missing); what they were before kept, for Leave."""
        projects = self._files.under(folder, rules.PROJECTS)
        self._files.make(projects)
        data = self._read()
        before = (data.get("team") or {}).get("before") if self._joined() else None
        if before is None:
            library = self._library.info()
            before = {
                "library": None if library["is_default"] else str(library["folder"]),
                "shared": self._explorer.shared_folder(),
            }
        # The user's Join (or the agent's, Allowed once above): the two folders follow without asking again.
        await self._library.set_folder({"folder": folder}, "user")
        await self._explorer.set_folder({"which": "shared", "folder": projects}, "user")
        data["team"] = {"repository": repository, "folder": folder, "before": before}
        data.pop("pending", None)
        self._write(data)
        await self._changed()

    async def _answer(self, who: str) -> dict[str, Any]:
        return await self.status(False, who) | {"setup": await self._setup.checklist(False, who)}

    # ===== leave =====

    async def leave(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"keep": true | false}: asked first ({} answers the question). The library goes back to this
        computer's own, the shared projects folder to what it was; the local copy stays where it is."""
        team = self._joined()
        if team is None:
            raise Conflict("This computer is not in a team.")
        keep = body.get("keep") if isinstance(body, dict) else None
        if keep is None:
            return {"ask": rules.leave_question(str(team["repository"]))}
        if not isinstance(keep, bool):
            raise rules.TeamError('Send {"keep": true} or {"keep": false}.')
        repository, folder = str(team["repository"]), str(team["folder"])
        await self._allow(
            who,
            "leave the team",
            f"Leave {repository}: the library goes back to this computer's own"
            + (", with a copy of the team's items." if keep else ", without a copy."),
        )
        kept = team.get("before")
        before: dict[str, Any] = kept if isinstance(kept, dict) else {}
        await self._library.set_folder({"folder": before.get("library")}, "user")
        own = str(self._library.info()["folder"])
        plan = rules.leave_plan(self._files.hashes(folder), self._files.hashes(own), keep)
        self._files.copy(folder, own, plan["copy"])
        shared = before.get("shared")
        await self._explorer.set_folder(
            {"which": "shared", "folder": shared} if shared else {"which": "shared", "default": True}, "user"
        )
        data = self._read()
        data.pop("team", None)
        self._write(data)
        self.ws.audit.write(who, "team_leave", None, copied=len(plan["copy"]), kept=len(plan["kept"]))
        await self._changed()
        if plan["copy"]:
            await self.ws.live.broadcast({"type": "library_changed"})
        return await self.status(False, who) | {
            "left": repository,
            "folder": folder,
            "copied": len(plan["copy"]),
            "kept": len(plan["kept"]),
            "words": rules.leave_words(repository, folder, len(plan["copy"]), len(plan["kept"])),
        }

    # ===== pull, push, show =====

    def _team(self) -> tuple[TeamSync, dict[str, Any]]:
        sync = self._needed()
        team = self._joined()
        if team is None:
            raise Conflict("This computer is not in a team: Settings, Team, Join a team.")
        return sync, team

    async def pull(self, who: str = "user") -> dict[str, Any]:
        sync, _team = self._team()
        done = await sync.pull(who)
        await self._changed()
        return done

    async def push(self, who: str = "user") -> dict[str, Any]:
        sync, _team = self._team()
        done = await sync.push(who)
        await self._changed()
        return done

    async def show(self, who: str = "user") -> dict[str, Any]:
        if who == "agent":
            raise Refused("Show its folder is the user's own: it opens on the user's screen.")
        team = self._joined()
        if team is None:
            raise Conflict("This computer is not in a team.")
        self._files.show(str(team["folder"]))
        return {"shown": team["folder"]}
