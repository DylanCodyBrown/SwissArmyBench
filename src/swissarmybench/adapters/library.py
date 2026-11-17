"""The library folder's edge (domain/library.py has the rules, services/library.py the use case).

  where       ~/.swissarmybench/library by default; Settings' Library folder points it elsewhere (a clone of a
              team's repository), kept in the state folder's library.json (the path only)
  made        README.md and .gitignore written on first use, never over the user's own
  counted     what is in it, by folder (names of files only: nothing is read for the answer)
  migration   once: this computer's stores from before the library (blades/*.json, variables.json and
              local/variables.json, colours.toml, tangs/) written as library files, the old files moved into a
              dated backup folder beside them (state folder/backup/before-library-<date>/)
  a project   its own blades (an older .sab's .sab/blades/*.json, in its working folder) read, and removed
              from the working folder once in the library, so its next save leaves them out

The app never runs git: the folder is a plain working copy the user commits and pushes with their own tools.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from swissarmybench.adapters.blades import BladeStore
from swissarmybench.adapters.variables import VariableFiles
from swissarmybench.domain import library as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.project_scope import BLADES as PROJECT_BLADES


class LibraryFolder:
    def __init__(self, default: Path, settings_file: Path | None) -> None:
        self.default = default
        self.settings_file = settings_file
        self._root = self._chosen() or default

    def _chosen(self) -> Path | None:
        if self.settings_file is None or not self.settings_file.is_file():
            return None
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        folder = data.get("folder") if isinstance(data, dict) else None
        return Path(folder) if isinstance(folder, str) and folder.strip() else None

    @property
    def root(self) -> Path:
        return self._root

    def ensure(self) -> list[str]:
        """The folder, its README.md and .gitignore, made when missing (never over the user's own)."""
        made: list[str] = []
        self._root.mkdir(parents=True, exist_ok=True)
        for name, text in (("README.md", rules.README), (".gitignore", rules.GITIGNORE)):
            path = self._root / name
            if not path.exists():
                path.write_text(text, encoding="utf-8", newline="\n")
                made.append(name)
        return made

    def check(self, raw: Any) -> Path:
        """A folder the user named: a whole path to a folder on this computer (made when its parent is)."""
        if not isinstance(raw, str) or not raw.strip():
            raise rules.LibraryError('Send {"folder": "the library folder\'s whole path"}.')
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute():
            raise rules.LibraryError(f"{raw.strip()[:300]}: give the folder's whole path.")
        if path.exists() and not path.is_dir():
            raise rules.LibraryError(f"{path} is a file, not a folder.")
        if not path.exists() and not path.parent.is_dir():
            raise rules.LibraryError(f"{path.parent} is not a folder on this computer.")
        return path

    def use(self, path: Path | None) -> None:
        """The library from now on: `path`, or the default (None). Kept in library.json (the path only)."""
        self._root = path or self.default
        if self.settings_file is not None:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps({"folder": str(path) if path else None}, indent=1) + "\n"
            self.settings_file.write_text(text, encoding="utf-8")
        self.ensure()

    def counts(self) -> dict[str, int]:
        """How many of each are in it (by file names), and how many files in local/."""
        root = self._root

        def files(sub: str, suffix: str) -> int:
            folder = root / sub
            return sum(1 for p in folder.glob(f"*{suffix}") if p.is_file()) if folder.is_dir() else 0

        apis = root / rules.APIS
        local = root / rules.LOCAL
        return {
            "connections": files(rules.CONNECTIONS, ".blade.py"),
            "vaults": files(rules.VAULTS, ".blade.py"),
            "blades": files(rules.BLADES, ".blade.py"),
            "apis": sum(1 for p in apis.iterdir() if p.is_dir()) if apis.is_dir() else 0,
            "tangs": files(rules.TANGS, ".tang"),
            "local_files": sum(1 for p in local.rglob("*") if p.is_file()) if local.is_dir() else 0,
        }

    def is_git(self) -> bool:
        """Whether the folder is a Git working copy (a .git folder or file there: nothing is run)."""
        return (self._root / ".git").exists()

    # ===== the one-time move of this computer's stores =====

    def migrate(
        self, state_dir: Path, blades: BladeStore, variables: VariableFiles, date: str
    ) -> dict[str, Any]:
        """This computer's stores from before the library, written as library files once; the old files moved
        into state folder/backup/before-library-<date>/. Returns what moved and where the backup is."""
        backup = state_dir / "backup" / f"before-library-{date}"
        before = [
            state_dir / n
            for n in ("blades", "variables.json", "local/variables.json", "colours.toml", "tangs")
        ]
        if any(p.exists() for p in before):
            self.ensure()
        moved = {"connections and blades": 0, "variables files": 0, "colours files": 0, "tangs": 0}
        old_blades = state_dir / "blades"
        if old_blades.is_dir() and old_blades.resolve() != self._root.resolve():
            for path in sorted(old_blades.glob("*.json")):
                blade = BladeStore.read_json(path)
                if blade is None:
                    continue
                try:
                    blades.get(blade.name)  # one of that name in the library already: it stays
                except KeyError:
                    blades.adopt(blade)
                    moved["connections and blades"] += 1
            self._backup(old_blades, backup / "blades")
        shared, local = state_dir / "variables.json", state_dir / "local" / "variables.json"
        if shared.is_file() or local.is_file():
            if variables.shared is not None and not variables.shared.is_file():
                variables.write(_json(shared), _json(local) or {"values": {}})
                moved["variables files"] += 1
            for old, where in ((shared, "variables.json"), (local, "local/variables.json")):
                if old.is_file():
                    self._backup(old, backup / where)
        colours = state_dir / "colours.toml"
        if colours.is_file() and colours.resolve() != (self._root / rules.COLOURS_FILE).resolve():
            target = self._root / rules.COLOURS_FILE
            if not target.is_file():
                shutil.copy2(colours, target)
                moved["colours files"] += 1
            self._backup(colours, backup / "colours.toml")
        tangs = state_dir / "tangs"
        if tangs.is_dir() and tangs.resolve() != (self._root / rules.TANGS).resolve():
            target_folder = self._root / rules.TANGS
            for path in sorted(tangs.glob("*.tang")):
                target = target_folder / path.name
                if not target.exists():
                    target_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    moved["tangs"] += 1
            self._backup(tangs, backup / "tangs")
        return {"moved": moved, "backup": str(backup) if backup.exists() else ""}

    @staticmethod
    def _backup(old: Path, to: Path) -> None:
        to.parent.mkdir(parents=True, exist_ok=True)
        if to.exists():
            to = to.with_name(f"{to.name}-{os.getpid()}")
        shutil.move(str(old), str(to))

    # ===== a project's own blades (an older .sab) =====

    @staticmethod
    def project_blades(folder: str) -> list[Blade]:
        root = Path(folder) / PROJECT_BLADES
        found = [BladeStore.read_json(p) for p in sorted(root.glob("*.json"))] if root.is_dir() else []
        return [b for b in found if b is not None]

    @staticmethod
    def drop_project_blades(folder: str) -> None:
        """The working folder's .sab/blades, gone once its items are in the library: the next save leaves
        it out (the .sab on disk keeps it until then, so an older app still opens it)."""
        shutil.rmtree(Path(folder) / PROJECT_BLADES, ignore_errors=True)


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None
