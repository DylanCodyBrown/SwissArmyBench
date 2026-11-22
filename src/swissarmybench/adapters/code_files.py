"""Code files on disk for services/code_files.py: a file's stamp and hash, a folder's code files."""

from __future__ import annotations

import hashlib
from pathlib import Path

Stamp = tuple[int, int]
MAX_WATCHED = 4000
_ENDINGS = (".py", ".ipynb")
# A project's structure files (a tab beside the code follows them as a script's): its top, structures/.
_STRUCTURE_ENDINGS = (".json", ".yaml", ".yml", ".xml", ".toml")


def text_hash(body: bytes) -> str:
    """The short hash a page compares with what it holds (the same as the open and save answers')."""
    return hashlib.sha256(body).hexdigest()[:16]


def file_hash(path: str) -> str | None:
    try:
        return text_hash(Path(path).read_bytes())
    except OSError:
        return None


def stamp(path: str) -> Stamp | None:
    try:
        found = Path(path).stat()
    except OSError:
        return None
    return found.st_size, found.st_mtime_ns


def code_files_in(folder: str | None, structures: bool = False) -> list[str]:
    """A folder's code files (.py and .ipynb), hidden folders, caches and environments left out; with
    `structures` (the open project's folder) its structure files too, at its top and in its structures/."""
    if not folder:
        return []
    root = Path(folder)
    if not root.is_dir():
        return []
    skip = {"__pycache__", ".venv", "venv", "node_modules", "builds", ".git", ".sab"}
    found: list[str] = []
    stack = [root]
    while stack and len(found) < MAX_WATCHED:
        here = stack.pop()
        try:
            entries = list(here.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.name in skip:
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.suffix.lower() in _ENDINGS or (
                structures
                and entry.suffix.lower() in _STRUCTURE_ENDINGS
                and (here in (root, root / "structures") or root / "structures" in here.parents)
            ):
                found.append(str(entry))
    return found


def resolve(path: str) -> str:
    return str(Path(path).expanduser().resolve())
