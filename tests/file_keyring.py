"""A keyring kept in one JSON file, for a browser test's own server (this container has no system keyring,
and a test must never touch a person's). The file is SAB_TEST_KEYRING_FILE; made-up values only.
Chosen with PYTHON_KEYRING_BACKEND=tests.file_keyring.FileKeyring."""

from __future__ import annotations

import json
import os
from pathlib import Path

from keyring.backend import KeyringBackend


class FileKeyring(KeyringBackend):
    priority = 1.0

    @staticmethod
    def _path() -> Path:
        return Path(os.environ["SAB_TEST_KEYRING_FILE"])

    def _read(self) -> dict[str, str]:
        try:
            found = json.loads(self._path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._read().get(f"{service}\n{username}")

    def set_password(self, service: str, username: str, password: str) -> None:
        kept = self._read() | {f"{service}\n{username}": password}
        self._path().write_text(json.dumps(kept), encoding="utf-8")

    def delete_password(self, service: str, username: str) -> None:
        kept = self._read()
        kept.pop(f"{service}\n{username}", None)
        self._path().write_text(json.dumps(kept), encoding="utf-8")
