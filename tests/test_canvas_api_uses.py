"""The canvases' uses of an API's endpoints (domain/canvas_wiring.py api_uses: what the local sandbox API's
Payload shapes read through the base's hooks.api_uses), on made-up canvases (craft review 2026-11-22)."""

from __future__ import annotations

from swissarmybench_streamlit.domain import canvas_wiring as wiring

CANVAS = {
    "pages": [
        {
            "id": "p1",
            "name": "Orders",
            "children": [
                {"kind": "widget", "id": "w1", "widget": "api_table", "values": {"endpoint": "GET /orders"}},
                {
                    "kind": "container",
                    "id": "c1",
                    "children": [
                        {
                            "kind": "widget",
                            "id": "w2",
                            "widget": "api_form",
                            "values": {},
                            "wires": {"submitted": {"actions": [{"do": "call", "endpoint": "POST /orders"}]}},
                        },
                        {"kind": "widget", "id": "w3", "widget": "metric", "values": {}},
                    ],
                },
            ],
        }
    ]
}


def test_each_endpoint_property_and_each_call_is_found_where_it_is() -> None:
    found = wiring.api_uses([("shop.canvas.json", CANVAS)])
    assert found == [
        {"canvas": "shop.canvas.json", "page": "Orders", "instance": "w1", "widget": "api_table",
         "values": {"endpoint": "GET /orders"}},
        {"canvas": "shop.canvas.json", "page": "Orders", "instance": "w2", "widget": "api_form",
         "event": "submitted", "action": {"do": "call", "endpoint": "POST /orders"}},
    ]  # fmt: skip


def test_a_file_that_is_not_a_canvas_names_nothing() -> None:
    assert wiring.api_uses([("broken.canvas.json", {"pages": [{"children": [{"id": "x"}]}]})]) == []
    assert wiring.api_uses([("other.canvas.json", {"no": "pages"})]) == []
