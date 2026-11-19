"""Everything Swiss Army Bench keeps in its own state folder (~/.swissarmybench), and nothing else is
written: the audit log, saved dashboards, the connection file and the model library's files.

  the audit log        one JSON line per action, never a cell value
  dashboards           Visualizations saved on the user's click: its cards as drawn, the last 60 versions
  themes               Visualizations themes the user imported (colours only), one small file each
  the connection file  where the running server is, and its token (owner-only)
  the model library    relationship sets and models: the shipped ones, the user's, SWISSARMYBENCH_MODELS
  preferences          small JSON files the user's own choices are kept in: the kind colours
                       (kind_colours.json), a script's run settings (run_settings.json: arguments and
                       where each variable comes from; a plain value only, never a secret's)

(Blades and their folders are adapters/blades.py; exports are adapters/export.py.)
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import JsonFile as JsonFile  # its old place, still read
from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain.datasets import validate_name
from swissarmybench.domain.library import OLD_TANGS, RELATIONSHIP_SETS
from swissarmybench.domain.relationships import (
    Model,
    RelationshipSetError,
    is_set_file,
    parse_model,
    read_set,
    same_set,
    set_file_name,
    write_set,
)
from swissarmybench.renamed import env, home_state_folder

# ===== the audit log =====
# The audit log: one JSON line per action, never a cell value (plan section 6, rule 9).
#
# Each entry records when, who (`user` or `agent`), what, on which dataset, the query text if
# any, and how many rows went out. Exports and agent reads are the ways client data leaves the
# system, so those are the entries that matter most. Like a structured ILogger sink writing to a
# local file; nothing is sent anywhere.


class AuditLog:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        actor: str,
        action: str,
        dataset: str | None = None,
        query: str | None = None,
        rows: int | None = None,
        **details: Any,
    ) -> None:
        entry: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(timespec="seconds"),
            "actor": actor,
            "action": action,
            "dataset": dataset,
        }
        if query is not None:
            entry["query"] = query
        if rows is not None:
            entry["rows"] = rows
        entry.update(details)
        if self._path is None:
            return
        line = json.dumps(entry, default=str)
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def tail(self, limit: int = 200, actor: str | None = None) -> list[dict[str, Any]]:
        """The last `limit` entries, or the last `limit` of one actor's."""
        if self._path is None or not self._path.exists():
            return []
        newest_first: list[dict[str, Any]] = []
        for line in reversed(self._path.read_text(encoding="utf-8").splitlines()):
            if len(newest_first) >= limit:
                break
            if line.strip():
                entry = json.loads(line)
                if actor is None or entry.get("actor") == actor:
                    newest_first.append(entry)
        return newest_first[::-1]


# ===== saved dashboards =====
# A dashboard is Visualizations frozen on the user's Save: every card's text, size and place, and what a
# chart or a query table showed (its points or rows), so it opens even when its tables are gone. It
# is written only on that click; each Save under the same name adds a version.

DASHBOARD_VERSIONS: int = 60


class DashboardFiles:
    """The saved dashboards in one folder: what the service layer's `Dashboards` port is here."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _path(self, name: str) -> Path:
        return self.folder / f"{validate_name(name)}.json"

    def names(self) -> list[dict[str, Any]]:
        found = []
        for path in sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []:
            body = self.read(path.stem)
            if body and body["versions"]:
                last = body["versions"][-1]
                found.append(
                    {
                        "name": body["name"],
                        "versions": len(body["versions"]),
                        "saved": last.get("saved"),
                        "cards": len(last.get("cards", [])),
                    }
                )
        return found

    def read(self, name: str) -> dict[str, Any] | None:
        path = self._path(name)
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(body, dict) or not isinstance(body.get("versions"), list):
            return None  # edited by hand into something else: ignore it
        return {"name": name, "versions": [v for v in body["versions"] if isinstance(v, dict)]}

    def add_version(self, name: str, cards: list[dict[str, Any]], saved: str) -> int:
        self.folder.mkdir(parents=True, exist_ok=True)
        versions = [*(self.read(name) or {"versions": []})["versions"], {"saved": saved, "cards": cards}]
        versions = versions[-DASHBOARD_VERSIONS:]
        self._path(name).write_text(
            json.dumps({"name": name, "versions": versions}, default=str), encoding="utf-8"
        )
        return len(versions)

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False


# ===== the user's Visualizations themes =====


class ThemeFiles:
    """Imported Visualizations themes in one folder: what the service layer's `ThemeShelf` port is here."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def all(self) -> list[dict[str, Any]]:
        found = []
        for path in sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []:
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(body, dict):
                found.append(body)
        return found

    def write(self, theme_id: str, file: dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / f"{validate_name(theme_id)}.json").write_text(
            json.dumps(file, indent=2), encoding="utf-8"
        )

    def delete(self, theme_id: str) -> bool:
        path = self.folder / f"{validate_name(theme_id)}.json"
        if path.exists():
            path.unlink()
            return True
        return False


# ===== a preference: one small JSON file =====


# ===== the connection file =====
# The connection file clients read to find the running server (plan section 4).
#
# On start the server writes ~/.swissarmybench/server.json with its port, its token, the dataset
# size limit and its process id; on clean shutdown it deletes it. The push client
# (swissarmybench.client.push_client) reads the same path, including the SWISSARMYBENCH_INFO
# override, so the two must stay in step. The process id lets anyone tell a live server from a
# file left behind by a crash (server/lifecycle.py).
#
# The token in this file is the only credential the server accepts, so the file is created
# owner-only. On Windows the mode bits do little, but the user's profile folder is already
# readable only by that user (plus administrators and SYSTEM).


def info_file_path() -> Path:
    """Where the connection file lives. SWISSARMYBENCH_INFO overrides it (tests use this)."""
    override: str | None = env("SWISSARMYBENCH_INFO")
    return Path(override) if override else home_state_folder() / "server.json"


def write_info_file(path: Path, info: dict[str, Any]) -> None:
    """Write the connection file atomically, so a client never reads a half-written one.

    The temp file is always a new one (O_EXCL, never through a symlink) and the file owner-only:
    reusing one left behind kept that file's mode, and the rename gave it to the connection file,
    token and all."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_atomic(path, json.dumps(info), mode=0o600)


def remove_info_file(path: Path, token: str | None = None) -> None:
    """Delete the connection file, but only our own: when `token` is given and the file now
    holds another server's token, leave it alone."""
    if token is not None:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = None
        if isinstance(current, dict) and current.get("token") != token:
            return
    path.unlink(missing_ok=True)


def is_own_file(path: str, state_dir: Path, export_dir: Path) -> bool:
    """True for a file of Swiss Army Bench's own: the connection file, or anything in the state folder
    except the export folder inside it (an export loaded back is a table). An unusable path is not
    one: the loader says why."""
    try:
        target = Path(path).expanduser().resolve()
        connection = info_file_path().expanduser().resolve()
        state = state_dir.expanduser().resolve()
        exports = export_dir.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    inside_state = target.is_relative_to(state) and not target.is_relative_to(exports)
    return target == connection or inside_state


# ===== the relationship sets =====
# Relationship sets (saved sets of relationships, domain/relationships.py has the file's shape) and the
# older model JSON files. Read in this order, a later one with the same name winning:
#
#   1. the models shipped in the package (src/swissarmybench/models/*.json), released with it
#   2. ~/.swissarmybench/models/*.json: a person's own older models
#   3. the library's relationship-sets/: a person's own sets ("mine"), where Save as a set writes by
#      default (and, one release, the library's old tangs/ folder, for a clone not moved yet)
#   4. every folder in SWISSARMYBENCH_MODELS (separated by ; on Windows)
#   5. the shared folders: the blade folders, so one team folder carries blades and sets alike
#      (.relationships.json files, and the old .tang ones, at any depth up to SHARED_DEPTH, hidden
#      folders and environments skipped). A set saved there is in a coworker's list the next time
#      their window opens.

SHARED_DEPTH = 4
_SKIPPED_DIRS = frozenset(
    {"__pycache__", "node_modules", "site-packages", ".venv", "venv", "env", "build", "dist"}
)
# Where a set may be renamed or deleted: the person's own and the shared folders. The package's, a
# pack's (from a marketplace: changed in its repository) and SWISSARMYBENCH_MODELS' are read-only.
EDITABLE = ("mine", "shared")


class ModelFiles:
    """The relationship sets and models: the service layer's `ModelLibrary` port. `shared` gives the
    shared folders (the blade folders that exist) each time, so a change there shows at once."""

    def __init__(
        self,
        state_dir: Path,
        shared: Callable[[], list[str]] | None = None,
        packs: Callable[[], list[tuple[Path, str]]] | None = None,
        library: Callable[[], Path] | None = None,
        made: Callable[[], object] | None = None,
    ) -> None:
        self.state_dir = state_dir
        self._made = made or (lambda: None)  # the library's README.md and .gitignore, on its first write
        # The library's relationship-sets/ (Plans/library.plan.md): where a saved set goes.
        self._library = library
        self._shared = shared or (lambda: [])
        # Installed packs' relationship-sets folders (adapters/packs.py): read-only sets from a marketplace.
        self._packs = packs or (lambda: [])

    @property
    def mine(self) -> Path:
        root = self._library() if self._library else self.state_dir
        return root / RELATIONSHIP_SETS

    @property
    def _old_mine(self) -> Path:
        root = self._library() if self._library else self.state_dir
        return root / OLD_TANGS

    def folders(self) -> list[str]:
        return [str(folder) for folder, _ in self._folders()]

    def shared_folders(self) -> list[str]:
        return [p for p in self._shared() if Path(p).is_dir()]

    def _folders(self) -> list[tuple[Path, str]]:
        folders = [
            (Path(str(files("swissarmybench").joinpath("models"))), "package"),
            (self.state_dir / "models", "mine"),
            (self._old_mine, "mine"),
            (self.mine, "mine"),
        ]
        folders += [
            (Path(p), "environment") for p in env("SWISSARMYBENCH_MODELS", "").split(os.pathsep) if p.strip()
        ]
        folders += [(Path(p), "shared") for p in self.shared_folders()]
        folders = [(folder, "pack") for folder, _ in self._packs()] + folders  # a clone wins over its install
        return folders

    def _set_files(self, folder: Path, deep: bool) -> list[Path]:
        if not deep:
            return sorted(p for p in folder.iterdir() if p.is_file() and is_set_file(p.name))
        found: list[Path] = []
        for root, dirs, names in os.walk(folder):
            depth = len(Path(root).relative_to(folder).parts)
            dirs[:] = (
                []
                if depth >= SHARED_DEPTH
                else sorted(d for d in dirs if not d.startswith(".") and d not in _SKIPPED_DIRS)
            )
            found += [Path(root) / n for n in sorted(names) if is_set_file(n)]
            if len(found) > 2000:
                break
        return found

    def read(self) -> tuple[dict[str, tuple[Model, str]], list[str]]:
        """Every set and model by name (with its file), and the files that could not be read."""
        found: dict[str, tuple[Model, str]] = {}
        problems: list[str] = []
        for folder, where in self._folders():
            if not folder.is_dir():
                continue
            plain = sorted(p for p in folder.glob("*.json") if not is_set_file(p.name))
            for path in plain if where not in ("shared", "pack") else []:
                try:
                    model = parse_model(json.loads(path.read_text(encoding="utf-8")))
                    found[model.name] = (model, str(path))
                except (OSError, ValueError) as error:
                    problems.append(f"{path.name}: {error}")
            for path in self._set_files(folder, deep=where in ("shared", "pack")):
                try:
                    if path.stat().st_size > 2_000_000:
                        raise RelationshipSetError("larger than 2 MB")
                    model = read_set(path.read_text(encoding="utf-8"))
                    found[model.name] = (model, str(path))
                except (OSError, ValueError) as error:
                    problems.append(f"{path.name}: {error}")
        return found, problems

    def where(self, path: str) -> str:
        """Which kind of folder a library file is in: package, mine, environment, shared or pack."""
        target = Path(path).resolve()
        for folder, kind in reversed(self._folders()):
            try:
                if target.is_relative_to(folder.resolve()):
                    return kind
            except OSError:
                continue
        return "mine"

    def save(self, model: Model, folder: str | None) -> str:
        """Write the set into the person's own folder, or into one of the shared folders (and no other).
        The same name writes the same file again: saving a set updates it, and a save that changes
        nothing but the time changes no byte (the library is made to be a Git repository)."""
        if folder is None:
            target = self.mine
        else:
            shared = {os.path.normcase(str(Path(p).resolve())): Path(p) for p in self.shared_folders()}
            chosen = shared.get(os.path.normcase(str(Path(folder).resolve())))
            if chosen is None:
                raise ValueError("Save into your own sets or one of the shared folders (the blade folders).")
            target = chosen
        if folder is None:
            self._made()
        target.mkdir(parents=True, exist_ok=True)
        path = target / set_file_name(model.name)
        if path.is_file():
            try:
                if same_set(read_set(path.read_text(encoding="utf-8")), model):
                    return str(path)
            except (OSError, ValueError):
                pass
        path.write_text(write_set(model), encoding="utf-8", newline="\n")
        return str(path)

    def _editable(self, path: str) -> Path:
        where = self.where(path)
        if where not in EDITABLE:
            said = {"package": "built in", "pack": "from a pack (change it in its repository)"}
            raise PermissionError(
                f"This set is {said.get(where, 'read-only here')}: it cannot be changed here."
            )
        return Path(path)

    def delete(self, path: str) -> None:
        """Delete a set's file (the person's own or a shared folder's)."""
        self._editable(path).unlink(missing_ok=True)

    def rename(self, path: str, model: Model, new: str) -> str:
        """The set saved again under its new name, beside its old file, and the old file gone. Answers
        the new file's path."""
        old = self._editable(path)
        target = old.parent / set_file_name(new)
        if target.exists() and target.resolve() != old.resolve():
            raise FileExistsError(f"{target.name} is there already: choose another name.")
        target.write_text(write_set(replace(model, name=new)), encoding="utf-8", newline="\n")
        if target.resolve() != old.resolve():
            old.unlink(missing_ok=True)
        return str(target)
