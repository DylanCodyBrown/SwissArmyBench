"""Extensions: optional packages that plug into this one app (Plans/editions.plan.md, the owner 2026-11-17).

An extension is a package that registers itself under the entry-point group `swissarmybench.extensions`
(its entry point names a module: `accounting = "swissarmybench_accounting.extension"`). The base finds the
installed ones here; nothing else in the shared code names one.

  extension_on(id)  the one capability check: installed (its entry point), or named in
                    SWISSARMYBENCH_EXTENSIONS (a comma list: a checkout or a test turns one on without
                    installing it; "-accounting" turns an installed one off)
  load(id)          its module (None: off, or it cannot be imported)
  enabled()         the on ones' modules, in id order
  modes()           every project type's mode, as data: the base's (BI) and each on extension's MODE
  mode_of(type)     a project type's mode (an unknown or missing type: the base's)

A mode is the working set a project type sets (Plans/editions.plan.md, "Project modes"): the canvas kinds,
the blade and function families shown first, the languages, the extra cell kinds, the agent's tool group
and the export. It is declared, never coded: shared code reads these fields, and never asks which type it
is. Until the manifest boundary exists the extension's MODE lives in its extension module (the entry point).

Standard library only (the MCP server reads it to order its tools).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
from types import ModuleType
from typing import Any

GROUP = "swissarmybench.extensions"
VARIABLE = "SWISSARMYBENCH_EXTENSIONS"

# The base's own project type: a BI project (a notebook as its deliverable). Streamlit is still built in
# (the coming release keeps it), so its canvas is the base's; every family shows (an empty list: all).
BASE_MODE: dict[str, Any] = {
    "type": "bi",
    "name": "BI",
    "deliverable": "a notebook",
    "canvases": ["streamlit"],
    "families": [],
    "languages": ["python"],
    "cell_kinds": [],
    "tools": [],
    "export": ["notebook"],
    # The cell kinds this mode runs somewhere else than the Python kernel: {kind: {name, language, run
    # (the route a run is posted to), preview (a route that draws it, or "")}}; a base kind too (a
    # DuckDB SQL cell run in the mode's kernel). The page reads them as data, never which mode it is.
    "cell_routes": {},
}
_ROUTE_FIELDS = ("name", "language", "run", "preview")
_MODE_FIELDS = ("canvases", "families", "languages", "cell_kinds", "tools", "export")


def _said(environ: dict[str, str] | None = None) -> tuple[set[str], set[str]]:
    """The variable's ids turned on, and the ones turned off ("-id")."""
    raw = (os.environ if environ is None else environ).get(VARIABLE, "")
    words = [w.strip().lower() for w in raw.split(",") if w.strip()]
    return {w for w in words if not w.startswith("-")}, {w[1:] for w in words if w.startswith("-")}


def installed() -> dict[str, str]:
    """The installed extensions' entry points: {id: "module"}."""
    try:
        found = importlib.metadata.entry_points(group=GROUP)
    except Exception:  # a broken install never stops the app
        return {}
    return {ep.name.lower(): ep.value for ep in found}


def extension_on(extension: str, environ: dict[str, str] | None = None) -> bool:
    """Is this extension on: installed or named in SWISSARMYBENCH_EXTENSIONS, and not turned off there."""
    on, off = _said(environ)
    name = extension.lower()
    return name not in off and (name in on or name in installed())


def load(extension: str) -> ModuleType | None:
    """The extension's module when it is on (its entry point's, else `swissarmybench_<id>.extension`)."""
    if not extension_on(extension):
        return None
    target = installed().get(extension.lower(), f"swissarmybench_{extension.lower()}.extension")
    try:
        return importlib.import_module(target.split(":")[0])
    except Exception:  # named but not importable here: off
        return None


def enabled() -> list[ModuleType]:
    """Every extension that is on and imports, in id order."""
    on, _ = _said()
    ids = sorted(set(installed()) | on)
    return [m for m in (load(i) for i in ids) if m is not None]


def _mode(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        return None
    mode = dict(BASE_MODE) | {k: v for k, v in raw.items() if k in BASE_MODE}
    for key in _MODE_FIELDS:
        value = mode.get(key)
        mode[key] = [str(v) for v in value] if isinstance(value, list | tuple) else []
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


def modes() -> list[dict[str, Any]]:
    """Every project type's mode: the base's first, then each on extension's (its MODE)."""
    out = [dict(BASE_MODE)]
    for module in enabled():
        mode = _mode(getattr(module, "MODE", None))
        if mode is not None and mode["type"] not in {m["type"] for m in out}:
            out.append(mode)
    return out


def mode_of(project_type: str | None) -> dict[str, Any]:
    """A project type's mode; the base's for no project, or a type whose extension is not on."""
    return next((m for m in modes() if m["type"] == project_type), dict(BASE_MODE))
