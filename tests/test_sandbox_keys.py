"""The sandbox keeps its keys (the owner approved the critic's proposal 5, 2026-11-21): a table's primary key
from where it came (a column list's, the one asked for, its connection's in the shared catalog) or from the
endpoint New endpoint from a table made; a write that repeats or blanks it refused in one sentence, as the
real database would; Reset and an older checkpoint keep it. Made-up data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import sandbox as rules
from swissarmybench.domain.sandbox import SandboxError
from tests.conftest import AGENT, AUTH, make_client


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _project(client: TestClient, tmp_path: Path) -> Path:
    folder = tmp_path / "clinic"
    ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
    return folder


def _sql(client: TestClient, sql: str) -> Any:
    return client.post("/sandbox/data", json={"op": "sql", "connection": "Sandbox", "sql": sql}, headers=AUTH)


def test_a_key_is_checked_and_a_refusal_says_the_key() -> None:
    assert rules.check_key("Visit_ID", ["visit_id", "store"]) == ["visit_id"]
    assert rules.check_key(["store", "visit_id"], ["visit_id", "store"]) == ["store", "visit_id"]
    with pytest.raises(SandboxError, match="no column named nope"):
        rules.check_key("nope", ["visit_id"])
    said = rules.db_words('Constraint Error: Duplicate key "visit_id: 4" violates primary key constraint.')
    assert said == "Duplicate key: a row with visit_id: 4 is there already (its primary key)."
    assert "cannot be blank" in rules.db_words(
        'Constraint Error: NOT NULL constraint failed: "PRIMARY_visits_visit_id"'
    )
    assert rules.db_words("Binder Error: no column x\nLINE 1") == "Binder Error: no column x"


def test_the_sandbox_refuses_a_duplicate_key_as_the_database_would(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        cols = [{"name": "visit_id", "type": "integer", "key": True}, {"name": "store", "type": "text"}]
        added = ok(
            client.post(
                "/sandbox/tables", json={"from": "columns", "name": "visits", "columns": cols}, headers=AUTH
            )
        )
        assert added["key"] == ["visit_id"]
        assert _sql(client, "INSERT INTO visits VALUES (1, 'Larkfield Shop')").status_code == 200
        again = _sql(client, "INSERT INTO visits VALUES (1, 'Marshby Depot')")
        assert again.status_code == 400 and again.json()["error"] == (
            "Duplicate key: a row with visit_id: 1 is there already (its primary key)."
        )
        blank = client.post(
            "/sandbox/data", json={"op": "insert", "table": "visits", "row": {"store": "x"}}, headers=AUTH
        )
        assert blank.status_code == 400 and "cannot be blank" in blank.json()["error"]


def test_a_key_set_later_is_kept_by_reset_and_an_older_checkpoint(tmp_path: Path) -> None:
    csv = tmp_path / "stock.csv"
    csv.write_text("sku,count\nA-1,3\nB-2,5\n", encoding="utf-8")
    dup = tmp_path / "moves.csv"
    dup.write_text("sku,count\nA-1,3\nA-1,5\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH))
        ok(client.post("/sandbox/checkpoints", json={"name": "before key"}, headers=AUTH))
        assert ok(
            client.post("/sandbox/tables/key", json={"table": "stock", "key": "SKU"}, headers=AGENT)
        ) == {
            "table": "stock",
            "key": ["sku"],
        }
        assert _sql(client, "INSERT INTO stock VALUES ('A-1', 9)").status_code == 400
        ok(client.post("/sandbox/reset", json={}, headers=AUTH))
        assert _sql(client, "INSERT INTO stock VALUES ('A-1', 9)").status_code == 400
        ok(client.post("/sandbox/checkpoints/restore", json={"name": "before key"}, headers=AUTH))
        assert _sql(client, "INSERT INTO stock VALUES ('A-1', 9)").status_code == 400
        listed = {t["name"]: t for t in ok(client.get("/sandbox", headers=AUTH))["tables"]}
        assert [c["name"] for c in listed["stock"]["columns"] if c["key"]] == ["sku"]
        # Rows that repeat it: the key refused, in one sentence; one asked for at Add: in, without it, said.
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(dup)}, headers=AUTH))
        refused = client.post("/sandbox/tables/key", json={"table": "moves", "key": ["sku"]}, headers=AUTH)
        assert refused.status_code == 400 and "two rows have the same key" in refused.json()["error"]
        came = ok(
            client.post(
                "/sandbox/tables",
                json={"from": "file", "path": str(dup), "name": "moves2", "key": "sku"},
                headers=AUTH,
            )
        )
        assert "key" not in came and "came in without its key (sku)" in came["note"]


def test_new_endpoint_from_a_table_keeps_its_key_in_the_sandbox(tmp_path: Path) -> None:
    csv = tmp_path / "visits.csv"
    csv.write_text("visit_id,store\n1,Larkfield Shop\n2,Marshby Depot\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH))
        made = ok(
            client.post("/local-api/scaffold", json={"table": "visits", "key": "visit_id"}, headers=AUTH)
        )
        assert "note" not in made
        assert _sql(client, "INSERT INTO visits VALUES (2, 'Fernhaven Shop')").status_code == 400
