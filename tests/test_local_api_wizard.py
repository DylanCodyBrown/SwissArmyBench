"""The endpoint wizard on its own (services/local_api_wizard.py), over a fake of what it asks of API.py: no
server, no process, no file (craft review 2026-11-22, item 10). Made-up tables."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swissarmybench.domain import local_api as rules
from swissarmybench.services.local_api_wizard import EndpointWizard, data_words
from swissarmybench.services.workspace import NotFound

ORDERS = {
    "name": "orders",
    "rows": 12,
    "columns": [
        {"name": "order_id", "type": "INTEGER", "key": True},
        {"name": "region", "type": "VARCHAR"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "ordered_on", "type": "DATE"},
    ],
    "client": {"kind": "duckdb"},
}


class FakeApi:
    def __init__(self, text: str | None = None) -> None:
        self.file = text
        self.writes: list[tuple[str, str, dict[str, Any]]] = []
        self.made = 0

    async def sandbox_tables(self) -> list[dict[str, Any]]:
        return [ORDERS]

    def text(self) -> str | None:
        return self.file

    async def new(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        self.made += 1
        self.file = rules.scaffold("api")
        return {}

    async def append(self, before: str, written: str, who: str, **facts: Any) -> None:
        self.writes.append((before, who, facts))
        self.file = written

    async def set_key(self, body: Any, who: str = "user") -> dict[str, Any]:
        return {}

    async def state(self, body: Any = None, who: str = "user", full: bool = False) -> dict[str, Any]:
        api = rules.parse(self.file or "")
        return {"endpoints": [{"name": e.name, "method": e.method, "path": e.path} for e in api.endpoints]}


def test_the_plan_ranks_the_patterns_and_writes_nothing() -> None:
    api = FakeApi()
    wizard = EndpointWizard(api)
    tables = asyncio.run(wizard.plan({}))
    assert [t["name"] for t in tables["tables"]] == ["orders"]
    assert tables["tables"][0]["data"] == "The sandbox (plain DuckDB)"
    ranked = asyncio.run(wizard.plan({"table": "Orders"}))
    assert ranked["table"] == "orders" and ranked["ranked"]
    planned = asyncio.run(wizard.plan({"table": "orders", "pattern": "table"}))
    assert planned["problem"] is None and "def " in planned["code"]
    assert api.writes == [] and api.made == 0


def test_a_table_not_in_the_sandbox_is_said() -> None:
    with pytest.raises(NotFound, match="Add to sandbox first"):
        asyncio.run(EndpointWizard(FakeApi()).plan({"table": "invoices"}))


def test_scaffold_makes_api_py_first_then_appends_its_endpoints() -> None:
    api = FakeApi()
    wizard = EndpointWizard(api)
    dry = asyncio.run(wizard.scaffold({"table": "orders", "pattern": "table", "dry_run": True}))
    assert dry["dry_run"] is True and api.made == 0 and api.writes == []
    done = asyncio.run(wizard.scaffold({"table": "orders", "pattern": "table"}, "agent"))
    assert api.made == 1
    assert [(who, facts) for _, who, facts in api.writes] == [
        ("agent", {"table": "orders", "pattern": "table"})
    ]
    assert done["added"] and done["pattern"] == "table"
    assert wizard.paired() and {p["pattern"] for p in wizard.paired()} == {"table"}


def test_data_words() -> None:
    assert data_words("Warehouse", None).startswith("Warehouse: no table of it")
    client = {"kind": "database", "connection": "Warehouse", "template": "sqlserver"}
    assert data_words("Warehouse", client) == "Mock of Warehouse (sqlserver)"
