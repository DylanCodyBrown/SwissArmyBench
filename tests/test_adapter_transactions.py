"""Several writes on one connection, all of them or none (adapter 1.6.0: write_all; docs/ideas.md "The
endpoint wizard and its patterns": an action that sets a status and adds its audit row), and a write's dry
run through the connection object (1.7.0: Connection.planned). Each against every backend it touches: DuckDB
(a file), SQLite, SQL Server (tests/sqlserver_standin.py: a passing error runs the whole set again), Trino's
refusal, and the sources that cannot (Dataverse's Web API, the lakes and SharePoint, files, a workbook); the
sandbox through Remote is tests/test_adapter_sandbox.py's. Made-up rows only."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter
from swissarmybench.adapters.adapter import Counts, Write
from tests import sqlserver_standin as standin
from tests.sqlserver_standin import Column
from tests.test_adapter_trino import TrinoStandIn

DONE = pa.table({"id": [1, 2], "status": ["Done", "Done"]})
NOTED = pa.table(
    {"id": [10, 11], "task_id": [1, 2], "said": ["Closed by the gardener", "Closed by the gardener"]}
)
TWICE = pa.table({"id": [10, 10], "task_id": [1, 2], "said": ["one", "the same id again"]})


def _both(audit: pa.Table = NOTED) -> list[Write]:
    return [Write("tasks", DONE, ("id",), "update"), Write("audit", audit, mode="insert")]


@pytest.fixture
def shop(tmp_path: Path) -> str:
    path = str(tmp_path / "garden.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, status VARCHAR)")
    con.execute("INSERT INTO tasks VALUES (1, 'Open'), (2, 'Open'), (3, 'Open')")
    con.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, task_id INTEGER, said VARCHAR)")
    con.close()
    return path


def _statuses(source: Any) -> list[Any]:
    found = adapter.read(source, "tasks", adapter.Plan(columns=("status",), sort=(("id", False),)))[0]
    return found.read_all().column("status").to_pylist()


def _audit(source: Any) -> int:
    return len(adapter.read(source, "audit")[0].read_all())


def test_duckdb_writes_two_tables_all_or_none(shop: str) -> None:
    source = adapter.DuckDB.file(shop)
    done = adapter.write_all(source, _both())
    assert done == [Counts(updated=2), Counts(inserted=2)]
    assert _statuses(source) == ["Done", "Done", "Open"] and _audit(source) == 2
    again = [Write("tasks", pa.table({"id": [3], "status": ["Done"]}), ("id",), "update"),
             Write("audit", TWICE)]  # fmt: skip
    with pytest.raises(duckdb.ConstraintException):
        adapter.write_all(source, again)
    assert _statuses(source) == ["Done", "Done", "Open"] and _audit(source) == 2  # task 3 not changed either


def test_a_connection_takes_its_writes_as_dicts_and_lists(shop: str) -> None:
    db = adapter.Connection(adapter.DuckDB.file(shop), "Garden")
    done = db.write_all(
        [
            {"table": "tasks", "rows": [{"id": 3, "status": "Done"}], "key": ["id"], "mode": "update"},
            ("audit", [{"id": 12, "task_id": 3, "said": "Closed"}]),
        ]
    )
    assert [d.rows for d in done] == [1, 1]
    assert adapter.write_all(db.source, []) == []
    with pytest.raises(adapter.AdapterError, match="A update names the key"):
        db.write_all([{"table": "tasks", "rows": [{"id": 3, "status": "Open"}], "mode": "update"}])


def test_sqlite_writes_two_tables_all_or_none(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "garden.db")
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, status TEXT)")
    con.executemany("INSERT INTO tasks VALUES (?, 'Open')", [(1,), (2,), (3,)])
    con.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, task_id INTEGER, said TEXT)")
    con.commit()
    source = adapter.Sql(con, "sqlite", "Garden")
    with pytest.raises(sqlite3.IntegrityError):
        adapter.write_all(source, _both(TWICE))
    assert _statuses(source) == ["Open", "Open", "Open"] and _audit(source) == 0
    assert adapter.write_all(source, _both()) == [Counts(updated=2), Counts(inserted=2)]
    assert _statuses(source) == ["Done", "Done", "Open"] and _audit(source) == 2


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[standin.Server]:
    made = standin.Server()
    made.table("dbo.tasks", [Column("id", "int", key=True), Column("status", "nvarchar(20)")],
               [(1, "Open"), (2, "Open"), (3, "Open")])  # fmt: skip
    made.table("dbo.audit", [Column("id", "int", key=True), Column("task_id", "int"),
                             Column("said", "nvarchar(80)")])  # fmt: skip
    monkeypatch.setitem(sys.modules, "mssql_python", made.module())
    monkeypatch.delitem(sys.modules, "pyodbc", raising=False)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    yield made


def test_sql_server_writes_two_tables_in_one_transaction_and_runs_them_again_whole(
    server: standin.Server,
) -> None:
    link = standin.Error(
        "Driver Error: Communication link failure; DDBC Error: [Microsoft]TCP Provider: Error code 0x2746"
    )
    server.failures = [("INSERT INTO [dbo].[audit]", link)]
    db = adapter.Sql(server.connect(), "sqlserver", "Warehouse", reopen=server.connect)
    plain = [Write("dbo.tasks", DONE, ("id",), "update"), Write("dbo.audit", NOTED)]
    done = adapter.write_all(db, plain)
    assert (done[0].updated, done[1].inserted) == (2, 2)
    assert done[1].notes and done[1].notes[0].startswith("Try 1 met a passing error")  # said on the last
    assert server.rows("dbo.tasks") == [(1, "Done"), (2, "Done"), (3, "Open")]
    assert len(server.rows("dbo.audit")) == 2  # once: the failed try rolled back whole
    refused = standin.Error(
        "Driver Error: Integrity constraint violation; DDBC Error: Violation of PRIMARY KEY"
    )
    server.failures = [("INSERT INTO [dbo].[audit]", refused)]
    again = [Write("dbo.tasks", pa.table({"id": [3], "status": ["Done"]}), ("id",), "update"),
             Write("dbo.audit", pa.table({"id": [20], "task_id": [3], "said": ["x"]}))]  # fmt: skip
    with pytest.raises(standin.Error):
        adapter.write_all(db, again)
    assert server.rows("dbo.tasks")[2] == (3, "Open")  # rolled back with the audit row


def test_trino_and_the_sources_without_a_transaction_refuse_two_writes_and_write_nothing(
    trino: TrinoStandIn, tmp_path: Path
) -> None:
    lake = adapter.Sql(trino, "trino", "Lake")
    two = [Write("sales.orders", pa.table({"order_id": [5], "region": ["East"]})),
           Write("sales.orders", pa.table({"order_id": [6], "region": ["West"]}))]  # fmt: skip
    with pytest.raises(
        adapter.AdapterError, match=r"^Lake cannot make several writes all or none \(it writes"
    ):
        adapter.write_all(lake, two)
    assert trino.statements == []  # nothing sent
    assert adapter.write_all(lake, two[:1]) == [Counts(inserted=1, notes=(adapter.NO_TRANSACTION,))]
    for source, why in (
        (adapter.OData(object(), "Dataverse"), "one change set"),
        (adapter.Rows(object(), "Lake files"), "its service's own call"),
        (adapter.Files(str(tmp_path), "Shop files"), "replaced on its own"),
        (adapter.Excel(str(tmp_path / "book.xlsx"), "Book"), "written on its own"),
    ):
        with pytest.raises(adapter.AdapterError, match=why):
            adapter.write_all(source, two)


@pytest.fixture
def trino(monkeypatch: pytest.MonkeyPatch) -> TrinoStandIn:
    import types

    fake = types.ModuleType("trino")
    fake.paramstyle = "qmark"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trino", fake)
    return TrinoStandIn()


# ----- 1.7.0: a write's dry run through the connection object -----

UPLOAD = [{"id": 2, "status": "Done"}, {"id": 3, "status": "Done"}, {"id": 4, "status": "New"}]


def test_a_connections_planned_says_what_its_write_would_do_and_writes_nothing(shop: str) -> None:
    db = adapter.Connection(adapter.DuckDB.file(shop), "Garden")
    assert db.planned("tasks", UPLOAD, key=["id"], mode="merge") == Counts(inserted=1, updated=2)
    assert db.planned("tasks", pa.table({"id": [1, 9]}), key="id", mode="delete") == Counts(deleted=1)
    assert db.planned("tasks", mode="truncate") == Counts(deleted=3)
    assert db.planned("tasks", UPLOAD) == Counts(inserted=3)
    assert _statuses(db.source) == ["Open", "Open", "Open"]  # nothing written
    with pytest.raises(adapter.AdapterError, match="A merge names the key"):
        db.planned("tasks", UPLOAD, mode="merge")


def test_planned_through_sqlite_and_sql_servers_own_dry_run(tmp_path: Path, server: standin.Server) -> None:
    con = sqlite3.connect(tmp_path / "garden.db")
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, status TEXT)")
    con.executemany("INSERT INTO tasks VALUES (?, 'Open')", [(1,), (2,), (3,)])
    con.commit()
    lite = adapter.Connection(adapter.Sql(con, "sqlite", "Garden"))
    assert lite.planned("tasks", UPLOAD, key=["id"], mode="merge") == Counts(inserted=1, updated=2)
    warehouse = adapter.Connection(adapter.Sql(server.connect(), "sqlserver", "Warehouse"))
    keys = pa.table({"id": pa.array([2, 3, 4], pa.int64())})  # the keys alone: what a dry run needs
    assert warehouse.planned("dbo.tasks", keys, key=["id"], mode="merge") == Counts(inserted=1, updated=2)
    assert any(s.startswith("CREATE TABLE #sab_keys") for s in server.statements)  # its own staged keys
    assert server.rows("dbo.tasks") == [(1, "Open"), (2, "Open"), (3, "Open")]
