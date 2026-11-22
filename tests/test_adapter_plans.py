"""What a plan says, added for the endpoint wizard (adapter 1.5.0 on; docs/ideas.md "The endpoint wizard
and its patterns"): a plan's values keep their type through JSON (a date sent as a date comes back as one),
a group by a date's period folded into every source's own SQL, and a "contains, any case" filter. Each
against every backend it touches: DuckDB, the sandbox through Remote, the SQL dialects (SQLite always; each
dialect's text read back by sqlglot), OData and Rows (DuckDB over the stream), Files and Excel. Made-up data
only."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest
import sqlglot
from starlette.testclient import TestClient

from swissarmybench.adapters import adapter
from swissarmybench.adapters.adapter import Filter, Period, Plan, Total
from tests import dataverse_standin as made_up
from tests import test_adapter_sql as sql_tests
from tests import test_dataverse as dataverse_tests
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_dataverse import connect as dataverse_connect
from tests.test_sandbox_query import TestRemote, _put

keyring = dataverse_tests.keyring  # the Dataverse stand-in's fixtures: a memory keyring, the stand-in
standin = dataverse_tests.standin
postgres = sql_tests.postgres  # the test bed's PostgreSQL, when it runs

VISITS = pa.table(
    {
        "id": [1, 2, 3, 4, 5],
        "garden": ["Rose Bed", "Herb Patch", "rose arch", "Pond", "Old Rose"],
        "seen": [dt.date(2026, 1, 5), dt.date(2026, 1, 20), dt.date(2026, 2, 3), dt.date(2026, 4, 9),
                 dt.date(2026, 4, 30)],
        "at": [dt.datetime(2026, 1, 5, 9, 30), dt.datetime(2026, 1, 20, 14, 0),
               dt.datetime(2026, 2, 3, 8, 15), dt.datetime(2026, 4, 9, 17, 45),
               dt.datetime(2026, 4, 30, 23, 59)],
        "cost": pa.array([decimal.Decimal("12.50"), decimal.Decimal("3.25"), decimal.Decimal("40.00"),
                          decimal.Decimal("7.75"), decimal.Decimal("1.00")], pa.decimal128(8, 2)),
    }
)  # fmt: skip


# ----- 1.5.0: a plan's values keep their type through JSON -----


def test_a_plans_dates_times_and_decimals_go_through_json_as_themselves() -> None:
    plan = Plan(
        filters=(
            Filter("seen", ">=", dt.date(2026, 1, 20)),
            Filter("at", "between", [dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 3, 1, 12, 30, 5, 7)]),
            Filter("opens", "=", dt.time(9, 30)),
            Filter("cost", "in", [decimal.Decimal("12.50"), decimal.Decimal("3.25")]),
            Filter("garden", "=", "Pond"),
        )
    )
    sent = json.dumps(plan.to_json(typed=True))  # no default=: every value is JSON's own
    back = adapter.plan_from(json.loads(sent))
    assert back == plan
    assert [type(f.value) for f in back.filters][:3] == [dt.date, list, dt.time]
    assert type(back.filters[1].value[1]) is dt.datetime and back.filters[1].value[1].microsecond == 7
    assert type(back.filters[3].value[0]) is decimal.Decimal
    # The plain JSON is as it was: a value as itself (a caller passing default= of its own).
    assert plan.to_json()["filters"][0] == ["seen", ">=", dt.date(2026, 1, 20)]
    # A zoned time keeps its zone.
    zoned = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    again = adapter.plan_from(json.loads(json.dumps(Plan(filters=(Filter("at", ">", zoned),)).to_json(True))))
    assert again.filters[0].value == zoned and again.filters[0].value.utcoffset() == dt.timedelta(hours=2)


def test_a_typed_value_that_is_not_one_is_said_plainly() -> None:
    with pytest.raises(adapter.AdapterError, match="not a date"):
        adapter.plan_from({"filters": [["seen", "=", {"sab_type": "date", "value": "the fifth"}]]})
    with pytest.raises(adapter.AdapterError, match="sab_type is one of"):
        adapter.plan_from({"filters": [["seen", "=", {"sab_type": "colour", "value": "red"}]]})


@pytest.fixture
def boxed(tmp_path: Path) -> Iterator[TestClient]:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "garden")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "visits", VISITS)
        yield client


def test_the_sandbox_through_remote_reads_with_a_date_a_datetime_and_a_decimal(boxed: TestClient) -> None:
    source = TestRemote(boxed, "Sandbox")
    plan = Plan(
        columns=("id",),
        filters=(
            Filter("seen", ">=", dt.date(2026, 1, 20)),
            Filter("at", "<", dt.datetime(2026, 4, 30, 0, 0)),
            Filter("cost", ">", decimal.Decimal("5")),
        ),
        sort=(("id", False),),
    )
    reader, folded = adapter.read(source, "visits", plan)
    assert reader.read_all().column("id").to_pylist() == [3, 4]
    assert folded.parts == ("filters", "columns", "sort")
    db = adapter.Connection(source, "Sandbox")
    january = [dt.date(2026, 1, 1), dt.date(2026, 1, 31)]
    found = db.read("visits", columns=["id"], filters=[["seen", "between", january]])
    assert sorted(found.read_all().column("id").to_pylist()) == [1, 2]


def test_sqlite_takes_a_plans_date_as_its_own_text(tmp_path: Path) -> None:
    con = sqlite3.connect(tmp_path / "garden.db")
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, seen TEXT, cost REAL)")
    con.executemany("INSERT INTO visits VALUES (?, ?, ?)", [(1, "2026-01-05", 12.5), (2, "2026-02-03", 40.0)])
    con.commit()
    source = adapter.Sql(con, "sqlite", "Garden")
    plan = Plan(columns=("id",), filters=(Filter("seen", ">=", dt.date(2026, 1, 20)),
                                          Filter("cost", ">", decimal.Decimal("10"))))  # fmt: skip
    assert adapter.read(source, "visits", plan)[0].read_all().column("id").to_pylist() == [2]


# ----- 1.8.0: a group by a date's period, folded into every source's own SQL -----

SALES = pa.table(
    {
        "id": list(range(1, 9)),
        "region": ["North", "North", "South", "North", "South", "South", "North", "South"],
        "placed": [dt.date(2025, 12, 31), dt.date(2026, 1, 1), dt.date(2026, 1, 4), dt.date(2026, 1, 5),
                   dt.date(2026, 3, 31), dt.date(2026, 4, 1), dt.date(2026, 6, 30), dt.date(2026, 7, 2)],
        "amount": [10.0, 20.0, 5.0, 7.0, 1.0, 2.0, 3.0, 4.0],
    }
)  # fmt: skip
# Each row's period's first day, by hand (a week starts on Monday: 2026-01-05 is one).
STARTS = {
    "year": ["2025-01-01"] + ["2026-01-01"] * 7,
    "quarter": ["2025-10-01", "2026-01-01", "2026-01-01", "2026-01-01", "2026-01-01", "2026-04-01",
                "2026-04-01", "2026-07-01"],
    "month": ["2025-12-01", "2026-01-01", "2026-01-01", "2026-01-01", "2026-03-01", "2026-04-01",
              "2026-06-01", "2026-07-01"],
    "week": ["2025-12-29", "2025-12-29", "2025-12-29", "2026-01-05", "2026-03-30", "2026-03-30",
             "2026-06-29", "2026-06-29"],
    "day": [str(d) for d in SALES.column("placed").to_pylist()],
}  # fmt: skip


def _expected(unit: str) -> list[tuple[dt.date, int, float]]:
    """Each period's start, its row count and its amount, by hand from STARTS."""
    totals: dict[dt.date, list[float]] = {}
    for start, amount in zip(STARTS[unit], SALES.column("amount").to_pylist(), strict=True):
        totals.setdefault(dt.date.fromisoformat(start), []).append(amount)
    return [(k, len(v), sum(v)) for k, v in sorted(totals.items())]


def _period_plan(unit: str) -> Plan:
    return Plan(
        periods=(Period("placed", unit, "period"),),
        totals=(Total("count", name="rows"), Total("sum", "amount", "amount")),
        sort=(("period", False),),
    )


def _answered(reader: pa.RecordBatchReader) -> list[tuple[dt.date, int, float]]:
    found = reader.read_all()
    assert found.schema.field("period").type == pa.date32(), found.schema  # a date, from every source
    return [(r["period"], r["rows"], r["amount"]) for r in found.to_pylist()]


SQLGLOT = {
    "postgres": "postgres", "mysql": "mysql", "sqlserver": "tsql", "oracle": "oracle", "sqlite": "sqlite",
    "snowflake": "snowflake", "trino": "trino", "databricks": "databricks",
}  # fmt: skip


@pytest.mark.parametrize("dialect", sorted(SQLGLOT))
@pytest.mark.parametrize("unit", adapter.PERIODS)
def test_each_dialect_groups_by_a_period_in_its_own_sql(dialect: str, unit: str) -> None:
    plan = Plan(
        periods=(Period("placed", unit),),
        group=("region",),
        filters=(Filter("region", "!=", "East"),),
        totals=(Total("sum", "amount"),),
        sort=(("placed_" + unit, True),),
        limit=10,
    )
    for style in ("qmark", "pyformat"):
        sql, params = adapter.dialect_sql(adapter.DIALECTS[dialect], "sales.orders", plan, style)
        assert params == ["East"]
        if style == "pyformat" and dialect != "sqlite":  # %s marks: a literal % would be misread
            assert sql.count("%") == sql.count("%s"), sql
    parsed = sqlglot.parse_one(sql.replace("%s", "1"), read=SQLGLOT[dialect])
    grouped = parsed.args.get("group")
    assert grouped is not None and len(grouped.expressions) == 2, sql  # the period's expression, region
    picked = [e.alias_or_name for e in parsed.expressions]
    assert picked == ["placed_" + unit, "region", "sum_amount"], sql


@pytest.mark.parametrize("unit", adapter.PERIODS)
def test_duckdb_and_sqlite_fold_a_period_and_give_each_periods_first_day(tmp_path: Path, unit: str) -> None:
    path = str(tmp_path / f"shop-{unit}.duckdb")
    con = duckdb.connect(path)
    con.register("given", SALES)
    con.execute("CREATE TABLE sales AS SELECT * FROM given")
    con.close()
    reader, folded = adapter.read(adapter.DuckDB.file(path), "sales", _period_plan(unit))
    assert folded.parts == ("group", "totals", "sort") and _answered(reader) == _expected(unit)
    lite = sqlite3.connect(tmp_path / f"shop-{unit}.db")
    lite.execute("CREATE TABLE sales (id INTEGER, region TEXT, placed TEXT, amount REAL)")
    rows = [(r["id"], r["region"], str(r["placed"]), r["amount"]) for r in SALES.to_pylist()]
    lite.executemany("INSERT INTO sales VALUES (?, ?, ?, ?)", rows)
    lite.commit()
    reader, folded = adapter.read(adapter.Sql(lite, "sqlite"), "sales", _period_plan(unit))
    assert folded.parts == ("group", "totals", "sort") and _answered(reader) == _expected(unit)


def test_postgresql_folds_every_period_when_the_test_bed_runs(postgres: Any) -> None:
    postgres.execute(
        "CREATE TEMP TABLE sales (id integer, region text, placed date, amount double precision)"
    )
    with postgres.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO sales VALUES (%s, %s, %s, %s)",
            [(r["id"], r["region"], r["placed"], r["amount"]) for r in SALES.to_pylist()],
        )
    postgres.commit()
    source = adapter.Sql(postgres, "postgres", "Shop")
    for unit in adapter.PERIODS:
        plan = replace(_period_plan(unit), filters=(Filter("region", "!=", "East"),))  # a %s mark beside it
        reader, folded = adapter.read(source, "pg_temp.sales", plan)
        assert folded.parts == ("filters", "group", "totals", "sort")
        assert _answered(reader) == _expected(unit), unit


def test_a_period_and_a_group_through_the_sandbox_and_by_name_in_json(tmp_path: Path) -> None:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "shop")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "sales", SALES)
        plan = adapter.plan_from(
            {"periods": [{"column": "placed", "unit": "quarter", "name": "quarter"}], "group": ["region"],
             "totals": [{"fn": "sum", "column": "amount", "name": "amount"}],
             "filters": [["placed", ">=", {"sab_type": "date", "value": "2026-01-01"}]],
             "sort": [["quarter", "asc"], ["region", "asc"]]}
        )  # fmt: skip
        assert adapter.plan_from(json.loads(json.dumps(plan.to_json(typed=True)))) == plan
        found = adapter.read(TestRemote(client, "Sandbox"), "sales", plan)[0].read_all().to_pylist()
    assert found == [
        {"quarter": dt.date(2026, 1, 1), "region": "North", "amount": 27.0},
        {"quarter": dt.date(2026, 1, 1), "region": "South", "amount": 6.0},
        {"quarter": dt.date(2026, 4, 1), "region": "North", "amount": 3.0},
        {"quarter": dt.date(2026, 4, 1), "region": "South", "amount": 2.0},
        {"quarter": dt.date(2026, 7, 1), "region": "South", "amount": 4.0},
    ]


def test_a_period_of_dates_held_as_text_is_read_as_dates_first(tmp_path: Path) -> None:
    texts = SALES.set_column(2, "placed", pa.array([str(d) for d in SALES.column("placed").to_pylist()]))
    path = str(tmp_path / "texts.duckdb")
    con = duckdb.connect(path)
    con.register("given", texts)
    con.execute("CREATE TABLE sales AS SELECT * FROM given")
    con.close()
    reader, _ = adapter.read(adapter.DuckDB.file(path), "sales", _period_plan("quarter"))
    assert _answered(reader) == _expected("quarter")

    class Texts(Shelf):
        def rows(self, table: str, schema: str = "", limit: Any = None, columns: Any = None,
                 filters: Any = None, frame: bool = False) -> tuple[pa.Table, int]:  # fmt: skip
            return texts.select(columns), texts.num_rows

    reader, _ = adapter.read(adapter.Rows(Texts(), "Lake"), "sales", _period_plan("week"))
    assert _answered(reader) == _expected("week")
    plain, _ = adapter.plan_sql('"sales"', _period_plan("month"))
    assert "CAST(DATE_TRUNC('month', \"placed\") AS DATE)" in plain  # a date column: no cast before it


def test_a_period_is_checked_and_said_plainly() -> None:
    with pytest.raises(adapter.AdapterError, match="A period is one of year, quarter, month, week, day"):
        adapter.check_plan(Plan(periods=(Period("placed", "fortnight"),), totals=(Total("count"),)))
    with pytest.raises(adapter.AdapterError, match="names its totals"):
        adapter.check_plan(Plan(periods=(Period("placed"),)))
    assert Period("placed").label == "placed_month"
    assert Plan(periods=(Period("placed"),), totals=(Total("count"),)).parts() == ("group", "totals")
    assert "periods" not in Plan().to_json()  # a plan without one says it as before


class Shelf:
    """A connection shaped like the lakes' and SharePoint's (rows applies what it is sent)."""

    def __init__(self) -> None:
        self.asked: list[Any] = []

    def catalog(self) -> list[dict[str, str]]:
        return [{"table_name": "sales", "column_name": n, "data_type": "VARCHAR"} for n in SALES.column_names]

    def rows(self, table: str, schema: str = "", limit: Any = None, columns: Any = None, filters: Any = None,
             frame: bool = False) -> tuple[pa.Table, int]:  # fmt: skip
        self.asked.append(columns)
        found = SALES.select(columns) if columns else SALES
        return found, found.num_rows


def test_rows_and_odata_read_only_the_columns_a_period_needs_and_duckdb_groups_them(
    standin: made_up.StandIn,
) -> None:
    shelf = Shelf()
    reader, folded = adapter.read(adapter.Rows(shelf, "Lake"), "sales", _period_plan("month"))
    assert folded.parts == () and _answered(reader) == _expected("month")
    assert shelf.asked == [["placed", "amount"]]  # never the whole table
    source = adapter.OData(dataverse_connect(standin))
    plan = Plan(periods=(Period("estimatedclosedate", "year", "year"),), totals=(Total("count"),),
                sort=(("year", False),))  # fmt: skip
    found = adapter.read(source, "opportunity", plan)[0].read_all()
    assert found.column_names == ["year", "count"] and found.schema.field("year").type == pa.date32()
    assert sum(found.column("count").to_pylist()) == made_up.OPPORTUNITIES
    asked = next(r for r in reversed(standin.gets()) if r["path"].endswith("/opportunities"))["query"]
    assert asked["$select"] == "estimatedclosedate"


# ----- 1.9.0: contains, in any case -----

GARDENS = pa.table(
    {
        "id": [1, 2, 3, 4, 5, 6],
        "name": ["Rose Bed", "Herb Patch", "rose arch", "Pond", "50% off_cuts", "OLD ROSE"],
    }
)


def _found(source: Any, text: str, table: str = "gardens") -> list[int]:
    plan = Plan(columns=("id",), filters=(Filter("name", "contains", text),), sort=(("id", False),))
    return list(adapter.read(source, table, plan)[0].read_all().column("id").to_pylist())


def test_contains_matches_in_any_case_and_takes_its_text_literally(tmp_path: Path) -> None:
    path = str(tmp_path / "gardens.duckdb")
    con = duckdb.connect(path)
    con.register("given", GARDENS)
    con.execute("CREATE TABLE gardens AS SELECT * FROM given")
    con.close()
    lite = sqlite3.connect(tmp_path / "gardens.db")
    lite.execute("CREATE TABLE gardens (id INTEGER, name TEXT)")
    lite.executemany("INSERT INTO gardens VALUES (?, ?)", [(r["id"], r["name"]) for r in GARDENS.to_pylist()])
    lite.commit()
    for source in (adapter.DuckDB.file(path), adapter.Sql(lite, "sqlite")):
        assert _found(source, "rose") == [1, 3, 6]
        assert _found(source, "ROSE A") == [3]
        assert _found(source, "0% off_") == [5]  # % and _ are the text's own, never a wildcard
        assert _found(source, "%") == [5] and _found(source, "_") == [5]
        assert _found(source, "") == [1, 2, 3, 4, 5, 6]
        assert _found(source, "!") == []
    with pytest.raises(adapter.AdapterError, match="contains takes text"):
        adapter.check_plan(Plan(filters=(Filter("name", "contains", 5),)))


@pytest.mark.parametrize("dialect", sorted(SQLGLOT))
def test_each_dialect_says_contains_as_a_lowered_like_with_its_text_escaped(dialect: str) -> None:
    plan = Plan(filters=(Filter("name", "contains", "50% Off_[x]!"),))
    sql, params = adapter.dialect_sql(adapter.DIALECTS[dialect], "gardens", plan)
    assert sql.endswith("WHERE LOWER(" + adapter.DIALECTS[dialect].quote("name") + ") LIKE ? ESCAPE '!'"), sql
    bracket = "![" if dialect == "sqlserver" else "["  # T-SQL's LIKE reads [ as a set of characters
    assert params == [f"%50!% off!_{bracket}x]!!%"]
    sqlglot.parse_one(sql.replace("?", "'x'"), read=SQLGLOT[dialect])


def test_postgresql_contains_in_any_case_when_the_test_bed_runs(postgres: Any) -> None:
    postgres.execute("CREATE TEMP TABLE gardens (id integer, name text)")
    with postgres.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO gardens VALUES (%s, %s)", [(r["id"], r["name"]) for r in GARDENS.to_pylist()]
        )
    postgres.commit()
    source = adapter.Sql(postgres, "postgres", "Shop")
    assert _found(source, "rose", "pg_temp.gardens") == [1, 3, 6]
    assert _found(source, "0% off_", "pg_temp.gardens") == [5]
    assert _found(source, "_", "pg_temp.gardens") == [5]


def test_contains_through_the_sandbox_rows_and_odata(tmp_path: Path, standin: made_up.StandIn) -> None:
    with memory_keyring(), make_client(tmp_path) as client:
        made = client.post("/project/new", json={"path": str(tmp_path / "garden")}, headers=AUTH)
        assert made.status_code == 200, made.text
        _put(client, tmp_path, "gardens", GARDENS)
        assert _found(TestRemote(client, "Sandbox"), "ROSE") == [1, 3, 6]

    class Shelf:
        def catalog(self) -> list[dict[str, str]]:
            return [{"table_name": "gardens", "column_name": "name", "data_type": "VARCHAR"}]

        def rows(self, table: str, **asked: Any) -> tuple[pa.Table, int]:
            assert asked["filters"] is None  # contains is DuckDB's here, over the answer
            return GARDENS, GARDENS.num_rows

    assert _found(adapter.Rows(Shelf(), "Lake"), "rose") == [1, 3, 6]
    source = adapter.OData(dataverse_connect(standin))
    plan = Plan(columns=("name",), filters=(Filter("name", "contains", "ER"),), sort=(("name", False),))
    reader, folded = adapter.read(source, "account", plan)
    wanted = sorted(n for n in made_up._ACCOUNT_NAMES if "er" in n.casefold())
    assert (
        folded.parts == ("filters", "columns", "sort")
        and reader.read_all().column("name").to_pylist() == wanted
    )
    asked = next(r for r in reversed(standin.gets()) if r["path"].endswith("/accounts"))["query"]
    assert asked["$filter"] == "contains(name,'ER')"  # Dataverse compares every string in any case
    wild = Plan(columns=("name",), filters=(Filter("name", "contains", "5_%"),))  # its wildcards: DuckDB's
    assert adapter.read(source, "account", wild)[1].parts == ()
