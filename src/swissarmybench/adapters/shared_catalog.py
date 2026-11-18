"""The shared catalog's files: the library's catalog/<connection>.json (domain/shared_catalog.py: rules).

  read      every file's text and its stamp (modified time and size), to see what a pull changed
  write     atomically (a .tmp beside it, then replaced), only when its bytes change; the library's README.md
            and .gitignore made on first use, as every library write does
  remove    a deleted connection's file

The app never runs git: the folder is the user's working copy; their pulls bring files in, their commits
take them out.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from swissarmybench.domain import shared_catalog as rules

Stamp = tuple[int, int]  # (modified time in nanoseconds, size)


class CatalogFiles:
    def __init__(self, library: Callable[[], Path] | None, made: Callable[[], object] = lambda: None) -> None:
        self._library = library  # None: nothing kept (tests that keep no state)
        self._made = made

    @property
    def folder(self) -> Path | None:
        return self._library() / rules.FOLDER if self._library is not None else None

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
        folder.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".tmp")
        part.write_bytes(data)
        os.replace(part, path)
        return True

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
