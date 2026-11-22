"""Extensions: the Extensions page's cards, Install and Remove (Plans/editions.plan.md; 2026-11-17).

The catalog (domain/extensions.py) with each extension's status: available, installed (found under the
entry-point group at start; Streamlit, preinstalled, is installed by the installers and kept by each update),
coming. Install and Remove
reuse Update to X's machinery (server/updater.py): the helper waits for the app to stop, runs
`uv tool install --force "swissarmybench[server]==<this version>" --with <each kept extension's wheel>`,
checks the version and starts the app; on a failure the old set again and a note. The agent's install and
remove wait for the user's Allow (installing software restarts the app). A development checkout (not a uv
tool) says what to run instead and does nothing.

A folder extension (the library's extensions/<id>/, Plans/folder-extensions.plan.md) changes without a
restart: Install is its missing packages (the one missing-package answer; the agent's on Allow) and Load
again, its routes mounted in the running app; Remove sends its folder to the trash (asked first; the agent's
on Allow); Show its folder is the user's click; New extension writes its folder (the agent's on Allow) and
loads it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import extension_folders as folder_rules
from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import Extension, Found
from swissarmybench.domain.updates import UpdateError
from swissarmybench.services.ports import Approvals, Audit, Notifier
from swissarmybench.services.workspace import Conflict, NotFound, Refused

# Long enough for the answer to reach the asker before the server stops.
STOP_AFTER_SECONDS: float = 0.5


class ExtensionHelper(Protocol):
    """server/updater.py's Helper: whether this copy is a uv tool, and the hand-over for a new set."""

    def installable(self) -> bool: ...

    def launch_change(self, wheels: list[str], before: list[str]) -> None: ...


class Record(Protocol):
    """A small JSON file of the state folder's (adapters/state_files.py JsonFile)."""

    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class Folders(Protocol):
    """The library's folder extensions (adapters/extensions.py FolderExtensions)."""

    def found(self) -> dict[str, Found]: ...

    def shadowed(self) -> dict[str, str]: ...

    def place(self, ident: str) -> str: ...

    def make(self, ident: str, files: dict[str, str]) -> str: ...

    def trash(self, ident: str) -> str: ...

    def show(self, ident: str) -> None: ...

    def reload(self, ident: str) -> None: ...


class _NoFolders:
    """No library: no folder extensions (a test's Extensions of packages only)."""

    def found(self) -> dict[str, Found]:
        return {}

    def shadowed(self) -> dict[str, str]:
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
        found: dict[str, Found],
        helper: ExtensionHelper,
        approvals: Approvals,
        audit: Audit,
        live: Notifier,
        stop: Callable[[], None],
        catalog: tuple[Extension, ...] = rules.CATALOG,
        record: Record | None = None,
        panels: dict[str, str] | None = None,
        folders: Folders | None = None,
        install_packages: InstallPackages = _no_install,
    ) -> None:
        self.current = current
        self.catalog = catalog
        self.found = dict(found)
        self._helper = helper
        self._approvals = approvals
        self._audit = audit
        self._live = live
        self._stop = stop
        self._changing: dict[str, str] | None = None
        # extensions.json: the preinstalled ones the user removed (never brought back) and the bring-backs
        # tried, by version (never twice).
        self._record = record
        # Each on extension's panel (its PANEL route): the card and Settings draw what it answers.
        self.panels = dict(panels or {})
        # The library's folder extensions (read live: New extension, Remove and Load again change them), their
        # packages installed into the app's Python, and their routes mounted and unmounted in the running app
        # (server/app.py sets mount and unmount: mount answers the error of a routes() that failed, or "").
        self._folders: Folders = folders or _NoFolders()
        self._install_packages = install_packages
        self.mount: Callable[[str], str] = lambda _ident: ""
        self.unmount: Callable[[str], None] = lambda _ident: None

    # ===== reading =====

    def listing(self) -> list[dict[str, Any]]:
        found = self._folders.found() | self.found  # a package wins over a folder of its id
        listed = rules.listed(self.catalog, found, self.current)
        shadowed = self._folders.shadowed()
        for entry in listed:
            if entry["id"] in self.panels:
                entry["panel"] = self.panels[entry["id"]]
            if entry["id"] in shadowed:
                entry["note"] = shadowed[entry["id"]]
        return listed

    def _folder(self, body: Any) -> dict[str, Any] | None:
        """The listing's entry of the folder extension the body names, or None (it is a package's)."""
        ident = rules.check_id(body.get("id") if isinstance(body, dict) else None)
        entry = next((e for e in self.listing() if e["id"] == ident), None)
        return entry if entry is not None and entry.get("source") == "folder" else None

    def state(self) -> dict[str, Any]:
        return {
            "extensions": self.listing(),
            "installable": self._helper.installable(),
            "changing": self._changing,
        }

    def changing(self) -> dict[str, str] | None:
        """An Install or Remove handed to the helper (the app stops for it): what it is, else None."""
        return self._changing

    def names(self) -> list[str]:
        """The extensions this install has, by name (the version mark's tooltip)."""
        return [str(e["name"]) for e in self.listing() if e["status"] in ("preinstalled", "installed")]

    def installed_ids(self) -> list[str]:
        """The extensions installed as packages of the catalog's (the ones each update keeps, `--with`)."""
        ours = {e.id for e in self.catalog if e.package}
        return [str(e["id"]) for e in self.listing() if e["status"] == "installed" and e["id"] in ours]

    def kept_wheels(self, version: str) -> list[str]:
        """Each installed extension's wheel at `version`: what an update of the base installs with it."""
        return rules.kept_wheels(self.catalog, self.installed_ids(), version)

    def _entry(self, body: Any) -> tuple[Extension, dict[str, Any]]:
        ident = rules.check_id(body.get("id") if isinstance(body, dict) else None)
        listed = {e["id"]: e for e in self.listing()}
        if ident not in listed:
            raise NotFound(f"There is no extension {ident!r}.")
        known = next((e for e in self.catalog if e.id == ident), None)
        said = listed[ident]
        ext = known or Extension(
            ident, str(said["name"]), str(said["description"]), package=str(said["package"])
        )
        return ext, said

    # ===== Install and Remove =====

    async def install(self, body: Any, who: str) -> dict[str, Any]:
        folder = self._folder(body)
        if folder is not None:
            return await self._load_folder(folder, who)
        ext, said = self._entry(body)
        status = said["status"]
        if status == "installed":
            raise Conflict(f"{ext.name} is installed already.")
        if status == "coming":
            raise Conflict(f"{ext.name} is coming: it cannot be installed yet.")
        before = self.installed_ids()
        answer = await self._change(ext, "install", [*before, ext.id], before, who, body)
        self._note(installed=ext.id)
        return answer

    async def remove(self, body: Any, who: str) -> dict[str, Any]:
        folder = self._folder(body)
        if folder is not None:
            return await self._remove_folder(folder, body, who)
        ext, said = self._entry(body)
        if said["status"] != "installed":
            raise Conflict(f"{ext.name} is not installed.")
        before = self.installed_ids()
        if ext.id not in before:
            raise Conflict(
                f"{ext.name} was not installed from here: remove its package the way it was installed."
            )
        answer = await self._change(ext, "remove", [i for i in before if i != ext.id], before, who, body)
        if "changing" in answer:
            self._note(removed=ext.id)  # a preinstalled one stays out of every bring-back
        return answer

    def _note(self, **change: Any) -> None:
        if self._record is not None:
            self._record.write(rules.recorded(self._record.read(), **change))

    def bring_back(self) -> dict[str, Any] | None:
        """At start: a preinstalled extension this install lacks (an update from a version that had it built
        in), never removed by the user, is installed once (the app restarts with it). A copy that is not an
        installed tool, or one tried at this version already, does nothing."""
        if self._changing or self._record is None or not self._helper.installable():
            return None
        wanted = rules.to_bring_back(self.catalog, self.found, self._record.read(), self.current)
        if not wanted:
            return None
        for ext in wanted:
            self._note(tried=(ext.id, self.current))
        before = self.installed_ids()
        after = [*before, *(e.id for e in wanted)]
        try:
            self._helper.launch_change(
                rules.kept_wheels(self.catalog, after, self.current),
                rules.kept_wheels(self.catalog, before, self.current),
            )
        except UpdateError:
            return None
        self._changing = {"id": wanted[0].id, "action": "install"}
        self._audit.write("app", "extension_install", None, extension=wanted[0].id, version=self.current)
        asyncio.get_running_loop().call_later(STOP_AFTER_SECONDS, self._stop)
        return self._changing

    async def _change(
        self, ext: Extension, action: str, after: list[str], before: list[str], who: str, body: Any
    ) -> dict[str, Any]:
        if self._changing:
            raise Conflict("An extension is being installed or removed already.")
        if not self._helper.installable():
            raise Conflict(rules.development_words(ext))
        question = rules.change_question("installs" if action == "install" else "removes", ext.name)
        if (
            who != "agent"
            and action == "remove"
            and not (isinstance(body, dict) and body.get("confirmed") is True)
        ):
            return {"confirm": question, "id": ext.id}
        await self._approvals.allowed(
            who,
            subject=ext.id,
            action=f"{action} the extension",
            detail=question,
            otherwise=f"{ext.name} was not {'installed' if action == 'install' else 'removed'}",
        )
        try:
            self._helper.launch_change(
                rules.kept_wheels(self.catalog, after, self.current),
                rules.kept_wheels(self.catalog, before, self.current),
            )
        except UpdateError as error:
            raise Conflict(str(error)) from None
        self._changing = {"id": ext.id, "action": action}
        self._audit.write(who, f"extension_{action}", None, extension=ext.id, version=self.current)
        await self._live.broadcast({"type": "extensions_changing", **self._changing})
        asyncio.get_running_loop().call_later(STOP_AFTER_SECONDS, self._stop)
        return {"changing": self._changing}

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
        entry = self._folder(body)
        if entry is None:
            raise NotFound("Only a folder extension has a folder to show.")
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
        taken = {e.id for e in self.catalog} | {str(e["id"]) for e in self.listing()}
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
