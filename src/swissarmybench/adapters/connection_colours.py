"""colours.toml: each connection's colour, in the library (Plans/library.plan.md: library/colours.toml;
domain/connection_colours.py writes and reads the text). The path is asked each time, so Settings' Library
folder moves it.

Written only when its text changes (a save that changes nothing touches no file), through a temporary file
and a replace, so a reader never sees half a file. None: no file at all (a test's server without a state
folder): nothing is ever written.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic


class ColoursFile:
    def __init__(
        self, path: Path | Callable[[], Path] | None, made: Callable[[], object] | None = None
    ) -> None:
        self._path = path
        self._made = made or (lambda: None)  # the library's README.md and .gitignore, on its first write

    @property
    def path(self) -> Path | None:
        return self._path() if callable(self._path) else self._path

    def read(self) -> str:
        if self.path is None or not self.path.is_file():
            return ""
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

    def write(self, text: str) -> None:
        path = self.path
        if path is None or (path.is_file() and self.read() == text):
            return
        self._made()
        write_atomic(path, text, newline="\n")
