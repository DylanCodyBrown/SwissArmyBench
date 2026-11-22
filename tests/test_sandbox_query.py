"""The sandbox as the adapter's backend for a local sandbox API (Plans/adapter.plan.md, phase 3): one
endpoint's code, the adapter's calls on connection(name), reads and writes the real source (SQLite,
Dataverse's stand-in) and the sandbox holding the same rows alike. A query in its connection's own SQL
and marks is made DuckDB SQL over the sandbox's tables (domain/sandbox_dialects.py); what cannot be
emulated is refused with its line. The mock clients that did this per source are gone. Made-up data
only."""

from __future__ import annotations

import io
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter
from swissarmybench.domain import dataverse
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.sandbox import SandboxError
from tests import dataverse_standin as made_up
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring


class _Answer(io.BytesIO):
    """A test client's answer read as Remote reads http.client's."""

    def __init__(self, answer: Any) -> None:
        super().__init__(answer.content)
        self.headers = answer.headers

    def getheader(self, name: str, default: str = "") -> str:
        return str(self.headers.get(name, default))


class TestRemote(adapter.Remote):
    """The adapter's sandbox source, through the test's client (the token's path) instead of HTTP."""

    __test__ = False

    def __init__(self, client: TestClient, connection: str) -> None:
        super().__init__("", connection)
        self.client = client

    def _post(self, path: str, body: bytes) -> Any:
        answer = self.client.post("/sandbox/adapter" + path, content=body, headers=AUTH)
        if answer.status_code >= 400:
            raise adapter.AdapterError(answer.json()["error"])
        return _Answer(answer)


def _put(client: TestClient, tmp_path: Path, name: str, table: pa.Table) -> None:
    import pyarrow.parquet as pq

    path = tmp_path / f"{name}.parquet"
    pq.write_table(table, path)
    answer = client.post(
        "/sandbox/tables", json={"from": "file", "path": str(path), "name": name}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text


def query(client: TestClient, sql: str, params: Any = None, connection: str = "Sandbox") -> Any:
    """The adapter's query on the sandbox's door, as a running API's Remote sends it: the raw answer."""
    body = {"connection": connection, "sql": sql, "params": params or []}
    return client.post("/sandbox/adapter/query", json=body, headers=AUTH)


def arrow_rows(answer: Any) -> list[dict[str, Any]]:
    """A door's Arrow IPC answer as records (its error said when it is one)."""
    assert answer.status_code == 200, answer.text
    return list(pa.ipc.open_stream(answer.content).read_all().to_pylist())


def _mock_as(folder: Path, table: str, connection: str, dialect: str, kind: str = "database") -> None:
    """A sandbox table as if read from `connection` (its sandbox.json record, as Add to sandbox writes it)."""
    path = folder / ".sab" / "sandbox" / "sandbox.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["tables"][table]["client"] = {"kind": kind, "connection": connection, "dialect": dialect}
    path.write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "shop")}, headers=AUTH)
        assert made.status_code == 200, made.text
        yield client


# ===== the dialects: the sandbox's half of query =====


def test_each_source_speaks_its_own_sql_and_marks() -> None:
    tables = ["orders"]
    t = dialects.to_duckdb(
        "SELECT * FROM dbo.orders ORDER BY id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        "sqlserver",
        [5, 10],
        tables,
    )
    assert t.sql == 'SELECT * FROM "orders" ORDER BY id NULLS FIRST LIMIT $2 OFFSET $1' and t.params == [
        5,
        10,
    ]
    t = dialects.to_duckdb(
        "SELECT * FROM public.orders WHERE note LIKE '50%%' AND id = %s", "postgres", [3], tables
    )
    assert "'50%'" in t.sql and t.params == [3]
    t = dialects.to_duckdb("SELECT * FROM orders WHERE id = :id AND id <> :id", "oracle", {"id": 2}, tables)
    assert t.params == [2] and t.sql.count("$1") == 2
    t = dialects.to_duckdb(
        "INSERT INTO dbo.orders (id) OUTPUT INSERTED.id VALUES (?)", "sqlserver", [9], tables
    )
    assert t.kind == "insert" and t.table == "orders" and "RETURNING id" in t.sql
    for sql, said in (
        ("MERGE INTO orders USING x ON 1 = 1 WHEN MATCHED THEN DELETE;", "cannot run MERGE"),
        ("SELECT 1\nFROM #work", "Line 2: the sandbox's mock has no temporary tables (#work)"),
        ("SELECT * FROM sys.columns", "no system views"),
        ("EXEC sp_who", "cannot run EXEC"),
        ("SELECT * FROM customers", "has no table customers"),
        ("SELECT ?", "has no value"),
    ):
        with pytest.raises(SandboxError, match=said.replace("(", r"\(").replace(")", r"\)")):
            dialects.to_duckdb(sql, "sqlserver", [], tables)


# ===== the same code, the real source and the sandbox =====


def orders_in(db: adapter.Connection, region: str) -> list[dict[str, Any]]:
    """One endpoint's code, as it is in API.py: the adapter's calls, the source's own SQL and marks."""
    joined = db.query(
        "SELECT o.order_id, o.amount, c.city FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
        "WHERE o.region = ? ORDER BY o.order_id",
        [region],
    )
    return list(joined.read_all().to_pylist())


ORDERS = [(1, "West", 10.5, 7), (2, "East", 7.25, 8), (3, "West", 3.0, 8)]
CUSTOMERS = [(7, "Springfield"), (8, "Shelbyville")]


def test_the_same_code_reads_and_writes_sqlite_and_the_sandbox_alike(
    boxed: TestClient, tmp_path: Path
) -> None:
    real = sqlite3.connect(":memory:")
    real.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount REAL, customer_id INTEGER)")
    real.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", ORDERS)
    real.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
    real.executemany("INSERT INTO customers VALUES (?, ?)", CUSTOMERS)
    names = ("order_id", "region", "amount", "customer_id")
    _put(boxed, tmp_path, "orders", pa.Table.from_pylist([dict(zip(names, r, strict=True)) for r in ORDERS]))
    _put(
        boxed,
        tmp_path,
        "customers",
        pa.table({"customer_id": [7, 8], "city": ["Springfield", "Shelbyville"]}),
    )
    for table in ("orders", "customers"):
        _mock_as(tmp_path / "shop", table, "Shop", "sqlite")
    here = adapter.Connection(TestRemote(boxed, "Shop"), "Shop")
    there = adapter.Connection(adapter.Sql(real, "sqlite"), "Shop")
    assert orders_in(here, "West") == orders_in(there, "West")
    assert [r["city"] for r in orders_in(here, "West")] == ["Springfield", "Shelbyville"]
    for db in (here, there):
        changed = db.query("UPDATE orders SET amount = ? WHERE order_id = ?", [1.0, 1])
        assert changed.read_all().to_pylist() == [{"count": 1}]
        read = db.read(
            "orders", columns=["order_id"], filters=[["amount", "<", 5]], sort=[["order_id", "asc"]]
        )
        assert read.read_all().column("order_id").to_pylist() == [1, 3]
        assert db.write("orders", [{"order_id": 3}], key=["order_id"], mode="delete") == adapter.Counts(
            deleted=1
        )
    log = boxed.get("/sandbox", headers=AUTH).json()["log"]
    assert log["orders"]["updated"] == 1 and log["orders"]["deleted"] == 1  # Reset undoes them
    with pytest.raises(adapter.AdapterError, match="makes a table from a query"):
        here.query("CREATE TABLE x (a INT)")


def test_a_long_read_comes_back_whole(boxed: TestClient, tmp_path: Path) -> None:
    """A query's answer is streamed (no page size, no "more" to ask for): every row, nested types kept."""
    many = 25_003
    _put(boxed, tmp_path, "lines", pa.table({"line_id": list(range(many)), "tags": [["a", "b"]] * many}))
    db = adapter.Connection(TestRemote(boxed, "Sandbox"))
    found = db.query("SELECT line_id, tags FROM lines ORDER BY line_id").read_all()
    assert found.num_rows == many and found.column("tags")[0].as_py() == ["a", "b"]


def test_an_api_makes_views_tables_and_sequences_and_reset_undoes_them(
    boxed: TestClient, tmp_path: Path
) -> None:
    """CREATE VIEW, CREATE TABLE AS (T-SQL's SELECT INTO) and sequences through query, each listed by tables()
    and columns(); never over a table the user added; Reset undoes them."""
    _put(boxed, tmp_path, "orders", pa.table({"order_id": [1, 2, 3], "region": ["West", "East", "West"]}))
    _put(boxed, tmp_path, "regions", pa.table({"region": ["West"]}))
    for table in ("orders", "regions"):
        _mock_as(tmp_path / "shop", table, "Shop", "postgres")
    pg = adapter.Connection(TestRemote(boxed, "Shop"))
    with pytest.raises(adapter.AdapterError, match="a view cannot hold a value given apart"):
        pg.query("CREATE VIEW west AS SELECT order_id FROM orders WHERE region = %s", ["West"])
    assert pg.query(
        "CREATE VIEW west AS SELECT order_id FROM orders WHERE region = 'West'"
    ).read_all().to_pylist() == [{"count": 0}]
    assert pg.query("SELECT count(*) AS n FROM west").read_all().to_pylist() == [{"n": 2}]
    assert [t.name for t in pg.tables()] == ["orders", "regions", "west"]
    assert pg.columns("WEST") == [adapter.Column("order_id", "BIGINT")]
    listed = {t["name"]: t for t in boxed.get("/sandbox", headers=AUTH).json()["tables"]}
    assert listed["west"]["source_words"] == "Made by the API (a view)"
    with pytest.raises(
        adapter.AdapterError, match="orders is a sandbox table you added: an API cannot replace it"
    ):
        pg.query("CREATE OR REPLACE VIEW orders AS SELECT 1 AS one")
    with pytest.raises(adapter.AdapterError, match="cannot drop it"):
        pg.query("DROP TABLE orders")
    assert boxed.post("/sandbox/reset", json={}, headers=AUTH).status_code == 200
    assert [t.name for t in pg.tables()] == ["orders", "regions"]


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def big_accounts(db: adapter.Connection) -> list[dict[str, Any]]:
    """One endpoint's code for Dataverse: a plan, folded into OData by the real source, by DuckDB here."""
    found = db.read("account", columns=["name", "revenue"], filters=[["revenue", ">", 1_000_000]],
                    sort=[["revenue", "desc"]], limit=3)  # fmt: skip
    return list(found.read_all().to_pylist())


def test_the_same_code_reads_dataverse_and_the_sandbox_alike(
    boxed: TestClient, tmp_path: Path, standin: made_up.StandIn
) -> None:
    from swissarmybench.adapters.blade_run import run_code

    code = (
        dataverse.APP.replace("https://your-org.crm.dynamics.com", standin.url)
        .replace("my-tenant-id", made_up.TENANT)
        .replace("my-client-id", made_up.CLIENT)
    )
    real, _ = run_code(code, "conn", {"client secret": made_up.SECRET}, "Sales CRM")
    every, _ = real.rows("account", columns=["name", "revenue"])
    _put(boxed, tmp_path, "account", pa.Table.from_pylist(every))
    _mock_as(tmp_path / "shop", "account", "Sales CRM", "sqlserver", "dataverse")
    here = adapter.Connection(TestRemote(boxed, "Sales CRM"))
    there = adapter.Connection(adapter.source_from(real, name="Sales CRM"))
    assert big_accounts(here) == big_accounts(there) and len(big_accounts(here)) == 3
    with pytest.raises(adapter.AdapterError, match="read-only: SELECT only"):
        here.query("DELETE FROM account")
