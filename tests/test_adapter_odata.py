"""Dataverse's Web API as a backend of the adapter (Plans/adapter.plan.md, Order 2): filters, columns, sort
and limit folded into one OData read through the connection's own calls, the records typed by the table's
metadata, the rest done by DuckDB over the answer. Against tests/dataverse_standin.py's made-up company."""

from __future__ import annotations

import datetime

import pytest

from swissarmybench.adapters import adapter as sab
from swissarmybench.adapters.adapter import Filter, Plan, Total
from tests import dataverse_standin as made_up
from tests import test_dataverse as dataverse_tests
from tests.test_dataverse import connect

keyring = dataverse_tests.keyring  # the fixtures: a memory keyring, the stand-in
standin = dataverse_tests.standin


def test_filters_say_themselves_in_odata_or_not_at_all() -> None:
    fields = {"name": "name", "estimatedvalue": "estimatedvalue", "parentaccountid": "_parentaccountid_value"}
    said = sab.odata_filter(
        [
            Filter("estimatedvalue", "between", [10, 20.5]),
            Filter("name", "in", ["Ann's", "Bo"]),
            Filter("parentaccountid", "is not null"),
            Filter("name", "like", "%gate%"),
            Filter("name", "like", "Gar%"),
        ],
        fields,
    )
    assert said == (
        "(estimatedvalue ge 10 and estimatedvalue le 20.5) and (name eq 'Ann''s' or name eq 'Bo') and "
        "_parentaccountid_value ne null and contains(name,'gate') and startswith(name,'Gar')"
    )
    assert sab.odata_filter([Filter("name", "like", "G%t%")], fields) is None
    assert sab.odata_filter([Filter("salesstage", "=", "Close")], fields) is None  # a choice's label
    assert sab.odata_literal(datetime.date(2026, 3, 1)) == "2026-03-01"


def test_a_read_folds_filters_columns_sort_and_limit_into_one_odata_read(standin: made_up.StandIn) -> None:
    source = sab.OData(connect(standin))
    plan = Plan(
        columns=("name", "estimatedvalue"),
        filters=(Filter("estimatedvalue", ">", 1000),),
        sort=(("estimatedvalue", True),),
        limit=5,
    )
    reader, folded = sab.read(source, "opportunity", plan)
    assert folded.parts == ("filters", "columns", "sort", "limit")
    found = reader.read_all()
    assert found.column_names == ["name", "estimatedvalue"] and found.num_rows == 5
    values = found.column("estimatedvalue").to_pylist()
    assert values == sorted(values, reverse=True) and min(values) > 1000
    asked = next(r for r in reversed(standin.gets()) if r["path"].endswith("/opportunities"))["query"]
    assert (asked["$top"], asked["$filter"], asked["$orderby"]) == (
        "5",
        "estimatedvalue gt 1000",
        "estimatedvalue desc",
    )


def test_what_odata_cannot_say_is_done_over_the_answer(standin: made_up.StandIn) -> None:
    source = sab.OData(connect(standin))
    counted, folded = sab.read(source, "opportunity", Plan(group=("salesstage",), totals=(Total("count"),)))
    assert folded.parts == ()
    rows = counted.read_all().to_pylist()
    assert sum(r["count"] for r in rows) == made_up.OPPORTUNITIES
    paged, folded = sab.read(source, "account", Plan(sort=(("name", False),), offset=10, limit=5))
    assert folded.parts == ("sort",) and paged.read_all().num_rows == 2  # 12 accounts, from the 11th


def test_tables_come_from_the_metadata_with_duckdb_types(standin: made_up.StandIn) -> None:
    listed = {t.name: t for t in sab.tables(sab.OData(connect(standin)))}
    assert {"account", "contact", "opportunity"} <= set(listed)
    kinds = {c.name: c.type for c in listed["opportunity"].columns}
    assert kinds["estimatedvalue"] == "DOUBLE" and kinds["estimatedclosedate"] == "TIMESTAMP"
    # Its writes are the adapter's since phase 3 (tests/test_adapter_writes.py).
    with pytest.raises(sab.AdapterError, match="takes the rows it writes"):
        sab.write(sab.OData(connect(standin)), "account", mode="merge")
