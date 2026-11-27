"""The Extensions page's edge: the built-in features as their modules declare them, and the library's folder
extensions (library/extensions/<id>/, loaded by swissarmybench/extensions.py).

built_in() reads each built-in feature's module (its ID, NAME, DESCRIPTION, ADDS and PANEL): every one's id
and name, so a folder never takes one's id, and its panel's route where it has one (its card).

FolderExtensions is the page's edge on the folders: each one as Found, New extension's folder written (never
over one that is there), Remove's move to the system's trash, Show its folder, Load again.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from swissarmybench import extensions as loader
from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import project_contract
from swissarmybench.domain.extensions import BuiltIn, Found


def built_in() -> tuple[BuiltIn, ...]:
    """The built-in features, in their order."""
    out: list[BuiltIn] = []
    for module in loader.built_in():
        said = loader.manifest(module)
        out.append(
            BuiltIn(
                id=said.ID.lower(),
                name=said.NAME,
                description=said.DESCRIPTION or str(_described(module, {}).get("description") or ""),
                adds=tuple(str(a) for a in said.ADDS),
                panel=said.PANEL if said.PANEL.startswith("/") else "",
            )
        )
    return tuple(out)


class FolderExtensions:
    """The library's folder extensions, for the Extensions page (services/extensions.py's Folders port)."""

    def __init__(self, trasher: Callable[[str], str], opener: Callable[[str], None]) -> None:
        # The system's trash and file manager: processes the server starts (server/file_manager.py).
        self._trasher = trasher
        self._opener = opener

    def found(self) -> dict[str, Found]:
        """Each folder as Found, loaded or not (one with a built-in feature's id: not loaded, and why)."""
        out: dict[str, Found] = {}
        for ident, folder in loader.folders().items():
            module = folder.module
            described = _described(module, folder.manifest)
            said = folder.contract
            out[ident] = Found(
                id=ident,
                version=str(described.get("version") or ""),
                name=str(described.get("name") or ident),
                description=str(described.get("description") or ""),
                adds=tuple(str(a) for a in described.get("adds") or ()),
                path=str(folder.path),
                error=folder.error,
                missing=tuple(folder.missing),
                project_type=said["type"] if said else "",
                project_name=said["name"] if said else "",
                deliverable=tuple(project_contract.deliverable_files(said)) if said else (),
            )
        return out

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
