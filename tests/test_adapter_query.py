"""SQL a plan cannot say: the adapter's `query(source, sql, params)` (the owner, 2026-11-22,
Plans/adapter.plan.md "after phase 2"): the source's own SQL (joins, CTEs, a write with RETURNING), answered
as Arrow. A statement that returns no rows answers one `count` column, the rows it changed. And `Connection`,
what API.py's `connection(name)` hands out: the adapter's calls (tables, columns, read, query, write) over
one source, the same code here and in an export. Made-up data only."""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter as sab


@pytest.fixture
def shop(tmp_path: Path) -> Path:
    path = tmp_path / "shop.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, city VARCHAR)")
    con.execute("INSERT INTO customers VALUES (1, 'Springfield'), (2, 'Shelbyville'), (3, 'Springfield')")
    con.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount DOUBLE, placed DATE)")
    con.execute(
        "INSERT INTO orders VALUES (10, 1, 12.5, '2026-01-03'), (11, 1, 7.5, '2026-01-09'), "
        "(12, 2, 40.0, '2026-02-01'), (13, 3, 1.0, '2026-02-11')"
    )
    con.close()
    return path


def _sqlite(tmp_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(tmp_path / "shop.sqlite"), check_same_thread=False)
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, city TEXT)")
    con.executemany(
        "INSERT INTO customers VALUES (?, ?)", [(1, "Springfield"), (2, "Shelbyville"), (3, "Springfield")]
    )
    con.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount REAL)")
    con.executemany(
        "INSERT INTO orders VALUES (?, ?, ?)", [(10, 1, 12.5), (11, 1, 7.5), (12, 2, 40.0), (13, 3, 1.0)]
    )
    con.commit()
    return con


JOINED = (
    "WITH spent AS (SELECT customer_id, sum(amount) AS total FROM orders GROUP BY customer_id) "
    "SELECT c.city, sum(s.total) AS total FROM customers c JOIN spent s ON s.customer_id = c.customer_id "
    "WHERE c.city = ? GROUP BY c.city"
)


def test_duckdb_answers_a_join_and_a_cte_as_arrow(shop: Path) -> None:
    source = sab.DuckDB.file(str(shop))
    found = sab.query(source, JOINED, ["Springfield"])
    assert isinstance(found, pa.RecordBatchReader)
    assert found.read_all().to_pylist() == [{"city": "Springfield", "total": 21.0}]


def test_a_write_answers_its_count_or_its_returning_rows(shop: Path) -> None:
    source = sab.DuckDB.file(str(shop))
    changed = sab.query(source, "UPDATE customers SET city = ? WHERE city = ?", ["Ogdenville", "Springfield"])
    assert changed.read_all().to_pylist() == [{"count": 2}]
    made = sab.query(
        source, "INSERT INTO customers SELECT max(customer_id) + 1, ? FROM customers RETURNING customer_id",
        ["North Haverbrook"],
    )  # fmt: skip
    assert made.read_all().to_pylist() == [{"customer_id": 4}]
    assert sab.query(source, "SELECT count(*) AS n FROM customers").read_all().to_pylist() == [{"n": 4}]


def test_a_sql_database_answers_in_its_own_sql_and_marks(tmp_path: Path) -> None:
    con = _sqlite(tmp_path)
    source = sab.Sql(con, "sqlite")
    found = sab.query(source, JOINED, ["Springfield"]).read_all()
    assert found.to_pylist() == [{"city": "Springfield", "total": 21.0}]
    gone = sab.query(source, "DELETE FROM orders WHERE amount < ?", [5])
    assert gone.read_all().to_pylist() == [{"count": 1}]
    assert con.execute("SELECT count(*) FROM orders").fetchone() == (3,)  # committed


def test_a_failed_write_is_rolled_back(tmp_path: Path) -> None:
    con = _sqlite(tmp_path)
    with pytest.raises(sqlite3.OperationalError):
        sab.query(sab.Sql(con, "sqlite"), "UPDATE nowhere SET a = 1")
    assert con.execute("SELECT count(*) FROM orders").fetchone() == (4,)


def test_a_source_with_no_sql_says_so() -> None:
    class Lists:
        def catalog(self) -> list[dict[str, str]]:
            return []

    with pytest.raises(sab.AdapterError, match="has no SQL of its own"):
        sab.query(sab.Rows(Lists(), "Team site"), "SELECT 1")


def test_the_connection_object_is_the_adapters_calls(shop: Path) -> None:
    db = sab.Connection(sab.DuckDB.file(str(shop)), "Shop")
    assert [t.name for t in db.tables()] == ["customers", "orders"]
    assert db.columns("CUSTOMERS")[0] == sab.Column("customer_id", "INTEGER", True)
    read = db.read(
        "orders", columns=["order_id"], filters=[["amount", ">", 5]], sort=[["order_id", "desc"]], limit=2
    )
    assert read.read_all().column("order_id").to_pylist() == [12, 11]
    assert db.read("orders", sab.Plan(limit=1)).read_all().num_rows == 1
    done = db.write(
        "orders", [{"order_id": 14, "customer_id": 2, "amount": 3.0, "placed": datetime.date(2026, 3, 1)}]
    )
    assert done == sab.Counts(inserted=1)
    assert db.write("orders", [{"order_id": 14}], key=["order_id"], mode="delete") == sab.Counts(deleted=1)
    assert db.query("SELECT count(*) AS n FROM orders").read_all().to_pylist() == [{"n": 4}]


def test_the_old_client_calls_are_refused_with_the_adapters_words(shop: Path) -> None:
    db = sab.Connection(sab.DuckDB.file(str(shop)), "Shop")
    with pytest.raises(AttributeError, match=r"query\(sql, params\)"):
        db.cursor()
    with pytest.raises(AttributeError, match="no attribute 'colour'"):
        db.colour  # noqa: B018 (an attribute that never was)


def test_a_real_client_is_wrapped_in_its_backend(tmp_path: Path, shop: Path) -> None:
    con = _sqlite(tmp_path)
    found = sab.source_from(con)
    assert isinstance(found, sab.Sql) and found.dialect.name == "sqlite"
    assert isinstance(sab.source_from(duckdb.connect(str(shop))), sab.DuckDB)

    class Dataverse:
        def rows(self) -> None: ...

        def described(self) -> None: ...

        def catalog(self) -> None: ...

    class Lake:
        def rows(self) -> None: ...

        def catalog(self) -> None: ...

    assert isinstance(sab.source_from(Dataverse()), sab.OData)
    assert isinstance(sab.source_from(Lake()), sab.Rows)
    assert sab.source_from(found) is found  # a source already
    with pytest.raises(sab.AdapterError, match="cannot tell"):
        sab.source_from(object())
