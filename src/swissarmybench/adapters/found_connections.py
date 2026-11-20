"""Find connections on this computer: the files and registry keys the known tools keep, and the hint scan of
the app settings folders (domain/found_readers.py has the readers and the rules; this finds and reads).

Read-only, always: a file is opened for reading (pgAdmin's database read-only too), a registry key for
reading, nothing in another tool is changed. A value whose name is a secret's is never asked for (the
registry's named values only; a file's secret lines dropped by its reader before it answers). It runs off
the event loop, on the user's click only, for a few seconds at most, and stops on Cancel.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from swissarmybench.domain import found_readers as rules
from swissarmybench.domain.found_connections import Found, Source, is_secret_key

MAX_KNOWN_BYTES = 4 * 1024 * 1024  # a known tool's file larger than this is not read
MAX_GLOB = 60  # files one place's pattern names, at most (a workspace with many projects)

# The registry values read for an ODBC data source and a HeidiSQL session (never a password's).
ODBC_VALUES = (
    "Driver",
    "Description",
    "Server",
    "Servername",
    "Host",
    "Address",
    "Port",
    "Database",
    "DBQ",
    "LastUser",
    "UID",
    "User",
    "Username",
    "Trusted_Connection",
)
HEIDI_VALUES = ("Host", "User", "Port", "NetType", "Databases", "WindowsAuth")
ODBC_INI = r"SOFTWARE\ODBC\ODBC.INI"
HEIDI = r"Software\HeidiSQL\Servers"


class Registry(Protocol):
    """Windows' registry, read only (a seam: tests give a dictionary)."""

    def subkeys(self, hive: str, path: str, view: int) -> list[str]: ...

    def values(self, hive: str, path: str, view: int, names: Iterable[str] | None) -> dict[str, str]:
        """The named values (None: every value of a list key such as ODBC Data Sources: names to drivers)."""
        ...


class NoRegistry:
    """Not Windows: no registry."""

    def subkeys(self, hive: str, path: str, view: int) -> list[str]:
        return []

    def values(self, hive: str, path: str, view: int, names: Iterable[str] | None) -> dict[str, str]:
        return {}


class WindowsRegistry:  # pragma: no cover (Windows only)
    """winreg, read only; HKLM in its 64-bit and 32-bit views (view 64 or 32; 0 the default)."""

    def subkeys(self, hive: str, path: str, view: int) -> list[str]:
        if sys.platform != "win32":
            return []
        import winreg

        root = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[hive]
        access = winreg.KEY_READ | {64: winreg.KEY_WOW64_64KEY, 32: winreg.KEY_WOW64_32KEY}.get(view, 0)
        found: list[str] = []
        try:
            with winreg.OpenKey(root, path, 0, access) as key:
                for i in range(2000):
                    try:
                        found.append(winreg.EnumKey(key, i))
                    except OSError:
                        break
        except OSError:
            return []
        return found

    def values(self, hive: str, path: str, view: int, names: Iterable[str] | None) -> dict[str, str]:
        if sys.platform != "win32":
            return {}
        import winreg

        root = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[hive]
        access = winreg.KEY_READ | {64: winreg.KEY_WOW64_64KEY, 32: winreg.KEY_WOW64_32KEY}.get(view, 0)
        out: dict[str, str] = {}
        try:
            with winreg.OpenKey(root, path, 0, access) as key:
                if names is None:  # a list key (ODBC Data Sources): each name and its driver's name
                    for i in range(5000):
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                        except OSError:
                            break
                        if not is_secret_key(name) and isinstance(value, str | int):
                            out[str(name)] = str(value)
                    return out
                for name in names:
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except OSError:
                        continue
                    if isinstance(value, str | int):
                        out[name] = str(value)
        except OSError:
            return {}
        return out


def system_name() -> str:
    return "windows" if os.name == "nt" else "mac" if sys.platform == "darwin" else "linux"


@dataclass
class Scan:
    """What one scan found: the connections (no password in any), what it said of what it skipped, how many
    files it opened, and why it stopped early (time, cancel, files; None: it looked everywhere)."""

    found: list[Found] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    files: int = 0
    stopped: str | None = None


class ConnectionFinder:
    """The known tools' files on this system, and the hint scan. `home` given (tests): every root is under it,
    the system's own folders (/etc, ProgramData) too; nothing of the real computer is looked at."""

    def __init__(
        self,
        home: Path | None = None,
        system: str | None = None,
        environ: Mapping[str, str] | None = None,
        registry: Registry | None = None,
        skip: Callable[[], Iterable[Path]] = lambda: (),
        seconds: float = rules.MAX_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fake = home is not None
        self.home = home or Path.home()
        self.system = system or system_name()
        self._environ = {} if self._fake else dict(environ if environ is not None else os.environ)
        if registry is not None:
            self._registry: Registry = registry
        elif self.system == "windows" and os.name == "nt" and not self._fake:  # pragma: no cover
            self._registry = WindowsRegistry()
        else:
            self._registry = NoRegistry()
        self._skip = skip  # this app's own state folder and library: never looked in
        self._seconds = seconds
        self._clock = clock

    # ===== the roots =====

    def roots(self) -> dict[str, Path]:
        h, env = self.home, self._environ

        def at(name: str, default: Path) -> Path:
            return Path(env[name]) if env.get(name) else default

        system_drive = h if self._fake else Path(env.get("SystemDrive", "C:") + "\\")
        programs = at("ProgramFiles", system_drive / "Program Files")
        out = {"home": h, "documents": h / "Documents"}
        if self.system == "windows":
            out |= {
                "appdata": at("APPDATA", h / "AppData" / "Roaming"),
                "localappdata": at("LOCALAPPDATA", h / "AppData" / "Local"),
                "programdata": at("ProgramData", system_drive / "ProgramData"),
                "programfiles": programs,
                "commonfiles": at("CommonProgramFiles", programs / "Common Files"),
            }
        elif self.system == "mac":
            out |= {
                "library": h / "Library",
                "appsupport": h / "Library" / "Application Support",
                "systemlibrary": h / "SystemLibrary" if self._fake else Path("/Library"),
            }
        else:
            out |= {
                "config": at("XDG_CONFIG_HOME", h / ".config"),
                "share": at("XDG_DATA_HOME", h / ".local" / "share"),
                "etc": h / "etc" if self._fake else Path("/etc"),
            }
        return out

    # ===== one scan =====

    def scan(self, cancel: threading.Event | None = None, hints: bool = True) -> Scan:
        """Every known tool's connections, then (`hints`) the settings folders searched, until the time is up
        or `cancel` is set."""
        cancel = cancel or threading.Event()
        deadline = self._clock() + self._seconds
        out = Scan()
        read: set[Path] = set()

        def stop() -> bool:
            if cancel.is_set():
                out.stopped = "cancel"
            elif self._clock() > deadline:
                out.stopped = "time"
            return out.stopped is not None

        roots = self.roots()
        for place in rules.PLACES:
            if self.system not in place.systems or stop():
                continue
            root = roots.get(place.root)
            if root is None or not root.is_dir():
                continue
            for path in sorted(_glob(root, place.pattern))[:MAX_GLOB]:
                if stop():
                    break
                read.add(path)
                out.found += self._known(place, root, path, out)
        if self.system == "windows" and not stop():
            out.found += self._odbc_registry()
            out.found += self._heidisql_registry()
        if hints and not stop():
            self._hints(roots, read, out, stop)
        return out

    def _where(self, root_key: str, root: Path, folder: Path) -> str:
        try:
            parts = folder.relative_to(root).parts
        except ValueError:
            parts = folder.parts
        return rules.where_words(root_key, parts, self.system)

    def _known(self, place: rules.Place, root: Path, path: Path, out: Scan) -> list[Found]:
        source = Source(place.tool, self._where(place.root, root, path.parent))
        if place.reader == "skip":
            if rules.SKIPPED_BINARY not in out.notes:
                out.notes.append(rules.SKIPPED_BINARY)
            return []
        if place.reader == "pgadmin":
            out.files += 1
            return rules.stamped(rules.read_pgadmin(_pgadmin_rows(path)), source)
        text = _text(path, MAX_KNOWN_BYTES)
        if text is None:
            return []
        out.files += 1
        if place.reader == "jetbrains_projects":
            return self._jetbrains_projects(text)
        local = _text(path.with_name("dataSources.local.xml"), MAX_KNOWN_BYTES) or ""
        return rules.read(place.reader, text, path.stem, source, local if place.reader == "jetbrains" else "")

    def _jetbrains_projects(self, text: str) -> list[Found]:
        found: list[Found] = []
        for written in rules.jetbrains_projects(text)[:100]:
            folder = Path(written.replace("$USER_HOME$", str(self.home)))
            file = folder / ".idea" / "dataSources.xml"
            sources = _text(file, MAX_KNOWN_BYTES) if folder.is_absolute() else None
            if sources is None:
                continue
            local = _text(file.with_name("dataSources.local.xml"), MAX_KNOWN_BYTES) or ""
            source = Source("JetBrains", self._where("home", self.home, file.parent))
            found += rules.read("jetbrains", sources, "", source, local)
        return found

    def _odbc_registry(self) -> list[Found]:
        found: list[Found] = []
        for hive, view, label in (
            ("HKCU", 0, "HKCU"),
            ("HKLM", 64, "HKLM (64-bit)"),
            ("HKLM", 32, "HKLM (32-bit)"),
        ):
            drivers = self._registry.values(hive, ODBC_INI + r"\ODBC Data Sources", view, None)
            sources = {
                name: self._registry.values(hive, ODBC_INI + "\\" + name, view, ODBC_VALUES)
                for name in self._registry.subkeys(hive, ODBC_INI, view)
                if name.casefold() not in ("odbc data sources", "odbc file dsn")
            }
            source = Source("ODBC", f"{label}\\{ODBC_INI}")
            found += rules.stamped(rules.read_odbc(sources, drivers), source)
        return found

    def _heidisql_registry(self) -> list[Found]:
        sessions: dict[str, dict[str, str]] = {}

        def walk(path: str, depth: int) -> None:
            for name in self._registry.subkeys("HKCU", path, 0)[:500]:
                key = f"{path}\\{name}"
                values = self._registry.values("HKCU", key, 0, HEIDI_VALUES)
                if values.get("Host"):
                    sessions[name] = values
                elif depth < 3:  # a folder of sessions
                    walk(key, depth + 1)

        walk(HEIDI, 0)
        return rules.stamped(rules.read_heidisql(sessions), Source("HeidiSQL", f"HKCU\\{HEIDI}"))

    # ===== the hint scan =====

    def _hints(self, roots: Mapping[str, Path], read: set[Path], out: Scan, stop: Callable[[], bool]) -> None:
        skipped = {_real(p) for p in self._skip()}
        kept = 0
        for key in rules.HINT_ROOTS.get(self.system, ()):
            root = roots.get(key)
            if root is None or not root.is_dir():
                continue
            pending: list[tuple[Path, tuple[str, ...]]] = [(root, ())]
            while pending:
                if stop():
                    return
                folder, parts = pending.pop()
                if _real(folder) in skipped:
                    continue
                try:
                    entries = sorted(os.scandir(folder), key=lambda e: e.name)
                except OSError:
                    continue
                for entry in entries:
                    if stop():
                        return
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir():
                            below = (*parts, entry.name)
                            if len(below) <= rules.MAX_DEPTH and not rules.skip_folder(below):
                                pending.append((Path(entry.path), below))
                            continue
                        size = entry.stat().st_size
                    except OSError:
                        continue
                    path = Path(entry.path)
                    if not parts or path in read or not rules.hint_file(entry.name, size):
                        continue
                    if out.files >= rules.MAX_FILES:
                        out.stopped = "files"
                        return
                    text = _text(path, rules.MAX_FILE_BYTES)
                    out.files += 1
                    if text is None:
                        continue
                    source = Source(parts[0], rules.where_words(key, parts[:1], self.system), searched=True)
                    found = rules.stamped(rules.hints(text, entry.name), source)
                    out.found += found[: rules.MAX_FOUND - kept]
                    kept += len(found)
                    if kept >= rules.MAX_FOUND:
                        out.stopped = "files"
                        return


def _real(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _glob(root: Path, pattern: str) -> list[Path]:
    try:
        return [p for p in root.glob(pattern) if p.is_file() and not p.is_symlink()]
    except (OSError, ValueError):
        return []


def _text(path: Path, limit: int) -> str | None:
    """A small text file's text (UTF-8, or UTF-16 by its byte order mark); None for a large, binary or
    unreadable one."""
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        with path.open("rb") as f:
            data = f.read(limit + 1)
    except OSError:
        return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8-sig", errors="replace")


_PGADMIN_COLUMNS = ("name", "host", "hostaddr", "port", "maintenance_db", "username")


def _pgadmin_rows(path: Path) -> list[dict[str, object]]:
    """pgAdmin 4's servers from its pgadmin4.db, opened read-only: the named columns only (never its
    password's)."""
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return []
    try:
        have = {str(r[1]) for r in db.execute("PRAGMA table_info(server)")}
        wanted = [c for c in _PGADMIN_COLUMNS if c in have]
        if "host" not in wanted:
            return []
        query = "SELECT " + ", ".join(f'"{c}"' for c in wanted) + " FROM server LIMIT 500"  # noqa: S608
        return [dict(zip(wanted, row, strict=True)) for row in db.execute(query)]
    except sqlite3.Error:
        return []
    finally:
        db.close()
