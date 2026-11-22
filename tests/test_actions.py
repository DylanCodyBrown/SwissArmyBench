"""Every API's actions through api_adapter in the app (services/actions.py; Plans/api-adapter.plan.md), over
HTTP on a live server: a library API added from its specification (tests/api_standins.py, made up)
and the project's local sandbox API. Run through the API blade's child process; the shape kept in the library
(types only, never a value); a drift said once; discover on the user's Allow, once; a write by the agent waits
for Allow; Build's cell and function; sab.run from Python. Every row is made up."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.api_standins import Service
from tests.conftest import TOKEN
from tests.fake_keyring import memory_keyring
from tests.live_server import running


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        info = tmp_path / "server.json"
        info.write_text(json.dumps({"port": port, "token": TOKEN}))
        monkeypatch.setenv("SWISSARMYBENCH_INFO", str(info))
        monkeypatch.setenv("SWISSARMYBENCH_OPEN", "0")
        yield port


@pytest.fixture
def service() -> Iterator[Service]:
    running_service = Service().start()
    yield running_service
    running_service.stop()


def ask(port: int, method: str, path: str, body: Any = None, agent: bool = False) -> Any:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers=headers | ({"X-Actor": "agent"} if agent else {}),
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:  # noqa: S310 (127.0.0.1)
            return json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as failed:
        raise AssertionError(f"{failed.code}: {failed.read().decode()}") from None


def answer_next(port: int, allow: bool) -> str:
    """The user's answer to the one approval waiting: its words."""
    for _ in range(400):
        pending = ask(port, "GET", "/agent/approvals")["pending"]
        if pending:
            ask(port, "POST", f"/agent/approvals/{pending[0]['id']}", {"approve": allow})
            return str(pending[0]["detail"])
        time.sleep(0.05)
    raise AssertionError("no approval was asked for")


def in_background(call: Any) -> tuple[threading.Thread, dict[str, Any]]:
    out: dict[str, Any] = {}

    def go() -> None:
        try:
            out["answer"] = call()
        except AssertionError as failed:
            out["error"] = str(failed)

    thread = threading.Thread(target=go)
    thread.start()
    return thread, out


def library(tmp_path: Path) -> Path:
    return tmp_path / "state" / "library" / "apis"


def add_orders(port: int, service: Service) -> None:
    ask(port, "POST", "/apis", {"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}})


def test_a_library_apis_actions_run_through_api_adapter_and_keep_its_shape(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    listed = ask(live, "GET", "/actions")["apis"]
    orders = next(a for a in listed if a["api"] == "Orders")
    names = {a["name"]: a for a in orders["actions"]}
    assert set(names) == {"list_orders", "create_order", "get_order", "list_clients", "list_regions"}
    assert names["list_orders"]["learned"] is False and names["list_orders"]["kind"] == "records"  # declared
    assert names["create_order"]["writes"] and names["create_order"]["maps_to"] == ["form"]
    done = ask(
        live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders", "inputs": {"status": "open"}}
    )
    assert done["ok"] and done["kind"] == "records" and len(done["records"]) == 17
    assert (
        done["paging"]["by"] == "cursor"
        and done["paging"]["pages"] == 2
        and done["shape"]["envelope"] == "$.items"
    )
    kept = library(tmp_path) / "Orders" / "shapes" / "list_orders.json"
    text = kept.read_text(encoding="utf-8")
    shape = json.loads(text)
    assert set(shape["returned"]["fields"]) == {"order_id", "amount", "status"}
    assert shape["sent"]["fields"] == {"query.status": {"type": "text", "format": "", "empty": False}}
    assert (
        "shipped" not in text and "open" not in text.replace('"open"', "") and "12.5" not in text
    )  # no value
    described = ask(live, "GET", "/actions/Orders/list_orders")
    assert described["contract"]["learned"] and described["last"]["records"] == 17
    again = ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    assert again["ok"] and kept.read_text(encoding="utf-8") == text  # the same shape: the same bytes
    one = ask(
        live, "POST", "/actions/run", {"api": "Orders", "action": "get_order", "inputs": {"order_id": 3}}
    )
    assert one["kind"] == "record" and one["record"]["order_id"] == 3
    refused = ask(live, "POST", "/actions/run", {"api": "Orders", "action": "get_order", "inputs": {}})
    assert not refused["ok"] and refused["error"]["error"] == "order_id (path) is required."


def test_a_drift_is_said_once_and_a_required_field_fails_the_call(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    first = ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    assert first["ok"]
    kept = library(tmp_path) / "Orders" / "shapes" / "list_orders.json"
    shape = json.loads(kept.read_text(encoding="utf-8"))
    shape["returned"]["fields"]["region"] = {
        "type": "text",
        "format": "",
        "empty": False,
    }  # as an older API had it
    shape["returned"]["fingerprint"] = "older"
    kept.write_text(json.dumps(shape), encoding="utf-8")
    drifted = ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    assert drifted["ok"] and drifted["shape"]["drift"]["missing"] == ["region"]
    assert drifted["records"][0]["region"] is None and drifted["shape"]["marks"]["region"] == "missing"
    now = json.loads(kept.read_text(encoding="utf-8"))
    assert "region" not in now["returned"]["fields"] and now["change"]["missing"] == ["region"]
    contract = ask(live, "GET", "/actions/Orders/list_orders")["contract"]
    assert contract["drift"].startswith("1 field missing since ")
    kept.write_text(json.dumps(shape), encoding="utf-8")
    required = ask(
        live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders", "required": ["region"]}
    )
    assert not required["ok"] and required["error"]["where"] == "region"


def test_discover_asks_once_probes_reads_only_and_keeps_shapes(
    live: int, service: Service, tmp_path: Path
) -> None:
    add_orders(live, service)
    thread, out = in_background(lambda: ask(live, "POST", "/actions/discover", {"api": "Orders"}, agent=True))
    words = answer_next(live, False)
    thread.join(60)
    assert "read-only" in words and "declined" in out["error"]
    assert not (library(tmp_path) / "Orders" / "shapes").exists()  # nothing was called
    before = len(service.seen)
    thread, out = in_background(lambda: ask(live, "POST", "/actions/discover", {"api": "Orders"}, agent=True))
    answer_next(live, True)
    thread.join(120)
    found = out["answer"]
    called = service.seen[before:]
    assert {c["method"] for c in called} == {"GET"} and found["calls"] == 4
    assert found["skipped"] == {"create_order": "it writes: learned from the specification"}
    assert {"master": "list_orders", "detail": "get_order", "by": "order_id", "input": "order_id"} in found[
        "pairs"
    ]
    assert found["contracts"]["get_order"]["learned"] and found["contracts"]["get_order"]["maps_to"] == [
        "detail",
        "form",
    ]
    files = sorted(p.name for p in (library(tmp_path) / "Orders" / "shapes").iterdir())
    assert files == ["get_order.json", "list_clients.json", "list_orders.json", "list_regions.json"]
    # Allowed once: the second discovery this session asks nothing.
    again = ask(live, "POST", "/actions/discover", {"api": "Orders"}, agent=True)
    assert again["calls"] == 4


def test_a_write_by_the_agent_waits_for_allow(live: int, service: Service) -> None:
    add_orders(live, service)
    body = {
        "api": "Orders",
        "action": "create_order",
        "inputs": {"order_id": 0, "amount": 4.5, "status": "open"},
    }
    thread, out = in_background(lambda: ask(live, "POST", "/actions/run", body, agent=True))
    answer_next(live, False)
    thread.join(60)
    assert "declined" in out["error"] and not [s for s in service.seen if s["method"] == "POST"]
    thread, out = in_background(lambda: ask(live, "POST", "/actions/run", body, agent=True))
    answer_next(live, True)
    thread.join(60)
    assert out["answer"]["status"] == 201 and out["answer"]["record"]["amount"] == 4.5
    mine = ask(live, "POST", "/actions/run", body)  # the user's own: no question
    assert mine["status"] == 201


def test_build_a_cell_and_a_function_and_sab_run(live: int, service: Service) -> None:
    add_orders(live, service)
    ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    cell = ask(
        live,
        "POST",
        "/actions/build",
        {"api": "Orders", "action": "list_orders", "as": "cell", "inputs": {"status": "open"}},
    )
    assert 'answer = sab.run("Orders", "list_orders", {"status": "open"})' in cell["code"]
    assert "list_orders = sab.records(answer)" in cell["code"]
    function = ask(live, "POST", "/actions/build", {"api": "Orders", "action": "get_order", "as": "function"})
    assert "def get_order(order_id):" in function["code"] and 'return answer["record"]' in function["code"]
    import swissarmybench as sab

    answer = sab.run("Orders", "list_orders", {"status": "shipped"})
    table = sab.records(answer)
    assert table.num_rows == 8 and table.column_names == ["order_id", "amount", "status"]
    namespace: dict[str, Any] = {}
    exec(function["code"], namespace)  # noqa: S102 (the code Build made, over made-up orders)
    assert namespace["get_order"](5)["order_id"] == 5


def test_the_local_sandbox_apis_endpoints_are_actions_too(live: int, tmp_path: Path) -> None:
    from tests.test_local_api import API_PY, ORDERS

    folder = tmp_path / "shop"
    ask(live, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    ask(live, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    (folder / "API.py").write_text(API_PY, encoding="utf-8")
    ask(live, "POST", "/local-api/run", {})
    listed = ask(live, "GET", "/actions?api=local")["apis"][0]
    assert listed["local"] and {a["name"] for a in listed["actions"]} >= {
        "orders_in",
        "add_order",
        "one_order",
    }
    west = ask(
        live, "POST", "/actions/run", {"api": "local", "action": "orders_in", "inputs": {"region": "West"}}
    )
    assert west["ok"] and [r["order_id"] for r in west["records"]] == [1, 3]
    kept = folder / ".sab" / "api-shapes" / "orders_in.json"
    assert "West" not in kept.read_text(encoding="utf-8")
    missing = ask(
        live, "POST", "/actions/run", {"api": "local", "action": "one_order", "inputs": {"order_id": 99}}
    )
    assert missing["status"] == 404 and missing["error"]["details"] == "No order 99."
    ask(live, "POST", "/local-api/stop", {})


def test_build_a_widget_on_the_projects_canvas(live: int, service: Service, tmp_path: Path) -> None:
    add_orders(live, service)
    ask(live, "POST", "/project/new", {"path": str(tmp_path / "shop"), "type": "streamlit"})
    if not ask(live, "GET", "/streamlit/canvases")["canvases"]:
        ask(live, "POST", "/streamlit/canvases", {"name": "app"})
    ask(live, "POST", "/actions/run", {"api": "Orders", "action": "list_orders"})
    built = ask(live, "POST", "/actions/build", {"api": "Orders", "action": "list_orders", "as": "widget"})
    assert built["widget"] == "data_table" and built["id"]
    canvas = json.dumps(ask(live, "GET", f"/streamlit/canvases/{built['canvas_id']}"))
    assert "[Orders].list_orders" in canvas
    with pytest.raises(AssertionError, match="no widget"):
        ask(live, "POST", "/actions/build", {"api": "Orders", "action": "get_order", "as": "widget"})
