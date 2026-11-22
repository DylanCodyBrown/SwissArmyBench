"""Extensions: optional packages that plug into this one app (Plans/editions.plan.md, the owner 2026-11-17).

An extension is a package that registers itself under the entry-point group `swissarmybench.extensions`
(its entry point names a module: `accounting = "swissarmybench_accounting.extension"`). The base finds the
installed ones here; nothing else in the shared code names one.

  extension_on(id)  the one capability check: installed (its entry point, or a folder in the library that
                    loaded), or named in SWISSARMYBENCH_EXTENSIONS (a comma list: a checkout or a test turns
                    one on without installing it; "-accounting" turns an installed one off)
  load(id)          its module (None: off, or it cannot be imported)
  enabled()         the on ones' modules, in id order
  folders()         the library's folder extensions (its extensions/<id>/, Plans/folder-extensions.plan.md):
                    each loaded as the package sab_ext_<id>, or kept with why not (its error, its missing
                    packages, a package of the same id winning); use_library(path): the server's library
  contract(module)  its contract.json (domain/project_contract.py), the project type it adds
  modes()           every project type's mode, as data: the base's (BI) and each on extension's MODE
  mode_of(type)     a project type's mode (an unknown or missing type: the base's)

A mode is the working set a project type sets (Plans/editions.plan.md, "Project modes"): the canvas kinds,
the blade and function families shown first, the languages, the extra cell kinds, the agent's tool group
and the export. It is declared, never coded: shared code reads these fields, and never asks which type it
is. Until the manifest boundary exists the extension's MODE lives in its extension module (the entry point).

Standard library and the domain's rules only (the MCP server reads it to order its tools).
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from swissarmybench.domain import extension_folders as folder_rules
from swissarmybench.domain import project_contract
from swissarmybench.domain.packages import pip_name

GROUP = "swissarmybench.extensions"
VARIABLE = "SWISSARMYBENCH_EXTENSIONS"

# The base's own project type: a BI project (a notebook as its deliverable); every family shows (an empty
# list: all). An extension that is on may add to it (its BASE_MODE_ADDS: the preinstalled Streamlit
# extension's canvas, offered in a BI project as before it was an extension).
BASE_MODE: dict[str, Any] = {
    "type": "bi",
    "name": "BI",
    "deliverable": "a notebook",
    "canvases": [],
    "families": [],
    "languages": ["python"],
    "cell_kinds": [],
    "tools": [],
    "export": ["notebook"],
    # The Project Explorer's words for beginners (the owner, 2026-11-17): each mode brings its own.
    "title": "Analysis",
    "for_whom": "For anyone exploring data and handing over what they found.",
    "explain": (
        "Explore your data in notebooks: tables from files and connections, SQL that shapes them, charts "
        "and statistics. You get data.ipynb for the tables, notebooks for the analysis, and the Analyze "
        "board for the report."
    ),
    "example": "Example: a quarter's sales by region, checked and charted for the finance team.",
    # The cell kinds this mode runs somewhere else than the Python kernel: {kind: {name, language, run
    # (the route a run is posted to), preview (a route that draws it), grid (a table result opened as a
    # grid), types (the editor's declarations), install (a missing tool installed)}}; a base kind too (a
    # DuckDB SQL cell run in the mode's kernel). The page reads them as data, never which mode it is.
    "cell_routes": {},
    # A route answering the project's files a person edits ({"files": [...]}), listed in the Workbench's
    # project files ("" for none: the base's own listing).
    "project_files": "",
    # The editors' inline completion (ghost text): each on extension's INLINE_COMPLETION, in every mode, as
    # data: {id, name, languages, complete, cancel, event, status, toggle} (routes the editor calls).
    "inline_completion": [],
    # Buttons an on extension adds to a base page (its PAGE_ACTIONS), in every mode, as data: {page, id,
    # label, icon, title}; the page runs its plug-in of that id (web/src/pageActions.ts), never naming it.
    "page_actions": [],
    # The features open in a project of this type (the rail's areas; empty: all of them, as for every type
    # but one that keeps some closed to stay simple), the first-open pop-up's words ({closed}: the closed
    # features' names) and the tour's own cards ({area, words}).
    "areas": [],
    "first_open": "",
    "tour": [],
}
# A Streamlit app, for beginners: a base project with its app's canvas (until the Streamlit extension brings
# its own project type, whose mode then says it). `make` is what New project sends for it.
STREAMLIT_KIND: dict[str, Any] = {
    "type": "streamlit",
    "name": "Streamlit app",
    "title": "Streamlit app",
    "deliverable": "a Streamlit app",
    "for_whom": "For people who want others to click through their data in a small web app.",
    "explain": (
        "Make the tables in data.ipynb, then place your notebooks' cells on pages: charts, tables, filters "
        "and buttons. You get data.ipynb, an app canvas and pages/*.py that run anywhere Streamlit runs."
    ),
    "example": "Example: a sales dashboard where each manager picks their region.",
    "make": {"type": "bi", "app": True},
}
_ROUTE_FIELDS = ("name", "language", "run", "preview", "grid", "types", "install")
_MODE_FIELDS = ("canvases", "families", "languages", "cell_kinds", "tools", "export")


def _said(environ: dict[str, str] | None = None) -> tuple[set[str], set[str]]:
    """The variable's ids turned on, and the ones turned off ("-id")."""
    raw = (os.environ if environ is None else environ).get(VARIABLE, "")
    words = [w.strip().lower() for w in raw.split(",") if w.strip()]
    return {w for w in words if not w.startswith("-")}, {w[1:] for w in words if w.startswith("-")}


# The entry points read once per process (every package's metadata is read for them: 10 ms a request), again
# when the import path changes. An extension's Install and Remove restart the app (server/updater.py).
_installed: tuple[tuple[str, ...], dict[str, str]] | None = None


def installed() -> dict[str, str]:
    """The installed extensions' entry points: {id: "module"}."""
    global _installed
    path = tuple(sys.path)
    if _installed is None or _installed[0] != path:
        try:
            found = {ep.name.lower(): ep.value for ep in importlib.metadata.entry_points(group=GROUP)}
        except Exception:  # a broken install never stops the app
            found = {}
        _installed = (path, found)
    return dict(_installed[1])


def forget_installed() -> None:
    """Read the entry points again on the next ask (an install in this process: tests, development)."""
    global _installed
    _installed = None


def _package_on(name: str, environ: dict[str, str] | None = None) -> bool:
    on, off = _said(environ)
    return name not in off and (name in on or name in installed())


def extension_on(extension: str, environ: dict[str, str] | None = None) -> bool:
    """Is this extension on: installed (a package, or a folder in the library that loaded) or named in
    SWISSARMYBENCH_EXTENSIONS, and not turned off there."""
    name = extension.lower()
    if _package_on(name, environ):
        return True
    _, off = _said(environ)
    found = folders().get(name)
    return name not in off and found is not None and found.module is not None


def _package(name: str) -> ModuleType | None:
    if not _package_on(name):
        return None
    target = installed().get(name, f"swissarmybench_{name}.extension")
    try:
        return importlib.import_module(target.split(":")[0])
    except Exception:  # named but not importable here: off
        return None


def load(extension: str) -> ModuleType | None:
    """The extension's module when it is on (its entry point's, else `swissarmybench_<id>.extension`; else
    the library's folder of that id)."""
    name = extension.lower()
    module = _package(name)
    if module is not None or not extension_on(name):
        return module
    found = folders().get(name)
    return found.module if found is not None else None


def enabled() -> list[ModuleType]:
    """Every extension that is on and imports, in id order: the packages', then the library's folders'."""
    on, off = _said()
    packages = {i: m for i in sorted(set(installed()) | on) if (m := _package(i)) is not None}
    for ident, found in folders().items():
        if found.module is not None and ident not in off and ident not in packages:
            packages[ident] = found.module
    return [packages[i] for i in sorted(packages)]


# ===== folder extensions: the library's extensions/<id>/ (Plans/folder-extensions.plan.md) =====
#
# Found at start beside the packages (the folders are read once per process, again after forget_folders: New
# extension, Remove, Load again), each loaded as the package sab_ext_<id> (its folder that package's only
# path). One that fails is kept with its error (never stops the app), one whose REQUIRES are missing is not
# loaded until they are installed, and one with a package's id loses to the package. Its contract.json (when
# it adds a project type) gives its MODE and its New project files where extension.py declares neither.

FOLDERS_VARIABLE = "SWISSARMYBENCH_EXTENSION_FOLDERS"  # a folder of folder extensions: tests and development


@dataclass
class Folder:
    """A folder extension as found: its module once loaded, else why not."""

    id: str
    path: Path
    module: ModuleType | None = None
    error: str = ""
    missing: list[str] = field(default_factory=list)
    shadowed: bool = False  # a package of the same id is on: it wins
    contract: dict[str, Any] | None = None
    # Its literal NAME, VERSION... read before it loads (its card when it does not).
    manifest: dict[str, Any] = field(default_factory=dict)


_library: Path | None = None
_folders: tuple[Path, dict[str, Folder]] | None = None


def _state_library() -> Path:
    """The library as the state folder says (SWISSARMYBENCH_STATE or ~/.swissarmybench; library.json's
    folder when Settings moved it): what a process with no Settings of its own (the MCP server) reads."""
    told = os.environ.get("SWISSARMYBENCH_STATE", "")
    state = Path(told) if told else Path.home() / ".swissarmybench"
    try:
        chosen = json.loads((state / "library.json").read_text(encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        chosen = None
    return Path(chosen) if isinstance(chosen, str) and chosen.strip() else state / "library"


def use_library(folder: Path | None) -> None:
    """The library the server uses (bootstrap's Settings); None: the state folder's. Its folders read
    again."""
    global _library
    _library = folder
    forget_folders()


def folders_root() -> Path:
    """Where folder extensions are: SWISSARMYBENCH_EXTENSION_FOLDERS, else the library's extensions/."""
    told = os.environ.get(FOLDERS_VARIABLE, "")
    if told:
        return Path(told)
    return (_library if _library is not None else _state_library()) / folder_rules.FOLDER


def forget_folders(ident: str | None = None) -> None:
    """Read the folders again on the next ask; each loaded one's modules dropped (all, or `ident`'s)."""
    global _folders
    prefixes = [folder_rules.MODULE_PREFIX + (ident or "")]
    for name in [n for n in sys.modules if any(n.startswith(p) for p in prefixes)]:
        del sys.modules[name]
    importlib.invalidate_caches()  # a file just written (New extension) is seen on the next import
    _folders = None
    _contracts.clear()


def folders() -> dict[str, Folder]:
    """The library's folder extensions by id (loaded once per process, in id order)."""
    global _folders
    root = folders_root()
    if _folders is not None and _folders[0] == root:
        return _folders[1]
    try:
        names = sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "extension.py").is_file())
    except OSError:
        names = []
    found = {n: _load_folder(n, root / n) for n in names if folder_rules.is_id(n)}
    _folders = (root, found)
    return found


def _missing(requires: list[str]) -> list[str]:
    out: list[str] = []
    for line in requires:
        try:
            importlib.metadata.distribution(folder_rules.dist_name(line))
        except Exception:  # not there (PackageNotFoundError), or a broken install's metadata: as missing
            out.append(line)
    return out


def _load_folder(ident: str, path: Path) -> Folder:
    """One folder: its contract checked, its REQUIRES present, then extension.py imported as sab_ext_<id>."""
    found = Folder(ident, path)
    if _package_on(ident):
        found.shadowed, found.error = True, folder_rules.shadowed(ident)
        return found
    try:
        source = (path / "extension.py").read_text(encoding="utf-8")
        found.manifest = folder_rules.literals(source)
        found.missing = _missing(folder_rules.requires_of(source))
        if (path / project_contract.FILE).is_file():
            found.contract = project_contract.read((path / project_contract.FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, project_contract.ContractError) as error:
        found.error = f"It did not load: {error}"
        return found
    if found.missing:
        return found
    package = folder_rules.MODULE_PREFIX + ident
    try:
        if (
            f"{package}.extension" not in sys.modules
        ):  # read again after another folder's change: kept as it is
            spec = importlib.machinery.ModuleSpec(package, None, is_package=True)
            holder = importlib.util.module_from_spec(spec)
            holder.__path__ = [str(path)]
            sys.modules[package] = holder
        module = importlib.import_module(f"{package}.extension")
    except ModuleNotFoundError as error:
        forget_folders(ident)
        if error.name and not error.name.startswith(folder_rules.MODULE_PREFIX):
            found.missing = [pip_name(error.name)[0]]
        else:
            found.error = folder_rules.load_error(error, str(path))
        return found
    except (Exception, SystemExit) as error:  # its own code: listed with its error, never the app's stop
        forget_folders(ident)
        found.error = folder_rules.load_error(error, str(path))
        return found
    declared = getattr(module, "ID", None)
    if declared is not None and str(declared).lower() != ident:
        forget_folders(ident)
        found.error = folder_rules.wrong_id(str(declared), ident)
        return found
    _complete(module, ident, path, found.contract)
    found.module = module
    return found


def _complete(module: ModuleType, ident: str, path: Path, contract: dict[str, Any] | None) -> None:
    """What a folder extension leaves out, from its folder: its ID, its commands' area, and (with a contract)
    its MODE and New project's files."""
    module.ID = ident  # type: ignore[attr-defined]
    module.FOLDER = str(path)  # type: ignore[attr-defined]
    if not getattr(module, "AREAS", None):
        module.AREAS = ((ident, f"{getattr(module, 'NAME', ident)}: a folder extension"),)  # type: ignore[attr-defined]
    if contract is None:
        return
    module.CONTRACT = contract  # type: ignore[attr-defined]
    if getattr(module, "MODE", None) is None:
        module.MODE = project_contract.as_mode(contract) | {"tools": [f"{ident}_"]}  # type: ignore[attr-defined]
    if getattr(module, "scaffold", None) is None:
        module.scaffold = lambda name, _names: project_contract.scaffold(contract, name)  # type: ignore[attr-defined]


_contracts: dict[str, dict[str, Any] | None] = {}


def contract(module: ModuleType) -> dict[str, Any] | None:
    """An extension's contract.json, checked (its package root's: beside its extension.py), or None (it adds
    no project type). A broken one raises ContractError."""
    if isinstance(getattr(module, "CONTRACT", None), dict):
        return dict(module.CONTRACT)
    key = module.__name__
    if key not in _contracts:
        file = Path(module.__file__ or "").with_name(project_contract.FILE)
        _contracts[key] = project_contract.read(file.read_text(encoding="utf-8")) if file.is_file() else None
    return _contracts[key]


def _mode(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        return None
    mode = dict(BASE_MODE) | {k: v for k, v in raw.items() if k in BASE_MODE or k == "make"}
    for key in ("title", "for_whom", "explain", "example"):  # an extension's own words, or none
        mode[key] = str(raw.get(key) or "")
    for key in _MODE_FIELDS:
        value = mode.get(key)
        mode[key] = [str(v) for v in value] if isinstance(value, list | tuple) else []
    mode["project_files"] = str(mode.get("project_files") or "")
    areas = raw.get("areas")
    mode["areas"] = [str(a) for a in areas] if isinstance(areas, list | tuple) else []
    mode["first_open"] = str(raw.get("first_open") or "")
    tour = raw.get("tour")
    mode["tour"] = (
        [
            {"area": str(t.get("area", "")), "words": str(t.get("words", ""))}
            for t in tour
            if isinstance(t, dict)
        ]
        if isinstance(tour, list | tuple)
        else []
    )
    routes = mode.get("cell_routes")
    mode["cell_routes"] = (
        {
            str(kind): {k: str(v) for k, v in spec.items() if k in _ROUTE_FIELDS}
            for kind, spec in routes.items()
            if isinstance(spec, dict)
        }
        if isinstance(routes, dict)
        else {}
    )
    return mode


def base_mode(on: list[ModuleType] | None = None) -> dict[str, Any]:
    """The base's mode, with what each on extension adds to it (its BASE_MODE_ADDS: lists, by field)."""
    mode = {k: list(v) if isinstance(v, list) else v for k, v in BASE_MODE.items()}
    for module in enabled() if on is None else on:
        adds = getattr(module, "BASE_MODE_ADDS", None)
        for key, values in (adds if isinstance(adds, dict) else {}).items():
            if key in _MODE_FIELDS and isinstance(values, list | tuple):
                mode[key] = list(dict.fromkeys([*mode[key], *(str(v) for v in values)]))
    return mode


_INLINE_FIELDS = ("id", "name", "complete", "cancel", "event", "status", "toggle")


def inline_completions(on: list[ModuleType]) -> list[dict[str, Any]]:
    """The on extensions' inline completion providers (their INLINE_COMPLETION), read loosely: one with no
    name or no complete route is left out. Not a project type's: every mode carries them."""
    out: list[dict[str, Any]] = []
    for module in on:
        raw = getattr(module, "INLINE_COMPLETION", None)
        if not isinstance(raw, dict) or not raw.get("name") or not raw.get("complete"):
            continue
        said: dict[str, Any] = {k: str(raw.get(k) or "") for k in _INLINE_FIELDS}
        languages = raw.get("languages")
        said["languages"] = [str(x) for x in languages] if isinstance(languages, list | tuple) else ["python"]
        out.append(said)
    return out


_ACTION_FIELDS = ("page", "id", "label", "icon", "title")


def page_actions(on: list[ModuleType]) -> list[dict[str, str]]:
    """The buttons the on extensions add to the base's pages (their PAGE_ACTIONS), read loosely: one with no
    page, id or label is left out."""
    out: list[dict[str, str]] = []
    for module in on:
        raw = getattr(module, "PAGE_ACTIONS", None)
        for action in raw if isinstance(raw, list | tuple) else ():
            if isinstance(action, dict) and all(action.get(k) for k in ("page", "id", "label")):
                out.append({k: str(action.get(k) or "") for k in _ACTION_FIELDS})
    return out


def opens() -> dict[str, str]:
    """The files the on extensions open: each one's OPENS, {".suffix": a route}."""
    out: dict[str, str] = {}
    for module in enabled():
        raw = getattr(module, "OPENS", None)
        for suffix, route in raw.items() if isinstance(raw, dict) else ():
            if (
                isinstance(suffix, str)
                and suffix.startswith(".")
                and isinstance(route, str)
                and route.startswith("/")
            ):
                out.setdefault(suffix.lower(), route)
    return out


def modes() -> list[dict[str, Any]]:
    """Every project type's mode: the base's first, then each on extension's (its MODE); each with the on
    extensions' inline completion providers."""
    on = enabled()
    out = [base_mode(on)]
    for module in on:
        mode = _mode(getattr(module, "MODE", None))
        if mode is not None and mode["type"] not in {m["type"] for m in out}:
            out.append(mode)
    providers = inline_completions(on)
    actions = page_actions(on)
    for mode in out:
        mode["inline_completion"] = [dict(p) for p in providers]
        mode["page_actions"] = [dict(a) for a in actions]
    return out


_AREA_FIELDS = ("area", "name", "icon", "mark", "panel")  # panel: only when an area names one


def areas() -> list[dict[str, Any]]:
    """The rail's areas the on extensions add (each one's RAIL: {area, name, icon, mark?}), as data."""
    out: list[dict[str, Any]] = []
    for module in enabled():
        for raw in getattr(module, "RAIL", ()) or ():
            if (
                isinstance(raw, dict)
                and isinstance(raw.get("area"), str)
                and raw["area"] not in {a["area"] for a in out}
            ):
                said = {k: str(raw.get(k) or "") for k in _AREA_FIELDS if k != "panel"}
                out.append(said | ({"panel": str(raw["panel"])} if raw.get("panel") else {}))
    return out


def mode_of(project_type: str | None) -> dict[str, Any]:
    """A project type's mode; the base's for no project, or a type whose extension is not on."""
    found = modes()
    return next((m for m in found if m["type"] == project_type), found[0])
