"""A key vault's remembered secret names: the library's local/vault-names/<vault>.json (domain/vault_names).

read      a vault's file's text (None: none)
write     atomically, only when its bytes change; the library's README.md and .gitignore made on first use
          (local/ is git-ignored: this computer's only)
remove    a deleted vault's file; listed: every file's name (pruning a vault that is gone)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import TextFolder
from swissarmybench.domain import vault_names as rules


class VaultNameFiles(TextFolder):
    def __init__(self, library: Callable[[], Path] | None, made: Callable[[], object] = lambda: None) -> None:
        super().__init__(library, rules.FOLDER, made)

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
