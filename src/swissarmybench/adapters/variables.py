"""The Variables page's edge (services/variables.py): this computer's keyring for the project's keyring
variables, and the server's own environment, which every process it starts inherits.

  keyring       service SwissArmyBench, user `variable/<NAME>`: one value per name on this computer (a
                project names the variable; each computer keeps its own value, as connections' passwords)
  environment   the values the open project gives, set in this process's environment (connections' runs,
                kernels started from now on and scheduled scripts inherit it); a name the computer had
                already gets its own value back when the project lets go of it. Memory only: never written.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping

from swissarmybench.adapters.blades import KEYRING_SERVICE, BladeStore


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
