"""A project folder on disk (domain/sab_files.py has the rules; services/sab_projects.py the use cases):
its .sab/ state written only when its bytes change, its documents listed, a copy, an old .sab file read
safely and unpacked into a folder (the import), and the recent projects' list.

  state     .sab/project.json, visualizations.json, model.json, data/<table>.parquet: each written
            atomically (a temporary file beside it, then one replace), and only when its bytes differ
  files     the project's own documents (code and text: never data, never .sab/, no environments)
  copy      Copy project to: the folder copied (.sab/data/ only on a tick; caches and environments left)
  import    an old .sab: every entry checked before anything is written (names, links, sizes; domain
            rules), then unpacked into an empty folder; each entry counted again as it is read, so a zip
            that lies about its sizes stops at the cap
  recent    recent_projects.json in the state folder: folder paths and times only

Nothing here is written but at the user's word (Save, Autosave, New project, Copy project to, the import)
or the agent's (its own, with the user's Allow when rows are kept).
"""

from __future__ import annotations

import io
import json
import os
import secrets
import shutil
import stat
import zipfile
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from swissarmybench.domain.project_scope import APP_FOLDER, app_entry
from swissarmybench.domain.sab_files import (
    APP_GITIGNORE,
    APP_IGNORE_FILE,
    DASHBOARDS_FOLDER,
    GITIGNORE,
    GITIGNORE_FILE,
    MANIFEST_PATH,
    OLD_DASHBOARDS_FOLDER,
    README_FILE,
    EntryInfo,
    SabError,
    check_entries,
    check_entry,
    packed,
    readme,
)

CHUNK: int = 1024 * 1024
MAX_RECENT: int = 100


class _Sink:
    """An entry read into memory (an import's few small files)."""

    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, chunk: bytes) -> None:
        self.data += chunk


def _is_link(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


class SabArchive:
    """A project's folder on disk, and an old .sab file read safely (the import)."""

    def __init__(self, max_file_bytes: int, max_entries: int, max_total: int) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_entries = max_entries
        self.max_total = max_total

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
    def join(folder: str, name: str) -> str:
        return str(Path(folder).expanduser() / name)

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

    def app_files(self, folder: str) -> list[tuple[str, int, float]]:
        """The project's own definitions in its working folder (domain/project_scope.py): .sab/blades and
        .sab/dashboards' JSON files, path inside the folder, size, last change."""
        root = Path(folder)
        found: list[tuple[str, int, float]] = []
        app = root / APP_FOLDER
        if not app.is_dir() or app.is_symlink():
            return found
        for file in sorted(app.glob("*/*.json")):
            relative = file.relative_to(root).as_posix()
            if file.is_symlink() or not app_entry(relative):
                continue
            try:
                facts = file.stat()
            except OSError:
                continue
            found.append((relative, facts.st_size, facts.st_mtime))
            if len(found) >= self.max_entries:
                break
        return found

    # ===== another project's entries, for an import =====

    def entry_names(self, path: str) -> list[str]:
        """Every file entry of a .sab (each one checked first)."""
        with self._zip(path) as archive:
            return [check_entry(i.filename) for i in self._checked(archive)]

    def read_entries(self, path: str, names: Sequence[str]) -> dict[str, bytes]:
        """Some entries of a .sab, each counted as it is read (a zip that lies about its sizes stops)."""
        wanted = set(names)
        found: dict[str, bytes] = {}
        with self._zip(path) as archive:
            budget = [self.max_total]
            for info in self._checked(archive):
                entry = check_entry(info.filename)
                if entry in wanted:
                    sink = _Sink()
                    self._read(archive, info, sink, budget)
                    found[entry] = bytes(sink.data)
        return found

    def read_loose(self, path: str) -> bytes:
        """A file outside the project (a notebook to import), at most the largest entry a .sab takes."""
        file = Path(path).expanduser()
        if not file.is_file():
            raise FileNotFoundError(f"{file} is not there.")
        if file.stat().st_size > self.max_total:
            raise SabError(f"{file.name} is too large to import.")
        return file.read_bytes()

    @staticmethod
    def write_into(folder: str, relative: str, body: bytes) -> str:
        """A file copied into the project's working folder (never outside it); its whole path."""
        root = Path(folder).resolve()
        target = (root / check_entry(relative)).resolve()
        if not target.is_relative_to(root):
            raise SabError(f"{relative[:80]} is outside the project.")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{target.name}.{secrets.token_hex(4)}.saving")
        partial.write_bytes(body)
        os.replace(partial, target)
        return str(target)

    @staticmethod
    def read_file(folder: str, relative: str) -> bytes:
        return (Path(folder) / relative).read_bytes()

    @staticmethod
    def read_text(path: str) -> str:
        return Path(path).read_bytes().decode("utf-8-sig")

    # ===== rows =====

    @staticmethod
    def read_rows(path: str) -> pa.Table:
        return pq.read_table(path)

    # ===== a project folder's .sab/ state: written only when its bytes change =====

    @staticmethod
    def _inside(folder: str, relative: str) -> Path:
        root = Path(folder).expanduser().resolve()
        target = (root / check_entry(relative)).resolve()
        if not target.is_relative_to(root):
            raise SabError(f"{relative[:80]} is outside the project.")
        return target

    def read_state(self, folder: str, relative: str) -> bytes | None:
        """A file of the project's (its .sab/project.json, say) as bytes; None when it is not there."""
        target = self._inside(folder, relative)
        if not target.is_file() or target.is_symlink():
            return None
        if target.stat().st_size > self.max_total:
            raise SabError(f"{relative[:80]} is too large to read.")
        return target.read_bytes()

    def write_state(self, folder: str, relative: str, body: bytes) -> bool:
        """A file of the project's written whole, only when its bytes differ (a save that changes nothing
        changes no byte): a temporary file beside it, then one replace. True when it was written."""
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"The project's folder {root} is not there.")
        target = self._inside(folder, relative)
        if target.is_file():
            if target.stat().st_size == len(body) and target.read_bytes() == body:
                return False
            if not os.access(target, os.W_OK):
                raise PermissionError(f"{target} is read-only.")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{target.name}.{secrets.token_hex(4)}.saving")
        try:
            partial.write_bytes(body)
            os.replace(partial, target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return True

    def remove_state(self, folder: str, relative: str) -> bool:
        """One of the app's own files in .sab/ taken away (Visualizations emptied, a row tick taken off)."""
        if not check_entry(relative).startswith(APP_FOLDER + "/"):
            raise SabError(f"{relative[:80]} is not the app's own.")
        target = self._inside(folder, relative)
        if target.is_file():
            target.unlink()
            return True
        return False

    def state_names(self, folder: str, sub: str) -> list[str]:
        """The files directly in one of .sab/'s folders (data, visualizations), as paths in the project."""
        place = self._inside(folder, sub)
        if not place.is_dir() or place.is_symlink():
            return []
        return sorted(f"{sub}/{p.name}" for p in place.iterdir() if p.is_file() and not p.is_symlink())

    @staticmethod
    def rows_bytes(table: pa.Table) -> bytes:
        """A table's rows as Parquet (the same rows, the same bytes)."""
        sink = io.BytesIO()
        pq.write_table(table, sink)
        return sink.getvalue()

    def move_old_dashboards(self, folder: str) -> bool:
        """A project from before folders keeps its saved dashboards in .sab/dashboards: moved once into
        .sab/visualizations (when that is not there yet)."""
        old = self._inside(folder, OLD_DASHBOARDS_FOLDER)
        new = self._inside(folder, DASHBOARDS_FOLDER)
        if old.is_dir() and not old.is_symlink() and not new.exists():
            old.rename(new)
            return True
        return False

    def ensure_ignored(self, folder: str, name: str) -> list[str]:
        """The scaffold's Git files: .sab/.gitignore (the app's: always), and the project's .gitignore and
        README.md only when it has none (a file there is never written over). The ones written."""
        written: list[str] = []
        if self.write_state(folder, APP_IGNORE_FILE, APP_GITIGNORE.encode("utf-8")):
            written.append(APP_IGNORE_FILE)
        for relative, text in ((GITIGNORE_FILE, GITIGNORE), (README_FILE, readme(name))):
            target = self._inside(folder, relative)
            if not target.exists():
                self.write_state(folder, relative, text.encode("utf-8"))
                written.append(relative)
        return written

    # ===== a project's folder: what it is, a new one, a copy =====

    @staticmethod
    def top_names(folder: str) -> list[str]:
        """The folder's own files by name, and .sab/project.json when it is there (is it a project?)."""
        root = Path(folder).expanduser()
        try:
            names = [e.name for e in os.scandir(root) if e.is_file()]
        except OSError:
            return []
        if (root / MANIFEST_PATH).is_file():
            names.append(MANIFEST_PATH)
        return sorted(names)

    @staticmethod
    def empty_folder(path: str) -> str:
        """A new project's folder: made (with its parents), or one that is there and empty. Refused in
        words for a file, or a folder that holds something (open it as a project instead)."""
        target = Path(path).expanduser().resolve()
        if target.exists() and not target.is_dir():
            raise FileExistsError(f"{target} is a file: pick a folder.")
        if target.is_dir() and any(target.iterdir()):
            raise FileExistsError(f"{target} is not empty: pick an empty folder, or open it as a project.")
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    @staticmethod
    def copy_project(source: str, target: str, data: bool) -> str:
        """Copy project to: the whole folder into `target` (a new or empty folder), its .sab/data only when
        `data`; environments and caches stay behind (they are this computer's)."""
        root = Path(source).expanduser().resolve()
        into = Path(target).expanduser().resolve()
        if into == root or into.is_relative_to(root):
            raise FileExistsError("Copy the project to a folder outside it.")
        if into.exists() and (not into.is_dir() or any(into.iterdir())):
            raise FileExistsError(f"{into} is not empty: pick a new or empty folder.")
        leave = {"__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints", ".mypy_cache"}

        def ignored(where: str, names: list[str]) -> set[str]:
            here = Path(where).resolve()
            skipped = {n for n in names if n in leave or n.endswith(".saving")}
            if not data and here == root / APP_FOLDER:
                skipped.add("data")
            return skipped

        into.parent.mkdir(parents=True, exist_ok=True)
        if into.exists():
            into.rmdir()
        shutil.copytree(root, into, symlinks=True, ignore=ignored)
        return str(into)

    # ===== an old .sab file imported into a folder =====

    def unpack_into(self, path: str, folder: str, place: Callable[[str], str | None]) -> dict[str, str]:
        """Every entry of an old .sab (each checked first) into `folder` (made, or empty): a project file at
        its own path, the app's own entries where `place` says ("": not written, the manifest). Each old
        entry's new path."""
        target = Path(self.empty_folder(folder))
        found: dict[str, str] = {}
        try:
            with self._zip(path) as archive:
                budget = [self.max_total]
                for info in self._checked(archive):
                    entry = check_entry(info.filename)
                    where = place(entry)
                    if where == "":
                        continue
                    out = self._inside(str(target), where or entry)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with open(out, "wb") as sink:
                        self._read(archive, info, sink, budget)
                    found[entry] = where or entry
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return found


class RecentProjects:
    """recent_projects.json in the state folder: the projects opened (their folders), paths and times only.
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
        """Each one with whether its folder is still there (an old .sab file: `sab`, to import)."""
        return [
            r | {"exists": SabArchive.is_folder(r["path"]), "sab": SabArchive.exists(r["path"])}
            for r in self._read()
        ]

    def replace(self, old: str, new: str) -> bool:
        """A project moved or renamed: its entry follows (Locate…, Rename)."""
        listed = self._read()
        if not any(r["path"] == old for r in listed):
            return False
        moved = [r | {"path": new} if r["path"] == old else r for r in listed if r["path"] != new]
        self._write(moved)
        return True

    def add(self, path: str, when: float) -> None:
        self._write([{"path": path, "opened": when}, *(r for r in self._read() if r["path"] != path)])

    def remove(self, path: str) -> bool:
        before = self._read()
        after = [r for r in before if r["path"] != path]
        self._write(after)
        return len(after) < len(before)
