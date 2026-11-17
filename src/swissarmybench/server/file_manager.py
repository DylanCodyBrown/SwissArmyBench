"""The system's own file manager and trash, for the Project Explorer's Show in folder and Delete and a
blade's Show its file (the user's clicks only: the services refuse the agent). Here because only server/
starts processes.

  show   the folder in Explorer, the Finder, or the desktop's own file manager (xdg-open)
  reveal a file in its folder (a blade's Show its file)
  trash  the folder to the Recycle Bin (SHFileOperationW with FOF_ALLOWUNDO), the Finder's Trash
         (osascript), or the freedesktop Trash (files/ and its .trashinfo): never a plain delete
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path


def trash(folder: str, home: Path | None = None) -> str:
    """The folder moved to the system's trash; where it went, in words."""
    root = Path(folder).resolve()
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


def show(folder: str) -> None:
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606 (the user's own folder, their click)
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([command, folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603


def reveal(path: str) -> None:
    """A file in its folder, selected where the system can (a blade's Show its file): Explorer's /select,
    the Finder's -R, else the desktop's file manager on its folder."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603, S607 (the user's own file, their click)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603, S607
    else:
        show(str(Path(path).parent))


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
