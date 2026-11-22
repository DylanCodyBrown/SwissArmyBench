"""The API's data door into the sandbox on its own (services/sandbox.py DataDoor), over a fake sandbox: no
DuckDB, no file (craft review 2026-11-22, item 10). Made-up tables."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench.domain import sandbox as rules
from swissarmybench.services.sandbox import DataDoor
from swissarmybench.services.workspace import NotFound


class Files:
    def __init__(self) -> None:
        self.meta = rules.Meta(tables={"orders": {"source": {"kind": "grid"}}})
        self.written: list[tuple[str, str]] = []

    def read_meta(self) -> rules.Meta:
        return self.meta

    def write_meta(self, meta: rules.Meta) -> None:
        self.meta = meta

    def columns(self, table: str) -> list[dict[str, Any]]:
        return [{"name": "order_id", "type": "INTEGER"}]

    def write_arrow(self, name: str, data: bytes, key: Any, mode: str) -> dict[str, int]:
        self.written.append((name, mode))
        return {"inserted": 2, "updated": 1, "deleted": 0}


class FakeSandbox:
    def __init__(self) -> None:
        self.files = Files()
        self.lock = asyncio.Lock()
        self.told: list[list[str]] = []
        self.audit: list[tuple[str, str, Any]] = []
        self.ws = SimpleNamespace(
            audit=SimpleNamespace(
                write=lambda who, action, what, **more: self.audit.append((who, action, what))
            )
        )

    async def client(self, connection: Any) -> dict[str, Any]:
        return {"kind": "database", "connection": "Warehouse", "dialect": "postgres", "tables": ["orders"]}

    def open_files(self) -> Any:
        return self.files

    async def run(self, fn: Any, *args: Any) -> Any:
        return fn(*args)

    def stamp(self) -> str:
        return "2026-11-22T10:00:00"

    async def wrote(self, tables: list[str]) -> None:
        self.told.append(tables)


def test_the_tables_a_connection_is_mocked_over() -> None:
    door = DataDoor(FakeSandbox())
    found = asyncio.run(door.source_tables({"connection": "Warehouse"}))
    assert found == {"tables": [{"name": "orders", "columns": [{"name": "order_id", "type": "INTEGER"}]}]}


def test_a_write_is_counted_stamped_told_and_audited() -> None:
    sandbox = FakeSandbox()
    door = DataDoor(sandbox)
    given = {"connection": "Warehouse", "table": "dbo.ORDERS", "key": "order_id", "mode": "merge"}
    counts = asyncio.run(door.write_arrow(given, b"arrow", "api"))
    assert counts == {"inserted": 2, "updated": 1, "deleted": 0}
    assert sandbox.files.written == [("orders", "merge")]  # dbo.ORDERS is the sandbox's orders
    log = sandbox.files.meta.log["orders"]
    assert (log.inserted, log.updated, log.deleted) == (2, 1, 0)
    assert sandbox.files.meta.tables["orders"]["changed_at"] == "2026-11-22T10:00:00"
    assert sandbox.told == [["orders"]]
    assert sandbox.audit == [("api", "sandbox_write", "orders")]


def test_a_table_the_connection_has_none_of_is_said() -> None:
    door = DataDoor(FakeSandbox())
    with pytest.raises(NotFound, match="no table invoices from Warehouse"):
        asyncio.run(door.write_arrow({"connection": "Warehouse", "table": "invoices"}, b"", "api"))
