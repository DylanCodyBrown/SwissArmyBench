"""A project's API.py on disk (services/local_api.py): read, written atomically, its stamp."""

from __future__ import annotations

from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic


class LocalApiFiles:
    """API.py: read, written atomically (the user's own file: only on their action), its stamp."""

    @staticmethod
    def read(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    @staticmethod
    def write(path: str, text: str) -> None:
        write_atomic(path, text, if_changed=True)

    @staticmethod
    def stamp(path: str) -> float | None:
        try:
            found = Path(path).stat()
        except OSError:
            return None
        return found.st_mtime_ns / 1e9 + found.st_size

    @staticmethod
    def join(folder: str, name: str) -> str:
        return str(Path(folder) / name)
