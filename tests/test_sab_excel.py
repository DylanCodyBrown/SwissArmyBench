"""sab_excel.build: the one way to make a workbook (Plans/excel.plan.md). A plain workbook from grids, a
design's blocks, a template filled, statements; text never a formula; the file runs copied alone, and an
export's workbook.py carries only the parts its design uses. Made-up data only (the Accounting builder's own
tests are tests/test_accounting_workbook.py and tests/test_accounting_statements.py)."""

from __future__ import annotations

import datetime as dt
import decimal
import io
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from openpyxl import Workbook, load_workbook

from swissarmybench import sab_excel
from swissarmybench.adapters import adapter
from swissarmybench.sab_excel import WorkbookError
from swissarmybench_accounting import exporter

ORDERS = pa.table(
    {
        "order_id": [1, 2, 3],
        "region": ["North", "South", "=cmd()"],
        "amount": [120.5, 80.0, 7.25],
        "ordered": [dt.date(2026, 1, 5), dt.date(2026, 2, 1), dt.date(1899, 12, 30)],
    }
)


def opened(data: bytes) -> Workbook:
    return load_workbook(io.BytesIO(data))


# ===== no design: a plain workbook =====


def test_no_design_is_a_plain_workbook_a_sheet_a_grid() -> None:
    book = opened(sab_excel.build({"Orders": ORDERS, "Totals": (["region", "n"], [("North", 1)])}))
    assert book.sheetnames == ["Orders", "Totals"]
    sheet = book["Orders"]
    assert [c.value for c in sheet[1]] == ["order_id", "region", "amount", "ordered"]
    assert sheet["A1"].font.bold and sheet.freeze_panes == "A2" and sheet.auto_filter.ref == "A1:D4"
    assert [c.value for c in sheet[2]] == [1, "North", 120.5, dt.datetime(2026, 1, 5)]
    assert (sheet["B4"].value, sheet["B4"].data_type) == (
        "=cmd()",
        "s",
    )  # text from the data: never a formula
    assert sheet["D4"].value == "1899-12-30"  # before Excel's dates: exact, as text
    assert [c.value for c in book["Totals"][2]] == ["North", 1]


def test_a_reader_from_the_adapter_streams_into_the_workbook_and_reads_back_the_same(tmp_path: Path) -> None:
    path = tmp_path / "out" / "orders.xlsx"
    rows = pa.table({"id": list(range(120_000)), "note": ["made up"] * 120_000})
    assert sab_excel.build({"Rows": rows.to_reader(50_000)}, out=path) == str(path)
    assert not list(path.parent.glob(".*sab-writing"))
    back = adapter.read(adapter.Excel(path), "Rows")[0].read_all()
    assert back.num_rows == 120_000 and back.column("id").to_pylist()[-1] == 119_999


def test_the_plain_rows_written_as_their_own_xml_keep_every_rule(tmp_path: Path) -> None:
    """The plain export writes its data rows' XML itself (openpyxl the rest: 2026-11-22, five times faster):
    each kind read back by openpyxl as openpyxl's own cells were (made-up values)."""
    zone = dt.timezone(dt.timedelta(hours=2))
    rows = pa.table(
        {
            "whole": [7, 10**15, None],
            "number": [1.5, float("nan"), 1e20],
            "text": ["=1+1", " a & <b> ", "ctrl\x01"],
            "flag": [True, False, None],
            "money": pa.array(
                [decimal.Decimal("12.34"), None, decimal.Decimal("-0.01")], pa.decimal128(10, 2)
            ),
            "day": [dt.date(2026, 1, 5), dt.date(1899, 12, 30), None],
            "at": [dt.datetime(2026, 1, 5, 9, 30, 15, 500000), None, dt.datetime(2026, 1, 5, 9)],
            "clock": [dt.time(9, 30), None, dt.time(23, 59, 59)],
            "lasted": [dt.timedelta(hours=30), None, dt.timedelta(0)],
            "listed": [[1, 2], None, []],
            "zoned": pa.array([dt.datetime(2026, 1, 5, 9, tzinfo=zone)] * 3, pa.timestamp("us", tz="+02:00")),
        }
    )
    path = tmp_path / "kinds.xlsx"
    sab_excel.build({"Kinds": rows.to_reader(2)}, out=path)  # a reader's batches, sliced as they come
    sheet = load_workbook(path)["Kinds"]
    got = [[(c.value, c.data_type, c.number_format) for c in row] for row in sheet.iter_rows(min_row=2)]
    assert got[0] == [
        (7, "n", "General"),
        (1.5, "n", "General"),
        ("=1+1", "s", "General"),
        (True, "b", "General"),
        (12.34, "n", "General"),
        (dt.datetime(2026, 1, 5), "d", "yyyy-mm-dd"),
        (dt.datetime(2026, 1, 5, 9, 30, 15, 500000), "d", "yyyy-mm-dd h:mm:ss"),
        (dt.time(9, 30), "d", "h:mm:ss"),
        (dt.timedelta(hours=30), "d", "[hh]:mm:ss"),
        ("[1, 2]", "s", "General"),
        ("2026-01-05T09:00:00+02:00", "s", "General"),
    ]  # fmt: skip  a time with its zone: its ISO text
    # A whole number Excel would round, NaN and a date before Excel's: exact text.
    assert [v for v, _, _ in got[1]][:6] == [
        "1000000000000000",
        "nan",
        " a & <b> ",
        False,
        None,
        "1899-12-30",
    ]
    assert got[2][2][0] == "ctrl_x0001_" and got[2][10][0] == "2026-01-05T09:00:00+02:00"  # a zone: ISO text
    assert (got[2][5][0], got[2][0][0], got[2][3][0]) == (None, None, None)  # blanks stay blank
    assert sheet.dimensions == "A1:K4" and sheet.auto_filter.ref == "A1:K4" and sheet.freeze_panes == "A2"
    assert not list(Path(tempfile.gettempdir()).glob("sab_excel.*.rows.xml"))  # its rows' files gone


def test_notes_are_sheets_of_labelled_lines_and_long_text_is_refused_or_cut() -> None:
    book = opened(sab_excel.build({"Data": ORDERS}, notes={"About": [("Rows", "3"), ("Source", "=made up")]}))
    assert [[c.value for c in row] for row in book["About"].iter_rows()] == [
        ["Rows", "3"],
        ["Source", "=made up"],
    ]
    assert book["About"]["B2"].data_type == "s" and book["About"]["A1"].font.bold
    long = {"Data": pa.table({"t": ["x" * 40_000]})}
    with pytest.raises(WorkbookError, match="Row 1, column t holds 40,000 characters"):
        sab_excel.build(long)
    assert len(opened(sab_excel.build(long, truncate=True))["Data"]["A2"].value) == 32_767
    with pytest.raises(WorkbookError, match="takes its grids by sheet name"):
        sab_excel.build({})


# ===== a design =====

DESIGN: dict[str, Any] = {
    "title": "Made-up report",
    "sheets": [
        {
            "name": "Report",
            "freeze": "A3",
            "blocks": [
                {"id": "t", "kind": "title", "cell": "A1", "text": "Orders"},
                {
                    "id": "orders",
                    "kind": "table",
                    "cell": "A2",
                    "source": {"table": "orders"},
                    "columns": [
                        {"name": "region", "label": "Region"},
                        {"name": "amount", "label": "Amount", "format": "currency", "total": "sum"},
                    ],
                    "total_row": True,
                },
            ],
        }
    ],
}


def test_a_design_lays_the_grids_out_and_the_datas_text_is_never_a_formula(tmp_path: Path) -> None:
    book = opened(sab_excel.build({"orders": ORDERS}, DESIGN))
    sheet = book["Report"]
    assert sheet["A1"].value == "Orders" and sheet["A1"].font.bold and sheet.freeze_panes == "A3"
    assert [c.value for c in sheet[2]] == ["Region", "Amount"]
    assert (sheet["A5"].value, sheet["A5"].data_type) == ("=cmd()", "s")
    assert sheet["B3"].number_format == sab_excel.FORMATS["currency"]
    assert sheet["B6"].value == "=SUM(B3:B5)"  # the total row's own formula stays one
    out = tmp_path / "report.xlsx"
    assert sab_excel.build({"orders": ORDERS}, DESIGN, out=out) == str(out)
    assert load_workbook(out)["Report"]["A2"].value == "Region"


def test_a_tables_columns_may_be_a_form_to_fill_in() -> None:
    design: dict[str, Any] = {
        "sheets": [
            {
                "name": "Data",
                "blocks": [
                    {
                        "id": "form",
                        "kind": "table",
                        "cell": "A1",
                        "source": {"query": "SELECT order_id, region FROM orders WHERE false"},
                        "columns": [
                            {
                                "name": "order_id",
                                "check": "whole",
                                "required": True,
                                "note": "The order's number",
                            },
                            {"name": "region", "choices": ["North", "South"]},
                        ],
                        "entry_rows": 500,
                    }
                ],
            }
        ]
    }
    sheet = opened(sab_excel.build({"orders": ORDERS}, design))["Data"]
    assert sheet["A1"].comment.text == "The order's number"
    assert sheet["A1"].fill.start_color.rgb.endswith(sab_excel.REQUIRED_FILL)
    checks = {str(v.sqref): v for v in sheet.data_validations.dataValidation}
    assert checks["A2:A501"].type == "whole" and checks["A2:A501"].allow_blank is False
    assert checks["B2:B501"].type == "list" and checks["B2:B501"].formula1 == '"North,South"'
    design["sheets"][0]["blocks"][0]["columns"][0]["check"] = "odd"
    with pytest.raises(WorkbookError, match="odd is not a check: whole, number, date"):
        sab_excel.build({"orders": ORDERS}, design)


# ===== a template =====


@pytest.fixture
def template(tmp_path: Path) -> Path:
    book = Workbook()
    sheet = book.active
    sheet.title = "Invoice"
    sheet["A1"], sheet["A2"] = "Invoice", "Customer"
    sheet["A4"], sheet["B4"] = "Item", "Amount"
    sheet["A6"], sheet["B6"] = "Total", "=SUM(B5:B5)"
    path = tmp_path / "invoice.xlsx"
    book.save(path)
    return path


BINDINGS = [
    {"kind": "value", "place": "B1", "value": {"number": True}},
    {"kind": "value", "place": "B2", "value": {"column": "customer"}},
    {"kind": "table", "place": "A5", "columns": ["item", "amount"], "rows": 1},
]
HEADER = (["customer", "month"], [("=Larkfield", "2026-01")])
LINES = (["item", "amount"], [("Desk lamp", 30.0), ("Kettle", 12.5), ("Wok", 40.0)])


def test_a_template_is_filled_once_its_table_growing(template: Path, tmp_path: Path) -> None:
    out = tmp_path / "INV-1001.xlsx"
    design = {"bindings": BINDINGS, "lines": "lines", "number": "INV-1001"}
    assert sab_excel.build({"invoice": HEADER, "lines": LINES}, design, template=template, out=out) == str(
        out
    )
    sheet = load_workbook(out)["Invoice"]
    assert sheet["B1"].value == "INV-1001"
    assert (sheet["B2"].value, sheet["B2"].data_type) == ("=Larkfield", "s")
    assert [[c.value for c in row] for row in sheet["A5:B7"]] == [list(r) for r in LINES[1]]
    assert sheet["A8"].value == "Total" and sheet["B8"].value == "=SUM(B5:B7)"  # the total moved and grew
    data = sab_excel.build({"invoice": HEADER, "lines": LINES}, design, template=template.read_bytes())
    assert opened(data)["Invoice"]["B7"].value == 40.0
    with pytest.raises(WorkbookError, match="filled by its bindings"):
        sab_excel.build({"invoice": HEADER}, {}, template=template)
    with pytest.raises(WorkbookError, match="no grid 'nope' for the lines"):
        sab_excel.build({"invoice": HEADER}, {"bindings": BINDINGS, "lines": "nope"}, template=template)


def test_a_template_with_group_by_is_a_statement_per_group_with_a_register(
    template: Path, tmp_path: Path
) -> None:
    months = (["customer", "month"], [("Larkfield", "2026-01"), ("Ogden", "2026-01")])
    lines = (["customer", "item", "amount"], [("Larkfield", "Desk lamp", 30.0), ("Ogden", "Wok", 40.0)])
    design = {
        "bindings": BINDINGS,
        "lines": "lines",
        "group_by": ["customer"],
        "name": "{customer} {month}.xlsx",
        "number": {"start": 7, "pattern": "INV-{n:03d}"},
        "date": "2026-02-01",
    }
    out = tmp_path / "statements"
    plan = sab_excel.build(
        {"months": months, "lines": lines}, design | {"dry_run": True}, template=template, out=out
    )
    assert [p["file"] for p in plan] == ["Larkfield 2026-01.xlsx", "Ogden 2026-01.xlsx"] and not out.exists()
    sab_excel.build({"months": months, "lines": lines}, design, template=template, out=out)
    assert load_workbook(out / "Ogden 2026-01.xlsx")["Invoice"]["B1"].value == "INV-008"
    header, rows = sab_excel.read_register(out)
    assert len(rows) == 2 and "file" in header
    with pytest.raises(WorkbookError, match="the folder they go in"):
        sab_excel.build({"months": months, "lines": lines}, design, template=template)


# ===== one file, carried =====


def test_the_builder_runs_copied_alone_with_openpyxl_and_duckdb(tmp_path: Path) -> None:
    (tmp_path / "sab_excel.py").write_bytes(Path(sab_excel.__file__).read_bytes())
    probe = (
        "import sys, sab_excel\n"
        "data = sab_excel.build({'Orders': (['id', 'note'], [(1, '=x')])})\n"
        "print(len(data) > 1000, [m for m in sys.modules if m.startswith('swissarmybench')])\n"
    )
    done = subprocess.run(  # noqa: S603 (this Python, made-up rows)
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n{probe}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "True []"


def test_workbook_py_carries_only_the_parts_its_design_uses() -> None:
    text = Path(sab_excel.__file__).read_text(encoding="utf-8")
    plain = exporter.workbook_py(DESIGN, text, ["orders"])
    assert exporter.parts_used(DESIGN) == ["cells", "data", "tables", "design"]
    assert "def build_workbook(" in plain and "def _table(" in plain
    gone = ("pivot_sql", "_chart", "fill_template", "build_statements", "plain_workbook")
    for absent in gone:
        assert f"def {absent}(" not in plain, absent
    compile(plain, "workbook.py", "exec")
    with_pivot = {
        "sheets": [
            {
                "name": "S",
                "blocks": [
                    {"id": "p", "kind": "pivot", "cell": "A1", "source": {"table": "orders"},
                     "rows": ["region"], "values": [{"column": "amount", "agg": "sum"}]},
                    {"id": "c", "kind": "chart", "cell": "E1", "from": "p"},
                ],
            }
        ]
    }  # fmt: skip
    both = exporter.workbook_py(with_pivot, text, ["orders"])
    assert exporter.parts_used(with_pivot) == ["cells", "data", "tables", "design", "pivots", "charts"]
    assert "def pivot_sql(" in both and "def _chart(" in both and "def fill_template(" not in both
    assert len(plain) < len(both) < len(text)
