"""A script's run settings (the Workbench's Script mode, 2026-11-15; Run as scheduled and its run history
went, the owner's simplicity pass, 2026-11-21).

RUN SETTINGS: the arguments the script is run with (one line, split as a shell would), and each
environment variable it needs with where its value comes from:

  env     this computer: the variable as this computer's environment has it ("This computer")
  value   a plain value, set as it is (no secret: a host's name, a folder)
  vault   a key vault's secret, read when the run starts ("Key vault · warehouse-password")

The variables are found for the user: those the script reads itself (`os.environ["X"]`,
`os.getenv("X")`, ...), with the line, and the passwords of each connection and blade it names
(`sab.read("Warehouse", ...)`: WAREHOUSE_PASSWORD, as a run without the app looks for it). Values are
never shown or kept but a plain value's. The settings are kept by the script's path.

Pure rules, no I/O.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import python_connections, script_export
from swissarmybench.domain.connections import env_name_for

SOURCES: tuple[str, ...] = ("env", "value", "vault")
SOURCE_WORDS: dict[str, str] = {"env": "This computer", "value": "Plain value", "vault": "Key vault"}
MAX_ARGUMENTS: int = 2_000
MAX_VARIABLES: int = 100
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class ScriptRunError(ValueError):
    """Run settings that cannot be used as sent (the message says why)."""


@dataclass(frozen=True)
class RunSettings:
    arguments: str = ""
    variables: dict[str, dict[str, str]] = field(default_factory=dict)  # name -> {"from", "value"?, ...}

    def to_json(self) -> dict[str, Any]:
        return {
            "arguments": self.arguments,
            "variables": [{"name": n, **s} for n, s in self.variables.items()],
        }


def split_arguments(arguments: str) -> list[str]:
    """The arguments as a shell splits them (`--date 2026-11-14 --region "East coast"`)."""
    try:
        return shlex.split(arguments)
    except ValueError as error:
        raise ScriptRunError(f"The arguments cannot be read: {error}.") from None


def check_settings(sent: Any) -> RunSettings:
    """Run settings as sent: {"arguments": "--date 2026-11-14", "variables": [{"name", "from", ...}]}."""
    if not isinstance(sent, dict):
        raise ScriptRunError(
            'Send {"arguments": "--region all", "variables": [{"name": "X", "from": "env"}]}.'
        )
    arguments = sent.get("arguments") or ""
    if not isinstance(arguments, str) or len(arguments) > MAX_ARGUMENTS or "\n" in arguments:
        raise ScriptRunError(f"The arguments are one line (at most {MAX_ARGUMENTS} characters).")
    split_arguments(arguments)
    raw = sent.get("variables") or []
    if not isinstance(raw, list) or len(raw) > MAX_VARIABLES:
        raise ScriptRunError(f"The variables are a list (at most {MAX_VARIABLES}).")
    variables: dict[str, dict[str, str]] = {}
    for row in raw:
        if not isinstance(row, dict):
            raise ScriptRunError('Each variable is {"name": "REPORT_FOLDER", "from": "env"}.')
        name, origin = row.get("name"), row.get("from", "env")
        if not isinstance(name, str) or not _NAME.match(name):
            raise ScriptRunError(f"{name!r} is not an environment variable's name (letters, digits and _).")
        if name in variables:
            raise ScriptRunError(f"{name} is given twice.")
        if origin not in SOURCES:
            raise ScriptRunError(
                f'{name} comes "from" env (this computer), value (a plain value) or vault (a key vault).'
            )
        source = {"from": str(origin)}
        if origin == "value":
            value = row.get("value", "")
            if not isinstance(value, str) or len(value) > 10_000 or "\x00" in value:
                raise ScriptRunError(f"{name}'s value is text (at most 10,000 characters).")
            if python_connections.looks_secret(name):
                raise ScriptRunError(
                    f"{name} reads like a secret: a plain value is kept as it is. Use a key vault or this "
                    "computer's environment."
                )
            source["value"] = value
        elif origin == "vault":
            vault, secret = row.get("vault"), row.get("secret")
            if not isinstance(vault, str) or not vault.strip() or len(vault) > 64:
                raise ScriptRunError(f"Name the key vault {name} comes from.")
            if not isinstance(secret, str) or not secret.strip() or len(secret) > 500:
                raise ScriptRunError(f"Name the secret in {vault.strip()} that {name} is.")
            source |= {"vault": vault.strip(), "secret": secret.strip()}
        variables[name] = source
    return RunSettings(arguments.strip(), variables)


def read_settings(raw: Any) -> RunSettings:
    """Settings as kept (anything unreadable: none)."""
    try:
        return check_settings(raw)
    except ScriptRunError:
        return RunSettings()


def source_words(source: Mapping[str, str]) -> str:
    """Where a variable comes from, in words, never its value: "Key vault · warehouse-password"."""
    origin = source.get("from", "env")
    if origin == "vault":
        return f"Key vault · {source.get('secret', '')}"
    return SOURCE_WORDS.get(origin, "This computer")


# ===== the variables a script needs =====


@dataclass(frozen=True)
class Needed:
    name: str
    why: str  # "line 23", or the connection or blade that needs it ("Warehouse")
    secret: bool
    # The script cannot run without it (os.environ["X"]); a connection's password may come from this
    # computer's keyring instead, and .get or getenv has its own default.
    required: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "why": self.why, "looks_secret": self.secret, "required": self.required}


def named_connections(code: str) -> list[str]:
    """The connections and blades the code names: `sab.read("Warehouse", ...)`, `sab.blade("FX rate")`,
    `sab.sql("Shop", ...)`, `sab.dax("Finance/Sales model", ...)` (the workspace: Finance), a `%%sql`
    cell's. Found as the one-script export finds them (domain/script_export.py `references`), so a
    scheduled run and an exported script look for the same passwords."""
    return script_export.references(script_export.script_cells(code), {})


def _line_of(code: str, name: str) -> int | None:
    for number, line in enumerate(code.splitlines(), start=1):
        if re.search(rf"['\"]{re.escape(name)}['\"]", line):
            return number
    return None


def needed(
    code: str,
    secrets_of: Callable[[str], Sequence[str] | None],
    files_of: Callable[[str], Sequence[str]] = lambda _: (),
) -> list[Needed]:
    """Every environment variable the script needs: those it reads itself (with the line), then each
    named connection's and blade's passwords (`secrets_of`: the names its code asks secret() for; None:
    no such connection here) and the certificate or keystore files it maps to a variable (`files_of`:
    those variables; domain/certificate_files.py)."""
    out: list[Needed] = []
    seen: set[str] = set()
    for named in named_connections(code):
        for secret in secrets_of(named) or ():
            variable = env_name_for(named, secret)
            if variable not in seen:
                seen.add(variable)
                out.append(Needed(variable, named, True))
        for variable in files_of(named):
            if variable not in seen:
                seen.add(variable)
                out.append(Needed(variable, named, False))
    own = [
        Needed(
            read.name,
            f"line {_line_of(code, read.name) or '?'}",
            python_connections.looks_secret(read.name),
            read.required,
        )
        for read in python_connections.env_reads(code)
        if read.name not in seen
    ]
    return own + out


def rows(settings: RunSettings, found: Iterable[Needed]) -> list[dict[str, Any]]:
    """Run settings' variables: each one found (with why) and each one added, with its source in words;
    a plain value's value (no secret) and a vault's names, never another value."""
    listed: list[dict[str, Any]] = []
    names: set[str] = set()
    for need in found:
        source = settings.variables.get(need.name, {"from": "env"})
        listed.append(need.to_json() | dict(source) | {"words": source_words(source)})
        names.add(need.name)
    for name, source in settings.variables.items():
        if name not in names:
            listed.append(
                {"name": name, "why": "added", "looks_secret": python_connections.looks_secret(name)}
                | dict(source)
                | {"words": source_words(source)}
            )
    return listed
