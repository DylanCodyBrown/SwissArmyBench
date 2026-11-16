"""Start at sign-in (the owner, 2026-11-16: "Swiss Army Bench should start itself then stay running when
it's on the computer"): the tray runs when the user signs in, and the tray starts the server.

    Windows   a shortcut in the Startup folder: the tool's pythonw.exe -m swissarmybench.server tray
              (pythonw: no console window). Chosen over a Task Scheduler task: no admin, nothing to
              register, the user sees it in Settings' Startup apps and can switch it off there too.
    macOS     a LaunchAgent, ~/Library/LaunchAgents/com.swissarmybench.tray.plist, RunAtLoad; launchd
              starts the tray again only if it crashed (KeepAlive SuccessfulExit false), never after
              Stop and quit.
    Linux     an XDG autostart entry, ~/.config/autostart/swissarmybench.desktop.

`swissarmybench autostart on|off|status`, the tray's switch and the agent's app_autostart all use this.
The installers turn it on (not on a build machine: --no-autostart, or CI set).
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

LABEL: str = "com.swissarmybench.tray"
SHORTCUT_NAME: str = "Swiss Army Bench.lnk"
DESKTOP_NAME: str = "swissarmybench.desktop"


def tray_command(prefix: Path | None = None, platform: str = sys.platform) -> list[str]:
    """The tray, from the uv tool's own Python (the same path after an update); on Windows its pythonw."""
    prefix = prefix or Path(sys.prefix)
    if platform == "win32":
        python = prefix / "Scripts" / "pythonw.exe"
    else:
        python = prefix / "bin" / "python"
    return [str(python), "-m", "swissarmybench.server", "tray"]


def entry_path(platform: str, home: Path, environ: Mapping[str, str]) -> Path | None:
    """Where the sign-in entry lives; None where there is no such place (Windows without APPDATA)."""
    if platform == "win32":
        appdata = environ.get("APPDATA")
        if not appdata:
            return None
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / SHORTCUT_NAME
    if platform == "darwin":
        return home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    config = environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(config) / "autostart" / DESKTOP_NAME


def label(platform: str = sys.platform) -> str:
    """The tray's menu item."""
    return "Start with Windows" if platform == "win32" else "Open at login"


def plist_text(command: list[str]) -> str:
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": command,
            "RunAtLoad": True,
            # Started again only if it crashed: Stop and quit ends it for good (exit code 0).
            "KeepAlive": {"SuccessfulExit": False},
            "ProcessType": "Interactive",
        }
    ).decode("utf-8")


def _desktop_quoted(word: str) -> str:
    """A word of a .desktop file's Exec line (the freedesktop quoting rules)."""
    if not any(c in word for c in " \t\n\"'\\><~|&;$*?#()`"):
        return word
    escaped = word.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def desktop_text(command: list[str]) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=Swiss Army Bench",
            "Exec=" + " ".join(_desktop_quoted(word) for word in command),
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            "",
        ]
    )


def shortcut_script(shortcut: Path, command: list[str]) -> str:
    """PowerShell that writes the Startup folder's shortcut to `command` (its first word, its arguments)."""

    def quoted(text: object) -> str:
        return "'" + str(text).replace("'", "''") + "'"

    target, arguments = command[0], " ".join(command[1:])
    return (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + quoted(shortcut) + "); "
        f"$s.TargetPath = {quoted(target)}; $s.Arguments = {quoted(arguments)}; "
        f"$s.WorkingDirectory = {quoted(Path.home())}; $s.Description = 'Swiss Army Bench'; $s.Save()"
    )


def run_hidden(command: list[str]) -> int:
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        # PowerShell, osascript or zenity, with our own script.
        done = subprocess.run(command, capture_output=True, timeout=30, creationflags=flags, check=False)  # noqa: S603
        return done.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


class Autostart:
    """The sign-in entry: on when its file is there."""

    def __init__(
        self,
        platform: str = sys.platform,
        home: Path | None = None,
        environ: Mapping[str, str] | None = None,
        command: list[str] | None = None,
        run: Callable[[list[str]], int] = run_hidden,
    ) -> None:
        self.platform = platform
        self.path = entry_path(platform, home or Path.home(), os.environ if environ is None else environ)
        self.command = command or tray_command(platform=platform)
        self._run = run

    @property
    def label(self) -> str:
        return label(self.platform)

    def status(self) -> bool:
        return self.path is not None and self.path.is_file()

    def set(self, on: bool) -> bool:
        """On or off; whether it is on now."""
        if self.path is None:
            raise OSError("There is no Startup folder here (APPDATA is not set).")
        if not on:
            self.path.unlink(missing_ok=True)
            return self.status()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.platform == "win32":
            script = shortcut_script(self.path, self.command)
            if self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]) != 0:
                raise OSError("Windows did not make the Startup shortcut.")
        elif self.platform == "darwin":
            self.path.write_text(plist_text(self.command), encoding="utf-8")
        else:
            self.path.write_text(desktop_text(self.command), encoding="utf-8")
        return self.status()

    def to_json(self) -> dict[str, object]:
        return {"on": self.status(), "label": self.label, "entry": str(self.path) if self.path else None}
