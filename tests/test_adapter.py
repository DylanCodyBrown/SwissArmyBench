"""adapter (src/swissarmybench/adapters/adapter.py), the one adapter every data call goes through
(Plans/adapter.plan.md): the plan, the DuckDB source (a file, a connection), what a source could not fold done
over the stream, writes by mode, JSON pages made Arrow with given types, grids as named Arrow tables, and the
file being one an export can copy as it is. Made-up data only."""

from __future__ import annotations

import ast
import contextlib
import datetime
import decimal
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter as sab
from swissarmybench.adapters.adapter import Filter, Plan, Total

ADAPTER = Path(sab.__file__)


@pytest.fixture
def shop(tmp_path: Path) -> str:
    path = tmp_path / "shop.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, region VARCHAR, amount DECIMAL(10,2), placed DATE)"
    )
    con.execute(
        "INSERT INTO orders VALUES (1, 'North', 12.50, DATE '2026-01-03'), (2, 'South', 40.00, "
        "DATE '2026-01-04'), (3, 'North', 7.25, DATE '2026-02-01'), (4, 'East', 99.99, NULL)"
    )
    con.execute("CREATE SCHEMA stock")
    con.execute("CREATE TABLE stock.items (sku VARCHAR, qty INTEGER)")
    con.execute("CREATE VIEW north AS SELECT * FROM orders WHERE region = 'North'")
    con.close()
    return str(path)


# ===== the plan =====


def test_a_plan_is_one_duckdb_query_with_its_values_bound() -> None:
    plan = Plan(
        columns=("id", "amount"),
        filters=(Filter("region", "in", ["North", "East"]), Filter("amount", ">=", 10)),
        sort=(("amount", True),),
        limit=2,
        offset=1,
    )
    sql, params = sab.plan_sql('"orders"', plan)
    assert sql == (
        'SELECT "id", "amount" FROM "orders" WHERE "region" IN (?, ?) AND "amount" >= ? '
        'ORDER BY "amount" DESC LIMIT 2 OFFSET 1'
    )
    assert params == ["North", "East", 10]
    grouped = Plan(group=("region",), totals=(Total("sum", "amount"), Total("count")))
    assert sab.plan_sql("t", grouped)[0] == (
        'SELECT "region", sum("amount") AS "sum_amount", count(*) AS "count" FROM t GROUP BY "region"'
    )


def test_a_plan_from_json_is_checked_and_goes_back_the_same() -> None:
    plan = sab.plan_from(
        {
            "columns": ["id"],
            "filters": [["region", "=", "North"], ["placed", "is null"]],
            "sort": [["id", "desc"]],
            "limit": 5,
            "totals": [],
        }
    )
    assert plan.filters == (Filter("region", "=", "North"), Filter("placed", "is null", None))
    assert sab.plan_from(plan.to_json()) == plan
    for bad, said in (
        ({"filters": [["a", "~", 1]]}, "op is one of"),
        ({"filters": [["a", "between", [1]]]}, "takes two values"),
        ({"limit": -1}, "whole number"),
        ({"totals": [{"fn": "median", "column": "a"}]}, "total is one of"),
        ({"group": ["a"]}, "names its totals"),
    ):
        with pytest.raises(sab.AdapterError, match=said):
            sab.plan_from(bad)


# ===== the DuckDB source =====


def test_a_duckdb_file_lists_its_tables_with_types_and_keys(shop: str) -> None:
    listed = {t.name: t for t in sab.tables(sab.DuckDB.file(shop))}
    assert sorted(listed) == ["north", "orders", "stock.items"]
    assert listed["orders"].columns[0] == sab.Column("id", "INTEGER", True)
    assert [c.type for c in listed["orders"].columns[1:]] == ["VARCHAR", "DECIMAL(10,2)", "DATE"]


def test_a_read_folds_the_whole_plan_and_streams_typed_batches(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    reader, folded = sab.read(
        source, "ORDERS", Plan(filters=(Filter("region", "=", "North"),), sort=(("id", False),))
    )
    assert folded.parts == ("filters", "sort")
    table = reader.read_all()
    assert table.column("id").to_pylist() == [1, 3]
    assert table.column("amount").to_pylist() == [decimal.Decimal("12.50"), decimal.Decimal("7.25")]
    assert table.column("placed").to_pylist()[0] == datetime.date(2026, 1, 3)
    totals, _ = sab.read(
        source, "orders", Plan(group=("region",), totals=(Total("count"),), sort=(("region", False),))
    )
    assert totals.read_all().to_pylist() == [
        {"region": "East", "count": 1},
        {"region": "North", "count": 2},
        {"region": "South", "count": 1},
    ]
    assert sab.read(source, "stock.items")[0].read_all().num_rows == 0


def test_a_read_names_what_the_table_does_not_have(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    with pytest.raises(sab.AdapterError, match="has no table 'invoices'"):
        sab.read(source, "invoices")
    with pytest.raises(sab.AdapterError, match="orders has no column 'colour'"):
        sab.read(source, "orders", Plan(columns=("colour",)))


def test_a_connection_someone_opened_is_read_through_a_cursor_of_its_own(shop: str) -> None:
    con = duckdb.connect(shop, read_only=True)
    reader, _ = sab.read(sab.DuckDB.over(con), "north", Plan(columns=("id",)))
    assert reader.read_all().column("id").to_pylist() == [1, 3]
    assert con.sql("SELECT count(*) FROM orders").fetchall() == [(4,)]  # still open, still the caller's
    con.close()


def test_the_reader_keeps_its_connection_only_while_it_is_read(shop: str) -> None:
    opened: list[str] = []

    @contextlib.contextmanager
    def connect(writing: bool) -> Iterator[Any]:
        con = duckdb.connect(shop, read_only=True)
        opened.append("open")
        try:
            yield con
        finally:
            con.close()
            opened.append("closed")

    reader, _ = sab.read(sab.DuckDB(connect), "orders")
    assert opened == ["open"]
    reader.read_all()
    assert opened == ["open", "closed"]
    dropped, _ = sab.read(sab.DuckDB(connect), "orders")
    del dropped
    assert opened[-1] == "closed"


# ===== what a source could not fold =====


class Unfolding:
    """A source that folds only what it is told it can (made-up rows)."""

    def __init__(self, folds: tuple[str, ...]) -> None:
        self.folds = folds
        self.asked: list[sab.Plan] = []

    def tables(self) -> list[sab.Table]:
        return [sab.Table("letters")]

    def read(self, table: str, plan: Plan) -> tuple[pa.RecordBatchReader, sab.Folded]:
        self.asked.append(plan)
        rows = pa.table({"n": list(range(10)), "letter": list("abcdefghij")})
        return rows.to_reader(max_chunksize=3), sab.Folded(tuple(p for p in plan.parts() if p in self.folds))

    def write(self, table: str, batches: pa.RecordBatchReader, key: Any, mode: str) -> sab.Counts:
        return sab.Counts(inserted=batches.read_all().num_rows)


def test_what_a_source_could_not_fold_is_done_over_the_stream() -> None:
    plan = Plan(filters=(Filter("n", ">", 2),), columns=("letter",), sort=(("n", True),), limit=3)
    reader, folded = sab.read(Unfolding(()), "letters", plan)
    assert folded.parts == ()
    assert reader.read_all().column("letter").to_pylist() == ["j", "i", "h"]


def test_a_source_that_folds_a_later_part_alone_is_refused() -> None:
    with pytest.raises(sab.AdapterError, match="in the order SQL applies them"):
        sab.read(Unfolding(("limit",)), "letters", Plan(filters=(Filter("n", ">", 2),), limit=3))


def test_a_name_is_found_by_what_use_was_given() -> None:
    source = Unfolding(())
    sab.use(lambda name: source if name == "Letters" else sab.DuckDB.file("/nowhere"))
    try:
        assert sab.tables("Letters") == [sab.Table("letters")]
        assert sab.write("Letters", "letters", pa.table({"n": [1, 2]})).inserted == 2
    finally:
        sab.use(None)
    with pytest.raises(sab.AdapterError, match="No source is named 'Letters'"):
        sab.tables("Letters")


# ===== writes =====


def _ids(path: str) -> list[tuple[Any, ...]]:
    con = duckdb.connect(path, read_only=True)
    try:
        return con.sql("SELECT id, region, amount FROM orders ORDER BY id").fetchall()
    finally:
        con.close()


def test_each_write_mode_counts_its_rows(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    new = pa.table({"id": [5], "region": ["West"], "amount": [1.5]})
    assert sab.write(source, "orders", new) == sab.Counts(inserted=1)
    changed = pa.table({"id": [1, 9], "amount": [13.0, 1.0]})
    assert sab.write(source, "orders", changed, key=("id",), mode="update") == sab.Counts(updated=1)
    both = pa.table({"id": [2, 6], "region": ["South", "West"], "amount": [41.0, 2.0]})
    assert sab.write(source, "orders", both, key=["id"], mode="merge") == sab.Counts(inserted=1, updated=1)
    gone = pa.table({"id": [3, 4, 99]})
    assert sab.write(source, "orders", gone, key=["id"], mode="delete") == sab.Counts(deleted=2)
    assert [r[0] for r in _ids(shop)] == [1, 2, 5, 6]
    assert _ids(shop)[0][2] == decimal.Decimal("13.00")


def test_a_write_that_fails_writes_nothing(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    clash = pa.table({"id": [7, 1], "region": ["West", "North"], "amount": [1.0, 1.0]})
    with pytest.raises(duckdb.ConstraintException):
        sab.write(source, "orders", clash)
    assert [r[0] for r in _ids(shop)] == [1, 2, 3, 4]
    with pytest.raises(sab.AdapterError, match="names the key"):
        sab.write(source, "orders", clash, mode="update")
    with pytest.raises(sab.AdapterError, match="mode is one of"):
        sab.write(source, "orders", clash, mode="upsert")


def test_a_truncate_with_no_rows_clears_the_table_and_keeps_its_columns(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    assert sab.write(source, "orders", mode="truncate") == sab.Counts(deleted=4)
    assert _ids(shop) == []
    listed = {t.name: t for t in sab.tables(source)}["orders"]
    assert [c.name for c in listed.columns] == ["id", "region", "amount", "placed"]
    with pytest.raises(sab.AdapterError, match="takes the rows"):
        sab.write(source, "orders", mode="insert")


def test_a_truncate_with_rows_clears_and_inserts_all_or_none(shop: str) -> None:
    source = sab.DuckDB.file(shop)
    fresh = pa.table({"id": [10, 11], "region": ["West", "East"], "amount": [1.0, 2.0]})
    assert sab.write(source, "orders", fresh, mode="truncate") == sab.Counts(inserted=2, deleted=4)
    assert [r[0] for r in _ids(shop)] == [10, 11]
    clash = pa.table({"id": [12, 12], "region": ["West", "West"], "amount": [1.0, 1.0]})
    with pytest.raises(duckdb.ConstraintException):
        sab.write(source, "orders", clash, mode="truncate")
    assert [r[0] for r in _ids(shop)] == [10, 11]  # nothing cleared: one transaction
    empty = pa.table({"id": pa.array([], pa.int32()), "region": pa.array([], pa.string())})
    assert sab.write(source, "orders", empty, mode="truncate") == sab.Counts(deleted=2)


# ===== JSON pages =====


def test_json_pages_become_arrow_with_the_types_given() -> None:
    pages: list[Any] = [
        json.dumps([{"id": 1, "amount": "12.5", "when": "2026-01-02", "extra": True}]),
        [{"id": "2"}],  # a page missing fields keeps the types
    ]
    reader = sab.from_json(pages, {"id": "BIGINT", "amount": "DECIMAL(10,2)", "when": "DATE"})
    assert reader.schema.names == ["id", "amount", "when"]
    batches = list(reader)
    assert len(batches) == 2
    table = pa.Table.from_batches(batches)
    assert table.to_pylist() == [
        {"id": 1, "amount": decimal.Decimal("12.50"), "when": datetime.date(2026, 1, 2)},
        {"id": 2, "amount": None, "when": None},
    ]


def test_json_pages_take_the_first_pages_types_when_none_are_given() -> None:
    reader = sab.from_json([b'[{"id": 1, "name": "Ada"}]', b'[{"id": 2}]'])
    assert reader.read_all().to_pylist() == [{"id": 1, "name": "Ada"}, {"id": 2, "name": None}]
    assert sab.from_json([]).read_all().num_rows == 0


def test_strict_json_refuses_a_value_of_the_wrong_type() -> None:
    with pytest.raises(sab.AdapterError, match="numerical"):
        sab.from_json(['[{"id": "seven"}]'], {"id": "INTEGER"}, strict=True).read_all()
    assert sab.from_json(['[{"id": "seven"}]'], {"id": "INTEGER"}).read_all().to_pylist() == [{"id": None}]
    with pytest.raises(sab.AdapterError, match="is not a DuckDB type"):
        sab.from_json(["[]"], {"id": "INTEGER); DROP TABLE x; --"})


# ===== tables =====


def test_a_table_is_made_on_first_use_kept_and_read_again_on_refresh(shop: str) -> None:
    made = sab.Tables()
    made.define(
        "by_region",
        sab.DuckDB.file(shop),
        "orders",
        Plan(filters=(Filter("placed", "is not null"),)),
        f"SELECT region, sum(amount) AS total FROM {sab.ROWS} GROUP BY 1 ORDER BY 1",  # noqa: S608
    )
    first = made.table("by_region")
    assert first.to_pylist() == [
        {"region": "North", "total": decimal.Decimal("19.75")},
        {"region": "South", "total": decimal.Decimal("40.00")},
    ]
    assert made.table("by_region") is first
    sab.write(sab.DuckDB.file(shop), "orders", pa.table({"id": [8], "region": ["West"], "amount": [3.0],
              "placed": [datetime.date(2026, 3, 1)]}))  # fmt: skip
    assert made.table("by_region") is first  # kept until a page asks
    assert made.refresh("by_region").num_rows == 3
    made.drop("by_region")
    with pytest.raises(sab.AdapterError, match="No table is named"):
        made.table("by_region")


# ===== one file, copied as it is =====


def test_the_adapter_imports_only_the_standard_library_duckdb_and_pyarrow() -> None:
    import sys

    found: set[str] = set()
    for node in ast.walk(ast.parse(ADAPTER.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.level == 0, "no relative import: an export copies this file alone"
            found.add(node.module.split(".")[0])
    # openpyxl (1.4.0): only inside the Excel source's functions, when a workbook is read or written.
    assert found - set(sys.stdlib_module_names) == {"duckdb", "pyarrow", "openpyxl"}
    at_import = {
        (a.name if isinstance(n, ast.Import) else n.module or "").split(".")[0]
        for n in ast.parse(ADAPTER.read_text(encoding="utf-8")).body
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in n.names
    }
    assert at_import - set(sys.stdlib_module_names) == {"duckdb", "pyarrow"}


def test_the_adapter_runs_copied_alone(tmp_path: Path, shop: str) -> None:
    import subprocess
    import sys

    (tmp_path / "adapter.py").write_bytes(ADAPTER.read_bytes())
    probe = (
        f"import adapter as a; r, f = a.read(a.DuckDB.file({shop!r}), 'orders', a.Plan(limit=2)); "
        "print(r.read_all().num_rows, f.parts)"
    )
    done = subprocess.run(  # noqa: S603 (this Python, a made-up file)
        [sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "2 ('limit',)"


# ===== memory stays flat =====

MEASURE = """
import sys
import duckdb
import adapter as sab

def rss():
    with open("/proc/self/status") as f:
        return next(int(line.split()[1]) // 1024 for line in f if line.startswith("VmRSS"))

path = sys.argv[1]
con = duckdb.connect(path)
con.execute(
    "CREATE TABLE lines AS SELECT range AS id, range % 97 AS product, (range % 1000) / 10.0 AS amount, "
    "'note ' || (range % 13) AS note FROM range(3000000)"
)
con.close()

def peak(plan):
    base, most, rows = rss(), 0, 0
    reader, _ = sab.read(sab.DuckDB.file(path), "lines", plan)
    for batch in reader:
        rows += batch.num_rows
        most = max(most, rss() - base)
        del batch
    return most, rows

folded, n = peak(sab.Plan(filters=(sab.Filter("product", "=", 5),), limit=20000))
streamed, every = peak(sab.Plan())
base = rss()
held = sab.read(sab.DuckDB.file(path), "lines")[0].read_all()
print(folded, n, streamed, every, rss() - base, held.nbytes // 2**20)
"""


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="reads the process's memory from /proc")
def test_a_read_streams_and_never_holds_the_table(tmp_path: Path) -> None:
    """Three million made-up lines in a DuckDB file, read in a process of its own: a read with a filter and a
    limit folded grows the process by little, and every row streamed far less than the same rows held."""
    import subprocess
    import sys

    (tmp_path / "adapter.py").write_bytes(ADAPTER.read_bytes())
    done = subprocess.run(  # noqa: S603 (this Python, made-up rows)
        [sys.executable, "-c", MEASURE, str(tmp_path / "lines.duckdb")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    folded, n, streamed, every, held, arrow = (int(v) for v in done.stdout.split())
    assert n == 20_000 and every == 3_000_000
    assert folded < 64, done.stdout  # MB: DuckDB's own buffers, never the table
    assert streamed < held / 2, done.stdout
    assert arrow > 50  # the table as Arrow is this big, held whole
