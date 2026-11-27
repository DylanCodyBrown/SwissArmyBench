"""Extensions: the Extensions page's cards (Plans/folder-extensions.plan.md; the owner, 2026-11-27: every
packaged extension built in, with no Install and no Remove).

The page lists the user's own folder extensions (the library's extensions/<id>/) and each built-in feature
that brings a panel of its own. A built-in feature is never installed or removed: asked to, the answer is
one sentence (domain/extensions.py built_in_words).

A folder extension changes without a restart: Install is its missing packages (the one missing-package
answer; the agent's on Allow) and Load again, its routes mounted in the running app; Remove sends its folder
to the trash (asked first; the agent's on Allow); Show its folder is the user's click; New extension writes
its folder (the agent's on Allow) and loads it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import extension_folders as folder_rules
from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import BuiltIn, Found
from swissarmybench.services.ports import Approvals, Audit, Notifier
from swissarmybench.services.workspace import Conflict, NotFound, Refused


class Folders(Protocol):
    """The library's folder extensions (adapters/extensions.py FolderExtensions)."""

    def found(self) -> dict[str, Found]: ...

    def place(self, ident: str) -> str: ...

    def make(self, ident: str, files: dict[str, str]) -> str: ...

    def trash(self, ident: str) -> str: ...

    def show(self, ident: str) -> None: ...

    def reload(self, ident: str) -> None: ...


class _NoFolders:
    """No library: no folder extensions."""

    def found(self) -> dict[str, Found]:
        return {}

    def place(self, ident: str) -> str:
        return ident

    def make(self, ident: str, files: dict[str, str]) -> str:
        raise FileNotFoundError("There is no library here.")

    def trash(self, ident: str) -> str:
        raise FileNotFoundError(ident)

    def show(self, ident: str) -> None:
        raise FileNotFoundError(ident)

    def reload(self, ident: str) -> None:
        return None


# Packages into the app's own Python (services/blades.py install): whether it worked, and what to show.
InstallPackages = Callable[[list[str]], Awaitable[tuple[bool, dict[str, Any]]]]


async def _no_install(packages: list[str]) -> tuple[bool, dict[str, Any]]:
    return False, {"ok": False, "output": "Installing packages is not possible here."}


class Extensions:
    def __init__(
        self,
        *,
        current: str,
        approvals: Approvals,
        audit: Audit,
        live: Notifier,
        built_in: tuple[BuiltIn, ...] = (),
        folders: Folders | None = None,
        install_packages: InstallPackages = _no_install,
    ) -> None:
        self.current = current
        # The built-in features (their ids and names; a panel's route where one has a card).
        self.built_in = built_in
        self._approvals = approvals
        self._audit = audit
        self._live = live
        # The library's folder extensions (read live: New extension, Remove and Load again change them), their
        # packages installed into the app's Python, and their routes mounted and unmounted in the running app
        # (server/app.py sets mount and unmount: mount answers the error of a routes() that failed, or "").
        self._folders: Folders = folders or _NoFolders()
        self._install_packages = install_packages
        self.mount: Callable[[str], str] = lambda _ident: ""
        self.unmount: Callable[[str], None] = lambda _ident: None

    # ===== reading =====

    def listing(self) -> list[dict[str, Any]]:
        return rules.listed(self.built_in, self._folders.found(), self.current)

    def _folder(self, body: Any, action: str) -> dict[str, Any]:
        """The listing's entry of the folder extension the body names. A built-in feature's id is refused in
        one sentence: there is nothing of it to install or remove."""
        ident = rules.check_id(body.get("id") if isinstance(body, dict) else None)
        entry = next((e for e in self.listing() if e["id"] == ident and e.get("source") == "folder"), None)
        if entry is not None:
            return entry
        feature = next((f for f in self.built_in if f.id == ident), None)
        if feature is not None and action != "show":
            raise Conflict(rules.built_in_words(feature.name or ident, action))
        if action == "show":
            raise NotFound("Only a folder extension has a folder to show.")
        raise NotFound(f"There is no extension {ident!r}.")

    def state(self) -> dict[str, Any]:
        return {"extensions": self.listing()}

    def names(self) -> list[str]:
        """The folder extensions that are on, by name (the version mark's tooltip)."""
        return [str(e["name"]) for e in self.listing() if e.get("source") == "folder" and e.get("on")]

    # ===== Install and Remove: a folder extension's only =====

    async def install(self, body: Any, who: str) -> dict[str, Any]:
        return await self._load_folder(self._folder(body, "install"), who)

    async def remove(self, body: Any, who: str) -> dict[str, Any]:
        return await self._remove_folder(self._folder(body, "remove"), body, who)

    # ===== folder extensions: the library's extensions/<id>/ (no restart) =====

    async def _load_folder(self, entry: dict[str, Any], who: str) -> dict[str, Any]:
        """Install, for a folder: its missing packages into the app's Python (the agent's on Allow; the user's
        Install now is their click), then it is read again from its folder and its routes mounted (Load
        again)."""
        ident, name = str(entry["id"]), str(entry["name"])
        missing = entry.get("missing")
        if missing:
            packages = [str(p) for p in missing["packages"]]
            await self._approvals.allowed(
                who,
                subject=ident,
                action="install the extension's packages",
                detail=f"Install {', '.join(packages)} into Swiss Army Bench's own Python, for {name}.",
                otherwise=f"{', '.join(packages)} not installed",
            )
            worked, shown = await self._install_packages(packages)
            if not worked:
                raise Conflict(
                    f"{', '.join(packages)} did not install: {shown.get('output') or 'see the log.'}"
                )
        self.unmount(ident)
        self._folders.reload(ident)
        loaded = next((e for e in self.listing() if e["id"] == ident), entry)
        if loaded.get("on"):
            failed = self.mount(ident)
            if failed:
                loaded = loaded | {"on": False, "error": failed}
        self._audit.write(who, "extension_load", None, extension=ident)
        await self._live.broadcast({"type": "extensions_changed", "id": ident})
        return {"loaded": loaded}

    async def _remove_folder(self, entry: dict[str, Any], body: Any, who: str) -> dict[str, Any]:
        """Remove, for a folder: its folder to the system's trash and its routes unmounted at once. The user's
        asks first (confirmed); the agent's waits for the user's Allow."""
        ident, name = str(entry["id"]), str(entry["name"])
        question = folder_rules.remove_question(name, str(entry["path"]))
        if who != "agent" and not (isinstance(body, dict) and body.get("confirmed") is True):
            return {"confirm": question, "id": ident}
        await self._approvals.allowed(
            who,
            subject=ident,
            action="remove the extension",
            detail=question,
            otherwise=f"{name} was not removed",
        )
        self.unmount(ident)
        try:
            went = self._folders.trash(ident)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except OSError as error:
            raise Conflict(f"{name}'s folder could not go to the trash: {error}") from None
        self._audit.write(who, "extension_remove", None, extension=ident, source="folder")
        await self._live.broadcast({"type": "extensions_changed", "id": ident})
        return {"removed": ident, "trash": went}

    def show(self, body: Any, who: str) -> dict[str, Any]:
        """Show its folder in the system's file manager: the user's click only."""
        if who == "agent":
            raise Refused("Show its folder opens the user's own file manager: only the user can.")
        entry = self._folder(body, "show")
        try:
            self._folders.show(str(entry["id"]))
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        return {"shown": entry["path"]}

    async def new(self, body: Any, who: str) -> dict[str, Any]:
        """New extension: {"id", "name"?, "project_type"?}: the library's extensions/<id>/ with one route, one
        command and (with a project type) contract.json, then loaded and its routes mounted. The agent's waits
        for the user's Allow (its code runs in the app's server)."""
        if not isinstance(body, dict):
            raise ValueError('Send {"id": "inventory", "name": "Inventory", "project_type"?: "inventory"}.')
        taken = {f.id for f in self.built_in} | {str(e["id"]) for e in self.listing()}
        raw_name = body.get("name")
        try:
            ident = folder_rules.check_id(body.get("id"), taken)
            name = (
                raw_name.strip()
                if isinstance(raw_name, str) and raw_name.strip()
                else ident.replace("_", " ").title()
            )
            files = folder_rules.scaffold(ident, name, body.get("project_type") or None)
        except ValueError as error:  # FolderError, ContractError
            raise ValueError(str(error)) from None
        listed = "\n".join(f"  {n}" for n in files)
        await self._approvals.allowed(
            who,
            subject=ident,
            action="make the extension",
            detail=f"A new folder extension, {name}, in the library:\n"
            f"  {self._folders.place(ident)}\n{listed}",
            otherwise=f"the extension {ident} was not made",
        )
        try:
            made = self._folders.make(ident, files)
        except FileExistsError as error:
            raise Conflict(str(error)) from None
        self._audit.write(who, "extension_new", None, extension=ident)
        answer = await self._load_folder({"id": ident, "name": name}, who)
        return {"made": made, "files": sorted(files), "extension": answer["loaded"]}
