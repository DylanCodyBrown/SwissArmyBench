"""The Variables page's edge (services/variables.py): its two files, this computer's keyring for the
keyring variables, and the server's own environment, which every process it starts inherits.

  files         two TOML files in the library (Plans/library.plan.md): variables.toml (shareable: names,
                sources, plain values not marked local) and local/variables.toml (this computer only, git-
                ignored: the local plain values). Written only when their text changes. No folder (a test's
                server): kept in memory.
  keyring       service SwissArmyBench, user `variable/<NAME>`: one value per name on this computer
  environment   the variables' values set in this process's environment (connections' runs, kernels
                started from now on and scheduled scripts inherit it); a name the computer had already
                gets its own value back when the variable goes. Memory only: never written.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeStore
from swissarmybench.domain import library


class VariableFiles:
    """The shareable file and this computer's local one, in the library (None: memory only). `root` gives the
    library folder each time, so Settings' Library folder moves them."""

    def __init__(self, root: Callable[[], Path] | None, made: Callable[[], object] | None = None) -> None:
        self._root = root
        self._made = made or (lambda: None)  # the library's README.md and .gitignore, on its first write
        self._memory: dict[str, Any] = {}

    @property
    def shared(self) -> Path | None:
        return self._root() / library.VARIABLES_FILE if self._root else None

    @property
    def local(self) -> Path | None:
        return self._root() / library.LOCAL_VARIABLES_FILE if self._root else None

    def _read(self, path: Path | None, key: str) -> Any:
        if path is None:
            return self._memory.get(key)
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeError):
            return None
        return library.read_variables_toml(text) if key == "shared" else library.read_local_toml(text)

    def _write(self, path: Path | None, key: str, data: Any) -> None:
        if path is None:
            self._memory[key] = data
            return
        text = library.variables_toml(data) if key == "shared" else library.local_toml(data)
        if not path.is_file() and key == "local" and not (data or {}).get("values"):
            return  # no local value: no local file
        # Nothing changed: no file touched (a Git diff shows only the user's changes).
        if write_atomic(path, text, newline="\n", if_changed=True):
            self._made()

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


def backup_copies(folder: Path) -> Callable[[list[Path]], str]:
    """A dated backup of files about to change (the password move): each copied into `folder`, which is
    made on the first copy. Says where ("" when nothing was copied)."""

    def copy(paths: list[Path]) -> str:
        copied = False
        for path in paths:
            if path.is_file():
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, folder / path.name)
                copied = True
        return str(folder) if copied else ""

    return copy
