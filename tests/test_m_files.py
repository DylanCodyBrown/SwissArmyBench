"""Power Query files in the app (the owner, 2026-11-27: "I just want a run button and the power query runs" /
"against the original source"): the file's rules, an M source matched to a saved connection, a dataset's
queries as one file, and the server: Run file and one query, the tables it builds, problems before a run, the
composed SQL, a failure's line, Edit in Scripts, New file and the import. duckpq itself is proven by
tests/test_duckpq_*.py; here it is the app's half. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

import duckpq
from swissarmybench.adapters import m_files as files
from swissarmybench.domain import code_tree, new_files, notebooks, project_scope, sab_files, workbench_pages
from swissarmybench.domain import m_files as rules
from swissarmybench.domain.table_cells import Origin
from tests.conftest import AGENT, AUTH, push
from tests.fake_keyring import memory_keyring
from tests.test_connection_tables import CATALOG

ORDERS = pa.table({"order_id": [1, 2, 3], "amount": [10.0, 20.0, 5.0], "customer": ["ann", "bob", "ann"]})


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


# ===== the file's rules =====


def test_a_power_query_file_is_a_document_of_the_scripts_page() -> None:
    for path in ("scripts/orders.pq", "C:\\work\\Sales.PQ", "queries/orders.m"):
        assert rules.is_file(path)
        assert notebooks.kind_of(path) == "powerquery"
        assert workbench_pages.page_of_path(path) == "scripts"
        assert workbench_pages.kind_of_path(path) == "powerquery"
    assert not rules.is_file("orders.sql")
    assert workbench_pages.wrong_page("powerquery", "notebooks") == (
        "A Power Query file opens on the Scripts page, not here."
    )
    assert workbench_pages.renamed("/p/scripts/orders.pq", "sales") == "/p/scripts/sales.pq"
    listed = project_scope.documents([("scripts/orders.pq", 10, 1.0), ("a.py", 1, 1.0)])
    assert [(d["path"], d["kind"]) for d in listed] == [
        ("a.py", "script"),
        ("scripts/orders.pq", "powerquery"),
    ]


def test_the_scripts_tree_lists_them_in_a_group_of_their_own() -> None:
    group = code_tree.power_query_group(["scripts/b.pq", "a.m", "scripts/x.sql", ".sab/x.pq"])
    assert group is not None and (group["id"], group["name"], group["kind"]) == (
        "powerquery", "Power Query", "powerquery",
    )  # fmt: skip
    assert [f["path"] for f in group["files"]] == ["a.m", "scripts/b.pq"]
    assert code_tree.power_query_group(["a.py"]) is None


def test_names() -> None:
    assert rules.query_name("/home/u/scripts/orders_by_month.pq") == "orders_by_month"
    assert rules.query_name("C:\\work\\Orders by month.M") == "Orders_by_month"
    assert rules.query_name(None) == "Query"
    assert rules.table_name("Sales Orders (2024)") == "Sales_Orders_2024"
    assert len(rules.table_name("a" * 100)) == 64
    assert rules.file_name("Sales Orders") == "Sales_Orders.pq"


def test_the_query_under_the_cursor() -> None:
    compiled = duckpq.compile("section S;\nshared A = 1;\n\nshared B = let\n  x = 2\nin x;\n")
    assert [rules.query_at(compiled, line).name for line in (1, 2, 3, 4, 5, 6, 9)] == [  # type: ignore[union-attr]
        "A", "A", "A", "B", "B", "B", "B",
    ]  # fmt: skip


def test_the_starters_run_as_they_are() -> None:
    empty = rules.starter()
    assert duckpq.run(empty, name="q")["q"].fetchall() == [("North", 120)]
    over = rules.starter("sales orders", ["Order Id", "amount"])
    assert not duckpq.check(over, tables={"sales orders": ["Order Id", "amount"]})
    assert '#"sales orders"' in over and "[Order Id] <> null" in over
    kind = new_files.type_of("powerquery")
    assert (kind.ending, kind.endings, kind.page, kind.kind) == (
        ".pq",
        (".pq", ".m"),
        "scripts",
        "powerquery",
    )
    made = new_files.starter(kind, "orders.pq", {"table": "orders", "columns": ["id"]})
    assert "Source = orders" in made and "Table.FirstN" in made
    importing = new_files.type_of("powerquery_import")
    assert importing.asks == ("name", "folder", "source") and importing.maker == "powerquery_import"


# ===== the sources' mapping =====

SAVED = [
    rules.Connection("Warehouse", "sqlserver", {"server": "SQL01.corp.example,1433", "database": "Sales"}),
    rules.Connection("Warehouse HR", "azuresql", {"server": "sql01.corp.example", "database": "HR"}),
    rules.Connection("Shop", "postgres", {"server": "pg.example", "port": "5432", "database": "shop"}),
    rules.Connection("Flakes", "snowflake", {"account": "acme-xy123", "database": "SALES"}),
    rules.Connection("Bricks", "databricks", {"server": "adb-1.azuredatabricks.net", "http path": "/sql/1"}),
    rules.Connection("CRM", "dataverse", {"address": "https://org.crm.dynamics.com/"}),
    rules.Connection("Ora", "oracle", {"data source": "ora.example:1521/svc"}),
    rules.Connection("Lake", "onelake", {"workspace": "W"}),
]


def source_of(text: str) -> duckpq.Source:
    context = duckpq.Context()
    duckpq.compile(text, context=context)
    return context.sources["m_source_0"]


@pytest.mark.parametrize(
    ("m", "connection", "named"),
    [
        (
            'Sql.Database("sql01.corp.example", "sales"){[Schema = "dbo", Item = "Orders"]}[Data]',
            "Warehouse",
            "[Warehouse].[dbo].[Orders]",
        ),
        (
            'Sql.Database("tcp:SQL01.corp.example", "HR"){[Schema = "dbo", Item = "People"]}[Data]',
            "Warehouse HR",
            "[Warehouse HR].[dbo].[People]",
        ),
        (
            'PostgreSQL.Database("pg.example:5432", "shop"){[Schema = "public", Item = "orders"]}[Data]',
            "Shop",
            "[Shop].[public].[orders]",
        ),
        (
            'Snowflake.Databases("acme-xy123.snowflakecomputing.com", "WH"){[Name = "SALES", Kind = "Database"]}'
            '[Data]{[Name = "PUBLIC", Kind = "Schema"]}[Data]{[Name = "ORDERS", Kind = "Table"]}[Data]',
            "Flakes",
            "[Flakes].[PUBLIC].[ORDERS]",
        ),
        (
            'Databricks.Catalogs("adb-1.azuredatabricks.net", "/sql/1", null){[Name = "main", Kind = "Database"]}'
            '[Data]{[Name = "gold", Kind = "Schema"]}[Data]{[Name = "orders", Kind = "Table"]}[Data]',
            "Bricks",
            "[Bricks].[gold].[orders]",
        ),
        (
            'CommonDataService.Database("org.crm.dynamics.com"){[Schema = "dbo", Item = "account"]}[Data]',
            "CRM",
            "[CRM].[dbo].[account]",
        ),
        (
            'Oracle.Database("ora.example:1521/svc"){[Schema = "HR", Item = "EMPLOYEES"]}[Data]',
            "Ora",
            "[Ora].[HR].[EMPLOYEES]",
        ),
    ],
)
def test_each_database_function_is_matched_to_its_saved_connection(
    m: str, connection: str, named: str
) -> None:
    source = source_of(m)
    found = rules.connection_for(source, SAVED)
    assert found.name == connection
    assert rules.reference(found, source) == named


def test_no_matching_connection_is_said_in_one_sentence_with_add_connection() -> None:
    with pytest.raises(rules.NoConnection) as said:
        rules.connection_for(
            source_of('Sql.Database("other", "Sales"){[Schema = "dbo", Item = "t"]}[Data]'), SAVED
        )
    assert str(said.value) == (
        "No saved connection matches Sql.Database for other and Sales: Add connection (a SQL Server one for "
        "that server and database)."
    )
    assert (said.value.label, said.value.server, said.value.database) == ("SQL Server", "other", "Sales")
    # The same server, another database: not a match (never the nearest one).
    with pytest.raises(rules.NoConnection):
        rules.connection_for(
            source_of('Sql.Database("sql01.corp.example", "Finance"){[Item = "t"]}[Data]'), SAVED
        )
    # A function with no connection kind here.
    with pytest.raises(rules.NoConnection, match=r"OData\.Feed has no connection kind here yet"):
        rules.connection_for(source_of('OData.Feed("https://example.org/odata"){[Name = "t"]}[Data]'), SAVED)


def test_a_source_with_no_table_picked_cannot_be_named() -> None:
    source = source_of('Table.SelectRows(Sql.Database("sql01.corp.example", "Sales"), each true)')
    with pytest.raises(ValueError, match="Pick a table"):
        rules.reference(SAVED[0], source)


# ===== a dataset's queries as one file =====

ORDERS_M = (
    'let\n    Source = Sql.Database(Server, "Sales"),\n'
    '    dbo_Orders = Source{[Schema="dbo",Item="Orders"]}[Data]\nin\n    dbo_Orders'
)
SCHEMA = {
    "model": {
        "tables": [
            {"name": "Orders", "partitions": [{"source": {"type": "m", "expression": ORDERS_M.split("\n")}}]},
            {
                "name": "Order Lines",
                "partitions": [
                    {"source": {"type": "m", "expression": 'let\n  S = #table({"a"}, {{1}})\nin\n  S'}}
                ],
            },
            {
                "name": "Calendar",
                "partitions": [{"source": {"type": "calculated", "expression": "CALENDARAUTO()"}}],
            },
        ],
        "expressions": [
            {
                "name": "Server",
                "kind": "m",
                "expression": '"sql01.corp.example" meta [IsParameterQuery=true, Type="Text"]',
            }
        ],
    }
}
EXPRESSIONS_TMDL = (
    'expression Server = "sql01.corp.example" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
    "\tlineageTag: 1\n\n"
)


def table_tmdl(name: str, m: str) -> str:
    body = "\n".join("\t\t\t\t" + line for line in m.split("\n"))
    quoted = f"'{name}'" if " " in name else name
    return (
        f"table {quoted}\n\tlineageTag: 2\n\n\tcolumn Id\n\t\tdataType: int64\n\n"
        f"\tpartition {quoted} = m\n\t\tmode: import\n\t\tsource =\n{body}\n\n\tannotation PBI_ResultType = Table\n"
    )


def check_dataset(found: rules.DatasetQueries) -> None:
    assert found.parameters[0][0] == "Server" and found.parameters[0][1].startswith(
        '"sql01.corp.example" meta'
    )
    assert [name for name, _ in found.tables] == ["Orders", "Order Lines"]
    assert found.tables[0][1] == ORDERS_M
    text = rules.document(found, "Sales.pbit")
    compiled = duckpq.compile(text)
    assert [x.name for x in compiled.queries] == ["Server", "Orders", "Order Lines"]
    assert compiled.query("Server").value == "sql01.corp.example"
    assert compiled.query("Order Lines").kind == "table" and compiled.query("Orders").depends == ("Server",)
    assert 'shared #"Order Lines" = let' in text and "imported from Sales.pbit" in text


def test_a_pbits_model_schema_is_read(tmp_path: Path) -> None:
    found = rules.from_schema(json.dumps(SCHEMA), "Sales")
    check_dataset(found)
    assert found.skipped == (("Calendar", "a calculated table (DAX)"),)
    assert "// Not imported: Calendar (a calculated table (DAX))." in rules.document(found)
    file = tmp_path / "Sales.pbit"
    with zipfile.ZipFile(file, "w") as archive:
        archive.writestr("DataModelSchema", json.dumps(SCHEMA).encode("utf-16-le"))
    check_dataset(files.read(str(file)))


def test_a_pbips_tmdl_is_read(tmp_path: Path) -> None:
    model = tmp_path / "Sales.SemanticModel" / "definition"
    (model / "tables").mkdir(parents=True)
    (tmp_path / "Sales.pbip").write_text("{}", encoding="utf-8")
    (model / "expressions.tmdl").write_text(EXPRESSIONS_TMDL, encoding="utf-8")
    (model / "tables" / "Orders.tmdl").write_text(table_tmdl("Orders", ORDERS_M), encoding="utf-8")
    (model / "tables" / "Order Lines.tmdl").write_text(
        table_tmdl("Order Lines", 'let\n  S = #table({"a"}, {{1}})\nin\n  S'), encoding="utf-8"
    )
    found = files.read(str(tmp_path / "Sales.pbip"))
    assert [name for name, _ in found.tables] == ["Order Lines", "Orders"]
    by_name = dict(found.tables)
    assert by_name["Orders"] == ORDERS_M
    assert dict(found.parameters)["Server"].startswith('"sql01.corp.example" meta')
    assert duckpq.compile(rules.document(found)).query("Order Lines").kind == "table"
    # A project with a model.bim instead of TMDL.
    other = tmp_path / "Other.SemanticModel"
    other.mkdir()
    (other / "model.bim").write_text(json.dumps(SCHEMA), encoding="utf-8")
    check_dataset(files.read(str(other)))


def test_a_pbix_through_pbixrays_frames() -> None:
    class Frame:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def to_dict(self, how: str) -> list[dict[str, Any]]:
            return self.rows

    class Model:
        power_query = Frame(
            [
                {"TableName": "Orders", "Expression": ORDERS_M},
                {"TableName": "Order Lines", "Expression": 'let\n  S = #table({"a"}, {{1}})\nin\n  S'},
            ]
        )
        m_parameters = Frame(
            [{"ParameterName": "Server", "Expression": '"sql01.corp.example" meta [IsParameterQuery=true]'}]
        )

    check_dataset(files.from_pbixray(Model(), "Sales"))


def test_a_file_that_is_no_dataset_says_so(tmp_path: Path) -> None:
    bad = tmp_path / "x.pbit"
    bad.write_text("not a zip")
    with pytest.raises(rules.ImportError_, match="not a Power BI file"):
        files.read(str(bad))
    with pytest.raises(FileNotFoundError):
        files.read(str(tmp_path / "nope.pbix"))
    with pytest.raises(rules.ImportError_, match=r"a \.pbix, a \.pbit or a \.pbip"):
        (tmp_path / "x.txt").write_text("x")
        files.read(str(tmp_path / "x.txt"))
    with pytest.raises(rules.ImportError_, match="no Power Query to import"):
        rules.document(rules.DatasetQueries("Empty"))


def test_a_tables_power_query_is_kept_with_the_project() -> None:
    origin = Origin(
        "query", sql="SELECT 1", path="/p/sales/scripts/shop.pq", m="let a = 1 in a", m_query="Totals"
    )
    source = sab_files.source_of(origin, "/p/sales", "/p/sales", None, None, True, False)
    assert source.to_json() == {
        "kind": "query",
        "sql": "SELECT 1",
        "powerquery": {"path": "scripts/shop.pq", "query": "Totals"},
    }
    again = sab_files.read_source(source.to_json())
    assert again.extra["powerquery"] == {"path": "scripts/shop.pq", "query": "Totals"}


# ===== the server =====


def shop_connection(client: TestClient, tmp_path: Path) -> None:
    """A saved connection that says it is a PostgreSQL database on pg.example (a made-up SQLite file)."""
    path = tmp_path / "shop.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE regions (region TEXT, code INTEGER)")
        made.executemany("INSERT INTO regions VALUES (?, ?)", [("North", 1), ("South", 2)])
    body = {
        "name": "Shop DB",
        "kind": "sql",
        "template": "postgres",
        "dialect": "sqlite",
        "code": (
            'import sqlite3\nfrom pathlib import Path\n\nserver = "pg.example"\ndatabase = "shop"\n'
            f'path = Path(r"{path}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
        "catalog": {"language": "sql", "command": CATALOG},
    }
    ok(client.post("/connections", json=body, headers=AUTH))


SHOP = """section Shop;

shared Least = 6 meta [IsParameterQuery = true];

shared People = Table.PromoteHeaders(Csv.Document(File.Contents("people.csv")));

shared Regions = PostgreSQL.Database("pg.example", "shop"){[Schema = "main", Item = "regions"]}[Data];

shared Totals = let
    Kept = Table.SelectRows(orders, each [amount] >= Least),
    Joined = Table.NestedJoin(Kept, {"customer"}, People, {"name"}, "p", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "p", {"region"}),
    More = Table.NestedJoin(Expanded, {"region"}, Regions, {"region"}, "r", JoinKind.LeftOuter),
    Coded = Table.ExpandTableColumn(More, "r", {"code"}),
    Grouped = Table.Group(Coded, {"region", "code"}, {{"total", each List.Sum([amount]), type number}}),
    Sorted = Table.Sort(Grouped, {"region"})
in
    Sorted;

shared Counted = Value.NativeQuery(PostgreSQL.Database("pg.example", "shop"), "SELECT count(*) AS n FROM regions");
"""


def rows_of(client: TestClient, grid: str) -> list[list[Any]]:
    answered = ok(client.get(f"/grids/{grid}/rows?start=0&end=50", headers=AUTH))
    return [list(r) for r in answered["rows"]]


def test_run_file_builds_every_table_from_its_original_sources(client: TestClient, tmp_path: Path) -> None:
    push(client, "orders", ORDERS)
    shop_connection(client, tmp_path)
    (tmp_path / "people.csv").write_text("name,region\nann,North\nbob,South\n", encoding="utf-8")
    file = tmp_path / "shop.pq"
    file.write_text(SHOP, encoding="utf-8")
    assert ok(client.post("/scripts/pq/problems", json={"path": str(file)}, headers=AGENT))["problems"] == []
    ran = ok(client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH))
    built = {t["table"]: t for t in ran["tables"]}
    assert list(built) == ["People", "Regions", "Totals", "Counted"]
    assert (built["People"]["rows"], built["Regions"]["rows"], built["Totals"]["rows"]) == (2, 2, 2)
    assert (ran["table"], ran["grid"]) == ("Counted", built["Counted"]["grid"])  # the last one comes forward
    assert rows_of(client, built["Totals"]["grid"]) == [["North", 1, 10.0], ["South", 2, 20.0]]
    assert rows_of(client, built["Counted"]["grid"]) == [[2]]
    # The table shows its M, and the SQL composed is beside it.
    info = ok(client.get(f"/grids/{built['Totals']['grid']}", headers=AUTH))
    assert info["query_language"] == "powerquery" and info["query"].startswith("shared Totals = let")
    assert "[Shop DB].[main].[regions]" in info["query_sql"]
    # Run again replaces each table in its own grid.
    again = ok(client.post("/scripts/pq/run", json={"path": str(file)}, headers=AGENT))
    assert [t["grid"] for t in again["tables"]] == [t["grid"] for t in ran["tables"]]


def test_a_per_row_try_otherwise_runs_to_a_table(client: TestClient, tmp_path: Path) -> None:
    """duckpq 1.1.0: a reading that is no number (a word, the app's reader's empty text for a blank) takes the
    otherwise value; the others keep their own."""
    (tmp_path / "readings.csv").write_text("sensor,value\na,12\nb,oops\nc,\nd,2.5\n", encoding="utf-8")
    file = tmp_path / "readings.pq"
    file.write_text(
        'let\n    Read = Table.PromoteHeaders(Csv.Document(File.Contents("readings.csv"))),\n'
        '    Typed = Table.TransformColumnTypes(Read, {{"value", type text}}),\n'
        '    Clean = Table.AddColumn(Typed, "number", each try Number.From([value]) otherwise -1),\n'
        '    Doubled = Table.AddColumn(Clean, "twice", each try Number.From([value]) * 2 otherwise 0)\n'
        "in\n    Doubled\n",
        encoding="utf-8",
    )
    assert ok(client.post("/scripts/pq/problems", json={"path": str(file)}, headers=AGENT))["problems"] == []
    ran = ok(client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH))
    assert ran["table"] == "readings"
    assert rows_of(client, ran["grid"]) == [
        ["a", "12", 12.0, 24.0],
        ["b", "oops", -1.0, 0.0],
        ["c", "", -1.0, 0.0],
        ["d", "2.5", 2.5, 5.0],
    ]


def test_one_query_by_its_line_or_its_name_and_the_unsaved_text_wins(
    client: TestClient, tmp_path: Path
) -> None:
    push(client, "orders", ORDERS)
    text = "section S;\nshared Big = Table.SelectRows(orders, each [amount] > 6);\n\nshared Small = let\n  S = orders\nin\n  Table.SelectRows(S, each [amount] <= 6);\n"
    at_line = ok(client.post("/scripts/pq/run", json={"text": text, "line": 5}, headers=AUTH))
    assert [(t["table"], t["rows"], t["line"], t["end_line"]) for t in at_line["tables"]] == [
        ("Small", 1, 4, 7)
    ]
    by_name = ok(client.post("/scripts/pq/run", json={"text": text, "query": "Big"}, headers=AUTH))
    assert (by_name["table"], by_name["rows"]) == ("Big", 2)
    # A plain let ... in file: one query, named after the file.
    file = tmp_path / "cheap orders.pq"
    file.write_text("let S = orders in Table.SelectRows(S, each [amount] < 0)", encoding="utf-8")
    plain = ok(
        client.post(
            "/scripts/pq/run",
            json={"path": str(file), "text": "let S = orders in Table.SelectRows(S, each [amount] < 15)"},
            headers=AUTH,
        )
    )
    assert (plain["table"], plain["rows"]) == ("cheap_orders", 2)
    # A parameter is not a table.
    value = client.post(
        "/scripts/pq/run", json={"text": "section S;\nshared P = 1;", "query": "P"}, headers=AUTH
    )
    assert value.status_code == 400 and "not a table" in value.json()["error"]


def test_problems_before_a_run_and_a_failure_names_its_line(client: TestClient) -> None:
    push(client, "orders", ORDERS)
    text = (
        "section S;\n"
        "shared A = Table.SelectRows(orders, each [nope] > 1);\n"
        "shared B = Table.Transpose(orders);\n"
        'shared C = Sql.Database("nowhere", "db"){[Schema = "dbo", Item = "t"]}[Data];\n'
        "shared D = Table.FirstN(orders, 1);\n"
        "shared E = let x = in x;\n"
    )
    broken = ok(client.post("/scripts/pq/problems", json={"text": text}, headers=AGENT))
    assert [(p["line"], p["column"]) for p in broken["problems"]] == [(6, 20)]  # the text does not parse
    text = text.replace("shared E = let x = in x;\n", "")
    found = ok(client.post("/scripts/pq/problems", json={"text": text}, headers=AGENT))
    assert [(p["query"], p["line"], p["name"]) for p in found["problems"]] == [
        ("A", 2, "nope"), ("B", 3, "Table.Transpose"), ("C", 4, None),
    ]  # fmt: skip
    assert (
        "No saved connection matches Sql.Database for nowhere and db: Add connection"
        in found["problems"][2]["message"]
    )
    assert [(x["name"], x["kind"]) for x in found["queries"]][-1] == ("D", "table")
    # Run file refuses with the first problem's line; nothing is built.
    refused = client.post("/scripts/pq/run", json={"text": text}, headers=AUTH)
    body = refused.json()
    assert (refused.status_code, body["line"], body["name"], body["where"]) == (400, 2, "nope", "line 2")
    assert ok(client.get("/datasets", headers=AUTH))["datasets"][0]["name"] == "orders"
    # The good query still runs alone; the unmatched source says Add connection.
    assert ok(client.post("/scripts/pq/run", json={"text": text, "query": "D"}, headers=AUTH))["rows"] == 1
    none = client.post("/scripts/pq/run", json={"text": text, "query": "C"}, headers=AUTH).json()
    assert none["add_connection"] is True and none["line"] == 4
    # What only DuckDB can say (a cast that fails on a row) names the query's line.
    cast = 'section S;\n\nshared Bad = Table.TransformColumnTypes(orders, {{"customer", Int64.Type}});\n'
    failed = client.post("/scripts/pq/run", json={"text": cast}, headers=AUTH).json()
    assert failed["line"] == 3 and failed["error"].startswith("Bad: ") and "ann" in failed["details"]


def test_the_composed_sql_and_its_sources(client: TestClient, tmp_path: Path) -> None:
    push(client, "orders", ORDERS)
    (tmp_path / "people.csv").write_text("name,region\nann,North\n", encoding="utf-8")
    text = (
        "section S;\n"
        'shared Big = Table.SelectColumns(Table.SelectRows(orders, each [amount] > 6), {"order_id"});\n'
        f'shared People = Table.PromoteHeaders(Csv.Document(File.Contents("{tmp_path / "people.csv"}")));\n'
    )
    said = ok(client.post("/scripts/pq/sql", json={"text": text}, headers=AGENT))
    big, people = said["queries"]
    assert big["sql"] == 'SELECT "order_id" FROM "orders" WHERE (("amount" > 6))' and big["columns"] == [
        "order_id"
    ]
    assert people["sql"] == 'SELECT * FROM "m_source_0"' and people["sources"][0]["kind"] == "file"
    one = ok(client.post("/scripts/pq/sql", json={"text": text, "line": 2}, headers=AGENT))
    assert [x["query"] for x in one["queries"]] == ["Big"]
    # The cursor in a parameter: every table's SQL, not a refusal.
    with_value = (
        "section S;\nshared Least = 6;\nshared Big = Table.SelectRows(orders, each [amount] > Least);\n"
    )
    every = ok(client.post("/scripts/pq/sql", json={"text": with_value, "line": 2}, headers=AGENT))
    assert [x["query"] for x in every["queries"]] == ["Big"]
    assert ok(client.get("/datasets", headers=AUTH))["datasets"][0]["name"] == "orders"  # nothing was built


def test_a_variable_is_bound_never_written_into_the_sql(client: TestClient) -> None:
    push(client, "orders", ORDERS)
    ok(client.put("/variables", json={"name": "WHO", "value": "ann"}, headers=AUTH))
    text = 'Table.SelectRows(orders, each [customer] = "${WHO}")'
    said = ok(client.post("/scripts/pq/sql", json={"text": text}, headers=AUTH))
    assert "${WHO}" in said["queries"][0]["sql"] and "'ann'" not in said["queries"][0]["sql"]
    assert ok(client.post("/scripts/pq/run", json={"text": text}, headers=AUTH))["rows"] == 2


def test_edit_in_scripts_opens_the_file_the_table_ran_from(client: TestClient, tmp_path: Path) -> None:
    push(client, "orders", ORDERS)
    file = tmp_path / "big.pq"
    file.write_text("let S = orders in Table.SelectRows(S, each [amount] > 6)", encoding="utf-8")
    ok(client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH))
    found = ok(client.post("/scripts/sql/for-table", json={"table": "big"}, headers=AGENT))
    assert (found["path"], found["made"], found["query"]) == (str(file), False, "big")
    # Run from text alone (the agent's): its M written once as the table's own file.
    ok(
        client.post(
            "/scripts/pq/run",
            json={"text": "section S;\nshared Few = Table.FirstN(orders, 1);"},
            headers=AGENT,
        )
    )
    made = ok(client.post("/scripts/sql/for-table", json={"table": "Few"}, headers=AUTH))
    assert made["made"] is True and Path(made["path"]).name == "Few.pq"
    assert Path(made["path"]).read_text() == "shared Few = Table.FirstN(orders, 1);\n"


def test_new_file_makes_a_power_query_file_and_imports_a_dataset(client: TestClient, tmp_path: Path) -> None:
    push(client, "orders", ORDERS)
    offered = {t["id"]: t for t in ok(client.get("/scripts/files/new", headers=AUTH))["types"]}
    assert offered["powerquery"]["label"] == "Power Query" and offered["powerquery"]["kind"] == "powerquery"
    assert offered["powerquery_import"]["asks"] == ["name", "folder", "source"]
    made = ok(
        client.post(
            "/scripts/files/new",
            json={"type": "powerquery", "name": "first rows", "folder": str(tmp_path)},
            headers=AUTH,
        )
    )
    assert (Path(made["path"]).name, made["kind"], made["page"]) == ("first rows.pq", "powerquery", "scripts")
    assert (
        ok(client.post("/scripts/pq/run", json={"path": made["path"]}, headers=AUTH))["table"] == "first_rows"
    )
    # Import Power BI queries…: a made-up template's queries as one file.
    template = tmp_path / "Sales.pbit"
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("DataModelSchema", json.dumps(SCHEMA).encode("utf-16-le"))
    body = {"type": "powerquery_import", "name": "sales", "folder": str(tmp_path), "source": str(template)}
    where = ok(client.post("/scripts/files/new", json=body | {"check": True}, headers=AUTH))
    assert where["made"] is False and not Path(where["path"]).exists()
    imported = ok(client.post("/scripts/files/new", json=body, headers=AGENT))
    assert (imported["queries"], imported["parameters"], imported["skipped"]) == (2, 1, ["Calendar"])
    text = Path(imported["path"]).read_text(encoding="utf-8")
    assert "shared Orders = let" in text and Path(imported["path"]).name == "sales.pq"
    # Its queries run against their sources: the literal one builds, the database one asks for its connection.
    lines = ok(
        client.post("/scripts/pq/run", json={"path": imported["path"], "query": "Order Lines"}, headers=AUTH)
    )
    assert lines["table"] == "Order_Lines" and lines["rows"] == 1
    missing = client.post("/scripts/pq/run", json={"path": imported["path"], "query": "Orders"}, headers=AUTH)
    assert missing.status_code == 400 and missing.json()["add_connection"] is True
    # No source picked, a taken name, a file that is no dataset: each one sentence.
    assert (
        client.post(
            "/scripts/files/new", json=body | {"name": "other", "source": ""}, headers=AUTH
        ).status_code
        == 403
    )
    assert client.post("/scripts/files/new", json=body, headers=AUTH).status_code == 409
    wrong = client.post("/scripts/files/new", json=body | {"name": "x", "source": made["path"]}, headers=AUTH)
    assert wrong.status_code == 403 and "a .pbix, a .pbit or a .pbip" in wrong.json()["error"]


def test_an_export_carries_the_library_and_runs_with_no_app(client: TestClient, tmp_path: Path) -> None:
    """Portability: the exported folder holds the .pq, duckpq.py as it is and run.py; run in a bare Python (the
    app's packages cannot be imported there), every table is written as Parquet."""
    import subprocess
    import sys

    import duckdb

    (tmp_path / "orders.csv").write_text("id,amount\n1,5\n2,50\n3,500\n", encoding="utf-8")
    file = tmp_path / "big orders.pq"
    file.write_text(
        "section Shop;\n"
        f'shared Orders = Table.PromoteHeaders(Csv.Document(File.Contents("{tmp_path / "orders.csv"}")));\n'
        "shared Big = Table.SelectRows(Orders, each [amount] > 10);\n"
        'shared Elsewhere = Sql.Database("made-up-sql.example", "Sales"){[Schema = "dbo", Item = "t"]}[Data];\n',
        encoding="utf-8",
    )
    made = ok(client.post("/scripts/pq/export", json={"path": str(file)}, headers=AGENT))
    folder = Path(made["folder"])
    assert folder == tmp_path / "big_orders_export"
    assert made["files"] == ["README.md", "big orders.pq", "duckpq.py", "requirements.txt", "run.py"]
    assert (folder / "duckpq.py").read_text(encoding="utf-8") == Path(duckpq.__file__).read_text(
        encoding="utf-8"
    )
    run = (folder / "run.py").read_text(encoding="utf-8")
    assert "source.function == 'Sql.Database' and source.arguments == ('made-up-sql.example', 'Sales')" in run
    assert "answer for it in `run.py`'s `resolver`" in (folder / "README.md").read_text(encoding="utf-8")
    assert "swissarmybench" not in run
    # A second export writes nothing (the same bytes).
    assert ok(client.post("/scripts/pq/export", json={"path": str(file)}, headers=AUTH))["written"] == []
    # With the database's query taken out, it runs as it is in a bare Python.
    text = file.read_text(encoding="utf-8")
    (folder / "big orders.pq").write_text(text[: text.index("shared Elsewhere")], encoding="utf-8")
    block = "import sys\nsys.modules['swissarmybench'] = None\nimport runpy\nrunpy.run_path('run.py', run_name='__main__')\n"
    done = subprocess.run(  # noqa: S603 (this Python, the exported script)
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.')\n" + block],
        cwd=folder, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    # A connection of its own: the app's process keeps DuckDB's default one to itself.
    read = duckdb.connect().sql(f"SELECT id FROM '{folder / 'out' / 'Big.parquet'}' ORDER BY id")
    assert read.fetchall() == [
        (2,),
        (3,),
    ]


def test_a_project_reads_a_power_querys_table_again_by_running_its_query(
    client: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "made_up_shop"
    ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
    (folder / "people.csv").write_text("name,region\nann,North\nbob,South\n", encoding="utf-8")
    scripts = folder / "scripts"
    scripts.mkdir(exist_ok=True)
    file = scripts / "shop.pq"
    file.write_text(
        "section Shop;\n"
        f'shared People = Table.PromoteHeaders(Csv.Document(File.Contents("{folder / "people.csv"}")));\n'
        'shared North = Table.SelectRows(People, each [region] = "North");\n',
        encoding="utf-8",
    )
    ran = ok(client.post("/scripts/pq/run", json={"path": str(file)}, headers=AUTH))
    assert [t["table"] for t in ran["tables"]] == ["People", "North"]
    ok(client.post("/project/save", json={}, headers=AUTH))
    kept = json.loads((folder / ".sab" / "project.json").read_text(encoding="utf-8"))
    sources = {t["name"]: t["source"] for t in kept["tables"]}
    assert sources["North"]["powerquery"] == {"path": "scripts/shop.pq", "query": "North"}
    assert "sql" in sources["North"] and sources["North"]["kind"] == "query"
    ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
    assert ok(client.get("/datasets", headers=AUTH))["datasets"] == []
    # The file changed while the project was closed: opening it runs the query as it is now.
    (folder / "people.csv").write_text("name,region\nann,North\ncy,North\nbob,South\n", encoding="utf-8")
    ok(client.post("/project/open", json={"path": str(folder)}, headers=AUTH))
    back = {d["name"]: d for d in ok(client.get("/datasets", headers=AUTH))["datasets"]}
    assert set(back) == {"People", "North"} and back["North"]["rows"] == 2
    ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
