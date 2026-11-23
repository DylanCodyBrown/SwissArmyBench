"""A connection's tables in DuckDB SQL, by the connection's name (the owner, 2026-11-17: "I feel like I
should be able to write duckdb as Select * from [Finance Captive].EntityName"). Two SQLite connections and
the Power BI stand-in (tests/powerbi_standin.py): a join across a database and a Power BI dataset in one
DuckDB query, bracket and quote spellings, a table two datasets share needing the dataset, an unknown name
saying what there is, the session's reads and Refresh, the tree, Open all of a dataset. Made-up data only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.ipc as ipc
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import connection_sql as cs
from swissarmybench.domain import connection_tables as ct
from swissarmybench.domain import web_calls
from swissarmybench.domain.connection_swap import Place
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_powerbi import NOT_TO_BE_SEEN, saved_connection


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


CATALOG = (
    "SELECT 'main' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
    "p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position "
    "FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p "
    "WHERE m.type = 'table' ORDER BY m.name, p.cid"
)


def sqlite_connection(client: TestClient, tmp_path: Path, name: str, tables: dict[str, Any]) -> None:
    path = tmp_path / f"{name.replace(' ', '_')}.sqlite"
    with sqlite3.connect(path) as made:
        for table, (columns, rows) in tables.items():
            made.execute(f"CREATE TABLE {table} ({columns})")
            marks = ", ".join("?" for _ in rows[0])
            made.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)  # noqa: S608 (made-up tables)
    body = {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{path}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
        "catalog": {"language": "sql", "command": CATALOG},
    }
    ok(client.post("/connections", json=body, headers=AUTH))


def shop(client: TestClient, tmp_path: Path) -> None:
    """Shop: the made-up customers' segments (keys 1-8 as the Power BI model's), and a second Shop2."""
    segments = [(i, "Gold" if i % 2 else "Silver") for i in range(1, 9)]
    sqlite_connection(client, tmp_path, "Shop", {"segments": ("CustomerKey INTEGER, Segment TEXT", segments)})
    sqlite_connection(
        client,
        tmp_path,
        "Shop Two",
        {"targets": ("Segment TEXT, Target REAL", [("Gold", 100.0), ("Silver", 50.0)])},
    )


def query(client: TestClient, name: str, sql: str, who: dict[str, str] = AUTH) -> Any:
    return client.post(f"/datasets/{name}/query", json={"sql": sql}, headers=who)


def rows(client: TestClient, grid: str) -> list[list[Any]]:
    return list(ok(client.get(f"/grids/{grid}/rows", headers=AUTH))["rows"])


# ===== the rules =====


def test_brackets_quote_a_connections_name_only() -> None:
    names = ["Finance Captive", "Shop"]
    text = "SELECT a[1], '[Finance Captive].x' FROM [Finance Captive].[Sales model].Date JOIN [y].z ON 1=1"
    assert cs.quote_brackets(text, names) == (
        'SELECT a[1], \'[Finance Captive].x\' FROM "Finance Captive"."Sales model".Date JOIN [y].z ON 1=1'
    )


def test_references_resolve_by_name_in_any_case_and_a_shared_one_names_its_dataset() -> None:
    sql = cs.quote_brackets(
        'SELECT * FROM [finance captive].sales s JOIN "Shop".main.segments g ON 1=1',
        ["Finance Captive", "Shop"],
    )
    found = cs.references(sql, ["Finance Captive", "Shop"])
    assert [(r.connection, r.parts) for r in found] == [
        ("Finance Captive", ("sales",)),
        ("Shop", ("main", "segments")),
    ]
    places = [
        Place("", "Sales model", "Sales"),
        Place("", "Sales model", "Date"),
        Place("", "Budget model", "Date"),
    ]
    assert ct.resolve("F", "powerbi", ["SALES"], places) == places[0]
    assert ct.resolve("F", "powerbi", ["budget MODEL", "date"], places) == places[2]
    with pytest.raises(ct.ConnectionSqlError, match="several datasets of F: Budget model, Sales model"):
        ct.resolve("F", "powerbi", ["Date"], places)
    with pytest.raises(ct.ConnectionSqlError, match=r"F has no table Sals\. Did you mean Sales"):
        ct.resolve("F", "powerbi", ["Sals"], places)
    db = [Place("", "main", "orders"), Place("", "sales", "orders"), Place("w", "dbo", "items")]
    assert ct.resolve("W", "database", ["sales", "orders"], db) == db[1]
    assert ct.resolve("W", "database", ["w", "dbo", "ITEMS"], db) == db[2]
    with pytest.raises(ct.ConnectionSqlError, match=r"could be main\.orders, sales\.orders"):
        ct.resolve("W", "database", ["orders"], db)
    rewritten = cs.rewrite(
        sql, ["Finance Captive", "Shop"], {r.key: cs.target_name(i) for i, r in enumerate(found)}
    )
    assert rewritten == 'SELECT * FROM "__sab_conn_0" AS s JOIN "__sab_conn_1" AS g ON 1 = 1'


def test_a_web_call_blade_is_a_table_only_with_return_as_table() -> None:
    call = {"api": "Orders", "operation": "list_orders", "method": "GET", "path": "/orders"}
    assert web_calls.is_table({"web_call": call | {"as_table": True}})
    assert not web_calls.is_table({"web_call": call | {"as_table": False}})
    assert not web_calls.is_table({"web_call": call})
    assert not web_calls.is_table({"web_call": call | {"as_table": True, "mode": "write rows"}})
    assert not web_calls.is_table({"kind": "other"})
    # The API blade is the connection its tables are read through; a web call blade is one of its tables.
    assert ct.is_api(["api"], "")
    assert not ct.is_api(["api", "web call"], "")
    assert ct.tables_kind("other", "python", tags=["api"]) == "api"
    assert ct.tables_kind("other", "python", tags=["finance"]) == "python"


# ===== on the server =====


def test_a_join_across_a_database_and_a_power_bi_dataset_in_one_duckdb_query(
    client: TestClient, tmp_path: Path, standin: made_up.StandIn
) -> None:
    saved_connection(client, "Finance Captive")
    shop(client, tmp_path)
    sql = (
        "SELECT g.Segment, t.Target, count(*) AS orders, sum(s.Quantity) AS units "
        "FROM [Finance Captive].[Sales model].Sales s "
        'JOIN "Shop".segments g ON g.CustomerKey = s.CustomerKey '
        "JOIN [Shop Two].targets t ON t.Segment = g.Segment GROUP BY ALL ORDER BY 1"
    )
    made = ok(query(client, "by_segment", sql))
    assert [r[:3] for r in rows(client, made["grid"])] == [["Gold", 100.0, 20], ["Silver", 50.0, 20]]
    reads = made["connection_reads"]
    assert [(r["connection"], r["place"]["table"], r["rows"], r["cached"]) for r in reads] == [
        ("Finance Captive", "Sales", 40, False),
        ("Shop", "segments", 8, False),
        ("Shop Two", "targets", 2, False),
    ]
    assert all(r["read_at"] for r in reads)
    assert "EVALUATE" in " ".join(standin.queries("Sales model"))
    # Read once for the session: the same table again comes from the session's read.
    asked = len(standin.queries("Sales model"))
    again = ok(query(client, "sales_again", "SELECT count(*) FROM [Finance Captive].sales"))
    assert again["connection_reads"][0]["cached"] is True and len(standin.queries("Sales model")) == asked
    # Refresh: read again.
    assert ok(
        client.post("/connections/sql/refresh", json={"connection": "Finance Captive"}, headers=AUTH)
    ) == {"dropped": 1}
    fresh = ok(query(client, "sales_fresh", "SELECT count(*) FROM [Finance Captive].sales"))
    assert fresh["connection_reads"][0]["cached"] is False and len(standin.queries("Sales model")) > asked
    # The grid keeps its query as its origin: its cell reads it again the same way.
    cells = client.get("/workbench/tables", headers=AUTH).text
    assert "sab.sql(" in cells and "Finance Captive" in cells
    for answer in (made, again, fresh, cells):
        assert not any(secret in str(answer) for secret in NOT_TO_BE_SEEN)


def test_a_shared_table_needs_its_dataset_and_an_unknown_one_says_what_there_is(
    client: TestClient, tmp_path: Path, standin: made_up.StandIn
) -> None:
    saved_connection(client, "Finance Captive")
    shared = query(client, "dates", "SELECT * FROM [Finance Captive].Date")
    assert shared.status_code == 400 and "Date is in several datasets of Finance Captive" in shared.text
    assert "Budget model, Sales model" in shared.text
    unknown = query(client, "nothing", 'SELECT * FROM "Finance Captive".Invoices')
    assert unknown.status_code == 400 and "Finance Captive has no table Invoices" in unknown.text
    assert "Customer" in unknown.text
    refused = query(client, "keys", "SELECT * FROM [Team vault].anything")
    assert (
        refused.status_code == 400 and "not a connection: a source of secrets for variables" in refused.text
    )
    # The agent writes the same SQL with the same answer.
    by_agent = query(
        client, "dates_agent", 'SELECT count(*) AS n FROM [Finance Captive]."Budget model".Date', AGENT
    )
    assert by_agent.status_code == 200, by_agent.text


def test_the_tree_open_all_and_a_kernel_read(
    client: TestClient, tmp_path: Path, standin: made_up.StandIn
) -> None:
    saved_connection(client, "Finance Captive")
    tree = ok(client.get("/connections/Finance%20Captive/tree", headers=AUTH))
    assert tree["kind"] == "powerbi" and tree["group"] == "dataset" and tree["state"]["state"] == "loaded"
    sales = next(g for g in tree["groups"] if g["schema"] == "Sales model")
    by_name = {t["table"]: t["sql"] for t in sales["tables"]}
    assert by_name["Sales"] == "[Finance Captive].Sales"
    assert by_name["Date"] == '[Finance Captive]."Sales model".Date'
    opened = ok(
        client.post(
            "/connections/Finance%20Captive/open-dataset", json={"dataset": "sales MODEL"}, headers=AGENT
        )
    )
    assert sorted(o["table"] for o in opened["opened"]) == ["Customer", "Date", "Product", "Sales"]
    assert opened["failed"] == []
    # What a Workbench kernel's %%sql asks: the query pointed at the reads, and each read as Arrow.
    prepared = ok(
        client.post(
            "/connections/sql/prepare", json={"sql": "SELECT * FROM [Finance Captive].Product"}, headers=AUTH
        )
    )
    assert prepared["sql"] == 'SELECT * FROM "__sab_conn_0" AS "Product"'
    got = client.get(f"/connections/sql/reads/{prepared['tables'][0]['id']}", headers=AUTH)
    assert got.status_code == 200
    table = ipc.open_stream(got.content).read_all()
    assert table.num_rows == 3 and "Product Name" in table.column_names
    plain = ok(client.post("/connections/sql/prepare", json={"sql": "SELECT 1"}, headers=AUTH))
    assert plain == {"sql": "SELECT 1", "tables": []}


# ===== never a cut table (2026-11-17): every row the query needs, work sent to the source =====


def big(client: TestClient, tmp_path: Path) -> None:
    """Big: 15,000 made-up orders, more than the 10,000 rows a grid opens with."""
    orders = [(i, "North" if i % 3 else "South", 1.0) for i in range(1, 15_001)]
    sqlite_connection(
        client, tmp_path, "Big", {"orders": ("order_id INTEGER, region TEXT, amount REAL", orders)}
    )


def test_a_query_reads_every_row_it_needs_never_the_first_rows_only(
    client: TestClient, tmp_path: Path
) -> None:
    big(client, tmp_path)
    shop(client, tmp_path)
    sql = (
        "SELECT g.Segment, count(*) AS n, sum(o.amount) AS amount FROM [Big].orders o "
        "JOIN [Shop].segments g ON g.CustomerKey = o.order_id % 8 + 1 GROUP BY ALL ORDER BY 1"
    )
    made = ok(query(client, "by_segment", sql))
    assert [r[1] for r in rows(client, made["grid"])] == [7_500, 7_500]  # a 10,000-row cut would say less
    read = made["connection_reads"][0]
    assert read["rows"] == 15_000 and read["cut"] is False
    assert read["sent"]["columns"] == ["amount", "order_id"]  # only the columns the query uses


def test_a_filter_and_a_safe_limit_go_to_the_source(client: TestClient, tmp_path: Path) -> None:
    big(client, tmp_path)
    sql = "SELECT count(*) FROM [Big].orders WHERE region = 'South' AND order_id > 3000"
    filtered = ok(query(client, "south", sql))
    read = filtered["connection_reads"][0]
    assert read["sent"]["filters"] == "region = 'South' AND order_id > 3000"
    assert read["rows"] == 4_000  # the source sent only those rows
    assert rows(client, filtered["grid"]) == [[4_000]]
    # A LIMIT goes too when nothing else needs more rows ...
    first = ok(query(client, "first", "SELECT * FROM [Big].orders WHERE region = 'North' LIMIT 5"))
    assert first["connection_reads"][0]["sent"]["limit"] == 5 and first["connection_reads"][0]["rows"] == 5
    # ... and not when the query groups, orders or filters on what the source was not sent.
    for at, sql in enumerate(
        (
            "SELECT region, count(*) FROM [Big].orders GROUP BY ALL LIMIT 1",
            "SELECT * FROM [Big].orders ORDER BY amount DESC LIMIT 1",
            "SELECT * FROM [Big].orders WHERE region <> 'North' LIMIT 1",
        )
    ):
        whole = ok(query(client, f"whole_{at}", sql))["connection_reads"][0]
        assert whole["sent"]["limit"] is None and whole["rows"] > 1, sql


def test_past_the_limit_a_table_is_refused_with_how_to_narrow_it(tmp_path: Path) -> None:
    with make_client(tmp_path, max_connection_query_rows=10_000) as client:
        big(client, tmp_path)
        refused = query(client, "all", "SELECT count(*) FROM [Big].orders")
        assert refused.status_code == 400
        assert (
            "[Big].orders has 15,000 rows" in refused.text and "Add a WHERE that narrows it" in refused.text
        )
        narrowed = ok(query(client, "some", "SELECT count(*) FROM [Big].orders WHERE region = 'South'"))
        assert rows(client, narrowed["grid"]) == [[5_000]]


def test_the_sql_box_names_a_connections_table_too(client: TestClient, tmp_path: Path) -> None:
    shop(client, tmp_path)
    made = ok(query(client, "gold", "SELECT * FROM [Shop].segments WHERE Segment = 'Gold'"))
    sql = "SELECT count(*) AS n FROM grid JOIN [Shop Two].targets t USING (Segment)"
    answer = ok(client.post(f"/grids/{made['grid']}/sql", json={"sql": sql}, headers=AGENT))
    assert answer["rows"] == [[4]] and answer["connection_reads"][0]["connection"] == "Shop Two"
