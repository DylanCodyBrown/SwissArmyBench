"""The Workbench's files: notebooks and scripts the user opens and saves (on their click only), and the
recent list (the last files opened, kept in the state folder). Nothing else is written."""

from __future__ import annotations

import codecs
import io
import json
import os
import stat
import tempfile
import tokenize
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic

MAX_FILE_BYTES: int = 20 * 1024 * 1024
MAX_RECENT: int = 15


def _encoding_of(raw: bytes, suffix: str) -> str:
    """How a file is written: UTF-8 with its byte-order mark, a script's coding line (PEP 263), else UTF-8."""
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if suffix.lower() == ".py":
        try:
            found, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        except SyntaxError:
            return "utf-8"
        return found
    return "utf-8"


class Documents:
    def __init__(
        self, recent_file: Path, default_folder: Path, environments_file: Path | None = None
    ) -> None:
        self._recent = recent_file
        self.default_folder = default_folder
        # Each document's environment (document path -> its Python), as the user chose or made it.
        self._environments = environments_file or recent_file.with_name("environments.json")

    def made_default_folder(self) -> str:
        """The app's own folder, made the first time it is needed: a document not saved yet runs there."""
        self.default_folder.mkdir(parents=True, exist_ok=True)
        return str(self.default_folder)

    def read(self, path: str) -> tuple[str, str, float]:
        """The file's text, its full path and when it was last changed."""
        try:
            file = Path(path).expanduser().resolve()
            there = file.is_file()
        except OSError as error:
            raise FileNotFoundError(
                f"{path[:200]} is not a file this computer can open ({error.strerror})."
            ) from None
        if not there:
            raise FileNotFoundError(f"{file} is not there.")
        if file.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(
                f"{file.name} is over {MAX_FILE_BYTES // 1024 // 1024} MB: too large to open here."
            )
        raw = file.read_bytes()
        encoding = _encoding_of(raw, file.suffix)
        try:
            # Decoded as it is: line endings kept (CRLF stays CRLF), a byte-order mark taken off.
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as error:
            raise ValueError(f"{file.name} is not readable as {encoding}: {error}") from None
        return text, str(file), file.stat().st_mtime

    def dataset_queries(self, path: str) -> Any:
        """A Power BI dataset's queries read from its file (adapters/m_files.py): New file's import."""
        from swissarmybench.adapters import m_files

        return m_files.read(path)

    def workbooks(self) -> Any:
        """An Excel workbook's file, for its Power Query (adapters/workbook_queries.py)."""
        from swissarmybench.adapters import workbook_queries

        return workbook_queries

    def modified(self, path: str) -> float | None:
        try:
            file = Path(path).expanduser()
            return file.stat().st_mtime if file.is_file() else None
        except OSError:
            return None

    def write(
        self, path: str, text: str, force: bool = False, make_folder: bool = False
    ) -> tuple[str, float]:
        """Write the file whole (a temporary file renamed over it, so a failed save leaves the old one).
        Its folder must exist, except the Workbench's own default folder, made on its first save, and one the
        app makes for its own file (`make_folder`: a project's scripts/ for a table's .sql file)."""
        try:
            file = Path(path).expanduser().resolve()
        except OSError as error:
            raise FileNotFoundError(
                f"{path[:200]} is not a place this computer can save ({error.strerror})."
            ) from None
        if make_folder or file.parent == self.default_folder.resolve():
            file.parent.mkdir(parents=True, exist_ok=True)
        if not file.parent.is_dir():
            raise FileNotFoundError(f"The folder {file.parent} is not there.")
        # A file that is there keeps its encoding (a byte-order mark, a coding line), its permissions, and
        # is replaced only when it may be written (or the user said Save anyway: `force`).
        encoding, mode = "utf-8", None
        if file.is_file():
            # Read-only to its owner: no write permission for this user, or no write bit at all (the
            # read-only attribute; root's os.access says yes regardless).
            no_bits = not file.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            if not force and (no_bits or not os.access(file, os.W_OK)):
                raise PermissionError(f"{file.name} is read-only. Save anyway to replace it.")
            encoding = _encoding_of(file.read_bytes(), file.suffix)
            mode = stat.S_IMODE(file.stat().st_mode)
        try:
            data = text.encode(encoding)
        except UnicodeEncodeError as error:
            raise ValueError(
                f"{file.name} is {encoding}, which cannot hold {error.object[error.start : error.end]!r}."
            ) from None
        write_atomic(file, data, mode=mode)
        return str(file), file.stat().st_mtime

    @staticmethod
    def read_bytes(path: str, most: int) -> bytes:
        """A file's bytes (a picture beside a document); one over `most` is refused."""
        file = Path(path).expanduser()
        if not file.is_file():
            raise FileNotFoundError(path)
        if file.stat().st_size > most:
            raise ValueError(f"{file.name} is over {most // 1_000_000} MB: not shown here.")
        return file.read_bytes()

    @staticmethod
    def write_bytes(path: str, data: bytes) -> tuple[str, bool]:
        """Bytes written beside a document (a diagram's picture), only when they differ; its folder must be
        there. (the whole path, whether it was written)"""
        file = Path(path).expanduser().resolve()
        if not file.parent.is_dir():
            raise FileNotFoundError(f"The folder {file.parent} is not there.")
        if file.is_file() and file.read_bytes() == data:
            return str(file), False
        write_atomic(file, data)
        return str(file), True

    def exists(self, path: str) -> bool:
        try:
            return Path(path).expanduser().is_file()
        except OSError:
            return False

    def move(self, path: str, to: str) -> str:
        """A document renamed (the tab's Rename): the file moved to `to` in the same folder, never over
        another
        one; its recent entry and its remembered Python follow. Its new full path."""
        file = Path(path).expanduser().resolve()
        target = Path(to).expanduser().resolve()
        if not file.is_file():
            raise FileNotFoundError(f"{file} is not there.")
        if target.exists():
            raise FileExistsError(f"{target.name} is there already.")
        file.rename(target)
        listed = [
            {"path": str(target) if r["path"] == str(file) else r["path"], "opened": r["opened"]}
            for r in self.recent()
        ]
        if listed:
            self._recent.write_text(json.dumps(listed[:MAX_RECENT], indent=1), encoding="utf-8")
        chosen = self._chosen()
        if str(file) in chosen:
            chosen[str(target)] = chosen.pop(str(file))
            self._environments.write_text(json.dumps(chosen, indent=1), encoding="utf-8")
        return str(target)

    def scratch(self, text: str) -> str:
        """An unsaved script written to a private folder of its own, so %run can run it as a file."""
        if not hasattr(self, "_scratch"):
            self._scratch = Path(tempfile.mkdtemp(prefix="swissarmybench-script-"))
        file = self._scratch / "untitled.py"
        file.write_text(text, encoding="utf-8")
        return str(file)

    def recent(self) -> list[dict[str, Any]]:
        try:
            listed = json.loads(self._recent.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for item in listed if isinstance(listed, list) else []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                out.append(
                    {
                        "path": item["path"],
                        "opened": item.get("opened", 0),
                        "exists": Path(item["path"]).is_file(),
                    }
                )
        return out[:MAX_RECENT]

    def remember(self, path: str, when: float) -> None:
        kept = [r for r in self.recent() if r["path"] != path]
        listed = [{"path": path, "opened": when}, *({"path": r["path"], "opened": r["opened"]} for r in kept)]
        self._recent.parent.mkdir(parents=True, exist_ok=True)
        self._recent.write_text(json.dumps(listed[:MAX_RECENT], indent=1), encoding="utf-8")

    def _chosen(self) -> dict[str, str]:
        try:
            found = json.loads(self._environments.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}

    def environment(self, path: str) -> str | None:
        """The Python remembered for a document, when it is still there."""
        python = self._chosen().get(str(Path(path).expanduser().resolve()))
        return python if python and Path(python).is_file() else None

    def forget_environment(self, path: str) -> None:
        """A document's own Python is no longer remembered (it runs in its project's one Python now)."""
        chosen = self._chosen()
        if chosen.pop(str(Path(path).expanduser().resolve()), None) is not None:
            self._environments.write_text(json.dumps(chosen, indent=1), encoding="utf-8")

    def remember_environment(self, path: str, python: str) -> None:
        chosen = self._chosen()
        chosen[str(Path(path).expanduser().resolve())] = python
        self._environments.parent.mkdir(parents=True, exist_ok=True)
        self._environments.write_text(json.dumps(chosen, indent=1), encoding="utf-8")
