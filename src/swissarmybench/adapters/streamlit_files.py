"""A notebook's Streamlit app on disk (docs/ideas.md, "Streamlit cells").

The live app is written to a temporary folder of its own, one for each notebook, never into the
user's folders, and the folder goes when the app stops. The export is the one thing written where the
user says: the folder they picked.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

PREFIX: str = "swissarmygrid-streamlit-"


class AppFiles:
    def __init__(self) -> None:
        self._made: set[str] = set()

    def folder(self) -> str:
        """A new temporary folder for one app (only this user reads it)."""
        made = tempfile.mkdtemp(prefix=PREFIX)
        (Path(made) / "data").mkdir()
        self._made.add(made)
        return made

    def write(self, folder: str, files: Mapping[str, str], keep: set[str]) -> None:
        """The app's files as they should be now: each written (a file whose text is the same is
        left alone, so Streamlit sees no change), and the pages of earlier versions taken away, but
        for `keep` (the version before this one: a page that is running just now may still read it)."""
        root = Path(folder)
        for name, text in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = text.encode("utf-8")
            if target.is_file() and target.read_bytes() == data:
                continue
            # Whole or not at all: a page is never read half written.
            partial = target.with_name(target.name + ".part")
            partial.write_bytes(data)
            os.replace(partial, target)
        for old in root.glob("*.py"):
            if old.name not in files and old.name not in keep:
                old.unlink(missing_ok=True)

    def touch(self, folder: str, name: str) -> None:
        """Mark a file changed, so Streamlit runs its open pages again."""
        target = Path(folder) / name
        if target.is_file():
            os.utime(target)

    def write_table(self, folder: str, name: str, data: bytes) -> None:
        target = Path(folder) / "data" / f"{name}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(data)
        os.replace(partial, target)

    def has_table(self, folder: str, name: str) -> bool:
        return (Path(folder) / "data" / f"{name}.parquet").is_file()

    def remove(self, folder: str) -> None:
        if folder in self._made:
            self._made.discard(folder)
            shutil.rmtree(folder, ignore_errors=True)

    def remove_all(self) -> None:
        for folder in list(self._made):
            self.remove(folder)

    def export(
        self, folder: str, files: Mapping[str, str], tables: Mapping[str, bytes]
    ) -> tuple[str, list[str]]:
        """Write an exported app into the folder the user picked (made when it is not there). Its own
        files are replaced; nothing else in the folder is touched. The folder and what was written."""
        try:
            root = Path(folder).expanduser().resolve()
        except OSError as error:
            raise FileNotFoundError(
                f"{folder[:200]} is not a folder this computer can use ({error})."
            ) from None
        if root.exists() and not root.is_dir():
            raise FileNotFoundError(f"{root} is a file: pick a folder.")
        if not root.parent.is_dir():
            raise FileNotFoundError(f"The folder {root.parent} is not there.")
        root.mkdir(exist_ok=True)
        written: list[str] = []
        for name, text in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            written.append(name)
        for name, data in tables.items():
            target = root / "data" / f"{name}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(f"data/{name}.parquet")
        return str(root), sorted(written)
