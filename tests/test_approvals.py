"""Approved outputs (docs/ideas.md, lineage with values and approved outputs, 2026-11-15): a cell's
output marked approved; a later run that differs says how (a text diff; for a table its shape and the
changed cells, capped); the approvals kept in the notebook's metadata; the headless run's
--check-approved, its report and its exit code. Made-up data only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from swissarmybench.client import standalone
from swissarmybench.domain import approvals as rules
from swissarmybench.domain import notebooks

ORDERS = pd.DataFrame({"region": ["East", "West", "North"], "amount": [100, 250, 40]})


def shown(value: Any) -> dict[str, Any]:
    """What a kernel sends for a cell whose last line is `value` (IPython's own forms)."""
    data: dict[str, Any] = {"text/plain": repr(value)}
    if hasattr(value, "_repr_html_"):
        data["text/html"] = value._repr_html_()
    return {"output_type": "execute_result", "data": data, "metadata": {}, "execution_count": 3}


def printed(text: str) -> dict[str, Any]:
    return {"output_type": "stream", "name": "stdout", "text": text}


# ===== a snapshot of a cell's outputs =====


def test_a_snapshot_reads_printed_text_and_a_table_from_its_html() -> None:
    snap = rules.snapshot([printed("Loaded 3 orders\n"), shown(ORDERS)])
    assert snap["text"] == "Loaded 3 orders"
    [table] = snap["tables"]
    assert table["columns"] == ["", "region", "amount"]  # the index's own column first
    assert table["rows"][1] == ["1", "West", "250"]
    assert table["shape"] == [3, 2]
    assert snap["error"] is None


def test_a_long_table_is_kept_to_its_first_rows_but_its_shape_is_whole() -> None:
    many = pd.DataFrame({"n": range(500), "twice": [i * 2 for i in range(500)]})
    snap = rules.snapshot([shown(many)])
    [table] = snap["tables"]
    assert table["shape"] == [500, 2]
    assert len(table["rows"]) <= rules.MAX_ROWS


def test_memory_addresses_and_counts_do_not_make_a_difference() -> None:
    one = rules.snapshot([printed("<object at 0x7f00aa>\n"), shown(3)])
    two = rules.snapshot([printed("<object at 0x7f99bb>\n"), shown(3) | {"execution_count": 9}])
    assert rules.compare(rules.approval(one), two) is None


def test_an_error_and_a_picture_are_part_of_the_output() -> None:
    error = {"output_type": "error", "ename": "KeyError", "evalue": "'amount'", "traceback": []}
    picture = {"output_type": "display_data", "data": {"image/png": "iVBORw0KGgo="}, "metadata": {}}
    snap = rules.snapshot([picture, error])
    assert snap["error"] == "KeyError: 'amount'"
    assert len(snap["drawings"]) == 1


# ===== the comparison =====


def test_the_same_output_is_no_difference() -> None:
    first = rules.snapshot([shown(ORDERS)])
    assert rules.compare(rules.approval(first), rules.snapshot([shown(ORDERS.copy())])) is None


def test_a_changed_cell_and_a_lost_row_are_said_exactly() -> None:
    approved = rules.approval(rules.snapshot([shown(ORDERS)]))
    later = ORDERS.copy()
    later.loc[1, "amount"] = 260
    later = later.iloc[:2]
    diff = rules.compare(approved, rules.snapshot([shown(later)]))
    assert diff is not None
    [table] = diff["tables"]
    assert table["shape"] == [[3, 2], [2, 2]]
    assert {"row": 1, "column": "amount", "was": "250", "now": "260"} in table["cells"]
    lines = rules.summary(diff)
    assert "rows: 3 → 2" in lines
    assert "row 1, amount: 250 → 260" in lines


def test_columns_added_and_removed_are_named() -> None:
    approved = rules.approval(rules.snapshot([shown(ORDERS)]))
    later = ORDERS.rename(columns={"amount": "total"}).assign(tax=[1, 2, 3])
    diff = rules.compare(approved, rules.snapshot([shown(later)]))
    assert diff is not None
    [table] = diff["tables"]
    assert table["added"] == ["total", "tax"] and table["removed"] == ["amount"]


def test_many_changed_cells_are_capped_and_counted() -> None:
    before = pd.DataFrame({"n": range(40)})
    after = pd.DataFrame({"n": range(100, 140)})
    diff = rules.compare(rules.approval(rules.snapshot([shown(before)])), rules.snapshot([shown(after)]))
    assert diff is not None
    [table] = diff["tables"]
    assert len(table["cells"]) == rules.MAX_CHANGES
    assert table["more"] == 40 - rules.MAX_CHANGES


def test_text_that_changed_is_a_line_diff() -> None:
    approved = rules.approval(rules.snapshot([printed("total 390\nregions 3\n")]))
    diff = rules.compare(approved, rules.snapshot([printed("total 400\nregions 3\n")]))
    assert diff is not None
    assert "-total 390" in diff["text"] and "+total 400" in diff["text"]


def test_an_error_where_there_was_none_is_said() -> None:
    approved = rules.approval(rules.snapshot([shown(3)]))
    error = {"output_type": "error", "ename": "NameError", "evalue": "name 'x' is not defined"}
    diff = rules.compare(approved, rules.snapshot([error]))
    assert diff is not None and diff["error"] == {"was": None, "now": "NameError: name 'x' is not defined"}


def test_an_approval_without_its_rows_still_tells_a_change() -> None:
    """A zip keeps an approval's mark and shapes, never its rows (no rows leave in a zip)."""
    full = rules.approval(rules.snapshot([shown(ORDERS)]))
    kept = rules.without_rows(full)
    assert "rows" not in json.dumps(kept["snapshot"]["tables"])
    assert "East" not in json.dumps(kept)
    assert rules.compare(kept, rules.snapshot([shown(ORDERS)])) is None
    diff = rules.compare(kept, rules.snapshot([shown(ORDERS.iloc[:1])]))
    assert diff is not None and "rows: 3 → 1" in rules.summary(diff)


def test_an_approval_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="approval"):
        rules.check_approval({"snapshot": "nope"})
    assert rules.check_approval(None) is None


def test_the_comparison_module_is_standard_library_only_and_stands_alone() -> None:
    """It can be inlined into an exported notebook or script (branch one-script)."""
    source = Path(rules.__file__).read_text(encoding="utf-8")
    assert "swissarmybench" not in source.split('"""', 2)[2]  # imports nothing of the package
    imported = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert all(line.split()[1].split(".")[0] in sys.stdlib_module_names | {"__future__"} for line in imported)


# ===== kept in the notebook's metadata =====


def test_an_approval_is_kept_in_the_cells_metadata_both_ways() -> None:
    approval = rules.approval(rules.snapshot([shown(ORDERS)]), "2026-11-15T09:00:00")
    cell = notebooks.Cell("code", "orders", number=4, approved=approval)
    text = notebooks.write_notebook([cell])
    raw = json.loads(text)["cells"][0]["metadata"]["swissarmybench"]
    assert raw["approved"]["at"] == "2026-11-15T09:00:00"
    [back] = notebooks.read_notebook(text)
    assert back.approved == approval
    [sent] = notebooks.read_cells([{"kind": "code", "source": "orders", "approved": approval}])
    assert sent.approved == approval


# ===== the headless run: --check-approved =====


def _approved_notebook(path: Path, first: str, run_now: str) -> None:
    """A notebook whose second cell's output was approved when `first` made it; it now runs `run_now`."""
    approved = rules.approval(rules.snapshot([printed(first)]))
    cells = [
        notebooks.Cell("code", "total = 390", number=1),
        notebooks.Cell("code", run_now, number=2, approved=approved),
        notebooks.Cell("markdown", "# Notes", number=3),
    ]
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")


def test_the_headless_run_passes_when_every_approved_output_is_the_same(tmp_path: Path) -> None:
    book = tmp_path / "check.ipynb"
    _approved_notebook(book, "total 390\n", "print('total', total)")
    report: list[str] = []
    assert standalone.run_notebook(book, check_approved=True, say=report.append) == 0
    assert any("1 approved output" in line for line in report)


def test_the_headless_run_fails_with_a_report_when_an_output_changed(tmp_path: Path) -> None:
    book = tmp_path / "check.ipynb"
    _approved_notebook(book, "total 390\n", "print('total', total + 10)")
    report: list[str] = []
    assert standalone.run_notebook(book, check_approved=True, say=report.append) == 1
    said = "\n".join(report)
    assert "@cell2" in said and "Changed since approved" in said
    assert "+total 400" in said


def test_the_headless_run_from_the_command_line_exits_non_zero(tmp_path: Path) -> None:
    book = tmp_path / "check.ipynb"
    _approved_notebook(book, "total 390\n", "print('total', 1)")
    done = subprocess.run(  # noqa: S603 (this Python, the package's own module)
        [sys.executable, "-m", "swissarmybench.client.standalone", str(book), "--check-approved"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert done.returncode == 1, done.stderr
    assert "Changed since approved" in done.stdout


def test_a_cell_that_fails_in_the_headless_run_is_an_exit_code_too(tmp_path: Path) -> None:
    book = tmp_path / "broken.ipynb"
    cells = [notebooks.Cell("code", "raise ValueError('made-up failure')", number=1)]
    book.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    report: list[str] = []
    assert standalone.run_notebook(book, check_approved=False, say=report.append) == 1
    assert any("ValueError: made-up failure" in line for line in report)


def test_a_projects_zip_keeps_an_approvals_marks_but_none_of_its_rows() -> None:
    from swissarmybench_streamlit.services.streamlit import StreamlitApps

    approved = rules.approval(rules.snapshot([shown(ORDERS), printed("made-up East total\n")]))
    cells = [notebooks.Cell("code", "orders", number=1, outputs=[shown(ORDERS)], approved=approved)]
    zipped = StreamlitApps._for_zip("sales.ipynb", notebooks.write_notebook(cells))
    assert "East" not in zipped and "West" not in zipped
    [back] = notebooks.read_notebook(zipped)
    assert back.approved is not None and back.approved["snapshot"]["digest"] == approved["snapshot"]["digest"]
    assert back.approved["snapshot"]["tables"] == [{"columns": ["", "region", "amount"], "shape": [3, 2]}]
