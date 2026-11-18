"""What an older version's tray left behind, removed once at the first start of this one (the owner,
2026-11-18: the tray icon and start at sign-in removed "entirely"; the server now runs while the app is open).

  the sign-in entries  Windows: the Startup folder's "Swiss Army Bench.lnk"; macOS: the LaunchAgent
                       com.swissarmybench.tray (its plist, and launchd told to forget it); Linux: the XDG
                       autostart entry swissarmybench.desktop. Removed only when it is ours (its text names
                       the tray's command; a Windows shortcut by its name).
  the tray itself      tray.json's process id ended when that process still runs; tray.json removed.

Here because only server/ starts processes (launchctl, ending the old tray). Returns whether anything was
there, so the page says once: "The tray icon is gone: Swiss Army Bench now runs while it's open."
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

LABEL = "com.swissarmybench.tray"
SHORTCUT_NAME = "Swiss Army Bench.lnk"
DESKTOP_NAME = "swissarmybench.desktop"
TRAY_WORDS = ("swissarmybench.server", "tray")


def entry_path(platform: str, home: Path, environ: Mapping[str, str]) -> Path | None:
    """Where an older version put its start-at-sign-in entry."""
    if platform == "win32":
        appdata = environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / SHORTCUT_NAME
    if platform == "darwin":
        return home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    config = environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(config) / "autostart" / DESKTOP_NAME


def ours(path: Path, platform: str) -> bool:
    """Is the entry the old tray's (a shortcut by its name; a plist or .desktop file by its command)?"""
    if platform == "win32":
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return all(word in text for word in TRAY_WORDS)


def _forget_launch_agent() -> None:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(  # noqa: S603 (launchctl, fixed arguments)
            ["/bin/launchctl", "remove", LABEL], capture_output=True, timeout=15, check=False
        )


def _tray_like(pid: int) -> bool:
    """Where the system says what a process runs (Linux's /proc), only the old tray is ended (a process id
    may have been given to another program since)."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        return b"swissarmybench" in cmdline.read_bytes() if cmdline.exists() else True
    except OSError:
        return True


def remove_old_tray(
    state_dir: Path,
    home: Path | None = None,
    platform: str = sys.platform,
    environ: Mapping[str, str] | None = None,
    end: Callable[[int], None] | None = None,
    alive: Callable[[int], bool] | None = None,
) -> bool:
    """The old sign-in entry and tray gone; True when there was something to remove."""
    from swissarmybench.server.lifecycle import process_alive
    from swissarmybench.server.updater import SystemOps

    found = False
    entry = entry_path(platform, home or Path.home(), dict(os.environ) if environ is None else environ)
    if entry is not None and entry.is_file() and ours(entry, platform):
        with contextlib.suppress(OSError):
            entry.unlink()
            found = True
        if platform == "darwin" and home is None:
            _forget_launch_agent()
    tray_file = state_dir / "tray.json"
    if tray_file.is_file():
        found = True
        try:
            pid = json.loads(tray_file.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError, AttributeError):
            pid = None
        is_alive = alive or process_alive
        if isinstance(pid, int) and pid > 0 and pid != os.getpid() and is_alive(pid) and _tray_like(pid):
            (end or SystemOps().end)(pid)
        with contextlib.suppress(OSError):
            tray_file.unlink()
    return found
