# ruff: noqa: F811
"""Lineage with values and approved outputs (docs/ideas.md, 2026-11-15), in a real browser: a cell's
lineage from its right-click menu, the flow drawn by Mermaid beside a card per step with its value, a
click marking a card and its node, a double-click going to the cell, the values following the kernel;
a canvas block's lineage, its values from the playing page, a filter changed on the page reaching the
cards; and an output approved, changed, said in amber, approved again. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.domain import notebooks
from tests.e2e.test_table_cells_page import close_tables, kernel_of, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None
LONG = 60000  # Streamlit's first start, in milliseconds
ORDERS = (
    "orders = pd.DataFrame({'region': ['East', 'West', 'East', 'North', 'West', 'East'], "
    "'amount': [100, 250, 40, 75, 10, 5]})"
)
FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'


def open_window(browser: Browser, server: dict[str, Any], path: Path) -> Page:
    context = browser.new_context(
        viewport={"width": 1500, "height": 950}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={quote(str(path))}")
    expect(page.locator(".wb-tab").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def notebook(
    path: Path, sources: list[str], python: str | None = None, server: dict[str, Any] | None = None
) -> None:
    cells = [notebooks.Cell("code", source, number=i) for i, source in enumerate(sources, start=1)]
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    if python and server:
        call(server, "POST", "/workbench/environment", {"path": str(path), "python": python})


def until(check: Any, seconds: float = 10.0) -> Any:
    """What `check()` gives once it is truthy (the window answers as it gets there)."""
    deadline = time.monotonic() + seconds
    while True:
        found = check()
        if found or time.monotonic() > deadline:
            return found
        time.sleep(0.2)


def card(page: Page, label: str) -> Any:
    return page.locator(".wb-lin-card").filter(
        has=page.locator(".wb-lin-label", has_text=re.compile(f"^{re.escape(label)}$"))
    )


def test_a_cells_lineage_shows_the_flow_and_its_values_and_follows_the_kernel(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    book = tmp_path / "sales.ipynb"
    notebook(
        book,
        [
            f"import pandas as pd\n{ORDERS}",
            '# Region\nregion = "West"',
            "west = orders[orders.region == region]",
            "# Total\ntotal = int(west.amount.sum())\ntotal",
        ],
    )
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    expect(cells).to_have_count(4, timeout=20000)
    window(server, "run.primary")
    expect(cells.nth(3).locator(".wb-outputs")).to_contain_text("260", timeout=60000)

    # ----- right-click the cell (its head): Lineage
    cells.nth(3).locator(".wb-cell-head .wb-number").click(button="right")
    workbench.get_by_role("menuitem", name="Lineage").click()
    overlay = workbench.get_by_role("dialog", name="Lineage")
    expect(overlay).to_be_visible()
    expect(overlay.locator(".wb-lin-target")).to_have_text("Total · sales.ipynb @cell4")
    # The flow, drawn by Mermaid: a node per cell, top to bottom, the data first.
    expect(overlay.locator(".wb-lin-chart svg g.node")).to_have_count(4, timeout=20000)
    expect(overlay.locator(".wb-lin-card .wb-lin-label")).to_have_text(
        ["import pandas as pd", "Region", "west = orders[orders.region == region]", "Total"]
    )
    # Each card: a table's rows and columns, its first rows, its row change; a value as itself.
    expect(card(workbench, "import pandas as pd")).to_contain_text("6 rows × 2 columns")
    west = card(workbench, "west = orders[orders.region == region]")
    expect(west).to_contain_text("2 rows × 2 columns")
    expect(west.locator(".wb-lin-change")).to_have_text("−4 rows")
    expect(west.locator(".wb-lin-table tbody tr")).to_have_count(2)
    expect(card(workbench, "Region").locator(".wb-lin-value")).to_have_text("West")
    expect(card(workbench, "Total").locator(".wb-lin-value")).to_have_text("260")
    # Each card sits beside its node (the flow top to bottom, the cards in its order).
    tops = [overlay.locator(".wb-lin-card").nth(i).bounding_box()["y"] for i in range(4)]  # type: ignore[index]
    assert tops == sorted(tops)
    shot(workbench, "lineage-from-a-cell")

    # ----- a click marks a card and its node
    card(workbench, "Region").click()
    expect(card(workbench, "Region")).to_have_class(re.compile("picked"))
    expect(overlay.locator(".wb-lin-chart g.node.picked")).to_have_count(1)
    overlay.locator(".wb-lin-chart g.node").nth(2).click()
    expect(west).to_have_class(re.compile("picked"))
    expect(card(workbench, "Region")).not_to_have_class(re.compile("picked"))

    # ----- live: the kernel's values change (code run elsewhere), and the cards follow
    call(
        server,
        "POST",
        f"/workbench/kernels/{kernel_of(server)}/execute",
        {"code": "region = 'East'\nwest = orders[orders.region == region]\ntotal = int(west.amount.sum())"},
    )
    expect(card(workbench, "Total").locator(".wb-lin-value")).to_have_text("145", timeout=15000)
    expect(card(workbench, "Region").locator(".wb-lin-value")).to_have_text("East")
    expect(west.locator(".wb-lin-change")).to_have_text("−3 rows")

    # ----- the agent's command: the same flow, its Mermaid and each value
    said = call(server, "POST", "/workbench/lineage", {"document": str(book), "cell": 4}, agent=True)
    assert [n["label"] for n in said["nodes"]][-1] == "Total" and said["mermaid"].startswith("flowchart TD")
    total = next(n["id"] for n in said["nodes"] if n["label"] == "Total")
    assert said["values"][total]["items"][0]["text"] == "145"

    # ----- a double-click goes to the cell; Escape had closed it, so does going there
    card(workbench, "Region").dblclick()
    expect(overlay).to_be_hidden()
    expect(cells.nth(1)).to_have_class(re.compile("selected"))
    # The same overlay from the palette's command (the agent's workbench_lineage_show).
    shown = window(server, "lineage.open", number=3)
    assert shown["nodes"] == 3
    expect(overlay).to_be_visible()
    workbench.keyboard.press("Escape")
    expect(overlay).to_be_hidden()
    workbench.context.close()


def test_an_approved_output_that_changes_says_so_in_amber(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    book = tmp_path / "checks.ipynb"
    notebook(book, ["total = 390", "print('total', total)\nprint('regions', 3)"])
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    expect(cells).to_have_count(2, timeout=20000)
    window(server, "run.primary")
    expect(cells.nth(1).locator(".wb-outputs")).to_contain_text("total 390", timeout=60000)

    # ----- approve the output (the cell's right-click menu)
    cells.nth(1).locator(".wb-outputs").click(button="right")
    workbench.get_by_role("menuitem", name="Approve the output").click()
    note = cells.nth(1).locator(".wb-approval")
    expect(note).to_be_hidden()  # the same: nothing to say
    listed = until(lambda: window(server, "approvals.list")["approvals"])
    assert [(a["cell"], a["changed"]) for a in listed] == [(2, None)]

    # ----- a run that differs: amber, with the difference; the same again: nothing
    window(server, "run.primary")
    expect(cells.nth(1).locator(".wb-outputs")).to_contain_text("total 390", timeout=60000)
    expect(note).to_be_hidden()
    cells.nth(0).locator(".monaco-editor").click()
    workbench.keyboard.press("Control+a")
    workbench.keyboard.insert_text("total = 400")
    window(server, "run.primary")
    expect(note).to_be_visible(timeout=60000)
    expect(note.locator(".wb-approval-word")).to_have_text("⚠ Changed since approved")
    expect(note.locator(".wb-approval-diff")).to_contain_text("-total 390")
    expect(note.locator(".wb-approval-diff .add")).to_have_text("+total 400")
    changed = until(lambda: window(server, "approvals.list")["approvals"][0]["changed"])
    assert changed == ["-total 390", "+total 400", " regions 3"]
    shot(workbench, "approved-output-changed")

    # ----- saved: the approval is in the cell's metadata (plain Jupyter keeps it)
    window(server, "file.save")
    expect(workbench.locator(".wb-tab.dirty")).to_have_count(0, timeout=10000)
    saved = json.loads(book.read_text(encoding="utf-8"))
    kept = saved["cells"][1]["metadata"]["swissarmybench"]["approved"]
    assert kept["snapshot"]["text"] == "total 390\nregions 3"

    # ----- Approve this output: the new output is the approved one, the note goes
    note.get_by_role("button", name="Approve this output").click()
    expect(note).to_be_hidden()
    assert window(server, "approvals.list")["approvals"][0]["changed"] is None
    window(server, "cell.approve", number=2, remove=True)
    assert window(server, "approvals.list")["approvals"] == []
    workbench.context.close()


@pytest.fixture(autouse=True)
def _no_tables_left(server: dict[str, Any]) -> Any:
    yield
    close_tables(server)
