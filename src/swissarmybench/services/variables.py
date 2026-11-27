"""The Variables page (domain/variables.py): every variable this computer gives or something reads, where
each comes from and what uses it; add, change, rename and remove this computer's own.

  scope     this computer's, whether or not a project is open, never in a project (the owner, 2026-11-17: the
            library of connections, vaults, APIs and blades is the computer's); two files, the shareable
            one and this computer's local values (adapters/variables.py VariableFiles); a project opened
            or closed changes the connections that read them (rescope: the page told)
  at once   a change is given to this server's environment straight away: a connection's next run, a
            scheduled script and a Workbench kernel started from now on read it; a running kernel keeps the
            environment it started with (the answer counts them: a restart picks the change up)
  secrets   a keyring variable's value goes to this computer's keyring (under its name) and is never
            answered back; Show is the user's (403 for the agent); a vault's value is never read here
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import variable_refs as refs
from swissarmybench.domain import variables as rules
from swissarmybench.domain.blades import Blade, BladeCodeError, detect_settings, env_settings
from swissarmybench.domain.python_connections import TEMPLATE as PYTHON_TEMPLATE
from swissarmybench.domain.python_connections import env_reads
from swissarmybench.services.changes import raised
from swissarmybench.services.workspace import Refused, Workspace

AGENT_REFUSED = (
    "A secret's value is shown to the user only (Show on the Environment's Settings and secrets tab)."
)


def _field_reads(blade: Blade, files: Iterable[tuple[str, str, str]]) -> tuple[str, ...]:
    """The variables a connection's code reads by name besides its passwords and certificate files: a form's
    box of `${NAME}` is written into the code as os.environ["NAME"] (12.7), and that connection uses NAME
    (test app one, 2026-11-22: a folder connection's ${LARKFIELD_DIR} was used by nothing)."""
    others = set(blade.secrets) | {variable for variable, _, _ in files}
    return tuple(dict.fromkeys(r.name for r in env_reads(blade.code) if r.name not in others))


class Kept(Protocol):
    """The shareable file and the local one (adapters/variables.py VariableFiles)."""

    def read(self) -> tuple[Any, Any]: ...

    def write(self, shared: Any, local: Any) -> None: ...


class Secrets(Protocol):
    """This computer's keyring, for the keyring variables (adapters/variables.py)."""

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

    def save(self, data: Any, previous_name: str | None = None) -> Blade: ...

    def file_of(self, name: str) -> Any: ...  # its file (a path), or None


VaultValues = Callable[[dict[str, dict[str, str]]], Awaitable[tuple[dict[str, str], list[str]]]]


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
        vault_values: VaultValues | None = None,
        remembered: Callable[[Blade], dict[str, str]] = lambda blade: {},
        renamed_notes: Callable[[], dict[str, dict[str, tuple[str, str]]]] = lambda: {},
    ) -> None:
        # A vault's variables given a prefixed name (another had the plain one): the plain name and who.
        self._renamed_notes = renamed_notes
        self._vault_values = vault_values
        # A vault that loads every secret: the variables its names last read give (services/vault_names.py).
        self._remembered = remembered
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

    # ===== this computer's own =====

    def _defined(self) -> list[rules.Defined]:
        return rules.read_defined(*self._kept.read())

    def defined_names(self) -> list[str]:
        """The names of this computer's own variables (they keep their names: a vault's taken one is
        prefixed, services/vault_names.py)."""
        try:
            return [d.name for d in self._defined()]
        except Exception:  # a file that cannot be read: no names held back
            return []

    def shareable(self) -> dict[str, str]:
        """The plain values that may be shared (not this computer's only, never a keyring's): Export to Power
        BI writes them as its parameters' values."""
        return {d.name: d.value for d in self._defined() if d.origin == "value" and not d.local}

    def _write(self, defined: list[rules.Defined]) -> None:
        self._kept.write(rules.shared_json(defined), rules.local_json(defined))

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
        """The variables' values given to this server's environment (and so to what it starts)."""
        defined = self._defined()
        keyring = self._keyring([d.name for d in defined if d.origin == "keyring"])
        self._environment.apply(rules.applied(defined, keyring))

    def release(self) -> None:
        """The server stopping: its environment as it was before (no value outlives it)."""
        self._environment.apply({})

    async def rescope(self) -> None:
        """A project opened, made or closed: its connections read variables too (the page told)."""
        self.apply()
        await self.ws.live.broadcast({"type": "variables_changed"})

    # ===== the list =====

    def _facts(self) -> list[rules.ConnectionFacts]:
        out = []
        notes = self._renamed_notes()
        for blade in self._blades.all():
            kind = connection_rules.connection_kind(blade.kind, blade.template)
            if blade.kind == "snippet":
                continue
            read_only = bool(blade.pack or blade.path)
            if blade.kind == "vault":
                out.append(
                    rules.ConnectionFacts(
                        blade.name,
                        vault_mapping=self._remembered(blade) | dict(blade.vault_mapping),
                        vault=True,
                        every=blade.vault_all,
                        read_only=bool(blade.pack),
                        notes=notes.get(blade.name, {}),
                    )
                )
                continue
            if kind is None and not blade.secrets:
                continue
            try:
                status = self._blades.secret_status(blade)
            except Exception:
                status = {}
            python = blade.template == PYTHON_TEMPLATE
            files = tuple((m["variable"], m["setting"], m["default"]) for m in env_settings(blade.code))
            out.append(
                rules.ConnectionFacts(
                    blade.name,
                    secrets=tuple(blade.secrets),
                    saved=frozenset(s for s, ok in status.items() if ok),
                    files=files,
                    reads=tuple(r.name for r in blade.env_reads) if python else _field_reads(blade, files),
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
            for variable in self._remembered(blade) | dict(blade.vault_mapping)
        }

    async def _changed(self, who: str, action: str, name: str, **details: Any) -> None:
        self.apply()
        # The change log (services/changes.py): the variable by name and how it is kept, never its value.
        kept = str(details.get("kept") or "")
        words = {
            "add_variable": f"Added the variable {name}" + (f" ({kept})" if kept else ""),
            "change_variable": f"Changed the variable {name}" + (f" ({kept})" if kept else ""),
            "rename_variable": f"Renamed the variable {name} to {details.get('to')}",
            "remove_variable": f"Removed the variable {name}",
        }.get(action, f"Changed the variable {name}")
        after = None if action == "remove_variable" else {"variable": {"kept": kept or "as it was"}}
        before = None if action == "add_variable" else {"variable": {"name": name}}
        change = raised("variable", str(details.get("to") or name), before, after, words)
        self.ws.audit.write(who, action, name, **details, **change)
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
        self._write(kept)
        await self._changed(who, "change_variable" if was else "add_variable", made.name, kept=made.origin)
        return {"variable": self._one(made.name), "kernels": self._kernels()}

    def taken(self) -> set[str]:
        """Every name a variable has here: this computer's own and the ones a key vault gives."""
        return {d.name for d in self._defined()} | set(self._vault_of())

    async def declare(self, names: list[str], who: str = "user") -> list[str]:
        """Keyring variables named but not set on this computer yet (a found connection's password: Set it
        asks once, never typed by the app). A name already here is left as it is. The names added."""
        defined = self._defined()
        have = {d.name for d in defined} | set(self._vault_of())
        added = [rules.check_name(n) for n in dict.fromkeys(names) if n not in have]
        if not added:
            return []
        if len(defined) + len(added) > rules.MAX_VARIABLES:
            raise rules.VariableError(f"This computer keeps at most {rules.MAX_VARIABLES} variables.")
        self._write([*defined, *(rules.Defined(n, "keyring") for n in added)])
        for name in added:
            self.ws.audit.write(who, "add_variable", name, kept="keyring")
        self.apply()
        await self.ws.live.broadcast({"type": "variables_changed"})
        return added

    def _forget(self, name: str) -> None:
        try:
            self._secrets.delete(name)
        except Exception:  # noqa: S110 (none saved, or no keyring here)
            pass

    async def rename(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name", "to"}: this computer's variable, or a key vault's entry, renamed; each connection that
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
            self._write(defined)
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
                    data["variables"] = [
                        {**v, "name": to} if v["name"] == old else v for v in data["variables"]
                    ]
                    touched = True
            if touched:
                await self._save_blade(data, blade.name, who)
                changed.append(blade.name)
        scripts = self._run_settings.rename_variable(old, to)
        still = [u.to_json() for u in variable.uses if u.kind in ("notebook", "script")]
        await self._changed(who, "rename_variable", old, to=to)
        return {
            "variable": self._one(to),
            "connections": changed,
            "run_settings": scripts,
            "still_reading": still,
            "kernels": self._kernels(),
        }

    async def remove(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"name"}: this computer's variable (its keyring value forgotten), or a key vault's entry (the
        secret stays in the vault). What still reads it is answered."""
        found, _ = self._collect()
        variable = rules.check_remove(found, body)
        if variable.defined is not None:
            self._write(rules.removed(self._defined(), variable.name))
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
            value = (
                variable.value if variable.source == "value" else self._environment.base().get(variable.name)
            )
        else:
            value = None
        if value is None:
            raise rules.VariableError(f"{variable.name} has no value on this computer.")
        self.ws.audit.write(who, "show_variable", variable.name)
        return {"name": variable.name, "value": value}

    # ===== ${NAME} resolved at use (design principle 12.7) =====

    def _sources(self) -> dict[str, rules.Variable]:
        """Where each variable's value comes from here (no document is read for this)."""
        defined = self._defined()
        saved = self._keyring([d.name for d in defined if d.origin == "keyring"])
        found, _ = rules.listing(defined, self._facts(), [], [], self._environment.base(), saved)
        return {v.name: v for v in found}

    def _known(self, name: str, by: Mapping[str, rules.Variable]) -> rules.Variable:
        v = by.get(name)
        if v is not None:
            return v
        here = rules.Variable(name)
        if name in self._environment.base():
            here.source, here.set = "env", True
        return here

    async def values(self, names: Iterable[str]) -> dict[str, str]:
        """The values of these variables on this computer, from their sources (a key vault's read by
        running it); a name not set here is left out. Never answered to a page or the agent."""
        by = self._sources()
        environ = self._environment.base()
        out: dict[str, str] = {}
        wanted: dict[str, dict[str, str]] = {}
        from_vault: set[str] = set()
        for name in dict.fromkeys(names):
            v = self._known(name, by)
            value: str | None = None
            if v.source == "value":
                value = v.value or ""
            elif v.source == "keyring" and v.owner:
                blade = next((b for b in self._blades.all() if b.name == v.owner), None)
                value = self._blades.saved_secrets(blade).get(v.owner_secret or "") if blade else None
            elif v.source == "keyring":
                value = self._keyring([name]).get(name)
            elif v.source == "env":
                value = environ.get(name)
            elif v.source == "vault" and v.vault and v.vault_secret:
                wanted.setdefault(v.vault, {})[name] = v.vault_secret
                from_vault.add(name)
            if value is not None:
                out[name] = value
        if wanted and self._vault_values is not None:
            got, _ = await self._vault_values(wanted)
            out |= {k: value for k, value in got.items() if k in from_vault}
        return out

    def secret_values(self) -> list[str]:
        """Every secret's value this computer keeps (the keyring variables', each connection's saved
        secrets): for masking what the user sends on (a review's selected code). Never answered."""
        found = list(self._keyring([d.name for d in self._defined() if d.origin == "keyring"]).values())
        for blade in self._blades.all():
            try:
                found += self._blades.saved_secrets(blade).values()
            except Exception:  # noqa: S112 (no keyring here: nothing saved)
                continue
        return [value for value in dict.fromkeys(found) if value]

    def unset(self, names: Iterable[str]) -> list[str]:
        """Of these names, those no source on this computer gives (a vault's entry counts as given)."""
        by = self._sources()
        return [n for n in dict.fromkeys(names) if not self._known(n, by).set]

    def check_code(self, code: str, where: str) -> None:
        """A connection's code about to run: each ${NAME} its settings read (with no default) set here, or
        the one error, every missing name in it."""
        try:
            settings = detect_settings(code)
        except BladeCodeError:
            return
        wanted = [r.name for s in settings for r in refs.find(s.text or "") if r.default is None]
        missing = self.unset(wanted) if wanted else []
        if missing:
            raise refs.MissingVariables(missing, where)

    async def resolve(self, text: str, where: str = "") -> str:
        """Typed text with each ${NAME} put in (one pass); MissingVariables for a name not set here."""
        names = refs.names(text)
        found = await self.values(names) if names else {}
        return refs.resolve(text, found.get, where)

    async def resolve_all(self, values: Mapping[str, Any], where: str = "") -> dict[str, Any]:
        names = [n for v in values.values() if isinstance(v, str) for n in refs.names(v)]
        found = await self.values(names) if names else {}
        return refs.resolve_all(values, found.get, where)

    async def bind(
        self, sql: str, dialect: str = "duckdb", style: str = "dollar", where: str = ""
    ) -> tuple[str, Any]:
        """SQL with each ${NAME} outside strings and comments a bound parameter: (sql, params). The params
        are [] (or {}) when it names none."""
        bound = refs.bind_sql(sql, dialect, style)
        if not bound.refs:
            return bound.sql, [] if style not in ("named", "pyformat") else {}
        found = await self.values(r.name for r in bound.refs)
        return bound.sql, bound.params(found.get, where)

    def preview(self, body: Any) -> dict[str, Any]:
        """What a box's text resolves to here: {"text"} -> the value with a secret's part masked (never a
        secret's value: the same rule as Show), the names, those not set (the one error, with Set it), and
        each name's source in words. The agent's too."""
        text = body.get("text") if isinstance(body, dict) else body
        if not isinstance(text, str) or len(text) > rules.MAX_VALUE:
            raise rules.VariableError('Send {"text": "https://${TENANT}.example.com"}.')
        by = self._sources()
        environ = self._environment.base()
        known = {name: self._known(name, by) for name in refs.names(text)}

        def look(name: str) -> str | None:
            v = known[name]
            if not v.set:
                return None
            if v.secret:
                return ""  # set; its value is never read for a preview
            return v.value if v.source == "value" else environ.get(name, "")

        shown = refs.preview(text, look, lambda name: known[name].secret)
        shown["variables"] = [
            {"name": v.name, "from": v.source, "words": rules.SOURCE_WORDS[v.source], "secret": v.secret}
            for v in known.values()
        ]
        return shown

    def sources(self) -> dict[str, tuple[str, list[tuple[str, str | None]]]]:
        """Each variable's source in words and what uses it ((kind name, its document's path)): names only,
        never a value (the project scaffold's README.md Variables list)."""
        found, _ = self._collect()
        out: dict[str, tuple[str, list[tuple[str, str | None]]]] = {}
        for v in found:
            words = rules.SOURCE_WORDS.get(v.source, v.source)
            if v.source == "vault" and v.vault:
                words = f"Key vault {v.vault}"
            out[v.name] = (words, [(f"{u.kind} {u.name}", u.path) for u in v.uses])
        return out

    def uses(self, name: Any = None) -> dict[str, Any]:
        """What reads each variable (connections' fields by setting, notebooks, scripts, Run settings), or
        one variable's."""
        found, _ = self._collect()
        if name not in (None, ""):
            v = rules.find(found, name)
            return {"name": v.name, "uses": [u.to_json() for u in v.uses]}
        return {"uses": {v.name: [u.to_json() for u in v.uses] for v in found if v.uses}}

    # ===== the first start: passwords as variables, and saved text that now names one =====

    def migrate_passwords(self, backup: Callable[[list[Any]], str]) -> str:
        """Each connection's own saved password made a keyring variable of the name the page shows it under
        (its value moved within the keyring, never into a file); the connection's code then asks for that
        variable. `backup` copies the connections' files first and says where. The words to say once ("" when
        nothing moved). Running again finds nothing to move: the library's files stay byte-stable."""
        defined = self._defined()
        moves = rules.password_moves(self._facts(), defined, self._vault_of())
        if not moves:
            return ""
        blades = {b.name: b for b in self._blades.all()}
        files = [p for m in moves if (p := self._blades.file_of(m.connection)) is not None]
        kept = backup(sorted(set(files)))
        done: list[rules.PasswordMove] = []
        for move in moves:
            blade = blades.get(move.connection)
            if blade is None:
                continue
            value = self._blades.saved_secrets(blade).get(move.secret)
            if value is None:
                continue
            try:
                self._secrets.set(move.variable, value)
                code = connection_rules.rename_secret(blade.code, move.secret, move.variable)
            except Exception:  # noqa: S112 (no keyring here, or code that changed: left as it was)
                continue
            data = blade.to_json()
            data["code"] = code
            self._blades.save(data, blade.name)
            defined = [*defined, rules.Defined(move.variable, "keyring")]
            done.append(move)
        if done:
            self._write(defined)
            self.apply()
            for move in done:
                self.ws.audit.write("user", "password_to_variable", move.connection, variable=move.variable)
        return rules.password_move_words(done, kept)

    def holding(self) -> list[dict[str, Any]]:
        """Saved text that now reads as naming a variable (12.7): a connection's or blade's setting whose
        value holds ${NAME}. {"where", "names"}."""
        items: list[tuple[str, str]] = []
        for blade in self._blades.all():
            if blade.pack or blade.path or "${" not in blade.code:
                continue
            try:
                settings = detect_settings(blade.code)
            except BladeCodeError:
                continue
            for s in settings:
                if isinstance(s.value, str) and s.text != s.value and s.text and not refs.find(s.text):
                    items.append((f"{blade.name}: {s.key}", s.value))
        return refs.holding(items)
