"""The shared catalog's files: the library's catalog/<connection>.json (domain/shared_catalog.py: rules).

  read      every file's text and its stamp (modified time and size), to see what a pull changed
  write     atomically (a .tmp beside it, then replaced), only when its bytes change; the library's README.md
            and .gitignore made on first use, as every library write does
  remove    a deleted connection's file

The app never runs git: the folder is the user's working copy; their pulls bring files in, their commits
take them out.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import TextFolder
from swissarmybench.domain import shared_catalog as rules

Stamp = tuple[int, int]  # (modified time in nanoseconds, size)


class CatalogFiles(TextFolder):
    def __init__(self, library: Callable[[], Path] | None, made: Callable[[], object] = lambda: None) -> None:
        super().__init__(library, rules.FOLDER, made)

    def stamps(self) -> dict[str, Stamp]:
        """Each catalog file's stamp, by its file name."""
        folder = self.folder
        if folder is None or not folder.is_dir():
            return {}
        found: dict[str, Stamp] = {}
        for path in folder.glob(f"*{rules.SUFFIX}"):
            try:
                st = path.stat()
            except OSError:
                continue
            if path.is_file():
                found[path.name] = (st.st_mtime_ns, st.st_size)
        return found

    def remove(self, name: str) -> bool:
        folder = self.folder
        if folder is None:
            return False
        try:
            (folder / name).unlink()
            return True
        except FileNotFoundError:
            return False

    def stamp(self, name: str) -> Stamp | None:
        folder = self.folder
        if folder is None:
            return None
        try:
            st = (folder / name).stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)
