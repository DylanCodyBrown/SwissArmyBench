"""The desktop app's process from the outside: starting it, telling it to open a page, what it shows. No Qt
here (Qt is imported only by the app's own process, server/desktop_shell.py).

Swiss Army Bench is a desktop app (the owner, 2026-11-18: "Change that to the primary install. It's not an
extension it is the app framework now and it should have been since the start"): `swissarmybench` opens it,
and it starts the server it owns.

  open_page(address)  "open a page" (`swissarmybench`, `swissarmybench open`, `start`, an update's restart,
                      desktop_open): sent to the running app over its channel; the app started with the
                      page when none runs. False where the app cannot run (no Qt WebEngine, Linux with no
                      display): the caller opens the browser instead.
  main(page)          the app's process: one at a time (its lock, desktop.json); a second start hands its
                      page to the first and ends.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from swissarmybench.adapters.desktop import RecordFile, ask
from swissarmybench.adapters.state_files import info_file_path
from swissarmybench.domain import desktop as rules
from swissarmybench.server.lifecycle import AlreadyStartingError, InstanceLock, process_alive
from swissarmybench.server.updater import detached

RECORD_WAIT_SECONDS = 20.0
NO_APP = (
    "The desktop app cannot open here: it needs Qt WebEngine (PySide6) and a desktop to show its windows on. "
    "`swissarmybench open --browser` opens the app in the browser."
)


def has_display(platform: str = sys.platform, environ: dict[str, str] | None = None) -> bool:
    """Windows and macOS always; Linux on a desktop (a display), or Qt told where to draw (tests)."""
    if platform in ("win32", "darwin"):
        return True
    said = dict(os.environ) if environ is None else environ
    return bool(said.get("DISPLAY") or said.get("WAYLAND_DISPLAY") or said.get("QT_QPA_PLATFORM"))


def can_run() -> bool:
    """Can the app run here: Qt WebEngine importable and a display to show it on."""
    try:
        found = importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        found = False
    return found and has_display()


def qt_version() -> str:
    try:
        return importlib.metadata.version("PySide6-Essentials")
    except importlib.metadata.PackageNotFoundError:
        return ""


def record_file(info_file: Path | None = None) -> RecordFile:
    return RecordFile((info_file or info_file_path()).with_name(rules.RECORD))


def running_app(info_file: Path | None = None) -> tuple[int, int, str] | None:
    """The running app's (pid, port, key), or None."""
    found = record_file(info_file).shell()
    return found if found and process_alive(found[0]) else None


def app_pid(info_file: Path) -> int:
    """The running app's process id (the update's helper ends it), else 0."""
    found = running_app(info_file)
    return found[0] if found else 0


def tell(said: dict[str, Any], info_file: Path | None = None, wait: float = 0.0) -> dict[str, Any] | None:
    """A message to the running app (waiting up to `wait` seconds for one that is starting); its answer,
    or None when no app answers."""
    deadline = time.monotonic() + wait
    while True:
        found = running_app(info_file)
        if found is not None:
            try:
                return ask(found[1], found[2], said)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


def lock_free(info_file: Path | None = None) -> bool:
    """No app holds its lock (one would be starting or running)."""
    try:
        lock = InstanceLock(record_file(info_file).path)
    except AlreadyStartingError:
        return False
    lock.release()
    return True


def start_app(page: str | None) -> None:
    detached(rules.shell_command(_gui_python(), page))


def _gui_python(executable: str = sys.executable) -> str:
    """Windows: pythonw.exe beside python.exe (no console window for the app); elsewhere this Python."""
    path = Path(executable)
    if path.name.lower() == "python.exe" and (path.parent / "pythonw.exe").is_file():
        return str(path.parent / "pythonw.exe")
    return executable


def open_page(address: str, info_file: Path | None = None) -> bool:
    """The page in the desktop app (started when none runs). False: the caller opens the browser."""
    if not can_run():
        return False
    try:
        page = rules.page_of(address)
    except rules.ShellError:
        return False
    if tell({"open": page}, info_file) is not None:
        return True
    if lock_free(info_file):
        start_app(page)
        return True
    # An app is starting: its channel comes up in a moment.
    return tell({"open": page}, info_file, wait=RECORD_WAIT_SECONDS) is not None


def status(info_file: Path | None = None) -> dict[str, Any]:
    """The app as the agent sees it (desktop_status): running, its windows (kind, title, page: no token)."""
    answer = tell({"status": True}, info_file)
    return answer if isinstance(answer, dict) and "running" in answer else {"running": False, "windows": []}


class SystemShell:
    """The app as the desktop service sees it, for the running server's connection file."""

    def __init__(self, info_file: Path) -> None:
        self.info_file = info_file

    def status(self) -> dict[str, Any]:
        return status(self.info_file)

    def open(self, page: str) -> bool:
        return open_page(page, self.info_file)


def main(page: str | None = None, info_file: Path | None = None) -> int:
    """The app's process (`swissarmybench app [page]`, `swissarmybench` with no arguments)."""
    try:
        wanted = rules.read_page(page)
    except rules.ShellError as error:
        print(error, file=sys.stderr)
        return 2
    info = info_file or info_file_path()
    if not can_run():
        print(NO_APP, file=sys.stderr)
        return 1
    try:
        lock = InstanceLock(record_file(info).path)
    except AlreadyStartingError:
        # Another start of the app: it opens the page (a second `swissarmybench` shows the home window).
        if tell({"open": wanted or rules.HOME_PAGE}, info, wait=RECORD_WAIT_SECONDS) is not None:
            return 0
        print("Swiss Army Bench is starting already.", file=sys.stderr)
        return 1
    from swissarmybench.server.desktop_shell import run

    return run(lock, wanted, info)
