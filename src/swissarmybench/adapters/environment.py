"""The Environment's files (services/environment.py): the project's Python and what it has installed,
requirements.txt, and the package index's newest versions.

  python_of      the project's own Python (its `.venv` at its top), else this app's own
  installed      a Python's libraries by name and version, read from its site-packages' metadata: nothing runs
  requires       each of them with what it says it needs (a notebook's older environment: what was chosen)
  requirements   the project's requirements.txt, read and written atomically, only when its bytes change
  latest         each library's newest version on the index: one GET a library, only when the Libraries
                 tab opens or the user asks (never in the background), carrying only the library's name.
                 SWISSARMYBENCH_PACKAGE_INDEX names another index (a team's mirror; a stand-in in tests).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path
from urllib.parse import quote

from swissarmybench.adapters.atomic_files import write_atomic

INDEX = "https://pypi.org/pypi"
INDEX_SECONDS: float = 8.0
MAX_ASKED: int = 80
REQUIREMENTS = "requirements.txt"
VENV = ".venv"


def venv_python(folder: str | Path) -> Path:
    """Where a project's own Python is (whether or not it is there yet)."""
    return Path(folder) / VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def python_of(folder: str | None) -> tuple[str, bool]:
    """The Python the project's code runs in, and whether it is the project's own (its .venv)."""
    if folder:
        python = venv_python(folder)
        if python.is_file():
            return str(python), True
    return sys.executable, False


def version_of(python: str) -> str:
    """A Python's version without running it: its environment's pyvenv.cfg, else this app's own."""
    config = Path(python).parent.parent / "pyvenv.cfg"
    try:
        for line in config.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in ("version", "version_info"):
                return ".".join(value.strip().split(".")[:2])
    except OSError:
        pass
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _site_packages(python: str) -> list[Path]:
    root = Path(python).parent.parent
    return [*root.glob("lib/python*/site-packages"), *root.glob("Lib/site-packages")]


def _is_app_python(python: str) -> bool:
    """Whether `python` is this app's own. By its place, never by what its link points to: a project's
    `.venv` made from the app's Python links to the same program, and is still another environment (found
    with a real `.venv`, 2026-11-22: its libraries were listed as the app's own)."""
    return os.path.normcase(os.path.abspath(python)) == os.path.normcase(os.path.abspath(sys.executable))


def installed(python: str) -> dict[str, str]:
    """A Python's libraries: name -> version. This app's own from its import system; another's from the
    metadata folders in its site-packages."""
    if _is_app_python(python):
        found = metadata.distributions()
    else:
        found = metadata.distributions(path=[str(p) for p in _site_packages(python)])
    out: dict[str, str] = {}
    for distribution in found:
        name = distribution.metadata.get("Name") if distribution.metadata else None
        if name:
            out.setdefault(str(name), str(distribution.version))
    return out


def requires(python: str) -> dict[str, list[str]]:
    """A Python's libraries, each with what it says it needs (its metadata's Requires-Dist names, an extra's
    left out): how the libraries someone chose are told from the ones they brought (domain/project_python.py).
    Read from the metadata folders in its site-packages: nothing runs."""
    if _is_app_python(python):
        found = metadata.distributions()
    else:
        found = metadata.distributions(path=[str(p) for p in _site_packages(python)])
    out: dict[str, list[str]] = {}
    for distribution in found:
        name = distribution.metadata.get("Name") if distribution.metadata else None
        if name:
            needs = [r for r in (distribution.requires or []) if "extra ==" not in r.replace("'", '"')]
            out.setdefault(str(name), needs)
    return out


def read_requirements(folder: str) -> str:
    try:
        return (Path(folder) / REQUIREMENTS).read_text(encoding="utf-8")
    except OSError:
        return ""


def write_requirements(folder: str, text: str) -> bool:
    """True when the file's bytes changed."""
    path = Path(folder) / REQUIREMENTS
    if read_requirements(folder) == text and path.exists():
        return False
    write_atomic(path, text.encode("utf-8"))
    return True


def _newest(index: str, name: str) -> str | None:
    url = f"{index.rstrip('/')}/{quote(name, safe='')}/json"
    if not url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        return None
    # The address is checked above: https, or this computer.
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=INDEX_SECONDS) as response:  # noqa: S310
            document = json.loads(response.read(2_000_000))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    version = document.get("info", {}).get("version") if isinstance(document, dict) else None
    return version if isinstance(version, str) else None


def latest(names: list[str]) -> dict[str, str]:
    """Each library's newest version on the index, by the name asked; one that cannot be read is left out."""
    index = os.environ.get("SWISSARMYBENCH_PACKAGE_INDEX") or INDEX
    asked = names[:MAX_ASKED]
    if not asked:
        return {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = list(pool.map(lambda name: _newest(index, name), asked))
    return {name: version for name, version in zip(asked, found, strict=True) if version}


def remove_structure_file(path: str) -> None:
    """A structure's saved file deleted (the Environment's Remove on one): only a file, only in a
    `structures` folder."""
    target = Path(path)
    if target.parent.name != "structures" or not target.is_file():
        raise FileNotFoundError(f"{path} is not a structure's file.")
    target.unlink()
