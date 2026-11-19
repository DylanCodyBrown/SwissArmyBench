"""A team's local copy and this computer's library as files (services/team.py): each file's hash (to compare
two
folders without reading them twice), files copied from one folder to another, a new team's layout written, a
folder made, and Show its folder (the system's file manager, the user's click)."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path


class TeamFiles:
    def __init__(self, show: Callable[[str], None]) -> None:
        self._show = show

    @staticmethod
    def hashes(folder: str) -> dict[str, str]:
        """Every file under the folder (relative slash path -> sha256), .git/ and links left out."""
        root = Path(folder).expanduser()
        out: dict[str, str] = {}
        if not root.is_dir():
            return out
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.is_symlink() or not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return out

    @staticmethod
    def copy(source: str, target: str, paths: list[str]) -> None:
        """Each named file copied from source to the same place under target (folders made)."""
        top, to = Path(source).expanduser(), Path(target).expanduser()
        for rel in paths:
            if rel.startswith("/") or ".." in rel.split("/"):
                continue
            destination = to / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(top / rel, destination)

    @staticmethod
    def write(folder: str, files: dict[str, bytes]) -> None:
        root = Path(folder).expanduser()
        for rel, data in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    @staticmethod
    def make(folder: str) -> None:
        Path(folder).expanduser().mkdir(parents=True, exist_ok=True)

    def show(self, folder: str) -> None:
        self._show(folder)

    @staticmethod
    def under(folder: str, *parts: str) -> str:
        return str(Path(folder).expanduser().joinpath(*parts))

    @staticmethod
    def same(one: str, other: str) -> bool:
        return Path(one).expanduser().resolve() == Path(other).expanduser().resolve()
