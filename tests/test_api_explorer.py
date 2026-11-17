"""The APIs page over HTTP (services/api_explorer.py): the library's cards, search across two made-up APIs,
an operation's inputs and outputs, an authored call sent with its body edited in Structures, its answer
in Structures with its lineage, Open as grid keeping the chain, Run again, Save as a web call blade,
Return as table as the one gate to SQL, Refresh's diff then apply, and delete listing its references.
Made-up services on 127.0.0.1 (tests/api_standins.py)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from tests.api_standins import Service
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def add_two(client: TestClient, service: Service) -> None:
    ok(
        client.post(
            "/apis", json={"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}}, headers=AUTH
        )
    )
    form = {
        "title": "Shop",
        "base_url": service.url + "/v1",
        "endpoints": [{"path": "/products", "table": True}, {"path": "/regions", "parameters": "page"}],
    }
    ok(client.post("/apis", json={"form": form}, headers=AUTH))


def test_the_cards_and_an_operations_inputs_and_outputs(client: TestClient, service: Service) -> None:
    add_two(client, service)
    cards = ok(client.get("/apis", headers=AGENT))["apis"]
    assert [(c["name"], c["operations"], c["auth"]) for c in cards] == [
        ("Orders", 5, "none"),
        ("Shop", 2, "none"),
    ]
    assert cards[0]["source"]["kind"] == "address" and cards[1]["source"]["kind"] == "form"
    explored = ok(client.get("/apis/Orders", headers=AGENT))
    assert [s["name"] for s in explored["schemas"]] == ["Order"]
    assert set(explored["schemas"][0]["used_by"]) >= {"list_orders", "create_order"}
    one = ok(client.get("/apis/Orders?operation=create_order", headers=AGENT))["operation"]
    assert one["body"]["required"] and one["body"]["example"] == {
        "order_id": 0,
        "amount": 0.0,
        "status": "open",
    }
    assert one["responses"][0]["status"] == "201" and "amount" in one["responses"][0]["schema"]
    get = ok(client.get("/apis/Orders?operation=get_order", headers=AGENT))["operation"]
    assert [(p["name"], p["in"], p["required"]) for p in get["parameters"]] == [("order_id", "path", True)]
    # The APIs are not on the Connections page (the owner, 2026-11-17): the APIs page is their home. The
    # list still has the API blade, marked as an API's (the page leaves those out), so SQL names its tables.
    listed = ok(client.get("/connections", headers=AUTH))["connections"]
    assert {c["tables_kind"] for c in listed} == {"api"}


def test_search_runs_across_every_api_and_operation(client: TestClient, service: Service) -> None:
    add_two(client, service)
    found = ok(client.get("/apis/search?q=orders", headers=AGENT))["results"]
    assert {(r["api"], r["operation"]) for r in found} >= {("Orders", "list_orders"), ("Orders", "get_order")}
    regions = ok(client.get("/apis/search?q=regions", headers=AGENT))["results"]
    assert {r["api"] for r in regions} == {"Orders", "Shop"}
    by_param = ok(client.get("/apis/search?q=pagetoken", headers=AGENT))["results"]
    assert [(r["operation"], r["matched"]) for r in by_param] == [
        ("list_orders", {"parameter": ["pagetoken"]})
    ]
    by_field = ok(client.get("/apis/search?q=amount post", headers=AGENT))["results"]
    assert [r["operation"] for r in by_field] == ["create_order"]


def test_an_authored_call_opens_in_structures_with_its_lineage(client: TestClient, service: Service) -> None:
    add_two(client, service)
    op = ok(client.get("/apis/Orders?operation=create_order", headers=AUTH))["operation"]
    # The body, in Structures: seeded from the example, edited in the tree (a step), then sent.
    draft = ok(
        client.post("/structures", json={"value": op["body"]["example"], "name": "draft"}, headers=AUTH)
    )
    step = {"op": "set", "path": "$.amount", "value": 42.5}
    edited = ok(client.post(f"/structures/{draft['id']}/steps", json=step, headers=AUTH))
    body = edited["value"]
    sent = ok(client.post("/apis/Orders/calls/create_order", json={"body": body}, headers=AUTH))
    assert sent["status"] == 201 and sent["ms"] >= 0 and "content-type" in sent["headers"]
    answer = ok(client.get(f"/structures/{sent['structure']}", headers=AUTH))
    assert answer["value"]["amount"] == 42.5 and answer["origin"]["kind"] == "api"
    assert answer["origin"]["body"] == body and answer["origin"]["operation"] == "create_order"

    # A list: its answer, a step, Open as grid; the lineage is the call, the structure, the step, the grid.
    listed = ok(
        client.post("/apis/Orders/calls/list_orders", json={"inputs": {"status": "open"}}, headers=AUTH)
    )
    assert listed["suggest_table"]["records"] == "$.items"  # a quiet suggestion, never switched on by itself
    sid = listed["structure"]
    ok(
        client.post(
            f"/structures/{sid}/steps",
            json={"op": "sort", "path": "$.items", "field": "amount"},
            headers=AUTH,
        )
    )
    grid = ok(
        client.post(f"/structures/{sid}/grid", json={"path": "$.items", "name": "open_orders"}, headers=AUTH)
    )
    assert grid["rows"] == 10
    chain = ok(client.get(f"/structures/{sid}/lineage", headers=AGENT))
    kinds = [(n["kind"], n["label"]) for n in chain["nodes"]]
    assert kinds[0] == ("source", "GET /orders") and kinds[1][0] == "text"
    assert ("step", "Sort $.items by amount") in kinds and ("table", "open_orders") in kinds
    assert "flowchart TD" in chain["mermaid"] and chain["origin"]["inputs"] == {"query": {"status": "open"}}
    # Run again: the same call, the steps kept.
    again = ok(client.post(f"/structures/{sid}/run-again", json={}, headers=AUTH))
    assert again["steps"][0]["op"] == "sort" and len(again["value"]["items"]) == 10


def test_save_as_a_web_call_and_return_as_table_is_the_one_gate(client: TestClient, service: Service) -> None:
    add_two(client, service)
    saved = ok(client.put("/apis/Orders/calls/get_order", json={"inputs": {"order_id": 4}}, headers=AUTH))
    assert saved["blade"] == "Orders.get_order" and saved["sql_name"] is None
    blade = ok(client.get("/blades/Orders.get_order", headers=AUTH))
    assert '"order_id": 4' in blade["code"] and blade["web_call"]["as_table"] is False
    # Off: not a table. On, from a real answer's list (Return as table... on the Structures result).
    listed = ok(client.post("/apis/Orders/calls/list_orders", json={}, headers=AUTH))
    on = ok(
        client.put(
            "/apis/Orders/calls/list_orders",
            json={"as_table": True, "structure": listed["structure"], "at": "$"},
            headers=AUTH,
        )
    )
    assert on["web_call"]["records"] == "$.items" and on["sql_name"] == "[Orders].list_orders"
    tables = ok(client.post("/connections/Orders/tables", json={}, headers=AUTH))["tables"]
    assert [t["table"] for t in tables] == ["list_orders"]
    # A required input with no value: the table says which.
    ok(client.put("/apis/Orders/calls/get_order", json={"as_table": True, "inputs": {}}, headers=AUTH))
    tables = ok(client.post("/connections/Orders/tables", json={}, headers=AUTH))["tables"]
    needs = next(t for t in tables if t["table"] == "get_order")
    assert needs["columns"][0]["column"] == "(needs order_id (path))"


def test_refresh_shows_what_changed_then_applies_it(client: TestClient, service: Service) -> None:
    add_two(client, service)
    original = service.openapi
    changed = original()
    del changed["paths"]["/regions"]
    changed["paths"]["/orders"]["get"]["parameters"].append(
        {"name": "since", "in": "query", "schema": {"type": "string"}}
    )
    changed["paths"]["/stores"] = {
        "get": {"operationId": "listStores", "responses": {"200": {"description": "ok"}}}
    }
    service.openapi = lambda: changed  # type: ignore[method-assign]
    shown = ok(client.post("/apis/Orders/refresh", json={}, headers=AGENT))["diff"]
    assert [a["id"] for a in shown["added"]] == ["list_stores"] and [r["id"] for r in shown["removed"]] == [
        "list_regions"
    ]
    assert (
        shown["changed"][0]["id"] == "list_orders"
        and "parameter since (query) added" in shown["changed"][0]["changes"]
    )
    assert ok(client.get("/apis/Orders", headers=AUTH))["operations"][-1]["id"] == "list_regions"  # not yet
    ok(client.post("/apis/Orders/refresh/apply", json={}, headers=AGENT))
    ids = [o["id"] for o in ok(client.get("/apis/Orders", headers=AUTH))["operations"]]
    assert "list_stores" in ids and "list_regions" not in ids
    assert client.get("/blades/Orders.list_regions", headers=AUTH).status_code == 404
    shop = client.post("/apis/Shop/refresh", json={}, headers=AUTH)
    assert shop.status_code == 400 and "form" in shop.text  # made with the form: nothing to read again


def test_delete_lists_the_code_that_uses_it_first(tmp_path: Path, service: Service) -> None:
    with make_client(tmp_path) as client:
        (tmp_path / "work").mkdir()
        state = ok(
            client.post("/project/new", json={"path": str(tmp_path / "work" / "shop.sab")}, headers=AUTH)
        )
        add_two(client, service)
        folder = Path(state["project"]["folder"])
        cell = notebooks.Cell(
            "code", 'import swissarmybench as sab\norders = sab.read("Orders", "list_orders")'
        )
        (folder / "analysis.ipynb").write_text(notebooks.write_notebook([cell]), encoding="utf-8")
        asked = ok(client.post("/apis/Orders/delete", json={}, headers=AUTH))
        assert asked["deleted"] is False and [r["title"] for r in asked["references"]] == ["analysis.ipynb"]
        library = tmp_path / "state" / "library" / "apis" / "Orders"
        assert library.is_dir()  # APIs are this computer's, never inside the project
        assert not list(folder.rglob("API_Orders.py"))
        done = ok(client.post("/apis/Orders/delete", json={"confirm": True}, headers=AUTH))
        assert done["deleted"] and not library.exists()
        assert [c["name"] for c in ok(client.get("/apis", headers=AUTH))["apis"]] == ["Shop"]
        assert client.get("/blades/Orders.list_orders", headers=AUTH).status_code == 404


def test_rename_renames_the_blades_and_their_calls(client: TestClient, service: Service) -> None:
    add_two(client, service)
    done = ok(client.put("/apis/Shop/name", json={"name": "Store"}, headers=AUTH))
    assert done["name"] == "Store"
    assert [c["name"] for c in ok(client.get("/apis", headers=AUTH))["apis"]] == ["Orders", "Store"]
    blade = ok(client.get("/blades/Store.get_products", headers=AUTH))
    assert 'sab.blade("Store")' in blade["code"] and blade["web_call"]["api"] == "Store"
    assert json.loads(json.dumps(done))["was"] == "Shop"
