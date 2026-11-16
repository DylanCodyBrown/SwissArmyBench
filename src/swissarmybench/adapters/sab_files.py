"""The .sab file on disk (domain/sab_files.py has the rules; services/sab_projects.py the use cases):
read and unpacked safely, written atomically, and the recent projects' list.

  open      every entry checked before anything is written (names, links, sizes; domain rules), then
            unpacked into a working folder of its own in the system's temporary folder; each entry is
            counted again as it is read, so a zip that lies about its sizes stops at the cap
  save      a temporary file beside the target, then one replace: a crash never leaves half a .sab
  working   a project's working folder (the temporary one is removed when it closes or the server stops)
  recent    recent_projects.json in the state folder: paths and times only

Nothing here is written but at the user's word (Save) or the agent's (its own save, with the user's
Allow when rows go in), and the working folders, which go when the project closes.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import zipfile
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from swissarmybench.domain.sab_files import EntryInfo, SabError, check_entries, check_entry, packed

CHUNK: int = 1024 * 1024
MAX_RECENT: int = 20
WORKING_PREFIX: str = "sab-project-"


def _is_link(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


class SabArchive:
    """Reading and writing .sab files, and the working folders they are unpacked into."""

    def __init__(
        self, max_file_bytes: int, max_entries: int, max_total: int, temp_root: Path | None = None
    ) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_entries = max_entries
        self.max_total = max_total
        self._temp_root = temp_root

    # ===== paths =====

    @staticmethod
    def full(path: str) -> str:
        """A whole path (a relative one would mean the server's own folder: refused)."""
        given = Path(path).expanduser()
        if not given.is_absolute():
            raise FileNotFoundError(
                f"{path[:200]} is not a full path: give the whole path, from the drive or /."
            )
        try:
            return str(given.resolve())
        except OSError as error:
            raise FileNotFoundError(f"{path[:200]} is not a place this computer can use ({error}).") from None

    @staticmethod
    def exists(path: str) -> bool:
        try:
            return Path(path).expanduser().is_file()
        except OSError:
            return False

    @staticmethod
    def is_folder(path: str) -> bool:
        try:
            return Path(path).expanduser().is_dir()
        except OSError:
            return False

    @staticmethod
    def folder_of(path: str) -> str:
        return str(Path(path).expanduser().resolve().parent)

    # ===== open =====

    def _zip(self, path: str) -> zipfile.ZipFile:
        file = Path(path).expanduser()
        if not file.is_file():
            raise FileNotFoundError(f"{file} is not there.")
        if file.stat().st_size > self.max_file_bytes:
            raise SabError(
                f"{file.name} is over {self.max_file_bytes // (1024 * 1024):,} MB: too large to open."
            )
        try:
            return zipfile.ZipFile(file)
        except (zipfile.BadZipFile, OSError):
            raise SabError(f"{file.name} is not a project file (it is not a zip).") from None

    def _checked(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        infos = archive.infolist()
        check_entries(
            [EntryInfo(i.filename, i.file_size, _is_link(i), i.is_dir()) for i in infos],
            self.max_entries,
            self.max_total,
            self.max_total,
        )
        return [i for i in infos if not i.is_dir()]

    def _read(self, archive: zipfile.ZipFile, info: zipfile.ZipInfo, out: Any, budget: list[int]) -> None:
        """One entry, counted as it is read: past its stated size or the whole budget, it stops."""
        seen = 0
        try:
            with archive.open(info) as source:
                while chunk := source.read(CHUNK):
                    seen += len(chunk)
                    budget[0] -= len(chunk)
                    if seen > info.file_size or budget[0] < 0:
                        raise SabError(
                            f"{info.filename[:80]} unpacks to more than it says: it was not opened."
                        )
                    out.write(chunk)
        except (zipfile.BadZipFile, zlib.error, EOFError):
            raise SabError(f"{info.filename[:80]} is damaged in this file: it was not opened.") from None

    def manifest(self, path: str) -> str:
        """project.json's text, every entry checked first."""
        with self._zip(path) as archive:
            self._checked(archive)
            info = archive.getinfo("project.json")
            if info.file_size > 50 * 1024 * 1024:
                raise SabError("Its project.json is too large to read.")
            try:
                return archive.read(info).decode("utf-8-sig")
            except (zipfile.BadZipFile, zlib.error, EOFError, UnicodeDecodeError):
                raise SabError("Its project.json is damaged: it was not opened.") from None

    def unpack(self, path: str, special: set[str], name: str) -> tuple[str, str, dict[str, str]]:
        """Every entry into a working folder of its own: the project's files into its `work` folder, the
        special ones (the Sandbox, the model, rows) beside it. The root (removed on close), the working
        folder, and each special entry's file."""
        root, folder = self.new_folder(name)
        meta = Path(root) / ".meta"  # (a project's own folder name never starts with a dot)
        meta.mkdir()
        try:
            with self._zip(path) as archive:
                budget = [self.max_total]
                found: dict[str, str] = {}
                work = Path(folder).resolve()
                for info in self._checked(archive):
                    entry = check_entry(info.filename)
                    if entry == "project.json":
                        continue
                    if entry in special:
                        target = meta / secrets.token_hex(8)
                        found[entry] = str(target)
                    else:
                        target = (work / entry).resolve()
                        if not target.is_relative_to(work):
                            raise SabError(f"The file holds an entry outside the project ({entry[:80]}).")
                        target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "wb") as out:
                        self._read(archive, info, out, budget)
        except BaseException:
            self.remove(root)
            raise
        return root, folder, found

    # ===== working folders =====

    def new_folder(self, name: str) -> tuple[str, str]:
        """A working folder of its own, named for the project, in a folder of the system's temporary
        folder: that root (removed when the project closes) and the working folder."""
        base = self._temp_root or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix=WORKING_PREFIX, dir=base))
        named = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name).strip(" .") or "project"
        work = root / named[:60]
        work.mkdir()
        return str(root), str(work)

    @staticmethod
    def remove(root: str | None) -> None:
        if root and Path(root).name.startswith(WORKING_PREFIX):
            shutil.rmtree(root, ignore_errors=True)

    def files(self, folder: str) -> list[tuple[str, int, float]]:
        """The working folder's files that go into the .sab: path inside it, size, last change."""
        root = Path(folder)
        found: list[tuple[str, int, float]] = []
        if not root.is_dir():
            return found
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            here = Path(dirpath)
            dirnames[:] = sorted(d for d in dirnames if not (here / d).is_symlink())
            for file_name in sorted(filenames):
                file = here / file_name
                relative = file.relative_to(root).as_posix()
                if file.is_symlink() or not packed(relative):
                    continue
                try:
                    facts = file.stat()
                except OSError:
                    continue
                found.append((relative, facts.st_size, facts.st_mtime))
                if len(found) >= self.max_entries:
                    return found
        return found

    @staticmethod
    def read_file(folder: str, relative: str) -> bytes:
        return (Path(folder) / relative).read_bytes()

    @staticmethod
    def read_text(path: str) -> str:
        return Path(path).read_bytes().decode("utf-8-sig")

    # ===== rows =====

    @staticmethod
    def write_rows(folder: str, table: pa.Table) -> str:
        """A table's rows as a Parquet file in `folder` (the save's own temporary one)."""
        target = Path(folder) / f"{secrets.token_hex(8)}.parquet"
        pq.write_table(table, target)
        return str(target)

    @staticmethod
    def read_rows(path: str) -> pa.Table:
        return pq.read_table(path)

    @staticmethod
    def scratch() -> str:
        return tempfile.mkdtemp(prefix=WORKING_PREFIX)

    # ===== save: atomic =====

    def write(self, target: str, entries: Sequence[tuple[str, bytes | str]]) -> str:
        """The .sab at `target` (its folder must be there): a temporary file beside it, then one replace.
        Each entry is bytes, or the path of a file to copy in."""
        file = Path(target).expanduser().resolve()
        if not file.parent.is_dir():
            raise FileNotFoundError(f"The folder {file.parent} is not there.")
        if file.is_dir():
            raise FileNotFoundError(f"{file} is a folder: name a .sab file.")
        if file.exists() and not os.access(file, os.W_OK):
            raise PermissionError(f"{file} is read-only.")
        partial = file.with_name(f".{file.name}.{secrets.token_hex(4)}.saving")
        try:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
                for name, body in entries:
                    entry = check_entry(name)
                    if isinstance(body, bytes):
                        out.writestr(entry, body)
                    else:
                        out.write(body, entry)
            with open(partial, "rb+") as written:
                os.fsync(written.fileno())
            os.replace(partial, file)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return str(file)


class RecentProjects:
    """recent_projects.json in the state folder: the last projects opened or saved, paths and times only.
    None: kept in memory (a test's server without state files)."""

    def __init__(self, file: Path | None) -> None:
        self._file = file
        self._memory: list[dict[str, Any]] = []

    def _read(self) -> list[dict[str, Any]]:
        if self._file is None:
            return list(self._memory)
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        listed = raw if isinstance(raw, list) else []
        return [
            {"path": r["path"], "opened": float(r.get("opened") or 0)}
            for r in listed
            if isinstance(r, dict)
            and isinstance(r.get("path"), str)
            and isinstance(r.get("opened", 0), int | float)
        ]

    def _write(self, listed: list[dict[str, Any]]) -> None:
        listed = listed[:MAX_RECENT]
        if self._file is None:
            self._memory = listed
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        partial = self._file.with_name(f".{self._file.name}.saving")
        partial.write_text(json.dumps(listed, indent=1), encoding="utf-8")
        os.replace(partial, self._file)

    def all(self) -> list[dict[str, Any]]:
        """Each one with whether its file is still there."""
        return [r | {"exists": SabArchive.exists(r["path"])} for r in self._read()]

    def add(self, path: str, when: float) -> None:
        self._write([{"path": path, "opened": when}, *(r for r in self._read() if r["path"] != path)])

    def remove(self, path: str) -> bool:
        before = self._read()
        after = [r for r in before if r["path"] != path]
        self._write(after)
        return len(after) < len(before)
