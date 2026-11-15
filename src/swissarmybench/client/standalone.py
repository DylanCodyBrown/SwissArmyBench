"""Connections and blades when the app is not running: a saved notebook runs top to bottom anywhere.

A notebook made in the Workbench reads its tables through `sab.sql("Shop", ...)`, `sab.dax(...)`,
`sab.connection(...)`, `sab.blade(...)` and `sab.read(...)`. With the app running, the app hands over
each connection's code. Without it (a scheduled run on this computer, an Azure Function, a CI job) the
same calls find the connection here, so the notebook runs as it is, with no export step (the owner,
2026-11-15: "no export feature"):

    1. this computer's saved connections and blades (the app's own folder, ~/.swissarmybench/blades),
       when the app is installed here but not running;
    2. the blade folders: those the app lists, those in SWISSARMYBENCH_BLADE_FOLDERS (separated by the
       system's path separator), the current folder and its blades/ folder. A connection's portable file
       (its Export, `Shop.blade.py`) put beside the notebook is found there;
    3. the starter pack, shipped inside the package (`sab.blade("Excel copy template")`).

Passwords: a value saved on this computer (the keyring, when this Python has the keyring package and
the computer a vault), else an environment variable named after the connection and the secret
(Shop's secret("password") reads SHOP_PASSWORD), else one named as the code names it (PASSWORD,
password). A password that comes from a key vault in the app is the variable the vault would set: an
Azure Function's Key Vault reference sets it, and the vault's own code runs only when it is not set.
Standard library only, like the rest of the client.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from swissarmybench.adapters.blades import BladeStore
from swissarmybench.domain import python_connections
from swissarmybench.domain.blades import Blade, VaultUnavailableError, is_blade, read_blade
from swissarmybench.domain.connections import connection_kind, env_name_for
from swissarmybench.renamed import env, home_state_folder

_PACKAGE = Path(__file__).resolve().parents[1]


class NotFoundHereError(LookupError):
    """No saved connection, blade folder or starter has this name."""


class _Store(BladeStore):
    """The app's blade store, read from this Python: a computer with no keyring package (an Azure
    Function, a CI runner) has no saved passwords rather than an import error."""

    @staticmethod
    def _keyring() -> Any:
        try:
            return BladeStore._keyring()
        except ImportError:
            raise VaultUnavailableError("This Python has no keyring package.") from None


def _state() -> Path:
    override = env("SWISSARMYBENCH_STATE")
    return Path(override) if override else home_state_folder()


def store() -> BladeStore:
    """The saved blades, the blade folders and the starter pack, as the app would read them."""
    state = _state()
    return _Store(
        state / "blades",
        folders_file=state / "blade_folders.json",
        pins_file=state / "blade_pins.json",
        starters=_PACKAGE / "starters",
    )


def _here() -> list[Blade]:
    """The blade files in the current folder and its blades/ folder (only those two: the current folder
    of a scheduled run may be anywhere)."""
    found: list[Blade] = []
    for folder in (Path.cwd(), Path.cwd() / "blades"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py")):
            try:
                size = path.stat().st_size
            except OSError:
                continue
            blade, _ = BladeStore._load_file(path, size, is_blade, read_blade)
            if blade is not None:
                found.append(blade)
    return found


def find(name: str, blades: BladeStore | None = None) -> Blade:
    """The blade or connection of this name (any case), from the places above, in that order."""
    blades = blades or store()
    try:
        return blades.get(name)
    except KeyError:
        pass
    for blade in _here():
        if blade.name.casefold() == name.casefold():
            return blade
    places = f"{_state() / 'blades'}, the blade folders, the current folder or the starter pack"
    raise NotFoundHereError(
        f"Swiss Army Bench is not running, and no connection or blade named {name!r} is in {places}. "
        "Start the app, or put the connection's exported file (its Export, a .blade.py file) beside the "
        "notebook."
    )


def _from_environment(blade: Blade, wanted: list[str]) -> dict[str, str]:
    """The secrets set as environment variables: the connection's own name first (SHOP_PASSWORD), then
    the name as the code writes it (secret() reads that one itself, too)."""
    found: dict[str, str] = {}
    for secret in wanted:
        for variable in (env_name_for(blade.name, secret), secret):
            if os.environ.get(variable):
                found[secret] = os.environ[variable]
                break
    return found


def spec(name: str) -> dict[str, Any]:
    """What `sab.blade()` runs, in the shape the app's /blades/{name}/python gives it
    (services/blades.py for_python), read from this computer and the environment."""
    blades = store()
    blade = find(name, blades)
    saved = blades.saved_secrets(blade)
    secrets = saved | _from_environment(blade, [s for s in blade.secrets if s not in saved])
    vaults, typed = blades.providers(blade)
    if all(s in secrets for s in blade.secrets):
        vaults, typed = [], {}  # every value is here: no vault needs to run, nobody is asked
    python: dict[str, Any] | None = None
    jobs: list[dict[str, Any]] = []
    if connection_kind(blade.kind, blade.template) == "python":
        python = {
            "tables": blade.catalog_command,
            "read": blade.read_command,
            "set": python_connections.plain_values(blade.variables),
            "keyring": python_connections.keyring_names(blade.variables),
        }
        # A variable a vault gives runs that vault only when the variable is not set already.
        unset = {n: s for n, s in blade.variables.items() if not os.environ.get(n)}
        jobs = python_connections.vault_jobs(unset, blades.get, blades.saved_secrets)
    return {
        "python": python,
        "name": blade.name,
        "kind": blade.kind,
        "code": blade.code,
        "variable": blade.variable,
        "secrets": secrets,
        "vault_mapping": blade.vault_mapping,
        "vault_all": blade.vault_all,
        "env_names": blade.env_names,
        "typed": typed,
        "vaults": [
            {
                "label": v.name,
                "code": v.code,
                "variable": v.variable,
                "mapping": v.vault_mapping,
                "every": v.vault_all,
                "secrets": blades.saved_secrets(v),
            }
            for v in vaults
        ]
        + jobs,
    }


def record(name: str) -> dict[str, Any]:
    """The connection as the app's connections list describes it (no code, no secrets)."""
    blade = find(name)
    return {
        "name": blade.name,
        "kind": blade.kind,
        "dialect": blade.dialect,
        "variable": blade.variable,
        "template": blade.template,
        "connection": connection_kind(blade.kind, blade.template),
    }


def records() -> list[dict[str, Any]]:
    """Every connection found here (saved and in the blade folders), as record() describes each."""
    found = {b.name.casefold(): b for b in [*_here(), *store().all()]}
    return [
        record(b.name)
        for b in sorted(found.values(), key=lambda b: b.name.casefold())
        if connection_kind(b.kind, b.template) not in (None, "vault")
    ]
