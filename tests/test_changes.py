"""The change log's rules (domain/changes.py; Plans/changes.plan.md): one event per change, its structural
difference by names (columns with their types), fingerprints before and after, plain words; the lines of
.sab/changes.jsonl; the agent's last, history, since and search. Never a value. Made-up data only."""

from __future__ import annotations

import json

import pytest

from swissarmybench.domain import changes as rules


def test_a_tables_columns_and_steps_changed() -> None:
    before = {"columns": {"id": "BIGINT", "region": "VARCHAR", "amount": "DOUBLE"}, "steps": ["filter"]}
    after = {
        "columns": {"id": "BIGINT", "amount": "DECIMAL(10,2)", "segment": "VARCHAR"},
        "steps": ["filter", "sort"],
    }
    made = rules.change("table", "orders", before, after)
    assert made is not None
    assert made["object"] == {"kind": "table", "name": "orders"}
    assert made["diff"]["columns"] == {
        "added": ["segment"],
        "removed": ["region"],
        "changed": ["amount"],
        "types": {"amount": {"was": "DOUBLE", "now": "DECIMAL(10,2)"}},
    }
    assert made["diff"]["steps"] == {"added": ["2 sort"], "removed": [], "changed": []}
    assert made["words"] == (
        "orders: columns added segment; removed region; retyped amount (DOUBLE to DECIMAL(10,2)); "
        "steps added 2 sort"
    )
    assert made["before"] != made["after"] and len(made["before"]) == 12


def test_nothing_changed_is_no_event() -> None:
    same = {"settings": {"host": "db.example.test", "port": 5432}}
    assert rules.change("connection", "Warehouse", same, dict(same)) is None


def test_a_settings_value_never_comes_along() -> None:
    made = rules.change(
        "connection",
        "Warehouse",
        {"settings": {"host": "db-one.example.test", "user": "sam"}},
        {"settings": {"host": "db-two.example.test", "user": "sam", "sslmode": "require"}},
    )
    assert made is not None
    text = json.dumps(made)
    assert "db-one" not in text and "db-two" not in text and "require" not in text and "sam" not in text
    assert made["diff"]["settings"] == {"added": ["sslmode"], "removed": [], "changed": ["host"]}
    assert made["words"] == "Warehouse: settings added sslmode; changed host"


def test_something_new_or_gone_says_so_in_plain_words() -> None:
    """The sweep, 2026-11-22: a table opened for the first time read "orders: columns added amount,
    customer_id, order_id, placed; source added connection, kind, where" (a new connection listed its
    twenty header fields). New and gone are said plainly; the difference still names every part."""
    shape = {"columns": {"order_id": "BIGINT", "amount": "DOUBLE"}, "source": {"kind": "connection"}}
    made = rules.change("table", "orders", None, shape)
    assert made is not None and made["words"] == "Added the table orders (2 columns)"
    assert made["diff"]["columns"]["added"] == ["amount", "order_id"]
    gone = rules.change("table", "orders", shape, None)
    assert gone is not None and gone["words"] == "Removed the table orders"
    api = rules.change("api", "Shop", None, {"actions": {"list_orders": "GET /orders"}})
    assert api is not None and api["words"] == "Added the API Shop"
    one = rules.change("table", "totals", None, {"columns": {"total": "DOUBLE"}})
    assert one is not None and one["words"] == "Added the table totals (1 column)"


def test_given_words_win_and_a_kind_is_checked() -> None:
    made = rules.change(
        "endpoint", "Shop list_orders", None, {"fields": {"id": "integer"}}, "Its answer gained id."
    )
    assert made is not None and made["words"] == "Its answer gained id." and made["before"] == ""
    with pytest.raises(rules.ChangesError):
        rules.change("planet", "Mars", {}, {"a": {"b": 1}})


def test_the_lines_and_the_agents_views() -> None:
    events = []
    for at, who, kind, name in (
        ("2026-11-22T09:00:00", "user", "table", "orders"),
        ("2026-11-22T09:05:00", "agent", "connection", "Warehouse"),
        ("2026-11-22T09:10:00", "app", "endpoint", "Shop list_orders"),
        ("2026-11-22T09:15:00", "agent", "table", "orders"),
    ):
        made = rules.change(kind, name, {"x": {"a": 1}}, {"x": {"a": 2}})
        assert made is not None
        events.append(rules.stamped(made, at, who))
    text = "".join(rules.line(e) for e in events) + "not json\n"
    read = rules.parse(text)
    assert read == events
    assert rules.view(read, "last", obj="table:orders")["change"]["at"] == "2026-11-22T09:15:00"
    assert rules.view(read, "last", obj="orders")["change"]["who"] == "agent"  # a name alone: any kind
    assert rules.view(read, "last", obj="nothing")["change"] is None
    assert [e["at"] for e in rules.view(read, "history", obj="table:orders", n=5)["changes"]] == [
        "2026-11-22T09:15:00",
        "2026-11-22T09:00:00",
    ]
    assert len(rules.view(read, "since", since="2026-11-22T09:05:00")["changes"]) == 2
    assert [e["who"] for e in rules.view(read, "search", who="agent")["changes"]] == ["agent", "agent"]
    assert len(rules.view(read, "search", kind="endpoint")["changes"]) == 1
    with pytest.raises(rules.ChangesError):
        rules.view(read, "history")
    with pytest.raises(rules.ChangesError):
        rules.view(read, "everything")


def test_a_scripts_definitions_and_the_rest_of_its_module() -> None:
    before = rules.document_shape("script", "LIMIT = 10\n\ndef load():\n    return 1\n")
    after = rules.document_shape(
        "script", "LIMIT = 20\n\ndef load():\n    return 1\n\ndef save():\n    pass\n"
    )
    made = rules.change("script", "etl.py", before, after)
    assert made is not None
    assert made["diff"]["definitions"]["added"] == ["save"] and made["diff"]["code"]["changed"] == ["module"]
    assert "20" not in json.dumps(made)


def test_a_canvas_page_and_api_pys_endpoints_as_the_log_names_them() -> None:
    from swissarmybench.domain import local_api
    from swissarmybench.services.local_api import _endpoint_shapes
    from swissarmybench_streamlit.services.canvas import _pages

    widget = {"id": "w1", "kind": "widget", "widget": "kpi_card", "values": {"title": "Revenue"}}
    canvas = {
        "pages": [
            {
                "id": "p1",
                "name": "Overview",
                "children": [{"id": "c1", "kind": "container", "children": [widget]}],
            }
        ]
    }
    pages = _pages(canvas)
    assert sorted(pages["Overview"]["items"]) == ["c1 container", "w1 kpi_card"]
    endpoint = (
        '\n\n@endpoint("GET", "/orders/{region}")\ndef orders_in(region: str) -> list[dict]:\n    return []\n'
    )
    shapes = _endpoint_shapes(local_api.scaffold("Orders") + endpoint)
    assert shapes is not None and list(shapes) == ["GET /orders/{region}"]
    assert all("line" not in s["endpoint"] for s in shapes.values())
