"""duckpq's sources: files read with no resolver, a resolver's answers, queries that name each other, the
order they run in, cycles, parameters and variables. Made-up data only. Imports only duckpq, duckdb and the
standard library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

import duckpq

ORDERS = "id,customer,amount\n1,ann,10.5\n2,bob,200\n3,ann,150\n"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "orders.csv").write_text(ORDERS, encoding="utf-8")
    (tmp_path / "semi.csv").write_text("id;name\n1;x\n", encoding="utf-8")
    (tmp_path / "people.json").write_text(
        json.dumps([{"name": "ann", "age": 31}, {"name": "bob", "age": 40}]), encoding="utf-8"
    )
    (tmp_path / "nested.json").write_text(
        json.dumps({"data": {"items": [{"sku": "a", "qty": 2}, {"sku": "b", "qty": 5}]}}), encoding="utf-8"
    )
    duckdb.connect().execute(
        f"COPY (SELECT 1 AS k, 'one' AS word UNION ALL SELECT 2, 'two') TO '{tmp_path / 'words.parquet'}' "
        "(FORMAT parquet)"
    )
    warehouse = duckdb.connect(str(tmp_path / "warehouse.duckdb"))
    warehouse.execute("CREATE SCHEMA crm")
    warehouse.execute(
        "CREATE TABLE crm.customers AS SELECT * FROM (VALUES ('ann', 'North'), ('bob', 'South')) v(name, region)"
    )
    warehouse.execute(
        "CREATE TABLE regions AS SELECT * FROM (VALUES ('North', 1), ('South', 2)) v(region, code)"
    )
    warehouse.close()
    return tmp_path


def test_a_csv_with_no_resolver(folder: Path) -> None:
    made = duckpq.run(
        'let S = Csv.Document(File.Contents("orders.csv"), [Delimiter = ",", Encoding = 65001]), '
        "P = Table.PromoteHeaders(S, [PromoteAllScalars = true]) in Table.SelectRows(P, each [amount] > 100)",
        folder=str(folder),
    )["Query"]
    assert made.columns == ["id", "customer", "amount"] and [r[0] for r in made.fetchall()] == [2, 3]


def test_a_csvs_delimiter_is_passed_on(folder: Path) -> None:
    made = duckpq.run(
        f'Table.PromoteHeaders(Csv.Document(File.Contents("{folder / "semi.csv"}"), [Delimiter = ";"]))'
    )["Query"]
    assert made.columns == ["id", "name"]


def test_a_file_never_promoted_is_refused_not_guessed(folder: Path) -> None:
    with pytest.raises(duckpq.PowerQueryError, match="Table.PromoteHeaders"):
        duckpq.run('Csv.Document(File.Contents("orders.csv"))', folder=str(folder))


def test_parquet_and_json(folder: Path) -> None:
    assert duckpq.run('Parquet.Document(File.Contents("words.parquet"))', folder=str(folder))["Query"].fetchall() == [
        (1, "one"), (2, "two"),
    ]  # fmt: skip
    people = duckpq.run('Table.FromRecords(Json.Document(File.Contents("people.json")))', folder=str(folder))
    assert people["Query"].fetchall() == [("ann", 31), ("bob", 40)]
    expanded = duckpq.run(
        'let J = Json.Document(File.Contents("people.json")), '
        "L = Table.FromList(J, Splitter.SplitByNothing(), null, null, ExtraValues.Error) in "
        'Table.ExpandRecordColumn(L, "Column1", {"name", "age"}, {"Name", "Age"})',
        folder=str(folder),
    )["Query"]
    assert expanded.columns == ["Name", "Age"] and expanded.fetchall() == [("ann", 31), ("bob", 40)]
    nested = duckpq.run(
        'Table.FromRecords(Json.Document(File.Contents("nested.json"))[data][items])', folder=str(folder)
    )["Query"]
    assert nested.fetchall() == [("a", 2), ("b", 5)]


def test_a_missing_file_says_so_at_its_line(folder: Path) -> None:
    with pytest.raises(duckpq.PowerQueryError) as caught:
        duckpq.run(
            'let\n  S = Csv.Document(File.Contents("nope.csv"))\nin Table.PromoteHeaders(S)',
            folder=str(folder),
        )
    assert caught.value.line == 2 and "nope.csv" in str(caught.value)


def database(folder: Path) -> Any:
    def resolver(source: duckpq.Source) -> Any:
        return str(folder / "warehouse.duckdb") if source.function == "Sql.Database" else None

    return resolver


def test_a_database_source_through_the_resolver_and_its_navigation(folder: Path) -> None:
    seen: list[duckpq.Source] = []

    def resolver(source: duckpq.Source) -> Any:
        seen.append(source)
        return str(folder / "warehouse.duckdb")

    made = duckpq.run(
        'let Source = Sql.Database("srv.example", "sales"), '
        'T = Source{[Schema = "crm", Item = "customers"]}[Data] in T',
        resolver=resolver,
    )["Query"]
    assert made.fetchall() == [("ann", "North"), ("bob", "South")]
    (source,) = seen
    assert (source.function, source.arguments, source.kind) == (
        "Sql.Database",
        ("srv.example", "sales"),
        "call",
    )
    assert [dict(step) for step in source.navigation] == [{"Schema": "crm", "Item": "customers"}]
    assert source.words() == 'Sql.Database("srv.example", "sales") crm.customers'


def test_a_native_query_runs_in_the_resolved_database(folder: Path) -> None:
    by_option = duckpq.run(
        'Sql.Database("srv", "db", [Query = "SELECT code FROM regions ORDER BY code DESC"])',
        resolver=database(folder),
    )["Query"]
    assert by_option.fetchall() == [(2,), (1,)]
    by_function = duckpq.run(
        'Value.NativeQuery(Sql.Database("srv", "db"), "SELECT count(*) AS n FROM crm.customers", null, '
        "[EnableFolding = true])",
        resolver=database(folder),
    )["Query"]
    assert by_function.fetchall() == [(2,)]


def test_snowflake_style_navigation_by_name(folder: Path) -> None:
    seen: list[duckpq.Source] = []

    def resolver(source: duckpq.Source) -> Any:
        seen.append(source)
        return duckdb.connect().sql("SELECT 42 AS answer").fetchdf()

    made = duckpq.run(
        'let S = Snowflake.Databases("acme.snowflakecomputing.com", "WH"), '
        'D = S{[Name = "SALES", Kind = "Database"]}[Data], '
        'Sch = D{[Name = "PUBLIC", Kind = "Schema"]}[Data], '
        'T = Sch{[Name = "ORDERS", Kind = "Table"]}[Data] in T',
        resolver=resolver,
    )["Query"]
    assert made.fetchall() == [(42,)]
    assert [step["Name"] for step in seen[0].navigation] == ["SALES", "PUBLIC", "ORDERS"]


@pytest.mark.parametrize(
    "call",
    [
        'PostgreSQL.Database("pg.example", "shop")',
        'MySQL.Database("my.example", "shop")',
        'Oracle.Database("ora.example")',
        'Databricks.Catalogs("adb.example", "/sql/1.0/warehouses/x", null)',
        'CommonDataService.Database("org.crm.dynamics.com")',
        'OData.Feed("https://example.org/odata")',
    ],
)
def test_every_database_function_reaches_the_resolver(call: str) -> None:
    seen: list[str] = []

    def resolver(source: duckpq.Source) -> Any:
        seen.append(source.function)
        return duckdb.sql("SELECT 1 AS one")

    made = duckpq.run(f'{call}{{[Schema = "s", Item = "t"]}}[Data]', resolver=resolver)["Query"]
    assert made.fetchall() == [(1,)] and seen == [call.split("(")[0]]


def test_a_source_nothing_resolves_is_refused_with_its_line() -> None:
    with pytest.raises(duckpq.PowerQueryError) as caught:
        duckpq.run('let\n  S = Sql.Database("srv", "db"),\n  T = S{[Schema = "dbo", Item = "t"]}[Data]\nin T')
    assert caught.value.line == 3 and "Nothing reads Sql.Database" in str(caught.value)
    with pytest.raises(duckpq.PowerQueryError, match="Nothing reads Web.Contents"):
        duckpq.run('Table.PromoteHeaders(Csv.Document(Web.Contents("https://example.org/a.csv")))')


def test_a_resolvers_refusal_is_said_at_the_source() -> None:
    def resolver(source: duckpq.Source) -> Any:
        raise RuntimeError("No saved connection matches srv.")

    with pytest.raises(duckpq.PowerQueryError, match="No saved connection matches srv."):
        duckpq.run('Sql.Database("srv", "db"){[Item = "t"]}[Data]', resolver=resolver)


def test_a_table_given_by_name() -> None:
    connection = duckdb.connect()
    stock = connection.sql("SELECT * FROM (VALUES ('a', 3), ('b', 0)) v(sku, qty)")
    made = duckpq.run(
        "Table.SelectRows(stock, each [qty] > 0)", tables={"stock": stock}, connection=connection
    )["Query"]
    assert made.fetchall() == [("a", 3)]


def test_queries_name_each_other_and_run_in_dependency_order(folder: Path) -> None:
    text = (
        "section S;\n"
        'shared Top = Table.FirstN(Table.Sort(Totals, {{"total", Order.Descending}}), 1);\n'
        'shared Totals = Table.Group(Orders, {"customer"}, {{"total", each List.Sum([amount]), type number}});\n'
        'shared Orders = Table.PromoteHeaders(Csv.Document(File.Contents("orders.csv")));\n'
        "Helper = (v) => v * 2;\n"
        "shared Limit = 100;\n"
    )
    made = duckpq.compile(text, context=None)
    assert not made.complete  # the CSV's columns are still to be read
    tables = duckpq.run(text, folder=str(folder))
    assert list(tables) == ["Orders", "Totals", "Top"]
    assert tables["Top"].fetchall() == [("bob", 200.0)]
    assert sorted(tables["Totals"].fetchall()) == [("ann", 160.5), ("bob", 200.0)]


def test_compile_reports_kinds_order_and_dependencies() -> None:
    made = duckpq.compile(
        "section S;\n"
        "shared B = Table.SelectRows(A, each [x] > Limit);\n"
        'shared A = #table({"x"}, {{1}, {5}});\n'
        "shared Limit = 2 meta [IsParameterQuery = true];\n"
        "F = (v) => v;\n"
    )
    assert made.complete and not made.problems
    assert {x.name: x.kind for x in made.queries} == {
        "B": "table",
        "A": "table",
        "Limit": "value",
        "F": "function",
    }
    assert made.order == ("A", "B") and made.query("B").depends == ("A", "Limit")
    assert made.query("Limit").value == 2 and made.query("B").columns == ("x",)


def test_a_cycle_is_one_problem_naming_the_loop() -> None:
    problems = duckpq.check(
        "section S;\nshared A = Table.Buffer(B);\nshared B = Table.Buffer(C);\nshared C = A;\n"
    )
    assert len(problems) >= 1
    assert "refers to itself (A -> B -> C -> A)" in problems[0].message and problems[0].line == 4
    inner = duckpq.check("let a = b, b = a in a")
    assert "refers to itself" in inner[0].message


def test_a_problem_in_one_query_does_not_stop_the_others() -> None:
    made = duckpq.compile(
        'section S;\nshared Good = #table({"x"}, {{1}});\nshared Bad = Table.Nope(Good);\n'
        "shared Uses = Table.Buffer(Bad);\nshared Wrong = Table.SelectRows(Good, each [y] = 1);\n"
    )
    assert [(p.query, p.line, p.name) for p in made.problems] == [("Bad", 3, "Table.Nope"), ("Wrong", 5, "y")]
    assert made.order == ("Good",) and made.query("Uses").kind == "problem"
    assert "Bad cannot run" in str(made.query("Uses").problem)


def test_parameters_and_variables(folder: Path) -> None:
    text = (
        "section S;\n"
        'shared File = "nope.csv" meta [IsParameterQuery = true, Type = "Text"];\n'
        "shared Least = 1000 meta [IsParameterQuery = true];\n"
        "shared Orders = Table.SelectRows(Table.PromoteHeaders(Csv.Document(File.Contents(File))), "
        "each [amount] >= Least);\n"
    )
    made = duckpq.run(text, parameters={"File": "orders.csv", "Least": 150}, folder=str(folder))
    assert [r[0] for r in made["Orders"].fetchall()] == [2, 3]
    by_variable = duckpq.run(
        'Table.PromoteHeaders(Csv.Document(File.Contents("${DATA}/orders.csv")))',
        variables={"DATA": str(folder)},
    )["Query"]
    assert len(by_variable.fetchall()) == 3
    with pytest.raises(duckpq.PowerQueryError, match="DATA.*has no value"):
        duckpq.run('Table.PromoteHeaders(Csv.Document(File.Contents("${DATA}/orders.csv")))')


def test_bound_variables_stay_names_in_the_sql() -> None:
    """A caller that binds ${NAME} itself gets it in the SQL, never its value."""
    context = duckpq.Context(bind_variables=True)
    made = duckpq.compile(
        'Table.SelectRows(#table({"region"}, {{"North"}}), each [region] = "${REGION}")', context=context
    )
    assert made.complete and "${REGION}" in str(made.queries[0].sql)


def test_to_sql_and_run_query(folder: Path) -> None:
    text = (
        'section S;\nshared Orders = Table.PromoteHeaders(Csv.Document(File.Contents("orders.csv")));\n'
        "shared Big = Table.SelectRows(Orders, each [amount] > 100);\n"
    )
    connection = duckdb.connect()
    sql = duckpq.to_sql(text, folder=str(folder), connection=connection)
    assert (
        list(sql) == ["Orders", "Big"] and sql["Big"] == 'SELECT * FROM "m_source_0" WHERE (("amount" > 100))'
    )
    assert connection.execute(sql["Big"]).fetchall() == [(2, "bob", 200.0), (3, "ann", 150.0)]
    one = duckpq.run_query(text, "Big", folder=str(folder))
    assert [r[0] for r in one.fetchall()] == [2, 3]
    with pytest.raises(duckpq.PowerQueryError, match="no query named Nope"):
        duckpq.run_query(text, "Nope", folder=str(folder))


def test_a_filter_and_a_pick_of_columns_stay_one_flat_query() -> None:
    """What a source can take (its columns, its filters) is not buried in subqueries."""
    context = duckpq.Context(tables={"orders": ["id", "amount", "note"]})
    made = duckpq.compile(
        'Table.SelectColumns(Table.SelectRows(Table.SelectRows(orders, each [amount] > 5), each [id] <> 3), {"id", "amount"})',
        context=context,
    )
    assert (
        made.queries[0].sql
        == 'SELECT "id", "amount" FROM "orders" WHERE (("amount" > 5)) AND (("id" IS DISTINCT FROM 3))'
    )


def test_compile_asks_by_key_and_a_caller_names_a_source_its_own_way() -> None:
    """The loop a caller with its own engine runs: missing keys, resolved, compiled again."""
    context = duckpq.Context()
    text = 'Table.SelectRows(Sql.Database("srv", "db"){[Schema = "dbo", Item = "Orders"]}[Data], each [Amount] > 1)'
    first = duckpq.compile(text, context=context)
    assert not first.complete and context.missing == [("source", "m_source_0")]
    assert context.sources["m_source_0"].function == "Sql.Database"
    context.resolved[("source", "m_source_0")] = duckpq.Resolved(["Id", "Amount"], "[Warehouse].dbo.Orders")
    second = duckpq.compile(text, context=context)
    assert (
        second.complete
        and second.queries[0].sql == 'SELECT * FROM [Warehouse].dbo.Orders WHERE (("Amount" > 1))'
    )
    context.resolved[("source", "m_source_0")] = duckpq.Failure("No saved connection matches srv and db.")
    (problem,) = duckpq.compile(text, context=context).problems
    assert problem.message == "No saved connection matches srv and db."


def test_what_cannot_run_is_refused_with_its_line_and_name() -> None:
    cases = {
        'let\n  a = #table({"x"}, {{1}}),\n  b = Table.Transpose(a)\nin b': (3, "Table.Transpose"),
        'Table.Group(#table({"x"}, {{1}}), {"x"}, {{"all", each _}})': (1, "all"),
        "Table.PromoteHeaders(Table.SelectRows(t, each true))": (1, "Table.PromoteHeaders"),
        'Table.AddColumn(#table({"x"}, {{1}}), "y", each List.Transform({1}, (v) => v){[x]})': (1, None),
    }
    for text, (line, name) in cases.items():
        problems = duckpq.check(text, tables={"t": ["a"]})
        assert problems, text
        assert problems[0].line == line and (name is None or problems[0].name == name), problems[0]
