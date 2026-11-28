"""The GitHub Copilot extension as the base reads it (swissarmybench/extensions.py): its description, the
inline completion it offers the editors and its panel as data, its door, its agent commands and its Session
page words. This is the extension's composition root: it builds its adapters and hands them to its service.

The editors never name it: the base's mode carries INLINE_COMPLETION (the routes an editor calls and the
provider's name), and the Extensions page and Settings draw PANEL's answer (lines, switches, actions, a code).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from swissarmybench_copilot import __version__

if TYPE_CHECKING:
    from swissarmybench.services.hooks import Seams

ID = "copilot"
NAME = "GitHub Copilot"
VERSION = __version__
DESCRIPTION = "GitHub Copilot's code completion in the Workbench's notebook cells and scripts."
ADDS = [
    "Ghost text as you type in notebook cells and scripts (Tab accepts, Esc dismisses, Alt+] / Alt+[ cycle)",
    "Sign in with GitHub's device flow (a GitHub Copilot plan; Copilot Free counts)",
    "An On switch; nothing is sent for a project marked private",
    "Only the document being edited is sent: never outputs, rows or variables' values; telemetry off",
]
AREAS = (("copilot", "GitHub Copilot: its status, the On switch, the language server's install"),)
# The editors' inline completion (lazy/codeEditor.ts asks these routes when a mode declares them).
INLINE_COMPLETION: dict[str, Any] = {
    "id": ID,
    "name": NAME,
    "languages": ["python", "sql"],
    "complete": "/copilot/complete",
    "cancel": "/copilot/cancel",
    "event": "/copilot/event",
    "status": "/copilot/inline",
    "toggle": "/copilot/toggle",
}
# The panel the Extensions card and Settings draw (GET it, POST a click).
PANEL = "/copilot/panel"
SECRET_PATHS: tuple[str, ...] = ()


def _area(what: str) -> tuple[str, str, dict[str, Any]]:
    return what, "settings", {"place": "area", "area": "extensions"}


# The Session page's words for each audit entry (never a token, a code or a document's text).
SESSION_RULES: dict[str, Any] = {
    "copilot_install": lambda d, x: _area(
        f"Installed GitHub's Copilot Language Server {x.get('version')}"
        + ("" if x.get("ok") else " (failed)")
    ),
    "copilot_toggle": lambda d, x: _area(f"Turned GitHub Copilot {'on' if x.get('on') else 'off'}"),
    "copilot_sign_in": lambda d, x: _area("Started signing in to GitHub Copilot"),
    "copilot_signed_in": lambda d, x: _area(f"GitHub Copilot sign-in: {x.get('state')}"),
    "copilot_sign_out": lambda d, x: _area("Signed out of GitHub Copilot"),
}


def describe() -> dict[str, Any]:
    return {"id": ID, "name": NAME, "description": DESCRIPTION, "version": VERSION, "adds": ADDS}


def private_project(seams: Seams) -> bool:
    """Is the open project marked private (.sab/project.json `private: true`)? (the base's seam)"""
    return bool(seams.project_private())


def routes(seams: Seams) -> list[Any]:
    from swissarmybench import __version__ as app_version
    from swissarmybench.adapters.state_files import JsonFile
    from swissarmybench_copilot.adapters.language_server import Machine
    from swissarmybench_copilot.server import routes as door
    from swissarmybench_copilot.services.copilot import Copilot

    state_dir = Path(seams.settings.state_dir)
    service = Copilot(
        machine=Machine(state_dir / "copilot"),
        record=JsonFile(state_dir / "copilot.json"),
        approvals=seams.approvals,
        audit=seams.ws.audit,
        live=seams.ws.live,
        private=lambda: private_project(seams),
        app_version=app_version,
        plugin_version=VERSION,
        process_id=os.getpid(),
    )
    seams.extension[ID] = service  # its own place on the record: its stop, and tests
    return door.routes(service)


async def stop(seams: Seams) -> None:
    service = seams.extension.get(ID)
    if service is not None:
        await service.stop()


def commands() -> dict[str, Any]:
    from swissarmybench_copilot.commands import COMMANDS

    return COMMANDS
