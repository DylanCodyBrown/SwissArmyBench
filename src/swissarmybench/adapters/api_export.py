"""A local sandbox API's export folder (services/api_export.py): its made files, the sandbox's copy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic


class ExportFolder:
    """A local sandbox API's export folder: its files written only when their bytes change, a stale one
    removed,
    the sandbox's copy (only on the user's tick)."""

    SKIP = ("data/", "__pycache__/", ".venv/", ".aws-sam/")

    def __init__(self, copy_sandbox: Callable[[Path], None]) -> None:
        self._copy = copy_sandbox

    def write(self, folder: str, files: dict[str, str]) -> dict[str, list[str]]:
        root = Path(folder)
        written: list[str] = []
        unchanged: list[str] = []
        for name, text in sorted(files.items()):
            (written if write_atomic(root / name, text, if_changed=True) else unchanged).append(name)
        return {"written": written, "unchanged": unchanged}

    def existing(self, folder: str) -> dict[str, str]:
        root = Path(folder)
        out: dict[str, str] = {}
        if not root.is_dir():
            return out
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if not path.is_file() or relative.startswith(self.SKIP):
                continue
            try:
                out[relative] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return out

    def remove(self, folder: str, names: list[str]) -> None:
        for name in names:
            (Path(folder) / name).unlink(missing_ok=True)

    def copy_sandbox(self, folder: str) -> None:
        self._copy(Path(folder) / "data" / "sandbox.duckdb")
