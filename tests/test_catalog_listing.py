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
    # Phase 4: every dialect the adapter knows (test_each_dialects_listing_is_its_starters_own_text).
    from swissarmybench.adapters import sab_adapter

    assert set(blade_tables.ADAPTER_LISTED) == {"duckdb", *sab_adapter.DIALECTS}


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


# ===== phase 4: every database lists through the adapter, at its starter's scope =====


def test_each_dialects_listing_is_its_starters_own_text() -> None:
    """The adapter's listing for a dialect is its Connections starter's List the tables, whitespace aside,
    so a connection with its starter's listing is listed by the adapter (and an edited one never)."""
    from swissarmybench.adapters import sab_adapter as sab

    def flat(text: object) -> str:
        return " ".join(str(text).split())

    for template, dialect in (
        ("mysql", "mysql"), ("mariadb", "mysql"), ("oracle", "oracle"), ("snowflake", "snowflake"),
        ("sqlserver", "sqlserver"), ("azuresql", "sqlserver"), ("trino", "trino"),
        ("databricks", "databricks"),
    ):  # fmt: skip
        starter = BY_ID[template]
        assert flat(sab.DIALECTS[dialect].listing) == flat(starter.catalog_command), template
        listed = blade_tables.listed_by_adapter(
            "sql", template, starter.dialect, "sql", starter.catalog_command, TEMPLATES
        )
        assert listed == dialect, template
        edited = str(starter.catalog_command).replace("ORDER BY", "WHERE 1 = 1 ORDER BY", 1)
        assert (
            blade_tables.listed_by_adapter("sql", template, starter.dialect, "sql", edited, TEMPLATES) == ""
        )


class _Listing:
    """A DB-API connection stood in for: each statement's rows as given (made-up), the rest none."""

    def __init__(self, answers: dict[str, list[tuple[Any, ...]]]) -> None:
        self.answers = answers

    def cursor(self) -> Any:
        connection = self

        class Cursor:
            rows: tuple[tuple[Any, ...], ...] = ()

            def execute(self, sql: str, *_: Any) -> None:
                self.rows = tuple(connection.answers.get(" ".join(sql.split()), []))

            def fetchall(self) -> list[tuple[Any, ...]]:
                return list(self.rows)

            def close(self) -> None:
                pass

        return Cursor()


def test_sql_servers_listing_keeps_its_descriptions_and_keys_row_for_row() -> None:
    from swissarmybench.adapters import sab_adapter as sab

    rows = [
        ("Shop", "dbo", "orders", "BASE TABLE", "", "", "YES", 0, "1,204 rows · Each order once"),
        ("Shop", "dbo", "orders", "BASE TABLE", "order_id", "int", "NO", 1, "Primary key. Identity."),
        ("Shop", "dbo", "orders", "BASE TABLE", "amount", "decimal(10,2)", "YES", 3, None),
        ("Shop", "sales", "regions", "VIEW", "region", "nvarchar(40)", "YES", 1, None),
    ]
    listing = " ".join(sab.DIALECTS["sqlserver"].listing.split())
    source = sab.Sql(_Listing({listing: rows}), "sqlserver")
    listed = sab.listed(source)
    assert [t.name for t in listed] == ["orders", "sales.regions"]
    orders = listed[0]
    assert orders.description == "1,204 rows · Each order once" and orders.columns[0].key
    assert orders.columns[0].description == "Primary key. Identity." and orders.columns[1].position == 3
    names, made = sab.catalog_rows(listed)
    assert names[0] == "table_catalog" and names[-1] == "description"
    assert [tuple(r) for r in made] == rows  # row for row: what the starter's own listing gave


def test_oracles_listing_reads_its_own_shape() -> None:
    from swissarmybench.adapters import sab_adapter as sab

    rows = [
        ("SALES", "ORDERS", "TABLE", "ORDER_ID", "NUMBER", "N", 1),
        ("HR", "STAFF", "VIEW", "NAME", "VARCHAR2", "Y", 1),
    ]
    listed = sab.listed(sab.Sql(_Listing({" ".join(sab.DIALECTS["oracle"].listing.split()): rows}), "oracle"))
    assert [(t.schema, t.name, t.kind) for t in listed] == [
        ("SALES", "ORDERS", "TABLE"),
        ("HR", "STAFF", "VIEW"),
    ]
    assert [c.nullable for t in listed for c in t.columns] == [False, True]


def test_mariadbs_listing_through_the_adapter_is_its_starters_row_for_row() -> None:
    """The test bed's MariaDB (skipped without it): every schema the reader sees, as the starter lists it."""
    pymysql = pytest.importorskip("pymysql")
    from tools.testbed import testbed

    state = (testbed.read_state() or {}).get("mariadb") or {}
    if "port" not in state:
        pytest.skip("The test bed is not up (python tools/testbed/testbed.py up).")
    conn = pymysql.connect(
        host=state["host"], port=state["port"], user=state["user"], password=state["password"],
        database=state["database"],
    )  # fmt: skip
    try:
        own = run_catalog(conn, {}, "sql", str(BY_ID["mariadb"].catalog_command), {}, "Warehouse")
        adapted = adapter_catalog(conn, "mysql", {}, "Warehouse")
    finally:
        conn.close()
    assert own[1] and [list(r) for r in adapted[1]] == [list(r) for r in own[1]]
    assert adapted[0] == [c.lower() for c in own[0]]
