"""A file written whole or not at all, and the small JSON state files written that way.

Every adapter that saves a file goes through `write_atomic` (or `replacing`, for a writer that needs a
path, such as a zip): the new bytes go to a temporary file of a unique name in the same folder (two
processes or threads never share one), are flushed to the disk, and are moved over the file in one
step, so a reader sees the old file or the new one, never half of one.

The file's mode: `mode` when given (0o600: a token, a blade's code); otherwise an existing file keeps
its own, and a new one gets the system's default (the umask's).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _temporary(path: Path, mode: int) -> tuple[Path, int]:
    """A new file beside `path`, never one already there (O_EXCL, never through a symlink)."""
    while True:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            return temporary, os.open(temporary, _FLAGS, mode)
        except FileExistsError:
            continue


def _mode_for(path: Path, mode: int | None) -> int | None:
    """The mode the file ends with: `mode`, or the existing file's own (None: the default)."""
    if mode is not None:
        return mode
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


@contextlib.contextmanager
def replacing(path: Path, mode: int | None = None) -> Iterator[Path]:
    """A temporary path to write the new file at; moved over `path` when the block ends, removed when
    it raises. The folder is made when missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = _mode_for(path, mode)
    temporary, descriptor = _temporary(path, 0o600 if kept is not None else 0o666)
    os.close(descriptor)
    try:
        yield temporary
        if kept is not None:
            os.chmod(temporary, kept)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def as_bytes(data: str | bytes, encoding: str = "utf-8", newline: str | None = None) -> bytes:
    """Text as open(..., "w") writes it: `newline` None turns each "\\n" into the system's line end,
    "" or "\\n" leaves it, anything else replaces it."""
    if isinstance(data, bytes):
        return data
    end = os.linesep if newline is None else newline
    if end not in ("", "\n"):
        data = data.replace("\n", end)
    return data.encode(encoding)


def write_atomic(
    path: Path | str,
    data: str | bytes,
    mode: int | None = None,
    if_changed: bool = False,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> bool:
    """`data` written to `path` atomically (text as `encoding`, its line ends by `newline`, as open()
    does). With `if_changed`, a file that already holds these bytes is left untouched. Whether it
    was written."""
    target = Path(path)
    body = as_bytes(data, encoding, newline)
    if if_changed:
        try:
            if target.stat().st_size == len(body) and target.read_bytes() == body:
                return False
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    kept = _mode_for(target, mode)
    temporary, descriptor = _temporary(target, 0o600 if kept is not None else 0o666)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        if kept is not None:
            os.chmod(temporary, kept)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return True


class JsonFile:
    """One small JSON file of the state folder (None: no file, so nothing is ever written: a test's
    server without a state folder), written atomically. `mode`: the file's (0o600 for one that holds a
    key); `if_changed`: written only when its text changes; `indent`: json.dumps's."""

    def __init__(
        self,
        path: Path | None,
        mode: int | None = None,
        if_changed: bool = False,
        indent: int | None = 1,
        end: str = "\n",
    ) -> None:
        self.path = path
        self.mode = mode
        self.if_changed = if_changed
        self.indent = indent
        self.end = end

    def read(self) -> Any:
        if self.path is None or not self.path.is_file():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, data: Any) -> None:
        self.write_text(json.dumps(data, indent=self.indent) + self.end)

    def write_text(self, text: str) -> None:
        if self.path is not None:
            write_atomic(self.path, text, mode=self.mode, if_changed=self.if_changed)
