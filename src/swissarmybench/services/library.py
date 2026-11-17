"""The library (Plans/library.plan.md; domain/library.py has the rules): this computer's connections, APIs,
vaults, blades, tangs, variables and colours in one folder made to be a Git repository, whatever project is
open.

  info        where the folder is, what is in it (counts), what stays on this computer (local/, the keyring),
              what never goes in, whether it is a Git working copy (looked at, never run)
  folder      Settings' Library folder: point it at another folder (a clone of a team's repository) or back
              at the default. It changes every store at once, so the agent's waits for the user's Allow
  migration   this computer's stores from before the library, moved in once at start (said once on the page);
              a project's own blades (an older .sab) copied in when it opens: the same skipped, a different
              one kept as "<name> from <project>", said in a notice; the working folder's copy then goes,
              so the project's next save leaves it out
  notices     what the page says once (memory only): taken by the page, read by the agent
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import library as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.services.workspace import Refused, Workspace


class Folder(Protocol):
    """adapters/library.py LibraryFolder."""

    default: Any  # a Path

    @property
    def root(self) -> Any: ...  # a Path

    def check(self, raw: Any) -> Any: ...

    def use(self, path: Any) -> None: ...

    def counts(self) -> dict[str, int]: ...

    def is_git(self) -> bool: ...

    def project_blades(self, folder: str) -> list[Blade]: ...

    def drop_project_blades(self, folder: str) -> None: ...


class Store(Protocol):
    """adapters/blades.py BladeStore: the library's saved blades."""

    def get(self, name: str) -> Blade: ...

    def all(self) -> list[Blade]: ...

    def adopt(self, blade: Blade) -> Any: ...

    def text_of(self, blade: Blade) -> str: ...

    def listed(self, blade: Blade) -> Blade: ...

    def copy_secrets(self, source: str, target: str) -> None: ...


class Asker(Protocol):
    async def ask(self, dataset: str, action: str, detail: str) -> bool: ...


class Library:
    def __init__(
        self,
        ws: Workspace,
        folder: Folder,
        store: Store,
        approvals: Asker,
        moved: Callable[[], Awaitable[None]],
    ) -> None:
        self.ws = ws
        self._folder = folder
        self._store = store
        self._approvals = approvals
        self._moved = moved  # every store pointed at the new folder (bootstrap), the pages told
        self.notices: list[dict[str, str]] = []

    # ===== what it is =====

    def info(self) -> dict[str, Any]:
        root = self._folder.root
        return {
            "folder": str(root),
            "default": str(self._folder.default),
            "is_default": root == self._folder.default,
            "git": self._folder.is_git(),
            "counts": self._folder.counts(),
            "local": [
                f"{rules.LOCAL}/ (git-ignored): plain values marked this computer only",
                "the keyring: every secret's value",
            ],
            "never": list(rules.NEVER),
            "notices": list(self.notices),
        }

    def take_notices(self) -> dict[str, Any]:
        """The page's: what to say once, then gone."""
        taken, self.notices = self.notices, []
        return {"notices": taken}

    def notice(self, kind: str, text: str) -> None:
        if text:
            self.notices.append({"kind": kind, "text": text})

    # ===== the folder =====

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"folder": a whole path} or {"folder": null} (the default). The agent's waits for the user's Allow:
        every connection, API, vault, blade and variable changes at once."""
        raw = body.get("folder") if isinstance(body, dict) else None
        path = None if raw is None else self._folder.check(raw)
        if path == self._folder.default:
            path = None
        target = path or self._folder.default
        if target == self._folder.root:
            return self.info()
        if who == "agent" and not await self._approvals.ask(
            "library",
            "use another library folder",
            f"Use {target} as the library: every connection, API, vault, blade and variable read there.",
        ):
            raise Refused("The user declined (or did not answer): the library folder stays as it is.")
        self._folder.use(path)
        await self._moved()
        self.ws.audit.write(who, "library_folder", None, default=path is None)
        await self.ws.live.broadcast({"type": "library_changed"})
        return self.info()

    # ===== a project's own blades, from before the library =====

    def adopt_project(self, folder: str, project: str) -> dict[str, Any]:
        """An opened project's .sab/blades copied into the library (take), then removed from its working
        folder so the next save leaves them out. Returns what happened, and its words (a notice too)."""
        found = self._folder.project_blades(folder)
        if not found:
            return {"added": [], "renamed": {}, "skipped": [], "words": ""}
        done = self.take(found, project)
        self._folder.drop_project_blades(folder)
        self.notice("project", done["words"] if (done["added"] or done["renamed"]) else "")
        return done

    def take(self, blades: list[Blade], project: str, who: str = "user") -> dict[str, Any]:
        """Blades from a project (opened, or imported from) into the library: a new name added, the same
        text skipped, a different one kept as "<name> from <project>" (its secrets copied to the new name)."""
        added: list[str] = []
        renamed: dict[str, str] = {}
        skipped: list[str] = []
        taken = [b.name for b in self._store.all()]
        for blade in blades:
            try:
                own = self._store.get(blade.name)
            except KeyError:
                own = None
            if own is None:
                self._store.adopt(blade)
                added.append(blade.name)
                taken.append(blade.name)
            elif own.path or own.pack or self._store.text_of(own) == self._store.text_of(self._store.listed(blade)):
                skipped.append(blade.name)  # the same one (or a folder's or a pack's of that name)
            else:
                old, new = blade.name, rules.migrated_name(blade.name, project, taken)
                blade.name = new
                self._store.adopt(blade)
                self._store.copy_secrets(old, new)
                renamed[old] = new
                taken.append(new)
        self.ws.audit.write(
            who, "library_adopt", None, added=len(added), renamed=len(renamed), skipped=len(skipped)
        )
        words = rules.migration_words(added, renamed, skipped, project)
        return {"added": added, "renamed": renamed, "skipped": skipped, "words": words}
