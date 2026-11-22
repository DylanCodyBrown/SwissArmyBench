"""SQL databases as one backend of the adapter (Plans/adapter.plan.md, Order 2): any DB-API connection, its
dialect's rules as data. The plan is folded whole into one query in the source's own SQL (checked here by
sqlglot reading each dialect's query back), the answer streamed as Arrow batches, a write all or none in each
mode. SQLite always; PostgreSQL when the real-world test bed runs (tools/testbed/testbed.py up). Made-up
data only."""

from __future__ import annotations

import datetime
import decimal
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
import sqlglot

from swissarmybench.adapters import adapter as sab
from swissarmybench.adapters.adapter import Filter, Plan, Total

FULL = Plan(
    columns=("region", "amount"),
    filters=(
        Filter("region", "in", ["North", "South"]),
        Filter("amount", "between", [1, 50]),
        Filter("note", "like", "%gift%"),
        Filter("placed", "is not null"),
        Filter("id", "!=", 3),
    ),
    sort=(("amount", True),),
    limit=10,
    offset=5,
)
TOTALS = Plan(
    group=("region",),
    totals=(Total("count"), Total("sum", "amount", "total"), Total("count_distinct", "id")),
    sort=(("total", True),),
    limit=3,
)
SQLGLOT = {
    "postgres": "postgres", "mysql": "mysql", "sqlserver": "tsql", "oracle": "oracle", "sqlite": "sqlite",
    "snowflake": "snowflake", "trino": "trino", "databricks": "databricks",
}  # fmt: skip


@pytest.mark.parametrize("dialect", sorted(SQLGLOT))
def test_each_dialects_query_is_its_own_sql(dialect: str) -> None:
    rules = sab.DIALECTS[dialect]
    for plan in (FULL, TOTALS, Plan(limit=4), Plan(offset=2), Plan()):
        sql, params = sab.dialect_sql(rules, "sales.orders", plan)
        assert sql.count("?") == len(params)
        parsed = sqlglot.parse_one(sql.replace("?", "1"), read=SQLGLOT[dialect])
        found = parsed.find(sqlglot.exp.Table)
        assert found is not None and found.name == "orders", sql


def test_each_dialect_says_its_limit_and_offset_its_own_way() -> None:
    def said(name: str, plan: Plan, style: str = "qmark") -> str:
        return sab.dialect_sql(sab.DIALECTS[name], "orders", plan, style)[0]

    assert said("postgres", Plan(limit=4, offset=2)).endswith(' FROM "orders" LIMIT 4 OFFSET 2')
    assert said("sqlserver", Plan(limit=4)) == "SELECT TOP (4) * FROM [orders]"
    assert said("sqlserver", Plan(limit=4, offset=2)).endswith(
        "ORDER BY (SELECT NULL) OFFSET 2 ROWS FETCH NEXT 4 ROWS ONLY"
    )
    assert said("oracle", Plan(limit=4)).endswith('"orders" OFFSET 0 ROWS FETCH NEXT 4 ROWS ONLY')
    assert said("trino", Plan(limit=4, offset=2)).endswith(" OFFSET 2 LIMIT 4")
    assert said("mysql", Plan(offset=2)).endswith("`orders` LIMIT 18446744073709551615 OFFSET 2")
    assert said("sqlite", Plan(offset=2)).endswith('"orders" LIMIT -1 OFFSET 2')
    assert 'WHERE "id" = %s' in said("postgres", Plan(filters=(Filter("id", "=", 1),)), "format")
    assert 'WHERE "id" = :p1' in said("oracle", Plan(filters=(Filter("id", "=", 1),)), "named")
    assert said("postgres", Plan(columns=('we"ird',)), "format").startswith('SELECT "we""ird" FROM')


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(tmp_path / "shop.sqlite")
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, region TEXT, amount REAL, placed TEXT)")
    con.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?)",
        [(1, "North", 12.5, "2026-01-03"), (2, "South", 40.0, "2026-01-04"), (3, "North", 7.25, None)],
    )
    con.execute("CREATE VIEW north AS SELECT * FROM orders WHERE region = 'North'")
    con.commit()
    yield con
    con.close()


def test_a_sqlite_database_lists_its_tables_with_keys(shop: sqlite3.Connection) -> None:
    listed = {t.name: t for t in sab.tables(sab.Sql(shop, "sqlite"))}
    assert sorted(listed) == ["north", "orders"]
    assert [(c.name, c.key) for c in listed["orders"].columns][:2] == [("id", True), ("region", False)]


def test_a_read_folds_the_whole_plan_and_streams_batches(shop: sqlite3.Connection) -> None:
    source = sab.Sql(shop, "sqlite")
    north = Plan(columns=("id",), filters=(Filter("region", "=", "North"),), sort=(("id", True),))
    reader, folded = sab.read(source, "orders", north)
    assert folded.parts == ("filters", "columns", "sort")
    assert reader.read_all().column("id").to_pylist() == [3, 1]
    reader, _ = sab.read(source, "orders", TOTALS)
    assert reader.read_all().to_pylist() == [
        {"region": "South", "count": 1, "total": 40.0, "count_distinct_id": 1},
        {
            "region": "North",
            "count": 2,
            "total": 19.75,
            "count_distinct_id": 2,
        },
    ]
    small = sab.cursor_batches(_cursor(shop, "SELECT * FROM orders ORDER BY id"), size=2)
    assert [b.num_rows for b in small] == [2, 1]


def _cursor(con: sqlite3.Connection, sql: str) -> sqlite3.Cursor:
    cursor = con.cursor()
    cursor.execute(sql)
    return cursor


def test_each_write_mode_counts_and_a_failure_writes_nothing(shop: sqlite3.Connection) -> None:
    source = sab.Sql(shop, "sqlite")
    new = pa.table(
        {
            "id": [4],
            "region": ["West"],
            "amount": [decimal.Decimal("1.5")],
            "placed": [datetime.date(2026, 3, 1)],
        }
    )
    assert sab.write(source, "orders", new) == sab.Counts(inserted=1)
    both = pa.table({"id": [1, 5], "region": ["North", "East"], "amount": [13.0, 2.0]})
    assert sab.write(source, "orders", both, ("id",), "merge") == sab.Counts(inserted=1, updated=1)
    assert sab.write(
        source, "orders", pa.table({"id": [2, 9], "amount": [41.0, 1.0]}), ("id",), "update"
    ) == sab.Counts(updated=1)
    assert sab.write(source, "orders", pa.table({"id": [3, 99]}), ("id",), "delete") == sab.Counts(deleted=1)
    rows = shop.execute("SELECT id, amount, placed FROM orders ORDER BY id").fetchall()
    assert rows == [(1, 13.0, "2026-01-03"), (2, 41.0, "2026-01-04"), (4, 1.5, "2026-03-01"), (5, 2.0, None)]
    clash = pa.table({"id": [6, 1], "region": ["West", "North"]})
    with pytest.raises(sqlite3.IntegrityError) as failed:
        sab.write(source, "orders", clash)
    assert len(shop.execute("SELECT id FROM orders").fetchall()) == 4  # the 6 was rolled back
    assert sab.batch_of(failed.value) == sab.Batch(1, 0, 2)  # added in phase 4: the batch beside its error
    assert "batch 1 (rows 1 to 2)" in failed.value.__notes__[0]
    with pytest.raises(sab.AdapterError, match="names the key"):
        sab.write(source, "orders", both, mode="merge")


def test_a_truncate_clears_and_inserts_in_one_transaction(shop: sqlite3.Connection) -> None:
    source = sab.Sql(shop, "sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        sab.write(source, "orders", pa.table({"id": [7, 7]}), mode="truncate")
    assert len(shop.execute("SELECT id FROM orders").fetchall()) == 3  # nothing cleared
    assert sab.write(
        source, "orders", pa.table({"id": [7], "region": ["West"]}), mode="truncate"
    ) == sab.Counts(inserted=1, deleted=3)
    assert sab.write(source, "orders", mode="truncate") == sab.Counts(deleted=1)
    assert [c.name for c in sab.tables(source)[1].columns] == ["id", "region", "amount", "placed"]


def test_a_source_with_no_transactions_is_read_only() -> None:
    with pytest.raises(sab.AdapterError, match="no transactions"):
        sab.write(sab.Sql(sqlite3.connect(":memory:"), "trino"), "orders", pa.table({"id": [1]}))


# ===== PostgreSQL, when the test bed runs =====


def _testbed() -> dict[str, Any] | None:
    folder = Path(os.environ.get("SAB_TESTBED_DIR") or Path(tempfile.gettempdir()) / "swissarmybench-testbed")
    state = folder / "testbed.json"
    return json.loads(state.read_text(encoding="utf-8")) if state.is_file() else None


@pytest.fixture
def postgres() -> Iterator[Any]:
    psycopg = pytest.importorskip("psycopg")
    bed = _testbed()
    if not bed or not bed.get("postgres"):
        pytest.skip("the real-world test bed is not running (tools/testbed/testbed.py up)")
    pg = bed["postgres"]
    try:
        con = psycopg.connect(host=pg["host"], port=pg["port"], dbname=pg["database"], user=pg["user"],
                              password=pg["password"], connect_timeout=3)  # fmt: skip
    except psycopg.OperationalError:
        pytest.skip("the test bed's PostgreSQL does not answer")
    yield con
    con.close()


def test_postgresql_lists_reads_with_its_plan_folded_and_writes(postgres: Any) -> None:
    source = sab.Sql(postgres, "postgres", "Shop")
    listed = {t.name: t for t in sab.tables(source)}
    orders = next(name for name in listed if name.endswith("orders"))
    reader, folded = sab.read(source, orders, Plan(totals=(Total("count"),)))
    assert folded.parts == ("totals",)
    assert reader.read_all().column("count")[0].as_py() > 0
    reader, _ = sab.read(source, orders, Plan(limit=3))
    assert reader.read_all().num_rows == 3
    postgres.execute("CREATE TEMP TABLE scratch (id integer PRIMARY KEY, label text)")
    postgres.commit()
    made = pa.table({"id": [1, 2], "label": ["one", "two"]})
    assert sab.write(source, "pg_temp.scratch", made, ("id",), "merge") == sab.Counts(inserted=2)
    assert sab.write(
        source, "pg_temp.scratch", pa.table({"id": [3], "label": ["three"]}), mode="truncate"
    ) == (sab.Counts(inserted=1, deleted=2))
    back, _ = sab.read(source, "pg_temp.scratch", Plan())
    assert back.read_all().to_pylist() == [{"id": 3, "label": "three"}]


def test_mariadb_reads_with_its_plan_folded_in_its_own_sql() -> None:
    pymysql = pytest.importorskip("pymysql")
    bed = _testbed()
    if not bed or not bed.get("mariadb") or "port" not in bed["mariadb"]:
        pytest.skip("the real-world test bed is not running (tools/testbed/testbed.py up)")
    db = bed["mariadb"]
    try:
        con = pymysql.connect(host=db["host"], port=db["port"], user=db["user"], password=db["password"],
                              database=db["database"], connect_timeout=3)  # fmt: skip
    except pymysql.MySQLError:
        pytest.skip("the test bed's MariaDB does not answer")
    try:
        source = sab.Sql(con, "mysql", "Warehouse")
        assert source.style == "pyformat"  # pymysql's marks: %s
        listed = {t.name: t for t in sab.tables(source)}
        assert {"customers", "order_lines"} <= set(listed)
        plan = Plan(columns=("product_id", "quantity"), filters=(Filter("quantity", ">=", 2),),
                    sort=(("quantity", True),), limit=5)  # fmt: skip
        reader, folded = sab.read(source, "order_lines", plan)
        assert folded.parts == ("filters", "columns", "sort", "limit")
        rows = reader.read_all().to_pylist()
        assert len(rows) == 5 and all(r["quantity"] >= 2 for r in rows)
        counted, _ = sab.read(source, "order_lines", Plan(totals=(Total("count"),)))
        assert counted.read_all().column("count")[0].as_py() > 0
    finally:
        con.close()
