"""The Accounting extension's one generator (runtime.py): a design built into a workbook, each block kind
read back cell by cell with openpyxl; a pivot against DuckDB's own GROUP BY; Export's workbook.py run in a
fresh Python making the same workbook. Made-up data only (tests/accounting_data.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest
from openpyxl import load_workbook

from swissarmybench_accounting import design as rules
from swissarmybench_accounting import exporter, runtime
from swissarmybench_accounting.runtime import WorkbookError
from tests import accounting_data as made_up


def _design() -> dict[str, Any]:
    return rules.check(
        {
            "title": "Cessions Q1-Q2",
            "sheets": [
                {
                    "name": "Summary",
                    "freeze": "A5",
                    "print": {
                        "orientation": "landscape",
                        "fit_width": True,
                        "footer": "Page &P of &N",
                        "paper": "A4",
                    },
                    "blocks": [
                        {
                            "id": "title",
                            "kind": "title",
                            "cell": "A1",
                            "w": 6,
                            "text": "Made-up Re: cessions",
                        },
                        {
                            "id": "note",
                            "kind": "text",
                            "cell": "A2",
                            "w": 6,
                            "h": 2,
                            "text": "Made-up figures.",
                        },
                        {
                            "id": "list",
                            "kind": "table",
                            "cell": "A5",
                            "source": {"table": "cessions"},
                            "columns": [
                                {"name": "cedant", "width": 22},
                                {"name": "treaty"},
                                {"name": "premium", "format": "currency", "total": "sum"},
                                {"name": "claims", "format": "currency", "total": "sum"},
                                {"name": "loss_ratio", "label": "Loss ratio", "format": "percent"},
                            ],
                            "total_row": True,
                            "conditional": [
                                {"column": "loss_ratio", "op": ">", "value": 0.6, "fill": "#F8D7DA"}
                            ],
                        },
                    ],
                },
                {
                    "name": "Pivot",
                    "blocks": [
                        {
                            "id": "pivot",
                            "kind": "pivot",
                            "cell": "B2",
                            "source": {"query": "SELECT * FROM cessions WHERE premium > 0"},
                            "rows": ["treaty"],
                            "columns": ["period"],
                            "values": [{"column": "premium", "agg": "sum", "format": "number"}],
                        },
                        {
                            "id": "chart",
                            "kind": "chart",
                            "cell": "B10",
                            "chart": "combo",
                            "from": "pivot",
                            "series": ["2026-Q1", "2026-Q2"],
                            "line_series": ["2026-Q2"],
                            "title": "Premium by treaty",
                        },
                        {
                            "id": "pie",
                            "kind": "chart",
                            "cell": "L10",
                            "chart": "pie",
                            "from": "list",
                            "category": "cedant",
                            "series": ["premium"],
                        },
                    ],
                },
            ],
        }
    )


def test_each_block_kind_lands_in_its_cells(tmp_path: Path) -> None:
    out = tmp_path / "cessions.xlsx"
    runtime.build_workbook(_design(), {"cessions": made_up.cessions()}, out)
    book = load_workbook(out)
    assert book.sheetnames == ["Summary", "Pivot"]
    ws = book["Summary"]
    # The title: bold, 16 points, merged across its six columns; the text wraps over two rows.
    assert ws["A1"].value == "Made-up Re: cessions" and ws["A1"].font.bold and ws["A1"].font.sz == 16
    assert "A1:F1" in {str(r) for r in ws.merged_cells.ranges}
    assert "A2:F3" in {str(r) for r in ws.merged_cells.ranges}
    # The table: its labels, its 18 rows, its formats, its totals as Excel's own formulas.
    assert [ws.cell(row=5, column=c).value for c in range(1, 6)] == [
        "cedant",
        "treaty",
        "premium",
        "claims",
        "Loss ratio",
    ]
    data = made_up.cessions()
    assert ws["A6"].value == data.loc[0, "cedant"] and ws["C6"].value == data.loc[0, "premium"]
    assert ws["C6"].number_format == runtime.FORMATS["currency"]
    assert ws["E6"].number_format == "0.0%"
    assert (
        ws["A24"].value == "Total" and ws["C24"].value == "=SUM(C6:C23)" and ws["D24"].value == "=SUM(D6:D23)"
    )
    assert ws["E24"].value is None
    assert ws.column_dimensions["A"].width == 22
    # The colour rule on the loss ratios, the frozen header, the print setup.
    rules_found = list(ws.conditional_formatting)
    assert [str(r.sqref) for r in rules_found] == ["E6:E23"]
    assert ws.freeze_panes == "A5"
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.fitToWidth == 1
    assert ws.oddFooter.center.text == "Page &P of &N"
    # The pivot and its charts: Excel's own (a combo is a column chart with a line on a second axis).
    pivot = book["Pivot"]
    assert [pivot.cell(row=2, column=c).value for c in range(2, 6)] == [
        "treaty",
        "2026-Q1",
        "2026-Q2",
        "Total",
    ]
    assert len(pivot._charts) == 2


def test_the_pivot_is_duckdbs_group_by() -> None:
    con = runtime.connect({"cessions": made_up.cessions()})
    block = {
        "source": {"table": "cessions"},
        "rows": ["cedant"],
        "columns": ["period"],
        "values": [{"column": "claims", "agg": "sum"}, {"column": "loss_ratio", "agg": "average"}],
    }
    shaped = runtime.pivot(con, block)
    assert shaped["header"] == [
        "cedant",
        "2026-Q1 · Sum of claims",
        "2026-Q1 · Average of loss_ratio",
        "2026-Q2 · Sum of claims",
        "2026-Q2 · Average of loss_ratio",
        "Total · Sum of claims",
        "Total · Average of loss_ratio",
    ]
    frame = made_up.cessions()
    check = duckdb.connect()
    check.register("c", frame)
    cells = {
        (c, p): (s, a)
        for c, p, s, a in check.execute(
            "SELECT cedant, period, SUM(claims), AVG(loss_ratio) FROM c GROUP BY ALL"
        ).fetchall()
    }
    by_row = {
        c: (s, a)
        for c, s, a in check.execute(
            "SELECT cedant, SUM(claims), AVG(loss_ratio) FROM c GROUP BY ALL"
        ).fetchall()
    }
    by_col = {
        p: (s, a)
        for p, s, a in check.execute(
            "SELECT period, SUM(claims), AVG(loss_ratio) FROM c GROUP BY ALL"
        ).fetchall()
    }
    grand = check.execute("SELECT SUM(claims), AVG(loss_ratio) FROM c").fetchone()
    for line in shaped["rows"]:
        cedant = line[0]
        assert line[1:3] == pytest.approx(list(cells[(cedant, "2026-Q1")]))
        assert line[3:5] == pytest.approx(list(cells[(cedant, "2026-Q2")]))
        assert line[5:7] == pytest.approx(list(by_row[cedant]))  # an average's total is every row's average
    assert [line[0] for line in shaped["rows"]] == sorted(made_up.CEDANTS)
    assert shaped["total"][0] == "Total"
    assert shaped["total"][1:3] == pytest.approx(list(by_col["2026-Q1"]))
    assert grand is not None and shaped["total"][5:7] == pytest.approx(list(grand))


def test_a_pivot_with_rows_only_and_with_a_count() -> None:
    con = runtime.connect({"cessions": made_up.cessions()})
    shaped = runtime.pivot(
        con, {"source": {"table": "cessions"}, "rows": ["treaty"], "values": [{"agg": "count"}]}
    )
    assert shaped["header"] == ["treaty", "Count"]
    assert all(line[1] == 6 for line in shaped["rows"])
    assert shaped["total"] == ["Total", 18]
    with pytest.raises(WorkbookError, match="sum, count, average"):
        runtime.pivot(
            con,
            {
                "source": {"table": "cessions"},
                "rows": ["treaty"],
                "values": [{"column": "premium", "agg": "median"}],
            },
        )


def test_the_builders_duckdb_reads_no_files(tmp_path: Path) -> None:
    secret = tmp_path / "secret.csv"
    secret.write_text("a\n1\n")
    con = runtime.connect({"cessions": made_up.cessions()})
    with pytest.raises(WorkbookError, match="could not be read"):
        runtime.rows_of(con, {"query": f"SELECT * FROM read_csv('{secret}')"})
    with pytest.raises(WorkbookError):
        runtime.rows_of(con, {"query": "SET enable_external_access = true"})


def test_a_chart_that_shows_nothing_is_said(tmp_path: Path) -> None:
    design = _design()
    design["sheets"][1]["blocks"][1]["category"] = "nope"
    with pytest.raises(WorkbookError, match="Pivot, B10: The chart's category"):
        runtime.build_workbook(design, {"cessions": made_up.cessions()})


def _cells(path: Path) -> dict[str, list[tuple[str, Any, str]]]:
    book = load_workbook(path)
    return {
        ws.title: [
            (c.coordinate, c.value, c.number_format)
            for row in ws.iter_rows()
            for c in row
            if c.value is not None
        ]
        for ws in book.worksheets
    }


def test_exports_workbook_py_builds_the_same_workbook_in_a_fresh_python(tmp_path: Path) -> None:
    design = _design()
    played = tmp_path / "played.xlsx"
    runtime.build_workbook(design, {"cessions": made_up.cessions()}, played)
    project = tmp_path / "project"
    project.mkdir()
    text = exporter.workbook_py(
        design, Path(runtime.__file__).read_text(encoding="utf-8"), rules.tables_read(design)
    )
    (project / "workbook.py").write_text(text, encoding="utf-8")
    # data.py, as the data notebook's export would make it: the same made-up table.
    (project / "data.py").write_text(
        f"import sys\nsys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from tests.accounting_data import cessions as _c\ncessions = _c()\n",
        encoding="utf-8",
    )
    compile(text, "workbook.py", "exec")
    done = subprocess.run(
        [sys.executable, "workbook.py", str(tmp_path / "exported.xlsx")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "swissarmybench" not in text.split("# ===== the builder")[1].split("# ===== the data")[0].replace(
        "Swiss Army Bench", ""
    )
    assert _cells(played) == _cells(tmp_path / "exported.xlsx")
    exported = load_workbook(tmp_path / "exported.xlsx")
    assert len(exported["Pivot"]._charts) == 2
    assert exported["Summary"].freeze_panes == "A5"


def test_workbook_py_says_which_table_data_py_lacks(tmp_path: Path) -> None:
    design = _design()
    text = exporter.workbook_py(design, Path(runtime.__file__).read_text(encoding="utf-8"), ["cessions"])
    (tmp_path / "workbook.py").write_text(text, encoding="utf-8")
    (tmp_path / "data.py").write_text("other = 1\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "workbook.py"], cwd=tmp_path, capture_output=True, text=True, timeout=120
    )
    assert done.returncode != 0 and "data.py does not make cessions" in done.stderr
