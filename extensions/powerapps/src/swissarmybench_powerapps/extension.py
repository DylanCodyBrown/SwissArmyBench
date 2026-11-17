"""The Power Apps extension as the base reads it (swissarmybench/extensions.py): its description and mode as
data, its door, its agent commands, its starters and its Session page words. This is the extension's
composition root: it builds its adapters and hands them to its service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swissarmybench_powerapps import __version__

ID = "powerapps"
NAME = "Power Apps"
VERSION = __version__
DESCRIPTION = "Power Apps code apps: React and TypeScript apps that run in Power Platform."
ADDS = [
    "Sign in to Power Platform and pick an environment",
    "New code app from Microsoft's template, or open one",
    "Dataverse tables and connectors as the app's data sources",
    "The environment's connectors, each one's operations, inputs and outputs",
    "Run live in a pane, and Push a new version",
    "Custom connectors from an API's OpenAPI document",
]
PROJECT_TYPE = "codeapp"
# The front-end plug-in it names (in the shared web/: codeAppPage.ts, the rail's Code App page).
FRONT_END = ["codeapp"]
# Its commands' area (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (("powerapps", "Power Apps: code apps (pa and pac), sources, connectors, Run live, Push"),)
# The code app mode (Plans/editions.plan.md, "Project modes"), as DATA: TypeScript and React; the
# component previews' canvas and the TypeScript and TSX cells are declared now and built in phase 2 (a
# kind the front end cannot draw yet is offered as "Coming"); the agent's tool group; Push as the export.
MODE: dict[str, Any] = {
    "type": PROJECT_TYPE,
    "name": "Code app",
    "deliverable": "a Power Apps code app",
    "canvases": ["components"],
    "families": ["TypeScript", "React", "Connectors"],
    "languages": ["typescript", "tsx"],
    "cell_kinds": ["typescript", "tsx"],
    "tools": ["powerapps_"],
    "export": ["push"],
    # The Project Explorer's words for beginners.
    "title": "Power Apps code app",
    "for_whom": "For developers building a business app their organisation runs in Power Apps.",
    "explain": (
        "Write the app in TypeScript and React, with Dataverse and connectors as its data. Run it live here, "
        "then push it to your environment. You get a code app's folder with power.config.json."
    ),
    "example": "Example: an expense approval app for your team.",
}

STARTERS = str(Path(__file__).resolve().parent / "starters")
SECRET_PATHS = ("/powerapps/live/",)


def _area(what: str) -> tuple[str, str, dict[str, Any]]:
    return what, "codeapp", {"place": "area", "area": "codeapp"}


def _name(value: Any) -> str:
    return str(value or "")[:120]


# The Session page's words for each audit entry (names and the commands' words only, never a value).
SESSION_RULES: dict[str, Any] = {
    "powerapps_run": lambda d, x: _area(
        f"Ran {_name(x.get('command'))} ({'done' if x.get('ok') else 'failed'})"
    ),
    "powerapps_new": lambda d, x: _area(f"Made the code app {_name(x.get('app'))}"),
    "powerapps_open": lambda d, x: _area(f"Opened the code app {_name(x.get('app'))}"),
    "powerapps_add_source": lambda d, x: _area(f"Added the data source {_name(x.get('source'))}"),
    "powerapps_remove_source": lambda d, x: _area(f"Removed the data source {_name(x.get('source'))}"),
    "powerapps_save_file": lambda d, x: _area(f"Saved {_name(x.get('file'))}"),
    "powerapps_run_live": lambda d, x: _area(f"Ran {_name(x.get('app')) or 'the code app'} live"),
    "powerapps_stop_live": lambda d, x: _area("Stopped Run live"),
    "powerapps_push": lambda d, x: _area(f"Pushed {_name(x.get('app'))}"),
    "powerapps_custom_connector": lambda d, x: _area(
        f"{'Updated' if x.get('update') else 'Made'} a custom connector from {_name(x.get('api'))}"
    ),
}


def routes(services: Any) -> list[Any]:
    """Its routes, its service built from the base's (the audit log, the live updates, the agent's
    approvals, the library's APIs, the open project) and its own adapters."""
    from swissarmybench_powerapps.adapters import environment_api, files, runner
    from swissarmybench_powerapps.server import routes as door
    from swissarmybench_powerapps.services.powerapps import PowerApps

    def opened(folder: str | None) -> None:
        # The open code app is the open project: its .sab/project.json's type sets the mode.
        if folder is not None or services.projects.opened == service.folder:
            services.projects.opened = folder

    service = PowerApps(
        runner=runner.Runner(),
        stop=runner.stop,
        files=files.ProjectFiles(Path(services.settings.state_dir) / "powerapps.json"),
        connector_service=environment_api.fetch_connector,
        audit=services.ws.audit,
        live=services.live,
        approvals=services.agent.approvals,
        api_documents=services.api_explorer.document_of,
        free_port=runner.free_port,
        prefix=door.LIVE_PREFIX,
        opened=opened,
    )
    services.powerapps = service  # its stop, and tests
    return door.routes(service)


async def stop(services: Any) -> None:
    """When the server stops: the dev server with it."""
    service = getattr(services, "powerapps", None)
    if service is not None:
        await service.stop_all()


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_powerapps.commands import COMMANDS

    return COMMANDS
