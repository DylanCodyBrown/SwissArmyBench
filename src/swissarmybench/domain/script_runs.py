"""A script's runs (the Workbench's Script mode, 2026-11-15): its run settings, "Run as scheduled" and
its run history.

RUN SETTINGS: the arguments the script is run with (one line, split as a shell would), and each
environment variable it needs with where its value comes from:

  env     this computer: the variable as this computer's environment has it ("This computer")
  value   a plain value, set as it is (no secret: a host's name, a folder)
  vault   a key vault's secret, read when the run starts ("Key vault · warehouse-password")

The variables are found for the user: those the script reads itself (`os.environ["X"]`,
`os.getenv("X")`, ...), with the line, and the passwords of each connection and blade it names
(`sab.read("Warehouse", ...)`: WAREHOUSE_PASSWORD, as a run without the app looks for it). Values are
never shown or kept but a plain value's. The settings are kept by the script's path.

RUN AS SCHEDULED runs the script as a schedule would: `python <script> <arguments>` in the script's
own Python, in its folder, as a fresh process with no app (the client finds no server and reads
connections as an exported script does), with the variables set from their sources. Its exit code,
how long it took, which sources gave its variables and the end of its output are kept in the run
history, with each Run file of the script (the kernel's run).

The history is memory only (it may hold what a script printed): the last MAX_RUNS runs of a script,
the last MAX_LOG_LINES lines of each. Pure rules, no I/O.
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
HOW: dict[str, str] = {"scheduled": "Run as scheduled", "file": "Run file"}
MAX_ARGUMENTS: int = 2_000
MAX_VARIABLES: int = 100
MAX_RUNS: int = 50
MAX_LOG_LINES: int = 400
MAX_LINE: int = 2_000
RUN_SECONDS: float = 30 * 60.0
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


def needed(code: str, secrets_of: Callable[[str], Sequence[str] | None]) -> list[Needed]:
    """Every environment variable the script needs: those it reads itself (with the line), then each
    named connection's and blade's passwords (`secrets_of`: the names its code asks secret() for; None:
    no such connection here)."""
    out: list[Needed] = []
    seen: set[str] = set()
    for named in named_connections(code):
        for secret in secrets_of(named) or ():
            variable = env_name_for(named, secret)
            if variable not in seen:
                seen.add(variable)
                out.append(Needed(variable, named, True))
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


# ===== a run =====


@dataclass(frozen=True)
class Plan:
    """What a scheduled run is given: the command's arguments, the plain values, the vaults to read
    (their variables' secret names), and each variable's source in words (for the history)."""

    arguments: list[str]
    values: dict[str, str]
    vaults: dict[str, dict[str, str]]  # vault -> variable -> secret
    sources: list[tuple[str, str]]
    missing: list[str]  # variables from this computer that it does not have


def plan(settings: RunSettings, found: Iterable[Needed], present: Callable[[str], bool]) -> Plan:
    values: dict[str, str] = {}
    vaults: dict[str, dict[str, str]] = {}
    sources: list[tuple[str, str]] = []
    missing: list[str] = []
    found = list(found)
    required = {n.name for n in found if n.required}
    every = {n.name: settings.variables.get(n.name, {"from": "env"}) for n in found} | settings.variables
    for name, source in every.items():
        origin = source.get("from", "env")
        sources.append((name, source_words(source)))
        if origin == "value":
            values[name] = source.get("value", "")
        elif origin == "vault":
            vaults.setdefault(source["vault"], {})[name] = source["secret"]
        elif name in required and not present(name):
            missing.append(name)
    return Plan(split_arguments(settings.arguments), values, vaults, sources, missing)


@dataclass(frozen=True)
class Run:
    how: str  # "scheduled" or "file"
    started: float
    seconds: float
    exit_code: int | None  # None: it was stopped (the time ran out)
    command: str
    sources: tuple[tuple[str, str], ...]
    log: tuple[str, ...]

    def to_json(self, with_log: bool = True) -> dict[str, Any]:
        said: dict[str, Any] = {
            "how": self.how,
            "how_words": HOW.get(self.how, self.how),
            "started": self.started,
            "seconds": round(self.seconds, 2),
            "exit_code": self.exit_code,
            "command": self.command,
            "sources": [{"name": n, "words": w} for n, w in self.sources],
        }
        if with_log:
            said["log"] = list(self.log)
        return said


def tail(text: str) -> tuple[str, ...]:
    """The end of a run's output: its last lines, each cut to a length."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return tuple(line[:MAX_LINE] for line in lines[-MAX_LOG_LINES:])


def command_line(script: str, arguments: Sequence[str]) -> str:
    """The run as the log shows it: `$ python daily_sales.py --date 2026-11-14`."""
    name = re.split(r"[\\/]", script)[-1]
    return " ".join(["$ python", shlex.quote(name), *(shlex.quote(a) for a in arguments)])


def recorded(sent: Any) -> Run:
    """A Run file of the script, as the window reports it: {"seconds", "exit_code", "log"?}."""
    if not isinstance(sent, dict):
        raise ScriptRunError('Send {"seconds": 3.9, "exit_code": 0}.')
    seconds, code = sent.get("seconds"), sent.get("exit_code")
    if not isinstance(seconds, int | float) or isinstance(seconds, bool) or seconds < 0:
        raise ScriptRunError("seconds is how long the run took.")
    if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
        raise ScriptRunError("exit_code is a whole number (0: it ran to its end).")
    log = sent.get("log") or ""
    started = sent.get("started")
    return Run(
        "file",
        float(started) if isinstance(started, int | float) and not isinstance(started, bool) else 0.0,
        float(seconds),
        code,
        "Run file",
        (),
        tail(log if isinstance(log, str) else ""),
    )
