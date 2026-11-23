"""Rules that were the composition root's closures, at the service layer with stand-ins: what the
server's stop does with the open project (services/sab_projects.py save_before_stop), and a loaded catalog's
summary for context.md (services/context_md.py catalog_of), and where a connection's references are looked
for (services/connection_usage.py documents_to_search), the outline's dashboards (services/project_outline.py
saved_dashboards). Made-up names only."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from swissarmybench.domain import context_md as rules
from swissarmybench.services.connection_usage import documents_to_search
from swissarmybench.services.context_md import catalog_of
from swissarmybench.services.project_outline import saved_dashboards
from swissarmybench.services.sab_projects import save_before_stop


class Projects:
    def __init__(self, current: Any, dirty: bool, fails: bool = False) -> None:
        self.current = current
        self._dirty = dirty
        self._fails = fails
        self.saved: list[str] = []

    def dirty(self) -> bool:
        return self._dirty

    async def save(self, body: Any, who: str = "user") -> dict[str, Any]:
        if self._fails:
            raise OSError("the disk is full")
        self.saved.append(who)
        return {}


def test_nothing_open_or_nothing_unsaved_stops_at_once() -> None:
    assert asyncio.run(save_before_stop(Projects(None, dirty=True))) == ""
    quiet = Projects(SimpleNamespace(autosave=True), dirty=False)
    assert asyncio.run(save_before_stop(quiet)) == "" and quiet.saved == []


def test_unsaved_work_is_saved_as_autosave_does_or_the_stop_waits() -> None:
    on = Projects(SimpleNamespace(autosave=True), dirty=True)
    assert asyncio.run(save_before_stop(on)) == "" and on.saved == ["autosave"]
    off = Projects(SimpleNamespace(autosave=False), dirty=True)
    assert asyncio.run(save_before_stop(off)) == "the open project has unsaved changes and Autosave is off"
    assert off.saved == []
    broken = Projects(SimpleNamespace(autosave=True), dirty=True, fails=True)
    assert asyncio.run(save_before_stop(broken)) == "the open project could not be saved: the disk is full"


class Catalogs:
    def __init__(self, schemas: list[dict[str, Any]] | None) -> None:
        self.schemas = schemas
        self.asked: list[tuple[str, str | None, int]] = []

    async def schema_names(self, name: str) -> list[dict[str, Any]] | None:
        return self.schemas

    async def tables(
        self, name: str, schema: str, database: str | None, offset: int, limit: int
    ) -> dict[str, Any]:
        self.asked.append((schema, database, limit))
        made = [{"database": database or "", "schema": schema, "table": f"t{i}"} for i in range(limit)]
        return {"tables": made[:3]}

    async def shared_tables(self, name: str) -> set[str]:
        return {"customers"}


def test_a_catalog_not_loaded_has_no_summary() -> None:
    assert asyncio.run(catalog_of(Catalogs(None), "Warehouse")) is None


def test_a_loaded_catalog_s_schemas_first_tables_count_and_shared_names() -> None:
    catalogs = Catalogs(
        [
            {"schema": "sales", "database": "shop", "tables": 2, "views": 1},
            {"schema": "empty", "database": "shop", "tables": 0, "views": 0},  # never asked for its tables
            {"schema": "stock", "database": "", "tables": 4},
        ]
    )
    schemas, tables, total, shared = asyncio.run(catalog_of(catalogs, "Warehouse")) or ([], [], 0, set())
    assert schemas == ["sales", "empty", "stock"]
    assert total == 7 and shared == {"customers"}
    most = rules.MAX_CATALOG_TABLES
    assert catalogs.asked == [("sales", "shop", most), ("stock", None, most)]
    assert tables[:2] == [
        rules.CatalogTable("shop", "sales", "t0"),
        rules.CatalogTable("shop", "sales", "t1"),
    ]
    assert len(tables) == 6


class FolderFiles:
    def __init__(self, names: list[str] | None) -> None:
        self._names = names

    def names(self, folder: str) -> list[str]:
        if self._names is None:
            raise OSError("gone")
        return self._names

    def path(self, folder: str, name: str) -> str:
        return f"{folder}/{name}"


def test_a_connection_s_references_are_looked_for_in_the_project_s_documents_each_once() -> None:
    def real(path: str) -> str:
        return path.replace("/link/", "/work/")

    files = FolderFiles(["load.py", "data.ipynb", "data.py", "notes.txt"])
    found = documents_to_search(["/link/shop/data.ipynb", "/work/x.py"], "/work/shop", files, list, real)
    assert found == ["/link/shop/data.ipynb", "/work/x.py", "/work/shop/load.py"]
    assert documents_to_search([], "/work/shop", FolderFiles(None), list, real) == []


def test_with_no_project_the_recent_files_that_are_still_there() -> None:
    recent = [{"path": "/work/a.py", "exists": True}, {"path": "/work/gone.py", "exists": False}]
    assert documents_to_search([], None, FolderFiles([]), lambda: recent, str) == ["/work/a.py"]


class Boards:
    def names(self) -> list[dict[str, Any]]:
        return [{"name": "Sales"}, {"name": "Draft"}]

    def read(self, name: str) -> dict[str, Any] | None:
        if name == "Sales":
            return {"versions": [{"cards": [{"id": "old"}]}, {"cards": [{"id": "c1"}, {"id": "c2"}]}]}
        return {"versions": []}

    def add_version(self, name: str, cards: list[dict[str, Any]], saved: str) -> int:
        return 0

    def delete(self, name: str) -> bool:
        return False


def test_the_outline_s_dashboards_are_each_one_s_last_version() -> None:
    assert saved_dashboards(Boards()) == [
        {"name": "Sales", "cards": [{"id": "c1"}, {"id": "c2"}]},
        {"name": "Draft", "cards": []},
    ]
