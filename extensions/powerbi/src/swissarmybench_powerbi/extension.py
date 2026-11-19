"""The Power BI extension as the base reads it (swissarmybench/extensions.py): its description, the actions it
adds to the base's pages as data (PAGE_ACTIONS: the ERD's Export to Power BI…), its door, its agent commands
and its Session page words. This is the extension's composition root: it builds its adapters and hands them
to its service.
"""

from __future__ import annotations

from typing import Any

from swissarmybench_powerbi import __version__

ID = "powerbi"
NAME = "Power BI"
VERSION = __version__
DESCRIPTION = "Power BI Desktop files from your model: tables, relationships and each table's Power Query."
ADDS = [
    "Export to Power BI… on the ERD page: a Power BI Project that Power BI Desktop opens",
    "Each table's Power Query from its connection or file; a database table's steps as its own SQL",
    "Relationships with one active path between two tables, as Power BI wants",
]
AREAS = (("powerbi", "Power BI (an extension): the model exported as a Power BI Project"),)
# The base's pages draw these as buttons (the words are the extension's); a click runs the page's plug-in of
# that id with the page's own tables (web/src/pageActions.ts).
PAGE_ACTIONS: list[dict[str, str]] = [
    {
        "page": "erd",
        "id": "powerbi_export",
        "label": "Export to Power BI…",
        "icon": "export",
        "title": "These tables and their relationships as a Power BI Project",
    }
]
SECRET_PATHS: tuple[str, ...] = ()
PROJECT_TYPE = "powerbi"
# The files this extension opens when one is opened with the app or dropped on a window (never their program).
OPENS: dict[str, str] = {".pbix": "/powerbi/opened", ".pbit": "/powerbi/opened", ".pbip": "/powerbi/opened"}
# The rail's Power BI area (GET /app/areas): its page drawn from data (`panel`), never named in web/.
RAIL: list[dict[str, str]] = [
    {"area": "powerbi", "name": "Power BI", "icon": "powerbi", "panel": "/powerbi/panel"}
]
# The Power BI project (the owner, 2026-11-19): its target is one .pbix; it keeps some features closed to stay
# simple (`areas`: the features open in it; missing: all, as for every other type).
MODE: dict[str, Any] = {
    "type": PROJECT_TYPE,
    "name": "Power BI",
    "deliverable": "a Power BI report",
    "canvases": [],
    "families": ["Power BI", "DAX"],
    "languages": ["python"],
    "cell_kinds": [],
    "tools": ["powerbi_"],
    "export": ["powerbi"],
    "title": "Power BI",
    "for_whom": "For anyone who works on a Power BI report and wants its data checked at the source.",
    "explain": (
        "Start from a .pbix: its connections, tables, relationships and measures come in ready to work. Each "
        "table is read from its source and as Power BI has it, side by side, so you can compare them."
    ),
    "example": "Example: the sales report's numbers tied out to the warehouse before the month closes.",
    "areas": [
        "projects", "powerbi", "connections", "variables", "data",
        "grids", "erd", "notebooks", "session", "settings",
    ],
    "first_open": (
        "This Power BI project keeps some features closed to stay simple: {closed}. You can open them "
        "any time "
        "in Settings, Open every feature in this project."
    ),
    "tour": [
        {"area": "powerbi", "words": "Your report: what it reads, what is left to set up, and its measures."},
        {"area": "grids", "words": "Each table twice: from its source and as Power BI has it. Compare them."},
        {"area": "erd", "words": "The report's relationships, active and inactive."},
        {"area": "notebooks", "words": "data.ipynb: each table's SQL and DAX, one cell each."},
    ],
}  # fmt: skip


def scaffold(name: str, data_names: list[str]) -> dict[str, Any]:
    """A Power BI project's own files: none beyond data.ipynb (the import writes it, and powerbi.json)."""
    return {"app": False, "files": {}, "requirements": []}


def _erd(what: str) -> tuple[str, str, dict[str, Any]]:
    return what, "relationships", {"place": "view", "view": "erd"}


# The Session page's words for each audit entry (names and counts only).
SESSION_RULES: dict[str, Any] = {
    "export to power bi": lambda d, x: _erd(f"Exported {d} to Power BI ({x.get('tables')} tables)"),
}


def describe() -> dict[str, Any]:
    return {"id": ID, "name": NAME, "description": DESCRIPTION, "version": VERSION, "adds": ADDS}


class _Files:
    """Export to Power BI's files (adapters/files.py), its .pbip opened or its folder shown."""

    def __init__(self) -> None:
        from swissarmybench.server import file_manager
        from swissarmybench_powerbi.adapters import files

        self._files = files
        self._show = file_manager.show

    def existing(self, folder: str) -> list[str]:
        return self._files.existing(folder)

    def write(self, folder: str, files: Any) -> list[str]:
        return self._files.write(folder, files)

    def remove(self, folder: str, paths: list[str]) -> None:
        self._files.remove(folder, paths)

    def zipped(self, files: Any, top: str) -> bytes:
        return self._files.zipped(files, top)

    def save_zip(self, folder: str, name: str, data: bytes) -> str:
        return self._files.save_zip(folder, name, data)

    def has_program(self, path: str) -> bool:
        return self._files.has_program(path)

    def open_file(self, path: str) -> str:
        return self._files.open_file(path, self._show)


def routes(services: Any) -> list[Any]:
    from swissarmybench_powerbi.adapters import report_files
    from swissarmybench_powerbi.server import routes as door
    from swissarmybench_powerbi.services.export import PowerBIExport

    service = PowerBIExport(
        services.ws,
        services.models,
        origins=services.datasets.origins.get,
        connection=lambda name: services.connections.blade(name)[0],
        shareable=services.variables.shareable,
        project=lambda: services.sab_projects.state().get("project"),
        used=services.project_tables.used,
        files=_Files(),
        writer=services.export_writer,
        approvals=services.agent.approvals,
        read_report=report_files.read,
    )
    services.powerbi_export = service  # tests
    from swissarmybench_powerbi.adapters import pbix_reader
    from swissarmybench_powerbi.adapters.files import StateFiles
    from swissarmybench_powerbi.server import routes_project
    from swissarmybench_powerbi.services.project import PowerBIProject

    project = PowerBIProject(
        services,
        pbix_reader.read,
        StateFiles(),
        services.agent.approvals,
        registrations=services.app_registrations.names,
    )
    from pathlib import Path

    from swissarmybench_powerbi.adapters import live_link as live_files
    from swissarmybench_powerbi.services.live_link import LiveLink

    state_dir = Path(services.settings.state_dir)

    def target() -> str | None:
        try:
            return str(project.state()["target"])
        except Exception:  # no Power BI project open
            return None

    def ours() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            state = project.state()
        except Exception:
            return [], []
        return list(state.get("relationships", [])), list(state.get("measures", []))

    live = LiveLink(
        services.ws,
        live_files.discover,
        lambda port: live_files.TomModel(port, state_dir),
        target,
        ours,
        services.agent.approvals,
        live_files.windows,
    )
    project.live = live
    service.kept = project.kept  # part 1's export reads the round trip
    _standins(project, live)
    services.powerbi_live = live  # tests hand it a fake
    services.app_registrations.query_hints = project.query_hints
    services.powerbi_project = project  # tests hand it a fake reader
    return door.routes(service) + routes_project.routes(project) + routes_project.live_routes(live)


def commands() -> dict[str, Any]:
    from swissarmybench_powerbi.commands import COMMANDS

    return COMMANDS


async def stop(services: Any) -> None:
    live = getattr(services, "powerbi_live", None)
    if live is not None:
        live.stop()


def _standins(project: Any, live: Any) -> None:
    """Tests and screenshots only: SWISSARMYBENCH_PBIX_STANDIN names a module whose `reader` stands in for
    pbixray,
    SWISSARMYBENCH_PBI_DESKTOP_STANDIN one whose `instances` and `FakeDesktop` stand in for a running Power BI
    Desktop (a server started in its own process has no other way to be handed them)."""
    import importlib
    import os

    named = os.environ.get("SWISSARMYBENCH_PBIX_STANDIN")
    if named:
        project.reader = importlib.import_module(named).reader
    named = os.environ.get("SWISSARMYBENCH_PBI_DESKTOP_STANDIN")
    if named:
        module = importlib.import_module(named)
        running = module.FakeDesktop()
        live._discover, live._opener, live._windows = module.instances, lambda port: running, lambda: True
