"""The desktop app's process from the outside: starting it, telling it to open a page, what it shows. No Qt
here (Qt is imported only by the app's own process, server/desktop_shell.py).

Swiss Army Bench is a desktop app (the owner, 2026-11-18: "Change that to the primary install. It's not an
extension it is the app framework now and it should have been since the start"): `swissarmybench` opens it,
and it starts the server it owns.

  open_page(address)  "open a page" (`swissarmybench`, `swissarmybench open`, `start`, an update's restart,
                      desktop_open): sent to the running app over its channel; the app started with the
                      page when none runs. False where the app cannot run (no Qt WebEngine, Linux with no
                      display): the caller opens the browser instead.
  show(address)       a grid a push or open_grid made with nothing showing it and no VS Code window to
                      ask (the running server's LiveUpdates.fallback): the app, else the browser.
  main(page)          the app's process: one at a time (its lock, desktop.json); a second start hands its
                      page to the first and ends.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

from swissarmybench.adapters.desktop import RecordFile, ask
from swissarmybench.adapters.state_files import info_file_path
from swissarmybench.domain import desktop as rules
from swissarmybench.server.lifecycle import (
    AlreadyStartingError,
    InstanceLock,
    get_json,
    post_json,
    process_alive,
)
from swissarmybench.server.updater import detached

RECORD_WAIT_SECONDS = 20.0
QUIT_WAIT_SECONDS = 5.0
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


def show(address: str, info_file: Path | None = None) -> bool:
    """A page nothing shows yet (a push or open_grid with no VS Code window to ask): the desktop app (started
    when none runs), else the browser where the app cannot run. False only when neither opened."""
    if open_page(address, info_file):
        return True
    try:
        return bool(webbrowser.open(address))
    except webbrowser.Error:
        return False


def hand_file(path: str, info_file: Path | None = None) -> bool:
    """`swissarmybench open <file>`, Open with: the file handed to the running app over its channel (one app,
    never a second), the app started first when none runs. False when no app answered."""
    said = {"file": path}
    if tell(said, info_file) is not None:
        return True
    if lock_free(info_file):
        start_app(None)
    return tell(said, info_file, wait=RECORD_WAIT_SECONDS) is not None


def file_page(path: str, info: dict[str, Any]) -> str:
    """A file opened with the app (`swissarmybench open <file>`, Open with, a file dropped on a window), by
    the running server `info`: a table read by its path (its grid shows in the home window: the page
    returned), a notebook in the Workbench (the one open, else a Workbench window that opens it), a blade of
    the library on the blades page (any other .blade.py in the Workbench), a folder as a project. The page to
    show (no token). ShellError for a file the app does not open; OSError with the server's words when it
    refuses."""
    target = Path(path).expanduser()
    if not target.exists():
        raise rules.ShellError(f"{target} is not there.")
    kind = rules.file_kind(target.name, target.is_dir(), (target / ".sab").is_dir())
    if not kind:
        raise rules.ShellError(rules.CANNOT_OPEN.format(name=target.name))
    full = str(target.resolve())
    if kind == rules.PROJECT:
        post_json(info, "/project/open", {"path": full, "ask": True})
        return rules.HOME_PAGE
    if kind == rules.TABLE:
        listed = get_json(info, "/datasets")
        taken = [str(d.get("name")) for d in (listed or {}).get("datasets", []) if isinstance(d, dict)]
        name = rules.table_name(target.name, taken)
        loaded = post_json(info, f"/datasets/{quote(name, safe='')}/load", {"path": full})
        grid = loaded.get("grid") if isinstance(loaded, dict) else None
        return f"/workspace#grid={grid}" if isinstance(grid, str) else rules.HOME_PAGE
    if kind == rules.BLADE:
        stem = rules.blade_stem(target.name)
        try:
            get_json(info, f"/blades/{quote(stem, safe='')}")
            return f"/catalog?blade={quote(stem, safe='')}"
        except OSError:
            pass  # not one of the library's: its file in the Workbench
    try:
        post_json(info, "/workbench/window", {"command": "file.open", "args": {"path": full}}, timeout=30)
        return "/workbench"  # the Workbench window that opened it, brought forward
    except OSError:
        return f"/workbench?file={quote(full, safe='')}"  # no Workbench window: one that opens it


def quit_app(info_file: Path | None = None, wait: float = QUIT_WAIT_SECONDS) -> bool:
    """`swissarmybench stop`: the running app asked to quit (every window closed, each one's place kept, the
    server told), waited for up to `wait` seconds. True when an app ran and has ended."""
    found = running_app(info_file)
    if found is None:
        return False
    try:
        ask(found[1], found[2], {"quit": True})
    except OSError:
        return False
    deadline = time.monotonic() + wait
    # Ended: its record gone (the app removes it last) or its process gone. (An app the server started is the
    # server's child: until the server reaps it, its process id still answers.)
    while record_file(info_file).shell() is not None and process_alive(found[0]):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


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
