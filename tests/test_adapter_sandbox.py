"""A local sandbox API's data through the adapter (Plans/adapter.plan.md, phases 1 and 3): the sandbox is its
one backend (adapter.Remote, Arrow IPC both ways through the app's data door), connection(name) is the
adapter's calls on it, and API.py itself may call `adapter` by name in its own process. Made-up data
only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.conftest import AUTH, TOKEN, make_client
from tests.fake_keyring import memory_keyring
from tests.live_server import running
from tests.test_local_api import _ask
from tests.test_sandbox_query import TestRemote, _put

TASKS = pa.table(
    {
        "id": [1, 2, 3, 4],
        "title": ["Count the shed", "Paint the gate", "Order seed", "Mend the fence"],
        "status": ["Open", "Done", "Open", "Open"],
        "hours": [1.5, 3.0, 0.5, 6.0],
    }
)


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "garden")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "tasks", TASKS)
        yield client


def test_the_sandbox_through_the_adapter_lists_reads_with_a_plan_and_writes(boxed: TestClient) -> None:
    source = TestRemote(boxed, "Sandbox")
    listed = {t.name: t for t in adapter.tables(source)}
    assert [c.name for c in listed["tasks"].columns] == ["id", "title", "status", "hours"]
    plan = adapter.Plan(filters=(adapter.Filter("status", "=", "Open"),), sort=(("hours", True),), limit=2)
    reader, folded = adapter.read(source, "TASKS", plan)
    assert folded.parts == ("filters", "sort", "limit")
    assert reader.read_all().column("title").to_pylist() == ["Mend the fence", "Count the shed"]
    done = adapter.write(
        source, "tasks", pa.table({"id": [2, 9], "status": ["Open", "Open"]}), ("id",), "update"
    )
    assert done == adapter.Counts(updated=1)
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert log["tasks"]["updated"] == 1  # counted as any API write (Reset undoes it)
    with pytest.raises(adapter.AdapterError, match="has no table invoices"):
        adapter.read(source, "invoices")


def test_a_truncate_reaches_the_sandbox_through_the_adapter(boxed: TestClient) -> None:
    source = TestRemote(boxed, "Sandbox")
    fresh = pa.table({"id": [7], "title": ["Sow beans"], "status": ["Open"], "hours": [2.0]})
    done = adapter.write(source, "tasks", fresh, mode="truncate")
    assert done == adapter.Counts(inserted=1, deleted=4)
    assert adapter.read(source, "tasks")[0].read_all().column("id").to_pylist() == [7]
    assert adapter.write(source, "tasks", mode="truncate") == adapter.Counts(deleted=1)
    left = adapter.read(source, "tasks")[0].read_all()
    assert left.num_rows == 0 and left.column_names == ["id", "title", "status", "hours"]
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert (log["tasks"]["inserted"], log["tasks"]["deleted"]) == (1, 5)


API_PY = '''# /// swissarmybench-api
# name = "Garden"
# ///
"""Made-up garden tasks, read and written through the adapter by name."""

import pyarrow as pa
from adapter import Filter, Plan, read, tables, write
from sab_api import connection, endpoint, records


@endpoint("GET", "/open")
def open_tasks() -> list[dict]:
    plan = Plan(filters=(Filter("status", "=", "Open"),), sort=(("id", False),))
    reader, folded = read("Sandbox", "tasks", plan)
    return [{"id": r["id"], "folded": list(folded.parts)} for r in reader.read_all().to_pylist()]


@endpoint("GET", "/hours")
def hours() -> list[dict]:
    db = connection("Sandbox")
    return records(db.query("SELECT status, sum(hours) AS hours FROM tasks GROUP BY status ORDER BY status"))


@endpoint("POST", "/done/{task}")
def finish(task: int) -> dict:
    done = write("Sandbox", "tasks", pa.table({"id": [task], "status": ["Done"]}), key=("id",), mode="update")
    return {"updated": done.updated, "tables": [t.name for t in tables("Sandbox")]}
'''


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    settings = Settings(
        state_dir=tmp_path / "state",
        export_dir=tmp_path / "exports",
        auto_load_catalogs=False,
        projects_dir=tmp_path / "projects",
        workbench_dir=tmp_path / "wb",
    )
    with memory_keyring(), running(lambda port: create_app(port, TOKEN, settings)) as (port, _server):
        yield port


def test_api_py_reads_and_writes_the_sandbox_through_the_adapter_in_its_own_process(
    live: int, tmp_path: Path
) -> None:
    folder = tmp_path / "garden"
    _ask(live, "POST", "/project/new", {"path": str(folder)})
    csv = tmp_path / "tasks.csv"
    csv.write_text(
        "id,title,status,hours\n1,Count the shed,Open,1\n2,Paint the gate,Done,3\n3,Order seed,Open,2\n"
    )
    _ask(live, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    (folder / "API.py").write_text(API_PY, encoding="utf-8")
    # A file of the project's own called adapter.py never stands in for the app's: the host registers the
    # app's adapter before API.py runs, and `python -I` keeps the project's folder off the import path.
    own = 'raise ImportError("the project\'s own adapter.py")\n'
    (folder / "adapter.py").write_text(own, encoding="utf-8")
    ran = _ask(live, "POST", "/local-api/run", {})
    assert ran["running"]["port"], ran.get("failed")
    opened = _ask(live, "POST", "/local-api/call", {"method": "GET", "path": "/open"})
    assert opened["status"] == 200, opened
    assert opened["body"] == [
        {"id": 1, "folded": ["filters", "sort"]},
        {"id": 3, "folded": ["filters", "sort"]},
    ]
    summed = _ask(live, "POST", "/local-api/call", {"method": "GET", "path": "/hours"})
    assert summed["body"] == [{"status": "Done", "hours": 3}, {"status": "Open", "hours": 3}], summed
    finished = _ask(live, "POST", "/local-api/call", {"method": "POST", "path": "/done/3"})
    assert finished["body"] == {"updated": 1, "tables": ["tasks"]}
    again = _ask(live, "POST", "/local-api/call", {"method": "GET", "path": "/open"})
    assert [r["id"] for r in again["body"]] == [1]
    _ask(live, "POST", "/local-api/stop", {})


# ----- adapter 1.6.0: several writes through the door, all or none -----


@pytest.fixture
def two_tables(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "garden")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "tasks", pa.table({"id": [1, 2, 3], "status": ["Open", "Open", "Open"]}))
        _put(client, tmp_path, "audit", pa.table({"id": [9], "task_id": [3], "said": ["Made"]}))
        key = client.post("/sandbox/tables/key", json={"table": "audit", "key": ["id"]}, headers=AUTH)
        assert key.status_code == 200, key.text
        yield client


def test_the_sandbox_through_remote_writes_two_tables_all_or_none(two_tables: TestClient) -> None:
    source = TestRemote(two_tables, "Sandbox")

    def statuses() -> list[str]:
        plan = adapter.Plan(columns=("status",), sort=(("id", False),))
        return list(adapter.read(source, "tasks", plan)[0].read_all().column("status").to_pylist())

    def audit() -> int:
        return int(adapter.read(source, "audit")[0].read_all().num_rows)

    done = pa.table({"id": [1, 2], "status": ["Done", "Done"]})
    taken = pa.table({"id": [9], "task_id": [1], "said": ["the id is taken"]})
    with pytest.raises(adapter.AdapterError, match=r"(?i)key"):
        adapter.write_all(source, [("tasks", done, ["id"], "update"), ("audit", taken)])
    assert statuses() == ["Open", "Open", "Open"] and audit() == 1  # the update rolled back with it
    noted = pa.table({"id": [10, 11], "task_id": [1, 2], "said": ["Closed", "Closed"]})
    counted = adapter.write_all(source, [("tasks", done, ["id"], "update"), ("audit", noted)])
    assert counted == [adapter.Counts(updated=2), adapter.Counts(inserted=2)]
    assert statuses() == ["Done", "Done", "Open"] and audit() == 3
    log = two_tables.get("/sandbox", headers=AUTH).json()["log"]
    assert (log["tasks"]["updated"], log["audit"]["inserted"]) == (2, 2)  # counted as any API write is
    broken = two_tables.post("/sandbox/adapter/write_all", content=b'{"writes": [{"bytes": 9}]}\nabc',
                             headers=AUTH)  # fmt: skip
    assert broken.status_code == 422 and "not what the JSON line said" in broken.json()["error"]


def test_a_connections_planned_counts_through_the_sandbox_and_writes_nothing(two_tables: TestClient) -> None:
    db = adapter.Connection(TestRemote(two_tables, "Sandbox"), "Sandbox")
    keys = [{"id": 2}, {"id": 3}, {"id": 7}]
    assert db.planned("tasks", keys, key="id", mode="merge") == adapter.Counts(inserted=1, updated=2)
    assert db.planned("audit", mode="truncate") == adapter.Counts(deleted=1)
    assert two_tables.get("/sandbox", headers=AUTH).json()["log"].get("tasks", {}).get("updated", 0) == 0
