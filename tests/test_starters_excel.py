"""The starter pack's Excel and file blades (docs/ideas.md, the starter pack), run on made-up workbooks and
CSV folders in a temporary folder, each result checked with openpyxl or read back."""

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


def test_add_sheet_makes_the_workbook_and_never_replaces_a_sheet_unasked(tmp_path: Path, book: Path) -> None:
    add_sheet = starter("excel_add_sheet")
    new = tmp_path / "new" / "report.xlsx"
    assert add_sheet(new, "Summary") == str(new)
    assert load_workbook(new).sheetnames == ["Summary"]
    add_sheet(book, "Cover", index=0)
    assert load_workbook(book).sheetnames == ["Cover", "Sales"]
    with pytest.raises(ValueError, match="already has a sheet 'Sales': pass overwrite=True"):
        add_sheet(book, "Sales")
    add_sheet(book, "Sales", overwrite=True)
    again = load_workbook(book)
    assert again.sheetnames == ["Cover", "Sales"] and again["Sales"]["A1"].value is None
    with pytest.raises(ValueError, match="not an Excel workbook"):
        add_sheet(tmp_path / "notes.txt", "Sheet")


def test_set_values_by_cell_or_as_rows(book: Path) -> None:
    set_values = starter("excel_set_cell_values")
    set_values(book, "Sales", {"E1": "Note", "E2": "made up", "B5": "=SUM(B2:B4)"})
    set_values(book, "Sales", [["West", 300], ["Central", 12]], start="A6")
    sheet = load_workbook(book)["Sales"]
    assert [sheet["E1"].value, sheet["E2"].value, sheet["B5"].value] == ["Note", "made up", "=SUM(B2:B4)"]
    assert [[c.value for c in row] for row in sheet["A6:B7"]] == [["West", 300], ["Central", 12]]
    with pytest.raises(ValueError, match=r"no sheet .Nope.\. It has: Sales"):
        set_values(book, "Nope", {"A1": 1})


def test_write_table_writes_a_frame_and_keeps_what_is_there_unless_asked(tmp_path: Path) -> None:
    write_table = starter("excel_write_table")
    frame = pd.DataFrame(
        {
            "region": ["North", "South"],
            "amount": [1250.5, None],
            "day": pd.to_datetime(["2026-01-02", "2026-01-03"]),
        }
    )
    path = tmp_path / "out.xlsx"
    write_table(path, "Orders", frame, start="B2")
    sheet = load_workbook(path)["Orders"]
    assert [c.value for c in sheet[2]][1:] == ["region", "amount", "day"]
    assert sheet["B3"].value == "North" and sheet["C3"].value == 1250.5 and sheet["C4"].value is None
    assert sheet["D3"].value.year == 2026
    with pytest.raises(ValueError, match=r"Orders!B2 already holds a value: pass overwrite=True"):
        write_table(path, "Orders", frame, start="B2")
    write_table(path, "Orders", frame.assign(region=["West", "East"]), start="B2", overwrite=True)
    assert load_workbook(path)["Orders"]["B3"].value == "West"


def test_borders_on_every_cell_or_the_outline(book: Path) -> None:
    borders = starter("excel_borders")
    borders(book, "Sales", "A1:C1")
    borders(book, "Sales", "A2:C4", style="thick", where="outline")
    sheet = load_workbook(book)["Sales"]
    assert {sheet["B1"].border.left.style, sheet["B1"].border.top.style} == {"thin"}
    assert sheet["A2"].border.left.style == "thick" and sheet["A2"].border.top.style == "thick"
    assert sheet["B3"].border.left.style is None and sheet["B3"].border.top.style is None  # inside
    assert sheet["C4"].border.right.style == "thick" and sheet["C4"].border.bottom.style == "thick"
    with pytest.raises(ValueError, match="style is one of thin"):
        borders(book, "Sales", "A1", style="wavy")


def test_fonts_and_fills_keep_what_is_not_given(book: Path) -> None:
    style_cells = starter("excel_fonts_and_fills")
    style_cells(book, "Sales", "A1:C1", bold=True, fill="DDEBF7")
    style_cells(book, "Sales", "A1", color="#C00000", size=14)
    sheet = load_workbook(book)["Sales"]
    assert (
        sheet["A1"].font.bold
        and sheet["A1"].font.size == 14
        and sheet["A1"].font.color.rgb.endswith("C00000")
    )
    assert sheet["B1"].font.bold and sheet["B1"].fill.fgColor.rgb.endswith("DDEBF7")
    assert not sheet["A2"].font.bold


def test_number_formats_by_name_or_code(book: Path) -> None:
    number_format = starter("excel_number_formats")
    number_format(book, "Sales", "B2:B4", "money")
    number_format(book, "Sales", "C2:C4", "percent")
    number_format(book, "Sales", "A2", "0.000")
    sheet = load_workbook(book)["Sales"]
    assert sheet["B3"].number_format == "#,##0.00" and sheet["C2"].number_format == "0.0%"
    assert sheet["A2"].number_format == "0.000"


def test_autofit_widens_columns_to_their_longest_value(book: Path) -> None:
    starter("excel_set_cell_values")(book, "Sales", {"A6": "A much longer made-up region name"})
    starter("excel_autofit_columns")(book)
    sheet = load_workbook(book)["Sales"]
    assert sheet.column_dimensions["A"].width == len("A much longer made-up region name") + 2
    assert sheet.column_dimensions["C"].width == 7  # "Share" (5) + 2
    starter("excel_autofit_columns")(book, "Sales", max_width=10)
    assert load_workbook(book)["Sales"].column_dimensions["A"].width == 10


def test_freeze_merge_conditional_colours_and_a_table(book: Path) -> None:
    starter("excel_freeze_panes")(book, "Sales", "B2")
    starter("excel_merge_cells")(book, "Sales", "E1:G1", "Made-up title")
    starter("excel_conditional_colours")(book, "Sales", "B2:B4", "<", 0)
    starter("excel_conditional_colours")(book, "Sales", "C2:C4", "between", 0.2, 0.3, fill="C6EFCE")
    starter("excel_range_as_table")(book, "Sales", "A1:C4", "Sales")
    sheet = load_workbook(book)["Sales"]
    assert sheet.freeze_panes == "B2"
    assert [str(r) for r in sheet.merged_cells.ranges] == ["E1:G1"] and sheet["E1"].value == "Made-up title"
    assert sheet["E1"].alignment.horizontal == "center"
    rules = {str(r.sqref): r.rules[0] for r in sheet.conditional_formatting}
    assert rules["B2:B4"].operator == "lessThan" and rules["B2:B4"].formula == ["0"]
    assert rules["C2:C4"].operator == "between" and rules["C2:C4"].formula == ["0.2", "0.3"]
    assert sheet.tables["Sales"].ref == "A1:C4"
    with pytest.raises(ValueError, match="already has a table named 'Sales'"):
        starter("excel_range_as_table")(book, "Sales", "A1:C4", "Sales")
    with pytest.raises(ValueError, match="between needs both ends"):
        starter("excel_conditional_colours")(book, "Sales", "C2:C4", "between", 1)


def test_copy_template_never_writes_over_unasked(tmp_path: Path, book: Path) -> None:
    copy_template = starter("excel_copy_template")
    out = tmp_path / "invoices" / "invoice-0001.xlsx"
    assert copy_template(book, out) == str(out)
    assert load_workbook(out)["Sales"]["A2"].value == "North"
    with pytest.raises(ValueError, match="already exists: pass overwrite=True"):
        copy_template(book, out)
    copy_template(book, out, overwrite=True)
    with pytest.raises(ValueError, match="no template"):
        copy_template(tmp_path / "missing.xlsx", tmp_path / "x.xlsx")


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
    "excel_add_sheet": "(path: str | Path, sheet: str, index: int | None = None, "
    "overwrite: bool = False) -> str",
    "excel_set_cell_values": "(path: str | Path, sheet: str, values: dict[str, Any] | list[list[Any]], "
    "start: str = 'A1') -> str",
    "excel_write_table": "(path: str | Path, sheet: str, frame: pd.DataFrame, start: str = 'A1', "
    "header: bool = True, overwrite: bool = False) -> str",
    "excel_borders": "(path: str | Path, sheet: str, cells: str, style: str = 'thin', where: str = 'all', "
    "color: str = '000000') -> str",
    "excel_fonts_and_fills": "(path: str | Path, sheet: str, cells: str, bold: bool | None = None, "
    "italic: bool | None = None, size: float | None = None, color: str | None = None, "
    "fill: str | None = None) -> str",
    "excel_number_formats": "(path: str | Path, sheet: str, cells: str, format: str = 'money') -> str",
    "excel_autofit_columns": "(path: str | Path, sheet: str | None = None, min_width: float = 6, "
    "max_width: float = 60) -> str",
    "excel_freeze_panes": "(path: str | Path, sheet: str, cell: str | None = 'A2') -> str",
    "excel_merge_cells": "(path: str | Path, sheet: str, cells: str, value: Any = None, "
    "center: bool = True) -> str",
    "excel_conditional_colours": "(path: str | Path, sheet: str, cells: str, rule: str, value: Any, "
    "upper: Any = None, fill: str = 'FFC7CE', text: str = '9C0006') -> str",
    "excel_range_as_table": "(path: str | Path, sheet: str, cells: str | None, name: str, "
    "style: str = 'TableStyleMedium2') -> str",
    "excel_copy_template": "(template: str | Path, path: str | Path, overwrite: bool = False) -> str",
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


def test_the_shared_part_is_the_same_in_every_excel_starter() -> None:
    def shared(text: str) -> str:
        start = text.index("# ===== opening and saving a workbook")
        return text[start : text.index("# ===== this starter =====")]

    assert len({shared(p.read_text(encoding="utf-8")) for p in STARTERS.glob("excel_*.blade.py")}) == 1
