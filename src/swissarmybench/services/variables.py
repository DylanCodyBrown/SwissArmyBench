"""The Variables page (domain/variables.py): every variable the project gives or something reads, where each
comes from and what uses it; add, change, rename and remove the project's own.

  scope     the open project's variables (its working folder's .sab/variables/variables.json, so they go
            into its .sab), else this computer's (the state folder's variables.json); each open, new and
            close points the file at the project (rescope) and gives its values to the server's processes
  at once   a change is given to this server's environment straight away: a connection's next run, a
            scheduled script and a Workbench kernel started from now on read it; a running kernel keeps the
            environment it started with (the answer counts them: a restart picks the change up)
  secrets   a keyring variable's value goes to this computer's keyring (under its name) and is never
            answered back; Show is the user's (403 for the agent); a vault's value is never read here
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import variables as rules
from swissarmybench.domain.blades import Blade, env_settings
from swissarmybench.domain.python_connections import TEMPLATE as PYTHON_TEMPLATE
from swissarmybench.services.workspace import Refused, Workspace

AGENT_REFUSED = "A secret's value is shown to the user only (Show on the Variables page)."


class Kept(Protocol):
    """The variables file (adapters/state_files.py JsonFile)."""

    def read(self) -> Any: ...

    def write(self, data: Any) -> None: ...


class Secrets(Protocol):
    """This computer's keyring, for the project's keyring variables (adapters/variables.py)."""

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class Environment(Protocol):
    """The server's own environment, which every process it starts inherits (adapters/variables.py)."""

    def base(self) -> Mapping[str, str]: ...

    def apply(self, values: Mapping[str, str]) -> None: ...


class Blades(Protocol):
    def all(self) -> list[Blade]: ...

    def secret_status(self, name: str | Blade) -> dict[str, bool]: ...

    def saved_secrets(self, blade: Blade) -> dict[str, str]: ...


class RunSettings(Protocol):
    def every(self) -> dict[str, dict[str, dict[str, str]]]: ...  # script -> variable -> source

    def rename_variable(self, old: str, new: str) -> list[str]: ...


SaveBlade = Callable[[dict[str, Any], str, str], Awaitable[Any]]


class Variables:
    def __init__(
        self,
        ws: Workspace,
        kept: Kept,
        secrets: Secrets,
        environment: Environment,
        blades: Blades,
        save_blade: SaveBlade,
        documents: Callable[[], list[str]],
        read: Callable[[str], tuple[str, str, float]],
        run_settings: RunSettings,
        kernels: Callable[[], int] = lambda: 0,
        project: Callable[[], str | None] = lambda: None,
    ) -> None:
        self.ws = ws
        self._kept = kept
        self._secrets = secrets
        self._environment = environment
        self._blades = blades
        self._save_blade = save_blade
        self._documents = documents
        self._read = read
        self._run_settings = run_settings
        self._kernels = kernels
        self._project = project

    # ===== the project's own =====

    def _defined(self) -> list[rules.Defined]:
        return rules.read_defined(self._kept.read())

    def _keyring(self, names: list[str]) -> dict[str, str]:
        """The keyring variables' values found on this computer (none when it has no keyring)."""
        found: dict[str, str] = {}
        for name in names:
            try:
                value = self._secrets.get(name)
            except Exception:  # noqa: S112 (no keyring here: nothing saved)
                continue
            if value is not None:
                found[name] = value
        return found

    def apply(self) -> None:
        """The project's values given to this server's environment (and so to what it starts)."""
        defined = self._defined()
        keyring = self._keyring([d.name for d in defined if d.origin == "keyring"])
        self._environment.apply(rules.applied(defined, keyring))

    async def rescope(self) -> None:
        """The project opened, made or closed: its variables now (the file already points at it)."""
        self.apply()
        await self.ws.live.broadcast({"type": "variables_changed"})

    # ===== the list =====

    def _facts(self) -> list[rules.ConnectionFacts]:
        out = []
        for blade in self._blades.all():
            kind = connection_rules.connection_kind(blade.kind, blade.template)
            if blade.kind == "snippet":
                continue
            read_only = bool(blade.pack or blade.path)
            if blade.kind == "vault":
                out.append(
                    rules.ConnectionFacts(
                        blade.name,
                        vault_mapping=dict(blade.vault_mapping),
                        vault=True,
                        every=blade.vault_all,
                        read_only=bool(blade.pack),
                    )
                )
                continue
            if kind is None and not blade.secrets:
                continue
            try:
                status = self._blades.secret_status(blade)
            except Exception:  # noqa: BLE001 (no keyring here: nothing saved)
                status = {}
            python = blade.template == PYTHON_TEMPLATE
            out.append(
                rules.ConnectionFacts(
                    blade.name,
                    secrets=tuple(blade.secrets),
                    saved=frozenset(s for s, ok in status.items() if ok),
                    files=tuple((m["variable"], m["setting"], m["default"]) for m in env_settings(blade.code)),
                    reads=tuple(r.name for r in blade.env_reads) if python else (),
                    sources=dict(blade.variables),
                    read_only=read_only,
                )
            )
        return out

    def _document_uses(self) -> list[dict[str, list[rules.Use]]]:
        found = []
        for path in self._documents():
            try:
                text, full, _ = self._read(path)
            except (OSError, ValueError):
                continue
            title = full.replace("\\", "/").rsplit("/", 1)[-1]
            found.append(rules.document_uses(full, title, text))
        return found

    def _collect(self) -> tuple[list[rules.Variable], list[str]]:
        defined = self._defined()
        saved = self._keyring([d.name for d in defined if d.origin == "keyring"])
        runs = [
            rules.run_settings_uses(path, path.replace("\\", "/").rsplit("/", 1)[-1], variables)
            for path, variables in self._run_settings.every().items()
        ]
        return rules.listing(
            defined, self._facts(), self._document_uses(), runs, self._environment.base(), saved
        )

    def listing(self, search: Any = None, source: Any = None) -> dict[str, Any]:
        """Every variable (names, sources, uses; a plain value's value, never a secret's), the vaults that
        load every secret they hold, whose list it is, and the kernels running."""
        found, every = self._collect()
        environ = self._environment.base()
        return {
            "variables": rules.shown(found, environ, search, source),
            "every_vault": every,
            "project": self._project(),
            "kernels": self._kernels(),
        }

    def _one(self, name: str) -> dict[str, Any]:
        found, _ = self._collect()
        return rules.find(found, name).to_json(self._environment.base())

    def _vault_of(self) -> dict[str, str]:
        return {
            variable: blade.name
            for blade in self._blades.all()
            if blade.kind == "vault"
            for variable in blade.vault_mapping
        }

    async def _changed(self, who: str, action: str, name: str, **details: Any) -> None:
        self.apply()
        self.ws.audit.write(who, action, name, **details)
        await self.ws.live.broadcast({"type": "variables_changed"})

    # ===== add, change, rename, remove =====

    async def put(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Add a variable or change one: {"name", "value", "from": "value" | "keyring"}. A keyring value is
        saved on this computer and never answered back (the agent may set one, never read it)."""
        defined = self._defined()
        kept, made, secret = rules.put(defined, body, self._vault_of())
        was = next((d for d in defined if d.name == made.name), None)
        if secret is not None:
            try:
                self._secrets.set(made.name, secret)
            except Exception as error:
                raise rules.VariableError(f"This computer's keyring did not keep it: {error}") from None
        if made.origin == "value" and was is not None and was.origin == "keyring":
            self._forget(made.name)
        self._kept.write(rules.defined_json(kept))
        await self._changed(who, "change_variable" if was else "add_variable", made.name, kept=made.origin)
        return {"variable": self._one(made.name), "kernels": self._kernels()}

    def _forget(self, name: str) -> None:
        try:
            self._secrets.delete(name)
        except Exception:  # noqa: S110 (none saved, or no keyring here)
            pass

    async def rename(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "to"}: the project's variable, or a key vault's entry, renamed; each connection that
        reads it changed to the new name (its code, a Python connection's mapping) and each script's Run
        settings; the notebooks and scripts that still read the old name listed (never edited here)."""
        found, _ = self._collect()
        variable, to = rules.check_rename(found, body)
        old = variable.name
        if variable.defined is not None:
            defined = rules.renamed(self._defined(), old, to)
            if variable.defined.origin == "keyring":
                value = self._keyring([old]).get(old)
                if value is not None:
                    self._secrets.set(to, value)
                    self._forget(old)
            self._kept.write(rules.defined_json(defined))
        changed: list[str] = []
        for blade in self._blades.all():
            if blade.pack or blade.kind == "snippet":
                continue
            data = blade.to_json()
            touched = False
            if blade.kind == "vault":
                mapping = data["vault_mapping"]
                if variable.source == "vault" and blade.name == variable.vault and old in blade.vault_mapping:
                    data["vault_mapping"] = [{**m, "env": to} if m["env"] == old else m for m in mapping]
                    touched = True
            else:
                for key in ("code",):
                    data[key], n = rules.rename_in_code(str(data[key] or ""), old, to)
                    touched = touched or n > 0
                for part in ("catalog", "read"):
                    if isinstance(data.get(part), dict) and isinstance(data[part].get("command"), str):
                        data[part]["command"], n = rules.rename_in_code(data[part]["command"], old, to)
                        touched = touched or n > 0
                if old in blade.variables:
                    data["variables"] = [{**v, "name": to} if v["name"] == old else v for v in data["variables"]]
                    touched = True
            if touched:
                await self._save_blade(data, blade.name, who)
                changed.append(blade.name)
        scripts = self._run_settings.rename_variable(old, to)
        still = [
            u.to_json()
            for u in variable.uses
            if u.kind in ("notebook", "script")
        ]
        await self._changed(who, "rename_variable", old, to=to)
        return {
            "variable": self._one(to),
            "connections": changed,
            "run_settings": scripts,
            "still_reading": still,
            "kernels": self._kernels(),
        }

    async def remove(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name"}: the project's variable (its keyring value forgotten), or a key vault's entry (the
        secret stays in the vault). What still reads it is answered."""
        found, _ = self._collect()
        variable = rules.check_remove(found, body)
        if variable.defined is not None:
            self._kept.write(rules.defined_json(rules.removed(self._defined(), variable.name)))
            if variable.defined.origin == "keyring":
                self._forget(variable.name)
        else:
            blade = next(b for b in self._blades.all() if b.name == variable.vault)
            data = blade.to_json()
            data["vault_mapping"] = [m for m in data["vault_mapping"] if m["env"] != variable.name]
            await self._save_blade(data, blade.name, who)
        await self._changed(who, "remove_variable", variable.name)
        return {"removed": variable.name, "uses": [u.to_json() for u in variable.uses]}

    def reveal(self, body: Any, who: str) -> dict[str, Any]:
        """Show: a keyring variable's value, or a secret this computer's environment holds; the user's
        click only (403 for the agent). A vault's value is never read here."""
        if who == "agent":
            raise Refused(AGENT_REFUSED)
        name = body.get("name") if isinstance(body, dict) else None
        found, _ = self._collect()
        variable = rules.find(found, name)
        if variable.source == "vault":
            raise rules.VariableError(
                f"{variable.name} comes from {variable.vault}: its value stays in the vault."
            )
        if variable.source == "keyring" and variable.owner:
            blade = next((b for b in self._blades.all() if b.name == variable.owner), None)
            value = self._blades.saved_secrets(blade).get(variable.owner_secret or "") if blade else None
        elif variable.source == "keyring":
            value = self._keyring([variable.name]).get(variable.name)
        elif variable.source in ("env", "value"):
            value = variable.value if variable.source == "value" else self._environment.base().get(variable.name)
        else:
            value = None
        if value is None:
            raise rules.VariableError(f"{variable.name} has no value on this computer.")
        self.ws.audit.write(who, "show_variable", variable.name)
        return {"name": variable.name, "value": value}
