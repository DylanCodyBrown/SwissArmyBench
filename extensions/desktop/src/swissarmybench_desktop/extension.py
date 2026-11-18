"""The Desktop extension as the base reads it (swissarmybench/extensions.py): its description, the hooks the
base's launcher and tray call while it is on, its door, its agent commands and its Session page words.

The owner, 2026-11-18, after weighing pywebview, Electron, Tauri, native Rust and a PWA: "I like the pyside6.
Can we just build it side by side here as an optional install version?" Installed, the app opens in windows
of its own (Qt WebEngine: Chromium); removed, it opens in the browser again. The front end is the same.

The hooks (each read by name, none of them named in the base):
  open_page(address)  the base's "open a page" (`swissarmybench start` and `open`, the tray's Open): in the
                      shell (server/launch.py); False where it cannot run, and the browser opens it
  run_tray(...)       the base's `swissarmybench tray` (start at sign-in): the shell's icon, not pystray's
  LAUNCHER            `swissarmybench desktop`: the app in its own windows

No Qt is imported here: the shell is a process of its own (server/shell.py).
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from swissarmybench_desktop import __version__

ID = "desktop"
NAME = "Desktop"
VERSION = __version__
DESCRIPTION = "Swiss Army Bench in app windows of its own instead of browser tabs."
ADDS = [
    "Each page in an app window of its own (Qt WebEngine: Chromium), its size and place remembered",
    "Pop-outs, the Workbench and panel windows as app windows; other addresses in your browser",
    "Downloads with a Save dialog and Show in folder; Print to PDF",
    "One tray icon: Start at sign-in, Update, Quit",
]
AREAS = (("desktop", "The Desktop app: its windows, a page opened in it"),)
SECRET_PATHS: tuple[str, ...] = ()


def _area(what: str) -> tuple[str, str, dict[str, Any]]:
    return what, "settings", {"place": "area", "area": "extensions"}


# The Session page's words for each audit entry.
SESSION_RULES: dict[str, Any] = {
    "desktop_open": lambda d, x: _area(f"Opened {x.get('page') or 'a page'} in the Desktop app"),
}


def describe() -> dict[str, Any]:
    return {"id": ID, "name": NAME, "description": DESCRIPTION, "version": VERSION, "adds": ADDS}


def open_page(address: str) -> bool:
    from swissarmybench_desktop.server.launch import open_page as opened

    return opened(address)


def run_tray(info_file: Path, events_file: Path | None = None) -> int:
    from swissarmybench_desktop.server.launch import run_tray as shell_tray

    return shell_tray(info_file, events_file)


def desktop() -> int:
    from swissarmybench_desktop.server.launch import desktop_command

    return desktop_command()


LAUNCHER: dict[str, Any] = {"desktop": desktop}


def qt_version() -> str:
    try:
        return importlib.metadata.version("PySide6-Essentials")
    except importlib.metadata.PackageNotFoundError:
        return ""


class SystemShell:
    """The shell as the service sees it (server/launch.py), for the running server's connection file."""

    def __init__(self, info_file: Path) -> None:
        self.info_file = info_file

    def status(self) -> dict[str, Any]:
        from swissarmybench_desktop.server.launch import status

        return status(self.info_file)

    def open(self, page: str) -> bool:
        from swissarmybench_desktop.server.launch import open_page as opened

        return opened(page, self.info_file)


def routes(services: Any) -> list[Any]:
    from swissarmybench.adapters.state_files import info_file_path
    from swissarmybench_desktop.server import routes as door
    from swissarmybench_desktop.services.desktop import Desktop

    service = Desktop(SystemShell(info_file_path()), services.ws.audit, qt_version())
    services.desktop = service
    return door.routes(service)


def commands() -> dict[str, Any]:
    from swissarmybench_desktop.commands import COMMANDS

    return COMMANDS
