"""A project folder on disk (domain/sab_files.py has the rules; services/sab_projects.py the use cases):
its .sab/ state written only when its bytes change, its documents listed, a copy, and the recent projects'
list.

  state     .sab/project.json, visualizations.json, model.json, data/<table>.parquet: each written
            atomically (a temporary file beside it, then one replace), and only when its bytes differ
  files     the project's own documents (code and text: never data, never .sab/, no environments)
  copy      Copy project to: the folder copied (.sab/data/ and sandbox/ only on a tick; no environments)
  recent    recent_projects.json in the state folder: folder paths and times only

Nothing here is written but at the user's word (Save, Autosave, New project, Copy project to, Import)
or the agent's (its own, with the user's Allow when rows are kept).
"""

from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from swissarmybench.adapters.atomic_files import write_atomic
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
    SabError,
    check_entry,
    packed,
    readme,
)

MAX_RECENT: int = 100


class SabArchive:
    """A project's folder on disk. `max_entries`: the most files listed; `max_total`: the largest read."""

    def __init__(self, max_entries: int, max_total: int) -> None:
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

    def files(self, folder: str) -> list[tuple[str, int, float]]:
        """The project's own files in its folder: path inside it, size, last change."""
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

    def structure_files(self, folder: str) -> list[str]:
        """The JSON, YAML, XML and TOML files at the project's top and in its structures/ folder (paths inside
        it): the code pages' Files pane opens each as a tab beside the code. Hidden ones left out."""
        root = Path(folder)
        found: list[str] = []
        suffixes = (".json", ".yaml", ".yml", ".xml", ".toml")
        places = [root, *([root / "structures"] if (root / "structures").is_dir() else [])]
        for place in places:
            walk = place.rglob("*") if place != root else place.iterdir()
            for file in sorted(walk):
                if len(found) >= self.max_entries:
                    return found
                try:
                    if file.is_symlink() or not file.is_file() or not file.name.lower().endswith(suffixes):
                        continue
                except OSError:
                    continue
                relative = file.relative_to(root).as_posix()
                if not any(part.startswith(".") for part in relative.split("/")):
                    found.append(relative)
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

    # ===== another project's files, for an import =====

    def read_loose(self, path: str) -> bytes:
        """A file outside the project (a notebook to import), at most the largest file read."""
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
        write_atomic(target, body)
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
        if target.is_file() and not os.access(target, os.W_OK) and target.read_bytes() != body:
            raise PermissionError(f"{target} is read-only.")
        return write_atomic(target, body, if_changed=True)

    def remove_state(self, folder: str, relative: str) -> bool:
        """One of the app's own files in .sab/ taken away (Visualizations emptied, a row tick taken off)."""
        if not check_entry(relative).startswith(APP_FOLDER + "/"):
            raise SabError(f"{relative[:80]} is not the app's own.")
        target = self._inside(folder, relative)
        if target.is_file():
            target.unlink()
            return True
        return False

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
    def copy_project(source: str, target: str, data: bool, git: bool = True, copied_from: str = "") -> str:
        """Copy project to: the whole folder into `target` (a new or empty folder), its .sab/data and its
        sandbox/ (the sandbox's rows) only when `data`; environments and caches stay behind (they are this
        computer's). `git` False: its .git too
        (Share and Make a local copy). `copied_from`: written into the copy's .sab/project.json."""
        root = Path(source).expanduser().resolve()
        into = Path(target).expanduser().resolve()
        if into == root or into.is_relative_to(root):
            raise FileExistsError("Copy the project to a folder outside it.")
        if into.exists() and (not into.is_dir() or any(into.iterdir())):
            raise FileExistsError(f"{into} is not empty: pick a new or empty folder.")
        leave = {"__pycache__", ".venv", "venv", "node_modules", ".ipynb_checkpoints", ".mypy_cache"}
        if not git:
            leave.add(".git")

        def ignored(where: str, names: list[str]) -> set[str]:
            here = Path(where).resolve()
            skipped = {n for n in names if n in leave or n.endswith(".saving")}
            if not data and here == root / APP_FOLDER:
                skipped.add("data")
            if not data and here == root and "sandbox" in names:
                skipped.add("sandbox")  # the sandbox's rows travel only on the same tick as .sab/data
            return skipped

        into.parent.mkdir(parents=True, exist_ok=True)
        if into.exists():
            into.rmdir()
        shutil.copytree(root, into, symlinks=True, ignore=ignored)
        if copied_from:
            manifest = into / APP_FOLDER / "project.json"
            try:
                raw = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
            except (OSError, ValueError):
                raw = {}
            raw = (raw if isinstance(raw, dict) else {}) | {"copied_from": copied_from}
            manifest.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(raw, indent=1, ensure_ascii=False, sort_keys=True, default=str) + "\n"
            manifest.write_text(text, encoding="utf-8", newline="\n")
        return str(into)


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
        write_atomic(self._file, json.dumps(listed, indent=1))

    def all(self) -> list[dict[str, Any]]:
        """Each one with whether its folder is still there."""
        return [r | {"exists": SabArchive.is_folder(r["path"])} for r in self._read()]

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
