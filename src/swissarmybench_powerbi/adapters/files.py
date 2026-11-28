"""Export to Power BI's files (domain/export.py makes their bytes): the export's folder in the open
project (`powerbi/`), each file written atomically and only when its bytes change, an earlier export's stale
files removed, the zip of the same folder for a download, and the .pbip opened with its program on the user's
click (else its folder shown).
"""

from __future__ import annotations

import io
import os
import secrets
import sys
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic

MAX_FILES: int = 5_000  # files an export's folder is looked through for


def _inside(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or ".." in relative.split("/") or relative.startswith("/"):
        raise ValueError(f"{relative[:80]} is outside the export's folder.")
    return target


def existing(folder: str) -> list[str]:
    """The files under the export's folder, '/' separated (none when it is not there)."""
    root = Path(folder)
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            found.append(path.relative_to(root).as_posix())
            if len(found) >= MAX_FILES:
                break
    return sorted(found)


def write(folder: str, files: Mapping[str, bytes]) -> list[str]:
    """Each file written whole (a temporary file beside it, then replaced) when its bytes differ; the ones
    written."""
    root = Path(folder).resolve()
    written: list[str] = []
    for relative in sorted(files):
        if write_atomic(_inside(root, relative), files[relative], if_changed=True):
            written.append(relative)
    return written


def remove(folder: str, paths: list[str]) -> None:
    """An earlier export's files this one no longer writes (and their folders, when emptied)."""
    root = Path(folder).resolve()
    for relative in paths:
        target = _inside(root, relative)
        if target.is_file():
            target.unlink()
        parent = target.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def zipped(files: Mapping[str, bytes], top: str) -> bytes:
    """The same folder as one zip (entries under `top`/, a fixed date: the same model, the same bytes)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):
            info = zipfile.ZipInfo(f"{top}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[relative])
    return out.getvalue()


def save_zip(folder: str, name: str, data: bytes) -> str:
    """The zip saved in the export folder (the agent's export with no project open)."""
    root = Path(folder).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    partial = target.with_name(f".{target.name}.{secrets.token_hex(4)}.saving")
    partial.write_bytes(data)
    os.replace(partial, target)
    return str(target)


def has_program(path: str) -> bool:
    """Whether a .pbip opens with a program here: Windows with Power BI Desktop's .pbip registered."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".pbip"):
            return True
    except OSError:
        return False


def open_file(path: str, show: Callable[[str], None]) -> str:
    """The .pbip opened with its program ("opened"), else its folder shown ("shown"). The user's click
    only."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"{target} is not there.")
    if has_program(path):
        os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606 (the user's own file, their click)
        return "opened"
    show(str(target.parent))
    return "shown"


class StateFiles:
    """A Power BI project's own small files (.sab/powerbi.json, data.ipynb): read whole, written atomically
    and
    only when their bytes change."""

    def read_text(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_text(self, path: str, text: str) -> bool:
        return write_atomic(path, text, if_changed=True)
