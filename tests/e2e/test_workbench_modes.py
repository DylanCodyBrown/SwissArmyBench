# ruff: noqa: F811
"""The Workbench's modes and kind colours (2026-11-15), in a real browser: app pages violet, notebooks
blue, scripts green on tabs, the group's band, the Streamlit cells pane and canvas blocks; App mode
(Properties for a block and the page settings, the wiring, undo, duplicate, align, zoom, the starter
gallery, Play's preview and the State panel); Notebook mode (run order, edited and out-of-date cells,
the Outline, Run up to here, Present); Script mode (run settings, Run as scheduled, run history); Data
mode (data.ipynb's Cells | Lineage | Dictionary). Made-up data only.

With SWISSARMYBENCH_MODES_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server, until  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_MODES_SHOTS", "") or None
ORDERS = pd.DataFrame(
    {
        "order_id": [10482, 10377, 10611, 10295, 10540, 10123],
        "region": ["East", "West", "East", "North", "West", "East"],
        "status": ["shipped", "delivered", "shipped", "returned", "shipped", "shipped"],
        "amount": [4120.0, 3860.5, 3402.75, 3118.2, 2990.0, 1200.0],
    }
)
FILTER = (
    '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()), key="region_pick")'
)
TOTAL = '# Total sales\nst.metric("Total sales", int(orders[orders["region"] == region]["amount"].sum()))'
LARGEST = '# Largest orders\nst.dataframe(orders[orders["region"] == region].nlargest(5, "amount"))'


def open_window(
    browser: Browser, server: dict[str, Any], path: Path | None = None, dark: bool = False
) -> Page:
    context = browser.new_context(
        viewport={"width": 1500, "height": 950},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    opened = f"&open={quote(str(path))}" if path else ""
    # A .py on the Scripts page, anything else on the Notebooks page (2026-11-21).
    where = "scripts" if path and path.suffix == ".py" else "notebooks"
    page.goto(f"http://127.0.0.1:{server['port']}/{where}#token={server['token']}{opened}")
    expect(page.locator(".wb-tab" if path else ".wb-codex").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:
    close_tables(server)
    push_client.push(ORDERS, name="orders", new_grid=True)
    yield
    close_tables(server)


def colour(page: Page, selector: str, prop: str = "color") -> str:
    return str(page.locator(selector).first.evaluate(f"e => getComputedStyle(e).{prop}"))


def token(page: Page, name: str) -> str:
    return str(
        page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('--kind-{name}').trim()")
    )


def rgb(hex_colour: str) -> str:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgb({r}, {g}, {b})"


def test_notebook_mode_run_order_outline_run_up_to_here_and_present(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    path = tmp_path / "analysis.ipynb"
    cells = [
        {"kind": "markdown", "source": "# Monthly sales\nShipped orders only."},
        {"kind": "code", "source": "shipped = sales[sales['status'] == 'shipped']", "name": "shipped"},
        {
            "kind": "code",
            "source": "monthly = shipped.groupby('region')['amount'].sum().reset_index()\nmonthly",
            "name": "monthly",
        },
        {"kind": "markdown", "source": "## By region"},
        {
            "kind": "code",
            "source": "by_region = shipped.groupby('region')['amount'].sum()",
            "name": "by_region",
        },
    ]
    first = (
        "import pandas as pd\nsales = pd.DataFrame({'region': ['East', 'West', 'East'], "
        "'status': ['shipped', 'shipped', 'returned'], 'amount': [10.0, 20.0, 5.0]})"
    )
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(path), "cells": [{"kind": "code", "source": first}, *cells]},
    )
    page = open_window(browser, server, path)
    expect(page.locator(".wb-cell")).to_have_count(6, timeout=20000)

    for number in (1, 3, 4, 6):
        window(
            server, "run.cell", index=[c["number"] for c in window(server, "doc.read")["cells"]].index(number)
        )
    states = {c["number"]: c["state"] for c in window(server, "notebook.runOrder")}
    assert states[3] == states[4] == states[6] == "current"
    # Edit the first: it says "edited", and the cells that read what it makes "out of date".
    window(server, "cell.select", index=2)
    page.locator(".wb-cell").nth(2).locator(".monaco-editor").click()
    page.keyboard.press("End")
    page.keyboard.type("  # shipped only")
    order: dict[int, Any] = {}
    for _ in range(20):  # the run order follows the typing after a short pause
        page.wait_for_timeout(300)
        order = {c["number"]: c for c in window(server, "notebook.runOrder")}
        if order[4]["state"] == "outOfDate":
            break
    assert (
        order[3]["state"] == "edited"
        and order[4]["state"] == "outOfDate"
        and order[4]["because"] == ["shipped"]
    )
    expect(page.locator(".wb-cell").nth(2).locator(".wb-flow")).to_have_text("edited")
    expect(page.locator(".wb-cell").nth(3).locator(".wb-flow")).to_have_text("out of date")
    # The Outline: the headings and the named cells, the stale ones marked.
    page.locator(".wb-status").get_by_role("button", name="Outline", exact=True).click()
    outline = page.locator(".wb-mode-outline")
    expect(outline.locator(".wb-outline-item.heading")).to_have_text(["Monthly sales", "By region"])
    expect(outline.locator(".wb-outline-item.cell")).to_have_count(3)
    expect(outline.locator(".wb-outline-stale")).to_have_count(3)
    # Open as grid on a DataFrame's output; Run up to here.
    expect(page.locator(".wb-cell").nth(3).get_by_role("button", name="Open as grid")).to_be_visible()
    page.locator(".wb-cell").nth(5).click()
    shot(page, "notebook-outline-runorder")
    window(server, "run.upToHere", number=6)
    states = {c["number"]: c["state"] for c in window(server, "notebook.runOrder")}
    assert states[3] == states[4] == states[6] == "current"
    expect(outline.locator(".wb-outline-stale")).to_have_count(0)
    # Present: the text and outputs, no code.
    page.get_by_role("button", name="Present", exact=True).click()
    expect(page.locator(".wb-cells.presenting")).to_be_visible()
    expect(page.locator(".wb-cells.presenting .wb-editor").first).to_be_hidden()
    expect(page.locator(".wb-markdown-view h1")).to_have_text("Monthly sales")
    shot(page, "notebook-present")
    assert window(server, "notebook.present", on=False) == {"presenting": False}
    page.context.close()


SCRIPT = """\
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="all")
options = parser.parse_args()
host = os.getenv("WAREHOUSE_HOST", "none")
folder = os.environ.get("REPORT_FOLDER", "reports")
print(f"region {options.region} host {host} folder {folder}")
"""


def test_script_mode_run_settings_run_as_scheduled_and_history(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    path = tmp_path / "daily_sales.py"
    path.write_text(SCRIPT, encoding="utf-8")
    page = open_window(browser, server, path)
    bar = page.locator(".wb-status")
    expect(bar.get_by_role("button", name="Run settings", exact=True)).to_be_visible(timeout=20000)
    bar.get_by_role("button", name="Run settings", exact=True).click()
    settings = page.locator(".wb-mode-runSettings")
    expect(settings.locator(".wb-run-var")).to_have_count(2, timeout=10000)
    expect(settings.locator(".wb-run-var").first).to_contain_text("WAREHOUSE_HOST")
    args = settings.locator(".wb-run-args")
    args.fill("--region East")
    args.press("Enter")
    settings_url = f"/workbench/scripts/settings?path={quote(str(path))}"
    until(lambda: call(server, "GET", settings_url)["arguments"] == "--region East")  # kept
    host = settings.locator('.wb-run-var[data-variable="WAREHOUSE_HOST"] select')
    host.select_option("value")
    value = settings.locator('.wb-run-var[data-variable="WAREHOUSE_HOST"] input')
    expect(value).to_be_visible()
    value.fill("db1.example.test")
    value.press("Enter")
    until(
        lambda: any(
            v["name"] == "WAREHOUSE_HOST" and v["words"] == "Plain value"
            for v in call(server, "GET", settings_url)["variables"]
        )
    )
    held = call(server, "GET", settings_url)
    assert held["arguments"] == "--region East"
    assert any(v["name"] == "WAREHOUSE_HOST" and v["words"] == "Plain value" for v in held["variables"])
    shot(page, "script-run-settings")
    # Run as scheduled: a fresh process; its run in the history, with its exit code and log.
    window(server, "script.runScheduled")
    history = page.locator(".wb-mode-runHistory")
    expect(history.locator(".wb-runs tbody tr")).to_have_count(1, timeout=30000)
    expect(history.locator(".wb-run-log")).to_contain_text("region East host db1.example.test folder reports")
    expect(history.locator(".wb-runs tbody tr").first).to_contain_text("Run as scheduled")
    # Run file (the kernel's) joins the history.
    window(server, "run.primary")
    expect(history.locator(".wb-runs tbody tr")).to_have_count(2, timeout=30000)
    expect(history.locator(".wb-runs tbody tr").first).to_contain_text("Run file")
    history.locator(".wb-runs tbody tr").nth(1).click()
    expect(history.locator(".wb-run-detail")).to_contain_text("Run as scheduled")
    shot(page, "script-history")
    page.context.close()


def test_data_mode_cells_lineage_and_the_dictionary(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    page = open_window(browser, server)
    window(server, "project.new", folder=str(tmp_path), name="sales", notebooks=["analysis"], app=False)
    data_tab = page.locator(".wb-tab", has_text="data.ipynb")
    expect(data_tab).to_be_visible(timeout=20000)
    data_tab.click()
    switch = page.locator(".wb-view-switch")
    expect(switch.get_by_role("button", name="Dictionary", exact=True)).to_be_visible()
    assert window(server, "data.view", view="dictionary") == {"view": "dictionary"}
    view = page.locator(".wb-data-view")
    expect(view.locator(".dict-columns tbody tr")).to_have_count(4, timeout=20000)
    expect(view.locator('tr[data-column="amount"] td').nth(1)).to_have_text("Decimal")
    expect(view.locator('tr[data-column="order_id"] td').nth(1)).to_have_text("Whole number")
    status = view.locator('tr[data-column="status"] input')
    status.fill("Shipped, delivered or returned")
    status.press("Enter")
    page.wait_for_timeout(400)
    window(server, "dictionary.describe", table="orders", text="One row per order line, shipped orders only.")
    shot(page, "data-dictionary")
    window(server, "file.save")
    saved = json.loads((tmp_path / "sales" / "data.ipynb").read_text(encoding="utf-8"))
    said = saved["metadata"]["swissarmybench"]["dictionary"]["orders"]
    assert said == {
        "description": "One row per order line, shipped orders only.",
        "columns": {"status": "Shipped, delivered or returned"},
    }
    window(server, "project.exportData")
    assert "#     status: Shipped, delivered or returned" in (tmp_path / "sales" / "data.py").read_text(
        encoding="utf-8"
    )
    # Lineage: the lineage overlay's own flow, drawn in place (data.ipynb's last cell: the orders
    # table's), its edges in the kind colours; a double-click on a node goes back to the cells.
    window(server, "data.view", view="lineage")
    placed = view.locator(".wb-lineage.in-place")
    expect(placed).to_be_visible(timeout=20000)
    expect(page.get_by_role("dialog", name="Lineage")).to_have_count(0)
    expect(placed.locator(".wb-lin-card.target")).to_contain_text("orders", timeout=20000)
    expect(placed.locator(".wb-lin-chart svg")).to_be_visible(timeout=20000)
    assert placed.evaluate("e => getComputedStyle(e).getPropertyValue('--lineage-notebook').trim()") == token(
        page, "notebook"
    )
    shot(page, "data-lineage")
    window(server, "data.view", view="cells")
    expect(page.locator(".wb-cells").first).to_be_visible()
    expect(view).to_be_hidden()
    page.context.close()
