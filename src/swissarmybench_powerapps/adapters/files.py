"""A code app's folder on disk: read, listed, the app's one marker file written; the custom connector's
files written where the user asked; and the extension's one small state file (`powerapps.json`: the code
app last opened, its path only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic

MAX_FILES = 5000
MAX_READ = 2_000_000
_SKIP = frozenset({"node_modules", ".git", "dist", ".vite", ".turbo"})


class ProjectFiles:
    def __init__(self, state_file: Path) -> None:
        self._state = state_file

    # ----- the folder -----

    def exists(self, folder: str) -> bool:
        return Path(folder).expanduser().is_dir()

    def resolve(self, folder: str) -> str:
        return str(Path(folder).expanduser().resolve())

    def parent_of(self, folder: str) -> str:
        return str(Path(folder).expanduser().resolve().parent)

    def name_of(self, folder: str) -> str:
        return Path(folder).name

    def join(self, folder: str, *parts: str) -> str:
        return str(Path(folder, *parts))

    def read(self, folder: str, relative: str) -> str | None:
        path = self._inside(folder, relative)
        try:
            if path.stat().st_size > MAX_READ:
                return None
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None

    def write(self, folder: str, relative: str, text: str) -> str:
        path = self._inside(folder, relative)
        write_atomic(path, text, newline="\n")
        return str(path)

    def listing(self, folder: str) -> list[str]:
        """Every file's path relative to the folder (packages and builds skipped), at most MAX_FILES."""
        root = Path(folder).expanduser().resolve()
        found: list[str] = []
        for here, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP)
            for name in sorted(files):
                found.append(Path(here, name).relative_to(root).as_posix())
                if len(found) >= MAX_FILES:
                    return found
        return found

    def empty_or_missing(self, folder: str) -> bool:
        path = Path(folder).expanduser()
        return not path.exists() or (path.is_dir() and not any(path.iterdir()))

    def _inside(self, folder: str, relative: str) -> Path:
        root = Path(folder).expanduser().resolve()
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise PermissionError(f"{relative} is outside the code app's folder.")
        return path

    # ----- a temporary folder (a dry run's files before the user said where) -----

    # ----- the extension's state -----

    def state(self) -> dict[str, Any]:
        try:
            data = json.loads(self._state.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_state(self, data: dict[str, Any]) -> None:
        write_atomic(self._state, json.dumps(data, indent=2, sort_keys=True) + "\n", if_changed=True)
