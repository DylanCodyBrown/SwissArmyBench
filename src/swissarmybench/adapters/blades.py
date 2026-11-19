"""Saved blades: one portable file each in the library (Plans/library.plan.md; ~/.swissarmybench/library by
default, Settings' Library folder elsewhere): connections/, vaults/ and blades/<name>.blade.py, whether or not
a project is open. Secrets in the operating system's vault, never in a file.

Four kinds (plan decisions 14-15b):
- `sql`: code that makes a database connection, with its dialect, and usually a catalog command.
- `other`: any code that reaches outside Python (an API client, a path); a catalog command is optional.
- `vault`: code that makes `get(name) -> value`, plus which vault secret goes to which environment
  variable. Values are fetched live when the blade runs and never kept.
- `secret`: only environment variable names. Their values are typed in each session and never kept.

Every blade has an optional description and tags, for finding and grouping blades.

Blades also live in **blade folders** (the owner's request): folders the user lists (Settings, or the
SWISSARMYBENCH_BLADE_FOLDERS environment variable) are searched for portable blade files, Python files whose
frontmatter is a `# /// swissarmybench-blade` header (domain/blades.py). Such a blade's file is its
source of truth: saving it writes the file, a change to the file (a `git pull`) shows on the next look, and
removing one is the user's to do in their folder. A saved blade with the same name comes first.

A blade's own secrets (`secret("password")` in its code) are kept in the vault through `keyring`,
under the service "SwissArmyBench" and the user name `blade/<name>/<secret>`; the file never holds a
value. A blade's code is the user's: the routes never show it to the agent.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import blades as rules
from swissarmybench.domain import library
from swissarmybench.domain.blade_tables import with_header
from swissarmybench.domain.blades import (
    Blade,
    BladeError,
    VaultUnavailableError,
    env_settings,
    file_name,
    is_blade,
    read_blade,
    write_blade,
)
from swissarmybench.renamed import env

KEYRING_SERVICE: str = "SwissArmyBench"
# The service SwissArmyGrid saved under before its rename (renamed.py): a secret found only there is
# copied to the new service on its first read, so saved passwords keep working; the next release drops it.
OLD_KEYRING_SERVICE: str = "SwissArmyGrid"
# Whether a blade's secret is saved, kept this long (a listing asks for every blade's, and an operating
# system's vault can take milliseconds an answer); a save or forget here clears it at once, so the time
# only bounds a change made outside the app.
SECRET_STATUS_SECONDS: float = 30.0


def parse_blade(data: Any, previous: Blade | None = None) -> Blade:
    """A blade from the save screen's JSON, checked (domain/blades.py) and stamped with the time now."""
    return rules.parse_blade(data, previous, time.time())


class BladeStore:
    """The saved blades, and the blades in the user's blade folders. Every method is quick file work; call
    them off the event loop when it matters."""

    def __init__(
        self,
        folder: Path,
        folders_file: Path | None = None,
        pins_file: Path | None = None,
        packs: Callable[[], list[tuple[Path, str]]] | None = None,
        starters: Path | None = None,
        made: Callable[[], object] | None = None,
        more_starters: Callable[[], list[Path]] | None = None,
        listing: Callable[[Blade], tuple[str, str] | None] | None = None,
    ) -> None:
        # The library (Plans/library.plan.md): saved blades are its connections/, vaults/ and blades/ files;
        # an API's blades (its API blade, its web call blades) are files in its apis/<name>/ folder, read like
        # a blade folder's and written back into their own files. Whether or not a project is open (the
        # owner, 2026-11-17: "Apis, Connections they live OUTSIDE of the project").
        self.folder = folder
        # A connection saved with no query that lists its tables gets its starter's as it is read
        # (domain/blade_tables.py listing_for): a connection's tables are always listed.
        self._listing = listing
        self._made = made or (lambda: None)  # the library's README.md and .gitignore, on its first write
        # The extensions' own starter blades (each an extension's STARTERS folder, while it is on).
        self._more_starters = more_starters or (lambda: [])
        self.folders_file = folders_file
        # Installed packs' blades folders, with each pack's label: read-only blades from a marketplace.
        self._packs = packs or (lambda: [])
        # The built-in starter pack (src/swissarmybench/starters/): read-only, shipped with the app, so a
        # new version brings new starters; listed apart (starters()), found by name after the rest.
        self.starters_folder = starters
        # Favourites: this person's own, so kept on this computer, never in a blade's file.
        self.pins_file = pins_file
        self._lock = threading.RLock()
        # A blade file -> (its modification time and size, what it held): files are read again only when
        # they change.
        self._seen: dict[str, tuple[tuple[int, int], Blade | None, str | None]] = {}
        self.problems: list[dict[str, str]] = []  # files with a blade header that could not be read
        # A secret's vault entry (its user) -> (when looked, whether a value is saved): never the value.
        self._saved_status: dict[str, tuple[float, bool]] = {}
        # A starter's name (ignoring case) -> its file, from the last listing of the starters.
        self._starter_index: dict[str, str] = {}

    @property
    def library(self) -> Path:
        return self.folder

    def use(self, folder: Path) -> None:
        """Save and read the library in `folder` from now on (Settings' Library folder)."""
        with self._lock:
            self.folder = folder

    # ===== files =====

    def _saved_paths(self) -> dict[str, Path]:
        """Each saved blade's file in the library, by its name (ignoring case): the first file of a name."""
        found: dict[str, Path] = {}
        for sub in library.BLADE_FOLDERS:
            root = self.folder / sub
            for path in sorted(root.glob(f"*{rules.SUFFIX}")) if root.is_dir() else []:
                blade = self._cached(path)
                if blade is not None:
                    found.setdefault(blade.name.casefold(), path)
        return found

    def _cached(self, path: Path) -> Blade | None:
        """The blade in a library file (read again only when it changed), as a saved blade (no path)."""
        try:
            stat = path.stat()
        except OSError:
            return None
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._seen.get(str(path))
        if cached is None or cached[0] != stamp:
            cached = (stamp, *self._load_file(path, stat.st_size, is_blade, read_blade))
            self._seen[str(path)] = cached
        if cached[1] is None:
            return None
        return replace(cached[1], path=None)

    @staticmethod
    def read_json(path: Path) -> Blade | None:
        """A blade saved as JSON (before the library: ~/.swissarmybench/blades, a project's .sab/blades)."""
        try:
            return BladeStore.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    @staticmethod
    def from_json(data: Any) -> Blade | None:
        return library.saved_json(data)

    @staticmethod
    def text_of(blade: Blade) -> str:
        """A saved blade's file: its portable text (the same blade, the same bytes)."""
        return write_blade(blade.to_json())

    def _write(self, blade: Blade, was: Path | None = None) -> Path:
        """A saved blade into its library file (vaults/, connections/ or blades/); a folder blade into its own
        file. Nothing is written when the file already reads the same."""
        if blade.path:
            self._write_file(blade)
            return Path(blade.path)
        root = self.folder / library.folder_for(blade.kind, blade.template)
        paths = self._saved_paths()
        own = paths.get(blade.name.casefold()) if was is None else was
        target = own if own is not None and own.parent == root else None
        if target is None:
            taken = {p.name.casefold() for p in paths.values()}
            stem = file_name(blade.name).removesuffix(rules.SUFFIX)
            target, number = root / file_name(blade.name), 2
            while target.name.casefold() in taken or target.exists():
                target, number = root / f"{stem}-{number}{rules.SUFFIX}", number + 1
        text = self.text_of(blade)
        if not (target.is_file() and target.read_text(encoding="utf-8") == text):
            self._made()
            # Only this user may read it: a blade's code can name servers and accounts.
            write_atomic(target, text, mode=0o600, newline="\n")
        if own is not None and own != target:
            own.unlink(missing_ok=True)  # it changed kind (a connection now a vault): its old file goes
        return target

    @staticmethod
    def _write_file(blade: Blade) -> None:
        """A folder blade goes back into its own file, as a portable blade."""
        write_atomic(Path(blade.path or ""), write_blade(blade.to_json()))

    # ===== favourites =====

    def pinned(self) -> set[str]:
        """The favourite blades' names (ignoring case)."""
        if self.pins_file is None:
            return set()
        try:
            names = json.loads(self.pins_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return {n.casefold() for n in names if isinstance(n, str)}

    def set_pinned(self, name: str, pinned: bool) -> bool:
        """Pin a blade to the favourites, or take it off. Returns whether it is pinned now."""
        blade = self.get(name)
        if self.pins_file is None:
            raise BladeError("Favourites are not available here.")
        names = self.pinned()
        if pinned:
            names.add(blade.name.casefold())
        else:
            names.discard(blade.name.casefold())
        self.pins_file.parent.mkdir(parents=True, exist_ok=True)
        self.pins_file.write_text(json.dumps(sorted(names), indent=2), encoding="utf-8")
        return pinned

    # ===== blade folders =====

    def folders(self) -> list[dict[str, Any]]:
        """The blade folders: the user's list, then those in SWISSARMYBENCH_BLADE_FOLDERS."""
        listed: list[dict[str, Any]] = []
        if self.folders_file is not None:
            try:
                saved = json.loads(self.folders_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                saved = []
            listed += [{"path": str(p), "from_env": False} for p in saved if isinstance(p, str)]
        for part in env("SWISSARMYBENCH_BLADE_FOLDERS", "").split(os.pathsep):
            if part.strip():
                listed.append({"path": part.strip(), "from_env": True})
        seen: set[str] = set()
        unique = []
        for entry in listed:
            key = os.path.normcase(os.path.abspath(entry["path"]))
            if key not in seen:
                seen.add(key)
                unique.append(entry | {"exists": Path(entry["path"]).is_dir()})
        return unique

    def set_folders(self, paths: Any) -> list[dict[str, Any]]:
        """Replace the user's list (the environment's folders stay). Each must be an existing folder."""
        if self.folders_file is None:
            raise BladeError("Blade folders are not available here.")
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths) or len(paths) > 50:
            raise BladeError('Send the folders as {"folders": ["C:\\\\blades", ...]} (at most 50).')
        clean: list[str] = []
        for raw in paths:
            text = raw.strip()
            if not text:
                continue
            path = Path(text).expanduser()
            if not path.is_absolute():
                raise BladeError(f"{text}: give the folder's full path.")
            if not path.is_dir():
                raise BladeError(f"{text} is not a folder on this computer.")
            clean.append(str(path))
        self.folders_file.parent.mkdir(parents=True, exist_ok=True)
        self.folders_file.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        return self.folders()

    def _scan(self) -> list[Blade]:
        """Every blade in the blade folders, in folder order (the first of a name wins). Hidden folders,
        virtual environments, site-packages and caches are skipped; at most 4 levels and 5,000 Python
        files per folder are looked at."""
        found: list[Blade] = []
        problems: list[dict[str, str]] = []
        skip = {"__pycache__", "node_modules", "site-packages", "venv", "env", "build", "dist"}
        roots = [Path(entry["path"]) for entry in self.folders()]
        roots.append(self.folder / library.APIS)  # each API's own folder: its API blade, its web calls
        for root in roots:
            if not root.is_dir():
                continue
            looked = 0
            for directory, subdirectories, files in os.walk(root):
                depth = len(Path(directory).relative_to(root).parts)
                subdirectories[:] = sorted(
                    d for d in subdirectories if not d.startswith(".") and d not in skip and depth < 4
                )
                for name in sorted(files):
                    if not name.endswith(".py") or looked >= 5_000:
                        continue
                    looked += 1
                    path = Path(directory) / name
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    stamp = (stat.st_mtime_ns, stat.st_size)
                    cached = self._seen.get(str(path))
                    if cached is None or cached[0] != stamp:
                        cached = (stamp, *self._load_file(path, stat.st_size, is_blade, read_blade))
                        self._seen[str(path)] = cached
                    blade, problem = cached[1], cached[2]
                    if problem:
                        problems.append({"path": str(path), "error": problem})
                    if blade is not None:
                        found.append(blade)
        for root, label in self._packs():
            found += self._pack_files(root, label, problems)
        self.problems = problems
        return found

    def _pack_files(self, root: Path, label: str, problems: list[dict[str, str]]) -> list[Blade]:
        """Every blade file of a pack's folder (read again only when it changed), marked with the pack."""
        found: list[Blade] = []
        for path in sorted(root.rglob("*.py")) if root.is_dir() else []:
            try:
                stat = path.stat()
            except OSError:
                continue
            stamp = (stat.st_mtime_ns, stat.st_size)
            cached = self._seen.get(str(path))
            if cached is None or cached[0] != stamp:
                cached = (stamp, *self._load_file(path, stat.st_size, is_blade, read_blade))
                self._seen[str(path)] = cached
            blade, problem = cached[1], cached[2]
            if problem:
                problems.append({"path": str(path), "error": problem})
            if blade is not None:
                blade.pack = label
                found.append(blade)
        return found

    def starters(self) -> list[Blade]:
        """The built-in starter pack's blades, by family then name (the families' order: FAMILIES)."""
        problems: list[dict[str, str]] = []
        found: list[Blade] = []
        for folder in [self.starters_folder, *self._more_starters()]:
            if folder is not None and folder.is_dir():
                found += self._pack_files(folder, rules.STARTERS, problems)
        order = {family: i for i, family in enumerate(rules.FAMILIES)}
        found.sort(key=lambda b: (order.get(b.family, len(order)), b.name.casefold()))
        index: dict[str, str] = {}
        for blade in found:
            index.setdefault(blade.name.casefold(), str(blade.path))
        self._starter_index = index
        return found

    def _starter(self, name: str) -> Blade | None:
        """A starter by its name: its file from the last listing's index, looked at alone (one stat), else
        the starters listed again (a new file, one changed or gone)."""
        path = self._starter_index.get(name.casefold())
        cached = self._seen.get(path) if path is not None else None
        if path is not None and cached is not None and cached[1] is not None:
            try:
                stat = Path(path).stat()
            except OSError:
                stat = None
            same = stat is not None and cached[0] == (stat.st_mtime_ns, stat.st_size)
            if same and cached[1].name.casefold() == name.casefold() and cached[1].pack == rules.STARTERS:
                return cached[1]
        return next((b for b in self.starters() if b.name.casefold() == name.casefold()), None)

    @staticmethod
    def _load_file(path: Path, size: int, is_blade: Any, read_blade: Any) -> tuple[Blade | None, str | None]:
        """The blade in one file (None for an ordinary Python file), or the reason it could not be read."""
        if size > 1_000_000:
            return None, None
        try:
            text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError):
            return None, None
        if not is_blade(text):
            return None, None  # an ordinary Python file: no blade header as its frontmatter
        try:
            blade = parse_blade(read_blade(text))
        except (ValueError, BladeError) as error:
            return None, str(error)
        blade.path = str(path)
        modified = path.stat().st_mtime
        blade.created_at = blade.updated_at = modified
        return blade, None

    # ===== the blades =====

    def _saved(self) -> list[Blade]:
        return [b for p in self._saved_paths().values() if (b := self._cached(p)) is not None]

    def saved_file(self, name: str) -> Path | None:
        """A saved blade's file in the library (None: not a saved one)."""
        return self._saved_paths().get(name.casefold())

    def listed(self, blade: Blade) -> Blade:
        """The blade, a connection with no listing query given its starter's (nothing is written)."""
        if blade.has_catalog or self._listing is None:
            return blade
        found = self._listing(blade)
        if found is None:
            return blade
        return replace(blade, catalog_language=found[0], catalog_command=found[1])

    def all(self) -> list[Blade]:
        """Saved blades, folder blades and pack blades; a saved blade comes first when two share a
        name, then the first folder's (a clone being edited), then an installed pack's."""
        by_name: dict[str, Blade] = {}
        for blade in [*self._saved(), *self._scan()]:
            by_name.setdefault(blade.name.casefold(), blade)
        return sorted((self.listed(b) for b in by_name.values()), key=lambda b: b.name.casefold())

    def get(self, name: str) -> Blade:
        path = self._saved_paths().get(name.casefold())
        blade = self._cached(path) if path is not None else None
        if blade is not None:
            return self.listed(blade)
        for found in self._scan():
            if found.name.casefold() == name.casefold():
                return self.listed(found)
        starter = self._starter(name)
        if starter is not None:
            return self.listed(starter)
        raise KeyError(name)

    def file_of(self, name: str) -> Path | None:
        """The file a blade is kept in (the library's, a blade folder's, a pack's or a starter's)."""
        blade = self.get(name)
        return Path(blade.path) if blade.path else self.saved_file(blade.name)

    def set_header(self, name: str, changes: Mapping[str, Any]) -> Blade:
        """Change a blade's name, description, tags or table name: its file's header only, the code's bytes
        untouched (domain/blades.py with_header). Nothing is written when nothing changes. A starter's and a
        pack's are read-only."""
        with self._lock:
            blade = self.get(name)
            if blade.pack == rules.STARTERS:
                raise BladeError(f"{blade.name} is a starter (read-only): copy it as your own to change.")
            if blade.pack:
                raise BladeError(f"{blade.name} comes from the pack {blade.pack}: change it in that pack.")
            path = self.file_of(blade.name)
            if path is None:
                raise BladeError(f"{blade.name} has no file to change.")
            raw = path.read_bytes()
            bom = raw.startswith(b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")
            before = parse_blade(read_blade(text.replace("\r\n", "\n")), blade)
            after = parse_blade(read_blade(text.replace("\r\n", "\n")) | dict(changes), blade)
            same = before.to_json() | {"updated_at": 0} == after.to_json() | {"updated_at": 0}
            if same:
                return blade
            renamed = after.name.casefold() != blade.name.casefold()
            if renamed:
                try:
                    taken: Blade | None = self.get(after.name)
                except KeyError:
                    taken = None
                if taken is not None:
                    raise BladeError(f"A blade named {taken.name!r} already exists. Pick another name.")
            written = (b"\xef\xbb\xbf" if bom else b"") + with_header(text, after.to_json()).encode("utf-8")
            write_atomic(path, written)  # the file's own mode kept
            self._seen.pop(str(path), None)
            if renamed:
                for secret in blade.secrets:
                    value = self._secret(blade.name, secret)
                    if value is not None:
                        self._set_secret(after.name, secret, value)
                    self._delete_secret(blade.name, secret)
            return self.get(after.name)

    def save(self, data: Any, previous_name: str | None = None) -> Blade:
        """Save a new blade, or replace `previous_name` (which may be a rename). A folder blade is saved
        back into its own file; a new blade with `"folder"` set goes into that blade folder as a file."""
        with self._lock:
            previous = None
            if previous_name is not None:
                try:
                    previous = self.get(previous_name)
                except KeyError:
                    raise BladeError(f"No blade named {previous_name!r} to change.") from None
            if previous is not None and previous.pack == rules.STARTERS:
                raise BladeError(f"{previous.name} is a starter (read-only): copy it as your own to change.")
            if previous is not None and previous.pack:
                raise BladeError(
                    f"{previous.name} comes from the pack {previous.pack}: change it in that pack's "
                    "repository (a clone added as a blade folder), or save a copy under another name."
                )
            blade = parse_blade(data, previous)
            renamed = previous is not None and previous.name.casefold() != blade.name.casefold()
            if previous is None or renamed:
                try:
                    taken = self.get(blade.name)
                except KeyError:
                    taken = None
                if taken is not None:
                    raise BladeError(f"A blade named {taken.name!r} already exists. Pick another name.")
            if previous is None and isinstance(data, dict) and data.get("folder"):
                blade.path = str(self._new_file(str(data["folder"]), blade.name))
            if previous is None and isinstance(data, dict) and data.get("library_folder"):
                blade.path = str(self._library_file(str(data["library_folder"]), blade.name))
            old = self.saved_file(previous.name) if previous is not None and not previous.path else None
            written = self._write(blade, None if renamed else old)
            if renamed and previous is not None:
                for secret in previous.secrets:
                    value = self._secret(previous.name, secret)
                    if value is not None and secret in blade.secrets:
                        self._set_secret(blade.name, secret, value)
                    self._delete_secret(previous.name, secret)
                if old is not None and old != written:
                    old.unlink(missing_ok=True)
            return blade

    def adopt(self, blade: Blade) -> Path:
        """A blade from before the library (a JSON store, a project's own) written as its library file, as
        it is (its secrets stay in the keyring under its name)."""
        with self._lock:
            return self._write(replace(blade, path=None, pack=None))

    def _new_file(self, folder: str, name: str) -> Path:
        listed = {os.path.normcase(os.path.abspath(f["path"])) for f in self.folders()}
        if os.path.normcase(os.path.abspath(folder)) not in listed:
            raise BladeError(f"{folder} is not one of your blade folders. Add it first.")
        path = Path(folder) / file_name(name)
        if path.exists():
            raise BladeError(f"{path} already exists. Pick another name, or edit that blade.")
        return path

    def _library_file(self, folder: str, name: str) -> Path:
        """A new blade's file in the library (apis/Orders): inside it, never over another file."""
        target = (self.library / folder).resolve()
        if not target.is_relative_to(self.library.resolve()):
            raise BladeError("A library blade's folder is inside the library.")
        self._made()
        target.mkdir(parents=True, exist_ok=True)
        path = target / file_name(name)
        if path.exists():
            raise BladeError(f"{path.name} is in {folder} already: pick another name.")
        return path

    def in_library(self, blade: Blade) -> bool:
        if not blade.path:
            return False
        return Path(blade.path).resolve().is_relative_to(self.library.resolve())

    def remove(self, name: str) -> None:
        with self._lock:
            blade = self.get(name)
            if self.in_library(blade):
                for secret in blade.secrets:
                    self._delete_secret(blade.name, secret)
                Path(blade.path or "").unlink(missing_ok=True)
                self._seen.pop(str(blade.path), None)
                return
            if blade.pack == rules.STARTERS:
                raise BladeError(f"{blade.name} is a starter: it comes with the app and stays.")
            if blade.pack:
                raise BladeError(
                    f"{blade.name} comes from the pack {blade.pack}. Uninstall or disable the pack in Claude "
                    "Code (/plugin) to remove its blades."
                )
            if blade.path:
                raise BladeError(
                    f"{blade.name} is a file in your blade folder ({blade.path}). Delete or move the file "
                    "there to remove it."
                )
            for secret in blade.secrets:
                self._delete_secret(blade.name, secret)
            path = self.saved_file(blade.name)
            if path is not None:
                path.unlink(missing_ok=True)
                self._seen.pop(str(path), None)

    # ===== secrets, in the operating system's vault =====

    @staticmethod
    def _keyring() -> Any:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            raise VaultUnavailableError(
                "This computer has no vault the grid server can keep secrets in (Windows Credential Manager, "
                "macOS Keychain or a Linux Secret Service). Use a secret blade (typed each session) or a "
                "vault blade instead."
            )
        return keyring

    @staticmethod
    def _user(name: str, secret: str) -> str:
        return f"blade/{name.casefold()}/{secret}"

    def _secret(self, name: str, secret: str) -> str | None:
        vault, user = self._keyring(), self._user(name, secret)
        value: str | None = vault.get_password(KEYRING_SERVICE, user)
        if value is None:
            # Saved before the rename: found under the old service, and copied across once.
            value = vault.get_password(OLD_KEYRING_SERVICE, user)
            if value is not None:
                try:
                    vault.set_password(KEYRING_SERVICE, user, value)
                except Exception:  # noqa: S110 (a vault that will not write still gives the value)
                    pass
        return value

    def _has_secret(self, name: str, secret: str) -> bool:
        """Whether a value is saved for the secret (kept SECRET_STATUS_SECONDS; raises
        VaultUnavailableError as _secret does)."""
        user, now = self._user(name, secret), time.monotonic()
        kept = self._saved_status.get(user)
        if kept is not None and now - kept[0] < SECRET_STATUS_SECONDS:
            return kept[1]
        saved = self._secret(name, secret) is not None
        self._saved_status[user] = (now, saved)
        return saved

    def _set_secret(self, name: str, secret: str, value: str) -> None:
        try:
            self._keyring().set_password(KEYRING_SERVICE, self._user(name, secret), value)
        finally:
            self._saved_status.pop(self._user(name, secret), None)

    def _delete_secret(self, name: str, secret: str) -> None:
        try:
            self._forget_secret(name, secret)
        finally:
            self._saved_status.pop(self._user(name, secret), None)

    def _forget_secret(self, name: str, secret: str) -> None:
        for service in (KEYRING_SERVICE, OLD_KEYRING_SERVICE):  # forgotten under the old name too
            try:
                self._keyring().delete_password(service, self._user(name, secret))
            except VaultUnavailableError:
                return
            except Exception:  # noqa: S112 (keyring raises PasswordDeleteError for one never set)
                continue

    def copy_secrets(self, source: str, target: str) -> None:
        """A blade kept under a new name (a project's, beside the library's own): the values saved under the
        old name, saved under the new one too (none here: nothing to copy)."""
        try:
            blade = self.get(target)
            for secret in blade.secrets:
                value = self._secret(source, secret)
                if value is not None:
                    self._set_secret(blade.name, secret, value)
        except (KeyError, VaultUnavailableError):
            return

    def secret_status(self, name: str | Blade) -> dict[str, bool]:
        """Each secret the blade's code asks for, and whether a value is saved (never the value)."""
        blade = name if isinstance(name, Blade) else self.get(name)
        try:
            return {s: self._has_secret(blade.name, s) for s in blade.secrets}
        except VaultUnavailableError:
            return {s: False for s in blade.secrets}

    def set_secrets(self, name: str, values: Any) -> dict[str, bool]:
        """Save (text) or forget (null) the blade's secrets. Only names its code asks for."""
        blade = self.get(name)
        if not isinstance(values, dict):
            raise BladeError('Send the secrets as {"password": "...", ...}; null forgets one.')
        for secret, value in values.items():
            if secret not in blade.secrets:
                raise BladeError(f"The blade's code never asks for secret({secret!r}).")
            if value is None:
                self._delete_secret(blade.name, secret)
            elif isinstance(value, str) and 0 < len(value) <= 10_000:
                self._set_secret(blade.name, secret, value)
            else:
                raise BladeError(f"{secret}: a secret is 1 to 10,000 characters of text.")
        return self.secret_status(name)

    def saved_secrets(self, blade: Blade) -> dict[str, str]:
        """The saved values, for running the blade (the client's sab.blade, the server's Refresh)."""
        values: dict[str, str] = {}
        try:
            for secret in blade.secrets:
                value = self._secret(blade.name, secret)
                if value is not None:
                    values[secret] = value
        except VaultUnavailableError:
            return {}
        return values

    # ===== what a blade needs from vault and secret blades =====

    def providers(
        self, blade: Blade, everything: list[Blade] | None = None
    ) -> tuple[list[Blade], dict[str, str]]:
        """For the secrets the blade asks for and has no saved value for: the vault blades that set
        them (to run first), and the variables a secret blade asks the user for (name -> that blade)."""
        try:
            missing = [s for s in blade.secrets if not self._has_secret(blade.name, s)]
        except VaultUnavailableError:
            missing = list(blade.secrets)
        # A setting's ${NAME} (12.7): the code reads os.environ["NAME"], which a vault's entry may give.
        missing += [m["variable"] for m in env_settings(blade.code) if m["variable"] not in os.environ]
        # A connection from the user's own Python: a variable its boxes read that a vault's entry gives (the
        # Variables page keeps where each comes from, 12.7).
        missing += [r.name for r in blade.env_reads if r.name not in os.environ]
        vaults: list[Blade] = []
        typed: dict[str, str] = {}
        for other in self.all() if everything is None else everything:
            if other.name == blade.name:
                continue
            # A vault that loads every secret may hold any of them: it runs first whenever one is missing.
            wanted = other.vault_all or any(env in missing for env in other.vault_mapping)
            if other.kind == "vault" and missing and wanted:
                vaults.append(other)
            if other.kind == "secret":
                for env in other.env_names:
                    if env in missing:
                        typed.setdefault(env, other.name)
        return vaults, typed
