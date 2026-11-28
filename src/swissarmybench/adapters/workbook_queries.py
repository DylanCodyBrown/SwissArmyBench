"""An Excel workbook's file, for its Power Query read and saved back (domain/workbook_queries.py the rules;
the owner, 2026-11-28: "Excel's own Power Query"): its bytes read, the owner file Excel leaves beside an open
workbook looked for, the one backup copy made before the first write, and the new bytes written whole or not
at all (a temporary file beside it, then one replace)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import workbook_queries as rules


def read(path: str) -> bytes:
    """The workbook's bytes. FileNotFoundError when it is not there; one over the size limit is refused."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise FileNotFoundError(f"{file.name} is not there.")
    if file.stat().st_size > rules.MAX_WORKBOOK_BYTES:
        raise rules.Unreadable(f"{file.name} is too large to read its queries here.")
    return file.read_bytes()


def locked(path: str) -> bool:
    """Whether Excel has the workbook open: its owner file (`~$<name>`) is beside it."""
    file = Path(path).expanduser()
    return any((file.parent / name).exists() for name in rules.lock_names(file.name))


def backup(path: str, project: str | None, today: date | None = None) -> str | None:
    """The one backup copy, made before the first write into a workbook: in the open project's
    `.sab/backup/<date>/` when the workbook is in it (the folder ignored by Git: a workbook holds rows),
    otherwise `<name>.backup.xlsx` beside it. None when the workbook already has its backup."""
    file = Path(path).expanduser()
    if project is None:
        target = file.with_name(rules.backup_name(file.name))
        if target.exists():
            return None
    else:
        folder = Path(project) / rules.BACKUP_FOLDER
        if any(folder.glob(f"*/{file.name}")):
            return None
        target = folder / (today or date.today()).isoformat() / file.name
        target.parent.mkdir(parents=True, exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")
    shutil.copyfile(file, target)
    return str(target)


def write(path: str, data: bytes) -> None:
    """The workbook replaced in one step, keeping its permissions."""
    write_atomic(Path(path).expanduser(), data)
