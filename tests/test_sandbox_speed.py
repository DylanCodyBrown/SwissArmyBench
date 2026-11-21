"""The local sandbox API builder's performance fixes (found by tests/stress/test_local_api_stress.py,
2026-11-21), each held by a rule here so it stays fixed:

- executemany is one call to the sandbox (it was one HTTP request a row), and a plain INSERT ... VALUES of
  its marks goes in as one columnar insert (DuckDB's own executemany took 120 s for 100k rows);
- connection("Sandbox") is one object, so what execute() answered is kept per thread (two requests at once
  fetched each other's rows);
- a statement's translation is made once (sqlglot parsed every call);
- the tables' names are read once until one is added or dropped (every call counted every table's rows);
- reads share the file: two at once are not queued behind one lock;
- the hosting process's socket says TCP, so asyncio sets TCP_NODELAY (each kept-open request waited ~40 ms).
Made-up data only."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.sandbox import SandboxFiles, _Gate
from swissarmybench.domain import sandbox as rules
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.server import api_host
from swissarmybench.server import sandbox_clients as mocks
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring

# ===== the rules =====


def test_an_executemany_is_translated_once_and_each_set_ordered_by_its_marks() -> None:
    made, values = dialects.to_duckdb_many(
        "INSERT INTO dbo.entries (a, b) VALUES (?, ?)", "sqlserver", [[1, "x"], [2, "y"]], ["entries"]
    )
    assert made.sql == 'INSERT INTO "entries" (a, b) VALUES ($1, $2)' and values == [[1, "x"], [2, "y"]]
    assert dialects.plain_insert(made.sql) == ("entries", ("a", "b"), 2)
    named, values = dialects.to_duckdb_many(
        "INSERT INTO entries (a, b) VALUES (:b, :a)",
        "oracle",
        [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        ["entries"],
    )
    assert values == [[2, 1], [4, 3]] and dialects.plain_insert(named.sql) == ("entries", ("a", "b"), 2)
    with pytest.raises(rules.SandboxError, match="Parameter set 2"):
        dialects.to_duckdb_many("INSERT INTO entries VALUES (?, ?)", "duckdb", [[1, 2], [3]], ["entries"])


def test_only_a_plain_insert_of_its_marks_goes_in_as_columns() -> None:
    for sql in (
        'INSERT INTO "t" (a, b) VALUES ($1, 5)',
        'INSERT INTO "t" (a) VALUES ($1), ($2)',
        'INSERT INTO "t" (a) SELECT $1',
        'UPDATE "t" SET a = $1',
        'INSERT INTO "t" (a) VALUES ($1) RETURNING a',
    ):
        assert dialects.plain_insert(sql) is None, sql
    assert dialects.plain_insert('INSERT INTO "t" VALUES ($1, $2, $3)') == ("t", None, 3)


def test_a_statement_is_parsed_once_whatever_its_values() -> None:
    dialects._translate.cache_clear()
    for n in range(50):
        dialects.to_duckdb(
            "SELECT * FROM orders WHERE region = ? AND n > ?", "sqlserver", ["West", n], ["orders"]
        )
    found = dialects._translate.cache_info()
    assert found.misses == 1 and found.hits == 49


def test_the_gate_lets_readers_share_and_keeps_a_holder_alone() -> None:
    gate = _Gate()
    inside = []
    both = threading.Barrier(2, timeout=5)

    def read() -> None:
        with gate.shared():
            both.wait()  # both readers inside at once, or this times out
            inside.append(1)

    threads = [threading.Thread(target=read) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert inside == [1, 1]
    order: list[str] = []
    with gate.exclusive():
        with gate.exclusive(), gate.shared():  # re-entrant for its holder
            order.append("held")

        def read_after() -> None:
            with gate.shared():
                order.append("read")

        reader = threading.Thread(target=read_after)
        reader.start()
        time.sleep(0.2)
        order.append("released")
    reader.join(5)
    assert order == ["held", "released", "read"]


def test_the_table_names_are_read_once_until_a_table_comes_or_goes(tmp_path: Path) -> None:
    import pyarrow as pa

    files = SandboxFiles(str(tmp_path))
    files.put_table("orders", pa.table({"id": [1, 2]}), False)
    assert files.table_names() == ["orders"]
    files._all("CREATE TABLE behind_its_back (id INTEGER)")  # not through the files: not seen
    assert files.table_names() == ["orders"]
    files.put_table("regions", pa.table({"id": [1]}), False)
    assert files.table_names() == ["behind_its_back", "orders", "regions"]
    files.drop("behind_its_back")
    assert files.table_name("ORDERS") == "orders" and files.table_name("behind_its_back") is None
    files.close()


# ===== through the app =====


class CountingLink(mocks.Link):
    """The mock's door through the test's client, counting the calls."""

    def __init__(self, client: TestClient) -> None:
        super().__init__("http://127.0.0.1:9/sandbox/data")
        self.client = client
        self.calls = 0

    def ask(self, op: str, **body: Any) -> dict[str, Any]:
        self.calls += 1
        answer = self.client.post("/sandbox/data", json={"op": op} | body, headers=AUTH)
        if answer.status_code != 200:
            raise self.error(answer.json()["error"])
        return dict(answer.json())


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        assert (
            client.post("/project/new", json={"path": str(tmp_path / "ledger")}, headers=AUTH).status_code
            == 200
        )
        made = client.post(
            "/sandbox/tables",
            json={"from": "columns", "name": "entries", "columns": [
                {"name": "batch_id", "type": "integer"}, {"name": "field", "type": "text"},
                {"name": "value_number", "type": "number"}, {"name": "value_date", "type": "date"},
                {"name": "value_bool", "type": "yes/no"}]},
            headers=AUTH,
        )  # fmt: skip
        assert made.status_code == 200, made.text
        yield client


def test_executemany_is_one_call_and_every_row_lands_typed(boxed: TestClient) -> None:
    link = CountingLink(boxed)
    db = mocks.MockDuckDB(link)
    rows = [(1, f"f{n % 4}", n * 1.5, f"2026-10-{1 + n % 28:02d}", n % 2 == 0) for n in range(20_000)]
    db.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?)", rows)
    assert link.calls == 1 and db.rowcount == 20_000
    db.execute(
        "SELECT count(*), sum(value_number), min(value_date), count(*) FILTER (WHERE value_bool) FROM entries"
    )
    found = db.fetchone()
    assert found is not None
    count, total, first, yes = found
    assert (count, total, str(first), yes) == (
        20_000,
        sum(n * 1.5 for n in range(20_000)),
        "2026-10-01",
        10_000,
    )
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert log["entries"]["inserted"] == 20_000
    # Any other statement: one call too, one transaction, each set in turn.
    db.executemany("UPDATE entries SET value_number = ? WHERE field = ?", [(0, "f0"), (1, "f1")])
    assert link.calls == 3 and db.rowcount == 10_000
    # All or none: a bad set and nothing of the part is written.
    with pytest.raises(mocks.MockError):
        db.executemany(
            "INSERT INTO entries (batch_id, value_date) VALUES (?, ?)", [(2, "2026-10-01"), (2, "not a day")]
        )
    db.execute("SELECT count(*) FROM entries WHERE batch_id = 2")
    assert db.fetchone() == (0,)


def test_two_requests_at_once_never_fetch_each_others_rows(boxed: TestClient) -> None:
    db = mocks.MockDuckDB(CountingLink(boxed))
    db.executemany("INSERT INTO entries (batch_id, field) VALUES (?, ?)", [(b, f"b{b}") for b in range(8)])
    wrong: list[str] = []
    ready = threading.Barrier(8, timeout=10)

    def one(batch: int) -> None:
        ready.wait()
        for _ in range(10):
            db.execute("SELECT field FROM entries WHERE batch_id = ?", [batch])
            time.sleep(0.001)
            got = db.fetchall()
            if got != [(f"b{batch}",)]:
                wrong.append(f"{batch}: {got}")

    threads = [threading.Thread(target=one, args=(b,)) for b in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert wrong == []


def test_the_hosting_socket_says_tcp_so_answers_are_not_held_back() -> None:
    import inspect

    source = inspect.getsource(api_host.main)
    assert "socket.IPPROTO_TCP" in source
