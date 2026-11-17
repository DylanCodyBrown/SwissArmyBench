"""The Variables page's edge (services/variables.py): its two files, this computer's keyring for the
keyring variables, and the server's own environment, which every process it starts inherits.

  files         two JSON files in the state folder: variables.json (shareable: names, sources, plain values
                not marked local; the library's variables.toml later, Plans/library.plan.md) and
                local/variables.json (this computer only: the local plain values). No state folder (a
                test's server): kept in memory. The later move to the library folder is these two paths.
  keyring       service SwissArmyBench, user `variable/<NAME>`: one value per name on this computer
  environment   the variables' values set in this process's environment (connections' runs, kernels
                started from now on and scheduled scripts inherit it); a name the computer had already
                gets its own value back when the variable goes. Memory only: never written.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeStore


class VariableFiles:
    """The shareable file and this computer's local one (None: memory only)."""

    def __init__(self, shared: Path | None, local: Path | None) -> None:
        self.shared = shared
        self.local = local
        self._memory: dict[str, Any] = {}

    def _read(self, path: Path | None, key: str) -> Any:
        if path is None:
            return self._memory.get(key)
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except (OSError, ValueError):
            return None

    def _write(self, path: Path | None, key: str, data: Any) -> None:
        if path is None:
            self._memory[key] = data
            return
        text = json.dumps(data, indent=1, sort_keys=True) + "\n"
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return  # nothing changed: no file touched (a Git diff shows only the user's changes)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text(text, encoding="utf-8")
        part.replace(path)

    def read(self) -> tuple[Any, Any]:
        return self._read(self.shared, "shared"), self._read(self.local, "local")

    def write(self, shared: Any, local: Any) -> None:
        self._write(self.shared, "shared", shared)
        self._write(self.local, "local", local)


class VariableKeyring:
    @staticmethod
    def _user(name: str) -> str:
        return f"variable/{name}"

    def get(self, name: str) -> str | None:
        value: str | None = BladeStore._keyring().get_password(KEYRING_SERVICE, self._user(name))
        return value

    def set(self, name: str, value: str) -> None:
        BladeStore._keyring().set_password(KEYRING_SERVICE, self._user(name), value)

    def delete(self, name: str) -> None:
        BladeStore._keyring().delete_password(KEYRING_SERVICE, self._user(name))


class ProcessEnvironment:
    def __init__(self, environ: MutableMapping[str, str] | None = None) -> None:
        self._environ: MutableMapping[str, str] = os.environ if environ is None else environ
        # The names this gave a value, and what the computer had under each before (None: nothing).
        self._before: dict[str, str | None] = {}

    def base(self) -> Mapping[str, str]:
        """This computer's own environment: as it is, with the project's values taken back out."""
        own = dict(self._environ)
        for name, before in self._before.items():
            if before is None:
                own.pop(name, None)
            else:
                own[name] = before
        return own

    def apply(self, values: Mapping[str, str]) -> None:
        for name in [n for n in self._before if n not in values]:
            before = self._before.pop(name)
            if before is None:
                self._environ.pop(name, None)
            else:
                self._environ[name] = before
        for name, value in values.items():
            if name not in self._before:
                self._before[name] = self._environ.get(name)
            self._environ[name] = value
