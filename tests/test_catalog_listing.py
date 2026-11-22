"""The Catalog lists a connection's tables through the adapter's tables() (Plans/adapter.plan.md, after phase
2), except a connection whose List the tables the user edited: theirs runs. "Edited" is told by its text: it
differs (whitespace aside) from its starter's listing query. The adapter lists only the dialects whose
listing is its starter's row for row (held here for DuckDB and SQLite; PostgreSQL when the test bed runs), so
the Catalog shows what it showed. Made-up data only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.blade_run import adapter_catalog, run_catalog
from swissarmybench.domain import blade_tables
from swissarmybench.server.blade_templates import BY_ID, TEMPLATES
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring


def test_the_adapter_lists_an_unedited_listing_and_never_an_edited_one() -> None:
    sqlite = BY_ID["sqlite"]
    listed = blade_tables.listed_by_adapter
    assert listed("sql", "sqlite", "sqlite", "sql", sqlite.catalog_command, TEMPLATES) == "sqlite"
    spaced = "\n\n" + str(sqlite.catalog_command).replace(" ", "   ") + "\n"
    assert listed("sql", "sqlite", "sqlite", "sql", spaced, TEMPLATES) == "sqlite"  # whitespace aside
    assert listed("sql", "sqlite", "sqlite", None, None, TEMPLATES) == "sqlite"  # none: its starter's
    edited = "SELECT 'main' AS table_schema, name AS table_name, 'id' AS column_name FROM sqlite_master"
    assert listed("sql", "sqlite", "sqlite", "sql", edited, TEMPLATES) == ""
    assert (
        listed("sql", "postgres", "postgres", "sql", BY_ID["postgres"].catalog_command, TEMPLATES)
        == "postgres"
    )
    for template in ("mysql", "oracle", "snowflake", "sql_server"):
        if template in BY_ID:
            found = BY_ID[template]
            assert listed("sql", template, found.dialect, "sql", found.catalog_command, TEMPLATES) == "", (
                template
            )


def _shop_sqlite(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, city TEXT NOT NULL)")
    con.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount REAL, placed DATE)")
    con.execute("CREATE VIEW big_orders AS SELECT * FROM orders WHERE amount > 100")
    con.commit()
    con.close()


def _shop_duckdb(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, city VARCHAR NOT NULL)")
    con.execute(
        "CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount DECIMAL(10, 2), placed DATE)"
    )
    con.execute("CREATE SCHEMA sales")
    con.execute("CREATE TABLE sales.targets (region VARCHAR, target DOUBLE)")
    con.execute("CREATE VIEW big_orders AS SELECT * FROM orders WHERE amount > 100")
    con.close()


@pytest.mark.parametrize("dialect", ["sqlite", "duckdb"])
def test_the_adapters_listing_is_its_starters_row_for_row(tmp_path: Path, dialect: str) -> None:
    path = tmp_path / f"shop.{dialect}"
    if dialect == "sqlite":
        _shop_sqlite(path)
        value: Any = sqlite3.connect(str(path))
    else:
        _shop_duckdb(path)
        value = duckdb.connect(str(path), read_only=True)
    starter = BY_ID[dialect]
    own = run_catalog(value, {}, "sql", str(starter.catalog_command), {}, "Shop")
    adapted = adapter_catalog(value, dialect, {}, "Shop")
    assert adapted[0] == [c.lower() for c in own[0]] and adapted[1] == own[1]
    assert any(r[adapted[0].index("table_type")] == "VIEW" or r[adapted[0].index("table_type")] == "view"
               for r in adapted[1])  # fmt: skip


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as made:
        yield made


def test_a_refresh_lists_through_the_adapter_unless_the_listing_is_the_users(
    client: TestClient, tmp_path: Path
) -> None:
    database = tmp_path / "shop.sqlite"
    _shop_sqlite(database)
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    shop = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    assert client.post("/connections", json=shop, headers=AUTH).status_code == 200
    refreshed = client.post("/blades/Shop/refresh", json={}, headers=AUTH)
    assert refreshed.status_code == 200, refreshed.text
    listed = refreshed.json()["catalog"]
    assert (listed["tables"], listed["views"], listed["columns"]) == (2, 1, 10)
    # The user's own List the tables (one table, renamed): theirs runs, never the adapter's.
    own = {
        "catalog": {
            "language": "sql",
            "command": "SELECT 'main' AS table_schema, 'clients' AS table_name, name AS column_name, "
            "type AS data_type FROM pragma_table_info('customers')",
        }
    }
    saved = client.put("/connections/Shop", json=shop | own, headers=AUTH)
    assert saved.status_code == 200, saved.text
    again = client.post("/blades/Shop/refresh", json={}, headers=AUTH).json()
    assert again["catalog"]["tables"] == 1
