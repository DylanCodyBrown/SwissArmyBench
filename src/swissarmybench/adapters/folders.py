"""A folder's contents on this computer, for the page's own file picker (when no system dialog opens:
services/file_dialogs.py). Names, sizes and dates only: nothing is read. Made: the app's own folder, the
first time it is looked at (ensure_own), and a folder the user's New folder names (make_folder).

  places       the picker's side: Home, Desktop, Documents, Downloads (where they are), XDG's names on Linux
  listing      a folder's subfolders, then its files; hidden ones only on request
  make_folder  New folder, inside the folder shown"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path
from typing import Any

MAX_ENTRIES: int = 2_000


def roots() -> list[str]:
    """Where browsing can start: the home folder, and each drive on Windows (/ elsewhere)."""
    if sys.platform == "win32":
        drives = [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
    else:
        drives = ["/"]
    return [str(Path.home()), *drives]


def ensure_own(where: str, own: Path) -> None:
    """Make the app's own folder when `where` is that folder and nothing is there yet (decision 15:
    made the first time it is needed). Any other path is left alone, and so is a file of that name."""
    try:
        asked, mine = Path(where).expanduser().resolve(), own.expanduser().resolve()
        if asked == mine and not mine.exists():
            mine.mkdir(parents=True, exist_ok=True)
    except OSError:
        return  # it cannot be made here: the listing says what is wrong


def _hidden(entry: os.DirEntry[str]) -> bool:
    if entry.name.startswith("."):
        return True
    if sys.platform == "win32":
        try:
            return bool(entry.stat(follow_symlinks=False).st_file_attributes & 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except (OSError, AttributeError):
            return False
    return False


def _xdg_dirs(home: Path) -> dict[str, Path]:
    """Linux's own names for Desktop, Documents and Downloads (~/.config/user-dirs.dirs), where set."""
    found: dict[str, Path] = {}
    try:
        text = (home / ".config" / "user-dirs.dirs").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return found
    for line in text.splitlines():
        key, _, value = line.partition("=")
        value = value.strip().strip('"')
        if key.strip() in ("XDG_DESKTOP_DIR", "XDG_DOCUMENTS_DIR", "XDG_DOWNLOAD_DIR") and value:
            found[key.strip()] = Path(value.replace("$HOME", str(home)))
    return found


def places(home: Path | None = None) -> list[dict[str, str]]:
    """Home, Desktop, Documents and Downloads, each only where it is a folder (OneDrive's on Windows too)."""
    home = home or Path.home()
    xdg = _xdg_dirs(home) if sys.platform.startswith("linux") else {}
    found = [{"name": "Home", "path": str(home), "kind": "home"}]
    for name, key in (
        ("Desktop", "XDG_DESKTOP_DIR"),
        ("Documents", "XDG_DOCUMENTS_DIR"),
        ("Downloads", "XDG_DOWNLOAD_DIR"),
    ):
        candidates = [xdg[key]] if key in xdg else []
        candidates += [home / name, home / "OneDrive" / name] if sys.platform == "win32" else [home / name]
        for candidate in candidates:
            try:
                if candidate.is_dir() and candidate != home:
                    found.append({"name": name, "path": str(candidate), "kind": name.lower()})
                    break
            except OSError:
                continue
    return found


def is_folder(path: str) -> bool:
    try:
        return Path(path).is_dir()
    except OSError:
        return False


def make_folder(parent: str, name: str) -> str:
    """New folder `name` inside `parent` (name checked by domain/file_dialogs.py); its path."""
    try:
        base = Path(parent).expanduser().resolve()
    except OSError as error:
        raise FileNotFoundError(
            f"{parent} is not a folder this computer can open ({error.strerror})."
        ) from None
    if not base.is_dir():
        raise FileNotFoundError(f"{base} is not a folder this computer can open.")
    made = base / name
    try:
        made.mkdir()
    except FileExistsError:
        raise FileExistsError(f"{made} is already there.") from None
    except PermissionError:
        raise PermissionError(f"This computer does not let you make a folder in {base}.") from None
    return str(made)


def listing(where: str | None, suffixes: set[str], hidden: bool = False) -> dict[str, Any]:
    """The folder's subfolders, then its files (only those ending in `suffixes`, when given). Hidden
    names are left out unless `hidden`. A file's path gives its folder."""
    try:
        path = Path(where).expanduser() if where else Path.home()
        if path.is_file():
            path = path.parent
        path = path.resolve()
        found = path.is_dir()
    except OSError as error:  # a name too long, a device not ready: not a folder to open
        raise FileNotFoundError(
            f"{where} is not a folder this computer can open ({error.strerror})."
        ) from None
    if not found:
        raise FileNotFoundError(f"{path} is not a folder this computer can open.")
    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.casefold())
    except PermissionError:
        raise PermissionError(f"This computer does not let you open {path}.") from None
    for entry in entries:
        if (not hidden and _hidden(entry)) or len(folders) + len(files) >= MAX_ENTRIES:
            continue
        try:
            if entry.is_dir():
                modified = entry.stat().st_mtime
                folders.append({"name": entry.name, "path": entry.path, "modified": modified})
            elif entry.is_file() and (not suffixes or Path(entry.name).suffix.lower() in suffixes):
                stat = entry.stat()
                files.append(
                    {"name": entry.name, "path": entry.path, "size": stat.st_size, "modified": stat.st_mtime}
                )
        except OSError:
            continue
    return {
        "path": str(path),
        "parent": str(path.parent) if path.parent != path else None,
        "folders": folders,
        "files": files,
        "roots": roots(),
        "home": str(Path.home()),
        "separator": os.sep,
    }
