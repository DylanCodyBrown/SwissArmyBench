"""Each connection's slots over HTTP: the limits kept in its library file's [queries] table (checked, byte
stable), the counts, a slow made-up SQLite connection whose second query waits in line with its place and
is cancelled, the finished list and its Clear, a query's SQL shown to the user only, a kernel's leased slot.
Made-up data only."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def slow_connection(
    client: TestClient, tmp_path: Path, name: str = "Slow Shop", seconds: float = 1.5
) -> None:
    """A made-up SQLite connection that takes `seconds` to connect (a slow server stood in for)."""
    path = tmp_path / "slow.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, amount REAL)")
        made.executemany("INSERT INTO orders VALUES (?, ?)", [(i, i * 2.5) for i in range(1, 6)])
    body = {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nimport time\nfrom pathlib import Path\n\n"
            f"time.sleep({seconds})\n"
            f'path = Path(r"{path}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
    }
    ok(client.post("/connections", json=body, headers=AUTH))


def library_file(tmp_path: Path, name: str) -> Path:
    found = [p for p in (tmp_path).rglob("*.blade.py") if name.replace(" ", "") in p.name.replace(" ", "")]
    found = found or [p for p in tmp_path.rglob("*.blade.py") if name in p.read_text(encoding="utf-8")]
    assert found, "no library file"
    return found[0]


def test_limits_are_checked_kept_in_the_file_and_shown(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        slow_connection(client, tmp_path, seconds=0)
        limits = ok(client.get("/connections/Slow%20Shop/limits", headers=AUTH))
        assert (limits["total"], limits["agent"], limits["wait"]) == (8, 4, 120)
        file = library_file(tmp_path, "Slow Shop")
        assert "[queries]" not in file.read_text(encoding="utf-8")  # the defaults change no file
        bad = client.put("/connections/Slow%20Shop/limits", json={"total": 4, "agent": 6}, headers=AUTH)
        assert bad.status_code == 400 and "at most" in bad.json()["error"]
        assert (
            client.put("/connections/Slow%20Shop/limits", json={"total": 65}, headers=AUTH).status_code == 400
        )
        ok(client.put("/connections/Slow%20Shop/limits", json={"total": 12, "agent": 3}, headers=AGENT))
        text = file.read_text(encoding="utf-8")
        assert "# [queries]" in text and "# total = 12" in text and "# agent = 3" in text
        ok(client.put("/connections/Slow%20Shop/limits", json={"total": 12, "agent": 3}, headers=AUTH))
        assert file.read_text(encoding="utf-8") == text  # the same limits: the same bytes
        # A save from the form keeps them.
        saved = ok(client.get("/connections/Slow%20Shop", headers=AUTH))
        assert saved
        slots = ok(client.get("/connections/slots", headers=AGENT))
        mine = next(c for c in slots["connections"] if c["connection"] == "Slow Shop")
        assert mine["limits"] == {"total": 12, "agent": 3, "wait": 120} and mine["words"] == "Running 0 of 12"


def test_a_second_query_waits_in_line_shows_its_place_and_cancel_frees_it(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        slow_connection(client, tmp_path, seconds=1.0)
        ok(client.put("/connections/Slow%20Shop/limits", json={"total": 1}, headers=AUTH))
        answers: dict[str, Any] = {}

        def run(key: str, headers: dict[str, str]) -> None:
            body = {"sql": "SELECT count(*) AS n FROM [Slow Shop].orders"}
            answers[key] = client.post(f"/datasets/{key}/query", json=body, headers=headers)

        first = threading.Thread(target=run, args=("first_read", AUTH | {"X-Sab-Client": "page-one"}))
        first.start()
        time.sleep(0.4)
        second = threading.Thread(target=run, args=("second_read", AGENT))
        second.start()
        deadline = time.time() + 10
        listed: dict[str, Any] = {}
        while time.time() < deadline:
            listed = ok(client.get("/connections/queries?connection=Slow%20Shop", headers=AGENT))
            if any(q["who"] == "The agent" and q["state"] == "waiting" for q in listed["queries"]):
                break
            time.sleep(0.05)
        states = {q["who"]: q for q in listed["queries"]}
        assert states["You"]["state"] == "running" and states["You"]["client"] == "page-one"
        assert states["You"]["what"] in ("catalog listing", "table read")
        waiting = states["The agent"]
        assert waiting["state"] == "waiting" and waiting["place"] == 1
        assert waiting["words"] == "Waiting: 1st in line for Slow Shop (1 query running)"
        assert all("sql" not in q for q in listed["queries"])
        assert listed["connections"][0]["full_words"] == "Running 1 of 1 · 1 waiting · agent 0 of 1"
        # The SQL is the user's only.
        running_id = states["You"]["id"]
        assert client.get(f"/connections/queries/{running_id}/sql", headers=AGENT).status_code == 403
        ok(client.post(f"/connections/queries/{waiting['id']}/cancel", json={}, headers=AGENT))  # its own
        second.join(20)
        assert (
            answers["second_read"].status_code == 408
            and "Cancelled" in answers["second_read"].json()["error"]
        )
        first.join(40)
        assert answers["first_read"].status_code == 200, answers["first_read"].text
        done = ok(client.get("/connections/queries", headers=AUTH))
        assert {f["outcome"] for f in done["finished"] if f["who"] == "You"} == {"ok"}
        assert [f["outcome"] for f in done["finished"] if f["who"] == "The agent"] == ["cancelled"]
        assert done["queries"] == []
        ok(client.post("/connections/queries/clear", json={}, headers=AUTH))
        assert ok(client.get("/connections/queries", headers=AUTH))["finished"] == []


def test_the_page_cancels_its_own_waiting_query(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        slow_connection(client, tmp_path, seconds=1.0)
        ok(client.put("/connections/Slow%20Shop/limits", json={"total": 1}, headers=AUTH))
        answers: dict[str, Any] = {}

        def run(key: str, client_id: str) -> None:
            body = {"sql": "SELECT * FROM [Slow Shop].orders"}
            headers = AUTH | {"X-Sab-Client": client_id}
            answers[key] = client.post(f"/datasets/{key}/query", json=body, headers=headers)

        threads = [threading.Thread(target=run, args=(k, k)) for k in ("one", "two")]
        threads[0].start()
        time.sleep(0.4)
        threads[1].start()
        deadline = time.time() + 10
        while time.time() < deadline:
            queued = ok(client.get("/connections/queries", headers=AUTH))["queries"]
            if any(q.get("client") == "two" and q["state"] == "waiting" for q in queued):
                break
            time.sleep(0.05)
        said = ok(
            client.post("/connections/queries/cancel-mine", json={}, headers=AUTH | {"X-Sab-Client": "two"})
        )
        assert len(said["cancelled"]) == 1
        for thread in threads:
            thread.join(40)
        assert answers["two"].status_code == 408 and answers["one"].status_code == 200


def test_a_kernels_slot_and_the_sql_formatted_for_the_user(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        kernel = AUTH | {"X-Kernel": "abc123"}
        body = {
            "connection": "Warehouse",
            "kind": "query",
            "sql": "select a, b from sales where c = '${REGION}'",
        }
        got = ok(client.post("/connections/slots/acquire", json=body, headers=kernel))
        assert got["state"] == "running"
        listed = ok(client.get("/connections/queries", headers=AUTH))["queries"]
        assert listed[0]["who"] == "A Workbench kernel" and listed[0]["kernel"] == "abc123"
        sql = ok(client.get(f"/connections/queries/{got['ticket']}/sql", headers=AUTH))
        assert sql["sql"] == body["sql"] and sql["formatted"].startswith("SELECT")
        assert "'${REGION}'" in sql["formatted"]
        assert (
            ok(client.post(f"/connections/slots/{got['ticket']}/renew", json={}, headers=kernel))["state"]
            == "running"
        )
        ok(client.post(f"/connections/slots/{got['ticket']}/release", json={"outcome": "ok"}, headers=kernel))
        assert ok(client.get("/connections/queries", headers=AUTH))["finished"][0]["outcome"] == "ok"
        assert client.post("/connections/slots/acquire", json=body, headers=AUTH).status_code == 400
