"""The statistics service (services/call_stats.py): a connection's call through its slots with its child's
facts, the adapter's hook in this process (the app's own session left out), an API envelope, .sab/stats.json
written only when it changes and read back by project, the agent's stats tool through the server. Made-up
data only."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter as sab
from swissarmybench.adapters.call_stats import StatsFiles
from swissarmybench.domain.connection_slots import Limits
from swissarmybench.services.call_stats import STATS_FILE, CallStats
from swissarmybench.services.connection_slots import Caller, ConnectionSlots, calling_as
from tests.conftest import AGENT, AUTH
from tests.test_connection_tables import sqlite_connection


class Live:
    async def broadcast(self, message: dict[str, Any]) -> None:
        pass


class Audit:
    def write(self, *args: Any, **more: Any) -> None:
        pass


class Folder:
    def __init__(self, path: str | None) -> None:
        self.path = path

    def __call__(self) -> str | None:
        return self.path


def _facts(rows: int) -> dict[str, Any]:
    return {
        "call": "read",
        "source": "Warehouse",
        "table": "orders",
        "ms": {"connect": None, "first_row": 5.0, "total": 9.0},
        "size": {"rows": rows, "bytes": rows * 8, "batches": 1, "columns": 2, "asked": 2},
        "folded": ["columns"],
        "by_duckdb": [],
        "outcome": {"ok": True, "error": ""},
        "fingerprint": "f" * 12,
    }


def test_a_call_through_the_slots_is_one_record_with_its_childs_facts(tmp_path: Path) -> None:
    stats = CallStats(StatsFiles(), Folder(str(tmp_path)), lambda: "2026-11-22T10:00:00")
    slots = ConnectionSlots(Live(), Audit(), lambda name: Limits(), clock=lambda: 0.0)  # type: ignore[arg-type]
    slots.on_finished = stats.finished

    async def work() -> dict[str, Any]:
        return {"table": pa.table({"id": [1, 2, 3]}), "facts": [_facts(3)]}

    async def scenario() -> dict[str, Any]:
        with calling_as(Caller("agent", "The agent", source={"document": "/x/sales.ipynb", "cell": 4})):
            return await slots.run("Warehouse", work, kind="read", targets=("orders",))

    answer = asyncio.run(scenario())
    assert "facts" not in answer  # the statistics' only: what a route answers is as it was
    view = stats.view("table", "Warehouse.orders")
    (call,) = view["calls"]
    assert call["who"] == "agent" and call["where"] == {"notebook": "sales.ipynb", "cell": 4}
    assert call["size"]["rows"] == 3 and call["ms"]["first"] == 5.0 and call["fingerprint"] == "f" * 12
    assert view["figures"]["count"] == 1
    stats.flush()
    kept = (tmp_path / STATS_FILE).read_text(encoding="utf-8")
    assert json.loads(kept)["figures"]["table:Warehouse.orders"]["count"] == 1
    stamp = (tmp_path / STATS_FILE).stat().st_mtime_ns
    stats.flush()  # nothing new: nothing written
    assert (tmp_path / STATS_FILE).stat().st_mtime_ns == stamp


def test_the_adapters_hook_leaves_the_apps_own_session_and_follows_the_project(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    project = Folder(str(one))
    stats = CallStats(StatsFiles(), project, lambda: "t")
    con = duckdb.connect()
    con.execute("CREATE TABLE lines AS SELECT range AS id FROM range(10)")
    sab.observe(stats.adapter)
    try:
        sab.query(sab.DuckDB.session(con), "SELECT 1").read_all()  # a grid's window: not a call
        sab.read(sab.DuckDB.over(con, "The sandbox"), "lines")[0].read_all()
        assert stats.view("summary")["calls"] == 1
        project.path = str(two)  # another project opens: the first one's figures are written first
        sab.read(sab.DuckDB.over(con, "The sandbox"), "lines")[0].read_all()
    finally:
        sab.observe(None)
    first = json.loads((one / STATS_FILE).read_text(encoding="utf-8"))
    assert first["figures"]["table:The sandbox.lines"]["count"] == 1
    assert stats.figures_of("table", ["The sandbox.lines"])["The sandbox.lines"]["count"] == 1
    project.path = str(one)
    assert stats.figures_of("table", ["The sandbox.lines"])["The sandbox.lines"]["count"] == 1


def test_an_api_envelope_and_the_observe_hook_count_once() -> None:
    stats = CallStats(StatsFiles(), Folder(None), lambda: "t")
    envelope: dict[str, Any] = {
        "facts": {
            "api": "Shop",
            "action": "list_orders",
            "who": "user",
            "ms": {"wait": 0, "first_byte": 3, "total": 8},
            "size": {"records": 2, "bytes": 40, "pages": 1, "columns": 2},
            "outcome": {"status": 200, "ok": True, "retries": 0, "error": ""},
        },
        "shape": {"fingerprint": "s" * 12},
    }
    with stats.own():
        stats.api_observed(envelope["facts"])  # said by its caller instead
    stats.api(envelope, {"widget": "orders_table", "page": "Overview"})
    stats.api_observed(envelope["facts"])  # a run nobody says: counted
    view = stats.view("endpoint", "Shop list_orders")
    assert view["figures"]["count"] == 2
    assert view["calls"][1]["where"] == {"widget": "orders_table", "page": "Overview"}


def test_a_connections_table_read_through_the_app_is_one_call_with_its_parts(
    client: TestClient, tmp_path: Path
) -> None:
    rows = [(i, "North" if i % 2 else "South") for i in range(1, 51)]
    sqlite_connection(client, tmp_path, "Shop", {"orders": ("id INTEGER, region TEXT", rows)})
    sql = "SELECT region, count(*) AS n FROM [Shop].orders WHERE region = 'North' GROUP BY region"
    prepared = client.post("/connections/sql/prepare", json={"sql": sql}, headers=AGENT)
    assert prepared.status_code == 200, prepared.text
    said = client.get("/stats", params={"action": "table", "name": "Shop.orders"}, headers=AGENT).json()
    (call,) = said["calls"]
    assert call["who"] == "agent" and call["outcome"]["ok"] is True
    assert (
        call["size"]["rows"] == 25 and call["ms"]["connect"] is not None and call["ms"]["first"] is not None
    )
    assert "filters" in call["folded"] and call["fingerprint"]
    assert "North" not in json.dumps(said)  # the filter's value never comes along
    cards = client.get("/stats/figures", params={"kind": "connection", "names": "Shop"}, headers=AUTH).json()
    assert cards["figures"]["Shop"]["count"] == 3  # its catalog listed, the rows counted, the table read
    card = next(
        c for c in client.get("/connections/usage", headers=AUTH).json()["connections"] if c["name"] == "Shop"
    )
    assert card["calls"]["figures"]["count"] == 3 and card["calls"]["total"] >= 1


def test_the_agents_stats_tool_through_the_server(client: TestClient) -> None:
    said = client.get("/stats", params={"action": "summary"}, headers=AGENT).json()
    assert said["action"] == "summary" and "busiest" in said
    assert client.get("/stats", params={"action": "nonsense"}, headers=AUTH).status_code == 400
    assert client.get("/stats", params={"action": "table"}, headers=AUTH).status_code == 400
    nobody = client.get("/stats/figures", params={"kind": "connection", "names": "Nobody"}, headers=AUTH)
    assert nobody.json() == {"figures": {}}
