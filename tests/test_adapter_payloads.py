"""API payloads through the adapter (Plans/adapter.plan.md: "every api payload in and out should travel
through the adapter"): an endpoint's Arrow answer made JSON records by sab_adapter.to_json (the same JSON
plain gives) or an Arrow IPC stream for a caller that accepts one (a widget); a body typed
Annotated[pa.Table, Model] checked against its model, then made Arrow by from_json with the model's types.
Other endpoints answer as before. Made-up data only."""

from __future__ import annotations

import datetime
import decimal
import json
import sys
from collections.abc import Iterator
from typing import Annotated, Any, TypedDict

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from swissarmybench.adapters import sab_adapter
from swissarmybench.domain import local_api
from swissarmybench.server import api_runtime


class Order(TypedDict):
    order_id: int
    region: str
    amount: float
    placed_on: datetime.date


ORDERS = pa.table(
    {
        "order_id": [1, 2],
        "region": ["North", "South"],
        "amount": pa.array([decimal.Decimal("12.50"), decimal.Decimal("4.00")], pa.decimal128(10, 2)),
        "placed_on": [datetime.date(2026, 3, 1), datetime.date(2026, 3, 2)],
    }
)


@pytest.fixture
def endpoints(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    monkeypatch.setitem(sys.modules, "sab_adapter", sab_adapter)  # as the host (and an export) has it
    api_runtime.ENDPOINTS.clear()
    seen: list[Any] = []

    @api_runtime.endpoint("GET", "/orders")
    def orders() -> pa.Table:
        return ORDERS

    @api_runtime.endpoint("POST", "/orders/load", status=201)
    def load(rows: Annotated[pa.Table, Order]) -> dict[str, int]:
        seen.append(rows)
        return {"loaded": rows.num_rows}

    yield seen
    api_runtime.ENDPOINTS.clear()


def test_an_arrow_answer_is_json_records_through_the_adapter(endpoints: list[Any]) -> None:
    status, headers, body = api_runtime.handle("GET", "/orders")
    assert (status, headers["Content-Type"]) == (200, "application/json")
    assert json.loads(body) == [
        {"order_id": 1, "region": "North", "amount": 12.5, "placed_on": "2026-03-01"},
        {"order_id": 2, "region": "South", "amount": 4.0, "placed_on": "2026-03-02"},
    ]
    assert json.loads(body) == api_runtime.plain(ORDERS)  # the same JSON as before the adapter


def test_a_widget_that_accepts_arrow_gets_an_arrow_stream(endpoints: list[Any]) -> None:
    status, headers, body = api_runtime.handle("GET", "/orders", accept=api_runtime.ARROW)
    assert (status, headers["Content-Type"]) == (200, api_runtime.ARROW)
    assert ipc.open_stream(body).read_all().equals(ORDERS)


def test_a_table_body_is_checked_then_made_arrow_with_its_models_types(endpoints: list[Any]) -> None:
    sent = [{"order_id": 7, "region": "East", "amount": 3, "placed_on": "2026-04-01"}]
    status, _, body = api_runtime.handle("POST", "/orders/load", body=json.dumps(sent))
    assert (status, json.loads(body)) == (201, {"loaded": 1})
    made = endpoints[-1]
    assert dict(zip(made.column_names, [str(t) for t in made.schema.types], strict=True)) == {
        "order_id": "int64", "region": "string", "amount": "double", "placed_on": "date32[day]",
    }  # fmt: skip
    assert made.column("placed_on")[0].as_py() == datetime.date(2026, 4, 1)
    wrong = [{"order_id": "seven", "region": "East", "amount": 3, "placed_on": "2026-04-01"}]
    status, _, body = api_runtime.handle("POST", "/orders/load", body=json.dumps(wrong))
    assert status == 422 and json.loads(body)["field"] == "rows[0].order_id"


def test_api_py_reads_a_table_body_as_the_list_it_is_sent_as() -> None:
    source = (
        "from typing import Annotated, TypedDict\n\nimport pyarrow as pa\nfrom sab_api import endpoint\n\n\n"
        "class Order(TypedDict):\n    order_id: int\n    region: str\n\n\n"
        '@endpoint("POST", "/orders/load")\ndef load(rows: Annotated[pa.Table, Order]) -> dict:\n'
        "    return {}\n"
    )
    api = local_api.parse(source)
    body = local_api.body_of(api.endpoints[0])
    assert body is not None and body.type == "list[Order]"
    assert [e["body"] for e in api_runtime.describe()] == []  # nothing registered here
