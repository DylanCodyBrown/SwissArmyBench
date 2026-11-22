"""Templates from existing workbooks and the statements built from them (the Accounting extension's
runtime.py and templates.py): a made-up reinsurer's statement template, its places bound, a table that
grows (formulas, merged cells and named ranges below it moved), the dry run, the build, the numbering and
the register. Made-up data only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.workbook.defined_name import DefinedName

from swissarmybench import sab_excel as runtime
from swissarmybench.sab_excel import WorkbookError
from swissarmybench_accounting import templates as rules
from swissarmybench_accounting.templates import TemplateError
from tests import accounting_data as made_up


def make_template(path: Path) -> Path:
    """A statement as a made-up reinsurer keeps one: its header, a line area of one row, totals under it,
    a remittance note merged across, named ranges."""
    book = Workbook()
    ws = book.active
    ws.title = "Statement"
    ws["A1"] = "Made-up Re"
    ws["A1"].font = Font(bold=True, size=18)
    ws["A3"], ws["A4"], ws["E3"], ws["E4"] = "Cedant:", "Period:", "No.:", "Date:"
    ws["F4"].number_format = "dd mmm yyyy"
    for i, name in enumerate(["Treaty", "Premium", "Claims", "Commission", "Balance"], start=1):
        ws.cell(row=11, column=i, value=name).font = Font(bold=True)
    for col in "BCDE":
        ws[f"{col}12"].number_format = '"$"#,##0.00'
    ws["A13"] = "Total"
    for col in "BCDE":
        ws[f"{col}13"] = f"=SUM({col}12:{col}12)"
    ws["A15"] = "Please remit the balance within 30 days."
    ws.merge_cells("A15:E15")
    for name, ref in {"Cedant": "$B$3", "Period": "$B$4", "StatementDate": "$F$4", "Remit": "$A$15"}.items():
        book.defined_names[name] = DefinedName(name, attr_text=f"Statement!{ref}")
    book.save(path)
    return path


BINDINGS: list[dict[str, Any]] = [
    {"kind": "value", "place": "Cedant", "value": {"column": "cedant"}},
    {"kind": "value", "place": "Period", "value": {"column": "period"}},
    {"kind": "value", "place": "Statement!F3", "value": {"number": True}},
    {"kind": "value", "place": "StatementDate", "value": {"date": True}, "format": "keep"},
    {
        "kind": "table",
        "place": "Statement!A12",
        "columns": ["treaty", "premium", "claims", "commission", "balance"],
    },
]


def test_bindings_are_checked() -> None:
    checked = rules.check_bindings({"template": "statement.xlsx", "bindings": BINDINGS})
    assert checked["bindings"][4] == {
        "kind": "table",
        "place": "Statement!A12",
        "columns": ["treaty", "premium", "claims", "commission", "balance"],
        "rows": 1,
        "grow": True,
    }
    assert rules.columns_needed(checked) == (
        ["cedant", "period"],
        ["treaty", "premium", "claims", "commission", "balance"],
    )
    rebound = rules.bind(checked, {"kind": "value", "place": "cedant", "value": {"text": "To {cedant}"}})
    assert [b["place"] for b in rebound["bindings"]][-1] == "cedant" and len(rebound["bindings"]) == 5
    assert len(rules.unbind(rebound, "Period")["bindings"]) == 4
    with pytest.raises(TemplateError, match="not a place"):
        rules.check_binding({"kind": "value", "place": "../x", "value": {"column": "a"}})
    with pytest.raises(TemplateError, match="bound once"):
        rules.check_bindings({"bindings": [BINDINGS[0], BINDINGS[0]]})
    with pytest.raises(TemplateError, match="one name"):
        rules.check_build({"template": "statement", "data": "statements", "name": "../{cedant}.xlsx"})


def test_a_template_filled_keeps_its_layout_and_its_table_grows(tmp_path: Path) -> None:
    template = make_template(tmp_path / "statement.xlsx")
    frame = made_up.lines()
    mine = frame[(frame["cedant"] == "Brindle Assurance") & (frame["period"] == "2026-Q1")]
    cols = ["treaty", "premium", "claims", "commission", "balance"]
    lines = (cols, [tuple(r) for r in mine[cols].itertuples(index=False)])
    import datetime as dt

    book = runtime.fill_template(
        template,
        BINDINGS,
        {"cedant": "Brindle Assurance", "period": "2026-Q1"},
        lines,
        "ST-0007",
        dt.date(2026, 4, 2),
    )
    ws = book["Statement"]
    assert ws["A1"].value == "Made-up Re" and ws["A1"].font.bold  # the fixed text and its look
    assert (
        ws["B3"].value == "Brindle Assurance" and ws["B4"].value == "2026-Q1" and ws["F3"].value == "ST-0007"
    )
    assert (
        ws["F4"].value.date() == dt.date(2026, 4, 2)
        if hasattr(ws["F4"].value, "date")
        else ws["F4"].value == dt.date(2026, 4, 2)
    )
    assert ws["F4"].number_format == "dd mmm yyyy"  # kept
    # Three lines in a one-row area: two rows inserted, the totals under it moved and made longer.
    assert [ws.cell(row=r, column=1).value for r in (12, 13, 14)] == list(mine["treaty"])
    assert (
        ws["A15"].value == "Total"
        and ws["B15"].value == "=SUM(B12:B14)"
        and ws["E15"].value == "=SUM(E12:E14)"
    )
    assert ws["B14"].number_format == '"$"#,##0.00'  # the area's style on the new rows
    assert "A17:E17" in {str(r) for r in ws.merged_cells.ranges} and ws["A17"].value.startswith(
        "Please remit"
    )
    assert list(book.defined_names["Remit"].destinations) == [("Statement", "$A$17")]
    assert list(book.defined_names["Cedant"].destinations) == [("Statement", "$B$3")]


def test_build_statements_dry_run_first_then_the_files_and_the_register(tmp_path: Path) -> None:
    template = make_template(tmp_path / "statement.xlsx")
    (tmp_path / "statement.bind.json").write_text(__import__("json").dumps({"bindings": BINDINGS}))
    out = tmp_path / "out"
    args: dict[str, Any] = {
        "group_by": ["cedant", "period"],
        "out_folder": out,
        "name": "{cedant} {period}.xlsx",
        "number": {"start": 7, "pattern": "ST-{n:04d}"},
        "date": "2026-04-02",
    }
    plan = runtime.build_statements(template, made_up.statements(), made_up.lines(), **args)
    assert not out.exists()  # a dry run writes nothing
    assert len(plan) == 6
    first = plan[0]
    assert (
        first["file"] == "Ashgrove Mutual 2026-Q1.xlsx"
        and first["number"] == "ST-0007"
        and first["rows"] == 3
    )
    lines = made_up.lines()
    mine = lines[(lines["cedant"] == "Ashgrove Mutual") & (lines["period"] == "2026-Q1")]
    assert first["totals"]["premium"] == pytest.approx(mine["premium"].sum())
    assert [p["number"] for p in plan] == [f"ST-{n:04d}" for n in range(7, 13)]
    built = runtime.build_statements(template, made_up.statements(), made_up.lines(), dry_run=False, **args)
    assert built == plan
    files = sorted(p.name for p in out.iterdir())
    assert files == sorted([p["file"] for p in plan] + ["register.csv"])
    ws = load_workbook(out / "Quillon Insurance 2026-Q2.xlsx")["Statement"]
    assert ws["B3"].value == "Quillon Insurance" and ws["F3"].value == "ST-0012"
    header, rows = runtime.read_register(out)
    assert header[:3] == ["file", "sheet", "group"] and len(rows) == 6
    assert rows[0][2] == "Ashgrove Mutual · 2026-Q1"
    # Nothing is written over unless asked.
    with pytest.raises(WorkbookError, match="there already"):
        runtime.build_statements(template, made_up.statements(), made_up.lines(), dry_run=False, **args)


def test_one_workbook_a_sheet_per_group(tmp_path: Path) -> None:
    template = make_template(tmp_path / "statement.xlsx")
    plan = runtime.build_statements(
        template,
        made_up.statements(),
        made_up.lines(),
        group_by=["cedant", "period"],
        out_folder=tmp_path / "out",
        bindings=BINDINGS,
        name="{cedant} {period}",
        one_workbook=True,
        dry_run=False,
    )
    book = load_workbook(tmp_path / "out" / plan[0]["file"])
    assert book.sheetnames == [p["sheet"] for p in plan]
    assert book["Brindle Assurance 2026-Q2"]["B3"].value == "Brindle Assurance"
    assert book["Brindle Assurance 2026-Q2"]["A15"].value == "Total"


def test_a_name_that_names_a_missing_column_is_said(tmp_path: Path) -> None:
    template = make_template(tmp_path / "statement.xlsx")
    with pytest.raises(WorkbookError, match="names 'treaty'"):
        runtime.build_statements(
            template,
            made_up.statements(),
            None,
            group_by=["cedant"],
            bindings=BINDINGS[:2],
            name="{treaty}.xlsx",
        )
