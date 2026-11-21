"""The body checked against its model in sab_api (the owner approved the critic's proposal 1, 2026-11-21): a
TypedDict's or a dataclass's fields, nested ones and lists of them; 422 naming the field (a wrong type, a
missing required one, an unknown one), the same in Swiss Army Bench's local host and in every export (they
all call handle). Made-up data."""

from __future__ import annotations

import dataclasses
import datetime
import json
from collections.abc import Iterator
from typing import Any, NotRequired, TypedDict

import pytest

from swissarmybench.server import api_runtime


class Line(TypedDict):
    sku: str
    quantity: int


class Order(TypedDict):
    order_id: int
    region: str
    amount: float
    placed_on: datetime.date
    paid: NotRequired[bool]
    note: str | None
    lines: NotRequired[list[Line]]


@dataclasses.dataclass
class Visit:
    store: str
    staff: int = 0


@pytest.fixture
def endpoints() -> Iterator[list[Any]]:
    api_runtime.ENDPOINTS.clear()
    seen: list[Any] = []

    @api_runtime.endpoint("POST", "/orders", status=201)
    def add_order(order: Order) -> Order:
        seen.append(order)
        return order

    @api_runtime.endpoint("POST", "/orders/many")
    def add_orders(orders: list[Order]) -> dict[str, int]:
        return {"added": len(orders)}

    @api_runtime.endpoint("POST", "/visits")
    def add_visit(visit: Visit) -> Visit:
        seen.append(visit)
        return visit

    yield seen
    api_runtime.ENDPOINTS.clear()


GOOD = {"order_id": 7, "region": "West", "amount": 12, "placed_on": "2026-10-02", "note": None}


def _post(path: str, body: Any) -> tuple[int, dict[str, Any]]:
    status, _, raw = api_runtime.handle("POST", path, {}, json.dumps(body))
    return status, json.loads(raw or b"null")


def test_a_body_that_fits_its_model_passes_as_sent(endpoints: list[Any]) -> None:
    lines = [{"sku": "A-1", "quantity": 2}]
    status, said = _post("/orders", GOOD | {"paid": True, "lines": lines})
    assert status == 201 and said["amount"] == 12 and endpoints[0]["lines"] == lines
    assert _post("/orders/many", [GOOD, GOOD | {"order_id": 8}]) == (200, {"added": 2})
    assert _post("/visits", {"store": "Larkfield Shop"})[0] == 200
    assert endpoints[-1] == Visit("Larkfield Shop", 0)
    # As FastAPI's own takes them (a form's boxes): 3.0 and "3" for a whole number, "12.5" for a number.
    status, said = _post("/orders", GOOD | {"order_id": 3.0, "amount": "12.5"})
    assert status == 201 and said["order_id"] == 3 and said["amount"] == 12.5
    assert _post("/visits", {"store": "Larkfield Shop", "staff": "2"})[0] == 200
    assert endpoints[-1] == Visit("Larkfield Shop", 2)


@pytest.mark.parametrize(
    ("path", "body", "field", "words"),
    [
        ("/orders", GOOD | {"amount": "twelve"}, "order.amount", "order.amount is a number, not 'twelve'."),
        ("/orders", GOOD | {"order_id": 7.5}, "order.order_id", "order.order_id is a whole number, not 7.5."),
        (
            "/orders",
            GOOD | {"order_id": True},
            "order.order_id",
            "order.order_id is a whole number, not True.",
        ),
        (
            "/orders",
            GOOD | {"placed_on": "2 Oct"},
            "order.placed_on",
            "order.placed_on is a date (2026-01-15)",
        ),
        (
            "/orders",
            {k: v for k, v in GOOD.items() if k != "region"},
            "order.region",
            "order.region is required.",
        ),
        ("/orders", GOOD | {"colour": "red"}, "order.colour", "order has no field 'colour'"),
        ("/orders", GOOD | {"region": None}, "order.region", "order.region is text, not None."),
        (
            "/orders",
            GOOD | {"lines": [{"sku": "A", "quantity": "two"}]},
            "order.lines[0].quantity",
            "is a whole number",
        ),
        ("/orders", GOOD | {"lines": {"sku": "A"}}, "order.lines", "order.lines is a list"),
        ("/orders", ["not", "an", "object"], "order", "order is a JSON object"),
        ("/orders/many", [GOOD, GOOD | {"amount": "x"}], "orders[1].amount", "orders[1].amount is a number"),
        (
            "/visits",
            {"store": "Larkfield Shop", "staff": "two"},
            "visit.staff",
            "visit.staff is a whole number",
        ),
        ("/visits", {}, "visit.store", "visit.store is required."),
    ],
)
def test_a_body_that_does_not_fit_is_422_naming_the_field(
    endpoints: list[Any], path: str, body: Any, field: str, words: str
) -> None:
    status, said = _post(path, body)
    assert status == 422, said
    assert said["field"] == field and words in said["error"], said
    assert endpoints == []  # the endpoint never ran
