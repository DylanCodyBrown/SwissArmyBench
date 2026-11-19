# ruff: noqa: F811
"""A DuckDB SQL cell sees the tables open in Grids under their names (feel-a, 2026-11-19): read-only,
the grid's view with its steps applied, read when the query names one this Python does not have. In
`sab.sql`/`%%sql` with no connection and in a Workbench kernel's SQL cell; a name nothing has keeps
DuckDB's error, said once, with the table's cell offered when it is open. Made-up data only."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.ipc as ipc
import pytest

import swissarmybench as sab
from swissarmybench.client import sql_cell, table_cells
from tests.test_cli import Live, live, run  # noqa: F401 (the running server, and the agent's commands)

ORDERS = pd.DataFrame(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["North", "South", "North", "East", "South", "North"],
        "amount": [10.5, 7.0, 2.5, 40.0, 31.0, 22.0],
    }
)
FILTER = [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 5}}]


def lines(live: Live, path: str, body: Any) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{live.port}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {live.token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (the test's own server)
        return [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]


def raw(live: Live, path: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{live.port}{path}", headers={"Authorization": f"Bearer {live.token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (the test's own server)
            return response.status, bytes(response.read())
    except urllib.error.HTTPError as error:
        return error.code, bytes(error.read())


@pytest.fixture(autouse=True)
def clean() -> Any:
    table_cells.forget()
    sql_cell._here.clear()
    yield
    table_cells.forget()
    sql_cell._here.clear()


def test_an_open_grid_is_read_as_its_view_with_its_steps(live: Live) -> None:
    grid = sab.push(ORDERS, name="orders")
    grid_id = next(t for t in live.user("GET", "/workbench/tables")["tables"] if t["name"] == "orders")[
        "grid"
    ]
    live.user("POST", f"/grids/{grid_id}/steps", {"steps": FILTER})
    status, body = raw(live, "/workbench/tables/orders/arrow")
    assert status == 200, body
    table = ipc.open_stream(body).read_all()
    assert table.num_rows == 5 and table.column_names == ["order_id", "region", "amount"]
    # Any case, as DuckDB reads a name; a table nothing has open is a 404 in the one refusal shape.
    assert raw(live, "/workbench/tables/ORDERS/arrow")[0] == 200
    status, body = raw(live, "/workbench/tables/nothing_open/arrow")
    assert status == 404 and "error" in json.loads(body)
    assert grid  # the push said where it went


def test_sab_sql_with_no_connection_names_an_open_grid(
    live: Live, capsys: pytest.CaptureFixture[str]
) -> None:
    sab.push(ORDERS, name="orders")
    grid_id = next(t for t in live.user("GET", "/workbench/tables")["tables"] if t["name"] == "orders")[
        "grid"
    ]
    live.user("POST", f"/grids/{grid_id}/steps", {"steps": FILTER})
    found = sql_cell.duck("SELECT region, count(*) AS n FROM orders GROUP BY ALL ORDER BY region", {})
    assert found.to_dict("records") == [
        {"region": "East", "n": 1},
        {"region": "North", "n": 2},
        {"region": "South", "n": 2},
    ]
    assert "orders: the open table in Grids" in capsys.readouterr().out
    # Never a copy kept: the next query reads the grid again, its new steps with it.
    live.user("POST", f"/grids/{grid_id}/steps", {"steps": []})
    assert int(sql_cell.duck("SELECT count(*) AS n FROM orders", {})["n"][0]) == 6
    # This Python's own table of that name wins over the grid's.
    mine = pd.DataFrame({"order_id": [9]})
    assert int(sql_cell.duck("SELECT count(*) AS n FROM orders", {"orders": mine})["n"][0]) == 1
    with pytest.raises(Exception, match="Table with name nothing_here does not exist"):
        sql_cell.duck("SELECT * FROM nothing_here", {})


def test_a_workbench_sql_cell_reads_an_open_grid_and_an_error_is_said_once(
    live: Live, tmp_path: Path
) -> None:
    sab.push(ORDERS, name="orders")
    kernel = live.user("POST", "/workbench/kernels", {"path": str(tmp_path / "report.ipynb")})["kernel"]
    execute = f"/workbench/kernels/{kernel}/execute"
    try:
        got = lines(live, execute, {"kind": "sql", "code": "SELECT count(*) AS n FROM orders"})
        assert got[-1]["done"]["ok"] is True, got
        assert any("6" in json.dumps(o) for o in got if o.get("output_type") == "execute_result")
        failed = lines(live, execute, {"kind": "sql", "code": "SELECT * FROM ordrs_typo"})
        streams = [o for o in failed if o.get("output_type") == "stream" and o.get("name") == "stderr"]
        assert not any("UsageError" in str(o.get("text")) for o in streams)  # the panel says it, once
        detail = next(o["error_detail"] for o in failed if "error_detail" in o)
        entry = detail["chain"][-1]
        assert "pg_" not in entry["message"]
        assert entry["sql"]["missing"] == "ordrs_typo"
    finally:
        live.user("DELETE", f"/workbench/kernels/{kernel}")
