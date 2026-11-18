"""Starting the shell, and telling it to open a page: what the base's hooks call (extension.py), and
`python -m swissarmybench_desktop`. No Qt here: Qt is imported only by the shell's own process.

  open_page(address)   the server's "open a page" (the launch, `swissarmybench open`, the tray's Open): sent
                       to the running shell over its channel; the shell started with the page when none runs.
                       False (the browser opens it instead) where the shell cannot run: no Qt WebEngine, or
                       Linux with no display.
  run_tray(...)        the base's `swissarmybench tray` (start at sign-in, `swissarmybench start`): the shell,
                       with its tray icon and no window
  main(argv)           the shell's process: one at a time (the tray's lock, tray.json); a second one hands its
                       page to the first and ends. A pystray tray still running (from before the extension
                       was installed) is ended first: one icon, not two.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from swissarmybench.adapters.state_files import info_file_path
from swissarmybench.server.lifecycle import AlreadyStartingError, InstanceLock, process_alive
from swissarmybench.server.updater import SystemOps, detached
from swissarmybench_desktop.adapters.channel import RecordFile, ask
from swissarmybench_desktop.domain import windows as rules

RECORD_WAIT_SECONDS = 20.0
OLD_TRAY_WAIT_SECONDS = 8.0
NO_SHELL = (
    "The Desktop app cannot open here: it needs Qt WebEngine (the extension's PySide6 packages) and a desktop "
    "to show its windows on."
)


def has_display(platform: str = sys.platform, environ: dict[str, str] | None = None) -> bool:
    """Windows and macOS always; Linux on a desktop (a display), or Qt told to draw off screen (tests)."""
    if platform in ("win32", "darwin"):
        return True
    said = dict(os.environ) if environ is None else environ
    return bool(said.get("DISPLAY") or said.get("WAYLAND_DISPLAY") or said.get("QT_QPA_PLATFORM"))


def can_run() -> bool:
    """Can the shell run here: Qt WebEngine importable and a display to show it on."""
    try:
        found = importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        found = False
    return found and has_display()


def record_file(info_file: Path | None = None) -> RecordFile:
    return RecordFile((info_file or info_file_path()).with_name("tray.json"))


def running_shell(info_file: Path | None = None) -> tuple[int, int, str] | None:
    """The running shell's (pid, port, key), or None."""
    found = record_file(info_file).shell()
    return found if found and process_alive(found[0]) else None


def tell(said: dict[str, Any], info_file: Path | None = None, wait: float = 0.0) -> dict[str, Any] | None:
    """A message to the running shell (waiting up to `wait` seconds for one that is starting); its answer,
    or None when no shell answers."""
    deadline = time.monotonic() + wait
    while True:
        found = running_shell(info_file)
        if found is not None:
            try:
                return ask(found[1], found[2], said)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.2)


def lock_free(info_file: Path | None = None) -> bool:
    """No shell and no tray holds the tray's lock (one would be starting or running)."""
    try:
        lock = InstanceLock(record_file(info_file).path)
    except AlreadyStartingError:
        return False
    lock.release()
    return True


def start_shell(page: str | None, tray: bool = False) -> None:
    detached(rules.shell_command(sys.executable, page, tray))


def open_page(address: str, info_file: Path | None = None) -> bool:
    """The base's hook: the page in the shell (started when none runs). False: the browser opens it."""
    if not can_run():
        return False
    try:
        page = rules.page_of(address)
    except rules.ShellError:
        return False
    if tell({"open": page}, info_file) is not None:
        return True
    if lock_free(info_file):
        start_shell(page)
        return True
    if old_tray(info_file):
        start_shell(page)  # it ends the pystray tray and takes its place
        return True
    # A shell is starting: its channel comes up in a moment.
    if tell({"open": page}, info_file, wait=RECORD_WAIT_SECONDS) is not None:
        return True
    if lock_free(info_file):
        start_shell(page)
        return True
    return False


def status(info_file: Path | None = None) -> dict[str, Any]:
    """The shell as the agent sees it (desktop_status): running, its windows (kind, title, page: no token)."""
    answer = tell({"status": True}, info_file)
    return answer if isinstance(answer, dict) and "running" in answer else {"running": False, "windows": []}


def old_tray(info_file: Path | None = None) -> int:
    """The pystray tray's process id while it runs (a tray.json with its pid and no shell), else 0."""
    said = record_file(info_file).read()
    pid = said.get("pid") if isinstance(said, dict) and not isinstance(said.get("shell"), dict) else None
    return pid if isinstance(pid, int) and pid != os.getpid() and process_alive(pid) else 0


def _end_old_tray(info_file: Path) -> bool:
    """The pystray tray holds the lock: it is ended, so the shell's icon is the one icon. True once the
    lock is free."""
    pid = old_tray(info_file)
    if pid:
        SystemOps().end(pid)
    deadline = time.monotonic() + OLD_TRAY_WAIT_SECONDS
    while time.monotonic() < deadline:
        if lock_free(info_file):
            return True
        time.sleep(0.2)
    return False


def main(argv: list[str], info_file: Path | None = None) -> int:
    """The shell's process (`python -m swissarmybench_desktop [--tray] [page]`)."""
    try:
        tray, page = rules.read_arguments(argv)
    except rules.ShellError as error:
        print(error, file=sys.stderr)
        return 2
    info = info_file or info_file_path()
    events = info.with_name("server_events.json")
    if not can_run():
        print(NO_SHELL, file=sys.stderr)
        return 1
    try:
        lock = InstanceLock(record_file(info).path)
    except AlreadyStartingError:
        # Another shell: it opens the page (a second `swissarmybench desktop` shows the home window).
        if not old_tray(info):
            if tray and not page:
                return 0
            if tell({"open": page or rules.HOME_PAGE}, info, wait=RECORD_WAIT_SECONDS) is not None:
                return 0
        if not _end_old_tray(info):
            print("Another Swiss Army Bench tray icon is running: quit it, then try again.", file=sys.stderr)
            return 1
        try:
            lock = InstanceLock(record_file(info).path)
        except AlreadyStartingError:
            return 1
    from swissarmybench_desktop.server.shell import run

    return run(lock, tray, page, info, events)


def run_tray(info_file: Path, events_file: Path | None = None) -> int:
    """The base's `swissarmybench tray`, with the shell's icon instead of pystray's. Where the shell cannot
    run, the server is still started (as the pystray tray does with no desktop), then nothing more."""
    if not can_run():
        from swissarmybench.server.tray import Server, Tray

        Tray(Server(info_file), _no_autostart(), events_file=events_file).ensure_server()
        return 0
    return main(["--tray"], info_file)


def _no_autostart() -> Any:
    from swissarmybench.server.autostart import Autostart

    return Autostart()


def desktop_command() -> int:
    """`swissarmybench desktop`: the app in its own windows (the server started when none runs)."""
    return main([])
