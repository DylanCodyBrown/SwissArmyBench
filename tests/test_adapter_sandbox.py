"""A local sandbox API's data through the adapter (Plans/adapter.plan.md, phase 1): the sandbox is its one
backend (sab_adapter.Remote, Arrow IPC both ways through the app's data door), the SharePoint mock's reads and
writes are the adapter's, every SQL mock lists its tables through it, and API.py itself may call
`sab_adapter` by name in its own process. Made-up data only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import sab_adapter
from swissarmybench.server import sandbox_clients as mocks
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests.conftest import AUTH, TOKEN, make_client
from tests.fake_keyring import memory_keyring
from tests.live_server import running
from tests.test_local_api import _ask
from tests.test_sandbox_clients import TestLink, TestRemote, _put

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


def test_the_sharepoint_mock_reads_and_writes_through_the_adapter(boxed: TestClient) -> None:
    lists = mocks.MockSharePoint("Sandbox", TestLink(boxed, mocks.SharePointError))
    found, total = lists.rows("tasks", columns=["title"], filters=[["status", "=", "Open"]], limit=2)
    assert isinstance(found, pa.Table) and found.column_names == ["title"]
    assert found.num_rows == 2 and total == 3
    assert lists.create("tasks", [{"id": 5, "title": "Sweep the path", "status": "Open", "hours": 1}]) == {
        "done": 1
    }
    assert lists.update("tasks", [{"id": 5, "STATUS": "Done"}]) == {"done": 1}
    assert lists.delete("tasks", [1, 5]) == {"done": 2}
    after, total = lists.rows("tasks", filters=[["status", "=", "Done"]])
    assert total == 1 and after.column("id").to_pylist() == [2]
    with pytest.raises(mocks.SharePointError, match="tasks has no column 'colour'"):
        lists.create("tasks", [{"id": 6, "colour": "red"}])
    with pytest.raises(mocks.SharePointError, match="op is one of"):
        lists.rows("tasks", filters=[["status", "~", "Open"]])
    assert [t["table"] for t in lists.tables()] == ["tasks"]


def test_every_sql_mock_lists_its_tables_through_the_adapter(boxed: TestClient) -> None:
    db = mocks.MockDbApi("Sandbox", "sqlite", TestLink(boxed))
    assert db.tables() == ["tasks"]
    assert db.columns("Tasks")[0] == {"name": "id", "type": "BIGINT", "key": False}


API_PY = '''# /// swissarmybench-api
# name = "Garden"
# ///
"""Made-up garden tasks, read and written through the adapter by name."""

import pyarrow as pa
from sab_adapter import Filter, Plan, read, tables, write
from sab_api import endpoint


@endpoint("GET", "/open")
def open_tasks() -> list[dict]:
    plan = Plan(filters=(Filter("status", "=", "Open"),), sort=(("id", False),))
    reader, folded = read("Sandbox", "tasks", plan)
    return [{"id": r["id"], "folded": list(folded.parts)} for r in reader.read_all().to_pylist()]


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
    csv.write_text("id,title,status\n1,Count the shed,Open\n2,Paint the gate,Done\n3,Order seed,Open\n")
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
    finished = _ask(live, "POST", "/local-api/call", {"method": "POST", "path": "/done/3"})
    assert finished["body"] == {"updated": 1, "tables": ["tasks"]}
    again = _ask(live, "POST", "/local-api/call", {"method": "GET", "path": "/open"})
    assert [r["id"] for r in again["body"]] == [1]
    _ask(live, "POST", "/local-api/stop", {})
