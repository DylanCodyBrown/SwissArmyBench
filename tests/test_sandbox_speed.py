"""The local sandbox API builder's performance fixes (found by tests/stress/test_local_api_stress.py,
2026-11-21), each held by a rule here so it stays fixed:

- many rows written are one call to the sandbox (they were one HTTP request a row): since phase 3 of the
  adapter, one Arrow write (connection(name).write), all or none;
- two requests at once never see each other's rows (connection(name) keeps no answer: each query is its
  own Arrow stream);
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

from swissarmybench.adapters import adapter
from swissarmybench.adapters.sandbox import SandboxFiles, _Gate
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.server import api_host
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_sandbox_query import TestRemote

# ===== the rules =====


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


class CountingRemote(TestRemote):
    """The adapter's sandbox door through the test's client, counting the calls."""

    __test__ = False

    def __init__(self, client: TestClient) -> None:
        super().__init__(client, "Sandbox")
        self.calls = 0

    def _post(self, path: str, body: bytes) -> Any:
        self.calls += 1
        return super()._post(path, body)


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


def test_many_rows_written_are_one_call_and_every_row_lands_typed(boxed: TestClient) -> None:
    door = CountingRemote(boxed)
    db = adapter.Connection(door)
    rows = [
        {"batch_id": 1, "field": f"f{n % 4}", "value_number": n * 1.5,
         "value_date": f"2026-10-{1 + n % 28:02d}", "value_bool": n % 2 == 0}
        for n in range(20_000)
    ]  # fmt: skip
    assert db.write("entries", rows).inserted == 20_000 and door.calls == 1
    found = (
        db.query(
            "SELECT count(*) AS n, sum(value_number) AS total, min(value_date) AS first, "
            "count(*) FILTER (WHERE value_bool) AS yes FROM entries"
        )
        .read_all()
        .to_pylist()[0]
    )
    assert (found["n"], found["total"], str(found["first"]), found["yes"]) == (
        20_000,
        sum(n * 1.5 for n in range(20_000)),
        "2026-10-01",
        10_000,
    )
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert log["entries"]["inserted"] == 20_000
    # All or none: a bad value and nothing of the write is there.
    with pytest.raises(adapter.AdapterError):
        db.write(
            "entries",
            [{"batch_id": 2, "value_date": "2026-10-01"}, {"batch_id": 2, "value_date": "not a day"}],
        )
    assert db.query("SELECT count(*) AS n FROM entries WHERE batch_id = 2").read_all().to_pylist() == [
        {"n": 0}
    ]


def test_two_requests_at_once_never_see_each_others_rows(boxed: TestClient) -> None:
    db = adapter.Connection(CountingRemote(boxed))
    db.write("entries", [{"batch_id": b, "field": f"b{b}"} for b in range(8)])
    wrong: list[str] = []
    ready = threading.Barrier(8, timeout=10)

    def one(batch: int) -> None:
        ready.wait()
        for _ in range(10):
            answer = db.query("SELECT field FROM entries WHERE batch_id = ?", [batch])
            time.sleep(0.001)
            got = answer.read_all().to_pylist()
            if got != [{"field": f"b{batch}"}]:
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
