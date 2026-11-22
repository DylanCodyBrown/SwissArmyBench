"""File connections as a source of the adapter (Plans/adapter.plan.md, phase 3): a CSV, Parquet or JSON file,
or a folder of them, each a table by its path below the folder. A read folds the whole plan (DuckDB over the
file, streamed), query joins the files in DuckDB SQL, a write puts a file in its place whole or adds to it.
Made-up data only."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from swissarmybench.adapters import sab_adapter as sab
from swissarmybench.adapters.sab_adapter import Counts, Filter, Plan, Total


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    shop = tmp_path / "shop"
    (shop / "sales").mkdir(parents=True)
    (shop / "orders.csv").write_text(
        "order_id,customer_id,amount,region\n1,7,12.5,North\n2,8,40.0,South\n3,7,7.5,North\n4,9,1.0,West\n",
        encoding="utf-8",
    )
    pq.write_table(pa.table({"customer_id": [7, 8, 9], "city": ["Springfield", "Shelbyville", "Ogdenville"]}),
                   shop / "customers.parquet")  # fmt: skip
    (shop / "sales" / "events.jsonl").write_text(
        '{"event": "visit", "customer_id": 7}\n{"event": "buy", "customer_id": 8}\n', encoding="utf-8"
    )
    (shop / "notes.md").write_text("not a table", encoding="utf-8")
    return shop


def test_a_folders_files_are_its_tables_with_duckdbs_types(folder: Path) -> None:
    source = sab.source_from(folder, name="Shop files")
    assert isinstance(source, sab.Files)
    listed = {t.name: t for t in sab.tables(source)}
    assert sorted(listed) == ["customers", "orders", "sales/events"]
    assert [(c.name, c.type) for c in listed["orders"].columns] == [
        ("order_id", "BIGINT"), ("customer_id", "BIGINT"), ("amount", "DOUBLE"), ("region", "VARCHAR")
    ]  # fmt: skip
    assert listed["sales/events"].schema == "sales" and listed["customers"].kind == "parquet"


def test_a_read_folds_the_whole_plan(folder: Path) -> None:
    source = sab.Files(str(folder))
    plan = Plan(columns=("order_id",), filters=(Filter("region", "=", "North"),), sort=(("amount", True),))
    reader, folded = sab.read(source, "ORDERS", plan)
    assert folded.parts == ("filters", "columns", "sort")
    assert reader.read_all().column("order_id").to_pylist() == [1, 3]
    totals = Plan(group=("region",), totals=(Total("sum", "amount", "total"),), sort=(("region", False),))
    assert sab.read(source, "orders", totals)[0].read_all().to_pylist()[0] == {
        "region": "North",
        "total": 20.0,
    }
    with pytest.raises(sab.AdapterError, match="has no table 'invoices'"):
        sab.read(source, "invoices")


def test_query_joins_the_files_in_duckdb_sql(folder: Path) -> None:
    db = sab.Connection(sab.Files(str(folder)), "Shop files")
    found = db.query(
        "SELECT c.city, sum(o.amount) AS total FROM orders o JOIN customers c USING (customer_id) "
        "WHERE o.region = ? GROUP BY c.city",
        ["North"],
    )
    assert found.read_all().to_pylist() == [{"city": "Springfield", "total": 20.0}]
    assert db.query("SELECT count(*) AS n FROM sales_events").read_all().to_pylist() == [{"n": 2}]
    with pytest.raises(sab.AdapterError, match="write a file with write"):
        db.query("DELETE FROM orders")


def test_a_file_is_written_whole_or_added_to(folder: Path) -> None:
    source = sab.Files(str(folder))
    fresh = pa.table({"order_id": [9], "customer_id": [8], "amount": [3.0], "region": ["East"]})
    assert sab.write(source, "orders", fresh, mode="truncate") == Counts(inserted=1, deleted=4)
    assert sab.write(source, "orders", fresh) == Counts(inserted=1)
    assert sab.read(source, "orders")[0].read_all().num_rows == 2
    made = sab.write(source, "exports/targets.parquet", pa.table({"region": ["North"], "target": [10.0]}))
    assert made == Counts(inserted=1) and (folder / "exports" / "targets.parquet").exists()
    assert sab.write(source, "orders", mode="truncate") == Counts(deleted=2)
    assert sab.read(source, "orders")[0].read_all().column_names == [
        "order_id",
        "customer_id",
        "amount",
        "region",
    ]
    with pytest.raises(sab.AdapterError, match="one file: it is written whole"):
        sab.write(source, "orders", fresh, ("order_id",), "merge")
    with pytest.raises(sab.AdapterError, match="named with its format"):
        sab.write(source, "exports/plain", fresh)
    assert not list(folder.rglob(".*sab-writing"))  # each written beside, then put in its place


def test_one_file_is_a_source_of_one_table(folder: Path) -> None:
    source = sab.source_from(str(folder / "customers.parquet"))
    assert [t.name for t in sab.tables(source)] == ["customers"]
    assert sab.read(source, "customers", Plan(limit=1))[0].read_all().num_rows == 1
