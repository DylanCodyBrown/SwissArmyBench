"""Write rows with this call (domain/write_rows.py, services/api_explorer.py): a table's rows sent through a
POST, mapped by name and nested fields, a required field unmapped named, a dry run that sends nothing,
per-row and batched sends, a 429 paced by Retry-After, the results table with its errors, Retry the failed
rows, and the blade's header round trip. Made-up orders on 127.0.0.1 (tests/api_standins.py)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import blades, write_rows
from tests.api_standins import Service
from tests.conftest import AGENT, AUTH, push
from tests.fake_keyring import memory_keyring

TREE = {"order_id": "integer", "amount*": "number", "customer*": {"name*": "string", "region": "string"}}
PARAMS = [
    {"name": "dry_run", "in": "query", "required": False},
    {"name": "x-tag", "in": "header", "required": True},
]


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


def test_columns_map_by_name_and_into_nested_fields() -> None:
    mapping = write_rows.auto_map(["Amount", "customer_name", "REGION", "X_Tag", "note"], TREE, PARAMS)
    assert mapping == {
        "header.x-tag": {"column": "X_Tag"},
        "body.amount": {"column": "Amount"},
        "body.customer.name": {"column": "customer_name"},
        "body.customer.region": {"column": "REGION"},
    }
    inputs, body = write_rows.request_of(
        {"Amount": 5, "customer_name": "Acme", "REGION": "N", "X_Tag": "t"}, mapping
    )
    assert body == {"amount": 5, "customer": {"name": "Acme", "region": "N"}} and inputs == {
        "header": {"x-tag": "t"}
    }
    lacking = write_rows.missing({"body.amount": {"column": "a"}}, TREE, PARAMS)
    assert lacking == ["header.x-tag", "body.customer.name"]
    with pytest.raises(write_rows.WriteError, match="no such column"):
        write_rows.check_mapping({"body.amount": {"column": "nope"}}, ["a"])


def test_a_dry_run_and_batches_are_planned_without_sending() -> None:
    rows = [{"a": n} for n in range(7)]
    mapping: dict[str, dict[str, Any]] = {"body.amount": {"column": "a"}, "query.dry_run": {"value": True}}
    one = write_rows.dry_run(rows, mapping, write_rows.check_settings({}))
    assert (one["rows"], one["calls"], len(one["first"])) == (7, 7, 3)
    assert one["first"][0] == {"inputs": {"query": {"dry_run": True}}, "body": {"amount": 0}}
    batched = write_rows.dry_run(rows, mapping, write_rows.check_settings({"batch": True, "batch_size": 3}))
    assert batched["calls"] == 3 and batched["first"][0]["body"] == [
        {"amount": 0},
        {"amount": 1},
        {"amount": 2},
    ]


def test_the_blades_header_round_trips_the_mapping() -> None:
    call = {"api": "Orders", "operation": "create_order", "method": "POST", "path": "/orders",
            "mode": "write rows",
            "mapping": {"body.amount": {"column": "amount"}, "query.dry": {"value": True}}, "batch": True,
            "batch_size": 50, "key_columns": ["ref"]}  # fmt: skip
    blade = blades.parse_blade({"name": "Orders.write_create_order", "kind": "other", "code": "result = 1",
                                "web_call": call})  # fmt: skip
    text = blades.write_blade(blade.to_json())
    assert (
        'mode = "write rows"' in text
        and '"body.amount" = "column amount"' in text
        and '"query.dry" = "value true"' in text
    )
    back = blades.parse_blade(blades.read_blade(text))
    assert back.web_call["mapping"] == call["mapping"] and back.web_call["batch_size"] == 50
    assert back.web_call["key_columns"] == ["ref"] and back.web_call["mode"] == "write rows"


def add(client: TestClient, service: Service) -> None:
    ok(
        client.post(
            "/apis", json={"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}}, headers=AUTH
        )
    )
    table = pa.table(
        {"ref": ["a", "b", "c"], "Amount": [10.5, -1.0, 7.0], "STATUS": ["open", "open", "shipped"]}
    )
    assert push(client, "to_send", table).status_code == 200


def test_rows_are_written_per_row_then_the_failed_ones_again(client: TestClient, service: Service) -> None:
    add(client, service)
    where = "/apis/Orders/calls/create_order/write"
    dry = ok(client.post(where, json={"table": "to_send", "key_columns": ["ref"]}, headers=AGENT))
    assert dry["dry_run"] and (dry["rows"], dry["calls"]) == (3, 3) and dry["missing"] == []
    assert dry["mapping"] == {"body.amount": {"column": "Amount"}, "body.status": {"column": "STATUS"}}
    assert dry["first"][0]["body"] == {"amount": 10.5, "status": "open"}
    assert service.posted == []  # a dry run sends nothing
    sent = ok(client.post(where, json={"table": "to_send", "key_columns": ["ref"], "dry_run": False,
                                       "response_field": "order_id"}, headers=AUTH))  # fmt: skip
    assert (sent["written"], sent["failed"], sent["calls"]) == (2, 1, 3)
    results = ok(client.get(f"/structures/{sent['structure']}", headers=AUTH))
    rows = results["value"]
    assert [(r["ref"], r["status"]) for r in rows] == [("a", 201), ("b", 422), ("c", 201)]
    assert rows[0]["order_id"] == 1000 and "amount must be positive" in rows[1]["error"]
    grid = ok(client.get(f"/grids/{sent['grid']}", headers=AUTH))
    assert grid["row_count"] == 3
    chain = ok(client.get(f"/structures/{sent['structure']}/lineage", headers=AUTH))
    assert [n["label"] for n in chain["nodes"]][:2] == ["to_send", "POST /orders"]
    # Retry the failed rows: only b is sent again.
    before = len(service.posted)
    again = ok(client.post(where, json={"retry": sent["structure"], "dry_run": False}, headers=AUTH))
    assert again["rows"] == 1 and len(service.posted) == before + 1
    redo = ok(client.get(f"/structures/{again['structure']}", headers=AUTH))["value"]
    assert [r["row"] for r in redo] == [1]


def test_a_batch_is_one_call_and_a_429_is_paced(client: TestClient, service: Service) -> None:
    add(client, service)
    service.throttle = 1
    where = "/apis/Orders/calls/create_order/write"
    sent = ok(client.post(where, json={"table": "to_send", "batch": True, "dry_run": False}, headers=AUTH))
    assert sent["calls"] == 1 and sent["written"] == 3
    assert len(service.posted) == 2 and service.posted[1] - service.posted[0] >= 0.9  # Retry-After: 1
    results = ok(client.get(f"/structures/{sent['structure']}", headers=AUTH))["value"]
    assert [r["id"] for r in results] == [None, None, None] or [r["status"] for r in results] == [201] * 3


def test_a_required_field_unmapped_blocks_the_send(client: TestClient, service: Service) -> None:
    add(client, service)
    doc = service.openapi()
    body = doc["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]
    body["schema"] = {
        "type": "object",
        "required": ["customer"],
        "properties": {"customer": {"type": "string"}},
    }
    service.openapi = lambda: doc  # type: ignore[method-assign]
    ok(
        client.post(
            "/apis", json={"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}}, headers=AUTH
        )
    )
    where = "/apis/Orders/calls/create_order/write"
    dry = ok(client.post(where, json={"table": "to_send"}, headers=AUTH))
    assert dry["missing"] == ["body.customer"]
    refused = client.post(where, json={"table": "to_send", "dry_run": False}, headers=AUTH)
    assert refused.status_code == 400 and "body.customer" in refused.text and service.posted == []
    mapped = {"body.customer": {"column": "ref"}}
    sent = ok(
        client.post(where, json={"table": "to_send", "mapping": mapped, "dry_run": False}, headers=AUTH)
    )
    assert sent["written"] == 3


def test_saved_as_a_write_rows_blade(client: TestClient, service: Service) -> None:
    add(client, service)
    mapping = {"body.amount": {"column": "Amount"}}
    where = "/apis/Orders/calls/create_order/write"
    saved = ok(client.put(where, json={"mapping": mapping, "table": "to_send"},
                          headers=AUTH))  # fmt: skip
    blade = ok(client.get(f"/blades/{saved['blade']}", headers=AUTH))
    assert blade["web_call"]["mode"] == "write rows" and "dry_run = True" in blade["code"]
    assert "table = to_send" in blade["code"] and json.dumps("Orders") in blade["code"]
