"""A project's builds/ folder (domain/builds.py): each build a folder of text files, written whole and only
when its bytes change; the analyzer's files in a launch's run folder (sab_perf.py beside the pages, its
switch and its records)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic

PERF_SOURCE: Path = Path(__file__).resolve().parents[1] / "server" / "sab_perf.py"
PERF_ON: str = "sab_perf.on"
PERF_LOG: str = "sab_perf.jsonl"


class BuildFiles:
    @staticmethod
    def builds(folder: str) -> list[str]:
        """The build folders' names (numbers) under `folder` (builds/<app>), none when it is not there."""
        root = Path(folder)
        if not root.is_dir():
            return []
        return sorted((p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit()), key=int)

    @staticmethod
    def write(folder: str, files: dict[str, str]) -> list[str]:
        """A build's files, each written atomically and only when its bytes change; their names."""
        root = Path(folder)
        written = []
        for name, text in sorted(files.items()):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(target, text.encode("utf-8"), if_changed=True)
            written.append(name)
        return written

    @staticmethod
    def read(folder: str) -> dict[str, str]:
        """Every text file of a build, by its path inside it (forward slashes)."""
        root = Path(folder)
        if not root.is_dir():
            raise FileNotFoundError(f"There is no build at {folder}.")
        found: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.stat().st_size <= 5_000_000:
                try:
                    found[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
        return found

    @staticmethod
    def read_one(folder: str, name: str) -> str | None:
        path = Path(folder) / name
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return None

    @staticmethod
    def remove(folder: str) -> None:
        shutil.rmtree(folder, ignore_errors=True)

    @staticmethod
    def join(*parts: str) -> str:
        return str(Path(*parts))

    # ----- the analyzer's files in a run folder -----

    @staticmethod
    def perf_helper() -> str:
        return PERF_SOURCE.read_text(encoding="utf-8")

    @staticmethod
    def perf_switch(folder: str, on: bool) -> None:
        flag = Path(folder) / PERF_ON
        if on:
            flag.write_text("on\n", encoding="utf-8")
        else:
            try:
                flag.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def perf_records(folder: str, offset: int) -> tuple[list[str], int]:
        """The analyzer's record lines written since `offset` (bytes), and the new offset."""
        path = Path(folder) / PERF_LOG
        try:
            with path.open("rb") as held:
                held.seek(offset)
                data = held.read(20_000_000)
        except FileNotFoundError:
            return [], offset
        whole = data.rfind(b"\n") + 1
        lines = data[:whole].decode("utf-8", "replace").splitlines()
        return lines, offset + whole

    @staticmethod
    def perf_clear(folder: str) -> None:
        try:
            os.remove(Path(folder) / PERF_LOG)
        except FileNotFoundError:
            pass
