"""The Variables page (the owner, 2026-11-16: "after Imported my keyvault and it made a ton on local
vairables, that we actually need a workspace Variable page for the rail to help manage project
variables"; "should be able to add new local env variables from the page easily and browse what is there
and for variables that are not from the key vault you can see their current values"). This computer's,
whether or not a project is open (the owner, 2026-11-17: connections, vaults, APIs and blades are this
computer's library, projects name them), and never in a project.

  defined   this computer's own variables: a name and where its value is kept, `value` (a plain value)
            or `keyring` (this computer's keyring, under the name)
  shared    what could be shared with other users (Plans/library.plan.md: the library's variables.toml):
            each variable's name and source, and a plain value's value unless it is "this computer only";
            never a secret's value
  local     this computer only: the values of the plain variables marked so (a local path, a machine's
            own setting); the keyring's values are not here either, they stay in the keyring
  sources   where a variable's value comes from, the first that has it: a key vault's secret (the vault
            and the secret's name, never its value), this computer's own definition, a connection that
            keeps it (its keyring, a Python connection's plain value), this computer's environment; else
            missing
  uses      what reads it: connections (a password, a certificate or keystore file, a Python connection's
            code), notebooks and scripts (`os.environ[...]`, `.get`, `getenv`, `secret(...)`, read with
            ast), scripts' Run settings
  values    in plain sight for a plain value and this computer's environment when nothing reads it as a
            secret; a keyring's value (and a secret from the environment) only behind Show, for the user;
            a vault's never
  rename    a connection's code (`secret("OLD")`, `os.environ.get("OLD", ...)`) changed by rule; the
            notebooks and scripts that read it are listed, never edited behind the user's back

Pure rules: no I/O, no clock.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import notebooks, table_cells
from swissarmybench.domain.connections import env_name_for
from swissarmybench.domain.python_connections import env_reads, looks_secret
from swissarmybench.domain.script_runs import source_words

FORMAT: int = 1
ORIGINS: tuple[str, ...] = ("value", "keyring")  # where this computer keeps one of its own
SOURCES: tuple[str, ...] = ("vault", "value", "keyring", "env", "missing")
SOURCE_WORDS: dict[str, str] = {
    "vault": "Key vault",
    "value": "Plain value",
    "keyring": "This computer's keyring",
    "env": "This computer's environment",
    "missing": "Not set",
}
MAX_VARIABLES: int = 500
MAX_VALUE: int = 10_000
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class VariableError(ValueError):
    """A variable that cannot be added, changed, renamed or removed as asked (why, in words)."""


# ===== this computer's own variables =====


@dataclass(frozen=True)
class Defined:
    name: str
    origin: str  # value or keyring
    value: str = ""  # a plain value's (a keyring's is never here)
    local: bool = False  # a plain value kept on this computer only (never shared)

    def shared_json(self) -> dict[str, str]:
        """What may be shared: the name and the source; a plain value's value unless it is local."""
        out = {"name": self.name, "from": self.origin}
        if self.origin == "value":
            out |= {"local": "yes"} if self.local else {"value": self.value}
        return out


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not _NAME.match(name.strip()):
        raise VariableError(
            "A variable's name is letters, digits and _, not starting with a digit (SALES_REGION)."
        )
    return name.strip()


def check_value(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_VALUE or "\x00" in value:
        raise VariableError(f"{name}'s value is text (at most {MAX_VALUE:,} characters).")
    return value


def read_defined(shared: Any, local: Any = None) -> list[Defined]:
    """The shared file and this computer's local values, as kept: anything unreadable is left out (never
    a reason not to start). A local variable with no value on this computer reads as an empty value."""
    rows = shared.get("variables") if isinstance(shared, dict) else None
    here = local.get("values") if isinstance(local, dict) else None
    here = here if isinstance(here, dict) else {}
    found: dict[str, Defined] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name, origin = row.get("name"), row.get("from")
        if not isinstance(name, str) or not _NAME.match(name) or origin not in ORIGINS or name in found:
            continue
        is_local = origin == "value" and row.get("local") in ("yes", True)
        value = (here.get(name, "") if is_local else row.get("value", "")) if origin == "value" else ""
        if not isinstance(value, str) or len(value) > MAX_VALUE:
            continue
        found[name] = Defined(name, str(origin), value, is_local)
        if len(found) >= MAX_VARIABLES:
            break
    return list(found.values())


def shared_json(defined: Iterable[Defined]) -> dict[str, Any]:
    """The shareable file: names and sources, sorted, so a save that changes nothing changes no byte."""
    return {"format": FORMAT, "variables": [d.shared_json() for d in sorted(defined, key=lambda d: d.name)]}


def local_json(defined: Iterable[Defined]) -> dict[str, Any]:
    """This computer only: the local plain values (never shared, never a keyring's value)."""
    kept = {d.name: d.value for d in sorted(defined, key=lambda d: d.name) if d.origin == "value" and d.local}
    return {"format": FORMAT, "values": kept}


def put(
    defined: Sequence[Defined],
    body: Any,
    vault_of: Mapping[str, str],
) -> tuple[list[Defined], Defined, str | None]:
    """Add a variable or change one: `{"name", "value", "from": "value" | "keyring", "local": bool}` (local:
    a plain value kept on this computer only, never shared). The new list, the
    definition, and the value to keep in the keyring (None: none, or keep the one there: a keyring
    variable changed with no value). `vault_of`: the names a key vault gives (variable -> vault)."""
    if not isinstance(body, dict):
        raise VariableError('Send {"name": "SALES_REGION", "value": "North", "from": "value"}.')
    name = check_name(body.get("name"))
    origin = body.get("from") or ("keyring" if looks_secret(name) else "value")
    if origin not in ORIGINS:
        raise VariableError('A variable is kept "from" value (a plain value) or keyring (a secret).')
    before = next((d for d in defined if d.name == name), None)
    if before is None and name in vault_of:
        raise VariableError(f"{name} is already a variable (from {vault_of[name]}). Pick another name.")
    if before is None and len(defined) >= MAX_VARIABLES:
        raise VariableError(f"This computer keeps at most {MAX_VARIABLES} variables.")
    value = body.get("value")
    if origin == "value":
        plain = check_value(name, "" if value is None else value)
        if looks_secret(name):
            raise VariableError(
                f"{name} reads like a secret: a plain value is kept as it is, in a file. Keep it in "
                "this computer's keyring."
            )
        local = body.get("local", before.local if before is not None else False)
        if not isinstance(local, bool):
            raise VariableError('"local" is true (this computer only) or false.')
        made = Defined(name, "value", plain, local)
        secret: str | None = None
    else:
        if value is None or value == "":
            if before is None or before.origin != "keyring":
                raise VariableError(f"Type {name}'s value: it is kept in this computer's keyring.")
            secret = None  # the one saved stays
        else:
            secret = check_value(name, value)
        made = Defined(name, "keyring")
    kept = [made if d.name == name else d for d in defined] if before else [*defined, made]
    return kept, made, secret


def renamed(defined: Sequence[Defined], old: str, new: str) -> list[Defined]:
    return [Defined(new, d.origin, d.value, d.local) if d.name == old else d for d in defined]


def removed(defined: Sequence[Defined], name: str) -> list[Defined]:
    return [d for d in defined if d.name != name]


def applied(defined: Iterable[Defined], keyring: Mapping[str, str]) -> dict[str, str]:
    """What the server's processes are given (connections run, kernels started, scheduled scripts): the
    plain values, and the keyring's values found on this computer."""
    out: dict[str, str] = {}
    for d in defined:
        if d.origin == "value":
            out[d.name] = d.value
        elif d.name in keyring:
            out[d.name] = keyring[d.name]
    return out


# ===== what each connection says about variables =====


@dataclass(frozen=True)
class ConnectionFacts:
    name: str
    secrets: tuple[str, ...] = ()  # the names its code asks secret() for
    saved: frozenset[str] = frozenset()  # those saved in its own keyring
    files: tuple[tuple[str, str, str], ...] = ()  # (variable, setting, this computer's default)
    reads: tuple[str, ...] = ()  # a Python connection's: the names its code reads
    sources: Mapping[str, Mapping[str, str]] = field(default_factory=dict)  # a Python connection's
    vault_mapping: Mapping[str, str] = field(default_factory=dict)  # a vault's: variable -> secret
    vault: bool = False
    every: bool = False  # a vault that loads every secret it holds
    read_only: bool = False  # a pack's or a blade folder's
    # A vault's variables named with its prefix (another had the plain name): variable -> (plain, taken by).
    notes: Mapping[str, tuple[str, str]] = field(default_factory=dict)


def variable_shaped(secret: str) -> bool:
    """secret("WAREHOUSE_PASSWORD") names a variable; secret("password") is the connection's own."""
    return bool(_NAME.match(secret)) and secret == secret.upper() and any(c.isalpha() for c in secret)


# ===== what reads each one: connections, notebooks, scripts, Run settings =====


@dataclass(frozen=True)
class Use:
    kind: str  # connection, notebook, script, run_settings
    name: str  # the connection's name, the document's title
    how: str  # password, keystore, its code, reads it, secret(), or a Run setting's source in words
    path: str | None = None
    cell: int | None = None
    line: int | None = None
    secret: bool = False  # read as a secret

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "name": self.name, "how": self.how}
        for key in ("path", "cell", "line"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out


def _line_of(text: str, name: str) -> int | None:
    pattern = re.compile(rf"['\"]{re.escape(name)}['\"]")
    for number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return number
    return None


def _as_secret(code: str, name: str) -> bool:
    return bool(re.search(rf"secret\(\s*['\"]{re.escape(name)}['\"]", code))


def document_uses(path: str, title: str, text: str) -> dict[str, list[Use]]:
    """The variables a notebook's or a script's Python reads, each with its cell (and a script's line)."""
    kind = notebooks.kind_of(path) if path.lower().endswith((".ipynb", ".py")) else ""
    found: dict[str, list[Use]] = {}
    pieces: list[tuple[int | None, str, str | None]]
    if kind == "notebook":
        try:
            cells, _ = notebooks.read_document(text)
        except (notebooks.NotebookError, ValueError):
            return {}
        pieces = [(c.number, c.source, None) for c in cells if c.kind == "code" and not c.role]
    elif kind == "script":
        try:
            script = table_cells.parse_script(text)
        except ValueError:
            return {}
        pieces = [(c.number, c.source, text) for c in script.cells if not c.html and not c.role]
    else:
        return {}
    for number, source, whole in pieces:
        for read in env_reads(source):
            secret = _as_secret(source, read.name)
            line = _line_of(whole, read.name) if whole is not None else None
            how = "secret()" if secret else "reads it"
            found.setdefault(read.name, []).append(Use(kind, title, how, path, number, line, secret))
    return found


def run_settings_uses(path: str, title: str, variables: Mapping[str, Mapping[str, str]]) -> dict[str, Use]:
    """A script's Run settings: each variable it gives a source (in words, never a value)."""
    return {
        name: Use("run_settings", title, f"Run settings: {source_words(source)}", path)
        for name, source in variables.items()
        if _NAME.match(name)
    }


# ===== the page's list =====


@dataclass
class Variable:
    name: str
    source: str = "missing"
    vault: str | None = None
    vault_secret: str | None = None
    owner: str | None = None  # the connection that keeps it (its keyring, its plain value)
    owner_secret: str | None = None  # the name that connection saves it under
    value: str | None = None  # a plain one's, or its connection's
    default: str | None = None  # a certificate file's path on this computer, when nothing sets it
    defined: Defined | None = None
    set: bool = False
    vault_read_only: bool = False
    uses: list[Use] = field(default_factory=list)
    note: str | None = None  # a vault's prefixed name: why (the plain one was taken)

    @property
    def secret(self) -> bool:
        if self.source in ("keyring", "vault"):
            return True
        return looks_secret(self.name) or any(u.secret for u in self.uses)

    def to_json(self, environ: Mapping[str, str]) -> dict[str, Any]:
        """As the page and the agent read it: a plain value, or this computer's environment's when
        nothing reads it as a secret; never a keyring's, a secret's or a vault's value."""
        out: dict[str, Any] = {
            "name": self.name,
            "from": self.source,
            "words": SOURCE_WORDS[self.source],
            "set": self.set,
            "secret": self.secret,
            # Kept by this computer's own list: changed here.
            "editable": self.defined is not None,
            "renamable": self.defined is not None or (self.source == "vault" and not self.vault_read_only),
            "uses": [u.to_json() for u in self.uses],
        }
        if self.source == "vault":
            out |= {"vault": self.vault, "vault_secret": self.vault_secret}
            if self.note:
                out["note"] = self.note
        if self.owner:
            out["owner"] = self.owner
        if self.defined is not None:
            out["kept"] = self.defined.origin
            out["local"] = self.defined.local
            if self.name in environ and self.source != "vault":
                out["replaces_env"] = True  # the environment's own value is set aside for this one
        if self.default is not None and self.source == "missing":
            out["default"] = self.default
        if self.source == "value":
            out["value"] = self.value or ""
        elif self.source == "env" and not self.secret:
            out["value"] = environ.get(self.name, "")
        # Show (the user's click): a keyring's value, or a secret this computer's environment holds.
        out["hidden"] = self.set and (self.source == "keyring" or (self.source == "env" and self.secret))
        return out


def listing(
    defined: Sequence[Defined],
    connections: Sequence[ConnectionFacts],
    documents: Iterable[Mapping[str, list[Use]]],
    run_settings: Iterable[Mapping[str, Use]],
    environ: Mapping[str, str],
    keyring_saved: Iterable[str],
) -> tuple[list[Variable], list[str]]:
    """Every variable this computer gives or something reads, by name; and the vaults that load every
    secret they hold (their names come only when they run). `environ`: this computer's own environment
    (before its variables' values were given to it); `keyring_saved`: the keyring variables with a value
    on this computer."""
    found: dict[str, Variable] = {}
    saved = set(keyring_saved)

    def at(name: str) -> Variable:
        return found.setdefault(name, Variable(name))

    every: list[str] = []
    for c in connections:
        if not c.vault:
            continue
        if c.every and not c.vault_mapping:  # its names not read on this computer yet
            every.append(c.name)
        for variable, secret in c.vault_mapping.items():
            v = at(variable)
            if v.source == "missing":
                v.source, v.vault, v.vault_secret, v.set = "vault", c.name, secret, True
                v.vault_read_only = c.read_only
                if variable in c.notes:
                    plain, by = c.notes[variable]
                    v.note = f"named {variable}: {plain} was taken by {by}"
    for d in defined:
        v = at(d.name)
        v.defined = d
        if v.source == "missing":
            v.source = d.origin
            v.value = d.value if d.origin == "value" else None
            v.set = (d.origin == "value" and (not d.local or d.value != "")) or d.name in saved
            if not v.set:
                v.source = "missing"  # named; its value not on this computer (its keyring, its local file)
    for c in connections:
        if c.vault:
            continue
        for secret in c.secrets:
            if secret in c.sources:
                continue  # a Python connection's own variable: below
            if variable_shaped(secret):
                v = at(secret)
                v.uses.append(Use("connection", c.name, "password", secret=True))
                if v.source == "missing" and secret in c.saved and secret not in environ:
                    v.source, v.owner, v.owner_secret, v.set = "keyring", c.name, secret, True
            elif secret in c.saved:
                v = at(env_name_for(c.name, secret))
                v.uses.append(Use("connection", c.name, "password", secret=True))
                if v.source == "missing":
                    v.source, v.owner, v.owner_secret, v.set = "keyring", c.name, secret, True
        for name in c.reads:
            source = c.sources.get(name, {})
            origin = source.get("from", "env")
            v = at(name)
            v.uses.append(Use("connection", c.name, "its code", secret=origin in ("keyring", "vault")))
            if v.source != "missing":
                continue
            if origin == "value":
                v.source, v.owner, v.value, v.set = "value", c.name, source.get("value", ""), True
            elif origin == "keyring" and name in c.saved:
                v.source, v.owner, v.owner_secret, v.set = "keyring", c.name, name, True
            elif origin == "vault":
                v.source, v.vault, v.vault_secret, v.owner, v.set = (
                    "vault",
                    source.get("vault"),
                    source.get("secret"),
                    c.name,
                    True,
                )
                v.vault_read_only = True  # changed in the connection's own mapping
        for variable, setting, default in c.files:
            v = at(variable)
            v.uses.append(Use("connection", c.name, setting))
            if v.default is None and default:
                v.default = default
    for uses in documents:
        for name, listed in uses.items():
            at(name).uses.extend(listed)
    for settings in run_settings:
        for name, use in settings.items():
            at(name).uses.append(use)
    for v in found.values():
        if v.source == "missing" and v.name in environ:
            v.source, v.set = "env", True
    return sorted(found.values(), key=lambda v: v.name.casefold()), every


def shown(
    variables: Iterable[Variable], environ: Mapping[str, str], search: Any = None, source: Any = None
) -> list[dict[str, Any]]:
    """The list as answered: searched (a name, a vault, a connection or a document that uses it) and
    kept to one source when asked."""
    if source not in (None, "") and source not in SOURCES:
        raise VariableError(f"source is one of {', '.join(SOURCES)}.")
    words = str(search or "").strip().casefold()
    out = []
    for v in variables:
        if source and v.source != source:
            continue
        if words:
            hay = [v.name, v.vault or "", v.vault_secret or "", v.owner or "", *(u.name for u in v.uses)]
            if not any(words in h.casefold() for h in hay):
                continue
        out.append(v.to_json(environ))
    return out


def find(variables: Iterable[Variable], name: Any) -> Variable:
    wanted = check_name(name)
    for v in variables:
        if v.name == wanted:
            return v
    raise VariableError(f"There is no variable {wanted}.")


# ===== rename: the code that reads it =====


def rename_in_code(code: str, old: str, new: str) -> tuple[str, int]:
    """The code reading `new` wherever it read `old` by name: secret("OLD"), os.environ["OLD"],
    os.environ.get("OLD", ...), os.getenv("OLD"), environ / getenv imported from os. How many changed."""
    quoted = rf"(['\"]){re.escape(old)}\2"
    patterns = [
        re.compile(rf"(\b(?:secret|getenv|environ\.get)\(\s*){quoted}"),
        re.compile(rf"(\benviron\[\s*){quoted}"),
    ]
    count = 0
    for pattern in patterns:
        code, n = pattern.subn(lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(2)}", code)
        count += n
    return code, count


def check_rename(variables: Sequence[Variable], body: Any) -> tuple[Variable, str]:
    if not isinstance(body, dict):
        raise VariableError('Send {"name": "OLD_NAME", "to": "NEW_NAME"}.')
    v = find(variables, body.get("name"))
    to = check_name(body.get("to"))
    if to == v.name:
        raise VariableError(f"{v.name} is its name already.")
    clash = next((o for o in variables if o.name == to and (o.defined or o.source == "vault")), None)
    if clash is not None:
        by = clash.vault if clash.source == "vault" and clash.vault else "your variables"
        raise VariableError(f"{to} is already a variable (from {by}). Pick another name.")
    if v.defined is None and not (v.source == "vault" and not v.vault_read_only):
        where = v.owner or v.vault or "this computer's environment"
        raise VariableError(
            f"{v.name} is not one of this computer's own: it comes from {where}. Rename it there."
        )
    return v, to


def check_remove(variables: Sequence[Variable], body: Any) -> Variable:
    name = body.get("name") if isinstance(body, dict) else body
    v = find(variables, name)
    if v.defined is None and not (v.source == "vault" and not v.vault_read_only):
        where = v.owner or v.vault or "this computer's environment"
        raise VariableError(f"{v.name} is not one of this computer's own: it comes from {where}.")
    return v


# ===== passwords as variables (12.7: a password field holds a reference) =====


@dataclass(frozen=True)
class PasswordMove:
    """A connection's own saved password made a variable: its keyring value kept under `variable`, and its
    code's secret("<secret>") asking for secret("<variable>")."""

    connection: str
    secret: str
    variable: str


def password_moves(
    connections: Sequence[ConnectionFacts], defined: Sequence[Defined], vault_names: Iterable[str] = ()
) -> list[PasswordMove]:
    """The passwords a connection keeps in its own keyring entry (not yet a variable's): each becomes a
    keyring variable of the name the page already shows it under (Sales DB, password -> SALES_DB_PASSWORD).
    A name taken (this computer's own, a vault's, another move's) leaves that one as it is."""
    taken = {d.name for d in defined} | set(vault_names)
    out: list[PasswordMove] = []
    for c in connections:
        if c.vault or c.read_only:
            continue
        for secret in c.secrets:
            if variable_shaped(secret) or secret in c.sources or secret not in c.saved:
                continue
            variable = env_name_for(c.name, secret)
            if variable in taken:
                continue
            taken.add(variable)
            out.append(PasswordMove(c.name, secret, variable))
    return out


def password_move_words(moves: Sequence[PasswordMove], backup: str) -> str:
    if not moves:
        return ""
    listed = ", ".join(f"{m.connection}'s {m.secret} as {m.variable}" for m in moves[:6])
    more = f" and {len(moves) - 6} more" if len(moves) > 6 else ""
    count = "1 password is" if len(moves) == 1 else f"{len(moves)} passwords are"
    kept = f" Their connections as they were: {backup}." if backup else ""
    where = "the Environment's Settings and secrets tab"
    return f"{count} now settings on {where}, in this computer's keyring: {listed}{more}.{kept}"


def holding_words(found: Sequence[Mapping[str, Any]]) -> str:
    """The first start's list: saved text that now reads as naming a variable (12.7)."""
    if not found:
        return ""
    listed = "; ".join(f"{f['where']} (${{{f['names'][0]}}})" for f in found[:8])
    more = f"; and {len(found) - 8} more" if len(found) > 8 else ""
    said = "These now read a variable where they say ${NAME} (type $${NAME} to keep the text)"
    return f"{said}: {listed}{more}."
