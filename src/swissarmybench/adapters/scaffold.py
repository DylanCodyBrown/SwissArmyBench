"""The project scaffold's files on disk (services/scaffold.py): a project folder's own made files read,
written atomically (only when their bytes change) and removed. Paths are relative to the project's top and
never leave it."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from swissarmybench.adapters.atomic_files import write_atomic


def _inside(folder: str, relative: str) -> Path:
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if not parts or relative.startswith("/") or any(p in ("..", "") for p in parts) or ":" in parts[0]:
        raise ValueError(f"{relative} is not inside the project.")
    return Path(folder).joinpath(*parts)


class ScaffoldFiles:
    def read(self, folder: str, relative: str) -> str | None:
        path = _inside(folder, relative)
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else None
        except (OSError, UnicodeDecodeError):
            return None

    def write(self, folder: str, relative: str, text: str) -> None:
        path = _inside(folder, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, text.encode("utf-8"), if_changed=True)

    def remove(self, folder: str, relative: str) -> None:
        _inside(folder, relative).unlink(missing_ok=True)
