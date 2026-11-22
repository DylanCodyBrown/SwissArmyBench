"""The starter pack's Excel and file blades (docs/ideas.md, the starter pack), run on made-up workbooks and
CSV folders in a temporary folder, each result checked with openpyxl or read back. The Excel starters are
three (Plans/excel.plan.md): Read a workbook (the adapter), Make a workbook and Fill a template
(sab_excel)."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from swissarmybench.adapters.blade_run import run_code
from swissarmybench.domain.blades import read_blade

STARTERS = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"


def starter(file: str) -> Any:
    """A starter's function, as sab.blade gives it."""
    blade = read_blade((STARTERS / f"{file}.blade.py").read_text(encoding="utf-8"))
    made, _ = run_code(blade["code"], blade["variable"], {}, blade["name"])
    return made


@pytest.fixture
def book(tmp_path: Path) -> Path:
    """A made-up workbook: a Sales sheet with a header and three rows."""
    path = tmp_path / "sales.xlsx"
    made = Workbook()
    sheet = made.active
    sheet.title = "Sales"
    for row in [
        ["Region", "Amount", "Share"],
        ["North", 1250.5, 0.25],
        ["South", -40, 0.5],
        ["East", 980, 0.25],
    ]:
        sheet.append(row)
    made.save(path)
    return path


def test_read_a_workbook_gives_a_sheet_or_a_range_by_the_adapters_rules(book: Path) -> None:
    read_workbook = starter("excel_read_workbook")
    frame = read_workbook(book, "Sales")
    assert list(frame.columns) == ["Region", "Amount", "Share"] and frame["Amount"].tolist() == [
        1250.5,
        -40.0,
        980.0,
    ]
    assert read_workbook(book)["Region"].tolist() == ["North", "South", "East"]  # the only sheet
    part = read_workbook(book, "Sales", cells="A1:B3", columns=["Amount"], limit=1)
    assert part.to_dict("records") == [{"Amount": 1250.5}]
    with pytest.raises(ValueError, match=r"no sheet or named table .Nope.\. It has: Sales"):
        read_workbook(book, "Nope")


def test_make_a_workbook_plain_or_by_a_design(tmp_path: Path) -> None:
    make_workbook = starter("excel_make_workbook")
    frame = pd.DataFrame(
        {
            "region": ["North", "=South"],
            "amount": [1250.5, -40.0],
            "day": pd.to_datetime(["2026-01-02", "2026-01-03"]),
        }
    )
    plain = tmp_path / "new" / "sales.xlsx"
    assert make_workbook(plain, {"Orders": frame}) == str(plain)
    sheet = load_workbook(plain)["Orders"]
    assert [c.value for c in sheet[1]] == ["region", "amount", "day"] and sheet.freeze_panes == "A2"
    assert (sheet["A3"].value, sheet["A3"].data_type) == (
        "=South",
        "s",
    )  # text from the data, never a formula
    design = {
        "sheets": [
            {
                "name": "Report",
                "freeze": "A3",
                "blocks": [
                    {"id": "t", "kind": "title", "cell": "A1", "text": "Sales", "w": 3},
                    {
                        "id": "orders",
                        "kind": "table",
                        "cell": "A2",
                        "source": {"table": "orders"},
                        "total_row": True,
                        "filter": True,
                        "columns": [
                            {"name": "region", "width": 20},
                            {"name": "amount", "format": "currency", "total": "sum"},
                        ],
                        "conditional": [{"column": "amount", "op": "<", "value": 0}],
                    },
                ],
            }
        ]
    }
    laid = tmp_path / "report.xlsx"
    make_workbook(laid, {"orders": frame}, design)
    sheet = load_workbook(laid)["Report"]
    # What the cell-level starters did, as the design's options: merged cells, a number format, a width, a
    # total, a colour rule, freeze panes, a filter.
    assert "A1:C1" in {str(r) for r in sheet.merged_cells.ranges} and sheet.freeze_panes == "A3"
    assert sheet["B3"].number_format.startswith('"$"') and sheet.column_dimensions["A"].width == 20
    assert sheet["B5"].value == "=SUM(B3:B4)" and sheet.auto_filter.ref == "A2:B4"
    assert len(sheet.conditional_formatting) == 1


def test_fill_a_template_keeps_the_template_and_grows_its_table(tmp_path: Path) -> None:
    fill_template = starter("excel_fill_template")
    template = tmp_path / "invoice.xlsx"
    made = Workbook()
    sheet = made.active
    sheet.title = "Invoice"
    sheet["A1"], sheet["A3"], sheet["B3"] = "Customer", "Item", "Amount"
    sheet["A5"], sheet["B5"] = "Total", "=SUM(B4:B4)"
    made.save(template)
    out = tmp_path / "out" / "INV-1001.xlsx"
    places = [
        {"kind": "value", "place": "B1", "value": {"column": "customer"}},
        {"kind": "value", "place": "C1", "value": {"number": True}},
        {"kind": "table", "place": "A4", "columns": ["item", "amount"], "rows": 1},
    ]
    lines = pd.DataFrame({"item": ["Desk lamp", "Kettle"], "amount": [30.0, 12.5]})
    assert fill_template(template, out, places, {"customer": "Larkfield Goods"}, lines, "INV-1001") == str(
        out
    )
    filled = load_workbook(out)["Invoice"]
    assert [filled["B1"].value, filled["C1"].value] == ["Larkfield Goods", "INV-1001"]
    assert [[c.value for c in row] for row in filled["A4:B5"]] == [["Desk lamp", 30.0], ["Kettle", 12.5]]
    assert filled["B6"].value == "=SUM(B4:B5)"
    assert load_workbook(template)["Invoice"]["B1"].value is None  # the template itself is never changed


def test_the_cell_level_starters_names_answer_with_where_their_effect_is_now(tmp_path: Path) -> None:
    from swissarmybench.adapters.blades import BladeStore
    from swissarmybench.domain.blade_templates import GONE_STARTERS
    from swissarmybench.domain.blades import BladeError

    store = BladeStore(tmp_path / "library", starters=STARTERS)
    assert len(GONE_STARTERS) == 12
    for old in GONE_STARTERS:
        with pytest.raises(BladeError, match=r"went with the one Excel module: it is now .*Excel"):
            store.get(old.upper())
    assert store.get("excel make a workbook").variable == "make_workbook"
    with pytest.raises(KeyError):
        store.get("Excel no such starter")


@pytest.fixture
def csv_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "daily"
    folder.mkdir()
    (folder / "orders_2026-01-01.csv").write_text(
        "id,region,amount\n1,North,10.5\n2,South,7\n", encoding="utf-8"
    )
    (folder / "orders_2026-01-02.csv").write_text("id,region,amount,note\n3,North,4,late\n", encoding="utf-8")
    (folder / "readme.txt").write_text("not a csv", encoding="utf-8")
    return folder


def test_combine_csvs_lines_columns_up_by_name(csv_folder: Path) -> None:
    combined = starter("files_combine_csvs")(csv_folder)
    assert combined.columns.tolist() == ["source_file", "id", "region", "amount", "note"]
    assert combined["id"].tolist() == [1, 2, 3]
    assert combined["source_file"].tolist() == ["orders_2026-01-01.csv"] * 2 + ["orders_2026-01-02.csv"]
    assert pd.isna(combined.loc[0, "note"]) and combined.loc[2, "note"] == "late"
    with pytest.raises(ValueError, match="No file in"):
        starter("files_combine_csvs")(csv_folder, "*.parquet")


def test_split_csv_one_file_per_value(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text("id;region;amount\n1;North;10\n2;South;7\n3;North;4\n4;;1\n", encoding="utf-8")
    written = starter("files_split_csv")(source, "region")
    folder = tmp_path / "orders_by_region"
    assert written == [
        str(folder / n) for n in ("orders_North.csv", "orders_South.csv", "orders_(blank).csv")
    ]
    assert (folder / "orders_North.csv").read_text(encoding="utf-8").splitlines() == [
        "id;region;amount",
        "1;North;10",
        "3;North;4",
    ]
    with pytest.raises(ValueError, match="already exists: pass overwrite=True"):
        starter("files_split_csv")(source, "region")
    with pytest.raises(ValueError, match=r"no column .city.\. It has: id, region, amount"):
        starter("files_split_csv")(source, "city", overwrite=True)


def test_change_a_files_delimiter_or_encoding(tmp_path: Path) -> None:
    source = tmp_path / "legacy.csv"
    source.write_bytes('id,city,note\n1,Zürich,"a, b"\n'.encode("cp1252"))
    convert = starter("files_change_delimiter_or_encoding")
    with pytest.raises(ValueError, match="not utf-8-sig text"):
        convert(source, tmp_path / "out.csv")
    out = convert(source, tmp_path / "out.csv", delimiter=";", from_encoding="cp1252")
    assert Path(out).read_text(encoding="utf-8").splitlines() == ["id;city;note", "1;Zürich;a, b"]
    with pytest.raises(ValueError, match="already exists"):
        convert(source, tmp_path / "out.csv", from_encoding="cp1252")
    with pytest.raises(ValueError, match="the source is never changed"):
        convert(source, source, from_encoding="cp1252", overwrite=True)


SIGNATURES = {
    "excel_read_workbook": "(path: str | Path, sheet: str = '', header_row: int = 1, cells: str = '', "
    "columns: list[str] | None = None, limit: int | None = None) -> Any",
    "excel_make_workbook": "(path: str | Path, tables: dict[str, Any], "
    "design: dict[str, Any] | None = None) -> str",
    "excel_fill_template": "(template: str | Path, path: str | Path, places: list[dict[str, Any]], "
    "values: Any = None, lines: Any = None, number: Any = None) -> str",
    "files_combine_csvs": "(folder: str | Path, pattern: str = '*.csv', recursive: bool = False, "
    "source_column: str | None = 'source_file', delimiter: str | None = None, "
    "encoding: str = 'utf-8-sig') -> pd.DataFrame",
    "files_split_csv": "(path: str | Path, column: str, folder: str | Path | None = None, "
    "overwrite: bool = False, encoding: str = 'utf-8-sig') -> list[str]",
    "files_change_delimiter_or_encoding": "(path: str | Path, out: str | Path, delimiter: str = ',', "
    "encoding: str = 'utf-8', from_delimiter: str | None = None, from_encoding: str = 'utf-8-sig', "
    "overwrite: bool = False) -> str",
}


@pytest.mark.parametrize("file", sorted(SIGNATURES))
def test_each_is_a_function_as_its_first_lines_say(file: str) -> None:
    text = (STARTERS / f"{file}.blade.py").read_text(encoding="utf-8")
    made = starter(file)
    assert str(inspect.signature(made)).replace("'", "") == SIGNATURES[file].replace("'", "")
    blade = read_blade(text)
    assert f'{made.__name__} = sab.blade("{blade["name"]}")' in text
