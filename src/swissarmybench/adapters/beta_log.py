"""The beta log's files (domain/beta_log.py has the rules): one JSON line per event in the state folder's
`logs/` folder, written by a thread of its own so no request ever waits on the disk.

  logs/beta-2026-11-15-01.jsonl   a day's events, in parts of a tenth of the cap each
  logs/pictures/<note id>.png     a note's picture, only when the user ticked "Attach a picture"
  beta.json                       beta mode, on or off, as the user last set it (the state folder)

Kept: about the last 7 days, at most about 20 MB (the oldest part goes first). A full queue drops the
event rather than wait. Nothing is sent anywhere; "Export beta log…" writes one zip where the user picks.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

QUEUE_SIZE = 2000
README = (
    "A beta log of the app: errors, slow requests, process starts and ends, page errors and the notes\n"
    "left with right-click. No cell values, SQL, code, secrets or full paths; table and column names\n"
    "are aliases (table#1, col#3). Pictures are here only if a note's 'Attach a picture' was ticked.\n"
    "Send this zip to Claude.\n"
)


class BetaFiles:
    """The log's folder: a writer thread fed by a queue, rotation, reading back, clearing and the zip."""

    def __init__(
        self, folder: Path | None, max_bytes: int, days: int, now: Callable[[], float] = time.time
    ) -> None:
        self.folder = folder
        self.max_bytes = max(max_bytes, 64 * 1024)
        self.part_bytes = max(self.max_bytes // 10, 16 * 1024)
        self.days = days
        self._now = now
        self._queue: queue.Queue[str] = queue.Queue(QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._start = threading.Lock()
        self._disk = threading.Lock()  # the writer, clear and the zip take turns
        self.dropped = 0

    # ----- writing -----

    def write(self, entry: dict[str, Any]) -> bool:
        """Queue one event; False when the folder is off or the queue is full (the event is dropped)."""
        if self.folder is None:
            return False
        self._ensure_thread()
        try:
            self._queue.put_nowait(json.dumps(entry, ensure_ascii=False, default=str, separators=(",", ":")))
        except queue.Full:
            self.dropped += 1
            return False
        return True

    def _ensure_thread(self) -> None:
        with self._start:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="beta-log", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            lines = [self._queue.get()]
            while len(lines) < 200:
                try:
                    lines.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                with self._disk:
                    self._append(lines)
            except OSError:
                pass  # a full or locked disk: the events are lost, the app goes on
            finally:
                for _ in lines:
                    self._queue.task_done()

    def _parts(self) -> list[Path]:
        if self.folder is None or not self.folder.is_dir():
            return []
        return sorted(self.folder.glob("beta-*.jsonl"))

    def _current(self) -> Path:
        if self.folder is None:
            raise ValueError("The beta log has no folder.")
        day = datetime.fromtimestamp(self._now(), UTC).strftime("%Y-%m-%d")
        today = [p for p in self._parts() if p.name.startswith(f"beta-{day}-")]
        if today and today[-1].stat().st_size < self.part_bytes:
            return today[-1]
        number = int(today[-1].stem.rsplit("-", 1)[1]) + 1 if today else 1
        return self.folder / f"beta-{day}-{number:02d}.jsonl"

    def _append(self, lines: list[str]) -> None:
        if self.folder is None:
            raise ValueError("The beta log has no folder.")
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._current()
        new = not path.exists()
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        if new:
            self._prune()

    def _prune(self) -> None:
        """Parts older than the days kept go; then the oldest, while the whole is over the cap."""
        oldest = self._now() - self.days * 86400
        parts = self._parts()
        for path in list(parts):
            if path.stat().st_mtime < oldest and path != parts[-1]:
                path.unlink(missing_ok=True)
                parts.remove(path)
        while len(parts) > 1 and sum(p.stat().st_size for p in parts) > self.max_bytes:
            parts.pop(0).unlink(missing_ok=True)
        pictures = sorted(self._pictures(), key=lambda p: p.stat().st_mtime)
        while pictures and (
            pictures[0].stat().st_mtime < oldest or sum(p.stat().st_size for p in pictures) > self.max_bytes
        ):
            pictures.pop(0).unlink(missing_ok=True)

    def flush(self, timeout: float = 5.0) -> None:
        """Wait (at most `timeout`) until every queued event is on disk."""
        deadline = time.monotonic() + timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks and time.monotonic() < deadline:
                self._queue.all_tasks_done.wait(0.05)

    # ----- pictures -----

    def _pictures(self) -> list[Path]:
        if self.folder is None or not (self.folder / "pictures").is_dir():
            return []
        return sorted((self.folder / "pictures").glob("*.png"))

    def save_picture(self, note_id: str, data: bytes) -> str:
        if self.folder is None:
            raise ValueError("The beta log has no folder.")
        with self._disk:
            folder = self.folder / "pictures"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{note_id}.png").write_bytes(data)
        return f"pictures/{note_id}.png"

    def pictures(self) -> list[str]:
        return [f"pictures/{p.name}" for p in self._pictures()]

    # ----- reading, clearing, the zip -----

    def read(self) -> list[dict[str, Any]]:
        """Every event kept, oldest first."""
        self.flush()
        events: list[dict[str, Any]] = []
        with self._disk:
            for path in self._parts():
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        continue  # a line cut short by a crash
        return events

    def size(self) -> dict[str, int]:
        parts, pictures = self._parts(), self._pictures()
        return {
            "files": len(parts),
            "bytes": sum(p.stat().st_size for p in parts),
            "pictures": len(pictures),
        }

    def clear(self) -> int:
        """Remove every log file and picture; how many files went."""
        self.flush()
        removed = 0
        with self._disk:
            for path in [*self._parts(), *self._pictures()]:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def zip_to(self, path: str, notes: list[dict[str, Any]], pictures: bool) -> dict[str, Any]:
        """One zip at `path`: the log's files, the notes, and (with `pictures`) their pictures."""
        target = Path(path).expanduser()
        if target.suffix.lower() != ".zip":
            raise ValueError("The beta log is saved as a .zip file.")
        if not target.parent.is_dir():
            raise ValueError("That folder does not exist.")
        self.flush()
        partial = target.with_name(f".{target.name}.{os.getpid()}.partial")
        with self._disk:
            parts = self._parts()
            shots = self._pictures() if pictures else []
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("README.txt", README)
                for part in parts:
                    archive.write(part, f"logs/{part.name}")
                archive.writestr("notes.json", json.dumps(notes, ensure_ascii=False, indent=1, default=str))
                for shot in shots:
                    archive.write(shot, f"pictures/{shot.name}")
        os.replace(partial, target)
        return {"path": str(target), "files": len(parts), "notes": len(notes), "pictures": len(shots)}


class BetaSwitch:
    """Beta mode as the user last set it: beta.json in the state folder (None: never set)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def read(self) -> bool | None:
        if self.path is None or not self.path.is_file():
            return None
        try:
            on = json.loads(self.path.read_text(encoding="utf-8")).get("on")
        except (OSError, ValueError, AttributeError):
            return None
        return on if isinstance(on, bool) else None

    def write(self, on: bool) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"on": on}) + "\n", encoding="utf-8")


class _Forward(logging.Handler):
    def __init__(self, callback: Callable[[str, BaseException | None], None]) -> None:
        super().__init__(logging.ERROR)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            error = record.exc_info[1] if record.exc_info else None
            self._callback(record.getMessage(), error)
        except Exception:  # noqa: S110 (a log must never break what it watches)
            pass


# The loggers whose errors are the server's own crashes: an exception that escaped a request (uvicorn's)
# and a background task's that nobody awaited (asyncio's).
WATCHED_LOGGERS = ("uvicorn.error", "asyncio")


def listen(callback: Callable[[str, BaseException | None], None]) -> Callable[[], None]:
    """Hand the watched loggers' errors to `callback`; the function returned stops it."""
    handler = _Forward(callback)
    for name in WATCHED_LOGGERS:
        logging.getLogger(name).addHandler(handler)

    def stop() -> None:
        for name in WATCHED_LOGGERS:
            logging.getLogger(name).removeHandler(handler)

    return stop
