"""Node.js and npm, which run and install the Copilot Language Server, found and versioned the way the Power
Apps extension finds them (its domain/tools.py: the same install commands, the same missing-tool answer: the
base's missing-package shape with "python": "tool"). Node.js 20.8 or later (the language server's README).

Pure rules: the caller says which system it is and what a tool printed.
"""

from __future__ import annotations

import re
from typing import Any

from swissarmybench_copilot.domain.lsp import MINIMUM_NODE, PACKAGE, PINNED

SYSTEMS: tuple[str, ...] = ("windows", "macos", "linux")
NAMES = {"node": "Node.js", "npm": "npm"}
PURPOSE = {
    "node": "runs GitHub's Copilot Language Server",
    "npm": "installs GitHub's Copilot Language Server",
}
INSTALLS: dict[str, dict[str, str]] = {
    "node": {
        "windows": "winget install --id OpenJS.NodeJS.LTS -e",
        "macos": "brew install node",
        "linux": "sudo apt install nodejs npm",
    },
    "npm": {
        "windows": "winget install --id OpenJS.NodeJS.LTS -e",
        "macos": "brew install node",
        "linux": "sudo apt install npm",
    },
}
FEATURES = {"install": "Installing GitHub's Copilot Language Server", "run": "GitHub Copilot"}
NEEDED = {"install": ("node", "npm"), "run": ("node",)}
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def system_of(platform: str) -> str:
    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


def parse_version(output: str) -> str | None:
    found = _VERSION.search(output or "")
    return ".".join(p for p in found.groups() if p is not None) if found else None


def version_tuple(version: str | None) -> tuple[int, ...]:
    return tuple(int(p) for p in (version or "").split(".") if p.isdigit())


def tool_state(tool: str, path: str | None, version: str | None, system: str) -> dict[str, Any]:
    minimum = MINIMUM_NODE if tool == "node" else ()
    ok = path is not None and (not minimum or version_tuple(version) >= minimum)
    state: dict[str, Any] = {
        "id": tool,
        "name": NAMES[tool],
        "purpose": PURPOSE[tool],
        "found": path is not None,
        "version": version,
        "ok": ok,
        "install": INSTALLS[tool][system],
    }
    if path is not None and not ok:
        state["problem"] = f"{NAMES[tool]} {version or '(no version)'} is older than " + ".".join(
            str(n) for n in minimum
        )
    return state


def missing(action: str, states: dict[str, dict[str, Any]], system: str) -> dict[str, Any] | None:
    """The missing-package answer for the first tool `action` needs that is not there (or too old)."""
    for tool in NEEDED[action]:
        state = states.get(tool)
        if state is None or not state["ok"]:
            return {
                "missing": {
                    "feature": FEATURES[action],
                    "packages": [NAMES[tool]],
                    "python": "tool",
                    "command": INSTALLS[tool][system],
                    "tool": tool,
                }
            }
    return None


def install_argv(npm: str, prefix: str) -> list[str]:
    """The language server, pinned, into the state folder's copilot/ (no audit, no fund messages, no scripts
    of other packages run: --ignore-scripts; the server's own platform package comes as its optional one)."""
    return [
        npm,
        "install",
        "--prefix",
        prefix,
        "--no-audit",
        "--no-fund",
        "--ignore-scripts",
        "--save-exact",
        f"{PACKAGE}@{PINNED}",
    ]


SCRIPT = ("node_modules", "@github", "copilot-language-server", "dist", "language-server.js")
