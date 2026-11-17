"""Extensions: the Extensions page's cards, Install and Remove (Plans/editions.plan.md; 2026-11-17).

The catalog (domain/extensions.py) with each extension's status: preinstalled (Streamlit comes with every
install), available, installed (found under the entry-point group at start), coming. Install and Remove
reuse Update to X's machinery (server/updater.py): the helper waits for the app to stop, runs
`uv tool install --force "swissarmybench[server]==<this version>" --with <each kept extension's wheel>`,
checks the version and starts the app; on a failure the old set again and a note. The agent's install and
remove wait for the user's Allow (installing software restarts the app). A development checkout (not a uv
tool) says what to run instead and does nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import Extension, Found
from swissarmybench.domain.updates import UpdateError
from swissarmybench.services.agent import Approvals
from swissarmybench.services.ports import Audit, Notifier
from swissarmybench.services.workspace import Conflict, NotFound, Refused

# Long enough for the answer to reach the asker before the server stops.
STOP_AFTER_SECONDS: float = 0.5


class ExtensionHelper(Protocol):
    """server/updater.py's Helper: whether this copy is a uv tool, and the hand-over for a new set."""

    def installable(self) -> bool: ...

    def launch_change(self, wheels: list[str], before: list[str]) -> None: ...


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

    # ===== reading =====

    def listing(self) -> list[dict[str, Any]]:
        return rules.listed(self.catalog, self.found, self.current)

    def state(self) -> dict[str, Any]:
        return {
            "extensions": self.listing(),
            "installable": self._helper.installable(),
            "changing": self._changing,
        }

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
        ext, said = self._entry(body)
        status = said["status"]
        if status == "preinstalled":
            raise Conflict(f"{ext.name} comes with every install.")
        if status == "installed":
            raise Conflict(f"{ext.name} is installed already.")
        if status == "coming":
            raise Conflict(f"{ext.name} is coming: it cannot be installed yet.")
        before = self.installed_ids()
        return await self._change(ext, "install", [*before, ext.id], before, who, body)

    async def remove(self, body: Any, who: str) -> dict[str, Any]:
        ext, said = self._entry(body)
        if said["status"] == "preinstalled":
            raise Conflict(f"{ext.name} comes with every install: it cannot be removed yet.")
        if said["status"] != "installed":
            raise Conflict(f"{ext.name} is not installed.")
        before = self.installed_ids()
        if ext.id not in before:
            raise Conflict(
                f"{ext.name} was not installed from here: remove its package the way it was installed."
            )
        return await self._change(ext, "remove", [i for i in before if i != ext.id], before, who, body)

    async def _change(
        self, ext: Extension, action: str, after: list[str], before: list[str], who: str, body: Any
    ) -> dict[str, Any]:
        if self._changing:
            raise Conflict("An extension is being installed or removed already.")
        if not self._helper.installable():
            raise Conflict(rules.development_words(ext))
        question = rules.change_question("installs" if action == "install" else "removes", ext.name)
        if who == "agent":
            if not await self._approvals.ask(ext.id, f"{action} the extension", question):
                done = "installed" if action == "install" else "removed"
                raise Refused(f"The user declined (or did not answer): {ext.name} was not {done}.")
        elif action == "remove" and not (isinstance(body, dict) and body.get("confirmed") is True):
            return {"confirm": question, "id": ext.id}
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
