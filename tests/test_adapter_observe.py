"""adapter.observe (1.2.0): each call's facts handed to a hook as it ends (Plans/stats.plan.md): times in
parts, sizes, what the source folded against what DuckDB did, the outcome, the result's fingerprint; never
a value. No hook: nothing is timed. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter as sab


@pytest.fixture
def heard() -> Iterator[list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    sab.observe(calls.append)
    yield calls
    sab.observe(None)


def _store() -> sab.DuckDB:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE orders AS SELECT i AS id, 'North' AS region, i * 2.5 AS amount, 'secret-ish' AS note "
        "FROM range(120000) t(i)"
    )
    return sab.DuckDB.over(con, "Shop")


def test_a_read_says_its_times_sizes_and_fingerprint_once_consumed(heard: list[dict[str, Any]]) -> None:
    reader, folded = sab.read(_store(), "orders", sab.Plan(columns=("id", "amount"), limit=100_000))
    assert heard == []  # a stream's facts come when it ends
    assert reader.read_all().num_rows == 100_000
    (facts,) = heard
    assert facts["call"] == "read" and facts["source"] == "Shop" and facts["table"] == "orders"
    assert facts["size"]["rows"] == 100_000 and facts["size"]["batches"] >= 2
    assert facts["size"]["bytes"] > 0 and facts["size"]["columns"] == 2 and facts["size"]["asked"] == 2
    assert facts["folded"] == list(folded.parts) and facts["by_duckdb"] == []
    assert facts["outcome"] == {"ok": True, "error": ""}
    assert facts["ms"]["first_row"] is not None and facts["ms"]["total"] >= facts["ms"]["first_row"]
    assert len(facts["fingerprint"]) == 12
    assert "secret-ish" not in json.dumps(facts) and "North" not in json.dumps(facts)


def test_the_same_shape_has_the_same_fingerprint(heard: list[dict[str, Any]]) -> None:
    store = _store()
    sab.read(store, "orders", sab.Plan(columns=("id",), limit=3))[0].read_all()
    sab.read(store, "orders", sab.Plan(columns=("id",), limit=9))[0].read_all()
    sab.read(store, "orders", sab.Plan(columns=("region",), limit=3))[0].read_all()
    prints = [f["fingerprint"] for f in heard]
    assert prints[0] == prints[1] != prints[2]


def test_what_a_source_could_not_fold_is_said_as_duckdbs(heard: list[dict[str, Any]]) -> None:
    class Plain:
        name = "Plain"

        def tables(self) -> list[sab.Table]:
            return []

        def read(self, table: str, plan: sab.Plan) -> tuple[pa.RecordBatchReader, sab.Folded]:
            data = pa.table({"id": [1, 2, 3], "region": ["North", "South", "North"]})
            return data.to_reader(), sab.Folded()

        def write(self, table: str, batches: Any, key: Any, mode: str) -> sab.Counts:
            return sab.Counts(inserted=len(batches.read_all()))

    got = sab.read(Plain(), "t", sab.Plan(filters=(sab.Filter("region", "=", "North"),), limit=1))[0]
    assert got.read_all().num_rows == 1
    assert heard[0]["folded"] == [] and heard[0]["by_duckdb"] == ["filters", "limit"]
    counts = sab.write(Plain(), "t", pa.table({"id": [1, 2]}))
    assert counts.inserted == 2
    write = heard[1]
    assert write["call"] == "write" and write["mode"] == "insert" and write["size"]["rows"] == 2


def test_a_query_a_failure_and_a_name_resolved(heard: list[dict[str, Any]]) -> None:
    store = _store()
    sab.use(lambda name: store)
    try:
        sab.query("Shop", "SELECT count(*) AS n FROM orders").read_all()
        with pytest.raises(duckdb.Error):
            sab.query("Shop", "SELECT * FROM no_such_table").read_all()
    finally:
        sab.use(None)
    ok, failed = heard
    assert ok["call"] == "query" and ok["ms"]["connect"] is not None and ok["size"]["rows"] == 1
    assert failed["outcome"]["ok"] is False and failed["outcome"]["error"]
    assert "no_such_table" not in json.dumps(failed)  # the error's kind, never its words


def test_a_stream_dropped_half_way_is_still_said(heard: list[dict[str, Any]]) -> None:
    reader, _ = sab.read(_store(), "orders")
    reader.read_next_batch()
    del reader
    import gc

    gc.collect()
    assert heard and heard[0]["size"]["rows"] > 0


def test_a_hook_that_fails_never_fails_the_call() -> None:
    def broken(facts: dict[str, Any]) -> None:
        raise RuntimeError("no")

    sab.observe(broken)
    try:
        assert sab.read(_store(), "orders", sab.Plan(limit=2))[0].read_all().num_rows == 2
    finally:
        sab.observe(None)


def test_no_hook_leaves_the_reader_as_the_source_gave_it() -> None:
    store = _store()
    reader, _ = sab.read(store, "orders", sab.Plan(limit=2))
    assert reader.read_all().num_rows == 2
    assert sab.VERSION.split(".")[:2] >= ["1", "2"]
