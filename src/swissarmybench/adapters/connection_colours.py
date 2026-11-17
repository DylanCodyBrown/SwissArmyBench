"""colours.toml: each connection's colour, this computer's (domain/connection_colours.py writes and reads
the text). One small adapter so the file can move into the library folder (Plans/library.plan.md:
library/colours.toml) by changing its path only.

Written only when its text changes (a save that changes nothing touches no file), through a temporary file
and a replace, so a reader never sees half a file. None: no file at all (a test's server without a state
folder): nothing is ever written.
"""

from __future__ import annotations

import os
from pathlib import Path


class ColoursFile:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def read(self) -> str:
        if self.path is None or not self.path.is_file():
            return ""
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

    def write(self, text: str) -> None:
        if self.path is None or (self.path.is_file() and self.read() == text):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)
