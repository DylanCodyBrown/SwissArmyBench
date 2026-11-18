"""Extensions (Plans/editions.plan.md; the owner, 2026-11-17): the base and what plugs into it.

"Bi edition is the base install and powerapps, streamlit, and accounting are the extensions"; "add an
extension button to the rail to show what extensions are available to install and one click installs them."

The catalog is every extension that exists or is coming, each with a status:
    preinstalled  comes with every install (Streamlit: the installers and each update install its package);
               listed as installed while its package is here (Remove asks first), available once removed
    available  a package this version can install (from the GitHub release of this exact version)
    installed  a package found under the entry-point group `swissarmybench.extensions`
    coming     listed, not installable

An installed extension's entry point gives its description (`describe`): id, name, description, version,
what it adds. Install and Remove are the updater's machinery (server/updater.py): the app stops, uv installs
the base at this version with each kept extension's wheel (`--with`), and the app starts again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.updates import PACKAGE, REPOSITORY, UpdateError, UpdatePlan

GROUP: str = "swissarmybench.extensions"
# Extension ids to treat as installed, comma separated: for tests and the development environment only.
ENV: str = "SWISSARMYBENCH_EXTENSIONS"
STATUSES: tuple[str, ...] = ("preinstalled", "available", "installed", "coming")
MAX_ID: int = 40


@dataclass(frozen=True)
class Extension:
    """One catalog entry. `package`: its distribution's name (its wheel's, with underscores)."""

    id: str
    name: str
    description: str
    adds: tuple[str, ...] = ()
    status: str = "coming"  # preinstalled | available | coming (installed is found, never written here)
    package: str = ""
    project_type: str = ""  # the project type it adds (the Project Explorer: "needs the <name> extension")
    # Its agent commands' names start with one of these: called while it is off, a plain answer names it.
    tools: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "adds": list(self.adds),
            "status": self.status,
            "package": self.package,
        }


# The base's own catalog (the plan's one line each).
CATALOG: tuple[Extension, ...] = (
    Extension(
        "streamlit",
        "Streamlit",
        "Build Streamlit apps from your notebooks' cells.",
        ("The Apps area", "The Streamlit canvas", "App mode", "Streamlit, Components, Controllers starters"),
        "preinstalled",
        "swissarmybench-streamlit",
        project_type="streamlit",
        tools=("streamlit_", "workbench_canvas", "workbench_live_", "workbench_new_app"),
    ),
    Extension(
        "accounting",
        "Accounting",
        "An Excel workbook built by a repeatable Python automation; cession statements and invoices.",
        ("The Accounting project", "The Excel canvas", "Statements and invoices from templates"),
        "available",
        "swissarmybench-accounting",
        project_type="accounting",
        tools=("workbook_", "template_", "statements_"),
    ),
    Extension(
        "powerapps",
        "Power Apps",
        "Power Apps code apps: a code app project, its data sources and connectors, Run live and push.",
        ("The code app project", "Dataverse and connectors", "Run live and push", "Custom connectors"),
        "available",
        "swissarmybench-powerapps",
        project_type="codeapp",
        tools=("powerapps_",),
    ),
    Extension(
        "copilot",
        "GitHub Copilot",
        "GitHub Copilot's code completion in the Workbench's notebook cells and scripts.",
        ("Ghost text in cells and scripts", "Sign in with GitHub", "Off for a private project"),
        "available",
        "swissarmybench-copilot",
        tools=("copilot_",),
    ),
)


def owner_of(command: str, catalog: tuple[Extension, ...] = CATALOG) -> Extension | None:
    """The catalog's extension an agent command belongs to (by its tools' prefixes), or None."""
    return next((e for e in catalog if any(command.startswith(p) for p in e.tools)), None)


class ExtensionError(ValueError):
    """An extension that is not one, or cannot be installed or removed from here."""


@dataclass(frozen=True)
class Found:
    """An installed extension, as its entry point described it."""

    id: str
    version: str = ""
    name: str = ""
    description: str = ""
    adds: tuple[str, ...] = field(default_factory=tuple)
    package: str = ""


def check_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtensionError('Send {"id": "<an extension\'s id>"}.')
    text = value.strip().lower()
    if len(text) > MAX_ID or not all(c.isalnum() or c in "-_" for c in text):
        raise ExtensionError(f"{value!r} is not an extension's id.")
    return text


def describe(entry_name: str, value: Any, dist: str = "", dist_version: str = "") -> Found | None:
    """What an entry point gave (a dict, or a callable giving one) read loosely; None: not an extension."""
    if callable(value):
        value = value()
    if not isinstance(value, dict):
        value = {}
    try:
        ident = check_id(value.get("id") or entry_name)
    except ExtensionError:
        return None
    adds = value.get("adds")
    return Found(
        id=ident,
        version=str(value.get("version") or dist_version or ""),
        name=str(value.get("name") or ""),
        description=str(value.get("description") or ""),
        adds=tuple(str(a) for a in adds) if isinstance(adds, (list, tuple)) else (),
        package=str(value.get("package") or dist or ""),
    )


def from_env(text: str | None) -> tuple[str, ...]:
    """SWISSARMYBENCH_EXTENSIONS's ids (tests and development only)."""
    found: list[str] = []
    for part in (text or "").split(","):
        if part.strip().startswith("-"):
            continue  # "-id" turns one off (turned_off)
        try:
            ident = check_id(part)
        except ExtensionError:
            continue
        if ident not in found:
            found.append(ident)
    return tuple(found)


def turned_off(text: str | None) -> set[str]:
    """SWISSARMYBENCH_EXTENSIONS's "-id" words: extensions treated as not installed, even one that is."""
    return {p.strip()[1:].lower() for p in (text or "").split(",") if p.strip().startswith("-")}


def listed(catalog: tuple[Extension, ...], found: dict[str, Found], current: str) -> list[dict[str, Any]]:
    """Every extension with its status and version: the catalog's, then any installed one it does not list.
    A preinstalled one (the installers put it in) is installed while its package is found and available once
    removed, marked `preinstalled` either way; any other found is installed."""
    out: list[dict[str, Any]] = []
    for ext in catalog:
        said = ext.to_json()
        said["preinstalled"] = ext.status == "preinstalled"
        here = found.get(ext.id)
        if here is not None:
            said["status"] = "installed"
            said["version"] = here.version or current
        else:
            if ext.status == "preinstalled":
                said["status"] = "available"
            said["version"] = current if ext.status in ("preinstalled", "available") else None
        out.append(said)
    known = {e.id for e in catalog}
    for ident, here in found.items():
        if ident in known:
            continue
        out.append(
            {
                "id": ident,
                "name": here.name or ident,
                "description": here.description,
                "adds": list(here.adds),
                "status": "installed",
                "package": here.package,
                "version": here.version or None,
            }
        )
    return out


def to_bring_back(
    catalog: tuple[Extension, ...], found: dict[str, Found], record: Any, version: str
) -> list[Extension]:
    """The preinstalled extensions an install lacks that the user never removed and that were not tried at
    this version already: an update from a version that had them built in (Streamlit before 0.0.18) brings
    them back once, at its first start. `record` is extensions.json's {"removed": [ids], "tried": {id: v}}."""
    said = record if isinstance(record, dict) else {}
    removed = {str(i) for i in said.get("removed") or [] if isinstance(i, str)}
    tried: dict[str, Any] = said["tried"] if isinstance(said.get("tried"), dict) else {}
    return [
        e
        for e in catalog
        if e.status == "preinstalled"
        and e.package
        and e.id not in found
        and e.id not in removed
        and tried.get(e.id) != version
    ]


def recorded(
    record: Any,
    *,
    removed: str | None = None,
    installed: str | None = None,
    tried: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """extensions.json after a change: an id removed by the user (kept out of every bring-back), installed
    again (no longer removed), or tried at a version."""
    said = dict(record) if isinstance(record, dict) else {}
    gone = [str(i) for i in said.get("removed") or [] if isinstance(i, str)]
    if removed and removed not in gone:
        gone.append(removed)
    if installed:
        gone = [i for i in gone if i != installed]
    attempts = dict(said["tried"]) if isinstance(said.get("tried"), dict) else {}
    if tried:
        attempts[tried[0]] = tried[1]
    return {"removed": sorted(gone), "tried": dict(sorted(attempts.items()))}


def wheel_name(package: str, version: str) -> str:
    return f"{package.replace('-', '_')}-{version}-py3-none-any.whl"


def wheel_url(package: str, version: str) -> str:
    """The extension's wheel on the GitHub release of this exact version (PyPI's trusted publishing covers
    only `swissarmybench`; a project of its own needs the owner to add a publisher there first)."""
    return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{wheel_name(package, version)}"


def kept_wheels(catalog: tuple[Extension, ...], installed: list[str], version: str) -> list[str]:
    """The `--with` wheels of the extensions installed as packages (a preinstalled one too) at `version`."""
    packages = {e.id: e.package for e in catalog}
    return [wheel_url(packages[i], version) for i in installed if packages.get(i)]


def install_command(uv: str, version: str, python: str, wheels: list[str]) -> list[str]:
    """`uv tool install --force --python X "swissarmybench[server]==V" --with <wheel>...`."""
    command = [uv, "tool", "install", "--force", "--refresh-package", PACKAGE, "--python", python]
    command.append(f"{PACKAGE}[server]=={version}")  # --refresh-package: the index read again for it
    for wheel in wheels:
        command += ["--with", wheel]
    return command


def plan_change(
    *,
    current: str,
    uv: str,
    tool_python: str,
    python_version: str,
    wheels: list[str],
    before: list[str],
    wait_pids: list[int],
    info_file: str,
    note_file: str,
    environ: dict[str, str] | None = None,
    stop_in: str = "",
) -> UpdatePlan:
    """Install or Remove: the base at this same version with `wheels`; on a failure, `before` again."""
    if not current:
        raise UpdateError("This version is not known.")
    probe = "import importlib.metadata as m; print(m.version('swissarmybench'))"
    return UpdatePlan(
        version=current,
        current=current,
        wait_pids=tuple(pid for pid in wait_pids if pid > 0),
        install=tuple(install_command(uv, current, python_version, wheels)),
        restore=tuple(install_command(uv, current, python_version, before)),
        installed_version=(tool_python, "-I", "-c", probe),
        start=(tool_python, "-m", f"{PACKAGE}.server", "start"),
        info_file=info_file,
        note_file=note_file,
        environ=dict(environ or {}),
        stop_in=stop_in,
    )


def development_words(ext: Extension) -> str:
    """What a development checkout runs instead of Install (it is not a uv tool)."""
    return (
        f"This copy is a development checkout, not the installed app: install {ext.package} into its "
        f"environment yourself (uv pip install -e extensions/{ext.id}), or run "
        f"SWISSARMYBENCH_EXTENSIONS={ext.id} to treat it as installed."
    )


def change_question(action: str, ext_name: str) -> str:
    return f"The app stops, {action} {ext_name} and starts again. Nothing is saved for you."


def off_project_types(catalog: tuple[Extension, ...], modes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The project types of the catalog's extensions that are not on here (a project of one says "needs the
    <Name> extension", with Install): {"project_type", "id", "name"}."""
    on = {str(m.get("type")) for m in modes}
    return [
        {"project_type": e.project_type, "id": e.id, "name": e.name}
        for e in catalog
        if e.project_type and e.project_type not in on
    ]
