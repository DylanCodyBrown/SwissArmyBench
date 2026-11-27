"""The built-in features and the library's folder extensions (Plans/editions.plan.md; the owner, 2026-11-27:
"Also I think all extensions should be built in now", merged into the one package, with no Remove).

Streamlit, Accounting, Power Apps, Power BI, Git and GitHub Copilot were packages of their own, installed and
removed on the Extensions page. They are built in now: each still its own package in the one wheel
(`swissarmybench_<id>`, its module `swissarmybench_<id>.extension` declaring what it adds), always on, on
every install. BUILT_IN names them; nothing else in the shared code names one. The user's own folder
extensions (the
library's extensions/<id>/) plug in the same way and stay installable and removable.

  extension_on(id)  the one capability check: built in, or a folder in the library that loaded
  load(id)          its module (None: not one, or it cannot be imported)
  enabled()         the built-in features' modules in their order, then the library's folders'
  folders()         the library's folder extensions (its extensions/<id>/, Plans/folder-extensions.plan.md):
                    each loaded as the package sab_ext_<id>, or kept with why not (its error, its missing
                    packages, a built-in feature of the same id winning); use_library(path): the server's
  contract(module)  its contract.json (domain/project_contract.py), the project type it adds
  modes()           every project type's mode, as data: the base's (BI) and each feature's MODE
  manifest(module)  its manifest: every module attribute a feature may declare, read once into one typed
                    record (Manifest); an upper-case name that is none of them is reported (`unknown`)
  mode_of(type)     a project type's mode (an unknown or missing type: the base's)

A mode is the working set a project type sets (Plans/editions.plan.md, "Project modes"): the canvas kinds,
the blade and function families shown first, the languages, the extra cell kinds, the agent's tool group
and the export. It is declared, never coded: shared code reads these fields, and never asks which type it
is.

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


@dataclass(frozen=True)
class Manifest:
    """Every module attribute an extension may declare (craft review 2026-11-22: one list, read once). A name
    the base reads is a field here; a misspelt one is in `unknown`, never quietly "not there"."""

    ID: str = ""
    NAME: str = ""
    VERSION: str = ""
    DESCRIPTION: str = ""
    ADDS: tuple[Any, ...] = ()
    PACKAGE: str = ""
    PROJECT_TYPE: str = ""
    FRONT_END: tuple[Any, ...] = ()
    AREAS: tuple[Any, ...] = ()  # (prefix, title) of its commands' areas
    MODE: Any = None  # its project type's mode, as data
    BASE_MODE_ADDS: Any = None  # what it adds to the base's mode, by field
    FAMILIES: tuple[Any, ...] = ()
    STARTERS: str = ""  # its starter pack's folder
    SECRET_PATHS: tuple[Any, ...] = ()  # its routes' prefixes that carry a secret in the address
    SESSION_RULES: Any = None  # the Session page's words for its audit entries
    RAIL: tuple[Any, ...] = ()  # the rail's areas it adds
    PANEL: str = ""  # its card's and Settings' panel route
    PAGE_ACTIONS: tuple[Any, ...] = ()  # the buttons it adds to the base's pages
    INLINE_COMPLETION: Any = None  # the editors' inline completion routes
    OPENS: Any = None  # the files it opens, {".suffix": a route}
    API_TARGETS: tuple[Any, ...] = ()  # the local sandbox API's framework targets it adds
    API_PATTERNS: tuple[Any, ...] = ()  # the endpoint wizard's patterns it adds
    REQUIRES: tuple[Any, ...] = ()  # a folder extension's packages
    CONTRACT: Any = None  # a folder extension's contract.json, as read
    FOLDER: str = ""  # a folder extension's folder
    # The upper-case names its module holds that are none of the above (its own constants, or a misspelling).
    unknown: tuple[str, ...] = ()


_MANIFEST_NAMES = tuple(f for f in Manifest.__dataclass_fields__ if f != "unknown")
# Its commands' own metadata, read by the registry with its commands (cli/commands.py), never here: reading
# them may import its commands, which import the registry.
COMMAND_NAMES = ("OLD_NAMES", "OLD_ARGS")
_TUPLES = {f for f, x in Manifest.__dataclass_fields__.items() if x.default == ()}
_TEXT = {f for f, x in Manifest.__dataclass_fields__.items() if x.default == ""}
_manifests: dict[int, tuple[ModuleType, Manifest]] = {}


def manifest(module: ModuleType) -> Manifest:
    """An extension module's manifest, read once (a folder extension read again is a new module)."""
    kept = _manifests.get(id(module))
    if kept is not None and kept[0] is module:
        return kept[1]
    given: dict[str, Any] = {}
    for name in _MANIFEST_NAMES:
        value = getattr(module, name, None)
        if value is None:
            continue
        if name in _TUPLES:
            value = tuple(value) if isinstance(value, list | tuple) else ()
        elif name in _TEXT:
            value = str(value)
        given[name] = value
    unknown = tuple(
        sorted(
            n
            for n in vars(module)
            if n.isupper() and not n.startswith("_") and n not in _MANIFEST_NAMES and n not in COMMAND_NAMES
        )
    )
    made = Manifest(**given, unknown=unknown)
    _manifests[id(module)] = (module, made)
    return made


# The built-in features (the owner, 2026-11-27): {id: its module}. Each is its own package in the one wheel.
# In the order their project types and rail areas are offered (Streamlit first, as when it alone came with
# every install).
BUILT_IN: dict[str, str] = {
    "streamlit": "swissarmybench_streamlit.extension",
    "accounting": "swissarmybench_accounting.extension",
    "powerapps": "swissarmybench_powerapps.extension",
    "git": "swissarmybench_git.extension",
    "powerbi": "swissarmybench_powerbi.extension",
    "copilot": "swissarmybench_copilot.extension",
}

# The base's own project type: a BI project (a notebook as its deliverable); every family shows (an empty
# list: all). A feature may add to it (its BASE_MODE_ADDS: Streamlit's canvas, offered in a BI project too).
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
    # label, icon, title}; the page runs its plug-in of that id (the front end), never naming it.
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


def built_in() -> list[ModuleType]:
    """The built-in features' modules, in their order (one that cannot be imported here is left out: the
    app starts anyway)."""
    return [m for i in BUILT_IN if (m := _package(i)) is not None]


def extension_on(extension: str) -> bool:
    """Is this one on: a built-in feature, or a folder in the library that loaded."""
    name = extension.lower()
    if name in BUILT_IN:
        return True
    found = folders().get(name)
    return found is not None and found.module is not None


def _package(name: str) -> ModuleType | None:
    if name not in BUILT_IN:
        return None
    try:
        return importlib.import_module(BUILT_IN[name])
    except Exception:  # a broken install: without it rather than no app
        return None


def load(extension: str) -> ModuleType | None:
    """Its module: a built-in feature's, else the library's folder of that id (None: not on)."""
    name = extension.lower()
    if name in BUILT_IN:
        return _package(name)
    found = folders().get(name)
    return found.module if found is not None else None


def enabled() -> list[ModuleType]:
    """Every feature that is on and imports: the built-in ones in their order, then the library's folders' in
    id order."""
    on = built_in()
    return [*on, *(f.module for i, f in folders().items() if f.module is not None and i not in BUILT_IN)]


# ===== folder extensions: the library's extensions/<id>/ (Plans/folder-extensions.plan.md) =====
#
# Found at start beside the built-in features (the folders are read once per process, again after
# forget_folders: New
# extension, Remove, Load again), each loaded as the package sab_ext_<id> (its folder that package's only
# path). One that fails is kept with its error (never stops the app), one whose REQUIRES are missing is not
# loaded until they are installed, and one with a built-in feature's id loses to it. Its contract.json (when
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
    shadowed: bool = False  # a built-in feature has this id: it wins
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
    if ident in BUILT_IN:
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
    made = raw.get("new_files")  # New file's types this project type adds (domain/new_files.py)
    mode["new_files"] = (
        [dict(t) for t in made if isinstance(t, dict)] if isinstance(made, list | tuple) else []
    )
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
        adds = manifest(module).BASE_MODE_ADDS
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
        raw = manifest(module).INLINE_COMPLETION
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
        for action in manifest(module).PAGE_ACTIONS:
            if isinstance(action, dict) and all(action.get(k) for k in ("page", "id", "label")):
                out.append({k: str(action.get(k) or "") for k in _ACTION_FIELDS})
    return out


def opens() -> dict[str, str]:
    """The files the on extensions open: each one's OPENS, {".suffix": a route}."""
    out: dict[str, str] = {}
    for module in enabled():
        raw = manifest(module).OPENS
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
        mode = _mode(manifest(module).MODE)
        if mode is not None and mode["type"] not in {m["type"] for m in out}:
            out.append(mode)
    providers = inline_completions(on)
    actions = page_actions(on)
    for mode in out:
        mode["inline_completion"] = [dict(p) for p in providers]
        mode["page_actions"] = [dict(a) for a in actions]
    return out


def requirements_of(project_type: str | None) -> list[str]:
    """What a project of this type needs in its own `.venv` beyond its requirements.txt: its extension's
    contract.json requirements; the base's type, those of each on extension whose canvas it offers (its
    BASE_MODE_ADDS' canvases: the Streamlit canvas in every BI project, so its widgets draw). A broken
    contract adds nothing."""
    on = enabled()
    out: list[str] = []
    for module in on:
        found = manifest(module)
        mode = found.MODE if isinstance(found.MODE, dict) else {}
        adds = found.BASE_MODE_ADDS if isinstance(found.BASE_MODE_ADDS, dict) else {}
        own = mode.get("type") == project_type
        lent = project_type in (None, BASE_MODE["type"]) and bool(adds.get("canvases"))
        if not (own or lent):
            continue
        try:
            said = contract(module)
        except Exception:  # a broken contract.json is said where it is read; nothing here
            said = None
        out += [str(r) for r in (said or {}).get("requirements") or []]
    return list(dict.fromkeys(out))


_AREA_FIELDS = ("area", "name", "icon", "mark", "panel")  # panel: only when an area names one


def areas() -> list[dict[str, Any]]:
    """The rail's areas the on extensions add (each one's RAIL: {area, name, icon, mark?}), as data."""
    out: list[dict[str, Any]] = []
    for module in enabled():
        for raw in manifest(module).RAIL:
            if (
                isinstance(raw, dict)
                and isinstance(raw.get("area"), str)
                and raw["area"] not in {a["area"] for a in out}
            ):
                said = {k: str(raw.get(k) or "") for k in _AREA_FIELDS if k != "panel"}
                out.append(said | ({"panel": str(raw["panel"])} if raw.get("panel") else {}))
    return out


def mode_of(project_type: str | None) -> dict[str, Any]:
    """A project type's mode; the base's for no project, or a type nothing here adds."""
    found = modes()
    return next((m for m in found if m["type"] == project_type), found[0])
