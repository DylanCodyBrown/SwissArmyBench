"""Grids made through the adapter (Plans/adapter.plan.md, phase 1): a DuckDB file connection's Open as grid
and the sandbox's Open in Grids read through sab_adapter (the plan folded into the read, the batches made the
grid, nothing else kept). Made-up data only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from starlette.testclient import TestClient

from tests.conftest import AUTH
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def duckdb_connection(path: Path, row_limit: int | None = None) -> dict[str, Any]:
    code = f'import duckdb\n\nconn = duckdb.connect(r"{path}", read_only=True)\n'
    return {"name": "Shop", "kind": "sql", "template": "duckdb", "dialect": "duckdb", "code": code} | (
        {"row_limit": row_limit} if row_limit is not None else {}
    )


@pytest.fixture
def shop(tmp_path: Path) -> Path:
    path = tmp_path / "shop.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE orders (order_id INTEGER, region VARCHAR, amount DECIMAL(10,2), ordered DATE)")
    con.execute(
        "INSERT INTO orders SELECT range, CASE WHEN range % 2 = 0 THEN 'North' ELSE 'South' END, "
        "range * 1.25, DATE '2026-01-01' + CAST(range AS INTEGER) FROM range(30)"
    )
    con.execute("CREATE SCHEMA stock")
    con.execute("CREATE TABLE stock.items AS SELECT 'sku-' || range AS sku, range AS qty FROM range(3)")
    con.close()
    return path


def _columns(client: TestClient, grid: str) -> dict[str, str]:
    found = client.get(f"/grids/{grid}", headers=AUTH).json()
    return {c["name"]: c["type"] for c in found["columns"]}


def test_a_duckdb_file_table_opens_through_the_adapter_typed(client: TestClient, shop: Path) -> None:
    assert client.post("/connections", json=duckdb_connection(shop, 10), headers=AUTH).status_code == 200
    opened = client.post("/connections/Shop/open", json={"table": "orders"}, headers=AUTH)
    assert opened.status_code == 200, opened.text
    assert opened.json()["shown"] == 10 and opened.json()["total"] == 30
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 10
    assert _columns(client, opened.json()["grid"]) == {
        "order_id": "INTEGER", "region": "VARCHAR", "amount": "DECIMAL(10,2)", "ordered": "DATE",
    }  # fmt: skip
    every = client.post("/connections/Shop/open", json={"table": "orders", "all": True}, headers=AUTH)
    assert client.get(f"/grids/{every.json()['grid']}", headers=AUTH).json()["row_count"] == 30
    items = client.post("/connections/Shop/open", json={"table": "items", "schema": "stock"}, headers=AUTH)
    assert items.status_code == 200, items.text
    assert client.get(f"/grids/{items.json()['grid']}", headers=AUTH).json()["row_count"] == 3


def test_a_table_the_file_does_not_have_is_said_by_the_adapter(client: TestClient, shop: Path) -> None:
    assert client.post("/connections", json=duckdb_connection(shop), headers=AUTH).status_code == 200
    missing = client.post("/connections/Shop/open", json={"table": "invoices"}, headers=AUTH)
    assert missing.status_code >= 400
    assert "has no table 'invoices'" in missing.text


def test_a_sqlite_table_opens_through_the_adapter_with_its_limit_and_count(
    client: TestClient, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE entries (entry_id INTEGER PRIMARY KEY, account TEXT, amount REAL)")
    con.executemany(
        "INSERT INTO entries VALUES (?, ?, ?)", [(i, f"acct-{i % 3}", i * 2.5) for i in range(25)]
    )
    con.commit()
    con.close()
    code = f'import sqlite3\n\nconn = sqlite3.connect(r"{path}")\n'
    made = {
        "name": "Ledger",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": code,
        "row_limit": 8,
    }
    assert client.post("/connections", json=made, headers=AUTH).status_code == 200
    opened = client.post("/connections/Ledger/open", json={"table": "entries"}, headers=AUTH)
    assert opened.status_code == 200, opened.text
    assert (opened.json()["shown"], opened.json()["total"]) == (8, 25)
    assert _columns(client, opened.json()["grid"]) == {
        "entry_id": "BIGINT",
        "account": "VARCHAR",
        "amount": "DOUBLE",
    }
