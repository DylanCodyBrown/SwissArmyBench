"""A table property takes a connection's table (the owner's ask, 2026-11-21: "[Conn].table through the same
picker as the open and data.ipynb tables"). The value is the table as DuckDB SQL names it; a run reads it
through the connection-tables contract (the one gate, so the connection's query limit holds) into the run's
data/ as Parquet, under a safe file name the runtime finds by the same rule. data.ipynb's tables are data.py's
top-level names (read with ast). A value naming no connection here is said with the fix. Made-up data only."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import canvas_build
from swissarmybench_streamlit.domain import widget_properties as props
from tests.conftest import AUTH, make_client
from tests.streamlit_helpers import FakeRunner
from tests.test_connection_tables import sqlite_connection


def test_a_connections_table_is_named_as_sql_names_it() -> None:
    assert props.connection_of("[Finance Captive].Sales") == "Finance Captive"
    assert props.connection_of("[Shop].public.orders") == "Shop"
    assert props.connection_of("orders") is None and props.connection_of("") is None
    assert props.connection_of("[Shop]") is None and props.connection_of(3) is None


def test_its_file_name_is_the_runtimes_too() -> None:
    """canvas_build.table_stem and the runtime's _stem are one rule: the page finds the run's Parquet."""
    tree = ast.parse(canvas_build.RUNTIME)
    source = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_stem")
    namespace: dict[str, Any] = {}
    exec(  # noqa: S102 (our own runtime's one function, standard library only)
        "import hashlib, re\n" + ast.unparse(source), namespace
    )
    for name in ("orders", "[Shop].segments", "[Finance Captive].Sales model", "[x].a/b..c", "_t1"):
        assert namespace["_stem"](name) == canvas_build.table_stem(name)
    assert canvas_build.table_stem("orders") == "orders"
    made = canvas_build.table_stem("[Shop].segments")
    assert made.startswith("Shop_segments_") and len(made) == len("Shop_segments_") + 8


def test_a_value_naming_no_connection_here_is_said_with_the_fix() -> None:
    table = props.Property("table_name", "table", "")
    here = props.Context(tables={"orders": ["region"]}, connections={"Shop"})
    props.check(table, "[shop].segments", here)  # any case, as SQL resolves it
    props.check(table, "orders", here)
    with pytest.raises(props.PropertyError) as said:
        props.check(table, "[Warehouse].sales", here)
    assert str(said.value) == "There is no connection called Warehouse here."
    assert "Connections page" in said.value.fix
    props.check(table, "[Warehouse].sales", props.Context(tables={}))  # connections not known: no refusal


def test_data_ipynbs_tables_are_data_pys_names() -> None:
    data = (
        "import pandas as pd\n"
        "LIMIT = 10\n"
        "_scratch = pd.DataFrame()\n"
        "orders = pd.read_csv('orders.csv')\n"
        "by_region: pd.DataFrame = orders.groupby('region').sum()\n"
        "regions = ['North', 'South']\n"
        "def helper():\n    return 1\n"
        "orders = orders[orders.amount > 0]\n"
    )
    assert props.module_tables(data) == ["orders", "by_region"]
    assert props.module_tables(None) == [] and props.module_tables("not python (") == []


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner, Path]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.live_runs._runner = runner  # type: ignore[attr-defined]
        segments = [(i, "Gold" if i % 2 else "Silver") for i in range(1, 9)]
        sqlite_connection(
            client, tmp_path, "Shop", {"segments": ("CustomerKey INTEGER, Segment TEXT", segments)}
        )
        project = tmp_path / "shop"
        project.mkdir()
        yield client, runner, project


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_a_widget_reads_a_connections_table_when_it_plays(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, runner, project = served
    context = ok(client.get("/streamlit/widgets/context", headers=AUTH))
    assert "Shop" in context["connection_tables"] and context["open_tables"] == []
    checked = ok(
        client.post(
            "/streamlit/widgets/check-value",
            headers=AUTH,
            json={"name": "data_table", "property": "table_name", "value": "[Nope].segments"},
        )
    )
    assert checked == {
        "ok": False,
        "said": "There is no connection called Nope here.",
        "fix": "Pick a connection's table from the list, or add the connection on the Connections page.",
    }
    made = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"name": "Sales", "folder": str(project)})
    )
    canvas = made["canvas"]
    body = {"kind": "insert_widget", "widget": "data_table", "values": {"table_name": "[Shop].segments"}}
    state = ok(client.post(f"/streamlit/canvases/{canvas}/command", headers=AUTH, json=body))
    assert state["marks"] == {}  # the value fits: no mark on the instance
    ok(client.post(f"/streamlit/canvases/{canvas}/play", headers=AUTH, json={"python": "/p"}))
    folder = Path(runner.started[-1][1])
    read = pq.read_table(folder / "data" / f"{canvas_build.table_stem('[Shop].segments')}.parquet")
    assert read.num_rows == 8 and read.column_names == ["CustomerKey", "Segment"]
    # The read went through the connection-tables contract: the session's reads say so.
    reads = ok(client.get("/connections/sql/reads", headers=AUTH))["reads"]
    assert any(r["connection"] == "Shop" for r in reads), json.dumps(reads)[:400]
