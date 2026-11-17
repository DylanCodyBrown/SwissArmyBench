"""The tools a code app needs, found and versioned, and each one's install command on each system.

Microsoft's current tooling (docs/verified.md, 2026-11-17): code apps are built with the **Power Apps CLI**
(`pa`, the npm package `@microsoft/power-apps-cli`, which needs Node.js 22 or later), Node.js and npm; the
**Power Platform CLI** (`pac`, a .NET tool) is kept for what `pa` does not do: its environments list and
custom connectors (`pac connector create`). Deno runs the data notebook's TypeScript cells
(phase 2). A missing tool is said
one way everywhere (the base's missing-package shape: {"missing": {feature, packages, python, command}}),
here with "python": "tool" and the command this system installs it with: installed on the user's word only.

Pure rules: the caller says which system it is and what a tool printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SYSTEMS: tuple[str, ...] = ("windows", "macos", "linux")


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    purpose: str  # what it is for, in plain words
    version_args: tuple[str, ...]
    installs: dict[str, str]  # system -> the command that installs it
    minimum: tuple[int, ...] = ()
    phase: int = 1  # 2: needed only for phase 2's TypeScript cells
    needs: tuple[str, ...] = ()  # other tools its install command uses


TOOLS: dict[str, Tool] = {
    t.id: t
    for t in (
        Tool(
            "node",
            "Node.js",
            "runs the code app's dev server and the Power Apps CLI",
            ("--version",),
            {
                "windows": "winget install --id OpenJS.NodeJS.LTS -e",
                "macos": "brew install node",
                "linux": "sudo apt install nodejs npm",
            },
            minimum=(22,),
        ),
        Tool(
            "npm",
            "npm",
            "installs the code app's packages",
            ("--version",),
            {
                "windows": "winget install --id OpenJS.NodeJS.LTS -e",
                "macos": "brew install node",
                "linux": "sudo apt install npm",
            },
        ),
        Tool(
            "pa",
            "Power Apps CLI",
            "makes, runs, connects and publishes code apps",
            ("--version",),
            dict.fromkeys(SYSTEMS, "npm install --global @microsoft/power-apps-cli"),
            needs=("npm",),
        ),
        Tool(
            "pac",
            "Power Platform CLI",
            "lists environments and makes custom connectors",
            (),  # `pac` alone prints its name, then "Version: 1.30.3+g0f0e0b9"
            {
                "windows": "dotnet tool install --global Microsoft.PowerApps.CLI.Tool",
                "macos": "dotnet tool install --global Microsoft.PowerApps.CLI.Tool",
                "linux": "dotnet tool install --global Microsoft.PowerApps.CLI.Tool",
            },
            needs=("dotnet",),
        ),
        Tool(
            "dotnet",
            ".NET SDK",
            "installs the Power Platform CLI",
            ("--version",),
            {
                "windows": "winget install --id Microsoft.DotNet.SDK.8 -e",
                "macos": "brew install --cask dotnet-sdk",
                "linux": "sudo apt install dotnet-sdk-8.0",
            },
        ),
        Tool(
            "deno",
            "Deno",
            "runs the data notebook's TypeScript and SQL cells, and draws TSX cells",
            ("--version",),
            {
                "windows": "winget install --id DenoLand.Deno -e",
                "macos": "brew install deno",
                # Deno's installation page (2026-07-09) lists npm on every system; it runs without a shell.
                "linux": "npm install --global deno",
            },
            phase=2,
        ),
    )
}
# What each action needs, in the order it is checked.
NEEDED: dict[str, tuple[str, ...]] = {
    "auth": ("node", "pa"),
    "init": ("node", "npm", "pa"),
    "sources": ("node", "pa"),
    "connectors": ("node", "pa"),
    "run": ("node", "npm"),
    "push": ("node", "npm", "pa"),
    "environments": ("pac",),
    "custom_connector": ("pac",),
    "typescript": ("deno",),
}
FEATURES: dict[str, str] = {
    "auth": "Signing in to Power Platform",
    "init": "A new code app",
    "sources": "A code app's data sources",
    "connectors": "The environment's connectors",
    "run": "Run live",
    "push": "Push",
    "environments": "The environments list",
    "custom_connector": "A custom connector",
    "typescript": "TypeScript cells",
}

_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def system_of(platform: str) -> str:
    """`sys.platform` as one of SYSTEMS."""
    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


def parse_version(tool: str, output: str) -> str | None:
    """The version a tool printed ("v22.23.4", "deno 2.1.4 (stable...)", "Version: 1.30.3+g0f0e0b9")."""
    text = output or ""
    if tool == "pac":
        line = next((x for x in text.splitlines() if x.strip().lower().startswith("version")), "")
        text = line or text
    found = _VERSION.search(text)
    if not found:
        return None
    return ".".join(p for p in found.groups() if p is not None)


def version_tuple(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def tool_state(tool: str, path: str | None, version: str | None, system: str) -> dict[str, Any]:
    """One tool as the extension's page shows it: found or not, its version, whether it is new enough, and
    the command that installs it here."""
    spec = TOOLS[tool]
    ok = path is not None and (not spec.minimum or version_tuple(version) >= spec.minimum)
    state: dict[str, Any] = {
        "id": tool,
        "name": spec.name,
        "purpose": spec.purpose,
        "found": path is not None,
        "path": path,
        "version": version,
        "ok": ok,
        "phase": spec.phase,
        "install": spec.installs[system],
    }
    if path is not None and not ok:
        state["problem"] = f"{spec.name} {version or '(no version)'} is older than " + ".".join(
            str(n) for n in spec.minimum
        )
    return state


def missing(action: str, states: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The base's missing-package answer for the first tool `action` needs that is not there (or too old),
    else None. The command is this system's install command; nothing is installed without the user."""
    for tool in NEEDED.get(action, ()):
        state = states.get(tool)
        if state is None or not state["ok"]:
            spec = TOOLS[tool]
            return {
                "missing": {
                    "feature": FEATURES.get(action, action),
                    "packages": [spec.name],
                    "python": "tool",
                    "command": state["install"] if state else spec.installs["linux"],
                    "tool": tool,
                }
            }
    return None


def install_argv(tool: str, system: str) -> list[str] | None:
    """The install command as an argument list, where it can run without a shell or a password: winget,
    brew, npm and dotnet. A `sudo` or piped command is shown for the user to run themselves (None)."""
    command = TOOLS[tool].installs[system]
    if "sudo " in command or "|" in command:
        return None
    return command.split()
