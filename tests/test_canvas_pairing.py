"""A widget dropped on the Canvas near a matching endpoint wires itself (the owner approved, 2026-11-21: "Each
pattern names its widget pairing; a widget dropped on the Canvas near a matching endpoint wires itself"):

  the pairing  is the pattern's data (domain/api_patterns.py), read through the base's local_api.paired()
  one match    the widget's endpoint property is set (or its In given the endpoint as its source), in the same
               change as the insert: one Undo takes both back; said once
  several      the endpoint over the same table as the nearest widget that already uses one; with none near,
               it is left for the user to pick, never guessed
  never        over a value the caller gave, or for a widget no pattern pairs with

Made-up data only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import canvas_wiring as wiring
from tests.conftest import AUTH, make_client
from tests.test_canvas_routes import command, ok, opened

ORDERS = "order_id,customer,region,amount\n1,Ada Fenn,North,120.5\n2,Bo Larch,East,80.0\n"
INVOICES = "invoice_id,payer,region,total\n7,Cy Moss,North,40.0\n8,Di Reed,South,200.0\n"


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    with make_client(tmp_path) as client:
        folder = tmp_path / "shop"
        ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
        for name, text in (("orders", ORDERS), ("invoices", INVOICES)):
            file = tmp_path / f"{name}.csv"
            file.write_text(text, encoding="utf-8")
            ok(client.post("/sandbox/tables", json={"from": "file", "path": str(file)}, headers=AUTH))
        yield client, folder


def scaffold(client: TestClient, table: str, pattern: str, **fields: Any) -> dict[str, Any]:
    body = {"table": table, "pattern": pattern, "fields": fields}
    return ok(client.post("/local-api/scaffold", json=body, headers=AUTH))


def node(state: dict[str, Any], wanted: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = []

    def look(children: list[dict[str, Any]]) -> None:
        for child in children:
            if child["id"] == wanted:
                found.append(child)
            look(child.get("children") or [])

    for page in state["model"]["pages"]:
        look(page["children"])
    return found[0]


def test_a_dropped_widget_wires_itself_to_the_endpoint_its_pattern_pairs_with(
    shop: tuple[TestClient, Path],
) -> None:
    client, folder = shop
    done = scaffold(client, "orders", "table")
    # The scaffold's answer says the pairing (the agent reads it); the base reads it from API.py's markers.
    assert {(p["widget"], p["endpoint"]) for p in done["paired"]} == {
        ("api_table", "GET /orders"),
        ("api_form", "POST /orders"),
    }
    canvas = opened(client, folder)["canvas"]
    # One endpoint matches an API table: wired as part of the insert, said once.
    first = ok(command(client, canvas, "insert_widget", widget="api_table"))
    assert node(first, first["made"])["values"] == {"endpoint": "GET /orders"}
    assert first["wired"]["endpoint"] == "GET /orders" and first["wired"]["as"] == "property"
    assert first["notes"] == [
        "api_table is wired to GET /orders: the table pattern over orders pairs with it. Change it in "
        "Properties."
    ]
    assert ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))["notes"] == []
    form = ok(command(client, canvas, "insert_widget", widget="api_form"))
    assert node(form, form["made"])["values"] == {"endpoint": "POST /orders"}
    # One Undo takes the widget and its wire back together.
    undone = ok(client.post(f"/streamlit/canvases/{canvas}/undo", headers=AUTH, json={}))
    assert [n for n in undone["model"]["pages"][0]["children"] if n["id"] == form["made"]] == []
    # A widget no pattern pairs with, and a value the caller gave, are left alone.
    plain = ok(command(client, canvas, "insert_widget", widget="metric"))
    assert "wired" not in plain and node(plain, plain["made"])["values"] == {}
    given = ok(
        command(client, canvas, "insert_widget", widget="api_table", values={"endpoint": "GET /orders/{key}"})
    )
    assert "wired" not in given

    # A Summary pairs with a chart's In: its source is the endpoint (the existing wiring).
    scaffold(client, "orders", "summary")
    chart = ok(command(client, canvas, "insert_widget", widget="bar_chart"))
    assert chart["wired"]["as"] == "in" and chart["wired"]["port"] == "table_name"
    assert node(chart, chart["made"])["wires"] == {"table_name": {"endpoint": "GET /orders/summary/region"}}
    assert chart["wiring"]["broken"] == []

    # Two tables' endpoints match: the one over the table its nearest neighbour already uses.
    scaffold(client, "invoices", "table")
    page_two = ok(command(client, canvas, "add_page", name="Invoices"))
    page = page_two["model"]["pages"][-1]["id"]
    alone = ok(command(client, canvas, "insert_widget", widget="api_table", page=page))
    assert "wired" not in alone  # nothing near uses an endpoint: left for the user, never guessed
    box = next(c["id"] for c in alone["model"]["pages"][-1]["children"] if c["kind"] == "container")
    ok(command(client, canvas, "set_values", id=alone["made"], values={"endpoint": "GET /invoices"}))
    near = ok(command(client, canvas, "insert_widget", widget="api_form", parent=box, page=page))
    assert node(near, near["made"])["values"] == {"endpoint": "POST /invoices"}
    # On the first page the nearest uses orders.
    first_page = near["model"]["pages"][0]
    home = next(c["id"] for c in first_page["children"] if c["kind"] == "container")
    back = ok(command(client, canvas, "insert_widget", widget="api_form", parent=home, page=first_page["id"]))
    assert node(back, back["made"])["values"] == {"endpoint": "POST /orders"}


def test_the_nearest_widget_decides_between_two_matching_endpoints() -> None:
    pairings = [
        {
            "endpoint": "GET /orders",
            "widget": "api_table",
            "port": "endpoint",
            "pattern": "table",
            "of": "orders",
        },
        {
            "endpoint": "GET /invoices",
            "widget": "api_table",
            "port": "endpoint",
            "pattern": "table",
            "of": "invoices",
        },
        {
            "endpoint": "POST /orders",
            "widget": "api_form",
            "port": "endpoint",
            "pattern": "table",
            "of": "orders",
        },
        {
            "endpoint": "POST /invoices",
            "widget": "api_form",
            "port": "endpoint",
            "pattern": "table",
            "of": "invoices",
        },
    ]

    def widget(name: str, kind: str, x: int, **values: Any) -> dict[str, Any]:
        return {
            "id": name,
            "kind": "widget",
            "widget": kind,
            "x": x,
            "y": 0,
            "w": 100,
            "h": 100,
            "values": values,
        }

    children = [
        widget("far", "api_table", 0, endpoint="GET /orders"),
        widget("near", "api_table", 600, endpoint="GET /invoices"),
        widget("new", "api_form", 720),
    ]
    box = {"id": "c1", "kind": "container", "x": 0, "y": 0, "w": 900, "h": 200, "children": children}
    canvas = {"pages": [{"id": "p1", "name": "One", "children": [box]}]}
    found = wiring.pair_for(canvas, "new", pairings, ["endpoint"], [])
    assert found is not None and found["endpoint"] == "POST /invoices"
    children[2]["x"] = 110
    found = wiring.pair_for(canvas, "new", pairings, ["endpoint"], [])
    assert found is not None and found["endpoint"] == "POST /orders"
    # Its endpoint already set, or a widget with no endpoint property: nothing.
    children[2]["values"] = {"endpoint": "POST /x"}
    assert wiring.pair_for(canvas, "new", pairings, ["endpoint"], []) is None
    children[2]["values"] = {}
    assert wiring.pair_for(canvas, "new", pairings, [], []) is None
    assert wiring.pair_for(canvas, "c1", pairings, ["endpoint"], []) is None
