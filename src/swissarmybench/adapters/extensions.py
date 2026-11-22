"""The installed extensions: the entry points under `swissarmybench.extensions`, read once at start, and the
library's folder extensions (library/extensions/<id>/, loaded by swissarmybench/extensions.py).

An extension's package declares, in its pyproject:

    [project.entry-points."swissarmybench.extensions"]
    accounting = "swissarmybench_accounting:describe"

where `describe` is a dict, or a function giving one: {"id", "name", "description", "version", "adds"}.
SWISSARMYBENCH_EXTENSIONS (ids, comma separated) treats more as installed: tests and development only.

FolderExtensions is the Extensions page's edge on the folders: each one as Found, New extension's folder
written (never over one that is there), Remove's move to the system's trash, Show its folder, Load again.
"""

from __future__ import annotations

import importlib.metadata
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from swissarmybench import extensions as loader
from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import extensions as rules
from swissarmybench.domain import project_contract
from swissarmybench.domain.extensions import Found


def _entry_points() -> Iterable[Any]:
    return importlib.metadata.entry_points(group=rules.GROUP)


def _with_contract(found: Found, module: ModuleType | None) -> Found:
    """Its contract.json's project type and deliverable on the card (a broken one: none said here)."""
    if module is None:
        return found
    try:
        said = loader.contract(module)
    except (OSError, project_contract.ContractError):
        return found
    if said is None:
        return found
    return Found(
        **{k: getattr(found, k) for k in found.__dataclass_fields__}
        | {
            "project_type": said["type"],
            "project_name": said["name"],
            "deliverable": tuple(project_contract.deliverable_files(said)),
        }
    )


def discover(
    environ: Mapping[str, str] | None = None, entry_points: Callable[[], Iterable[Any]] = _entry_points
) -> dict[str, Found]:
    """Every installed extension package by its id; one that fails to load is left out (the app starts
    anyway). The library's folder extensions are FolderExtensions'."""
    found: dict[str, Found] = {}
    try:
        points = list(entry_points())
    except Exception:  # a broken install's metadata: no extensions rather than no app
        points = []
    for point in points:
        try:
            value = point.load()
            dist = getattr(point, "dist", None)
            said = rules.describe(
                str(point.name),
                value,
                str(getattr(dist, "name", "") or ""),
                str(getattr(dist, "version", "") or ""),
            )
        except Exception:  # noqa: S112 (an extension that cannot load is not installed)
            continue
        if said is not None:
            found.setdefault(said.id, said)
    told = (environ if environ is not None else os.environ).get(rules.ENV)
    for ident in rules.from_env(told):
        found.setdefault(ident, Found(id=ident))
    kept = {ident: f for ident, f in found.items() if ident not in rules.turned_off(told)}
    return {ident: _with_contract(f, loader.load(ident)) for ident, f in kept.items()}


class FolderExtensions:
    """The library's folder extensions, for the Extensions page (services/extensions.py's Folders port)."""

    def __init__(self, trasher: Callable[[str], str], opener: Callable[[str], None]) -> None:
        # The system's trash and file manager: processes the server starts (server/file_manager.py).
        self._trasher = trasher
        self._opener = opener

    def found(self) -> dict[str, Found]:
        """Each folder as Found (source "folder"), loaded or not; one a package of its id wins over is left
        out (the package's card says so: shadowed)."""
        out: dict[str, Found] = {}
        for ident, folder in loader.folders().items():
            if folder.shadowed:
                continue
            module = folder.module
            described = _described(module, folder.manifest)
            said = folder.contract
            out[ident] = Found(
                id=ident,
                version=str(described.get("version") or ""),
                name=str(described.get("name") or ident),
                description=str(described.get("description") or ""),
                adds=tuple(str(a) for a in described.get("adds") or ()),
                source="folder",
                path=str(folder.path),
                error=folder.error,
                missing=tuple(folder.missing),
                project_type=said["type"] if said else "",
                project_name=said["name"] if said else "",
                deliverable=tuple(project_contract.deliverable_files(said)) if said else (),
            )
        return out

    def shadowed(self) -> dict[str, str]:
        """The folders a package of the same id wins over: {id: the words for the package's card}."""
        return {i: f.error for i, f in loader.folders().items() if f.shadowed}

    def module(self, ident: str) -> ModuleType | None:
        found = loader.folders().get(ident)
        return found.module if found is not None else None

    def place(self, ident: str) -> str:
        return str(loader.folders_root() / ident)

    def make(self, ident: str, files: dict[str, str]) -> str:
        """New extension's folder, written whole (FileExistsError: one is there)."""
        folder = Path(self.place(ident))
        if folder.exists():
            raise FileExistsError(f"{folder} is there already.")
        folder.mkdir(parents=True)
        for relative, text in files.items():
            write_atomic(folder / relative, text)
        loader.forget_folders(ident)
        return str(folder)

    def trash(self, ident: str) -> str:
        """Its folder to the system's trash; where it went, in words."""
        folder = loader.folders().get(ident)
        if folder is None:
            raise FileNotFoundError(f"There is no folder extension {ident}.")
        went = self._trasher(str(folder.path))
        loader.forget_folders(ident)
        return went

    def show(self, ident: str) -> None:
        folder = loader.folders().get(ident)
        if folder is None:
            raise FileNotFoundError(f"There is no folder extension {ident}.")
        self._opener(str(folder.path))

    def reload(self, ident: str) -> None:
        """Read it again from its folder (its modules dropped first)."""
        loader.forget_folders(ident)


def _described(module: ModuleType | None, manifest: dict[str, Any]) -> dict[str, Any]:
    """Its card's words: describe(), else its module's values, else what its file says before it loads."""
    if module is None:
        return {k.lower(): v for k, v in manifest.items()}
    made = getattr(module, "describe", None)
    try:
        said = made() if callable(made) else {}
    except Exception:  # its own code: its card from its values instead
        said = {}
    said = said if isinstance(said, dict) else {}
    for key, attr in (
        ("name", "NAME"),
        ("description", "DESCRIPTION"),
        ("version", "VERSION"),
        ("adds", "ADDS"),
    ):
        said.setdefault(key, getattr(module, attr, None))
    return said
