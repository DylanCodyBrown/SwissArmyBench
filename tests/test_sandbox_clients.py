"""The mock clients (server/sandbox_clients.py) have their real clients' shape, and the same endpoint code
runs
against both (the owner, 2026-11-21: "Things that get built should always hand back to a client that mimics
the
connections client shape").

Each real client is taken from its starter's own code (the SQL Server starter's SqlServer, the Dataverse
starter's Dataverse, the SharePoint lists starter's SharePointLists) or its driver (sqlite3, duckdb); every
public
method it has, the mock has, with the same parameters in the same order and the same defaults. Then one
function
reads a made-up table through the real client (sqlite3; Dataverse's stand-in, tests/dataverse_standin.py) and
through the mock over the sandbox holding the same rows: the same answer. The source's dialect is spoken
(domain/sandbox_dialects.py) and what cannot be emulated is refused with its line. Made-up data only."""

from __future__ import annotations

import inspect
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import dataverse, sharepoint, sql_server
from swissarmybench.domain import sandbox_dialects as dialects
from swissarmybench.domain.sandbox import SandboxError
from swissarmybench.server import sandbox_clients as mocks
from tests import dataverse_standin as made_up
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring


def _class_from(code: str, name: str) -> type:
    namespace: dict[str, Any] = {"secret": str}
    exec(compile(code, f"<{name}>", "exec"), namespace)  # noqa: S102 (the starters' own code, made up nothing)
    return namespace[name]  # type: ignore[no-any-return]


def real_sql_server() -> type:
    return _class_from(sql_server._IMPORTS + sql_server.RUNTIME, "SqlServer")


def real_dataverse() -> type:
    return _class_from(dataverse.APP.split("\nconn = ")[0], "Dataverse")


def real_sharepoint() -> type:
    return _class_from(sharepoint.LISTS.split("\nconn = ")[0], "SharePointLists")


def _public(kind: type) -> dict[str, Any]:
    return {
        n: v
        for n, v in inspect.getmembers(kind)
        if not n.startswith("_") and (callable(v) or isinstance(v, property))
    }


def _shape(fn: Any) -> list[tuple[str, Any, Any]]:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    return [(p.name, p.kind, p.default) for p in signature.parameters.values() if p.name != "self"]


@pytest.mark.parametrize(
    ("real", "mock"),
    [
        (real_sql_server, mocks.MockSqlServer),
        (real_dataverse, mocks.MockDataverse),
        (real_sharepoint, mocks.MockSharePoint),
    ],
    ids=["sqlserver", "dataverse", "sharepoint_lists"],
)
def test_every_public_method_of_the_real_client_is_on_its_mock(real: Any, mock: type) -> None:
    kind = real()
    theirs, ours = _public(kind), _public(mock)
    missing = sorted(set(theirs) - set(ours))
    assert not missing, f"{mock.__name__} lacks {missing}"
    for name, fn in theirs.items():
        if isinstance(fn, property):
            assert isinstance(ours[name], property) or not callable(ours[name]), name
            continue
        assert _shape(ours[name]) == _shape(fn), f"{mock.__name__}.{name}"


def test_the_cursors_keep_their_drivers_execute() -> None:
    cursor: Any = _class_from(sql_server._IMPORTS + sql_server.RUNTIME, "Cursor")
    assert _shape(mocks.MockSqlServerCursor.execute) == _shape(cursor.execute)
    tds: Any = _class_from(dataverse.APP.split("\nconn = ")[0], "SqlCursor")
    assert _shape(mocks.MockDataverseCursor.execute) == _shape(tds.execute)
    for name in ("cursor", "execute", "executemany", "commit", "rollback", "close"):
        assert hasattr(sqlite3.Connection, name) and hasattr(mocks.MockDbApi, name), name
    for name in (
        "execute",
        "executemany",
        "fetchone",
        "fetchmany",
        "fetchall",
        "close",
        "description",
        "rowcount",
    ):
        assert hasattr(sqlite3.Cursor, name), name
        assert hasattr(mocks.MockCursor(mocks.MockDbApi("x", "sqlite", mocks.Link(""))), name), name
    import duckdb

    for name in (
        "execute",
        "fetchone",
        "fetchmany",
        "fetchall",
        "description",
        "cursor",
        "commit",
        "rollback",
        "df",
    ):
        assert hasattr(duckdb.DuckDBPyConnection, name) and hasattr(mocks.MockDuckDB, name), name


# ===== the dialects =====


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


def test_odata_fetchxml_and_list_filters() -> None:
    where, params = dialects.odata_where(
        "revenue gt 10 and (contains(name,'O''Neil') or statecode eq 0)", ["revenue", "name", "statecode"]
    )
    assert where == '"revenue" > ? AND ("name" ILIKE ? OR "statecode" = ?)' and params == [10, "%O'Neil%", 0]
    with pytest.raises(SandboxError, match="cannot emulate the operator has"):
        dialects.odata_where("name has 'x'", ["name"])
    with pytest.raises(SandboxError, match="cannot emulate a FetchXML link-entity"):
        dialects.fetchxml(
            '<fetch><entity name="a"><link-entity name="b"/></entity></fetch>', ["a"], lambda t: []
        )
    found = dialects.fetchxml(
        '<fetch top="2"><entity name="account"><attribute name="name"/>'
        '<filter><condition attribute="revenue" operator="ge" value="5"/></filter>'
        '<order attribute="name"/></entity></fetch>',
        ["account"],
        lambda t: ["name", "revenue"],
    )
    assert found.sql == 'SELECT "name" FROM "account" WHERE ("revenue" >= ?) ORDER BY "name" LIMIT 2'
    where, params = dialects.list_where(
        [["Status", "=", "Open"], ["Size", "between", [1, 5]]], ["Status", "Size"]
    )
    assert where == '"Status" = ? AND "Size" BETWEEN ? AND ?' and params == ["Open", 1, 5]


# ===== the same code, the real client and the mock =====


class TestLink(mocks.Link):
    """The mock's door, through the test's client instead of HTTP."""

    def __init__(self, client: TestClient, error: type[mocks.MockError] = mocks.MockError) -> None:
        super().__init__("", error)
        self.client = client

    def _post(self, op: str, body: dict[str, Any]) -> dict[str, Any]:
        answer = self.client.post("/sandbox/data", json={"op": op} | body, headers=AUTH)
        if answer.status_code != 200:
            raise self.error(answer.json()["error"])
        return dict(answer.json())


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        assert (
            client.post("/project/new", json={"path": str(tmp_path / "shop")}, headers=AUTH).status_code
            == 200
        )
        yield client


def _put(client: TestClient, tmp_path: Path, name: str, table: pa.Table) -> None:
    import pyarrow.parquet as pq

    path = tmp_path / f"{name}.parquet"
    pq.write_table(table, path)
    answer = client.post(
        "/sandbox/tables", json={"from": "file", "path": str(path), "name": name}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text


def orders_in(db: Any, region: str) -> list[tuple[Any, ...]]:
    """One endpoint's code, as it would be in API.py: the source's own SQL and marks."""
    cursor = db.cursor()
    cursor.execute("SELECT order_id, amount FROM orders WHERE region = ? ORDER BY order_id", (region,))
    rows = [tuple(r) for r in cursor.fetchall()]
    cursor.close()
    return rows


def test_the_same_code_reads_sqlite_and_its_mock_alike(boxed: TestClient, tmp_path: Path) -> None:
    rows = [(1, "West", 10.5), (2, "East", 7.25), (3, "West", 3.0)]
    real = sqlite3.connect(":memory:")
    real.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount REAL)")
    real.executemany("INSERT INTO orders VALUES (?, ?, ?)", rows)
    table = pa.table(
        {"order_id": [r[0] for r in rows], "region": [r[1] for r in rows], "amount": [r[2] for r in rows]}
    )
    _put(boxed, tmp_path, "orders", table)
    mock = mocks.MockDbApi("Sandbox", "sqlite", TestLink(boxed))
    assert orders_in(mock, "West") == orders_in(real, "West") == [(1, 10.5), (3, 3.0)]
    cursor = mock.cursor()
    cursor.execute("UPDATE orders SET amount = ? WHERE order_id = ?", (1.0, 1))
    assert cursor.rowcount == 1
    with pytest.raises(mocks.MockError, match="makes a table from a query"):
        mock.execute("CREATE TABLE x (a INT)")


def test_a_read_past_one_answer_comes_back_whole_as_the_real_client_gives_it(
    boxed: TestClient, tmp_path: Path
) -> None:
    """MAX_ROWS_ANSWERED is one answer's size, not a cut (the test app's gap 10): every real client hands back
    every row, so the mock follows the rest page by page; a page asked for once it is gone is said."""
    from swissarmybench.domain import sandbox as rules

    many = rules.MAX_ROWS_ANSWERED * 2 + 3
    _put(boxed, tmp_path, "lines", pa.table({"line_id": list(range(many)), "tags": [["a", "b"]] * many}))
    duck = mocks.MockDuckDB(TestLink(boxed))
    rows = duck.execute("SELECT line_id, tags FROM lines ORDER BY line_id").fetchall()
    assert len(rows) == many and rows[-1] == (many - 1, ["a", "b"]) and rows[0][0] == 0
    assert len(duck.execute("SELECT * FROM lines").df()) == many
    db = mocks.MockDbApi("Sandbox", "postgres", TestLink(boxed))
    assert [
        r[0] for r in db.execute("SELECT line_id FROM lines WHERE line_id >= %s", (5,)).fetchall()
    ] == list(range(5, many))
    first = boxed.post(
        "/sandbox/data",
        json={"op": "sql", "connection": "Sandbox", "sql": "SELECT * FROM lines"},
        headers=AUTH,
    ).json()
    assert len(first["rows"]) == rules.MAX_ROWS_ANSWERED and first["left"] == many - rules.MAX_ROWS_ANSWERED
    second = boxed.post("/sandbox/data", json={"op": "more", "more": first["more"]}, headers=AUTH).json()
    assert len(second["rows"]) == rules.MAX_ROWS_ANSWERED and second["more"]
    again = boxed.post("/sandbox/data", json={"op": "more", "more": first["more"]}, headers=AUTH)
    assert again.status_code == 404 and "read it again" in again.json()["error"]


def test_an_api_makes_views_tables_and_sequences_and_reset_undoes_them(
    boxed: TestClient, tmp_path: Path
) -> None:
    """The test app's gaps 8 and 9: CREATE VIEW, CREATE TABLE AS (T-SQL's SELECT INTO) and sequences through
    the mock, each listed by tables() and columns(); never over a table the user added; Reset undoes them."""
    _put(boxed, tmp_path, "orders", pa.table({"order_id": [1, 2, 3], "region": ["West", "East", "West"]}))
    pg = mocks.MockDbApi("Sandbox", "postgres", TestLink(boxed))
    ms = mocks.MockSqlServer("Sandbox", TestLink(boxed, mocks.SqlServerError))
    with pytest.raises(mocks.MockError, match="a view cannot hold a value given apart"):
        pg.execute("CREATE VIEW west AS SELECT order_id FROM orders WHERE region = %s", ("West",))
    pg.execute("CREATE VIEW west AS SELECT order_id FROM orders WHERE region = 'West'")
    assert pg.execute("SELECT count(*) FROM west").fetchone() == (2,)
    ms.cursor().execute("SELECT order_id, region INTO dbo.east FROM orders WHERE region = ?", "East")
    ms.cursor().execute("CREATE SEQUENCE order_no START WITH 100")
    ms.cursor().execute("INSERT INTO east (order_id, region) VALUES (NEXT VALUE FOR order_no, 'North')")
    assert [r[0] for r in pg.execute("SELECT order_id FROM east ORDER BY 1").fetchall()] == [2, 100]
    assert pg.tables() == ms.tables() == ["east", "orders", "west"]
    assert pg.columns("WEST") == [{"name": "order_id", "type": "BIGINT", "key": False}]
    with pytest.raises(mocks.MockError, match="no table 'nope'"):
        pg.columns("nope")
    listed = {t["name"]: t for t in boxed.get("/sandbox", headers=AUTH).json()["tables"]}
    assert listed["west"]["source_words"] == "Made by the API (a view)"
    with pytest.raises(
        mocks.MockError, match="orders is a sandbox table you added: an API cannot replace it"
    ):
        pg.execute("CREATE OR REPLACE VIEW orders AS SELECT 1 AS one")
    with pytest.raises(mocks.MockError, match="cannot drop it"):
        pg.execute("DROP TABLE orders")
    with pytest.raises(mocks.MockError, match="a table from a query"):
        pg.execute("CREATE TABLE notes (a INT)")
    pg.execute("DROP VIEW west")
    assert pg.tables() == ["east", "orders"]
    pg.execute("CREATE VIEW west AS SELECT order_id FROM orders WHERE region = 'West'")
    assert boxed.post("/sandbox/reset", json={}, headers=AUTH).status_code == 200
    assert pg.tables() == ["orders"]
    assert set(boxed.get("/sandbox", headers=AUTH).json()["tables"][0]) and [
        t["name"] for t in boxed.get("/sandbox", headers=AUTH).json()["tables"]
    ] == ["orders"]
    with pytest.raises(mocks.MockError):
        pg.execute("SELECT nextval('order_no')")


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def big_accounts(conn: Any) -> Any:
    """One endpoint's code for Dataverse: an OData read through the client's own rows()."""
    rows, _ = conn.rows(
        "account", columns=["name", "revenue"], filter="revenue gt 1000000", order_by="revenue desc", limit=3
    )
    return rows


def test_the_same_code_reads_dataverse_and_its_mock_alike(
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
    mock = mocks.MockDataverse("Sandbox", TestLink(boxed, mocks.DataverseError))
    assert big_accounts(mock) == big_accounts(real)
    with pytest.raises(mocks.DataverseError, match="cannot emulate a Web API call"):
        mock.get("WhoAmI", "Who am I")
    with pytest.raises(mocks.DataverseError, match="read-only: SELECT only"):
        mock.cursor().execute("DELETE FROM account")
