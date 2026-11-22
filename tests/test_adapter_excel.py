"""An Excel workbook as a source of the adapter (Plans/excel.plan.md): a path, an upload's bytes or a
SharePoint document's bytes; its sheets and named tables are its tables, a read gives Arrow by one set of
type rules, a write puts rows into a sheet (added or replaced) with the other sheets kept. Made-up data
only."""

from __future__ import annotations

import io
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table as NamedTable

from swissarmybench.adapters import adapter as sab
from swissarmybench.adapters.adapter import Counts, Filter, Plan

ADAPTER = Path(sab.__file__)


def workbook(sheets: dict[str, list[list[object]]], named: dict[str, tuple[str, str]] | None = None) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    for name, (sheet_name, ref) in (named or {}).items():
        book[sheet_name].add_table(NamedTable(displayName=name, ref=ref))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


ORDERS = [
    ["order_id", "region", "amount", "ordered", "paid"],
    [1, "North", 120.5, datetime(2026, 1, 5), True],
    [2, "South", 80, datetime(2026, 2, 1), False],
    [None, None, None, None, None],  # a blank row inside the data: kept
    [4, "North", 7.25, datetime(2026, 2, 9), True],
    [None, None, None, None, None],  # blank rows after the data: dropped
]


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "shop.xlsx"
    path.write_bytes(
        workbook(
            {
                "Orders": ORDERS,
                "Report": [
                    ["Made-up report", None, None],
                    [None, None, None],
                    [None, "city", "people"],
                    [None, "Springfield", 30],
                    [None, "Shelbyville", 12],
                ],
            },
            {"Cities": ("Report", "B3:C5")},
        )
    )
    return path


# ===== tables: its sheets and its named tables =====


def test_a_workbooks_sheets_and_named_tables_are_its_tables(book: Path) -> None:
    source = sab.source_from(book, name="Shop workbook")
    assert isinstance(source, sab.Excel)
    listed = {t.name: t for t in sab.tables(source)}
    assert list(listed) == ["Orders", "Report", "Cities"]
    assert [(c.name, c.type) for c in listed["Orders"].columns] == [
        ("order_id", "BIGINT"), ("region", "VARCHAR"), ("amount", "DOUBLE"), ("ordered", "TIMESTAMP"),
        ("paid", "BOOLEAN"),
    ]  # fmt: skip
    assert listed["Orders"].kind == "sheet" and listed["Cities"].kind == "named table"
    assert "Report" in listed["Cities"].description and "B3:C5" in listed["Cities"].description
    assert [c.name for c in listed["Cities"].columns] == ["city", "people"]


def test_bytes_are_a_workbook_too(book: Path) -> None:
    source = sab.source_from(book.read_bytes(), name="An upload")
    assert isinstance(source, sab.Excel)
    assert [t.name for t in source.tables()] == ["Orders", "Report", "Cities"]
    reader, _ = sab.read(source, "Cities")
    assert reader.read_all().to_pylist() == [
        {"city": "Springfield", "people": 30},
        {"city": "Shelbyville", "people": 12},
    ]


# ===== read: one set of type rules =====


def test_a_sheet_reads_with_its_header_and_types(book: Path) -> None:
    reader, folded = sab.read(sab.Excel(book), "orders")  # a name in any case
    table = reader.read_all()
    assert folded.parts == ()
    assert table.column_names == ["order_id", "region", "amount", "ordered", "paid"]
    assert [str(t) for t in table.schema.types] == ["int64", "string", "double", "timestamp[us]", "bool"]
    assert table.column("order_id").to_pylist() == [1, 2, None, 4]
    assert table.column("amount").to_pylist() == [120.5, 80.0, None, 7.25]
    assert table.column("ordered").to_pylist()[3] == datetime(2026, 2, 9)


def test_mixed_columns_become_text_and_headers_are_made_unique() -> None:
    data = workbook({"Sheet": [["code", None, "Code", None], [42, "x", 1, None], ["n/a", "y", 2, None]]})
    table = sab.read(sab.Excel(data), "Sheet")[0].read_all()
    assert table.column_names == [
        "code",
        "column_2",
        "Code_2",
    ]  # a column with no name and no value: left out
    assert table.column("code").to_pylist() == ["42", "n/a"]
    assert table.column("Code_2").to_pylist() == [1, 2]


def test_a_column_that_changes_kind_far_down_is_text_whole() -> None:
    rows: list[list[object]] = [["n", "m"]] + [[i, i] for i in range(60_000)] + [["oops", 1.5]]
    table = sab.read(sab.Excel(workbook({"Big": rows})), "Big")[0].read_all()
    assert table.num_rows == 60_001
    assert table.column("n").to_pylist()[-2:] == ["59999", "oops"]
    assert str(table.schema.field("m").type) == "double" and table.column("m").to_pylist()[-1] == 1.5


def test_the_plan_is_folded_where_a_sheet_can_and_duckdb_does_the_rest(book: Path) -> None:
    source = sab.Excel(book)
    reader, folded = sab.read(source, "Orders", Plan(columns=("region", "amount"), limit=2))
    assert folded.parts == ("columns", "limit")
    assert reader.read_all().to_pylist() == [
        {"region": "North", "amount": 120.5},
        {"region": "South", "amount": 80.0},
    ]
    reader, folded = sab.read(
        source, "Orders", Plan(filters=(Filter("region", "=", "North"),), sort=(("amount", True),))
    )
    assert folded.parts == ()
    assert reader.read_all().column("order_id").to_pylist() == [1, 4]
    blank_third = sab.read(source, "Orders", Plan(limit=3))[0].read_all()
    assert blank_third.column("order_id").to_pylist() == [1, 2, None]  # the blank row inside counts
    with pytest.raises(sab.AdapterError, match="Orders has no column 'nope'"):
        sab.read(source, "Orders", Plan(columns=("nope",)))


def test_a_header_row_and_a_range_of_cells_say_where_the_table_is(book: Path) -> None:
    by_range = sab.read(sab.Excel(book, cells="B3:C5"), "Report")[0].read_all()
    assert by_range.to_pylist() == [
        {"city": "Springfield", "people": 30},
        {"city": "Shelbyville", "people": 12},
    ]
    by_row = sab.read(sab.Excel(book, header_row=3), "Report")[0].read_all()
    assert by_row.column_names == ["city", "people"]


def test_what_cannot_be_read_is_said_in_one_sentence(book: Path, tmp_path: Path) -> None:
    with pytest.raises(sab.AdapterError, match=r"no sheet or named table 'Nope'.*Orders, Report, Cities"):
        sab.read(sab.Excel(book), "Nope")
    with pytest.raises(sab.AdapterError, match=r"3 tables \(Orders, Report, Cities\): name the one to read"):
        sab.read(sab.Excel(book), "")
    fake = tmp_path / "fake.xlsx"
    fake.write_text("not a zip file", encoding="utf-8")
    with pytest.raises(sab.AdapterError, match="as an Excel workbook"):
        sab.tables(sab.Excel(fake))
    with pytest.raises(sab.AdapterError, match="reaches no file"):
        sab.tables(sab.Excel(tmp_path / "gone.xlsx"))
    with pytest.raises(sab.AdapterError, match="is empty"):
        sab.read(sab.Excel(workbook({"Blank": []})), "Blank")
    assert sab.read(sab.Excel(workbook({"One": [["a"], [1]]})), "")[0].read_all().to_pylist() == [{"a": 1}]


# ===== write: rows into a sheet, the others kept =====


def test_a_truncate_replaces_one_sheet_and_keeps_the_others(book: Path) -> None:
    rows = pa.table({"city": ["Ogdenville"], "people": [9], "since": [date(2026, 3, 1)]})
    counts = sab.write(sab.Excel(book), "Orders", rows, mode="truncate")
    assert counts == Counts(inserted=1, deleted=4)
    made = load_workbook(book)
    assert made.sheetnames == ["Orders", "Report"]
    assert [[c.value for c in r] for r in made["Orders"].iter_rows()] == [
        ["city", "people", "since"],
        ["Ogdenville", 9, datetime(2026, 3, 1)],
    ]
    assert made["Report"]["A1"].value == "Made-up report"
    assert not list(book.parent.glob(".*sab-writing"))


def test_an_insert_adds_below_by_the_headers_names_and_makes_a_new_sheet_or_workbook(tmp_path: Path) -> None:
    path = tmp_path / "new" / "out.xlsx"
    source = sab.Excel(path)
    assert sab.write(source, "Sales", pa.table({"region": ["North"], "amount": [1.5]})) == Counts(inserted=1)
    assert sab.write(source, "Sales", pa.table({"amount": [2.5], "region": ["South"]})) == Counts(inserted=1)
    assert sab.write(source, "Notes", pa.table({"note": ["made up"]})) == Counts(inserted=1)
    assert sab.read(source, "Sales")[0].read_all().to_pylist() == [
        {"region": "North", "amount": 1.5},
        {"region": "South", "amount": 2.5},
    ]
    assert [t.name for t in source.tables()] == ["Sales", "Notes"]
    with pytest.raises(sab.AdapterError, match="Sales has no column 'city'"):
        sab.write(source, "Sales", pa.table({"city": ["x"]}))
    with pytest.raises(sab.AdapterError, match=r"added to \(insert\) or replaced \(truncate\)"):
        sab.write(source, "Sales", pa.table({"region": ["x"]}), key=("region",), mode="merge")


def test_a_write_keeps_text_as_text_long_numbers_exact_and_early_dates_true(tmp_path: Path) -> None:
    path = tmp_path / "safe.xlsx"
    rows = pa.table(
        {
            "text": ["=1+1", "+cmd", "plain"],
            "id": [12345678901234567890 % 2**63, 7, None],
            "day": [date(1899, 12, 30), date(2026, 1, 2), None],
            "at": pa.array([datetime(2026, 1, 2, 3, 4), None, None], pa.timestamp("us", tz="Europe/Paris")),
        }
    )
    sab.write(sab.Excel(path), "Data", rows, mode="truncate")
    sheet = load_workbook(path)["Data"]
    assert [sheet["A2"].value, sheet["A2"].data_type] == ["=1+1", "s"]  # never a formula
    assert sheet["A3"].data_type == "s"
    assert sheet["B2"].value == str(12345678901234567890 % 2**63) and sheet["B3"].value == 7
    assert sheet["C2"].value == "1899-12-30" and sheet["C3"].value == datetime(2026, 1, 2)
    assert sheet["D2"].value == "2026-01-02T04:04:00+01:00"  # Excel has no zones: the offset kept as text


def test_bytes_written_are_the_sources_new_bytes(book: Path) -> None:
    source = sab.Excel(book.read_bytes(), "An upload")
    sab.write(source, "Extra", pa.table({"n": [1, 2]}))
    assert load_workbook(io.BytesIO(source.data)).sheetnames == ["Orders", "Report", "Extra"]
    assert load_workbook(book).sheetnames == ["Orders", "Report"]


# ===== openpyxl only when a workbook is used =====


def test_openpyxl_is_imported_only_when_a_workbook_is_used_and_missing_is_said_plainly(
    book: Path, tmp_path: Path
) -> None:
    (tmp_path / "adapter.py").write_bytes(ADAPTER.read_bytes())
    probe = (
        "import sys, adapter as a\n"
        "assert 'openpyxl' not in sys.modules\n"
        f"source = a.Excel({str(book)!r})\n"
        "print(len(source.tables()), 'openpyxl' in sys.modules)\n"
        "sys.modules['openpyxl'] = None\n"
        "try:\n"
        "    a.read(source, 'Orders')\n"
        "except ModuleNotFoundError as error:\n"
        "    print(error.name, '|', error)\n"
    )
    done = subprocess.run(  # noqa: S603 (this Python, a made-up workbook)
        [sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    first, second = done.stdout.strip().splitlines()
    assert first == "3 True"
    assert second.startswith("openpyxl | An Excel workbook is read and written with openpyxl")
    assert "pip install openpyxl" in second
