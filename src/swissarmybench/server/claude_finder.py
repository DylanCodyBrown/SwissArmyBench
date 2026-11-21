"""Finding Claude on this computer and starting it (services/claude.py's probes and launcher).

The owner (2026-11-16): "a lot of the users will have a 3p claude install so dynamically finding it will
be the key". So nothing here is one fixed path: each system is asked in the ways it knows its apps, and
domain/claude.py reads the answers loosely (any app whose name or bundle says Claude):

- Windows: the App Paths and Uninstall registry keys (HKCU and HKLM, 64- and 32-bit views), Store (MSIX)
  packages and Start menu shortcuts' targets (one PowerShell call), Programs folders, PATH, Claude Code's
  own folder, npm's global bin, WinGet's links.
- macOS: .app bundles in /Applications and ~/Applications and Spotlight's (mdfind), each Info.plist read;
  PATH, ~/.claude/local/claude, ~/.local/bin, Homebrew's and npm's bins.
- Linux: .desktop files in the applications folders (the user's, the system's, Flatpak's, Snap's); PATH,
  ~/.claude/local/claude, ~/.local/bin, npm's global bin.

Starting: an argument list (never a shell string), detached from this server, in a console of its own on
Windows. Claude Code refuses to start inside another Claude Code session, so that session's markers are
left out of its environment.

`SWISSARMYBENCH_CLAUDE_STANDIN` (tests): a JSON file says what was found and the launches are written
beside it, so no test probes this computer or opens a terminal.
"""

from __future__ import annotations

import contextlib
import glob
import itertools
import json
import os
import plistlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from swissarmybench.domain import claude as rules
from swissarmybench.domain.claude import Install

PROBE_SECONDS = 20.0
# Claude Code's markers: a claude started from inside one would refuse ("nested session").
_SESSION_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")

_POWERSHELL = r"""
$ErrorActionPreference = 'SilentlyContinue'
$packages = @(Get-AppxPackage -Name '*Claude*' | ForEach-Object {
  [pscustomobject]@{ Name = $_.Name; PackageFamilyName = $_.PackageFamilyName;
    InstallLocation = $_.InstallLocation; Publisher = $_.Publisher;
    AppIds = @((Get-AppxPackageManifest $_).Package.Applications.Application | ForEach-Object { $_.Id }) } })
$shell = New-Object -ComObject WScript.Shell
$menus = @([Environment]::GetFolderPath('StartMenu'), [Environment]::GetFolderPath('CommonStartMenu'))
$shortcuts = @(foreach ($menu in $menus) { Get-ChildItem -LiteralPath $menu -Recurse -Filter '*.lnk' |
  ForEach-Object { [pscustomobject]@{ lnk = $_.FullName;
    target = $shell.CreateShortcut($_.FullName).TargetPath } } })
@{ packages = $packages; shortcuts = $shortcuts } | ConvertTo-Json -Depth 4 -Compress
"""


def platform_name() -> str:
    return "windows" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"


def own_command(name: str) -> str:
    """This install's own `swissarmybench-mcp` or `swissarmybench-context` (beside the Python that runs the
    server, so Claude reaches this app), else the one on PATH, else the bare name."""
    folder = Path(sys.executable).parent
    for candidate in (folder / f"{name}.exe", folder / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name


# Where Windows lists its programs, and the values of a program's key that say what it is.
_REGISTRY_PLACES = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
)
_REGISTRY_VALUES = ("DisplayName", "DisplayIcon", "InstallLocation", "Publisher", "")


def _registry_programs(hive: int, base: str, view: int) -> list[dict[str, Any]]:
    """Every program's key under one of the registry's places (Windows only)."""
    if sys.platform != "win32":
        return []
    import winreg

    try:
        parent = winreg.OpenKey(hive, base, 0, winreg.KEY_READ | view)
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    with parent:
        for n in itertools.count():
            try:
                name = winreg.EnumKey(parent, n)
            except OSError:
                break
            entry = _registry_program(parent, name)
            if entry is not None:
                out.append(entry)
    return out


def _registry_program(parent: Any, name: str) -> dict[str, Any] | None:
    """One program's key as {key, DisplayName, ...} (None: it cannot be opened)."""
    if sys.platform != "win32":
        return None
    import winreg

    entry = {"key": name}
    try:
        with winreg.OpenKey(parent, name) as key:
            for value in _REGISTRY_VALUES:
                with contextlib.suppress(OSError):
                    entry[value or "Default"] = str(winreg.QueryValueEx(key, value)[0])
    except OSError:
        return None
    return entry


class Finder:
    """Asks this computer where Claude is; `run` and `which` stand in for subprocess and shutil in tests."""

    def __init__(
        self,
        platform: str | None = None,
        home: Path | None = None,
        environ: Mapping[str, str] | None = None,
        run: Callable[..., Any] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.platform = platform or platform_name()
        self.home = home or Path.home()
        self.environ = dict(os.environ if environ is None else environ)
        self._run = run
        self._which = which

    # ===== what is there =====

    def find(self) -> list[Install]:
        found = self._code()
        probe = {"windows": self._windows, "darwin": self._mac}.get(self.platform, self._linux)
        with contextlib.suppress(Exception):  # a probe that fails finds nothing; the others still count
            found += probe()
        return rules.ranked(found)

    def terminals(self) -> dict[str, str]:
        names = {"windows": ("wt",), "darwin": ("osascript",)}.get(self.platform, rules.LINUX_TERMINALS)
        return {name: path for name in names if (path := self._which(name))}

    # ===== Claude Code: the `claude` command =====

    def _code(self) -> list[Install]:
        home = self.home
        places: list[tuple[str, str]] = []
        if found := self._which("claude"):
            places.append((found, "PATH"))
        if self.platform == "windows":
            local = self.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
            roaming = self.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            places += [
                (str(home / ".local" / "bin" / "claude.exe"), "Claude Code's own folder"),
                (str(home / ".claude" / "local" / "claude.exe"), "Claude Code's own folder"),
                (str(Path(roaming) / "npm" / "claude.cmd"), "npm"),
                (str(Path(local) / "Microsoft" / "WinGet" / "Links" / "claude.exe"), "WinGet"),
            ]
        else:
            places += [
                (str(home / ".claude" / "local" / "claude"), "Claude Code's own folder"),
                (str(home / ".local" / "bin" / "claude"), "Claude Code's own folder"),
                ("/opt/homebrew/bin/claude", "Homebrew"),
                ("/home/linuxbrew/.linuxbrew/bin/claude", "Homebrew"),
                ("/usr/local/bin/claude", "PATH"),
            ]
        if prefix := self._npm_prefix():
            bin_ = Path(prefix) if self.platform == "windows" else Path(prefix) / "bin"
            places.append((str(bin_ / ("claude.cmd" if self.platform == "windows" else "claude")), "npm"))
        out = []
        for path, source in places:
            if Path(path).is_file() and (install := rules.code_install(path, source)):
                out.append(install)
        return out

    def _npm_prefix(self) -> str | None:
        npm = self._which("npm")
        if not npm:
            return None
        try:
            answer = self._run([npm, "prefix", "-g"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return answer.stdout.strip() or None if answer.returncode == 0 else None

    # ===== Windows =====

    def _windows(self) -> list[Install]:
        found = rules.from_registry(self._registry())
        local = self.environ.get("LOCALAPPDATA", "")
        answer = self._powershell()
        found += rules.from_store(_as_list(answer.get("packages")), local)
        found += rules.from_shortcuts(_as_list(answer.get("shortcuts")))
        programs = []
        for base in (local, str(Path(local) / "Programs"), self.environ.get("ProgramFiles", "")):
            if base:
                programs += glob.glob(str(Path(base) / "*[Cc]laude*" / "*.exe"))
                programs += glob.glob(str(Path(base) / "*[Cc]laude*" / "app-*" / "*.exe"))
        found += rules.from_programs(programs)
        return [i for i in found if i.launch or Path(i.path).exists()]

    def _registry(self) -> list[dict[str, Any]]:  # Windows only
        if sys.platform != "win32":
            return []
        import winreg

        out: list[dict[str, Any]] = []
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                for base in _REGISTRY_PLACES:
                    out += _registry_programs(hive, base, view)
        return out

    def _powershell(self) -> dict[str, Any]:
        shell = self._which("powershell") or "powershell.exe"
        try:
            answer = self._run(
                [shell, "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL],
                capture_output=True,
                text=True,
                timeout=PROBE_SECONDS,
            )
            data = json.loads(answer.stdout or "{}")
        except (OSError, subprocess.SubprocessError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    # ===== macOS =====

    def _mac(self) -> list[Install]:
        bundles = [
            (p, "Applications")
            for base in ("/Applications", str(self.home / "Applications"))
            for p in glob.glob(f"{base}/*.app")
        ]
        try:
            answer = self._run(
                [
                    "mdfind",
                    "kMDItemContentType == 'com.apple.application-bundle' && "
                    "(kMDItemDisplayName == '*claude*'cd || kMDItemCFBundleIdentifier == '*claude*'cd)",
                ],
                capture_output=True,
                text=True,
                timeout=PROBE_SECONDS,
            )
            bundles += [(line.strip(), "Spotlight") for line in answer.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
        found = []
        for path, source in bundles:
            try:
                with open(Path(path) / "Contents" / "Info.plist", "rb") as file:
                    info = plistlib.load(file)
            except (OSError, ValueError, plistlib.InvalidFileException):
                info = {}
            if install := rules.from_bundle(path, info if isinstance(info, dict) else {}, source):
                found.append(install)
        return found

    # ===== Linux =====

    def _linux(self) -> list[Install]:
        data_home = self.environ.get("XDG_DATA_HOME") or str(self.home / ".local" / "share")
        data_dirs = (self.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
        folders = [data_home, *data_dirs, str(self.home / ".local/share/flatpak/exports/share")]
        folders += ["/var/lib/flatpak/exports/share"]
        places = [str(Path(f) / "applications") for f in folders if f] + [
            "/var/lib/snapd/desktop/applications"
        ]
        found = []
        for folder in dict.fromkeys(places):
            for path in glob.glob(f"{folder}/*.desktop"):
                try:
                    text = Path(path).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if "claude" in text.casefold() and (install := rules.from_desktop_file(path, text)):
                    found.append(install)
        return found


def _as_list(value: Any) -> list[dict[str, Any]]:
    # ConvertTo-Json writes one item as an object, not a list of one.
    if isinstance(value, dict):
        return [value]
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


class Starter:
    """Starts Claude: detached from this server, nothing read from it."""

    def start(self, argv: list[str], cwd: str | None, new_console: bool) -> None:
        environ = {k: v for k, v in os.environ.items() if k not in _SESSION_MARKERS}
        options: dict[str, Any] = {
            "cwd": cwd,
            "env": environ,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_CONSOLE if new_console else subprocess.DETACHED_PROCESS
            options["creationflags"] = flags | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        subprocess.Popen(argv, **options)  # noqa: S603 (an argument list: no shell reads it)


# ===== the stand-in for tests: nothing probed, nothing started =====


class StandinFinder:
    """What a JSON file says was found: {"platform", "installs": [Install's fields], "terminals"}."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.platform = str(self._data().get("platform") or "linux")

    def _data(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def find(self) -> list[Install]:
        data = self._data()
        self.platform = str(data.get("platform") or "linux")
        installs = []
        for raw in _as_list(data.get("installs")):
            installs.append(
                Install(
                    str(raw.get("kind")),
                    str(raw.get("path")),
                    str(raw.get("name") or "Claude"),
                    str(raw.get("source") or "PATH"),
                    bool(raw.get("official", True)),
                    tuple(raw.get("launch") or ()),
                    str(raw.get("config") or ""),
                )
            )
        return rules.ranked(installs)

    def terminals(self) -> dict[str, str]:
        terminals = self._data().get("terminals", {"x-terminal-emulator": "/usr/bin/x-terminal-emulator"})
        return {str(k): str(v) for k, v in terminals.items()} if isinstance(terminals, dict) else {}


class RecordingStarter:
    """Writes each launch (one JSON line) beside the stand-in's file instead of starting anything."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def start(self, argv: list[str], cwd: str | None, new_console: bool) -> None:
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"argv": argv, "cwd": cwd, "new_console": new_console}) + "\n")
