"""Set up from the meta store (domain/library_setup.py has the rules): what a new person's computer still
needs before the team's connections work: the key vaults' sign-ins, the values to type once, each
connection's status, the shared projects not set up here.

  check     each vault's names() run in a child process (as the Variables page's list does), a few at once,
            each within settings.setup_vault_seconds: readable or not, and the sign-in that fixes it. Kept
            until Check again (or the meta store folder moves)
  fixes     a value typed once goes through the Variables page (the keyring, or local/variables.toml) and a
            password through the connection's own Set the password: the user's own typing, never the agent's;
            Move to a vault (a keyring password mapped to a vault's secret, so the next person needs nothing)
            is the user's and the agent's alike
  notice    said once when the meta store is pointed at a folder that already holds connections
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import library_setup as rules
from swissarmybench.domain import portability
from swissarmybench.domain import project_explorer as explorer_rules
from swissarmybench.domain.blades import Blade, BladeError
from swissarmybench.domain.connections import connection_kind
from swissarmybench.services.workspace import Workspace


class BladeAccess(Protocol):
    """services/blades.py BladeService."""

    def everything(self) -> list[Blade]: ...

    def get(self, name: str) -> Blade: ...

    def needs_passwords(self, blade: Blade | str, everything: list[Blade] | None = None) -> list[str]: ...

    async def vault_names(self, data: Any) -> dict[str, Any]: ...

    def remembered(self, blade: Blade) -> dict[str, str]: ...

    async def save(self, body: Any, previous: str | None, who: str = "user") -> dict[str, Any]: ...


class Source(Protocol):
    """services/connections.py ConnectionService.source: a password pointed at a vault's entry."""

    async def source(self, body: Any) -> dict[str, Any]: ...


class LibrarySetup:
    def __init__(
        self,
        ws: Workspace,
        blades: BladeAccess,
        secret_status: Callable[[Blade], dict[str, bool]],
        variables: Callable[[], list[dict[str, Any]]],
        sources: Source,
        shared_projects: Callable[[set[str]], Awaitable[list[rules.SharedProject]]] | None = None,
    ) -> None:
        self.ws = ws
        self._blades = blades
        self._secret_status = secret_status
        self._variables = variables
        self._sources = sources
        self.shared_projects = shared_projects
        self._checked: dict[
            str, tuple[bool | None, str, tuple[str, ...]]
        ] = {}  # vault -> readable, error, names

    def _vaults(self, everything: list[Blade]) -> list[Blade]:
        return [b for b in everything if b.kind == "vault"]

    def _connections(self, everything: list[Blade]) -> list[Blade]:
        return [
            b
            for b in everything
            if connection_kind(b.kind, b.template) not in (None, "vault") and not b.web_call and not b.pack
        ]

    async def _check(self, vault: Blade) -> tuple[bool | None, str, tuple[str, ...]]:
        try:
            answer = await asyncio.wait_for(
                self._blades.vault_names({"name": vault.name}), self.ws.settings.setup_vault_seconds
            )
        except TimeoutError:
            return False, "it did not answer in time", ()
        except Exception as error:  # the vault's own failure: its words, first line, short
            return False, (str(error).strip().splitlines() or [type(error).__name__])[0][:300], ()
        names = answer.get("names")
        if names is None:
            return None, "", ()
        return True, "", tuple(str(n.get("env")) for n in names if isinstance(n, dict))

    async def checklist(self, check: bool = False, who: str = "user") -> dict[str, Any]:
        """The checklist ({"check": true}: each vault checked again now)."""
        everything = self._blades.everything()
        vaults = self._vaults(everything)
        wanted = [v for v in vaults if check or v.name not in self._checked]
        found = await asyncio.gather(*(self._check(v) for v in wanted))
        self._checked |= {v.name: f for v, f in zip(wanted, found, strict=True)}
        variables = self._variables()
        vault_rows = []
        unreadable: dict[str, str] = {}  # variable -> its vault, when the vault cannot be read here
        for v in vaults:
            readable, error, listed = self._checked.get(v.name, (None, "", ()))
            given = tuple(sorted(v.vault_mapping)) if v.vault_mapping else listed
            if v.vault_all:  # its names as read now, else as last read on this computer
                given = tuple(sorted({*given, *listed, *self._blades.remembered(v)}))
            if readable is False:
                unreadable |= {name: v.name for name in given}
            vault_rows.append(rules.Vault(v.name, str(v.template or ""), readable, error, given))
        values = [x for x in rules.values_needed(variables) if x.name not in unreadable]
        needing = {x.name for x in values}
        connections = []
        writable = [
            v.name for v in vaults if self._checked.get(v.name, (None,))[0] and not v.pack and not v.vault_all
        ]
        for blade in self._connections(everything):
            try:
                missing = self._blades.needs_passwords(blade, everything)
                status = self._secret_status(blade)
            except Exception:  # a connection whose passwords cannot be told: none said
                missing, status = [], {}
            reads = {*blade.secrets, *blade.env_names, *(r.name for r in blade.env_reads)}
            in_keyring = tuple(s for s, ok in sorted(status.items()) if ok)
            sources = ["keyring" if s in in_keyring else "" for s in blade.secrets]
            local = tuple(portability.as_json(portability.check(blade.code, blade.template, sources)))
            values += [rules.Value(p, "password", blade.name) for p in missing if p not in needing]
            connections.append(
                rules.Connection(
                    blade.name,
                    missing=tuple(missing),
                    vaults=tuple(sorted({unreadable[r] for r in reads if r in unreadable})),
                    values=tuple(sorted(r for r in reads if r in needing)),
                    keyring=in_keyring,
                    local=local,
                    vault_choices=tuple(writable),
                )
            )
        not_working = {c.name.casefold() for c in connections if c.needs()}
        projects = await self.shared_projects(not_working) if self.shared_projects is not None else []
        if check:
            self.ws.audit.write(who, "library_setup_check", None, vaults=len(vaults))
        made = rules.Checklist(vault_rows, values, connections, projects)
        return made.to_json()

    async def move_to_vault(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Move to a vault: {"connection", "secret": its password, "vault", "vault_secret": the secret's
        name in the vault}. The vault gets the entry; the connection's code reads it from there."""
        if not isinstance(body, dict):
            raise ValueError('Send {"connection", "secret", "vault", "vault_secret"}.')
        blade = self._blades.get(str(body.get("connection") or ""))
        secret = str(body.get("secret") or "")
        if secret not in blade.secrets:
            raise BladeError(f"{blade.name} has no password {secret!r}.")
        moved = await self._sources.source(
            {
                "code": blade.code,
                "secret": secret,
                "from": "vault",
                "vault": body.get("vault"),
                "vault_secret": body.get("vault_secret"),
                "env": body.get("env"),
                "connection": blade.name,
            }
        )
        data = blade.to_json() | {"code": moved["code"]}
        data.pop("secrets", None)
        await self._blades.save(data, blade.name, who)
        self.ws.audit.write(who, "library_move_to_vault", blade.name, vault=moved.get("vault"))
        return {"connection": blade.name, "secret": moved["secret"], "vault": moved.get("vault")}

    def forget(self) -> None:
        """The meta store folder moved: every vault is checked again."""
        self._checked.clear()


class SharedProjects:
    """Shared projects (2026-11-18): each one's connections that do not work here (the checklist's), and a
    shared project opened or made whose connections only work on this machine, said once.

    Its ports: the shared projects folder (None: none), where a project folder is ("shared", "local"), the
    projects in a folder (a scan off the loop), the connections a project folder names (services/
    project_scope.py ProjectUse.named_in), this computer's connection names, a blade and its secrets' status,
    and the notice (the library's, said to the pages)."""

    def __init__(
        self,
        shared_folder: Callable[[], str | None],
        where: Callable[[str], str],
        scan: Callable[[str], list[str]],
        named_in: Callable[[str], list[str]],
        here: Callable[[], list[str]],
        blade: Callable[[str], Blade],
        secret_status: Callable[[Blade], dict[str, bool]],
        notice: Callable[[str], Awaitable[None]],
    ) -> None:
        self._shared_folder = shared_folder
        self._where = where
        self._scan = scan
        self._named_in = named_in
        self._here = here
        self._blade = blade
        self._secret_status = secret_status
        self._notice = notice

    async def listing(self, not_working: set[str]) -> list[rules.SharedProject]:
        """Each shared project and the connections it names that do not work here."""
        folder = self._shared_folder()
        if not folder:
            return []
        here = {name.casefold() for name in self._here()}
        out = []
        for path in await asyncio.to_thread(self._scan, folder):
            named = await asyncio.to_thread(self._named_in, path)
            missing = [n for n in named if n.casefold() not in here or n.casefold() in not_working]
            name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            out.append(rules.SharedProject(name, path, tuple(missing)))
        return out

    async def opened(self, folder: str, _extra: Any = None) -> None:
        """A shared project opened (or made): its connections that only work on this machine, said once."""
        if self._where(folder) != "shared":
            return
        local = 0
        for name in await asyncio.to_thread(self._named_in, folder):
            try:
                blade = self._blade(name)
                status = self._secret_status(blade)
            except Exception:  # noqa: S112 (a teammate's connection not here: the checklist says so)
                continue
            sources = ["keyring" if status.get(s) else "" for s in blade.secrets]
            local += bool(portability.check(blade.code, blade.template, sources))
        said = explorer_rules.local_only_words(local)
        if said:
            await self._notice(said)
