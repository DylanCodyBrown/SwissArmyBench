"""A project's sandbox (domain/sandbox.py, services/sandbox.py; the owner, 2026-11-21: "transform scaffold
create
an app then test it out and then reset the data changes and try again. It makes for the ultimate sandbox").

The rules first (names, the meta file, the change log, the writes' SQL with every value bound), then the store
on
disk (Reset gives back exactly the baseline, checkpoints), then the routes: a table in from an open grid, a
file,
a connection (read once), and by its columns; writes counted; Reset and checkpoints; the grid following;
DuckDB
SQL naming [Sandbox]; the Catalog's section; the agent's Reset on Allow. Made-up data only."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter
from swissarmybench.adapters.database import duckdb_grammar
from swissarmybench.adapters.sandbox import SandboxFiles
from swissarmybench.domain import sandbox as rules
from swissarmybench.domain.sandbox import SandboxError
from tests.conftest import AGENT, AUTH, make_client
from tests.test_sandbox_query import TestRemote

ORDERS = "order_id,region,amount\n1,West,10.5\n2,East,7.25\n3,West,3.0\n"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


# ===== the rules =====


def test_names_are_checked() -> None:
    assert rules.check_table_name("orders_2") == "orders_2"
    for bad in ("", "2orders", "or ders", "a;drop", "x" * 70):
        with pytest.raises(SandboxError):
            rules.check_table_name(bad)
    assert rules.check_checkpoint_name("Before demo 1") == "Before demo 1"
    with pytest.raises(SandboxError):
        rules.check_checkpoint_name("../etc")
    assert rules.checkpoint_file("Before demo 1") == "Before_demo_1.duckdb"


def test_writes_bind_every_value_and_name_only_real_columns() -> None:
    cols = ["order_id", "Region", "amount"]
    [s] = rules.insert_statements("orders", cols, {"order_id": 4, "region": "x'); DROP TABLE orders; --"})
    assert s.sql == 'INSERT INTO "orders" ("order_id", "Region") VALUES (?, ?)'
    assert s.params[1].startswith("x'")
    u = rules.update_statement("orders", cols, {"amount": 1}, {"order_id": 2, "region": None})
    assert u.sql == 'UPDATE "orders" SET "amount" = ? WHERE "order_id" = ? AND "Region" IS NULL'
    assert u.params == [1, 2]
    with pytest.raises(SandboxError, match="no column named nope"):
        rules.update_statement("orders", cols, {"nope": 1}, {"order_id": 1})
    with pytest.raises(SandboxError, match="which rows"):
        rules.delete_statement("orders", cols, {})
    assert rules.delete_statement("orders", cols, None, every=True).sql == 'DELETE FROM "orders"'
    read = rules.table_read("orders", cols, {"region": "West"}, 5, 10)
    assert read.sql.endswith('WHERE "Region" = ? LIMIT 5 OFFSET 10') and read.params == ["West"]


def test_a_query_reads_with_one_select_only() -> None:
    parse = duckdb_grammar().parse
    assert rules.check_read("SELECT 1;", parse) == "SELECT 1"
    for bad in ("DELETE FROM t", "SELECT 1; SELECT 2", "CREATE TABLE x (a INT)", ""):
        with pytest.raises(SandboxError):
            rules.check_read(bad, parse)


def test_the_meta_file_is_byte_stable_and_reads_back() -> None:
    meta = rules.Meta(tables={"orders": {"source": {"kind": "file", "file": "orders"}}}, baseline_at="t")
    rules.noted(meta.log, "orders", "insert", 2)
    rules.noted(meta.log, "orders", "delete", 1)
    meta.checkpoints.append(rules.Checkpoint("one", "t2", rules.copied_log(meta.log)))
    text = rules.meta_text(meta)
    again = rules.read_meta(text)
    assert rules.meta_text(again) == text
    assert again.log["orders"].to_json() == {"inserted": 2, "updated": 0, "deleted": 1}
    assert rules.log_words(again.log) == "orders: 2 inserted, 1 deleted"
    assert rules.log_words({}) == "No changes since the baseline"
    assert rules.read_meta("not json").tables == {}


def test_an_empty_table_by_its_columns() -> None:
    cols = rules.columns_spec([{"name": "id", "type": "integer", "key": True}, {"name": "note"}])
    assert rules.create_sql("notes", cols) == (
        'CREATE TABLE "notes" ("id" BIGINT, "note" VARCHAR, PRIMARY KEY ("id"))'
    )
    with pytest.raises(SandboxError, match="type is one of"):
        rules.columns_spec([{"name": "x", "type": "blob"}])
    with pytest.raises(SandboxError, match="twice"):
        rules.columns_spec([{"name": "x"}, {"name": "X"}])


# ===== the store on disk =====


def test_reset_gives_back_exactly_the_baseline_and_checkpoints_their_state(tmp_path: Path) -> None:
    files = SandboxFiles(str(tmp_path))
    files.put_table("orders", pa.table({"order_id": [1, 2, 3], "region": ["West", "East", "West"]}), False)
    files.set_baseline()
    before = files.arrow("orders")
    [n] = files.write(
        [rules.insert_statements("orders", ["order_id", "region"], [{"order_id": 4, "region": "N"}])]
    )
    assert n == 1
    files.save_checkpoint("four rows")
    files.write([[rules.delete_statement("orders", ["order_id", "region"], {"region": "West"})]])
    assert files.arrow("orders").num_rows == 2
    assert files.reset() is True
    assert files.arrow("orders").equals(before)
    assert files.restore_checkpoint("four rows") is True
    assert files.arrow("orders").num_rows == 4
    files.close()
    # One transaction: a failing write leaves nothing written.
    bad = rules.Statement('INSERT INTO "orders" ("order_id") VALUES (?)', ["not a number"])
    good = rules.insert_statements("orders", ["order_id", "region"], {"order_id": 9})
    with pytest.raises(Exception):  # noqa: B017 (DuckDB's conversion error)
        files.write([good, [bad]])
    assert files.arrow("orders").num_rows == 4
    # No file or network from a query: external access is off.
    with pytest.raises(Exception, match=r"(?i)permission|disabled"):
        files.query(rules.Statement("SELECT * FROM read_csv('/etc/hosts')", []), 5)
    files.close()


# ===== the routes =====


def _project(client: TestClient, tmp_path: Path) -> Path:
    target = tmp_path / "shop"
    ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
    return target


def test_without_a_project_the_sandbox_says_to_open_one(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert ok(client.get("/sandbox", headers=AUTH))["project"] is None
        refused = client.post(
            "/sandbox/tables", json={"from": "columns", "name": "x", "columns": [{"name": "a"}]}, headers=AUTH
        )
        assert refused.status_code == 409 and "Open a project first" in refused.text


def test_tables_in_writes_counted_grid_follows_reset_and_checkpoints(tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    with make_client(tmp_path) as client:
        folder = _project(client, tmp_path)
        grid = ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))["grid"]
        steps = [{"kind": "filter", "params": {"column": "region", "op": "eq", "value": "West"}}]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": steps}, headers=AUTH))
        # From an open grid: its view, after its steps.
        added = ok(
            client.post(
                "/sandbox/tables", json={"from": "grid", "table": "orders", "name": "west"}, headers=AUTH
            )
        )
        assert added == {"added": "west", "rows": 2, "sql": "[Sandbox].west"}
        # From a file, and empty by its columns.
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH))
        cols = [{"name": "id", "type": "integer", "key": True}, {"name": "note", "type": "text"}]
        ok(
            client.post(
                "/sandbox/tables", json={"from": "columns", "name": "notes", "columns": cols}, headers=AUTH
            )
        )
        taken = client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH)
        assert taken.status_code == 409
        listed = ok(client.get("/sandbox", headers=AUTH))
        by = {t["name"]: t for t in listed["tables"]}
        assert by["orders"]["rows"] == 3 and by["notes"]["rows"] == 0
        assert by["notes"]["columns"][0] == {"name": "id", "type": "BIGINT", "key": True}
        assert by["orders"]["client"] == {"kind": "duckdb"}
        assert (folder / ".sab" / "sandbox" / "sandbox.duckdb").exists()
        assert "sandbox/" in (folder / ".sab" / ".gitignore").read_text(encoding="utf-8")
        assert ".sab/sandbox/" in (folder / ".gitignore").read_text(encoding="utf-8")
        # Open in Grids: follows every write, where it is.
        opened = ok(client.post("/sandbox/tables/open", json={"table": "orders"}, headers=AUTH))
        box_grid = opened["grid"]

        def rows() -> int:
            return int(ok(client.get(f"/grids/{box_grid}/count", headers=AUTH))["row_count"])

        assert rows() == 3
        # An API's writes through the adapter: counted, the grid following.
        db = adapter.Connection(TestRemote(client, "Sandbox"))
        assert db.write("orders", [{"order_id": 4, "region": "North", "amount": 1.5}]).inserted == 1
        assert db.query("UPDATE orders SET amount = 99 WHERE order_id = ?", [1]).read_all().to_pylist() == [
            {"count": 1}
        ]
        assert db.write("orders", [{"region": "East"}], key=["region"], mode="delete").deleted == 1
        assert rows() == 3
        log = ok(client.get("/sandbox", headers=AUTH))
        assert log["log"] == {"orders": {"inserted": 1, "updated": 1, "deleted": 1}}
        read = db.query("SELECT amount FROM orders WHERE order_id = ?", [1]).read_all()
        assert read.to_pylist() == [{"amount": 99.0}]
        # DuckDB SQL names it [Sandbox].orders, read again after a write.
        built = ok(
            client.post(
                "/datasets/boxed/query",
                json={"sql": "SELECT count(*) AS n FROM [Sandbox].orders"},
                headers=AUTH,
            )
        )
        first = ok(client.get(f"/grids/{built['grid']}/rows?offset=0&limit=5", headers=AUTH))
        assert first["rows"][0][0] == 3
        # A checkpoint, more writes, then Reset to the baseline.
        ok(client.post("/sandbox/checkpoints", json={"name": "after edits"}, headers=AUTH))
        db.query("DELETE FROM orders")
        assert rows() == 0
        # One table back alone first: the others keep their changes.
        db.query("DELETE FROM west")
        one = ok(client.post("/sandbox/reset", json={"table": "west"}, headers=AUTH))
        assert one["undone"] == {"west": {"inserted": 0, "updated": 0, "deleted": 2}}
        assert db.read("west").read_all().num_rows
        assert rows() == 0
        reset = ok(client.post("/sandbox/reset", json={}, headers=AUTH))
        assert reset["undone"]["orders"]["deleted"] == 4
        assert rows() == 3
        assert ok(client.get("/sandbox", headers=AUTH))["log"] == {}
        restored = ok(client.post("/sandbox/checkpoints/restore", json={"name": "after edits"}, headers=AUTH))
        assert restored["log"]["orders"] == {"inserted": 1, "updated": 1, "deleted": 1}
        ok(
            client.post(
                "/sandbox/checkpoints", json={"name": "after edits", "action": "delete"}, headers=AUTH
            )
        )
        assert ok(client.get("/sandbox", headers=AUTH))["checkpoints"] == []
        # The Catalog's Sandbox section.
        browse = ok(client.get("/explorer/browse", headers=AUTH))
        section = next(s for s in browse["sections"] if s["kind"] == "sandbox")
        assert {i["name"] for i in section["items"]} == {"notes", "orders", "west"}
        # A write naming a column that is not there: one sentence, nothing written.
        with pytest.raises(adapter.AdapterError, match="nope"):
            db.write("orders", [{"nope": 1}])
        with pytest.raises(adapter.AdapterError, match="duplicate key"):
            db.write("notes", [{"id": 1}, {"id": 1}])
        assert db.read("notes").read_all().num_rows == 0


def test_a_connections_table_is_read_once_and_remembers_its_client(tmp_path: Path) -> None:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
        made_up.executemany("INSERT INTO customers VALUES (?, ?)", [(1, "Springfield"), (2, "Shelbyville")])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    shop = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        ok(client.post("/connections", json=shop, headers=AUTH))
        added = ok(
            client.post(
                "/sandbox/tables",
                json={"from": "connection", "connection": "Shop", "table": "customers"},
                headers=AUTH,
            )
        )
        assert added["rows"] == 2
        database.unlink()  # never read again: the sandbox has its own copy
        [t] = ok(client.get("/sandbox", headers=AUTH))["tables"]
        assert t["client"]["connection"] == "Shop" and t["client"]["template"] == "sqlite"
        assert t["source_words"] == "Read once from Shop"
        assert t["rows"] == 2


def test_the_agents_reset_waits_for_the_users_allow(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        cols = [{"name": "id", "type": "integer"}]
        ok(
            client.post(
                "/sandbox/tables", json={"from": "columns", "name": "t", "columns": cols}, headers=AGENT
            )
        )
        adapter.Connection(TestRemote(client, "Sandbox")).write("t", [{"id": 1}])
        answer: dict[str, Any] = {}
        waiting = threading.Thread(
            target=lambda: answer.update(r=client.post("/sandbox/reset", json={}, headers=AGENT))
        )
        waiting.start()
        pending: list[Any] = []
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            time.sleep(0.05)
        assert pending and "t: 1 inserted" in pending[0]["detail"]
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH))
        waiting.join(10)
        assert answer["r"].status_code == 403
        found = adapter.Connection(TestRemote(client, "Sandbox")).read("t").read_all()
        assert found.to_pylist() == [{"id": 1}]


def test_a_running_apis_key_path_needs_its_own_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        refused = client.post("/sandbox/data/not-a-key/tables", json={"connection": "Sandbox"})
        assert refused.status_code == 403
