"""The Power Apps extension as the base reads it (swissarmybench/extensions.py): its description and mode as
data, its door, its agent commands, its starters and its Session page words. This is the extension's
composition root: it builds its adapters and hands them to its service.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from swissarmybench_powerapps import __version__

if TYPE_CHECKING:
    from swissarmybench.services.hooks import ConnectionsSeam, Seams

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
    "A data notebook with TypeScript and SQL cells on one DuckDB (Deno's kernel), its data.ts for the app",
    "TSX cells drawn as React components; Dataverse tables as grids",
]
PROJECT_TYPE = "codeapp"
# The front-end plug-in it names (in the shared web/: codeAppPage.ts, the rail's Code App page).
FRONT_END = ["codeapp"]
# Its commands' area (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (("powerapps", "Power Apps: code apps (pa and pac), sources, connectors, Run live, Push"),)
# The code app mode (Plans/editions.plan.md, "Project modes"), as DATA: TypeScript and React; the
# component previews' canvas; the TypeScript and TSX cells and where each runs (phase 2: the data
# notebook's kernel; a DuckDB SQL cell runs there too, so both kinds share one DuckDB); the agent's tool
# group; Push as the export.
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
    # The project's files a person edits, for the Workbench's project files (domain/shown.py).
    "project_files": "/powerapps/project/files",
    "cell_routes": {
        "typescript": {
            "name": "TypeScript",
            "language": "typescript",
            "run": "/powerapps/notebook/run",
            "grid": "/powerapps/notebook/grid",
            "types": "/powerapps/notebook/types",
            "install": "/powerapps/tools/install",
        },
        "tsx": {
            "name": "TSX",
            "language": "tsx",
            "run": "",
            "preview": "/powerapps/notebook/preview",
            "types": "/powerapps/notebook/types",
            "install": "/powerapps/tools/install",
        },
        "sql": {
            "name": "SQL",
            "language": "sql",
            "run": "/powerapps/notebook/run",
            "grid": "/powerapps/notebook/grid",
            "install": "/powerapps/tools/install",
        },
    },
}

STARTERS = str(Path(__file__).resolve().parent / "starters")
SECRET_PATHS = ("/powerapps/live/", "/powerapps/notebook/prepare/")


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
    "powerapps_new_page": lambda d, x: _area(f"Made the page {_name(x.get('page'))}"),
    "powerapps_scaffold": lambda d, x: _area(f"Wrote {x.get('files')} starter files into the code app"),
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
    "powerapps_ts_run": lambda d, x: _area(
        f"Ran a {'SQL' if x.get('kind') == 'sql' else 'TypeScript'} cell"
        + (f" [{x.get('cell')}]" if x.get("cell") is not None else "")
        + ("" if x.get("ok") else " (failed)")
    ),
    "powerapps_ts_grid": lambda d, x: _area(f"Opened the result {_name(d)} as a grid"),
    "powerapps_ts_restart": lambda d, x: _area("Restarted the data notebook's kernel"),
    "powerapps_data_notebook": lambda d, x: _area("Made the code app's data notebook"),
    "powerapps_use_in_app": lambda d, x: _area("Wrote data.ts into the code app (Use in app)"),
    "powerapps_tsx_preview": lambda d, x: _area("Drew a TSX cell"),
    "powerapps_dataverse_grid": lambda d, x: _area(
        f"Opened the Dataverse source {_name(x.get('source'))} as a grid"
    ),
}


def dataverse_connections(connections: ConnectionsSeam) -> list[dict[str, Any]]:
    """The library's Dataverse connections and each one's environment address (its code's `url`)."""
    from swissarmybench.domain.blades import detect_settings

    found = []
    for listed in connections.listing()["connections"]:
        if listed.get("template") != "dataverse":
            continue
        try:
            blade, _ = connections.blade(str(listed["name"]))
            url = next(
                (str(s.value) for s in detect_settings(blade.code) if s.key == "url" or s.name == "address"),
                "",
            )
        except Exception:  # noqa: S112 (a connection that cannot be read is not the one)
            continue
        found.append({"name": str(listed["name"]), "kind": "dataverse", "url": url})
    return found


def routes(seams: Seams) -> list[Any]:
    """Its routes, its service built from the base's (the audit log, the live updates, the agent's
    approvals, the library's APIs, the open project) and its own adapters."""
    from swissarmybench.adapters import export as export_writer
    from swissarmybench_powerapps.adapters import deno_kernel, environment_api, files, notebook_files, runner
    from swissarmybench_powerapps.server import routes as door
    from swissarmybench_powerapps.services.notebook import OpenTables, TsNotebooks
    from swissarmybench_powerapps.services.powerapps import PowerApps

    def opened(folder: str | None) -> None:
        # The open code app is the open project: its .sab/project.json's type sets the mode.
        if folder is not None or seams.opened_folder() == service.folder:
            seams.set_opened(folder)

    processes = runner.Runner()
    project_files = files.ProjectFiles(Path(seams.settings.state_dir) / "powerapps.json")
    service = PowerApps(
        runner=processes,
        stop=runner.stop,
        files=project_files,
        connector_service=environment_api.fetch_connector,
        audit=seams.ws.audit,
        live=seams.ws.live,
        approvals=seams.approvals,
        api_documents=seams.api_document,
        free_port=runner.free_port,
        prefix=door.LIVE_PREFIX,
        opened=opened,
    )

    async def environments() -> list[dict[str, Any]]:
        # Listed once when none are yet (pac env list: the user's or the agent's own action).
        if not service.state_environments():
            await service.environments()
        return service.state_environments()

    notebook = TsNotebooks(
        launcher=deno_kernel.Launcher(),
        runner=processes,
        files=notebook_files.NotebookFiles(),
        tables=OpenTables(seams.ws, export_writer),
        store_table=lambda name, table, who: seams.datasets.store_table(name, table, "parquet", True, who),
        prepare=seams.connection_tables.prepare,
        code_app=lambda: service.folder,
        write_app_file=project_files.write,
        audit=seams.ws.audit,
        live=seams.ws.live,
        connections=lambda: dataverse_connections(seams.connections),
        open_connection_table=seams.connections.open_table,
        environments=environments,
        environment_id=lambda: str(service.project_state().get("app", {}).get("environment_id") or ""),
        sources=lambda: list(service.project_state().get("sources") or []),
    )
    # Its own place on the record: its stop, and tests.
    seams.extension[ID] = Own(service, notebook)
    return door.routes(service, notebook)


@dataclass
class Own:
    """The Power Apps extension's own services (services.extension["powerapps"])."""

    powerapps: Any
    notebook: Any


async def stop(seams: Seams) -> None:
    """When the server stops: the dev server and the data notebooks' kernels with it."""
    own = seams.extension.get(ID)
    if own is not None:
        await own.powerapps.stop_all()
        await own.notebook.stop_all()


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_powerapps.commands import COMMANDS

    return COMMANDS
