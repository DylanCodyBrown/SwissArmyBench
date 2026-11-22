# ruff: noqa: F811
"""The open tables as a source of the adapter (Plans/adapter.plan.md, Order 3; the owner: the rule covers the
engine too): a kernel's sab.table(name) is the adapter's read over a table's grid view, its steps applied and
its plan folded by the app's DuckDB, the answer an Arrow table; the table itself stays the app's one copy.
A kernel's DuckDB SQL naming an open table reads it the same way. Made-up data only."""

from __future__ import annotations

import pandas as pd
import pytest

import swissarmybench as sab
from swissarmybench.adapters import adapter
from swissarmybench.client import sql_cell, table_cells
from tests.test_cli import Live, live  # noqa: F401 (the running server)

ORDERS = pd.DataFrame(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["North", "South", "North", "East", "South", "North"],
        "amount": [10.5, 7.0, 2.5, 40.0, 31.0, 22.0],
    }
)
FILTER = [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 5}}]


@pytest.fixture(autouse=True)
def clean() -> object:
    table_cells.forget()
    sql_cell._here.clear()
    yield
    table_cells.forget()
    sql_cell._here.clear()


def _with_filter(live: Live) -> None:
    sab.push(ORDERS, name="orders")
    grid = next(t for t in live.user("GET", "/workbench/tables")["tables"] if t["name"] == "orders")["grid"]
    live.user("POST", f"/grids/{grid}/steps", {"steps": FILTER})


def test_sab_table_reads_the_grid_view_through_the_adapter(live: Live) -> None:
    _with_filter(live)
    whole = sab.table("orders")
    assert whole.num_rows == 5 and whole.column_names == ["order_id", "region", "amount"]
    planned = sab.table("ORDERS", columns=["region", "amount"], filters=[("region", "=", "North")],
                        sort=[("amount", "desc")], limit=1)  # fmt: skip
    assert planned.to_pylist() == [{"region": "North", "amount": 22.0}]
    listed = {t["name"]: t for t in live.user("POST", "/workbench/tables/adapter/tables", {})["tables"]}
    assert [c["name"] for c in listed["orders"]["columns"]] == ["order_id", "region", "amount"]


def test_the_adapter_lists_and_folds_the_whole_plan(live: Live) -> None:
    _with_filter(live)
    door = adapter.Remote(
        f"http://127.0.0.1:{live.port}/workbench/tables/adapter", "Open tables",
        {"Authorization": f"Bearer {live.token}"},
    )  # fmt: skip
    totals = adapter.Plan(group=("region",), totals=(adapter.Total("sum", "amount", "total"),),
                              sort=(("total", True),))  # fmt: skip
    reader, folded = adapter.read(door, "orders", totals)
    assert folded.parts == ("group", "totals", "sort")
    assert reader.read_all().to_pylist()[0] == {"region": "East", "total": 40.0}
    assert "orders" in [t.name for t in adapter.tables(door)]
    with pytest.raises(adapter.AdapterError, match="No table named nothing_open"):
        adapter.read(door, "nothing_open")


def test_a_kernels_duckdb_sql_reads_an_open_table_through_it(live: Live) -> None:
    _with_filter(live)
    found = sab.sql("SELECT count(*) AS n FROM orders")
    assert int(found["n"][0]) == 5
