"""A key vault's remembered secret names: the library's local/vault-names/<vault>.json (domain/vault_names).

read      a vault's file's text (None: none)
write     atomically, only when its bytes change; the library's README.md and .gitignore made on first use
          (local/ is git-ignored: this computer's only)
remove    a deleted vault's file; listed: every file's name (pruning a vault that is gone)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import vault_names as rules


class VaultNameFiles:
    def __init__(self, library: Callable[[], Path] | None, made: Callable[[], object] = lambda: None) -> None:
        self._library = library  # None: nothing kept (tests that keep no state)
        self._made = made

    @property
    def folder(self) -> Path | None:
        return self._library() / rules.FOLDER if self._library is not None else None

    def read(self, name: str) -> str | None:
        folder = self.folder
        if folder is None:
            return None
        try:
            return (folder / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def write(self, name: str, text: str) -> bool:
        """Written when its bytes change (atomically). Whether it was."""
        folder = self.folder
        if folder is None:
            return False
        path = folder / name
        data = text.encode("utf-8")
        try:
            if path.read_bytes() == data:
                return False
        except OSError:
            pass
        self._made()
        return write_atomic(path, data)

    def remove(self, name: str) -> bool:
        folder = self.folder
        if folder is None:
            return False
        try:
            (folder / name).unlink()
            return True
        except OSError:
            return False

    def listed(self) -> list[str]:
        folder = self.folder
        if folder is None or not folder.is_dir():
            return []
        return sorted(p.name for p in folder.glob(f"*{rules.SUFFIX}") if p.is_file())
