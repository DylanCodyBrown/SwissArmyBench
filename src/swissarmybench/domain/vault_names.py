"""A key vault's secret names remembered on this computer (the owner, 2026-11-20: "Every time I update or
reopen the app my Vault variables disappear").

A vault that loads every secret it holds ("Every secret in the vault") keeps no names in its own file: they
come from reading the vault. Each read's names are kept in the library's `local/vault-names/<vault>.json`
(git-ignored: this computer's only), so the vault's variables are there from the first second after a start.

  the file   the vault's name, each secret's name and its variable (as domain/connections.py vault_names
             makes them), the time they were read; sorted, the same bytes for the same names; never a value,
             a token or a secret
  written    only when the names change (a read giving the same names writes nothing)
  read as    the vault's variables: every name its own variable, a secret the user renamed keeping that
             name (domain/variable_refs.py every_secret)

Standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.blades import file_name as blade_file_name
from swissarmybench.domain.variable_refs import env_name_for_secret

FOLDER: str = "local/vault-names"
SUFFIX: str = ".json"
FORMAT: int = 1
MAX_NAMES: int = 5000


@dataclass(frozen=True)
class Remembered:
    vault: str
    names: tuple[tuple[str, str], ...]  # (the secret's name in the vault, its variable), sorted
    read_at: str  # when these names were read (ISO 8601, UTC)

    def secrets(self) -> list[str]:
        return [secret for secret, _ in self.names]


def file_name(vault: str) -> str:
    """local/vault-names/<this>: the vault's name made file-safe as its blade file is (team_vault.json)."""
    return blade_file_name(vault).removesuffix(".blade.py") + SUFFIX


def rows(found: Iterable[Any]) -> tuple[tuple[str, str], ...]:
    """What a read gave ([{"secret", "env"}] or plain names) as sorted (secret, variable) pairs, each once."""
    pairs: dict[str, str] = {}
    for item in found:
        if isinstance(item, Mapping):
            secret, env = str(item.get("secret") or "").strip(), str(item.get("env") or "").strip()
        elif isinstance(item, str):
            secret, env = item.strip(), ""
        else:
            continue
        if secret:
            pairs.setdefault(secret, env or env_name_for_secret(secret))
    ordered = sorted(pairs.items(), key=lambda p: (p[0].casefold(), p[0]))
    return tuple(ordered[:MAX_NAMES])


def render(remembered: Remembered) -> str:
    """The file's text: sorted keys, one name per line, a newline at the end."""
    lines = ["{", f'  "format": {FORMAT},', '  "names": [']
    items = [
        "    " + json.dumps({"env": env, "secret": secret}, ensure_ascii=False, sort_keys=True)
        for secret, env in remembered.names
    ]
    if items:
        lines.append(",\n".join(items))
    lines += [
        "  ],",
        f'  "read_at": {json.dumps(remembered.read_at)},',
        f'  "vault": {json.dumps(remembered.vault, ensure_ascii=False)}',
        "}",
    ]
    return "\n".join(lines) + "\n"


def parse(text: str | None) -> Remembered | None:
    """A file read back; None when it is not one (broken, a newer format, no vault)."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("vault"), str) or not data["vault"].strip():
        return None
    if isinstance(data.get("format"), int) and data["format"] > FORMAT:
        return None
    listed = data.get("names")
    found: list[Any] = listed if isinstance(listed, list) else []
    stamp = data.get("read_at")
    read_at = stamp if isinstance(stamp, str) else ""
    return Remembered(data["vault"], rows(found), read_at)


def renamed_to(remembered: Remembered, vault: str) -> Remembered:
    return Remembered(vault, remembered.names, remembered.read_at)


# ===== one name, one variable (the owner, 2026-11-20: "make sure that we handle env variable collisions by
# not allowing duplicate variables, and if any overlap in the vault then they get prefixed by the vault
# name") =====

YOURS: str = "your variables"


@dataclass(frozen=True)
class VaultIn:
    """A vault as the names are given out: its explicit entries, whether it loads every secret, the secret
    names it lists (read now, or remembered), and the variable each was given before (kept: stable)."""

    name: str
    renamed: Mapping[str, str]  # its own entries: variable -> secret
    every: bool = False
    secrets: Sequence[str] = ()
    kept: Mapping[str, str] = field(default_factory=dict)  # secret -> the variable it had


@dataclass(frozen=True)
class Assigned:
    mapping: dict[str, str]  # variable -> secret
    notes: dict[str, tuple[str, str]]  # a prefixed variable -> (the plain name, what took it)


def _order(vault: VaultIn) -> tuple[str, str]:
    return (vault.name.casefold(), vault.name)


def prefix_of(vault: str) -> str:
    """The vault's name as a variable's prefix: Team Vault -> TEAM_VAULT, 2024 keys -> _2024_KEYS."""
    words = re.sub(r"[^A-Za-z0-9]+", "_", vault).strip("_").upper()[:64] or "VAULT"
    return f"_{words}" if words[0].isdigit() else words


def reserved(defined: Iterable[str], vaults: Sequence[VaultIn]) -> dict[str, str]:
    """The names that keep their plain name, and whose they are: the user's own variables first, then each
    vault's explicit entries (vaults by name: the first keeps a name two map)."""
    out = {name: YOURS for name in sorted(defined)}
    for vault in sorted(vaults, key=_order):
        for env in sorted(vault.renamed):
            out.setdefault(env, vault.name)
    return out


def assign(vaults: Sequence[VaultIn], taken_first: Mapping[str, str]) -> dict[str, Assigned]:
    """Each vault's variables, no name given twice: an explicit entry is its own; a vault that loads every
    secret gives each secret its own name (env_name_for_secret) unless it is taken (by `taken_first`, the
    user's variables and the explicit entries, or by a vault whose name sorts first), then <VAULT>_<NAME>
    (and _2, _3 when that is taken too). A secret keeps the variable it had before while that is free, so a
    name never jumps between starts. Deterministic: the same inputs give the same names."""
    taken = dict(taken_first)
    every = sorted((v for v in vaults if v.every), key=_order)
    out = {v.name: Assigned(dict(v.renamed), {}) for v in vaults if not v.every}
    rest: dict[str, list[str]] = {}
    for vault in every:
        mapping = dict(vault.renamed)
        out[vault.name] = Assigned(mapping, {})
        own = set(mapping.values())
        waiting = rest.setdefault(vault.name, [])
        for secret in sorted(
            {s for s in vault.secrets if s and s not in own}, key=lambda s: (s.casefold(), s)
        ):
            env = vault.kept.get(secret)
            if env and env not in taken and env not in mapping:
                mapping[env] = secret
                taken[env] = vault.name
            else:
                waiting.append(secret)
    for vault in every:
        mapping = out[vault.name].mapping
        for secret in rest[vault.name]:
            env = env_name_for_secret(secret)
            if env in taken or env in mapping:
                base = f"{prefix_of(vault.name)}_{env}"[:128]
                env, n = base, 2
                while env in taken or env in mapping:
                    env, n = f"{base}_{n}", n + 1
            mapping[env] = secret
            taken[env] = vault.name
    for vault in every:
        found = out[vault.name]
        for env, secret in found.mapping.items():
            if secret in vault.renamed.values():
                continue
            plain = env_name_for_secret(secret)
            if env != plain:
                found.notes[env] = (plain, taken.get(plain, "another variable"))
    return out


def note_words(env: str, plain: str, by: str) -> str:
    return f"named {env}: {plain} was taken by {by}"


def taken_words(name: str, by: str) -> str:
    """The one refusal (9.5) for a name given twice."""
    return f"{name} is already a variable (from {by}). Pick another name."
