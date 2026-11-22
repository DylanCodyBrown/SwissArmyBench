"""sab.write (Plans/simplify-decisions.plan.md, "one sab.write through the adapter"): the app's client's one
write, `sab.write(connection, table, rows, mode, key=None, dry_run=False)`, for every source the adapter
writes. The connection is the kernel's own (sab.connection, signed in its own way), wrapped in its backend by
adapter.source_from; rows are a DataFrame, an Arrow table, a list of dicts or an open table's name; a
dry run counts by reads (adapter.planned) and writes nothing. Made-up data only."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import swissarmybench
from swissarmybench.client import writes
from swissarmybench.client.writes import WriteError


@pytest.fixture
def shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A made-up shop's SQLite file, opened read-only as the SQLite connection opens it."""
    file = tmp_path / "shop.sqlite"
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, region TEXT, amount REAL)")
        db.execute("INSERT INTO orders VALUES (1, 'North', 10.0), (9, 'North', 90.0)")

    def connection(name: str) -> Any:
        assert name == "Shop"
        return sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True)

    monkeypatch.setattr(swissarmybench, "connection", connection, raising=False)
    return file


def rows_of(file: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(file) as db:
        return db.execute("SELECT * FROM orders ORDER BY 1").fetchall()


def test_every_mode_writes_through_the_adapter_and_counts(shop: Path) -> None:
    new = pa.table({"order_id": [2, 3], "region": ["East", "West"], "amount": [2.0, 3.0]})
    done = swissarmybench.write("Shop", "orders", new)  # insert, written at once
    assert done.counts == {"inserted": 2} and str(done).startswith("Wrote orders on Shop: inserted 2 rows")
    merged = pd.DataFrame({"order_id": [1, 4], "region": ["South", "East"], "amount": [1.5, 4.0]})
    assert swissarmybench.write("Shop", "orders", merged, "merge", key="order_id").counts == {
        "updated": 1,
        "inserted": 1,
    }
    changed = [{"order_id": 9, "region": "Far North", "amount": 99.0}]
    assert swissarmybench.write("Shop", "orders", changed, "update", ["order_id"]).counts == {"updated": 1}
    assert swissarmybench.write(
        "Shop", "orders", [{"order_id": 2}, {"order_id": 77}], "delete", "order_id"
    ).counts == {"deleted": 1}
    assert rows_of(shop) == [(1, "South", 1.5), (3, "West", 3.0), (4, "East", 4.0), (9, "Far North", 99.0)]
    cleared = swissarmybench.write("Shop", "orders", None, "truncate")
    assert cleared.counts == {"deleted": 4, "inserted": 0} and rows_of(shop) == []


def test_a_dry_run_counts_by_reads_and_writes_nothing(shop: Path) -> None:
    rows = pa.table({"order_id": [1, 2, 3], "region": ["a", "b", "c"], "amount": [0.0, 0.0, 0.0]})
    dry = swissarmybench.write("Shop", "orders", rows, mode="merge", key="order_id", dry_run=True)
    assert dry.counts is None and dry.planned == {"updated": 1, "inserted": 2}
    assert str(dry).startswith("Dry run: nothing was written.")
    assert rows_of(shop) == [(1, "North", 10.0), (9, "North", 90.0)]


def test_an_open_tables_name_is_rows_too(shop: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def table(name: str) -> pa.Table:
        asked.append(name)
        return pa.table({"order_id": [5], "region": ["West"], "amount": [5.0]})

    monkeypatch.setattr(swissarmybench, "table", table, raising=False)
    assert swissarmybench.write("Shop", "orders", "new_orders").counts == {"inserted": 1}
    assert asked == ["new_orders"] and rows_of(shop)[1] == (5, "West", 5.0)


def test_a_file_connection_writes_a_file_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "exports"
    folder.mkdir()
    monkeypatch.setattr(swissarmybench, "connection", lambda name: str(folder), raising=False)
    rows = pa.table({"region": ["North", "South"], "amount": [1.0, 2.0]})
    assert swissarmybench.write("Exports", "regions.parquet", rows, "truncate").counts == {
        "deleted": 0,
        "inserted": 2,
    }
    assert pq.read_table(folder / "regions.parquet").num_rows == 2


def test_wrong_modes_keys_and_rows_are_refused_in_one_sentence(shop: Path) -> None:
    rows = pa.table({"order_id": [1]})
    with pytest.raises(WriteError, match="mode is one of insert, update, merge, delete, truncate"):
        swissarmybench.write("Shop", "orders", rows, "upsert")
    with pytest.raises(WriteError, match="names the key"):
        swissarmybench.write("Shop", "orders", rows, "merge")
    with pytest.raises(WriteError, match="rows are a DataFrame, an Arrow table, a list of dicts"):
        swissarmybench.write("Shop", "orders", 42)
    with pytest.raises(WriteError, match=r"batch 1 \(rows 1 to 1\) failed: UNIQUE"):
        swissarmybench.write("Shop", "orders", pa.table({"order_id": [9], "region": ["x"], "amount": [0.0]}))
    assert rows_of(shop) == [(1, "North", 10.0), (9, "North", 90.0)]


def test_the_child_process_job_answers_what_the_agent_sees(shop: Path) -> None:
    """The agent's connections_write runs the same function in a child process: its answer is the counts and
    the report's words, never a row beyond the report's 5-row sample."""
    rows = pa.table({"order_id": [3], "region": ["West"], "amount": [3.0]})
    opened: Callable[[], Any] = lambda: swissarmybench.connection("Shop")  # noqa: E731
    answer = writes.answer(writes.write_with("Shop", opened(), "orders", rows, "insert", None, True))
    assert answer["dry_run"] is True and answer["planned"] == {"inserted": 1} and answer["counts"] is None
    assert answer["said"].startswith("Dry run: nothing was written.")


def test_the_agents_write_waits_for_the_users_allow(tmp_path: Path) -> None:
    """connections_write (POST /connections/{name}/write): sab.write for the agent, run in a child process
    as every connection run is. A dry run needs no Allow; a write to the live source waits for it. Rows are
    records or an open table's name (its grid's view)."""
    from tests.conftest import AGENT, AUTH, make_client, push
    from tests.streamlit_helpers import answering
    from tests.test_connection_tables import sqlite_connection

    with make_client(tmp_path) as client:
        sqlite_connection(
            client,
            tmp_path,
            "Shop",
            {"orders": ("order_id INTEGER PRIMARY KEY, region TEXT", [(1, "North")])},
        )
        pending = lambda: client.get("/agent/approvals", headers=AUTH).json()["pending"]  # noqa: E731

        def answer(request: str, yes: bool) -> Any:
            return client.post(f"/agent/approvals/{request}", headers=AUTH, json={"approve": yes})

        body = {"table": "orders", "rows": [{"order_id": 2, "region": "East"}], "mode": "insert"}
        dry = client.post("/connections/Shop/write", headers=AGENT, json=body | {"dry_run": True})
        assert dry.status_code == 200, dry.text
        assert dry.json()["planned"] == {"inserted": 1} and dry.json()["counts"] is None
        with answering(pending, answer, approve=False) as asked:
            declined = client.post("/connections/Shop/write", headers=AGENT, json=body)
        assert declined.status_code == 403 and "Write 1 row to orders on Shop (insert)" in asked[0]["detail"]
        with answering(pending, answer, approve=True):
            done = client.post("/connections/Shop/write", headers=AGENT, json=body)
        assert done.status_code == 200, done.text
        assert done.json()["counts"] == {"inserted": 1}
        assert push(client, "more_orders", pa.table({"order_id": [3], "region": ["West"]})).status_code == 200
        merged = {"table": "orders", "from_table": "more_orders", "mode": "merge", "key": "order_id"}
        assert client.post("/connections/Shop/write", headers=AUTH, json=merged).json()["counts"] == {
            "updated": 0,
            "inserted": 1,
        }
        with sqlite3.connect(tmp_path / "Shop.sqlite") as db:
            assert db.execute("SELECT order_id FROM orders ORDER BY 1").fetchall() == [(1,), (2,), (3,)]
        wrong = client.post(
            "/connections/Shop/write", headers=AUTH, json={"table": "orders", "mode": "upsert"}
        )
        assert (
            wrong.status_code == 400
            and "mode is one of insert, update, merge, delete, truncate" in wrong.text
        )


def test_the_agents_modes_are_the_adapters() -> None:
    from swissarmybench.adapters import adapter
    from swissarmybench.domain import write_capability

    assert write_capability.WRITE_MODES == adapter.MODES
    assert write_capability.KEYED_MODES == adapter.KEYED
