"""Set up from the meta store (the owner, 2026-11-18: "Connections are shared and the vault env vars are
shared as well so minimal setup is required for new people"). A new person's first run against a team's
meta store (the library folder, a clone of the team's repository): one checklist of what this computer needs.

  1 vaults       each key vault in vaults/: whether this computer can read it now (its own names() run), the
                 one thing that fixes it ("Sign in to Azure"), and how many variables that sign-in gives
  2 values       what still needs a value here: a keyring or local variable with none on this computer, a
                 connection's password with no source here; each with its fix inline (typed once: the keyring,
                 or local/variables.toml)
  3 connections  each connection's status after that: works, needs <thing>, or only works on your machine (the
                 portability rule's words, domain/portability.py)
  4 projects     the shared projects whose connections are not set up here
  the count      "3 things to set up", or "Ready: 9 connections work"
  sharing        a connection whose password comes from this computer's keyring is offered "Move to a vault":
                 mapped to a vault's secret, the next person needs nothing

Pure rules: no I/O. Names and words only, never a value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# The words that sign in to a vault's service, by its starter; others: "Sign in for <vault>".
SIGN_IN: dict[str, str] = {
    "azure_key_vault": "Sign in to Azure",
    "aws_secrets_manager": "Sign in to AWS",
    "aws_parameter_store": "Sign in to AWS",
    "google_secret_manager": "Sign in to Google Cloud",
    "onepassword": "Sign in to 1Password",
    "hashicorp_vault": "Sign in to Vault",
}
# How each sign-in is made, in a few words (what the person runs).
HOW: dict[str, str] = {
    "azure_key_vault": "az login, then Check again",
    "aws_secrets_manager": "aws sso login, then Check again",
    "aws_parameter_store": "aws sso login, then Check again",
    "google_secret_manager": "gcloud auth application-default login, then Check again",
    "onepassword": "op signin, then Check again",
    "hashicorp_vault": "vault login, then Check again",
}
HEADING: str = "Set up this computer"


@dataclass(frozen=True)
class Vault:
    name: str
    template: str = ""
    readable: bool | None = None  # None: its code cannot list (no names()): not checked
    error: str = ""
    variables: tuple[str, ...] = ()  # the variables it gives (mapped, or every secret it lists)

    def sign_in(self) -> str:
        return SIGN_IN.get(self.template, f"Sign in for {self.name}")

    def to_json(self) -> dict[str, Any]:
        n = len(self.variables)
        gives = f"{self.sign_in()} gives {n} variable{'' if n == 1 else 's'}"
        return {
            "name": self.name,
            "template": self.template,
            "readable": self.readable,
            "state": "ready" if self.readable else "unchecked" if self.readable is None else "sign_in",
            "words": "Readable here"
            if self.readable
            else "Not checked: it cannot list its secrets"
            if self.readable is None
            else self.sign_in(),
            "error": self.error,
            "fix": None
            if self.readable is not False
            else {
                "kind": "sign_in",
                "label": self.sign_in(),
                "how": HOW.get(self.template, "then Check again"),
            },
            "gives": gives,
            "variables": list(self.variables),
        }


@dataclass(frozen=True)
class Value:
    """A variable or a connection's password with nothing for it on this computer."""

    name: str
    kind: str  # "keyring" (a secret, typed once into this computer's keyring), "local" (a plain value
    #            kept in local/variables.toml), "password" (a connection's, with no source here)
    connection: str = ""  # a password's connection
    used_by: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        if self.kind == "password":
            fix = {"kind": "password", "label": "Set the password", "connection": self.connection}
            words = f"{self.connection} needs its password {self.name} on this computer"
        elif self.kind == "keyring":
            fix = {
                "kind": "keyring",
                "label": "Type it once (kept in this computer's keyring)",
                "name": self.name,
            }
            words = f"{self.name}: a secret this computer does not have"
        else:
            fix = {"kind": "local", "label": "Type it once (kept in local/variables.toml)", "name": self.name}
            words = f"{self.name}: a value for this computer only"
        return {
            "name": self.name,
            "kind": self.kind,
            **({"connection": self.connection} if self.connection else {}),
            "used_by": list(self.used_by),
            "words": words,
            "fix": fix,
        }


@dataclass(frozen=True)
class Connection:
    name: str
    missing: tuple[str, ...] = ()  # passwords with no source here
    vaults: tuple[str, ...] = ()  # the vaults its passwords come from that are not readable here
    values: tuple[str, ...] = ()  # the variables it reads that need a value here
    keyring: tuple[str, ...] = ()  # passwords this computer's keyring holds: Move to a vault
    local: tuple[Mapping[str, str], ...] = ()  # portability.as_json: only works on this machine
    vault_choices: tuple[str, ...] = ()  # the vaults a password could move to (readable, writable here)

    def needs(self) -> list[str]:
        return [
            *(f"a sign-in to {v}" for v in self.vaults),
            *(f"its password {p}" for p in self.missing),
            *(f"a value for {v}" for v in self.values),
        ]

    def to_json(self) -> dict[str, Any]:
        needs = self.needs()
        if needs:
            state, words = "needs", "Needs " + ", ".join(needs)
        elif self.local:
            reasons = "; ".join(str(r.get("reason") or r.get("words") or "") for r in self.local)
            state, words = "local", f"Only works on your machine: {reasons}".rstrip(": ")
        else:
            state, words = "works", "Works"
        return {
            "name": self.name,
            "state": state,
            "words": words,
            "local": [dict(r) for r in self.local],
            "move_to_vault": [
                {"secret": s, "vaults": list(self.vault_choices), "label": "Move to a vault"}
                for s in self.keyring
            ]
            if self.vault_choices
            else [],
        }


@dataclass(frozen=True)
class SharedProject:
    name: str
    folder: str
    connections: tuple[str, ...] = ()  # the connections it names that are not set up here

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "folder": self.folder,
            "connections": list(self.connections),
            "words": f"{self.name} needs {', '.join(self.connections)} set up here",
        }


@dataclass(frozen=True)
class Checklist:
    vaults: Sequence[Vault] = ()
    values: Sequence[Value] = ()
    connections: Sequence[Connection] = ()
    projects: Sequence[SharedProject] = field(default_factory=tuple)

    def count(self) -> int:
        return (
            sum(1 for v in self.vaults if v.readable is False)
            + len(self.values)
            + sum(1 for p in self.projects if p.connections)
        )

    def to_json(self) -> dict[str, Any]:
        n = self.count()
        working = sum(1 for c in self.connections if not c.needs())
        if n:
            words = f"{n} thing{'' if n == 1 else 's'} to set up"
        else:
            words = (
                f"Ready: {working} connection{'' if working == 1 else 's'} work{'s' if working == 1 else ''}"
            )
        return {
            "heading": HEADING,
            "count": n,
            "ready": n == 0,
            "words": words,
            "vaults": [v.to_json() for v in self.vaults],
            "values": [v.to_json() for v in self.values],
            "connections": [c.to_json() for c in self.connections],
            "projects": [p.to_json() for p in self.projects if p.connections],
        }


def values_needed(variables: Iterable[Mapping[str, Any]]) -> list[Value]:
    """From the Variables page's listing: each variable that is not set here and is not a vault's (a vault's
    comes with its sign-in): a keyring one, or a plain one that is this computer's own (or read by something
    with no value anywhere)."""
    out = []
    for v in variables:
        if v.get("set") or v.get("from") == "vault":
            continue
        kept, origin = v.get("kept"), v.get("from")
        if origin == "keyring" or kept == "keyring":
            kind = "keyring"
        elif v.get("local") or origin in ("value", "missing"):
            kind = "keyring" if v.get("secret") else "local"
        else:
            continue
        uses = tuple(sorted({str(u.get("name")) for u in v.get("uses") or [] if u.get("name")}))
        out.append(Value(str(v["name"]), kind, used_by=uses))
    return sorted(out, key=lambda x: x.name.casefold())


def setup_notice(connections: int, vaults: int) -> str:
    """Said once when the meta store is pointed at a folder that already holds connections."""
    if not connections:
        return ""
    parts = [f"{connections} connection{'' if connections == 1 else 's'}"]
    if vaults:
        parts.append(f"{vaults} key vault{'' if vaults == 1 else 's'}")
    return (
        f"This team library has {' and '.join(parts)}: Settings, Team, {HEADING}, lists what this "
        "computer needs."
    )
