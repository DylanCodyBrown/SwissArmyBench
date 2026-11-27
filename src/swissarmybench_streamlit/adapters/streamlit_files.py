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

from swissarmybench.adapters.atomic_files import write_atomic

PREFIX: str = "swissarmybench-streamlit-"


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
            # Whole or not at all: a page is never read half written.
            write_atomic(root / name, text.encode("utf-8"), if_changed=True)
        for old in root.glob("*.py"):
            if old.name not in files and old.name not in keep:
                old.unlink(missing_ok=True)

    def touch(self, folder: str, name: str) -> None:
        """Mark a file changed, so Streamlit runs its open pages again."""
        target = Path(folder) / name
        if target.is_file():
            os.utime(target)

    def write_table(self, folder: str, name: str, data: bytes) -> bool:
        """A table's Parquet in the run's data/, written only when its bytes changed (so the page, which
        reads it again only when its file changed, keeps what it read): whether it was written."""
        return write_atomic(Path(folder) / "data" / f"{name}.parquet", data, if_changed=True)

    def drop_table(self, folder: str, name: str) -> bool:
        """A table's Parquet taken away (its table is no longer open): whether there was one."""
        target = Path(folder) / "data" / f"{name}.parquet"
        if not target.is_file():
            return False
        target.unlink(missing_ok=True)
        return True

    def read(self, folder: str, name: str) -> str | None:
        """A small file the live app wrote in its folder (its session's state); None: not there yet."""
        if folder not in self._made:
            return None
        try:
            return (Path(folder) / name).read_text(encoding="utf-8")[:1_000_000]
        except (OSError, UnicodeDecodeError):
            return None

    def has_table(self, folder: str, name: str) -> bool:
        return (Path(folder) / "data" / f"{name}.parquet").is_file()

    def remove(self, folder: str) -> None:
        if folder in self._made:
            self._made.discard(folder)
            shutil.rmtree(folder, ignore_errors=True)

    @staticmethod
    def export_target(folder: str) -> str:
        """The full path an export into `folder` writes to (what the agent's approval names), checked:
        a folder, or a new one in a folder that is there."""
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
        return str(root)

    def export(
        self, chosen: str, files: Mapping[str, str], tables: Mapping[str, bytes]
    ) -> tuple[str, list[str]]:
        """Write an exported app into `chosen` (export_target's: the folder the user picked or
        approved; made when it is not there). Its own files are replaced; nothing else in the folder
        is touched. The folder and what was written. A target that no longer resolves to itself (a
        link put in its place since) is refused before anything is written."""
        root = Path(self.export_target(chosen))
        if str(root) != chosen:
            raise PermissionError(f"{chosen} has changed since it was chosen: nothing was written.")
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


def parquet_of(table: object) -> bytes:
    """An Arrow table as Parquet's bytes (a connection's table read for a run: data/<stem>.parquet)."""
    import io

    import pyarrow.parquet as pq

    out = io.BytesIO()
    pq.write_table(table, out)
    return out.getvalue()
