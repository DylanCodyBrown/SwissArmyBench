"""The Project Explorer on disk (domain/project_explorer.py has the rules; services/project_explorer.py the
use cases): projects.json, the projects folder's projects, each project's facts, and the user's own clicks
on a folder (show it in the system's file manager, rename it, move it to the trash).

  settings  projects.json in the state folder (None: in memory, a test's server without state files)
  scan      the projects folder's subfolders that are projects (.sab/project.json, or the scaffold's
            data.ipynb)
  facts     a project's type, documents, tables, Git (.git/HEAD read as text: git itself never runs), its
            folder's created and last changed times
  show      the folder in the system's file manager (Explorer, Finder, the desktop's own): the user's click
  trash     the folder to the system's trash (the Recycle Bin, the Finder's Trash, the desktop's Trash), never
            deleted outright: the user's click and typed name only

Nothing is written here but projects.json (the user's sort, order and folder), a rename the user asked for,
and a move to the trash the user confirmed by typing the project's name.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from swissarmybench.domain import project_scope
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain.project_explorer import read_settings, write_settings
from swissarmybench.domain.sab_files import MANIFEST_PATH, is_project, packed

MAX_SCANNED: int = 500  # projects in the projects folder
MAX_FILES: int = 2_000  # a project's files looked at for its card
_SKIPPED = frozenset({"__pycache__", "venv", "node_modules"})


class ExplorerSettings:
    """projects.json: the projects folder, the custom order, the sort, the hidden ones, the strip put away."""

    def __init__(self, file: Path | None) -> None:
        self._file = file
        self._memory: dict[str, Any] = {}

    def read(self) -> dict[str, Any]:
        if self._file is None:
            return read_settings(self._memory)
        try:
            return read_settings(json.loads(self._file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return read_settings({})

    def write(self, settings: dict[str, Any]) -> None:
        if self._file is None:
            self._memory = dict(settings)
            return
        text = write_settings(settings)
        try:
            if self._file.read_text(encoding="utf-8") == text:
                return
        except OSError:
            pass
        self._file.parent.mkdir(parents=True, exist_ok=True)
        partial = self._file.with_name(f".{self._file.name}.saving")
        partial.write_text(text, encoding="utf-8")
        os.replace(partial, self._file)


def _top(folder: Path) -> list[str]:
    try:
        names = [e.name for e in os.scandir(folder) if e.is_file()]
    except OSError:
        return []
    if (folder / MANIFEST_PATH).is_file():
        names.append(MANIFEST_PATH)
    return names


def _files(root: Path) -> list[tuple[str, int, float]]:
    """The project's own documents (path in it, size, last change), at most MAX_FILES."""
    found: list[tuple[str, int, float]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in ("__pycache__", "venv", "node_modules")
        )
        for name in sorted(filenames):
            relative = (here / name).relative_to(root).as_posix()
            if not packed(relative):
                continue
            try:
                facts = (here / name).stat()
            except OSError:
                continue
            found.append((relative, facts.st_size, facts.st_mtime))
            if len(found) >= MAX_FILES:
                return found
    return found


def _git_head(root: Path) -> tuple[bool, str | None]:
    """Is it a repository, and .git/HEAD's text (a worktree's .git file followed to its own HEAD)."""
    git = root / ".git"
    try:
        if git.is_dir():
            return True, (git / "HEAD").read_text(encoding="utf-8", errors="replace")[:400]
        if git.is_file():
            said = git.read_text(encoding="utf-8", errors="replace")[:2000].strip()
            if said.startswith("gitdir:"):
                place = Path(said[7:].strip())
                place = place if place.is_absolute() else (root / place)
                return True, (place / "HEAD").read_text(encoding="utf-8", errors="replace")[:400]
            return True, None
    except OSError:
        return git.exists(), None
    return False, None


class ExplorerFiles:
    """The projects on disk, and the user's clicks on a project's folder."""

    def __init__(self, opener: Callable[[str], None] | None = None) -> None:
        self._opener = opener or _show_in_file_manager

    @staticmethod
    def full(path: str) -> str:
        given = Path(path).expanduser()
        if not given.is_absolute():
            raise FileNotFoundError(
                f"{path[:200]} is not a full path: give the whole path, from the drive or /."
            )
        return str(given.resolve())

    @staticmethod
    def is_folder(path: str) -> bool:
        try:
            return Path(path).is_dir()
        except OSError:
            return False

    @staticmethod
    def scan(folder: str) -> list[str]:
        """The projects folder's projects: its subfolders that are projects."""
        root = Path(folder).expanduser()
        try:
            children = sorted(e.path for e in os.scandir(root) if e.is_dir() and not e.name.startswith("."))
        except OSError:
            return []
        return [str(Path(c).resolve()) for c in children if is_project(_top(Path(c)))][:MAX_SCANNED]

    @staticmethod
    def facts(folder: str) -> dict[str, Any] | None:
        """A project's facts for its card (None: the folder is not there)."""
        root = Path(folder)
        if not root.is_dir():
            return None
        files = _files(root)
        manifest: dict[str, Any] = {}
        state = root / MANIFEST_PATH
        try:
            raw = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
            manifest = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            manifest = {}
        tables = manifest.get("tables")
        repository, head = _git_head(root)
        try:
            facts = root.stat()
            created = float(getattr(facts, "st_birthtime", 0) or facts.st_ctime)
        except OSError:
            created = None
        times = [m for _, _, m in files]
        try:
            times.append(state.stat().st_mtime)
        except OSError:
            pass
        return {
            "type": project_rules.check_type(manifest.get("type"))
            if isinstance(manifest.get("type"), str)
            else "bi",
            "documents": project_scope.documents(files),
            "tables": len(tables) if isinstance(tables, list) else 0,
            "repository": repository,
            "head": head,
            "changed": max(times) if times else created,
            "created": created,
        }

    @staticmethod
    def rename(folder: str, name: str) -> str:
        """The project's folder renamed in place (its parent kept); refused when the name is taken."""
        root = Path(folder)
        if not root.is_dir():
            raise FileNotFoundError(f"{root} is not there.")
        target = root.with_name(name)
        if target.exists():
            raise FileExistsError(f"{target} is there already: pick another name.")
        root.rename(target)
        return str(target)

    def show(self, folder: str) -> None:
        if not Path(folder).is_dir():
            raise FileNotFoundError(f"{folder} is not there.")
        self._opener(folder)

    @staticmethod
    def trash(folder: str, home: Path | None = None) -> str:
        """The folder moved to the system's trash; where it went, in words."""
        root = Path(folder).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"{root} is not there.")
        if sys.platform == "win32":
            _windows_recycle(str(root))
            return "the Recycle Bin"
        if sys.platform == "darwin":
            script = 'tell application "Finder" to delete POSIX file "{}"'.format(
                str(root).replace("\\", "\\\\").replace('"', '\\"')
            )
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=60)  # noqa: S603, S607
            return "the Trash"
        return _freedesktop_trash(root, home)


def _show_in_file_manager(folder: str) -> None:
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606 (the user's own folder, their click)
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([command, folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603


def _windows_recycle(path: str) -> None:
    """SHFileOperationW with FOF_ALLOWUNDO: the Recycle Bin, never a plain delete."""
    import ctypes
    from ctypes import wintypes

    class _Op(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    op = _Op(None, 3, path + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))  # type: ignore[attr-defined]
    if result != 0 or op.fAnyOperationsAborted:
        raise OSError(f"{path} could not be moved to the Recycle Bin (code {result}).")


def _freedesktop_trash(root: Path, home: Path | None) -> str:
    """The desktop's Trash (the freedesktop.org specification): files/ and its .trashinfo."""
    base = Path(os.environ.get("XDG_DATA_HOME") or ((home or Path.home()) / ".local" / "share")) / "Trash"
    files, info = base / "files", base / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    name, n = root.name, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        n += 1
        name = f"{root.name}.{n}"
    stamp = datetime.fromtimestamp(time.time()).strftime("%Y-%m-%dT%H:%M:%S")
    (info / f"{name}.trashinfo").write_text(
        f"[Trash Info]\nPath={urllib.parse.quote(str(root))}\nDeletionDate={stamp}\n", encoding="utf-8"
    )
    try:
        os.rename(root, files / name)
    except OSError:
        import shutil

        shutil.move(str(root), str(files / name))
    return "the Trash"
