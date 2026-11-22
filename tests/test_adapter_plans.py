"""What a plan says, added for the endpoint wizard (adapter 1.5.0 on; docs/ideas.md "The endpoint wizard
and its patterns"): a plan's values keep their type through JSON (a date sent as a date comes back as one),
a group by a date's period folded into every source's own SQL, and a "contains, any case" filter. Each
against every backend it touches: DuckDB, the sandbox through Remote, the SQL dialects (SQLite always; each
dialect's text read back by sqlglot), OData and Rows (DuckDB over the stream), Files and Excel. Made-up data
only."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter
from swissarmybench.adapters.adapter import Filter, Plan
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_sandbox_query import TestRemote, _put

VISITS = pa.table(
    {
        "id": [1, 2, 3, 4, 5],
        "garden": ["Rose Bed", "Herb Patch", "rose arch", "Pond", "Old Rose"],
        "seen": [dt.date(2026, 1, 5), dt.date(2026, 1, 20), dt.date(2026, 2, 3), dt.date(2026, 4, 9),
                 dt.date(2026, 4, 30)],
        "at": [dt.datetime(2026, 1, 5, 9, 30), dt.datetime(2026, 1, 20, 14, 0),
               dt.datetime(2026, 2, 3, 8, 15), dt.datetime(2026, 4, 9, 17, 45),
               dt.datetime(2026, 4, 30, 23, 59)],
        "cost": pa.array([decimal.Decimal("12.50"), decimal.Decimal("3.25"), decimal.Decimal("40.00"),
                          decimal.Decimal("7.75"), decimal.Decimal("1.00")], pa.decimal128(8, 2)),
    }
)  # fmt: skip


# ----- 1.5.0: a plan's values keep their type through JSON -----


def test_a_plans_dates_times_and_decimals_go_through_json_as_themselves() -> None:
    plan = Plan(
        filters=(
            Filter("seen", ">=", dt.date(2026, 1, 20)),
            Filter("at", "between", [dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 3, 1, 12, 30, 5, 7)]),
            Filter("opens", "=", dt.time(9, 30)),
            Filter("cost", "in", [decimal.Decimal("12.50"), decimal.Decimal("3.25")]),
            Filter("garden", "=", "Pond"),
        )
    )
    sent = json.dumps(plan.to_json(typed=True))  # no default=: every value is JSON's own
    back = adapter.plan_from(json.loads(sent))
    assert back == plan
    assert [type(f.value) for f in back.filters][:3] == [dt.date, list, dt.time]
    assert type(back.filters[1].value[1]) is dt.datetime and back.filters[1].value[1].microsecond == 7
    assert type(back.filters[3].value[0]) is decimal.Decimal
    # The plain JSON is as it was: a value as itself (a caller passing default= of its own).
    assert plan.to_json()["filters"][0] == ["seen", ">=", dt.date(2026, 1, 20)]
    # A zoned time keeps its zone.
    zoned = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    again = adapter.plan_from(json.loads(json.dumps(Plan(filters=(Filter("at", ">", zoned),)).to_json(True))))
    assert again.filters[0].value == zoned and again.filters[0].value.utcoffset() == dt.timedelta(hours=2)


def test_a_typed_value_that_is_not_one_is_said_plainly() -> None:
    with pytest.raises(adapter.AdapterError, match="not a date"):
        adapter.plan_from({"filters": [["seen", "=", {"sab_type": "date", "value": "the fifth"}]]})
    with pytest.raises(adapter.AdapterError, match="sab_type is one of"):
        adapter.plan_from({"filters": [["seen", "=", {"sab_type": "colour", "value": "red"}]]})


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "garden")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "visits", VISITS)
        yield client


def test_the_sandbox_through_remote_reads_with_a_date_a_datetime_and_a_decimal(boxed: TestClient) -> None:
    source = TestRemote(boxed, "Sandbox")
    plan = Plan(
        columns=("id",),
        filters=(
            Filter("seen", ">=", dt.date(2026, 1, 20)),
            Filter("at", "<", dt.datetime(2026, 4, 30, 0, 0)),
            Filter("cost", ">", decimal.Decimal("5")),
        ),
        sort=(("id", False),),
    )
    reader, folded = adapter.read(source, "visits", plan)
    assert reader.read_all().column("id").to_pylist() == [3, 4]
    assert folded.parts == ("filters", "columns", "sort")
    db = adapter.Connection(source, "Sandbox")
    january = [dt.date(2026, 1, 1), dt.date(2026, 1, 31)]
    found = db.read("visits", columns=["id"], filters=[["seen", "between", january]])
    assert sorted(found.read_all().column("id").to_pylist()) == [1, 2]


def test_sqlite_takes_a_plans_date_as_its_own_text(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "garden.db")
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, seen TEXT, cost REAL)")
    con.executemany("INSERT INTO visits VALUES (?, ?, ?)", [(1, "2026-01-05", 12.5), (2, "2026-02-03", 40.0)])
    con.commit()
    source = adapter.Sql(con, "sqlite", "Garden")
    plan = Plan(columns=("id",), filters=(Filter("seen", ">=", dt.date(2026, 1, 20)),
                                          Filter("cost", ">", decimal.Decimal("10"))))  # fmt: skip
    assert adapter.read(source, "visits", plan)[0].read_all().column("id").to_pylist() == [2]
