"""Every extension package keeps the layers the base keeps (REFACTOR.md; the craft review of 2026-11-22: four
of the six had no such test and two had a breach): its domain does no I/O and knows no service, its services
touch nothing themselves and import no adapter or door, its adapters do not know its doors, nothing is deeper
than a folder, and the base imports none of it.

Five packages are laid out in folders (domain/, services/, adapters/, server/). Accounting is flat (one file a
layer, the owner's layout for a small package), so its files are declared here by layer; a new file there
must be added to FLAT or the test refuses it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_architecture import DOMAIN_FORBIDDEN, SERVICES_FORBIDDEN, _imports

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "src" / "swissarmybench"
EXTENSIONS = ("accounting", "copilot", "git", "powerapps", "powerbi", "streamlit")
LAYERS = ("domain", "services", "adapters", "server")
# The package's root: its manifest, composition root and commands (they may import any layer).
ROOT_FILES = {"__init__.py", "extension.py", "commands.py"}
# A flat package's files by layer.
FLAT: dict[str, dict[str, tuple[str, ...]]] = {
    "accounting": {
        "domain": ("design.py", "templates.py", "exporter.py"),
        "services": ("service.py",),
        "adapters": ("files.py",),
        "server": ("routes.py",),
    },
}
# What a layer may not import, as (package layer) names: `swissarmybench*.<layer>`.
OUTWARD: dict[str, tuple[str, ...]] = {
    "domain": ("services", "adapters", "server", "cli", "mcp", "client", "bootstrap", "extensions"),
    "services": ("adapters", "server", "cli", "mcp"),
    "adapters": ("server", "cli", "mcp"),
    "server": (),
}
STDLIB_FORBIDDEN: dict[str, set[str]] = {
    "domain": DOMAIN_FORBIDDEN,
    "services": SERVICES_FORBIDDEN,
    "adapters": set(),
    "server": set(),
}


def package(extension: str) -> Path:
    return ROOT / "extensions" / extension / "src" / f"swissarmybench_{extension}"


def files_of(extension: str, layer: str) -> list[Path]:
    """The layer's files: its folder's, or a flat package's declared ones."""
    home = package(extension)
    if extension in FLAT:
        return [home / name for name in FLAT[extension][layer]]
    return sorted((home / layer).glob("*.py"))


def layer_of(extension: str, module: str) -> str:
    """The layer a dotted module of the base or of an extension belongs to ("" for a root module or one
    that is neither): swissarmybench.server.http is server; a flat package's module by its declaration."""
    parts = module.split(".")
    if not parts[0].startswith("swissarmybench") or len(parts) < 2:
        return ""
    owner = parts[0].removeprefix("swissarmybench").removeprefix("_")
    if owner in FLAT:
        return next((layer for layer, names in FLAT[owner].items() if f"{parts[1]}.py" in names), "")
    return parts[1]


def breaches(extension: str, layer: str) -> list[str]:
    found: list[str] = []
    for path in files_of(extension, layer):
        for module in sorted(_imports(path)):
            if module.split(".")[0] in STDLIB_FORBIDDEN[layer]:
                found.append(f"{path.name} imports {module}")
            elif layer_of(extension, module) in OUTWARD[layer]:
                found.append(f"{path.name} imports {module}")
    return found


@pytest.mark.parametrize("extension", EXTENSIONS)
def test_every_extension_is_listed_and_no_deeper_than_a_folder(extension: str) -> None:
    home = package(extension)
    assert home.is_dir()
    code = [p for p in home.rglob("*.py") if "widgets" not in p.parts and "starters" not in p.parts]
    assert all(len(p.relative_to(home).parts) <= 2 for p in code)
    top = {p.name for p in home.glob("*.py")}
    if extension in FLAT:
        declared = {name for names in FLAT[extension].values() for name in names}
        assert top == declared | ROOT_FILES, "a flat package's every file is declared by its layer (FLAT)"
        assert not [d.name for d in home.iterdir() if d.is_dir() and d.name in LAYERS]
    else:
        assert top <= ROOT_FILES, sorted(top - ROOT_FILES)
        assert all((home / layer).is_dir() for layer in LAYERS)


def test_the_list_is_every_extension_package() -> None:
    found = sorted(p.parent.parent.name for p in (ROOT / "extensions").glob("*/src/swissarmybench_*"))
    assert found == sorted(EXTENSIONS)


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("extension", EXTENSIONS)
def test_the_package_keeps_the_layers(extension: str, layer: str) -> None:
    assert breaches(extension, layer) == []


@pytest.mark.parametrize("extension", EXTENSIONS)
def test_the_base_knows_none_of_it(extension: str) -> None:
    name = f"swissarmybench_{extension}"
    assert not [
        str(p.relative_to(BASE)) for p in BASE.rglob("*.py") if any(m.startswith(name) for m in _imports(p))
    ]


def test_an_extension_imports_no_other_extension() -> None:
    found = []
    for extension in EXTENSIONS:
        others = tuple(f"swissarmybench_{other}" for other in EXTENSIONS if other != extension)
        for path in package(extension).rglob("*.py"):
            found += [f"{extension}/{path.name} imports {m}" for m in _imports(path) if m.startswith(others)]
    assert found == []
