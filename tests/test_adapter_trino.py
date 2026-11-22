"""The adapter's Trino writes (phase 5, Plans/adapter.plan.md: "Trino's write without a transaction, said
plainly in its dry run"): the project scaffold's adapter.py against a stand-in of trino.dbapi's connection
over DuckDB that keeps the rows (tests/trino_standin.py answers reads only, the same five orders to any
query, so it cannot prove a write). A statement a batch, no transaction (the stand-in refuses a rollback),
the dry run's note, a truncate with rows refused, a failure part-way naming the rows already written.
Made-up rows only."""

from __future__ import annotations

import sys
import types
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter

# ===== Trino =====


class TrinoStandIn:
    """trino.dbapi's connection over DuckDB: each statement stands alone (no transaction; rollback refused, as
    Trino's connectors have none), every statement kept; `refuse` raises Trino's words for a statement's
    start."""

    def __init__(self) -> None:
        self.db = duckdb.connect()
        self.db.execute("CREATE SCHEMA sales; CREATE TABLE sales.orders (order_id BIGINT, region VARCHAR)")
        self.db.execute("INSERT INTO sales.orders VALUES (1, 'North'), (9, 'North')")
        self.statements: list[str] = []
        self.refuse: dict[str, str] = {}
        self.description: list[tuple[str]] | None = None
        self.rowcount = -1
        self._rows: list[Any] = []

    def cursor(self) -> TrinoStandIn:
        return self

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append(sql)
        for start, words in self.refuse.items():
            if sql.startswith(start):
                raise RuntimeError(f'TrinoUserError(type=USER_ERROR, name=NOT_SUPPORTED, message="{words}")')
        self.db.execute(sql.replace('"lake".', ""), params)
        self.description = [(d[0],) for d in self.db.description] if self.db.description else None
        self._rows = self.db.fetchall() if self.db.description else []

    def fetchall(self) -> list[Any]:
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, size: int) -> list[Any]:
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        raise AssertionError("Trino's connection is never rolled back: it has no transaction")

    def close(self) -> None:
        pass


@pytest.fixture
def trino(monkeypatch: pytest.MonkeyPatch) -> TrinoStandIn:
    fake = types.ModuleType("trino")
    fake.paramstyle = "qmark"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trino", fake)
    return TrinoStandIn()


def lake_rows(t: TrinoStandIn) -> list[Any]:
    return t.db.execute("SELECT * FROM sales.orders ORDER BY 1").fetchall()


def test_trino_writes_a_statement_a_batch_without_a_transaction(trino: TrinoStandIn) -> None:
    db = adapter.Sql(trino, "trino", "Lake")
    rows = pa.table({"order_id": [1, 2, 3], "region": ["South", "East", "West"]})
    done = adapter.write(db, "lake.sales.orders", rows.to_reader(max_chunksize=2), ["order_id"], "merge")
    assert (done.inserted, done.updated, done.notes) == (2, 1, (adapter.NO_TRANSACTION,))
    merges = [s for s in trino.statements if s.startswith("MERGE")]
    assert len(merges) == 2  # three rows, two a statement
    assert merges[0].startswith(
        'MERGE INTO "lake"."sales"."orders" AS t USING (VALUES (?, ?), (?, ?)) AS s ("order_id", "region")\n'
        'ON t."order_id" = s."order_id"\nWHEN MATCHED THEN UPDATE SET "region" = s."region"\n'
    )
    assert lake_rows(trino) == [(1, "South"), (2, "East"), (3, "West"), (9, "North")]
    assert adapter.write(db, "lake.sales.orders", pa.table({"order_id": [4], "region": ["N"]})).inserted == 1
    assert adapter.write(db, "lake.sales.orders", pa.table({"order_id": [9], "region": ["Z"]}), ["order_id"],
                         "update").updated == 1  # fmt: skip
    assert adapter.write(db, "lake.sales.orders", pa.table({"order_id": [9, 4, 404]}), ["order_id"],
                         "delete").deleted == 2  # fmt: skip
    assert adapter.write(db, "lake.sales.orders", None, mode="truncate").deleted == 3
    assert lake_rows(trino) == []


def test_trino_says_it_has_no_transaction_in_its_dry_run_and_refuses_a_truncate_with_rows(
    trino: TrinoStandIn,
) -> None:
    db = adapter.Sql(trino, "trino", "Lake")
    rows = pa.table({"order_id": [1, 2], "region": ["South", "East"]})
    plan = adapter.planned(db, "lake.sales.orders", rows, ["order_id"], "merge")
    assert (plan.updated, plan.inserted, plan.notes) == (1, 1, (adapter.NO_TRANSACTION,))
    assert adapter.NO_TRANSACTION == (
        "Trino writes row batches without a transaction: a failure part-way leaves the rows already written."
    )
    for call in (adapter.planned, adapter.write):
        with pytest.raises(
            adapter.AdapterError, match="Trino writes row batches without a transaction: a fail"
        ) as no:
            call(db, "lake.sales.orders", rows, (), "truncate")
        assert "Clear it first (truncate with no rows), then insert the rows." in str(no.value)
    assert lake_rows(trino) == [(1, "North"), (9, "North")]
    said = adapter.statements(db, "lake.sales.orders", ["order_id", "region"], (), "insert")
    assert said == [
        'INSERT INTO "lake"."sales"."orders" ("order_id", "region") VALUES (?, ?), ...'
        "  -- a batch of rows a statement"
    ]


def test_a_trino_batch_that_fails_says_the_rows_before_it_were_written(trino: TrinoStandIn) -> None:
    db = adapter.Sql(trino, "trino", "Lake")
    rows = pa.table({"order_id": [5, 6, 7], "region": ["A", "B", "C"]})
    trino.refuse = {}
    first = {"done": False}
    original = trino.execute

    def second_fails(sql: str, params: Any = None) -> None:
        if sql.startswith("INSERT") and first["done"]:
            raise RuntimeError("TrinoQueryError: the made-up catalog went away")
        original(sql, params)
        first["done"] = first["done"] or sql.startswith("INSERT")

    trino.execute = second_fails  # type: ignore[method-assign]
    with pytest.raises(RuntimeError) as failed:
        adapter.write(db, "lake.sales.orders", rows.to_reader(max_chunksize=2))
    assert adapter.batch_of(failed.value) == adapter.Batch(2, 2, 1)
    assert "the 2 rows before it were written" in " ".join(failed.value.__notes__)
    assert [r[0] for r in lake_rows(trino)] == [1, 5, 6, 9]  # the first batch stays: no transaction
