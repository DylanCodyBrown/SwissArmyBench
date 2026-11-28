"""The data notebook's files: each notebook's temporary folder (the open tables and connection reads as
Parquet, a result written for Open as grid, a TSX preview's bundle; removed when its kernel stops or the
server ends), a Parquet file read as an Arrow table, and the code app's node_modules looked at (read only).
Nothing here writes into a project: data.ts is written by the project's own files adapter, on Use in app.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


class NotebookFiles:
    def make_folder(self) -> str:
        return tempfile.mkdtemp(prefix="sab-ts-notebook-")

    def remove_folder(self, folder: str) -> None:
        shutil.rmtree(folder, ignore_errors=True)

    def join(self, folder: str, *parts: str) -> str:
        return str(Path(folder, *parts))

    def write_bytes(self, path: str, data: bytes) -> None:
        Path(path).write_bytes(data)

    def write_text(self, path: str, text: str) -> None:
        Path(path).write_text(text, encoding="utf-8", newline="\n")

    def read_text(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None

    def remove(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)

    def is_file(self, path: str) -> bool:
        return Path(path).is_file()

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def folder_of(self, path: str) -> str:
        return str(Path(path).expanduser().resolve().parent)

    def resolve(self, path: str) -> str:
        return str(Path(path).expanduser().resolve())

    def read_parquet(self, path: str) -> Any:
        import pyarrow.parquet as pq

        return pq.read_table(path)

    def write_parquet(self, path: str, table: Any) -> None:
        import pyarrow.parquet as pq

        pq.write_table(table, path)
