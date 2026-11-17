"""The starter pack's Write family (docs/ideas.md, "Writing data"; the owner, 2026-11-17: "writes are meant
to be handled with blades and cells in notebooks"): each Write starter is a Python snippet dropped into a
cell, its settings first (a dry run that changes nothing), then the statements written out and a helper
(client/writes.py, write_sql.py, write_dataverse.py) for the rows, the transaction and
the counts.

Run here against SQLite, PostgreSQL and MariaDB (the test bed, tools/testbed: skipped when it is not up),
SQL Server's T-SQL against a stand-in driver that records every call, Dataverse against its
stand-in (tests/dataverse_standin.py), and files written and read back. Made-up
data only."""

from __future__ import annotations

import ast
import json
import sqlite3
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pytest
from starlette.testclient import TestClient

import swissarmybench
from swissarmybench.adapters.blade_run import run_code
from swissarmybench.client import write_sql
from swissarmybench.client.writes import WriteError
from swissarmybench.domain import dataverse, write_capability
from swissarmybench.domain.blades import needed, read_blade
from swissarmybench.domain.connection_tables import TABLE_KINDS
from swissarmybench.domain.connections import connection_kind
from swissarmybench.domain.snippets import fill, placeholders
from swissarmybench.server.blade_templates import TEMPLATES
from tests import dataverse_standin
from tests.conftest import AUTH, push

FOLDER = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"
WRITERS = sorted(FOLDER.glob("write_*.blade.py"))
VALUES = {
    "connection": "Warehouse",
    "table": "orders",
    "key column": "order_id",
    "partition column": "region",
}


def starter(file: str) -> dict[str, Any]:
    return read_blade((FOLDER / f"{file}.blade.py").read_text(encoding="utf-8"))


def cell(starter_file: str, dry_run: bool, **values: str) -> str:
    """A Write starter's text, filled as its form fills it, with dry_run as asked."""
    blade = starter(starter_file)
    text = fill(blade["code"], blade["language"], VALUES | values)
    assert "dry_run = True\n" in text
    return text.replace("dry_run = True\n", f"dry_run = {dry_run}\n", 1)


def run(text: str, **names: Any) -> Any:
    """The cell run as a notebook runs it; its last line's value (the write's report)."""
    space: dict[str, Any] = dict(names)
    exec(compile(text, "<cell>", "exec"), space)  # noqa: S102 (the starter pack's own cell, filled here)
    return space["w"]


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable[[], Any]], list[str]]:
    """sab.connection stood in for: `opens()` makes the live connection; the names asked for are kept."""

    def use(opens: Callable[[], Any]) -> list[str]:
        asked: list[str] = []

        def connection(name: str) -> Any:
            asked.append(name)
            return opens()

        monkeypatch.setattr(swissarmybench, "connection", connection, raising=False)
        return asked

    return use


# ===== every Write starter =====


def test_the_write_family_is_43_starters_each_a_python_snippet() -> None:
    blades = [read_blade(p.read_text(encoding="utf-8")) for p in WRITERS]
    assert len(blades) == 43
    assert {b["family"] for b in blades} == {"Write"}
    assert {b["language"] for b in blades} == {"python"} and {b["kind"] for b in blades} == {"snippet"}
    for blade in blades:
        assert blade["description"].endswith("(dry run first; writes on the user's word)")
        assert (
            "An agent sets dry_run = False only after you said to write, in your own words" in blade["code"]
        )
        assert "password" not in blade["code"].replace("no password", "").lower(), blade["name"]


@pytest.mark.parametrize("path", WRITERS, ids=lambda p: p.stem)
def test_a_write_starter_fills_parses_and_lists_its_packages(path: Path) -> None:
    blade = read_blade(path.read_text(encoding="utf-8"))
    names = [p.name for p in placeholders(blade["code"])]
    assert "table" in names
    text = fill(blade["code"], "python", VALUES)
    tree = ast.parse(text)
    assigned = [
        t.id for s in tree.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)
    ]
    assert assigned[0] == "dry_run" and "rows" in assigned  # the dry run is the first setting
    assert isinstance(tree.body[-1], ast.Expr)  # the report is the cell's last value
    packages = [p.pip for p in needed(text, lambda module: True)]
    tags = blade["tags"]
    if not {"dataverse", "powerbi", "excel"} & set(tags):
        assert "duckdb" in packages, blade["name"]  # the rows are staged in DuckDB
    drivers = {
        "postgres": "psycopg",
        "sqlserver": "pyodbc",
        "oracle": "oracledb",
        "trino": "trino",
        "odbc": "pyodbc",
    }
    for tag, driver in drivers.items():
        if tag in tags:
            assert any(p.split("[")[0] == driver for p in packages), blade["name"]
    if "excel" in tags:
        assert "openpyxl" in packages


# ===== what each kind of connection writes =====


def test_every_connection_kind_is_writable_or_read_only_with_its_reason() -> None:
    kinds = {t.id for t in TEMPLATES if connection_kind(t.kind, t.id) not in (None, "vault")}
    assert kinds | {"api"} == set(write_capability.WRITABLE) | set(
        write_capability.READ_ONLY
    )  # api: a tables kind
    assert not set(write_capability.WRITABLE) & set(write_capability.READ_ONLY)
    power_bi = write_capability.capability("powerbi", tables_kind="powerbi")
    assert power_bi["writable"] is False and "refresh it" in power_bi["reason"]  # refresh is its action
    assert write_capability.capability("dataverse")["how"].endswith("(its SQL endpoint is read-only)")
    assert "connector" in write_capability.capability("trino")["note"]
    duck = write_capability.capability("duckdb")
    assert duck["writable"] is False and duck["words"].startswith(
        "Read-only: the connection opens the file read-only"
    )


def test_every_kind_of_connection_tables_is_writable_read_only_or_decided_by_its_template() -> None:
    covered = write_capability.tables_kinds_covered()
    assert set(covered) == set(TABLE_KINDS) and "" not in covered.values()
    assert covered == {
        "database": "template",
        "powerbi": "read-only",
        "dataverse": "writable",
        "dataverse_web": "writable",  # the Web API writes whichever way it reads
        "python": "read-only",
        "api": "read-only",
        "file": "template",
        "folder": "writable",
    }
    api = write_capability.capability("python", tables_kind="api")
    assert api["words"] == "Read-only: an API writes through the APIs page's Write rows with this call"
    assert write_capability.capability("dataverse", tables_kind="dataverse_web")["writable"] is True
    assert write_capability.capability("postgres", tables_kind="database")["writable"] is True
    assert write_capability.capability(None, tables_kind="database")["writable"] is False  # code of its own


def test_every_writable_kind_has_a_starter_and_every_starter_names_writable_kinds_only() -> None:
    blades = [read_blade(p.read_text(encoding="utf-8")) for p in WRITERS]
    for kind in write_capability.WRITABLE:
        assert write_capability.starters_for(kind, blades), f"{kind} is writable but has no Write starter"
    for blade in blades:
        named = write_capability.kinds_named(blade["tags"])
        assert named, f"{blade['name']} names no connection kind"
        assert not set(named) & set(write_capability.READ_ONLY), blade["name"]
    for kind in write_capability.READ_ONLY:
        assert write_capability.starters_for(kind, blades) == []
    words = write_capability.capability("postgres", blades)["words"]
    assert (
        words
        == "Writes: PostgreSQL append, PostgreSQL create table, PostgreSQL delete, PostgreSQL replace, PostgreSQL upsert"
    )


def test_the_connections_page_says_what_each_connection_writes(client: TestClient) -> None:
    for name, template, code in (
        ("Finance file", "sqlite", "import sqlite3\nconn = sqlite3.connect(':memory:')"),
        ("Planning", "duckdb", "import duckdb\nconn = duckdb.connect(':memory:')"),
    ):
        body = {"name": name, "kind": "sql", "template": template, "dialect": template, "code": code}
        assert client.post("/connections", json=body | {"variable": "conn"}, headers=AUTH).status_code == 200
    listed = {c["name"]: c for c in client.get("/connections", headers=AUTH).json()["connections"]}
    assert listed["Finance file"]["writes"]["writable"] is True
    assert listed["Finance file"]["writes"]["starters"][0] == "SQLite append"
    assert listed["Planning"]["writes"]["words"].startswith("Read-only: ")
    cards = {c["name"]: c for c in client.get("/connections/usage", headers=AUTH).json()["connections"]}
    assert cards["Planning"]["writes"]["writable"] is False
    detail = client.get("/connections/Finance%20file/usage", headers=AUTH).json()
    assert detail["writes"]["words"].startswith("Writes: SQLite append")
    forms = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    assert forms["sqlserver"]["writes"]["starters"] == [
        "SQL Server append",
        "SQL Server create table",
        "SQL Server delete",
        "SQL Server replace",
        "SQL Server upsert",
    ]
    assert "writes" not in forms["azure_key_vault"]


def test_the_write_family_lists_excel_and_power_bi_starters_too(client: TestClient) -> None:
    families = {
        f["family"]: f["blades"] for f in client.get("/blades/starters", headers=AUTH).json()["families"]
    }
    also = [b["name"] for b in families["Write"] if b.get("also")]
    assert also == [
        "Excel write table",
        "Excel range as table",
        "Power BI refresh dataset",
        "Power BI refresh and wait",
    ]
    assert any(b["name"] == "Excel write table" and not b.get("also") for b in families["Excel"])


def test_a_write_starters_form_offers_the_connections_of_its_kind_first(client: TestClient) -> None:
    assert (
        push(client, "orders", pa.table({"order_id": [1, 2], "region": ["North", "South"]})).status_code
        == 200
    )
    for name, template in (("Alpha CSV", "csv"), ("Zed shop", "sqlite")):
        code = (
            "from pathlib import Path\npath = Path('x.csv')"
            if template == "csv"
            else "import sqlite3\nconn = 1"
        )
        kind = "other" if template == "csv" else "sql"
        body = {
            "name": name,
            "kind": kind,
            "template": template,
            "code": code,
            "variable": "path" if kind == "other" else "conn",
        }
        assert (
            client.post(
                "/connections", json=body | ({"dialect": "sqlite"} if kind == "sql" else {}), headers=AUTH
            ).status_code
            == 200
        )
    form = client.get("/blades/SQLite%20upsert/snippet", headers=AUTH).json()
    assert form["cell"] == "code" and form["cell_words"] == "a Python cell"
    assert form["options"]["connections"] == ["Zed shop", "Alpha CSV"]
    kinds = {p["name"]: p["kind"] for p in form["placeholders"]}
    assert kinds == {"connection": "connection", "target": "text", "table": "table", "key column": "column"}
    filled = client.post(
        "/blades/SQLite%20upsert/snippet",
        json={"values": {"connection": "Zed shop", "table": "orders", "key column": "order_id"}},
        headers=AUTH,
    ).json()
    assert 'connection = "Zed shop"' in filled["text"] and "rows = orders" in filled["text"]
    assert 'keys = ["order_id"]' in filled["text"] and filled["cell_name"] is None


# ===== SQLite: every write, its dry run, its rollback =====


ORDERS = pd.DataFrame({"order_id": [1, 2, 3], "region": ["South", "East", "West"], "amount": [1.5, 2.5, 3.5]})


@pytest.fixture
def shop(tmp_path: Path, connection: Callable[[Callable[[], Any]], list[str]]) -> Iterator[Path]:
    """A made-up shop's SQLite file, opened read-only as the SQLite connection opens it."""
    file = tmp_path / "shop.sqlite"
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, region TEXT, amount REAL)")
        db.execute("INSERT INTO orders VALUES (1, 'North', 10.0), (9, 'North', 90.0)")
    connection(lambda: sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True))
    yield file


def rows_of(file: Path, table: str = "orders") -> list[tuple[Any, ...]]:
    with sqlite3.connect(file) as db:
        return db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()


def test_a_dry_run_changes_nothing_and_says_what_it_would_do(shop: Path) -> None:
    report = run(cell("write_sqlite_upsert", dry_run=True), orders=ORDERS)
    said = str(report)
    assert said.startswith("Dry run: nothing was written. Set dry_run = False to write.")
    assert "Target    orders on Warehouse" in said and "Database  SQLite" in said
    assert "Rows      3: order_id (BIGINT), region (VARCHAR), amount (DOUBLE)" in said
    assert "Would     update 1 row, insert 2 rows" in said
    assert 'ON CONFLICT ("order_id") DO UPDATE SET "region" = excluded."region"' in said
    assert "The first 3 rows:" in said
    assert rows_of(shop) == [(1, "North", 10.0), (9, "North", 90.0)]


def test_append_upsert_replace_delete_and_create_give_the_right_rows(shop: Path) -> None:
    new = pd.DataFrame({"order_id": [4, 5], "region": ["East", "West"], "amount": [4.0, 5.0]})
    done = run(cell("write_sqlite_append", dry_run=False), orders=new)
    assert done.counts == {"inserted": 2} and str(done).startswith(
        "Wrote orders on Warehouse: inserted 2 rows"
    )
    assert [r[0] for r in rows_of(shop)] == [1, 4, 5, 9]
    upserted = run(cell("write_sqlite_upsert", dry_run=False), orders=ORDERS)
    assert upserted.counts == {"inserted": 2, "updated": 1}
    assert rows_of(shop)[:3] == [(1, "South", 1.5), (2, "East", 2.5), (3, "West", 3.5)]
    gone = run(cell("write_sqlite_delete", dry_run=False), orders=pd.DataFrame({"order_id": [2, 3, 3, 77]}))
    assert gone.counts == {"deleted": 2}
    assert [r[0] for r in rows_of(shop)] == [1, 4, 5, 9]
    replaced = run(cell("write_sqlite_replace", dry_run=False), orders=ORDERS)
    assert replaced.counts == {"deleted": 4, "inserted": 3} and len(rows_of(shop)) == 3
    made = run(cell("write_sqlite_create_table", dry_run=False, target="orders_copy"), orders=ORDERS)
    assert made.counts == {"inserted": 3} and rows_of(shop, "orders_copy") == rows_of(shop)
    with sqlite3.connect(shop) as db:
        declared = db.execute("SELECT sql FROM sqlite_master WHERE name = 'orders_copy'").fetchone()[0]
    assert '"order_id" INTEGER' in declared and '"region" TEXT' in declared and '"amount" REAL' in declared


def test_a_failing_batch_rolls_every_row_back_and_says_which(shop: Path) -> None:
    text = cell("write_sqlite_append", dry_run=False).replace("batch_size = 1000", "batch_size = 2")
    rows = pd.DataFrame({"order_id": [20, 21, 22, 1], "region": ["A", "B", "C", "D"], "amount": [0.0] * 4})
    with pytest.raises(WriteError) as refused:
        run(text, orders=rows)
    said = str(refused.value)
    assert said.startswith("Nothing was written: batch 2 (rows 3 to 4) failed: UNIQUE constraint failed")
    assert rows_of(shop) == [(1, "North", 10.0), (9, "North", 90.0)]  # batch 1 rolled back too


def test_a_write_says_when_the_table_changed_since_its_dry_run(shop: Path) -> None:
    run(cell("write_sqlite_upsert", dry_run=True), orders=ORDERS)  # 1 to update, 2 to insert
    with sqlite3.connect(shop) as db:
        db.execute("INSERT INTO orders VALUES (2, 'East', 0.0)")
    done = run(cell("write_sqlite_upsert", dry_run=False), orders=ORDERS)
    assert done.counts == {"inserted": 1, "updated": 2}
    assert "The dry run counted otherwise (updated 1 -> 2; inserted 2 -> 1)" in str(done)


def test_wrong_columns_keys_and_connections_are_refused_in_plain_words(shop: Path) -> None:
    wrong = pd.DataFrame({"order_id": [1], "colour": ["red"]})
    with pytest.raises(WriteError, match=r"orders has no column colour: rename or drop it in the rows first"):
        run(cell("write_sqlite_append", dry_run=True), orders=wrong)
    twice = pd.DataFrame({"order_id": [1, 1], "region": ["a", "b"], "amount": [1.0, 2.0]})
    with pytest.raises(WriteError, match="1 keys are shared by more than one row"):
        run(cell("write_sqlite_upsert", dry_run=True), orders=twice)
    with pytest.raises(
        WriteError, match="Warehouse is a SQLite connection: this starter writes to PostgreSQL"
    ):
        run(cell("write_postgresql_append", dry_run=True), orders=ORDERS)
    with pytest.raises(WriteError, match="orders is already on Warehouse"):
        run(cell("write_sqlite_create_table", dry_run=True), orders=ORDERS)


def test_a_duckdb_relation_and_an_arrow_table_are_rows_too(shop: Path) -> None:
    import duckdb

    relation = duckdb.sql("SELECT 30 AS order_id, 'North' AS region, 3.0 AS amount")
    assert run(cell("write_sqlite_append", dry_run=False), orders=relation).counts == {"inserted": 1}
    table = pa.table({"order_id": [31], "region": ["South"], "amount": [None]})
    assert run(cell("write_sqlite_append", dry_run=False), orders=table).counts == {"inserted": 1}
    assert rows_of(shop)[-2:] == [(30, "North", 3.0), (31, "South", None)]


# ===== PostgreSQL and MariaDB: the test bed's databases =====


def bed_state() -> dict[str, Any]:
    from tools.testbed import testbed as bed

    state = bed.read_state()
    if not state or "port" not in (state.get("postgres") or {}):
        pytest.skip("The test bed is not up (python tools/testbed/testbed.py up).")
    return state


def test_postgresql_writes_through_copy_on_conflict_and_one_transaction(
    connection: Callable[[Callable[[], Any]], list[str]],
) -> None:
    psycopg = pytest.importorskip("psycopg")
    pg = bed_state()["postgres"]
    owner = f"host={pg['data']} port={pg['port']} dbname=shop user=postgres"  # the socket: trusted
    try:
        with psycopg.connect(owner, autocommit=True) as admin:
            admin.execute(f"CREATE SCHEMA IF NOT EXISTS sab_writes AUTHORIZATION {pg['user']}")
    except psycopg.OperationalError as error:
        pytest.skip(f"The test bed's PostgreSQL could not be reached as its owner: {error}")
    reader = f"host=127.0.0.1 port={pg['port']} dbname=shop user={pg['user']} password={pg['password']}"
    with psycopg.connect(reader, autocommit=True) as db:
        db.execute("DROP TABLE IF EXISTS sab_writes.orders")
    connection(lambda: psycopg.connect(reader))
    target = {"target": "sab_writes.orders"}
    rows = pd.DataFrame(
        {"order_id": [1, 2, 3], "Region": ["North", "South", "East"], "amount": [1.25, 2.5, None]}
    )
    made = run(cell("write_postgresql_create_table", dry_run=False, **target), orders=rows)
    assert made.counts == {"inserted": 3}
    with psycopg.connect(reader, autocommit=True) as db:
        db.execute("ALTER TABLE sab_writes.orders ADD PRIMARY KEY (order_id)")
        kinds = dict(
            db.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'sab_writes'"
            ).fetchall()
        )
    assert kinds == {"order_id": "bigint", "region": "text", "amount": "double precision"}  # Region: region
    dry = run(
        cell("write_postgresql_upsert", dry_run=True, **target), orders=rows.assign(amount=[9.0, 9.0, 9.0])
    )
    assert dry.planned == {"updated": 3, "inserted": 0}
    more = pd.DataFrame({"order_id": [3, 4], "Region": ["East", "West"], "amount": [3.0, 4.0]})
    assert run(cell("write_postgresql_upsert", dry_run=False, **target), orders=more).counts == {
        "inserted": 1,
        "updated": 1,
    }
    assert run(
        cell("write_postgresql_append", dry_run=False, **target), orders=more.assign(order_id=[5, 6])
    ).counts == {"inserted": 2}
    with pytest.raises(WriteError, match="Nothing was written"):
        run(cell("write_postgresql_append", dry_run=False, **target), orders=more.assign(order_id=[7, 1]))
    assert run(
        cell("write_postgresql_delete", dry_run=False, **target), orders=pd.DataFrame({"order_id": [5, 6]})
    ).counts == {"deleted": 2}
    replaced = run(cell("write_postgresql_replace", dry_run=False, **target), orders=rows)
    assert replaced.counts == {"deleted": 4, "inserted": 3}
    with psycopg.connect(reader) as db:
        assert db.execute("SELECT order_id, region FROM sab_writes.orders ORDER BY 1").fetchall() == [
            (1, "North"),
            (2, "South"),
            (3, "East"),
        ]


def test_mariadb_writes_with_on_duplicate_key_update(
    connection: Callable[[Callable[[], Any]], list[str]],
) -> None:
    pymysql = pytest.importorskip("pymysql", reason="MariaDB's test needs pymysql in the test environment")
    maria = bed_state().get("mariadb") or {}
    if "port" not in maria:
        pytest.skip("The test bed's MariaDB is not up.")
    try:
        admin = pymysql.connect(unix_socket=maria["socket"], user="root", autocommit=True)
    except pymysql.err.OperationalError as error:
        pytest.skip(f"The test bed's MariaDB could not be reached as root: {error}")
    with admin.cursor() as c:
        c.execute("CREATE DATABASE IF NOT EXISTS sab_writes")
        c.execute(f"GRANT ALL ON sab_writes.* TO '{maria['user']}'@'127.0.0.1'")
        c.execute("DROP TABLE IF EXISTS sab_writes.orders")
        c.execute(
            "CREATE TABLE sab_writes.orders (order_id INT PRIMARY KEY, region VARCHAR(20), amount DOUBLE)"
        )
    admin.close()

    def opens() -> Any:
        return pymysql.connect(
            host="127.0.0.1", port=maria["port"], user=maria["user"], password=maria["password"]
        )

    connection(opens)
    target = {"target": "sab_writes.orders"}
    assert run(cell("write_mysql_append", dry_run=False, **target), orders=ORDERS).counts == {"inserted": 3}
    changed = ORDERS.assign(order_id=[3, 4, 5], amount=[30.0, 40.0, 50.0])
    assert run(cell("write_mysql_upsert", dry_run=True, **target), orders=changed).planned == {
        "updated": 1,
        "inserted": 2,
    }
    assert run(cell("write_mysql_upsert", dry_run=False, **target), orders=changed).counts == {
        "inserted": 2,
        "updated": 1,
    }
    assert run(
        cell("write_mysql_delete", dry_run=False, **target), orders=pd.DataFrame({"order_id": [1, 2]})
    ).counts == {"deleted": 2}
    with opens() as db, db.cursor() as c:
        c.execute("SELECT order_id, amount FROM sab_writes.orders ORDER BY 1")
        assert c.fetchall() == ((3, 30.0), (4, 40.0), (5, 50.0))


# ===== SQL Server and Azure SQL: the T-SQL, against a driver that records every call =====


class FakeOdbcError(Exception):
    """pyodbc's Error: (SQLSTATE, message)."""


class FakeCursor:
    def __init__(self, conn: FakeSqlServer) -> None:
        self.conn = conn
        self.fast_executemany = False
        self.description: list[tuple[str]] | None = None
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        self.conn.log.append(("execute", sql, params))
        self.conn.fail("execute", sql)
        self._rows = self.conn.answer(sql, params)
        return self

    def executemany(self, sql: str, batch: list[tuple[Any, ...]]) -> None:
        self.conn.log.append(("executemany", sql, list(batch), self.fast_executemany))
        self.conn.fail("executemany", sql)
        if sql.startswith("INSERT INTO #sab_stage") or sql.startswith("INSERT INTO #sab_keys"):
            self.conn.staged += len(batch)

    def setinputsizes(self, sizes: list[Any]) -> None:
        self.conn.log.append(("setinputsizes", sizes))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class FakeSqlServer:
    """pyodbc's connection to SQL Server, stood in for: sys.columns, the primary key and triggers of a
    made-up dbo.orders; every statement kept; `failures` makes the next matching calls fail."""

    COLUMNS = [
        ("order_id", "int", 4, 10, 0, False, False),
        ("region", "nvarchar", 80, 0, 0, False, False),
        ("code", "varchar", 10, 0, 0, False, False),
        ("amount", "decimal", 9, 12, 2, False, False),
        ("row_no", "int", 4, 10, 0, True, False),
        ("total", "decimal", 9, 14, 2, False, True),
    ]

    def __init__(self, world: dict[str, Any]) -> None:
        self.world = world
        self.log: list[Any] = world.setdefault("log", [])
        self.staged = 0
        self.closed = False
        world.setdefault("opened", []).append(self)

    def getinfo(self, what: int) -> str:
        return "Microsoft SQL Server"

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.log.append(("commit",))

    def rollback(self) -> None:
        self.log.append(("rollback",))

    def close(self) -> None:
        self.closed = True

    def fail(self, how: str, sql: str) -> None:
        for at, (kind, start, error) in enumerate(list(self.world.get("failures", []))):
            if kind == how and sql.startswith(start):
                del self.world["failures"][at]
                raise error

    def answer(self, sql: str, params: Any) -> list[tuple[Any, ...]]:
        if "FROM sys.columns" in sql:
            return list(self.world.get("columns", self.COLUMNS))
        if "is_primary_key" in sql:
            return [("order_id",)] if self.world.get("primary", True) else []
        if "sys.triggers" in sql:
            return [("orders_audit",)]
        if sql.startswith("SELECT COUNT(*) FROM #sab_keys AS s JOIN") or "WITH (UPDLOCK, HOLDLOCK) ON" in sql:
            return [(self.world.get("matched", 1),)]
        if sql.startswith("SELECT COUNT(*) FROM #sab_stage"):
            return [(self.staged,)]
        if sql.startswith("SELECT COUNT(*) FROM"):
            return [(self.world.get("count", 5),)]
        if "WHERE 1 = 0" in sql:
            self.cursor_description = [(c[0],) for c in self.COLUMNS]
        return []


FakeSqlServer.__module__ = "pyodbc"  # the driver it stands in for, as the helper tells drivers apart


@pytest.fixture
def sql_server(
    monkeypatch: pytest.MonkeyPatch, connection: Callable[[Callable[[], Any]], list[str]]
) -> dict[str, Any]:
    fake = types.ModuleType("pyodbc")
    fake.SQL_DBMS_NAME = 17  # type: ignore[attr-defined]
    fake.SQL_WVARCHAR, fake.SQL_VARCHAR, fake.SQL_DECIMAL = -9, 12, 3  # type: ignore[attr-defined]
    fake.paramstyle = "qmark"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    world: dict[str, Any] = {}
    connection(lambda: FakeSqlServer(world))
    return world


ROWS = pd.DataFrame(
    {
        "order_id": [1, 2, 3],
        "region": ["Nörth", "South", None],
        "code": ["A1", "B2", "C3"],
        "amount": [1.5, float("nan"), 3.25],
    }
)


def calls(world: dict[str, Any], kind: str) -> list[Any]:
    return [c for c in world["log"] if c[0] == kind]


def test_sql_server_upsert_stages_the_rows_in_the_targets_types_then_merges_with_holdlock(
    sql_server: dict[str, Any],
) -> None:
    dry = run(
        cell("write_sql_server_upsert", dry_run=True, target="dbo.orders", **{"key column": "order_id"}),
        orders=ROWS,
    )
    assert dry.planned == {"updated": 1, "inserted": 2}  # one COUNT join against the staged keys
    said = str(dry)
    assert "Triggers  orders_audit fire on this write" in said
    assert (
        "MERGE INTO [dbo].[orders] WITH (HOLDLOCK) AS t\nUSING #sab_stage AS s ON t.[order_id] = s.[order_id]"
        in said.replace("\n    ", "\n")
    )
    executed = [c[1] for c in calls(sql_server, "execute")]
    assert "CREATE TABLE #sab_keys ([order_id] int NULL)" in executed
    assert ("rollback",) in sql_server["log"] and ("commit",) not in sql_server[
        "log"
    ]  # a dry run: rolled back
    sql_server["log"].clear()
    done = run(
        cell("write_sql_server_upsert", dry_run=False, target="dbo.orders", **{"key column": "order_id"}),
        orders=ROWS,
    )
    assert done.counts == {"updated": 1, "inserted": 2}
    executed = [c[1] for c in calls(sql_server, "execute")]
    assert (
        "CREATE TABLE #sab_stage ([order_id] int NULL, [region] nvarchar(40) COLLATE DATABASE_DEFAULT NULL, "
        "[code] varchar(10) COLLATE DATABASE_DEFAULT NULL, [amount] decimal(12,2) NULL)"
    ) in executed
    merge = next(s for s in executed if s.startswith("MERGE"))
    assert (
        "WHEN MATCHED THEN UPDATE SET t.[region] = s.[region], t.[code] = s.[code], t.[amount] = s.[amount]"
        in merge
    )
    assert merge.endswith(
        "WHEN NOT MATCHED BY TARGET THEN INSERT ([order_id], [region], [code], [amount]) VALUES (s.[order_id], s.[region], s.[code], s.[amount]);"
    )
    staged = next(c for c in calls(sql_server, "executemany") if c[1].startswith("INSERT INTO #sab_stage"))
    assert staged[3] is True  # fast_executemany
    assert staged[2][1] == (2, "South", "B2", None)  # NaN is NULL
    assert calls(sql_server, "setinputsizes")[-1][1] == [None, (-9, 40, 0), (12, 10, 0), (3, 12, 2)]
    assert sql_server["log"][-1] == ("commit",)


def test_sql_server_sends_each_value_in_the_targets_exact_type(sql_server: dict[str, Any]) -> None:
    import datetime as dt
    import uuid

    sql_server["columns"] = [
        ("event_id", "uniqueidentifier", 16, 0, 0, False, False),
        ("at", "datetime2", 8, 27, 7, False, False),
        ("at_zone", "datetimeoffset", 10, 34, 7, False, False),
        ("done", "bit", 1, 1, 0, False, False),
        ("payload", "varbinary", -1, 0, 0, False, False),
        ("price", "decimal", 9, 18, 4, False, False),
    ]
    sql_server["primary"] = True
    zone = dt.timezone(dt.timedelta(hours=2))
    rows = pd.DataFrame(
        {
            "event_id": [str(uuid.UUID(int=1)), str(uuid.UUID(int=2))],
            "at": pd.to_datetime(["2026-01-02 03:04:05.1234567", None]),  # NaT is NULL
            "at_zone": [dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=zone), None],
            "done": [True, False],
            "payload": [b"\x00\x01", None],
            "price": [1.2345, float("nan")],  # NaN is NULL
        }
    )
    text = cell("write_sql_server_append", dry_run=False, target="dbo.events")
    assert run(text, orders=rows).counts == {"inserted": 2}
    sizes = calls(sql_server, "setinputsizes")[-1][1]
    assert sizes == [None, (93, 27, 7), None, None, (-3, 0, 0), (3, 18, 4)]
    (insert,) = [c for c in calls(sql_server, "executemany") if c[1].startswith("INSERT INTO [dbo].[events]")]
    first, second = insert[2]
    assert first[0] == "00000000-0000-0000-0000-000000000001" and first[3] is True and first[4] == b"\x00\x01"
    # a datetimeoffset's text with its offset: the same instant (DuckDB keeps zoned times as instants)
    assert dt.datetime.fromisoformat(first[2]) == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=zone)
    assert isinstance(first[1], dt.datetime) and first[1].microsecond == 123456
    assert second[1] is None and second[2] is None and second[4] is None and second[5] is None


def test_sql_server_runs_the_whole_transaction_again_on_azures_passing_errors(
    sql_server: dict[str, Any],
) -> None:
    passing = FakeOdbcError(
        "08S01", "[Microsoft][ODBC Driver 18 for SQL Server]Communication link failure (10054)"
    )
    busy = FakeOdbcError("42000", "Database 'shop' on server 'made-up' is not currently available (40613)")
    sql_server["failures"] = [("executemany", "INSERT INTO #sab_stage", passing), ("execute", "MERGE", busy)]
    text = cell("write_sql_server_upsert", dry_run=False, target="dbo.orders", **{"key column": "order_id"})
    done = run(text, orders=ROWS)
    assert done.counts == {"updated": 1, "inserted": 2}
    assert len(sql_server["opened"]) == 3  # two passing errors: two fresh connections, each a whole try
    assert [c for c in sql_server["log"] if c[0] in ("commit", "rollback")] == [
        ("rollback",),
        ("rollback",),
        ("commit",),
    ]
    assert sum(1 for c in calls(sql_server, "execute") if c[1].startswith("CREATE TABLE #sab_stage")) == 3
    assert "Try 1 met a passing error" in str(done) and "Try 2 met a passing error" in str(done)
    assert write_sql.transient(
        FakeOdbcError("40001", "Transaction (Process ID 61) was deadlocked ... (1205)")
    )
    assert not write_sql.transient(FakeOdbcError("23000", "Violation of PRIMARY KEY constraint (2627)"))


def test_sql_server_falls_back_to_update_then_insert_when_merge_is_refused(
    sql_server: dict[str, Any],
) -> None:
    refused = FakeOdbcError("42000", "MERGE is not supported in this version of SQL Server (40514)")
    sql_server["failures"] = [("execute", "MERGE", refused)]
    done = run(
        cell("write_sql_server_upsert", dry_run=False, target="dbo.orders", **{"key column": "order_id"}),
        orders=ROWS,
    )
    executed = [c[1] for c in calls(sql_server, "execute")]
    assert "ROLLBACK TRANSACTION sab_merge" in executed
    assert any(s.startswith("UPDATE t SET t.[region] = s.[region]") for s in executed)
    assert any(s.startswith("INSERT INTO [dbo].[orders]") and "WHERE NOT EXISTS" in s for s in executed)
    assert "MERGE was refused here: UPDATE, then INSERT, in the same transaction." in str(done)


def test_sql_server_keys_default_to_the_primary_key_and_identity_and_computed_columns_are_said(
    sql_server: dict[str, Any],
) -> None:
    text = cell("write_sql_server_upsert", dry_run=True, target="dbo.orders", **{"key column": "order_id"})
    no_keys = text.replace('keys = ["order_id"]', "keys = []")
    assert "Keys      order_id" in str(run(no_keys, orders=ROWS))
    sql_server["primary"] = False
    with pytest.raises(WriteError, match=r"dbo\.orders has no primary key: name the key columns"):
        run(no_keys, orders=ROWS)
    numbered = ROWS.assign(row_no=[7, 8, 9])
    with pytest.raises(WriteError, match="row_no is dbo.orders's identity column: SQL Server numbers it"):
        run(cell("write_sql_server_append", dry_run=True, target="dbo.orders"), orders=numbered)
    chosen = cell("write_sql_server_append", dry_run=False, target="dbo.orders").replace(
        "identity_insert = False", "identity_insert = True"
    )
    run(chosen, orders=numbered)
    executed = [c[1] for c in calls(sql_server, "execute")]
    assert executed[-2:] == [
        "SET IDENTITY_INSERT [dbo].[orders] ON",
        "SET IDENTITY_INSERT [dbo].[orders] OFF",
    ]
    with pytest.raises(WriteError, match="total is computed by dbo.orders"):
        run(
            cell("write_sql_server_append", dry_run=True, target="dbo.orders"),
            orders=ROWS.assign(total=[1, 2, 3]),
        )


def test_sql_server_batches_stay_under_its_parameter_limit_without_fast_executemany(
    sql_server: dict[str, Any],
) -> None:
    w = write_sql.SqlServerWrite("Warehouse", "dbo.orders", "append", ROWS, dry_run=False, batch_size=5000)
    names = ["order_id", "region", "code", "amount"]
    assert w.rows_a_batch(names) == 5000
    w.fast = False
    assert w.rows_a_batch(names) == 524  # 2,099 parameters / 4 columns
    w.insert_into("#sab_stage", names)
    inserted = calls(sql_server, "execute")[-1]
    assert inserted[1].startswith(
        "INSERT INTO #sab_stage ([order_id], [region], [code], [amount]) VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)"
    )
    assert len(inserted[2]) == 12


def test_sql_server_delete_deletes_by_a_join_on_the_staged_keys(sql_server: dict[str, Any]) -> None:
    sql_server["matched"] = 2
    gone = pd.DataFrame({"order_id": [1, 2, 2]})
    assert run(
        cell("write_sql_server_delete", dry_run=True, target="dbo.orders", **{"key column": "order_id"}),
        orders=gone,
    ).planned == {"deleted": 2}
    done = run(
        cell("write_sql_server_delete", dry_run=False, target="dbo.orders", **{"key column": "order_id"}),
        orders=gone,
    )
    assert done.counts == {"deleted": 2}
    executed = [c[1] for c in calls(sql_server, "execute")]
    assert "DELETE t FROM [dbo].[orders] AS t JOIN #sab_keys AS s ON t.[order_id] = s.[order_id]" in executed
    staged = [c for c in calls(sql_server, "executemany") if c[1].startswith("INSERT INTO #sab_keys")][-1]
    assert sorted(staged[2]) == [(1,), (2,)]  # each key once


# ===== Trino: a statement at a time, MERGE where the connector has it =====


class FakeTrino:
    """trino.dbapi's connection, stood in for: every statement kept; a MERGE refused when `merge` is off,
    in Trino's own words."""

    def __init__(self, world: dict[str, Any]) -> None:
        self.world = world
        self.log: list[Any] = world.setdefault("log", [])

    def cursor(self) -> FakeTrino:
        return self

    def execute(self, sql: str, params: Any = None) -> None:
        self.log.append((sql, params))
        if sql.startswith("MERGE") and not self.world.get("merge", True):
            raise RuntimeError(
                'TrinoUserError(type=USER_ERROR, name=NOT_SUPPORTED, message="This connector does not support MERGE")'
            )
        self._rows = [(self.world.get("count", 4),)] if sql.startswith("SELECT COUNT(*)") else []
        self.description = [("order_id",), ("region",), ("amount",)]

    def fetchall(self) -> list[Any]:
        return self._rows

    def commit(self) -> None:
        self.log.append(("commit",))

    def rollback(self) -> None:
        raise AssertionError("Trino's connection is never rolled back: it has no transaction")

    def close(self) -> None:
        pass


FakeTrino.__module__ = "trino.dbapi"


def test_trino_merges_a_batch_at_a_time_and_says_when_the_connector_cannot(
    monkeypatch: pytest.MonkeyPatch, connection: Callable[[Callable[[], Any]], list[str]]
) -> None:
    fake = types.ModuleType("trino")
    fake.paramstyle = "qmark"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trino", fake)
    world: dict[str, Any] = {}
    connection(lambda: FakeTrino(world))
    values = {"target": "iceberg.sales.orders"}
    text = cell("write_trino_upsert", dry_run=False, **values).replace("batch_size = 200", "batch_size = 2")
    done = run(text, orders=ORDERS)
    merges = [sql for sql, _ in world["log"] if sql.startswith("MERGE")]
    assert len(merges) == 2  # three rows, two a statement
    assert merges[0].startswith(
        'MERGE INTO "iceberg"."sales"."orders" AS t USING (VALUES (?, ?, ?), (?, ?, ?)) AS s ("order_id", "region", "amount")'
    )
    assert 'WHEN MATCHED THEN UPDATE SET "region" = s."region", "amount" = s."amount"' in merges[0]
    assert done.facts[2] == ("Database", "Trino (no transactions)") and ("commit",) not in world["log"]
    world["merge"] = False
    with pytest.raises(WriteError) as refused:
        run(text, orders=ORDERS)
    said = str(refused.value)
    assert said.startswith("Batch 1 (rows 1 to 2) failed: TrinoUserError")
    assert "This catalog's connector has no MERGE: Iceberg, Delta Lake, Hive" in said
    assert said.endswith("Trino writes each statement by itself: nothing was written.")


# ===== Dataverse: the Web API's change sets =====


@pytest.fixture
def crm(
    monkeypatch: pytest.MonkeyPatch, connection: Callable[[Callable[[], Any]], list[str]]
) -> Iterator[dataverse_standin.StandIn]:
    from tests.fake_keyring import memory_keyring

    running = dataverse_standin.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    code = (
        dataverse.APP.replace("https://your-org.crm.dynamics.com", running.url)
        .replace("my-tenant-id", dataverse_standin.TENANT)
        .replace("my-client-id", dataverse_standin.CLIENT)
    )
    with memory_keyring():
        conn, _ = run_code(code, "conn", {"client secret": dataverse_standin.SECRET}, "Sales CRM")
    connection(lambda: conn)
    yield running
    running.stop()


def accounts(standin: dataverse_standin.StandIn) -> dict[str, dict[str, Any]]:
    return {str(r["accountnumber"]): r for r in standin.rows["account"]}


def test_dataverse_create_sends_change_sets_with_choice_labels_as_numbers(
    crm: dataverse_standin.StandIn,
) -> None:
    rows = pd.DataFrame({"name": ["Oak Hollow Tea", "Pine Ridge Bikes"], "accountnumber": ["AC-2001", "AC-2002"],
                         "industrycode": ["Retail", "Consulting"]})  # fmt: skip
    values = {"target": "account", "connection": "Sales CRM"}
    dry = run(cell("write_dataverse_create", dry_run=True, **values), orders=rows)
    assert dry.planned == {"inserted": 2} and crm.batches == []
    assert "Choices  industrycode: labels sent as their numbers" in str(dry)
    crm.throttle = 1  # the first $batch is asked to wait: it goes again
    done = run(cell("write_dataverse_create", dry_run=False, **values), orders=rows)
    assert done.counts == {"inserted": 2}
    made = accounts(crm)
    assert made["AC-2001"]["industrycode"] == 19 and made["AC-2002"]["industrycode"] == 7
    assert [b["applied"] for b in crm.batches] == [True]
    assert all(
        r["authorization"] == f"Bearer {dataverse_standin.TOKEN}"
        for r in crm.requests
        if r["what"] == "batch"
    )
    with pytest.raises(WriteError, match="industrycode has no choice 'Bakery': its choices are"):
        run(
            cell("write_dataverse_create", dry_run=False, **values),
            orders=rows.assign(industrycode=["Bakery", "Retail"]),
        )


def test_dataverse_upsert_update_and_delete_find_records_by_an_alternate_key(
    crm: dataverse_standin.StandIn,
) -> None:
    values = {"target": "account", "connection": "Sales CRM", "key column": "accountnumber"}
    rows = pd.DataFrame(
        {"accountnumber": ["AC-1001", "AC-3001"], "name": ["Bluefin Outfitters Ltd", "Cedar Lane Pottery"]}
    )
    dry = run(cell("write_dataverse_upsert", dry_run=True, **values), orders=rows)
    assert dry.planned == {"updated": 1, "inserted": 1}
    done = run(cell("write_dataverse_upsert", dry_run=False, **values), orders=rows)
    assert done.counts == {"inserted": 1, "updated": 1}
    assert accounts(crm)["AC-1001"]["name"] == "Bluefin Outfitters Ltd" and "AC-3001" in accounts(crm)
    with pytest.raises(ValueError, match="1 keys are not records of account: ac-9999"):
        run(
            cell("write_dataverse_update", dry_run=True, **values),
            orders=pd.DataFrame({"accountnumber": ["AC-9999"], "name": ["x"]}),
        )
    updated = run(
        cell("write_dataverse_update", dry_run=False, **values), orders=rows.assign(name=["Bluefin", "Cedar"])
    )
    assert updated.counts == {"updated": 2} and accounts(crm)["AC-3001"]["name"] == "Cedar"
    gone = run(
        cell("write_dataverse_delete", dry_run=False, **values),
        orders=pd.DataFrame({"accountnumber": ["AC-3001", "AC-9999"]}),
    )
    assert gone.counts == {"deleted": 1} and "AC-3001" not in accounts(crm)


def test_dataverse_a_refused_change_set_is_rolled_back_and_named(crm: dataverse_standin.StandIn) -> None:
    values = {"target": "account", "connection": "Sales CRM"}
    rows = pd.DataFrame({"name": ["A", "B", "C"], "accountnumber": ["AC-4001", "AC-4002", "AC-4003"],
                         "numberofemployees": [1, 2, 3], "industrycode": [1, 1, 999]})  # fmt: skip
    text = cell("write_dataverse_create", dry_run=False, **values).replace(
        "batch_size = 1000", "batch_size = 2"
    )
    with pytest.raises(WriteError) as refused:
        run(text, orders=rows)
    said = str(refused.value)
    assert said.startswith(
        "Batch 2 (rows 3 to 3) was refused and rolled back: Dataverse refused (400): 999 is not a valid value"
    )
    assert "the 2 rows before it were written" in said
    assert [b["applied"] for b in crm.batches] == [True, False]
    assert "AC-4003" not in accounts(crm) and "AC-4002" in accounts(crm)


# ===== files: written beside the target, then put in its place =====


def test_files_are_written_and_read_back(tmp_path: Path) -> None:
    import duckdb
    import openpyxl

    rows = pd.DataFrame(
        {"order_id": [1, 2, 3], "region": ["North", "South", "North"], "amount": [1.5, 2.5, None]}
    )
    csv = tmp_path / "orders.csv"
    dry = run(cell("write_csv_file", dry_run=True, file=str(csv)), orders=rows)
    assert not csv.exists() and f"COPY sab_rows TO '{csv}' (FORMAT csv, HEADER, DELIMITER ',')" in str(dry)
    assert run(cell("write_csv_file", dry_run=False, file=str(csv)), orders=rows).counts == {"written": 3}
    assert pd.read_csv(csv)["region"].tolist() == ["North", "South", "North"]
    with pytest.raises(WriteError, match="There is a file at .* already"):
        run(cell("write_csv_file", dry_run=True, file=str(csv)), orders=rows)
    parquet = tmp_path / "orders.parquet"
    run(cell("write_parquet_file", dry_run=False, file=str(parquet)), orders=rows)
    assert pd.read_parquet(parquet).equals(rows)
    folder = tmp_path / "by_region"
    run(cell("write_partitioned_parquet", dry_run=False, folder=str(folder)), orders=rows)
    assert sorted(p.name for p in folder.iterdir()) == ["region=North", "region=South"]
    add = cell("write_partitioned_parquet", dry_run=False, folder=str(folder)).replace(
        'if_there = "stop"', 'if_there = "add"'
    )
    run(add, orders=rows)
    read = f"SELECT count(*) FROM read_parquet('{folder}/*/*.parquet', hive_partitioning = true)"
    assert duckdb.execute(read).fetchall() == [(6,)]
    data = tmp_path / "orders.json"
    run(cell("write_json_file", dry_run=False, file=str(data)), orders=rows)
    assert [r["order_id"] for r in json.loads(data.read_text())] == [1, 2, 3]
    book = tmp_path / "orders.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "Notes"
    workbook.active["A1"] = "kept"
    workbook.save(book)
    run(cell("write_excel_sheet", dry_run=False, file=str(book), sheet="Orders"), orders=rows)
    added = cell("write_excel_sheet", dry_run=False, file=str(book), sheet="Orders").replace(
        'if_there = "stop"', 'if_there = "add"'
    )
    run(added, orders=rows.head(1))
    opened = openpyxl.load_workbook(book)
    assert opened.sheetnames == ["Notes", "Orders"] and opened["Notes"]["A1"].value == "kept"
    assert [c.value for c in opened["Orders"][1]] == ["order_id", "region", "amount"]
    assert opened["Orders"].max_row == 5  # the header, three rows, then one added below
    with pytest.raises(ValueError, match="has a sheet 'Orders' already"):
        run(cell("write_excel_sheet", dry_run=True, file=str(book), sheet="Orders"), orders=rows)
