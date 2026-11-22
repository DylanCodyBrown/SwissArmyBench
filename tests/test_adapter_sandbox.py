"""A local sandbox API's data through the adapter (Plans/adapter.plan.md, phases 1 and 3): the sandbox is its
one backend (sab_adapter.Remote, Arrow IPC both ways through the app's data door), connection(name) is the
adapter's calls on it, and API.py itself may call `sab_adapter` by name in its own process. Made-up data
only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import sab_adapter
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
    listed = {t.name: t for t in sab_adapter.tables(source)}
    assert [c.name for c in listed["tasks"].columns] == ["id", "title", "status", "hours"]
    plan = sab_adapter.Plan(
        filters=(sab_adapter.Filter("status", "=", "Open"),), sort=(("hours", True),), limit=2
    )
    reader, folded = sab_adapter.read(source, "TASKS", plan)
    assert folded.parts == ("filters", "sort", "limit")
    assert reader.read_all().column("title").to_pylist() == ["Mend the fence", "Count the shed"]
    done = sab_adapter.write(
        source, "tasks", pa.table({"id": [2, 9], "status": ["Open", "Open"]}), ("id",), "update"
    )
    assert done == sab_adapter.Counts(updated=1)
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert log["tasks"]["updated"] == 1  # counted as any API write (Reset undoes it)
    with pytest.raises(sab_adapter.AdapterError, match="has no table invoices"):
        sab_adapter.read(source, "invoices")


def test_a_truncate_reaches_the_sandbox_through_the_adapter(boxed: TestClient) -> None:
    source = TestRemote(boxed, "Sandbox")
    fresh = pa.table({"id": [7], "title": ["Sow beans"], "status": ["Open"], "hours": [2.0]})
    done = sab_adapter.write(source, "tasks", fresh, mode="truncate")
    assert done == sab_adapter.Counts(inserted=1, deleted=4)
    assert sab_adapter.read(source, "tasks")[0].read_all().column("id").to_pylist() == [7]
    assert sab_adapter.write(source, "tasks", mode="truncate") == sab_adapter.Counts(deleted=1)
    left = sab_adapter.read(source, "tasks")[0].read_all()
    assert left.num_rows == 0 and left.column_names == ["id", "title", "status", "hours"]
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert (log["tasks"]["inserted"], log["tasks"]["deleted"]) == (1, 5)


API_PY = '''# /// swissarmybench-api
# name = "Garden"
# ///
"""Made-up garden tasks, read and written through the adapter by name."""

import pyarrow as pa
from sab_adapter import Filter, Plan, read, tables, write
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
