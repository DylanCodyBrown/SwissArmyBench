"""Export to Power BI… (domain/powerbi_export.py, domain/power_query.py, services/powerbi_export.py): the
model as a Power BI Project. Made-up data only (examples/sample_store.py, a made-up warehouse)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from examples.sample_store import TRUE_RELATIONSHIPS, make_store
from starlette.testclient import TestClient

from swissarmybench.domain import power_query as pq
from swissarmybench.domain import powerbi_export as rules
from swissarmybench.domain.relationships import Relationship
from swissarmybench.domain.table_cells import Origin
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

SCHEMAS = Path(__file__).parent / "golden" / "powerbi_schemas"
SECRET = "made-up-Secret-9f3k2"  # never in a written file
TABLES = ("regions", "stores", "customers", "orders", "calendar")


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


# ===== types =====


@pytest.mark.parametrize(
    ("duckdb", "power_bi", "said"),
    [
        ("BIGINT", "int64", False),
        ("INTEGER", "int64", False),
        ("DOUBLE", "double", False),
        ("DECIMAL(18,2)", "decimal", False),
        ("VARCHAR", "string", False),
        ("DATE", "dateTime", False),
        ("TIMESTAMP WITH TIME ZONE", "dateTime", False),
        ("BOOLEAN", "boolean", False),
        ("INTEGER[]", "string", True),
        ("STRUCT(a INTEGER)", "string", True),
        ("BLOB", "string", True),
        ("HUGEINT", "string", True),
    ],
)
def test_duckdb_types_map_to_power_bis(duckdb: str, power_bi: str, said: bool) -> None:
    assert rules.data_type(duckdb) == (power_bi, said)


# ===== relationships =====


def rel(a: str, ac: str, b: str, bc: str, **more: Any) -> Relationship:
    return Relationship(a, (ac,), b, (bc,), **more)


def test_one_active_path_between_two_tables_the_strongest_stays_active() -> None:
    columns = {
        "orders": {"order_date": "dateTime", "ship_date": "dateTime", "customer_id": "int64"},
        "calendar": {"date_key": "dateTime"},
        "customers": {"cust_key": "int64"},
    }
    planned = rules.plan_relationships(
        [
            rel("orders", "ship_date", "calendar", "date_key", evidence="91% of values found"),
            rel("orders", "order_date", "calendar", "date_key", evidence="99% of values found"),
            rel("orders", "customer_id", "customers", "cust_key"),
        ],
        columns,
    )
    by = {p.relationship.from_columns[0]: p for p in planned}
    assert by["order_date"].active and not by["ship_date"].active
    assert "one active path" in by["ship_date"].note
    assert by["customer_id"].active


def test_a_cycle_through_three_tables_leaves_its_weakest_inactive() -> None:
    columns = {
        "a": {"b_id": "int64", "c_id": "int64"},
        "b": {"id": "int64", "c_id": "int64"},
        "c": {"id": "int64"},
    }
    planned = rules.plan_relationships(
        [
            rel("a", "b_id", "b", "id", evidence="100%"),
            rel("b", "c_id", "c", "id", evidence="100%"),
            rel("a", "c_id", "c", "id", evidence="50%"),
        ],
        columns,
    )
    assert [p.active for p in planned] == [True, True, False]


def test_types_that_differ_and_two_column_joins_are_left_out_and_said() -> None:
    columns = {"customers": {"home_store": "string"}, "stores": {"store_id": "int64"}, "x": {"a": "int64"}}
    planned = rules.plan_relationships(
        [
            rel("customers", "home_store", "stores", "store_id"),
            Relationship("x", ("a", "a"), "stores", ("store_id", "store_id")),
            rel("customers", "home_store", "elsewhere", "id"),
        ],
        columns,
    )
    assert len(planned) == 2  # a table not going: not listed at all
    assert "types differ (string and int64)" in planned[0].left_out
    assert "one column each side" in planned[1].left_out
    assert rules.relationships_tmdl(planned) is None


def test_relationship_text_cardinality_and_inactive() -> None:
    planned = [
        rules.Planned(rel("orders", "customer_id", "customers", "cust_key")),
        rules.Planned(
            rel("customers", "cust_key", "orders", "customer_id", kind="one-to-many"), active=False
        ),
        rules.Planned(rel("a", "x", "b", "y", kind="one-to-one")),
        rules.Planned(rel("a", "x", "c", "y", kind="many-to-many")),
    ]
    text = (rules.relationships_tmdl(planned) or b"").decode()
    blocks = text.split("\r\n\r\n")
    assert "fromColumn: orders.customer_id\r\n\ttoColumn: customers.cust_key" in blocks[0]
    assert "isActive: false" in blocks[1] and "fromColumn: orders.customer_id" in blocks[1]
    assert "fromCardinality: one" in blocks[2]
    assert "toCardinality: many" in blocks[3]


# ===== Power Query =====

M_CASES: dict[str, tuple[pq.MSource, str]] = {
    "sqlserver": (
        pq.MSource(
            "sqlserver", {"server": "sql.example.test", "database": "Sales"}, "Sales", "dbo", "orders"
        ),
        'let\n    Source = Sql.Database("sql.example.test", "Sales"),\n'
        '    Navigation = Source{[Schema="dbo",Item="orders"]}[Data]\nin\n    Navigation',
    ),
    "postgres": (
        pq.MSource(
            "postgres", {"server": "${PG_HOST}", "port": "5432", "database": "shop"}, "", "public", "orders"
        ),
        'let\n    Source = PostgreSQL.Database(#"PG_HOST" & ":5432", "shop"),\n'
        '    Navigation = Source{[Schema="public",Item="orders"]}[Data]\nin\n    Navigation',
    ),
    "mysql": (
        pq.MSource(
            "mysql", {"server": "db.example.test", "port": "3306", "database": "shop"}, "", "", "orders"
        ),
        'let\n    Source = MySQL.Database("db.example.test:3306", "shop"),\n'
        '    Navigation = Source{[Schema="shop",Item="orders"]}[Data]\nin\n    Navigation',
    ),
    "snowflake": (
        pq.MSource(
            "snowflake", {"account": "xy12345", "warehouse": "WH", "database": "SHOP"}, "", "PUBLIC", "ORDERS"
        ),
        'let\n    Source = Snowflake.Databases("xy12345.snowflakecomputing.com", "WH"),\n'
        '    Database = Source{[Name="SHOP",Kind="Database"]}[Data],\n'
        '    Schema = Database{[Name="PUBLIC",Kind="Schema"]}[Data],\n'
        '    Navigation = Schema{[Name="ORDERS",Kind="Table"]}[Data]\nin\n    Navigation',
    ),
    "databricks": (
        pq.MSource(
            "databricks", {"server": "adb.example.test", "http path": "/sql/1.0/x"}, "main", "sales", "orders"
        ),
        'let\n    Source = Databricks.Catalogs("adb.example.test", "/sql/1.0/x", null),\n'
        '    Catalog = Source{[Name="main",Kind="Database"]}[Data],\n'
        '    Schema = Catalog{[Name="sales",Kind="Schema"]}[Data],\n'
        '    Navigation = Schema{[Name="orders",Kind="Table"]}[Data]\nin\n    Navigation',
    ),
    "oracle": (
        pq.MSource("oracle", {"data source": "ora.example.test:1521/svc"}, "", "SALES", "ORDERS"),
        'let\n    Source = Oracle.Database("ora.example.test:1521/svc"),\n'
        '    Navigation = Source{[Schema="SALES",Item="ORDERS"]}[Data]\nin\n    Navigation',
    ),
    "dataverse": (
        pq.MSource("dataverse", {"address": "https://contoso-made-up.crm.dynamics.com"}, "", "", "account"),
        'let\n    Source = CommonDataService.Database("contoso-made-up.crm.dynamics.com"),\n'
        '    Navigation = Source{[Schema="dbo",Item="account"]}[Data]\nin\n    Navigation',
    ),
    "sharepoint": (
        pq.MSource("sharepoint", {"site_url": "https://made-up.sharepoint.com/sites/s"}, table="Orders"),
        'let\n    Source = SharePoint.Tables("https://made-up.sharepoint.com/sites/s", [ApiVersion = 15]),\n'
        '    Navigation = Source{[Title="Orders"]}[Items]\nin\n    Navigation',
    ),
    "csv": (
        pq.MSource("csv", path="C:\\data\\orders.csv"),
        'let\n    Source = Csv.Document(File.Contents("C:\\data\\orders.csv"), [Delimiter=",", Encod'
        "ing=65001, "
        "QuoteStyle=QuoteStyle.Csv]),\n    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalar"
        "s=true]),\n"
        '    Typed = Table.TransformColumnTypes(Promoted, {{"id", Int64.Type}, {"day", type datetim'
        "e}})\nin\n    Typed",
    ),
    "excel": (
        pq.MSource("excel", path="${DATA}/book.xlsx", sheet="Orders"),
        'let\n    Source = Excel.Workbook(File.Contents(#"DATA" & "/book.xlsx"), null, true),\n'
        '    Sheet = Source{[Item="Orders",Kind="Sheet"]}[Data],\n'
        "    Promoted = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true]),\n"
        '    Typed = Table.TransformColumnTypes(Promoted, {{"id", Int64.Type}, {"day", type datetim'
        "e}})\nin\n    Typed",
    ),
    "parquet": (
        pq.MSource("parquet", path="/data/orders.parquet"),
        'let\n    Source = Parquet.Document(File.Contents("/data/orders.parquet"))\nin\n    Source',
    ),
    "datalake": (
        pq.MSource("datalake", {"account": "madeup", "container": "lake"}, path="sales/orders.parquet"),
        'let\n    Source = AzureStorage.DataLake("https://madeup.dfs.core.windows.net/lake/sales/ord'
        'ers.parquet", '
        "[HierarchicalNavigation=false]),\n    Navigation = Parquet.Document(Source{0}[Content])\nin"
        "\n    Navigation",
    ),
    "delta": (
        pq.MSource("delta", {"root": "abfss://lake@madeup.dfs.core.windows.net/gold"}, path="orders"),
        'let\n    Source = AzureStorage.DataLake("https://madeup.dfs.core.windows.net/lake/gold/orders", '
        "[HierarchicalNavigation=false]),\n    Navigation = DeltaLake.Table(Source)\nin\n    Navigation",
    ),
    "onelake": (
        pq.MSource("onelake", {"workspace": "Sales", "item": "Shop.Lakehouse"}, path="Tables/orders"),
        'let\n    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/Sales/Shop.Lakehouse/'
        'Tables/orders", [HierarchicalNavigation=false]),\n    Navigation = DeltaLake.Table(Source)'
        "\nin\n    Navigation",
    ),
}


@pytest.mark.parametrize("kind", sorted(M_CASES))
def test_each_kinds_power_query(kind: str) -> None:
    source, expected = M_CASES[kind]
    made = pq.m_for(source, [("id", "int64"), ("day", "dateTime")])
    assert made.text == expected


@pytest.mark.parametrize("kind", sorted(M_CASES))
def test_each_kinds_power_query_reads_back(kind: str) -> None:
    source, _ = M_CASES[kind]
    made = pq.m_for(source, [("id", "int64")])
    read = pq.read_source(made.text, {n: "" for n in made.parameters})
    assert read.source is not None, read.why
    assert read.source.kind == source.kind
    assert (read.source.table or read.source.path) in (source.table, source.path) or source.kind in (
        "datalake",
        "delta",
        "onelake",
    )


def test_a_variable_is_a_parameter_and_a_native_query_rides_the_query_option() -> None:
    source = pq.MSource(
        "sqlserver", {"server": "${SQL_SERVER}", "database": "db_${ENV}"}, query="SELECT 1 AS x"
    )
    made = pq.m_for(source)
    assert made.parameters == ("SQL_SERVER", "ENV")
    assert 'Sql.Database(#"SQL_SERVER", "db_" & #"ENV", [Query="SELECT 1 AS x"])' in made.text
    escaped = pq.m_for(pq.MSource("parquet", path="$${NOT_A_VARIABLE}.parquet"))
    assert escaped.parameters == () and '"${NOT_A_VARIABLE}.parquet"' in escaped.text


def test_a_source_with_no_power_query_is_said() -> None:
    with pytest.raises(pq.PowerQueryError, match="no reader"):
        pq.m_for(pq.MSource("bigquery"))
    with pytest.raises(pq.PowerQueryError, match="names no server"):
        pq.m_for(pq.MSource("sqlserver", {"database": "x"}, table="t"))


VIEW = 'SELECT "region", count(*) AS "orders"\nFROM orders\nWHERE "status_code" <> 5\nGROUP BY "region"'


def test_steps_transpile_for_sql_server_and_postgresql() -> None:
    tsql = pq.native_steps(VIEW, "orders", "sqlserver", "dbo", "orders")
    assert tsql.sql is not None and "[dbo].[orders] AS orders" in tsql.sql and "GROUP BY" in tsql.sql
    assert "ALL" not in tsql.sql.split("GROUP BY")[1]  # DuckDB's GROUP BY ALL spelled out
    pg = pq.native_steps(
        'SELECT * FROM orders ORDER BY "day" DESC LIMIT 10', "orders", "postgres", "public", "orders"
    )
    assert pg.sql is not None and '"public"."orders" AS orders' in pg.sql and "LIMIT 10" in pg.sql
    around = pq.native_steps(
        "SELECT * FROM orders WHERE x > 1", "orders", "sqlserver", "", "", "SELECT x FROM t"
    )
    assert around.sql is not None and "FROM t\n) AS orders" in around.sql


def test_a_function_sqlglot_cannot_carry_is_said() -> None:
    gone = pq.native_steps("SELECT made_up_fn(a) FROM orders", "orders", "sqlserver", "dbo", "orders")
    assert gone.sql is None and "made_up_fn" in gone.why
    grouped = pq.native_steps(
        "SELECT a, count(*) FROM orders GROUP BY ALL", "orders", "sqlserver", "dbo", "orders"
    )
    assert grouped.sql is None and "GROUP BY ALL" in grouped.why
    excluded = pq.native_steps("SELECT * EXCLUDE (a) FROM orders", "orders", "postgres", "public", "orders")
    assert excluded.sql is None and "EXCLUDE" in excluded.why
    file = pq.native_steps("SELECT * FROM orders", "orders", "csv", "", "orders")
    assert file.sql is None


# ===== the files =====


def table(name: str = "orders") -> rules.ExportTable:
    m = pq.m_for(pq.MSource("parquet", path="${DATA}/o.parquet"))
    return rules.ExportTable(
        name,
        (("order_id", "int64"), ("total", "double"), ("Net Price", "decimal")),
        m,
        frozenset({"order_id"}),
    )


def test_a_table_file_is_as_power_bi_desktop_writes_it() -> None:
    text = rules.table_tmdl(
        table(), [rules.Measure("orders", "Total Sales", "SUM(orders[total])", "#,##0")]
    ).decode()
    lines = text.split("\r\n")
    assert lines[0] == "table orders" and lines[1].startswith("\tlineageTag: ")
    assert "\tmeasure 'Total Sales' = SUM(orders[total])" in lines
    assert "\tcolumn 'Net Price'" in lines and "\t\tsourceColumn: Net Price" in lines
    key = lines.index("\tcolumn order_id")
    assert lines[key + 3] == "\t\tsummarizeBy: none"
    assert lines[lines.index("\tcolumn total") + 3] == "\t\tsummarizeBy: sum"
    assert "\tpartition orders = m" in lines and "\t\t\t\tlet" in lines
    assert text.endswith("\tannotation PBI_ResultType = Table\r\n")


def test_lineage_tags_and_bytes_are_the_same_every_time() -> None:
    a = rules.build("Store", [table("orders"), table("customers")], [], {"DATA": ""})
    b = rules.build("Store", [table("customers"), table("orders")], [], {"DATA": ""})
    assert a.files == b.files
    assert rules.lineage_tag("table", "orders") == rules.lineage_tag("table", "orders")
    assert rules.lineage_tag("table", "orders") != rules.lineage_tag("table", "customers")


def test_the_json_files_follow_microsofts_schemas() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    package = rules.build("Store", [table()], [], {"DATA": ""})
    schema_of = {
        "Store.pbip": "fabric_pbip_pbipProperties_1.0.0.json",
        "Store.SemanticModel/definition.pbism": "fabric_item_semanticModel_definitionProperties_1.0.0.json",
        "Store.Report/definition.pbir": "fabric_item_report_definitionProperties_2.0.0.json",
        "Store.Report/definition/version.json": "fabric_item_report_definition_versionMetadata_1.0.0.json",
        "Store.Report/definition/report.json": "fabric_item_report_definition_report_3.1.0.json",
        "Store.Report/definition/pages/pages.json": "fabric_item_report_definition_pagesMetadata_1.0.0.json",
        f"Store.Report/definition/pages/{rules.PAGE}/page.json": "fabric_item_report_definition_page"
        "_2.0.0.json",
    }
    for path, schema_file in schema_of.items():
        data = package.files[path]
        assert not data.startswith(b"\xef\xbb\xbf")  # UTF-8 without a byte order mark
        schema = json.loads((SCHEMAS / schema_file).read_text(encoding="utf-8"))
        jsonschema.validate(json.loads(data), schema)
    assert json.loads(package.files["Store.Report/definition.pbir"])["datasetReference"] == {
        "byPath": {"path": "../Store.SemanticModel"}
    }


def test_a_parameter_is_text_required_and_named_in_the_model() -> None:
    package = rules.build("Store", [table()], [], {"DATA": "", "SQL_SERVER": "sql.example.test"})
    expressions = package.files["Store.SemanticModel/definition/expressions.tmdl"].decode()
    assert (
        'expression SQL_SERVER = "sql.example.test" meta [IsParameterQuery=true, Type="Text", IsPara'
        "meterQueryRequired=true]" in expressions
    )
    assert 'expression DATA = "" meta' in expressions
    model = package.files["Store.SemanticModel/definition/model.tmdl"].decode()
    assert (
        'annotation PBI_QueryOrder = ["DATA","SQL_SERVER","orders"]' in model and "ref table orders" in model
    )


def test_stale_files_of_an_earlier_export() -> None:
    package = rules.build("Store", [table()], [], {})
    earlier = [
        "Store.SemanticModel/definition/tables/gone.tmdl",
        "Store.SemanticModel/data/gone.parquet",
        "Store.SemanticModel/.pbi/cache.abf",
        "Store.SemanticModel/definition/tables/orders.tmdl",
        "notes.txt",
    ]
    assert rules.stale("Store", earlier, package) == [
        "Store.SemanticModel/data/gone.parquet",
        "Store.SemanticModel/definition/tables/gone.tmdl",
    ]


# ===== through the server =====


def project(client: TestClient, tmp_path: Path) -> Path:
    """A made-up project: the store's tables read from CSV files, its relationships, and orders' steps."""
    folder = tmp_path / "Store analysis"
    ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
    store = make_store()
    (folder / "data").mkdir()
    for name in TABLES:
        csv = folder / "data" / f"{name}.csv"
        store[name].head(40).to_csv(csv, index=False)
        ok(client.post(f"/datasets/{name}/load", json={"path": str(csv)}, headers=AUTH))
    model = {
        "name": "current",
        "relationships": [
            {
                "from": r.from_table,
                "from_columns": list(r.from_columns),
                "to": r.to_table,
                "to_columns": list(r.to_columns),
                "kind": r.cardinality,
                "active": r.active,
            }
            for r in TRUE_RELATIONSHIPS
            if r.from_table in TABLES and r.to_table in TABLES
        ],
    }
    ok(client.post("/relationships", json={"model": model, "replace": True}, headers=AUTH))
    return folder


def warehouse(client: TestClient) -> None:
    """A made-up PostgreSQL connection: its host a variable, its password a secret (never in a file)."""
    code = (
        "import os\n\nimport psycopg\n\nconn = psycopg.connect(\n"
        '    host=os.environ["PG_HOST"],\n    port=5432,\n    dbname=os.environ["PG_DB"],\n    user='
        '"reader",\n'
        '    password=secret("password"),\n)\n'
    )
    body = {"name": "Warehouse", "kind": "sql", "template": "postgres", "dialect": "postgres", "code": code,
            "secrets": {"password": SECRET}}  # fmt: skip
    ok(client.post("/connections", json=body, headers=AUTH))
    ok(
        client.put(
            "/variables", json={"name": "PG_HOST", "value": "pg.example.test", "from": "value"}, headers=AUTH
        )
    )
    ok(client.put("/variables", json={"name": "PG_DB", "value": SECRET, "from": "keyring"}, headers=AUTH))


def test_export_into_the_project_byte_stable_and_no_secret(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = project(client, tmp_path)
        warehouse(client)
        ctx = client.app.state.ctx  # type: ignore[attr-defined]
        place = ("shop", "public", "suppliers")
        ok(
            client.post(
                "/datasets/suppliers/paste", content="supplier_id\tname\n1\tAcme Made-Up\n", headers=AUTH
            )
        )
        ctx.datasets.origins.note("suppliers", Origin("connection", connection="Warehouse", place=place))
        grid = ok(client.get("/grids", headers=AUTH))
        orders = next(g["grid"] for g in grid["grids"] if g["dataset"] == "orders")
        steps = [{"kind": "filter", "params": {"column": "status_code", "op": "ne", "value": 5}}]
        ok(client.post(f"/grids/{orders}/steps", json={"steps": steps}, headers=AUTH))
        ok(client.post("/datasets/notes/paste", content="a\tb\n1\t2\n", headers=AUTH))

        plan = ok(
            client.post("/powerbi/plan", json={"tables": [*TABLES, "suppliers", "notes"]}, headers=AUTH)
        )
        assert plan["name"] == "Store analysis" and plan["where"].endswith("powerbi/Store analysis.pbip")
        by = {t["name"]: t for t in plan["tables"]}
        assert by["notes"]["needs_rows"] and not by["notes"]["goes"] and "pasted" in by["notes"]["why"]
        assert any("steps are not carried" in n for n in by["orders"]["notes"])
        assert any("Only works on your machine" in n for n in by["orders"]["local"])
        assert by["suppliers"]["goes"] and plan["parameters"] == ["PG_DB", "PG_HOST"]
        rels = plan["relationships"]
        assert any(not r["active"] and r["goes"] for r in rels)  # calendar's second path

        body = {"tables": [*TABLES, "suppliers", "notes"], "include_rows": ["notes"]}
        done = ok(client.post("/powerbi/export", json=body, headers=AUTH))
        out = folder / "powerbi"
        assert (out / "Store analysis.pbip").is_file() and done["written"]
        assert (out / "Store analysis.SemanticModel" / "data" / "notes.parquet").is_file()
        tmdl = (out / "Store analysis.SemanticModel" / "definition" / "tables" / "suppliers.tmdl").read_text()
        assert 'PostgreSQL.Database(#"PG_HOST" & ":5432", #"PG_DB")' in tmdl
        expressions = (out / "Store analysis.SemanticModel" / "definition" / "expressions.tmdl").read_text()
        assert (
            'expression PG_HOST = "pg.example.test"' in expressions and "expression DataFolder" in expressions
        )
        assert 'expression PG_DB = "" meta' in expressions  # a keyring value: empty, for the user to fill in
        for path in out.rglob("*"):
            if path.is_file():
                assert SECRET.encode() not in path.read_bytes(), path
        assert ".pbi/cache.abf" in (out / ".gitignore").read_text()
        again = ok(client.post("/powerbi/export", json=body, headers=AUTH))
        assert again["written"] == [] and again["removed"] == []
        fewer = ok(client.post("/powerbi/export", json={"tables": list(TABLES)}, headers=AUTH))
        assert "Store analysis.SemanticModel/definition/tables/suppliers.tmdl" in fewer["removed"]
        assert not (out / "Store analysis.SemanticModel" / "data" / "notes.parquet").exists()
        refused = client.post("/powerbi/open", json={"path": done["where"]}, headers=AGENT)
        assert refused.status_code == 403


def test_with_no_project_a_zip_download(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        ok(client.post("/datasets/notes/paste", content="a\tb\n1\t2\n", headers=AUTH))
        response = client.post(
            "/powerbi/export", json={"tables": ["notes"], "include_rows": True}, headers=AUTH
        )
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
        assert response.content[:2] == b"PK"
        nothing = client.post("/powerbi/export", json={"tables": ["notes"]}, headers=AUTH)
        assert nothing.status_code == 403 and "Include its rows" in nothing.text


def test_the_agents_export_with_rows_waits_for_the_users_allow(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        project(client, tmp_path)
        ok(client.post("/datasets/notes/paste", content="a\tb\n1\t2\n", headers=AUTH))
        answer: dict[str, Any] = {}

        def export() -> None:
            body = {"tables": ["notes", "regions"], "include_rows": ["notes"]}
            answer["response"] = client.post("/powerbi/export", json=body, headers=AGENT)

        waiting = threading.Thread(target=export)
        waiting.start()
        pending: list[dict[str, Any]] = []
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            time.sleep(0.05)
        assert pending and "notes" in pending[0]["detail"]
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH))
        waiting.join(10)
        assert answer["response"].status_code == 403
        assert not (tmp_path / "Store analysis" / "powerbi").exists()
        without = ok(client.post("/powerbi/export", json={"tables": ["regions"]}, headers=AGENT))
        assert without["written"]
