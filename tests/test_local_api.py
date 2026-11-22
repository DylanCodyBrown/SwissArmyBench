"""The project's local sandbox API (domain/local_api.py, services/local_api.py, server/api_host.py; the owner,
2026-11-21: "build api's here that could host locally inside the app so the streamlit could use our API as a
testing ground" / "No never run against live data ever").

API.py read with ast (endpoints, parameters, models, the OpenAPI document; problems with their lines), its
header
written alone; then the full loop on a real server: a made-up table into the sandbox, API.py with a mock
client,
Run, a GET and a POST through it, the grid of the sandbox table following, Reset back to the baseline, Stop.
The
hosting process gets no connection, variable or secret: an endpoint that asks for the real one gets the mock
or a
refusal. Made-up data only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import local_api as rules
from swissarmybench.server import api_runtime
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.conftest import TOKEN
from tests.live_server import running

API_PY = '''\
# /// swissarmybench-api
# name = "Shop API"
# description = "Made-up orders"
# target = "fastapi"
# base_path = ""
# ///
"""The shop's local sandbox API."""

import os
from typing import TypedDict

from sab_api import ApiError, connection, endpoint, records


class Order(TypedDict):
    order_id: int
    region: str
    amount: float


@endpoint("GET", "/orders/{region}")
def orders_in(region: str, limit: int = 100) -> list[Order]:
    """The orders of one region."""
    db = connection("Sandbox")
    found = db.query("SELECT * FROM orders WHERE region = ? ORDER BY order_id LIMIT ?", [region, limit])
    return records(found)


@endpoint("POST", "/orders", status=201)
def add_order(order: Order) -> Order:
    """Add an order."""
    connection("Sandbox").write("orders", [order])
    return order


@endpoint("GET", "/orders/one/{order_id}")
def one_order(order_id: int) -> Order:
    found = records(connection("Sandbox").read("orders", filters=[["order_id", "=", order_id]]))
    if not found:
        raise ApiError(404, f"No order {order_id}.")
    return found[0]


@endpoint("GET", "/peek/env")
def env_names() -> list[str]:
    return sorted(os.environ)


@endpoint("GET", "/peek/real")
def real_connection() -> dict:
    import swissarmybench as sab

    try:
        sab.blade("Warehouse")
    except RuntimeError as error:
        return {"refused": str(error)}
    return {"refused": ""}
'''

ORDERS = "order_id,region,amount\n1,West,10.5\n2,East,7.25\n3,West,3.0\n"


# ===== the rules =====


def test_api_py_is_read_with_ast_never_run() -> None:
    api = rules.parse(API_PY)
    assert api.settings.name == "Shop API" and api.settings.target == "fastapi"
    by = {e.name: e for e in api.endpoints}
    assert by["orders_in"].method == "GET" and by["orders_in"].path == "/orders/{region}"
    assert [(p.name, p.where, p.required) for p in by["orders_in"].params] == [
        ("region", "path", True),
        ("limit", "query", False),
    ]
    assert [(p.name, p.where) for p in by["add_order"].params] == [("order", "body")]
    assert by["orders_in"].connections == ["Sandbox"]
    assert by["orders_in"].sql[0]["text"].startswith("SELECT * FROM orders")
    assert set(api.models["Order"].fields) == {"order_id", "region", "amount"}
    doc = rules.openapi(api)
    op = doc["paths"]["/orders/{region}"]["get"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/Order"},
    }
    assert doc["components"]["schemas"]["Order"]["required"] == ["order_id", "region", "amount"]
    assert api.problems == []


def test_problems_say_their_lines() -> None:
    text = (
        "from sab_api import endpoint\n\n"
        '@endpoint("FETCH", "/x")\ndef a(): ...\n\n'
        '@endpoint("GET", "/y/{id}")\ndef b(): ...\n\n'
        '@endpoint("GET", "/z")\ndef c(): ...\n\n'
        '@endpoint("GET", "/z")\ndef d(): ...\n'
    )
    problems = rules.parse(text).problems
    assert [p["line"] for p in problems] == [3, 7, 12]
    assert "no parameter for the path's {id}" in problems[1]["message"]
    assert "answered by c already" in problems[2]["message"]
    assert rules.parse("def (:\n").problems[0]["line"] == 1


def test_the_header_is_written_alone() -> None:
    text = "# my notes\n" + API_PY.split("# ///\n", 1)[1]
    again = rules.with_settings(text, rules.Settings("Shop", "", "aws_lambda", "/api"))
    assert again.endswith(text) and again.startswith("# /// swissarmybench-api\n")
    assert rules.read_settings(again).target == "aws_lambda"
    moved = rules.with_settings(again, rules.Settings("Shop 2", "d", "fastapi", ""))
    assert moved.count("swissarmybench-api") == 1 and rules.read_settings(moved).name == "Shop 2"
    assert compile(rules.scaffold("shop"), "API.py", "exec")


def test_the_runtime_binds_the_path_the_query_and_the_body() -> None:
    api_runtime.ENDPOINTS.clear()
    calls: list[Any] = []

    @api_runtime.endpoint("GET", "/sum/{a}")
    def add(a: int, b: int = 1, flag: bool = False) -> dict[str, Any]:
        calls.append(flag)
        return {"sum": a + b}

    status, _, body = api_runtime.handle("GET", "/sum/2", {"b": "5", "flag": "true"}, None)
    assert status == 200 and json.loads(body) == {"sum": 7} and calls == [True]
    status, _, body = api_runtime.handle("GET", "/sum/x", {}, None)
    assert status == 422 and "a is not a whole number" in json.loads(body)["error"]
    assert api_runtime.handle("POST", "/sum/2", {}, None)[0] == 405
    assert api_runtime.handle("GET", "/nope", {}, None)[0] == 404
    api_runtime.ENDPOINTS.clear()


def test_the_hosting_process_gets_no_secret_or_connection_variable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    server = {
        "PATH": "/usr/bin",
        "WAREHOUSE_PASSWORD": "made-up-pa55",
        "SWISSARMYBENCH_TOKEN": "t",
        "AZURE_CLIENT_SECRET": "x",
    }
    env = rules.runner_env(server, {"SAB_API_KEY": "k"}, str(home))
    assert env["PATH"] == "/usr/bin" and env["SAB_API_KEY"] == "k"
    assert not {"WAREHOUSE_PASSWORD", "SWISSARMYBENCH_TOKEN", "AZURE_CLIENT_SECRET"} & set(env)
    assert env["HOME"] == env["SWISSARMYBENCH_STATE"] == str(home)


# ===== the full loop on a real server =====


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    monkeypatch.setenv("WAREHOUSE_PASSWORD", "made-up-pa55")  # the server's: never the API process's
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        info = tmp_path / "server.json"
        info.write_text(json.dumps({"port": port, "token": TOKEN}))
        monkeypatch.setenv("SWISSARMYBENCH_INFO", str(info))
        monkeypatch.setenv("SWISSARMYBENCH_OPEN", "0")
        yield port


def _ask(port: int, method: str, path: str, body: Any = None, agent: bool = False) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers=headers | ({"X-Actor": "agent"} if agent else {}),
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:  # noqa: S310
            return json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as failed:
        raise AssertionError(f"{failed.code}: {failed.read().decode()}") from None


def test_the_full_loop_sandbox_api_run_write_grid_reset(live: int, tmp_path: Path) -> None:
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    assert (folder / "API.py").exists()  # the scaffold makes it
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    grid = _ask(port, "POST", "/sandbox/tables/open", {"table": "orders"})["grid"]
    (folder / "API.py").write_text(API_PY, encoding="utf-8")
    state = _ask(port, "GET", "/local-api")
    assert [e["name"] for e in state["endpoints"]][:2] == ["orders_in", "add_order"]
    assert state["endpoints"][0]["data"] == ["The sandbox (plain DuckDB)"]
    ran = _ask(port, "POST", "/local-api/run", {})
    assert ran["running"]["port"], ran.get("failed")
    west = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/West"})
    assert west["status"] == 200 and [r["order_id"] for r in west["body"]] == [1, 3]
    added = _ask(
        port,
        "POST",
        "/local-api/call",
        {"method": "POST", "path": "/orders", "body": {"order_id": 4, "region": "West", "amount": 2.5}},
    )
    assert added["status"] == 201
    # From a kernel: sab.api(), through the app.
    from swissarmybench.client.api_client import ApiCallError, api

    assert [r["order_id"] for r in api().get("/orders/West", params={"limit": 1})] == [1]
    with pytest.raises(ApiCallError, match="404: No order 99"):
        api().get("/orders/one/99")
    missing = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/one/99"})
    assert missing["status"] == 404 and missing["body"] == {"error": "No order 99."}
    # The grid of the sandbox table shows the write.
    count = _ask(port, "GET", f"/grids/{grid}/count")
    assert count["row_count"] == 4
    assert _ask(port, "GET", "/sandbox")["log"] == {"orders": {"inserted": 1, "updated": 0, "deleted": 0}}
    # No connection, variable or secret in the API's process; the real client refused.
    names = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/peek/env"})["body"]
    assert "WAREHOUSE_PASSWORD" not in names and not [n for n in names if "TOKEN" in n]
    real = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/peek/real"})["body"]
    assert "never reaches a real connection" in real["refused"]
    log = _ask(port, "GET", "/local-api/log")["log"]
    assert [(r["method"], r["status"]) for r in log[:2]] == [("GET", 200), ("POST", 201)]
    assert log[0]["rows"] == 2
    assert "body" not in log[0]
    # Reset: back to the baseline, the grid following.
    _ask(port, "POST", "/sandbox/reset", {})
    assert _ask(port, "GET", f"/grids/{grid}/count")["row_count"] == 3
    again = _ask(port, "POST", "/local-api/call", {"method": "GET", "path": "/orders/West"})
    assert [r["order_id"] for r in again["body"]] == [1, 3]
    # A change on disk starts it again; a broken file says its line.
    (folder / "API.py").write_text(API_PY + "\ndef broken(:\n", encoding="utf-8")
    deadline = time.monotonic() + 20
    failed = None
    while time.monotonic() < deadline:
        failed = _ask(port, "GET", "/local-api").get("failed")
        if failed:
            break
        time.sleep(0.3)
    assert failed and failed["line"] == API_PY.count("\n") + 2
    stopped = _ask(port, "POST", "/local-api/stop", {})
    assert stopped["running"] is None


def _answer_next_approval(port: int, allow: bool) -> str:
    """The user's answer to the one approval the agent is waiting on: its words."""
    for _ in range(200):
        pending = _ask(port, "GET", "/agent/approvals")["pending"]
        if pending:
            _ask(port, "POST", f"/agent/approvals/{pending[0]['id']}", {"approve": allow})
            return str(pending[0]["detail"])
        time.sleep(0.05)
    raise AssertionError("no approval was asked for")


def _try(call: Any) -> Any:
    try:
        return call()
    except AssertionError as failed:
        return str(failed)


def test_one_allow_lets_the_agent_write_through_the_api_for_the_session(live: int, tmp_path: Path) -> None:
    import threading

    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    (folder / "API.py").write_text(API_PY, encoding="utf-8")
    assert _ask(port, "POST", "/local-api/run", {})["running"]
    assert _ask(port, "GET", "/local-api", agent=True)["agent_writes"] is False

    def add(order_id: int) -> Any:
        body = {"order_id": order_id, "region": "West", "amount": 1.0}
        return _ask(
            port, "POST", "/local-api/call", {"method": "POST", "path": "/orders", "body": body}, True
        )

    said: dict[str, Any] = {}
    first = threading.Thread(target=lambda: said.update(r=add(10)))
    first.start()
    words = _answer_next_approval(port, True)
    first.join(30)
    assert said["r"]["status"] == 201 and "for the rest of this session" in words and "never live" in words
    assert add(11)["status"] == 201  # no question this time
    assert _ask(port, "GET", "/local-api", agent=True)["agent_writes"] is True
    assert _ask(port, "POST", "/local-api/agent-writes", {"allow": False}) == {"agent_writes": False}
    second = threading.Thread(target=lambda: said.update(r=_try(lambda: add(12))))
    second.start()
    _answer_next_approval(port, False)
    second.join(30)
    assert "403" in said["r"]
    assert _ask(port, "GET", "/sandbox")["log"]["orders"]["inserted"] == 2
    _ask(port, "POST", "/local-api/stop", {})


# ===== New endpoint from a table =====


def test_the_crud_set_compiles_in_every_source_style() -> None:
    from swissarmybench.domain import api_scaffold as scaffold

    columns: list[dict[str, Any]] = [
        {"name": "order_id", "type": "BIGINT", "key": True},
        {"name": "region", "type": "VARCHAR"},
        {"name": "placed", "type": "DATE"},
    ]
    for source in (
        scaffold.Source("duckdb", "Sandbox"),
        scaffold.Source("database", "Warehouse", "sqlserver", "dbo"),
        scaffold.Source("database", "Shop", "postgres", "public"),
        scaffold.Source("database", "Ledger", "oracle"),
        scaffold.Source("dataverse", "Sales CRM", "dataverse"),
        scaffold.Source("sharepoint", "Team site"),
    ):
        block = scaffold.crud("orders", columns, source)
        api = rules.parse(rules.scaffold("x") + block)
        assert not api.problems, (source, api.problems)
        assert {e.name for e in api.endpoints} >= {"list_orders", "get_orders"}
        assert "OrdersRow" in api.models and api.models["OrdersRow"].fields["placed"][0] == "date"
    # One style for every source (phase 3): the adapter's calls, its schema in the table's name.
    tsql = scaffold.crud("orders", columns, scaffold.Source("database", "Warehouse", "sqlserver", "dbo"))
    assert 'connection("Warehouse").read("dbo.orders", sort=[["order_id", "asc"]]' in tsql
    odata = scaffold.crud("orders", columns, scaffold.Source("dataverse", "Sales CRM", "dataverse"))
    assert "create_orders" in odata and 'mode="update"' in odata
    with pytest.raises(scaffold.ScaffoldError, match="has list_orders already"):
        scaffold.crud("orders", columns, scaffold.Source("duckdb", "Sandbox"), taken=["list_orders"])
    with pytest.raises(scaffold.ScaffoldError, match="no column nope"):
        scaffold.crud("orders", columns, scaffold.Source("duckdb", "Sandbox"), key="nope")


def test_new_endpoint_from_a_table_runs_its_crud_set_on_the_mocks(live: int, tmp_path: Path) -> None:
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv), "name": "invoices"})
    # invoices as if read from a SQL Server connection: its mock speaks T-SQL.
    meta_path = folder / "sandbox" / "sandbox.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["tables"]["invoices"]["client"] = {
        "kind": "database",
        "connection": "Warehouse",
        "dialect": "sqlserver",
    }
    meta["tables"]["invoices"]["source"] = {
        "kind": "connection",
        "connection": "Warehouse",
        "place": {"schema": "dbo"},
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    one = _ask(port, "POST", "/local-api/scaffold", {"table": "orders", "key": "order_id"})
    assert one["added"] == ["list_orders", "get_orders", "create_orders", "update_orders", "delete_orders"]
    two = _ask(port, "POST", "/local-api/scaffold", {"table": "invoices", "key": "order_id"})
    by = {e["name"]: e for e in two["endpoints"]}
    assert by["list_invoices"]["data"] == ["Mock of Warehouse (sqlserver)"]
    assert by["list_orders"]["data"] == ["The sandbox (plain DuckDB)"]
    text = (folder / "API.py").read_text(encoding="utf-8")
    assert (
        'connection("Warehouse").read("dbo.invoices"' in text
        and 'connection("Sandbox").read("orders"' in text
    )
    assert _ask(port, "POST", "/local-api/run", {})["running"]

    def call(method: str, path: str, body: Any = None, query: dict[str, Any] | None = None) -> Any:
        return _ask(
            port,
            "POST",
            "/local-api/call",
            {"method": method, "path": path, "body": body, "query": query or {}},
        )

    for name in ("orders", "invoices"):
        page = call("GET", f"/{name}", query={"limit": 2, "offset": 1})
        assert [r["order_id"] for r in page["body"]] == [2, 3], name
        assert call("GET", f"/{name}/2")["body"]["region"] == "East"
        assert call("POST", f"/{name}", {"order_id": 9, "region": "North", "amount": 1.5})["status"] == 201
        assert call("PUT", f"/{name}/9", {"region": "South"})["body"]["region"] == "South"
        assert call("DELETE", f"/{name}/9")["status"] == 204
        assert call("DELETE", f"/{name}/9")["status"] == 404
    log = _ask(port, "GET", "/sandbox")["log"]
    assert log["invoices"] == {"inserted": 1, "updated": 1, "deleted": 1}
    _ask(port, "POST", "/local-api/stop", {})


def test_payload_shapes_flag_a_widget_whose_endpoint_answers_otherwise(tmp_path: Path) -> None:
    from tests.conftest import AUTH, make_client

    with make_client(tmp_path) as client:
        folder = tmp_path / "shop"
        assert client.post("/project/new", json={"path": str(folder)}, headers=AUTH).status_code == 200
        (folder / "API.py").write_text(API_PY, encoding="utf-8")
        canvas = {
            "format": 2,
            "pages": [
                {
                    "name": "Home",
                    "children": [
                        {
                            "id": "w1",
                            "kind": "widget",
                            "widget": "api_table",
                            "values": {"endpoint": "GET /orders/{region}", "path_values": {"region": "West"}},
                        },
                        {
                            "id": "w2",
                            "kind": "widget",
                            "widget": "api_table",
                            "values": {"endpoint": "GET /orders/one/{order_id}"},
                        },
                        {
                            "id": "w3",
                            "kind": "widget",
                            "widget": "api_metric",
                            "values": {
                                "endpoint": "GET /orders/one/{order_id}",
                                "field": "total",
                                "path_values": {"order_id": 1},
                            },
                        },
                        {
                            "id": "w4",
                            "kind": "widget",
                            "widget": "api_form",
                            "values": {"endpoint": "POST /orders", "fields": ["region", "colour"]},
                        },
                        {
                            "id": "w5",
                            "kind": "widget",
                            "widget": "api_button",
                            "values": {"endpoint": "GET /gone"},
                        },
                    ],
                }
            ],
        }
        (folder / "sales.canvas.json").write_text(json.dumps(canvas), encoding="utf-8")
        found = client.get("/local-api/shapes", headers=AUTH).json()
        by = {u["instance"]: u["problems"] for u in found["uses"]}
        assert by["w1"] == ["orders_in takes no limit and offset: api_table shows its first page only."]
        assert "answers Order" in by["w2"][0] and "gives no order_id" in by["w2"][-1]
        assert by["w3"] == ["one_order's answer has no field total (it has order_id, region, amount)."]
        assert by["w4"] == ["add_order's body has no field colour."]
        assert by["w5"] == ["API.py has no endpoint GET /gone."]
        assert not found["ok"]
        first = next(u for u in found["uses"] if u["instance"] == "w1")
        assert first["answers"]["fields"] == {"order_id": "int", "region": "str", "amount": "float"}
