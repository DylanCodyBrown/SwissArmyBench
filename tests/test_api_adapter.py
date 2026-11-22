"""api_adapter.py (Plans/api-adapter.plan.md; design principle 12b): any payload in, one envelope out.
Recorded made-up payloads of every format, envelope and paging style, every drift case, the inputs checked
first, retries, the specification as the front door, the kept shape (types only, byte-stable), learn and
discover; then live calls against the made-up orders service (tests/api_standins.py) and the file run alone
in an empty folder, as every export runs it. Every name, number and address here is made up."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.adapters import api_adapter as aa
from swissarmybench.adapters.api_adapter import Action, Api, Input, Request, Response
from tests.api_standins import Service

BASE = "https://api.example.test/v1"


def answer(body: Any, status: int = 200, kind: str = "application/json", **headers: str) -> Response:
    raw = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
    return Response(
        status, {"content-type": kind, **{k.replace("_", "-"): v for k, v in headers.items()}}, raw
    )


def recorded(pages: Mapping[str, Response | list[Response]]) -> tuple[Api, list[Request]]:
    """An Api that answers each address (its path and query after BASE) with its recorded Response (a list:
    one after another), and the requests it was sent."""
    asked: list[Request] = []
    queue = {k: list(v) if isinstance(v, list) else [v] for k, v in pages.items()}

    def send(request: Request) -> Response:
        asked.append(request)
        key = request.url.removeprefix(BASE)
        got = queue.get(key)
        if not got:
            return answer({"error": f"nothing recorded at {key}"}, 404)
        return got.pop(0) if len(got) > 1 else got[0]

    return Api(BASE, send, "Shop"), asked


GET = Action("list_orders", "GET", "/orders", api="Shop")
NO_SLEEP: Callable[[float], None] = lambda seconds: None  # noqa: E731


def call(
    action: Action, pages: Mapping[str, Any], inputs: Mapping[str, Any] | None = None, **more: Any
) -> dict[str, Any]:
    api, _ = recorded(pages)
    return aa.run(action, inputs, api=api, sleep=NO_SLEEP, **more)


# ===== formats =====


def test_every_format_is_detected_from_its_bytes() -> None:
    rows = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]
    cases = {
        "json": answer(rows),
        "jsonl": answer(
            '{"id": 1, "name": "Ada"}\n{"id": 2, "name": "Grace"}\n', kind="application/x-ndjson"
        ),
        "xml": answer(
            "<orders><order id='1'><name>Ada</name></order><order id='2'><name>Grace</name></order></orders>",
            kind="application/xml",
        ),
        "csv": answer("id,name\n1,Ada\n2,Grace\n", kind="text/csv"),
        "tsv": answer("id\tname\n1\tAda\n2\tGrace\n", kind="text/tab-separated-values"),
    }
    for fmt, response in cases.items():
        found = call(GET, {"/orders": response})
        assert (found["format"], found["kind"]) == (fmt, "records"), fmt
        names = [r.get("name") for r in found["records"]]
        assert names == ["Ada", "Grace"], fmt
    xml = call(GET, {"/orders": cases["xml"]})
    assert xml["records"][0]["@id"] == "1"
    csv_ids = [r["id"] for r in call(GET, {"/orders": cases["csv"]})["records"]]
    assert csv_ids == [1, 2]  # a CSV's cells read as the values they are


def test_a_file_text_empty_and_a_scalar() -> None:
    pdf = answer(
        b"%PDF-1.4 made-up\x00\xff",
        kind="application/pdf",
        content_disposition='attachment; filename="invoice-0001.pdf"',
    )
    found = call(GET, {"/orders": pdf})
    assert found["kind"] == "file" and found["file"]["name"] == "invoice-0001.pdf"
    assert found["file"]["type"] == "application/pdf" and found["file"]["size"] == 18
    assert call(GET, {"/orders": answer("All is well.", kind="text/plain")})["kind"] == "text"
    assert call(GET, {"/orders": Response(204, {}, b"")})["kind"] == "empty"
    value = call(GET, {"/orders": answer(42)})
    assert (value["kind"], value["value"]) == ("value", 42)
    assert value["shape"]["fields"]["value"]["type"] == "integer"


def test_xml_with_a_doctype_or_an_entity_is_not_read() -> None:
    hostile = answer(
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>', kind="application/xml"
    )
    found = call(GET, {"/orders": hostile})
    assert found["kind"] == "text"  # kept as text, never expanded


def test_yaml_when_pyyaml_is_here() -> None:
    pytest.importorskip("yaml")
    found = call(
        GET, {"/orders": answer("- id: 1\n  name: Ada\n- id: 2\n  name: Grace\n", kind="application/yaml")}
    )
    assert (found["format"], found["kind"], len(found["records"])) == ("yaml", "records", 2)


# ===== envelopes =====


@pytest.mark.parametrize(
    ("body", "where"),
    [
        ([{"id": 1}], "$"),
        ({"value": [{"id": 1}], "@odata.count": 1}, "$.value"),
        ({"data": [{"id": 1}]}, "$.data"),
        ({"items": [{"id": 1}], "total": 1}, "$.items"),
        ({"results": [{"id": 1}]}, "$.results"),
        ({"data": {"records": [{"id": 1}]}}, "$.data.records"),
        ({"orders": [{"id": 1}], "count": 1}, "$.orders"),
        ({"columns": [{"name": "id", "type": "integer"}], "rows": [[1]]}, "$.rows"),
        ({"result": {"header": ["id"], "data": [[1]]}}, "$.result.data"),
        ({"order": {"id": 1, "lines": 2}}, None),
    ],
)
def test_records_are_found_wherever_they_sit(body: Any, where: str | None) -> None:
    found = call(GET, {"/orders": answer(body)})
    if where is None:  # one object under a wrapper: a record, kept whole
        assert found["kind"] == "record"
        return
    assert (found["kind"], found["shape"]["envelope"]) == ("records", where)
    assert found["records"] == [{"id": 1}]


def test_a_record_is_kept_whole_and_flattened_by_path() -> None:
    order = {"id": 7, "customer": {"id": 31, "name": "Ada"}, "lines": [{"sku": "A-1"}]}
    found = call(GET, {"/orders": answer(order)})
    assert found["kind"] == "record" and found["record"] == order
    assert found["flat"] == {"id": 7, "customer.id": 31, "customer.name": "Ada", "lines": [{"sku": "A-1"}]}
    assert found["shape"]["fields"]["customer.id"]["type"] == "integer"
    assert found["shape"]["fields"]["lines"]["type"] == "list"


def test_types_are_read_from_values_not_the_declaration() -> None:
    rows = [
        {
            "id": "001",
            "amount": "12.50",
            "paid": "true",
            "on": "2026-11-14",
            "at": "2026-11-14T09:30:00Z",
            "us": "11/14/2026",
            "note": None,
        },
        {
            "id": "002",
            "amount": "3.00",
            "paid": "false",
            "on": "2026-11-15",
            "at": "2026-11-15T10:00:00Z",
            "us": "11/15/2026",
            "note": "gift",
        },
    ]
    declared = Action("x", declared={"kind": "records", "fields": {"amount": "integer"}})
    fields = call(declared, {"/": answer(rows)})["shape"]["fields"]
    assert fields["id"] == {"type": "text", "format": "", "empty": False}  # a leading zero stays text
    assert fields["amount"] == {"type": "number", "format": "text", "empty": False}
    assert fields["paid"]["type"] == "boolean" and fields["on"] == {
        "type": "date",
        "format": "iso",
        "empty": False,
    }
    assert fields["at"]["type"] == "datetime" and fields["us"]["format"] == "m/d/y"
    assert fields["note"]["empty"] is True and fields["note"]["type"] == "text"
    assert aa.type_of("02/30/2026") == ("text", "") and aa.type_of("14.11.2026") == ("date", "d.m.y")
    assert aa.type_of("14 Nov 2026") == ("date", "d mon y") and aa.type_of("2026-13-01") == ("text", "")


# ===== paging =====


def test_paging_by_next_link_link_header_cursor_offset_and_page_number() -> None:
    link = {
        "/orders": answer({"value": [{"id": 1}], "@odata.nextLink": BASE + "/orders?$skiptoken=2"}),
        "/orders?$skiptoken=2": answer({"value": [{"id": 2}]}),
    }
    assert [r["id"] for r in call(GET, link)["records"]] == [1, 2]
    header = {
        "/orders": answer([{"id": 1}], link='</v1/orders?cursor=b>; rel="next"'),
        "/orders?cursor=b": answer([{"id": 2}]),
    }
    found = call(GET, header)
    assert [r["id"] for r in found["records"]] == [1, 2] and found["paging"]["by"] == "next link"
    cursor = Action("list", "GET", "/orders", inputs=(Input("pageToken"),))
    pages = {
        "/orders": answer({"items": [{"id": 1}], "nextToken": "p1"}),
        "/orders?pageToken=p1": answer({"items": [{"id": 2}]}),
    }
    found = call(cursor, pages)
    assert [r["id"] for r in found["records"]] == [1, 2] and found["paging"]["by"] == "cursor"
    offset = Action(
        "list", "GET", "/orders", inputs=(Input("limit", type="integer"), Input("offset", type="integer"))
    )
    pages = {
        "/orders?limit=2": answer([{"id": 1}, {"id": 2}]),
        "/orders?limit=2&offset=2": answer([{"id": 3}]),
    }
    found = call(offset, pages, {"limit": 2})
    assert [r["id"] for r in found["records"]] == [1, 2, 3] and found["paging"]["by"] == "offset"
    numbered = Action("list", "GET", "/orders", inputs=(Input("page", type="integer"),))
    pages = {
        "/orders": answer({"data": [{"id": 1}], "meta": {"total_pages": 2}}),
        "/orders?page=2": answer({"data": [{"id": 2}], "meta": {"total_pages": 2}}),
    }
    found = call(numbered, pages)
    assert [r["id"] for r in found["records"]] == [1, 2] and found["paging"]["by"] == "page number"


def test_paging_stops_at_the_calls_limits_and_on_a_repeated_page() -> None:
    cursor = Action("list", "GET", "/orders", inputs=(Input("cursor"),))
    loop = {
        "/orders": answer({"data": [{"id": 1}], "next_cursor": "a"}),
        "/orders?cursor=a": answer({"data": [{"id": 1}], "next_cursor": "a"}),
    }
    found = call(cursor, loop)
    assert found["paging"]["stopped"] == "the same page came back" and len(found["records"]) == 1
    many = {"/orders": answer({"data": [{"id": 0}], "next_cursor": "1"})} | {
        f"/orders?cursor={n}": answer({"data": [{"id": n}], "next_cursor": str(n + 1)}) for n in range(1, 9)
    }
    found = call(cursor, many, max_pages=3)
    assert found["paging"] == {
        "pages": 3,
        "by": "cursor",
        "more": True,
        "stopped": "the call's limit of 3 pages",
        "retried": 0,
    }
    found = call(cursor, many, max_records=2)
    assert len(found["records"]) == 2 and found["paging"]["more"] is True
    stop = {"/orders": answer({"data": [{"id": 1}], "has_more": False, "next_cursor": "z"})}
    assert call(cursor, stop)["paging"]["pages"] == 1


# ===== inputs, retries, errors =====


ORDER = Action(
    "create_order",
    "POST",
    "/orders/{shop}",
    api="Shop",
    inputs=(Input("shop", "path", required=True), Input("notify", "query", "boolean")),
    body=(Input("amount", "body", "number", True), Input("status", "body", choices=("open", "shipped"))),
    body_required=True,
)


def test_inputs_are_checked_first_naming_the_one() -> None:
    api, asked = recorded({})
    for inputs, said, where in (
        ({}, "shop (path) is required.", "shop"),
        (
            {"shop": "north", "notify": "maybe", "amount": 1},
            "notify is true or false: 'maybe' is neither.",
            "notify",
        ),
        ({"shop": "north"}, "create_order needs a body.", "body"),
        ({"shop": "north", "status": "open"}, "The body's amount is required.", "body.amount"),
        (
            {"shop": "north", "amount": "x"},
            "The body's amount is a number: 'x' is not one.",
            "The body's amount",
        ),
        (
            {"shop": "north", "amount": 1, "status": "lost"},
            "The body's status is one of open, shipped.",
            "body.status",
        ),
        (
            {"shop": "north", "amount": 1, "colour": "red"},
            "create_order takes no input called colour.",
            "colour",
        ),
    ):
        found = aa.run(ORDER, inputs, api=api)
        assert not found["ok"] and found["error"]["error"] == said, inputs
        assert found["error"]["where"] == where and set(found["error"]) == {
            "error",
            "where",
            "fixes",
            "details",
        }
    assert asked == []  # nothing was sent


def test_a_body_is_sent_as_json_and_its_shape_is_kept_without_values() -> None:
    api, asked = recorded({"/orders/north?notify=true": answer({"order_id": 1000, "amount": 9.5}, 201)})
    found = aa.run(ORDER, {"shop": "north", "notify": "yes", "amount": "9.5", "status": "open"}, api=api)
    assert found["ok"] and found["status"] == 201 and found["kind"] == "record"
    assert json.loads(asked[0].body or b"") == {"amount": 9.5, "status": "open"}
    assert asked[0].headers["Content-Type"] == "application/json"
    sent = found["sent"]["fields"]
    assert sent["body.amount"]["type"] == "number" and sent["path.shop"]["type"] == "text"
    assert "9.5" not in json.dumps(found["sent"]) and "north" not in json.dumps(found["sent"])


def test_throttling_and_passing_errors_are_tried_again() -> None:
    waits: list[float] = []
    api, asked = recorded(
        {
            "/orders": [
                answer({"error": "slow"}, 429, retry_after="2"),
                answer({"e": 1}, 503),
                answer([{"id": 1}]),
            ]
        }
    )
    found = aa.run(GET, api=api, sleep=waits.append)
    assert found["ok"] and found["paging"]["retried"] == 2 and waits == [2.0, 2.0] and len(asked) == 3
    post = Action("make", "POST", "/orders")
    api, asked = recorded({"/orders": [answer({"e": 1}, 503), answer({"id": 1}, 201)]})
    found = aa.run(post, api=api, sleep=waits.append)
    assert found["status"] == 503 and len(asked) == 1  # a write is never sent twice after a passing error
    assert found["error"]["fixes"] == [{"label": "Try again", "action": "try_again"}]


def test_an_error_answer_is_the_one_refusal_with_the_apis_own_words() -> None:
    found = call(GET, {"/orders": answer({"error": {"message": "Unknown shop north"}}, 404)})
    assert found["error"] == {
        "error": "list_orders answered 404: there is nothing at that address.",
        "where": "list_orders",
        "fixes": [],
        "details": "Unknown shop north",
    }
    assert found["raw"]["status"] == 404
    signed = call(GET, {"/orders": answer([], 200, set_cookie="session=made-up", x_api_key="made-up")})
    assert (
        signed["raw"]["headers"]["set-cookie"] == "(hidden)"
        and signed["raw"]["headers"]["x-api-key"] == "(hidden)"
    )


# ===== drift =====


def shape_after(rows: Any) -> dict[str, Any]:
    first = call(GET, {"/orders": answer(rows)})
    kept, _ = aa.keep(None, first, "2026-11-14")
    return kept


def test_a_field_added_appears_and_nothing_breaks() -> None:
    kept = shape_after([{"id": 1, "amount": 2.5}])
    found = call(
        GET, {"/orders": answer([{"id": 1, "amount": 2.5, "region": "North"}])}, known=kept["returned"]
    )
    assert found["ok"] and found["records"][0]["region"] == "North"
    assert found["shape"]["drift"]["added"] == ["region"] and found["shape"]["marks"] == {"region": "new"}
    assert found["shape"]["words"] == "1 field new"


def test_a_field_missing_is_null_and_marked() -> None:
    kept = shape_after([{"id": 1, "amount": 2.5}])
    found = call(GET, {"/orders": answer([{"id": 1}])}, known=kept["returned"])
    assert found["ok"] and found["records"] == [{"id": 1, "amount": None}]
    assert found["shape"]["drift"]["missing"] == ["amount"] and found["shape"]["marks"] == {
        "amount": "missing"
    }


def test_only_a_field_marked_required_fails_a_call() -> None:
    kept = shape_after([{"id": 1, "amount": 2.5}])
    found = call(GET, {"/orders": answer([{"id": 1}])}, known=kept["returned"], required=["amount"])
    assert (
        not found["ok"] and found["error"]["error"] == "amount is required and the answer no longer has it."
    )
    assert found["records"] == [{"id": 1, "amount": None}]  # the records still come back


def test_a_type_changed_is_coerced_where_it_reads_cleanly_else_kept_and_marked() -> None:
    kept = shape_after([{"id": 1, "amount": 2.5, "on": "2026-11-14", "qty": 3}])
    later = [{"id": 1, "amount": "2.50", "on": "11/14/2026", "qty": "three"}]
    found = call(GET, {"/orders": answer(later)}, known=kept["returned"])
    assert found["records"] == [{"id": 1, "amount": 2.5, "on": "2026-11-14", "qty": "three"}]
    assert found["shape"]["marks"] == {"amount": "retyped", "on": "retyped", "qty": "retyped"}
    retyped = {r["path"]: (r["was"], r["now"]) for r in found["shape"]["drift"]["retyped"]}
    assert retyped == {
        "amount": ("number", "number in text"),
        "on": ("date (iso)", "date (m/d/y)"),
        "qty": ("integer", "text"),
    }


def test_the_envelope_moved_is_found_again() -> None:
    kept = shape_after([{"id": 1}])
    found = call(GET, {"/orders": answer({"data": [{"id": 1}], "next": None})}, known=kept["returned"])
    assert found["records"] == [{"id": 1}]
    assert found["shape"]["drift"]["moved"] == {"was": "$", "now": "$.data"}
    assert "the records moved" in found["shape"]["words"]


def test_paths_match_in_any_case_and_style() -> None:
    kept = shape_after([{"customer_id": 1, "orderTotal": 2.5}])
    found = call(GET, {"/orders": answer([{"CustomerID": 1, "order_total": 2.5}])}, known=kept["returned"])
    assert found["records"] == [{"customer_id": 1, "orderTotal": 2.5}]
    assert found["shape"]["drift"] == {"added": [], "missing": [], "retyped": [], "moved": None, "offers": []}
    assert aa.pick({"Customer ID": 5}, "customer_id") == 5
    assert aa.pick({"customer": {"Id": 6}}, "customer.id") == 6


def test_a_rename_is_offered_once_never_guessed_and_the_answer_remembered() -> None:
    kept = shape_after([{"customer_id": 1, "amount": 2.5}])
    later = answer([{"customerNo": 1, "amount": 2.5}])
    found = call(GET, {"/orders": later}, known=kept["returned"])
    assert found["records"][0]["customer_id"] is None  # never guessed
    assert found["shape"]["drift"]["offers"] == [
        {"from": "customer_id", "to": "customerNo", "said": "customerNo looks like customer_id: use it?"}
    ]
    kept, change = aa.keep(kept, found, "2026-11-20")
    assert change == {"added": ["customerNo"], "missing": ["customer_id"], "retyped": [], "moved": None}
    assert kept["offers"][0]["from"] == "customer_id"
    taken = aa.answered(kept, "customer_id", "customerNo", True)
    assert taken["renames"] == {"customer_id": "customerNo"} and taken["offers"] == []
    first = aa.keep(None, call(GET, {"/orders": answer([{"customer_id": 1, "amount": 2.5}])}), "2026-11-14")[
        0
    ]
    found = call(GET, {"/orders": later}, known=first["returned"], renames=taken["renames"])
    assert found["records"][0]["customer_id"] == 1 and found["shape"]["marks"]["customer_id"] == "renamed"
    declined = aa.answered(kept, "customer_id", "customerNo", False)
    assert declined["declined"] == ["customer_id"]
    again, _ = aa.keep(declined | {"returned": first["returned"]}, found, "2026-11-21")
    assert again["offers"] == []  # declined: never offered again
    two = call(GET, {"/orders": answer([{"customerNo": 1, "customerRef": 2}])}, known=first["returned"])
    assert two["shape"]["drift"]["offers"] == []  # two alike: that would be a guess


# ===== the kept shape and learn =====


def test_the_kept_shape_holds_types_only_and_is_byte_stable() -> None:
    rows = [{"id": 1, "name": "Ada Lovelace", "amount": 1234.5}]
    first = call(GET, {"/orders": answer(rows)})
    kept, change = aa.keep(None, first, "2026-11-14")
    assert change is None and kept["seen"] == "2026-11-14" and kept["changed"] == "2026-11-14"
    text = aa.text(kept)
    assert "Ada" not in text and "1234.5" not in text and text.endswith("}\n")
    same, change = aa.keep(
        json.loads(text),
        call(GET, {"/orders": answer([{"id": 2, "name": "Grace", "amount": 1.0}])}),
        "2026-11-15",
    )
    assert change is None and aa.text(same) == text.replace('"seen": "2026-11-14"', '"seen": "2026-11-15"')
    failed, change = aa.keep(same, call(GET, {"/orders": answer({"error": "x"}, 500)}), "2026-11-16")
    assert failed == same and change is None
    assert aa.shape_file("orders/get by id") == "orders_get_by_id.json"


def test_learn_gives_the_widgets_the_learned_contract_over_the_declared_one() -> None:
    declared = Action(
        "list_orders",
        "GET",
        "/orders",
        inputs=(Input("status", choices=("open", "shipped")),),
        declared={"kind": "records", "fields": {"amount": "integer"}},
    )
    first = aa.learn(None, declared)
    assert first["learned"] is False and first["fields"][0]["path"] == "amount"
    assert first["inputs"][0]["box"] == "dropdown" and first["maps_to"] == ["table", "grid"]
    kept, _ = aa.keep(
        None, call(declared, {"/orders": answer([{"amount": 2.5, "on": "2026-11-14"}])}), "2026-11-14"
    )
    found = call(
        declared,
        {"/orders": answer([{"amount": "2.5", "on": "2026-11-14", "extra": 1}])},
        known=kept["returned"],
    )
    kept, _ = aa.keep(kept, found, "2026-11-20")
    contract = aa.learn(kept, declared)
    assert contract["learned"] and {f["path"]: f["type"] for f in contract["fields"]} == {
        "amount": "number",
        "extra": "integer",
        "on": "date",
    }
    assert {f["path"]: f["mark"] for f in contract["fields"]} == {
        "amount": "retyped",
        "extra": "new",
        "on": "",
    }
    assert contract["drift"] == "1 field new, 1 retyped since 2026-11-20"
    form = aa.learn(None, ORDER)
    assert [(b["name"], b["box"]) for b in form["body"]] == [("amount", "number"), ("status", "dropdown")]
    assert form["maps_to"] == ["form"]


# ===== the specification is the front door =====


def test_actions_come_from_openapi_3_and_swagger_2() -> None:
    service = Service()
    three = aa.actions(service.openapi(), "Orders")
    assert sorted(three) == ["createOrder", "getOrder", "listClients", "listOrders", "listRegions"]
    listed = three["listOrders"]
    assert listed.declared["kind"] == "records" and listed.declared["envelope"] == "$.items"
    assert set(listed.declared["fields"]) == {"order_id", "amount", "status"}
    assert three["getOrder"].inputs[0] == Input("order_id", "path", "integer", True)
    assert three["createOrder"].writes and three["createOrder"].body_required
    assert [b.name for b in three["createOrder"].body] == ["order_id", "amount", "status"]
    two = aa.actions(service.swagger(), "Orders Two")
    assert (
        set(two) >= {"listOrders", "getOrder", "createOrder"} and two["getOrder"].inputs[0].type == "integer"
    )
    with pytest.raises(aa.ActionError):
        aa.actions({"openapi": "3.0.0"})
    again = Action.from_json(json.loads(json.dumps(listed.to_json())))
    assert again == listed


# ===== discovery =====


def test_discover_probes_reads_only_fills_ids_and_maps_each_endpoint() -> None:
    doc = {
        "openapi": "3.0.3",
        "paths": {
            "/customers": {
                "get": {
                    "operationId": "listCustomers",
                    "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer"}}],
                },
                "post": {"operationId": "addCustomer"},
            },
            "/customers/{customer_id}": {"get": {"operationId": "getCustomer"}},
            "/customers/{customer_id}/orders": {"get": {"operationId": "customerOrders"}},
            "/stats/total": {"get": {"operationId": "total"}},
            "/report": {"get": {"operationId": "report"}},
            "/things/{thing}": {"get": {"operationId": "thing"}},
        },
    }
    found = aa.actions(doc, "Shop")
    api, asked = recorded(
        {
            "/customers?limit=1": answer({"data": [{"customer_id": 31, "name": "Ada"}]}),
            "/customers/31": answer({"customer_id": 31, "name": "Ada"}),
            "/customers/31/orders": answer([{"order_id": 7, "customer_id": 31}]),
            "/stats/total": answer(1234),
            "/report": answer(b"%PDF made-up\x00", kind="application/pdf"),
        }
    )
    learned = aa.discover(found, api, max_calls=10, sleep=NO_SLEEP)
    assert [r.method for r in asked] == ["GET"] * 5 and learned["calls"] == 5
    assert learned["skipped"] == {
        "addCustomer": "it writes: learned from the specification",
        "thing": "its required inputs: no other answer gave them",
    }
    assert learned["maps"] == {
        "listCustomers": ["table", "grid"],
        "addCustomer": ["form"],
        "getCustomer": ["detail", "form"],
        "customerOrders": ["table", "grid"],
        "total": ["metric"],
        "report": ["download"],
        "thing": [],
    }
    assert {
        "master": "listCustomers",
        "detail": "getCustomer",
        "by": "customer_id",
        "input": "customer_id",
    } in learned["pairs"]
    said = json.dumps(learned["answers"])
    assert "Ada" not in said and "1234" not in said.replace('"status": 200', "")  # no value leaves discovery
    capped = aa.discover(found, recorded({"/customers?limit=1": answer([])})[0], max_calls=1, sleep=NO_SLEEP)
    assert capped["calls"] == 1 and "the discovery's limit of 1 calls" in capped["skipped"].values()


# ===== the statistics' seam =====


def test_each_call_hands_its_facts_to_the_hook_never_a_value() -> None:
    seen: list[dict[str, Any]] = []
    aa.observe(seen.append)
    try:
        found = call(GET, {"/orders": answer([{"id": 1, "name": "Ada"}])}, who="agent")
    finally:
        aa.observe(None)
    facts = found["facts"]
    assert seen == [facts] and facts["who"] == "agent" and facts["action"] == "list_orders"
    assert facts["size"]["records"] == 1 and facts["size"]["columns"] == 2 and facts["size"]["pages"] == 1
    assert facts["outcome"] == {"status": 200, "ok": True, "retries": 0, "error": ""}
    assert set(facts["ms"]) == {"wait", "first_byte", "total"} and "Ada" not in json.dumps(facts)
    refused = aa.run(ORDER, {}, api=recorded({})[0])
    assert refused["facts"]["outcome"]["error"] == "input"


# ===== live, and alone =====


@pytest.fixture
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


def test_live_calls_against_the_made_up_orders_service(service: Service) -> None:
    found = aa.actions(service.openapi(), "Orders")
    api = aa.http(service.url + "/v1")
    orders = aa.run(found["listOrders"], api=api)
    assert orders["kind"] == "records" and len(orders["records"]) == 25 and orders["paging"]["by"] == "cursor"
    assert orders["paging"]["pages"] == 3 and orders["shape"]["envelope"] == "$.items"
    clients = aa.run(found["listClients"], api=api)
    assert len(clients["records"]) == 3 and clients["paging"]["by"] == "next link"
    regions = aa.run(found["listRegions"], api=api)
    assert len(regions["records"]) == 7 and regions["paging"]["by"] == "page number"
    one = aa.run(found["getOrder"], {"order_id": 4}, api=api)
    assert one["kind"] == "record" and one["record"]["order_id"] == 4
    missing = aa.run(found["getOrder"], {"order_id": 999}, api=api)
    assert missing["status"] == 404 and missing["error"]["details"] == "No such order"
    flaky = Action("flaky", "GET", "/flaky")
    assert aa.run(flaky, api=api, sleep=NO_SLEEP)["paging"]["retried"] == 1


def test_a_bearer_sign_in_from_an_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    running = Service("bearer").start()
    try:
        from tests.api_standins import BEARER

        monkeypatch.setenv("SHOP_TOKEN", BEARER)
        api = aa.http(running.url + "/v1", {"type": "bearer", "variable": "SHOP_TOKEN"})
        found = aa.run(Action("products", "GET", "/products"), api=api)
        assert found["ok"] and found["records"][0]["sku"] == "A-1"
        monkeypatch.setenv("SHOP_TOKEN", "wrong")
        refused = aa.run(Action("products", "GET", "/products"), api=api)
        assert refused["status"] == 401 and BEARER not in json.dumps(refused)
    finally:
        running.stop()


def test_it_runs_alone_in_an_empty_folder_as_an_export_does(tmp_path: Path, service: Service) -> None:
    shutil.copy(aa.__file__, tmp_path / "api_adapter.py")
    script = (
        "import json, os, sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # beside it, as an export has it\n"
        "import api_adapter as aa\n"
        "spec = json.loads(sys.argv[2])\n"
        "found = aa.actions(spec, 'Orders')\n"
        "got = aa.run(found['listOrders'], {'status': 'open'}, api=aa.http(sys.argv[1] + '/v1'))\n"
        "mods = sorted(m for m in sys.modules if m.startswith(('swissarmybench', 'adapter')))\n"
        "print(json.dumps({'n': len(got['records']), 'mods': mods}))\n"
    )
    (tmp_path / "run.py").write_text(script, encoding="utf-8")
    done = subprocess.run(  # noqa: S603 (this Python, a made-up service)
        [sys.executable, "-I", "run.py", service.url, json.dumps(service.openapi())],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    said = json.loads(done.stdout)
    assert said == {"n": 17, "mods": []}  # 17 open orders; nothing of the app imported
