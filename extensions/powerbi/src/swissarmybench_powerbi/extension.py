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
    )
    services.powerbi_export = service  # tests
    return door.routes(service)


def commands() -> dict[str, Any]:
    from swissarmybench_powerbi.commands import COMMANDS

    return COMMANDS
