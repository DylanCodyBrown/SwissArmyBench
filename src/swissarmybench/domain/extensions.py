"""The Extensions page's rules (Plans/editions.plan.md, Plans/folder-extensions.plan.md).

The owner, 2026-11-27: "Also I think all extensions should be built in now"; merged into the one package, with
no Remove. Streamlit, Accounting, Power Apps, Power BI, Git and GitHub Copilot are built in: on every install,
never installed, never removed, so the page has no catalog of them and no status to tell apart.

What the page lists:
    a folder extension  the user's own, a folder in the library (`library/extensions/<id>/`; its rules are
                        domain/extension_folders.py's): status "installed", source "folder", its path, whether
                        it is on, its load error and its missing packages (the one missing-package answer).
                        Install is its packages and Load again; Remove moves its folder to the trash (the
                        user's own; the agent's on Allow); no restart
    a built-in feature  only one that brings a panel of its own (its sign-in and switches, as data): status
                        "builtin", nothing to install or remove
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.packages import missing_packages

STATUSES: tuple[str, ...] = ("builtin", "installed")
MAX_ID: int = 40


@dataclass(frozen=True)
class BuiltIn:
    """A built-in feature as its module declares it: its id and name (every one: a folder may not take its
    id), and its panel's route when it has one (then it has a card)."""

    id: str
    name: str
    description: str = ""
    adds: tuple[str, ...] = ()
    panel: str = ""


class ExtensionError(ValueError):
    """An extension that is not one, or cannot be installed or removed from here."""


@dataclass(frozen=True)
class Found:
    """A folder extension, as its folder's extension.py described it."""

    id: str
    version: str = ""
    name: str = ""
    description: str = ""
    adds: tuple[str, ...] = field(default_factory=tuple)
    source: str = "folder"
    path: str = ""  # its folder
    error: str = ""  # a folder that did not load: its one sentence (with the line)
    missing: tuple[str, ...] = ()  # its REQUIRES not in the app's Python (it is not on until they are)
    project_type: str = ""  # its contract.json's type
    project_name: str = ""
    deliverable: tuple[str, ...] = ()  # its contract.json's files


def check_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtensionError('Send {"id": "<an extension\'s id>"}.')
    text = value.strip().lower()
    if len(text) > MAX_ID or not all(c.isalnum() or c in "-_" for c in text):
        raise ExtensionError(f"{value!r} is not an extension's id.")
    return text


def listed(built_in: tuple[BuiltIn, ...], found: dict[str, Found], current: str) -> list[dict[str, Any]]:
    """The page's cards: each built-in feature with a panel of its own, then the library's folder extensions
    (one with a built-in feature's id is listed too, with why it is not loaded)."""
    out: list[dict[str, Any]] = [
        {
            "id": feature.id,
            "name": feature.name or feature.id,
            "description": feature.description,
            "adds": list(feature.adds),
            "status": "builtin",
            "version": current,
            "panel": feature.panel,
        }
        for feature in built_in
        if feature.panel
    ]
    for ident, here in found.items():
        entry: dict[str, Any] = {
            "id": ident,
            "name": here.name or ident,
            "description": here.description,
            "adds": list(here.adds),
            "status": "installed",
            "version": here.version or None,
        }
        out.append(entry | _folder_fields(here) | _contract_fields(here))
    return out


def _folder_fields(here: Found) -> dict[str, Any]:
    """A folder extension's card: where it is, whether it is on, why not (its error, its missing packages)."""
    feature = f"The {here.name or here.id} extension"
    # Into the app's own Python ("app"): its command names no other Python.
    missing = missing_packages(feature, list(here.missing), "", own=True) if here.missing else None
    return {
        "source": "folder",
        "path": here.path,
        "on": not here.error and not here.missing,
        "error": here.error or None,
        "missing": missing,
    }


def _contract_fields(here: Found) -> dict[str, Any]:
    """What its contract.json says, for its card: the project type it adds and the deliverable's files."""
    if not here.project_type:
        return {}
    return {
        "project_type": here.project_type,
        "project_name": here.project_name or here.project_type,
        "deliverable": list(here.deliverable),
    }


def built_in_words(name: str, action: str) -> str:
    """Install or Remove asked of a built-in feature: one sentence (the old Extensions page's buttons and the
    agent's extensions_install and extensions_remove of one, gone 2026-11-27)."""
    if action == "install":
        return f"{name} is built in: it is on every install, so there is nothing to install."
    return f"{name} is built in: it comes with Swiss Army Bench and cannot be removed."
