"""A workbook beside a project's own deliverable (Plans/excel.plan.md: "a workbook is a file any contract.json
may declare"): the contract's checker takes it, and the forms and reconciliation example (a Streamlit project)
emits its monthly workbook from its sandbox with only the scaffold's files beside it. Made-up data only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest
from openpyxl import load_workbook

from swissarmybench import sab_excel
from swissarmybench.adapters import adapter
from swissarmybench.domain import project_contract as contracts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "forms_recon"
STREAMLIT = ROOT / "extensions/streamlit/src/swissarmybench_streamlit/contract.json"
MONTHLY: dict[str, Any] = {
    "path": "workbooks/{slug}.xlsx",
    "owner": "app",
    "about": "The month's reconciliations as a workbook.",
    "made_from": "workbook.py",
    "grows_on": ["month"],
}


def test_any_project_type_may_declare_a_workbook_in_its_contract() -> None:
    raw = json.loads(STREAMLIT.read_text(encoding="utf-8"))
    raw["files"].append(MONTHLY)
    raw["requirements"] = ["openpyxl>=3.1"]
    contract = contracts.read(contracts.write(raw))  # checked, written and read back the same
    assert contracts.workbooks(contract) == ["workbooks/{slug}.xlsx"]
    assert contract["deliverable"] == "a Streamlit app"  # its own deliverable stays what it was
    assert contracts.matches("workbooks/forms_recon_2026_10.xlsx", "workbooks/{slug}.xlsx")
    assert (
        "workbooks/forms_recon.xlsx" not in contracts.scaffold(contract, "Forms recon")["files"]
    )  # made later
    for ident in ("accounting", "powerbi", "powerapps"):  # every packaged type's contract takes one too
        other = json.loads(
            (ROOT / f"extensions/{ident}/src/swissarmybench_{ident}/contract.json").read_text()
        )
        other["files"].append(MONTHLY)
        assert contracts.workbooks(contracts.check(other)) == ["workbooks/{slug}.xlsx"]
    with pytest.raises(contracts.ContractError, match=r"files\[\d+\] is an Excel workbook: it is made"):
        contracts.check(raw | {"files": [MONTHLY | {"starter": "not a workbook"}]})


def sandbox(path: Path) -> None:
    """A made-up sandbox as API.py leaves it: two reconciliations run for October, one of them twice."""
    path.parent.mkdir(parents=True)
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE recon_runs (run_id BIGINT, recon_id VARCHAR, period VARCHAR, ran_at VARCHAR, "
        "matched BIGINT, "
        "differences BIGINT, only_entries BIGINT, only_source BIGINT, duplicates BIGINT, totals VARCHAR)"
    )
    con.execute(
        "CREATE TABLE recon_results (run_id BIGINT, status VARCHAR, record_key VARCHAR, "
        "entry_values VARCHAR, "
        "source_values VARCHAR, difference DOUBLE, fields_off VARCHAR)"
    )
    con.executemany(
        "INSERT INTO recon_runs VALUES (?, ?, ?, '2026-11-01T09:00:00', ?, ?, ?, ?, ?, '[]')",
        [
            (1, "stock_count", "2026-10", 40, 9, 1, 0, 0),  # an earlier run of the month: left out
            (2, "stock_count", "2026-10", 47, 2, 1, 0, 0),
            (3, "supplier_invoices", "2026-10", 30, 0, 0, 1, 0),
            (4, "stock_count", "2026-09", 50, 0, 0, 0, 0),
        ],
    )
    con.executemany(
        "INSERT INTO recon_results VALUES (?, ?, ?, '{}', '{}', ?, ?)",
        [
            (1, "difference", "SKU-0001", 9.0, "quantity"),
            (2, "matched", "SKU-0002", 0.0, ""),
            (2, "difference", "SKU-0007", -3.0, "quantity"),
            (2, "difference", "=SKU-0009", 1.5, "quantity, unit_cost"),
            (2, "only_entries", "SKU-0101", None, ""),
            (3, "only_source", "INV-5001", None, ""),
        ],
    )
    con.close()


def test_the_forms_and_reconciliation_app_emits_its_monthly_workbook_without_the_app(tmp_path: Path) -> None:
    project = tmp_path / "forms_recon"
    sandbox(project / ".sab" / "sandbox" / "sandbox.duckdb")
    (project / "workbook.py").write_bytes((EXAMPLE / "workbook.py").read_bytes())
    # What the project scaffold carries beside it: the adapter and the workbook builder, as they are.
    (project / "adapter.py").write_bytes(Path(adapter.__file__).read_bytes())
    (project / "sab_excel.py").write_bytes(Path(sab_excel.__file__).read_bytes())
    done = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import workbook; workbook.main()",
         "2026-10"],
        cwd=project, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    made = project / "workbooks" / "forms_recon_2026_10.xlsx"
    assert done.stdout.strip() == f"Wrote {made}"
    assert contracts.matches(made.relative_to(project).as_posix(), MONTHLY["path"])
    book = load_workbook(made)
    assert book.sheetnames == ["Summary", "To look at"] and book.properties.title == "Reconciliations 2026-10"
    summary = book["Summary"]
    assert summary["A1"].value == "Reconciliations, 2026-10"
    assert [[c.value for c in row] for row in summary["A3:F6"]] == [
        ["Reconciliation", "matched", "differences", "only_entries", "only_source", "duplicates"],
        ["stock_count", 47, 2, 1, 0, 0],  # the month's latest run, not its first
        ["supplier_invoices", 30, 0, 0, 1, 0],
        ["Total", "=SUM(B4:B5)", "=SUM(C4:C5)", "=SUM(D4:D5)", "=SUM(E4:E5)", "=SUM(F4:F5)"],
    ]
    assert len(summary._charts) == 1 and len(summary.conditional_formatting) == 1
    look = book["To look at"]
    rows = [[c.value for c in row] for row in look.iter_rows(min_row=2)]
    assert [r[:3] for r in rows] == [
        ["stock_count", "difference", "=SKU-0009"],
        ["stock_count", "difference", "SKU-0007"],
        ["stock_count", "only_entries", "SKU-0101"],
        ["supplier_invoices", "only_source", "INV-5001"],
    ]
    assert (
        look["C2"].data_type == "s" and look.auto_filter.ref == "A1:E5"
    )  # a key from the data: never a formula
    missing = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import workbook; workbook.main()",
         "2026-01"],
        cwd=project, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert missing.returncode != 0 and "No reconciliation was run for 2026-01" in missing.stderr
