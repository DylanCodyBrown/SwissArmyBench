"""Extensions (Plans/editions.plan.md; the owner, 2026-11-17): the base and what plugs into it.

"Bi edition is the base install and powerapps, streamlit, and accounting are the extensions"; "add an
extension button to the rail to show what extensions are available to install and one click installs them."

The catalog is every extension that exists or is coming, each with a status:
    preinstalled  comes with every install (Streamlit, until it moves into a package of its own)
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
        ("The Apps area", "The Streamlit canvas", "App mode", "Streamlit and Components starters"),
        "preinstalled",
        "swissarmybench-streamlit",
    ),
    Extension(
        "accounting",
        "Accounting",
        "An Excel workbook built by a repeatable Python automation; cession statements and invoices.",
        ("The Accounting project", "The Excel canvas", "Statements and invoices from templates"),
        "available",
        "swissarmybench-accounting",
    ),
    Extension(
        "powerapps",
        "Power Apps",
        "Power Apps code apps: a code app project, its data sources and connectors, Run live and push.",
        ("The code app project", "Dataverse and connectors", "Run live and push", "Custom connectors"),
        "available",
        "swissarmybench-powerapps",
    ),
)


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
        try:
            ident = check_id(part)
        except ExtensionError:
            continue
        if ident not in found:
            found.append(ident)
    return tuple(found)


def listed(catalog: tuple[Extension, ...], found: dict[str, Found], current: str) -> list[dict[str, Any]]:
    """Every extension with its status and version: the catalog's, then any installed one it does not list.
    A preinstalled extension stays preinstalled (it comes with the app); any other found is installed."""
    out: list[dict[str, Any]] = []
    for ext in catalog:
        said = ext.to_json()
        here = found.get(ext.id)
        if here is not None and ext.status != "preinstalled":
            said["status"] = "installed"
            said["version"] = here.version or current
        else:
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


def wheel_name(package: str, version: str) -> str:
    return f"{package.replace('-', '_')}-{version}-py3-none-any.whl"


def wheel_url(package: str, version: str) -> str:
    """The extension's wheel on the GitHub release of this exact version (PyPI's trusted publishing covers
    only `swissarmybench`; a project of its own needs the owner to add a publisher there first)."""
    return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{wheel_name(package, version)}"


def kept_wheels(catalog: tuple[Extension, ...], installed: list[str], version: str) -> list[str]:
    """The `--with` wheels of the extensions installed as packages (never a preinstalled one) at `version`."""
    packages = {e.id: e.package for e in catalog}
    return [wheel_url(packages[i], version) for i in installed if packages.get(i)]


def install_command(uv: str, version: str, python: str, wheels: list[str]) -> list[str]:
    """`uv tool install --force --python X "swissarmybench[server]==V" --with <wheel>...`."""
    command = [uv, "tool", "install", "--force", "--python", python, f"{PACKAGE}[server]=={version}"]
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
        f"environment yourself (uv pip install -e extensions/{ext.id}), or run SWISSARMYBENCH_EXTENSIONS={ext.id} "
        "to treat it as installed."
    )


def change_question(action: str, ext_name: str) -> str:
    return f"The app stops, {action} {ext_name} and starts again. Nothing is saved for you."
