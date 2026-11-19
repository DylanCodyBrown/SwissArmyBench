"""The canvas's property pane in the Workbench window (the owner, 2026-11-19): a block selected, its Uses
list a table and a variable, the table's preview opens beside the canvas with Open as grid; a Default
changed in the pane changes the cell's code and Undo takes it back; a cache's ttl changes its decorator;
with a Python that has Streamlit, Play, a Now value changes the live page and Clear this cache runs.
Screenshots when SWISSARMYBENCH_CANVAS_SHOTS names a folder. Made-up data only."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from swissarmybench.renamed import env
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

SHOTS = env("SWISSARMYBENCH_CANVAS_SHOTS") or None
ORDERS = pd.DataFrame(
    {
        "order_id": [10482, 10377, 10611, 10295, 10540, 10123],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [4120.0, 3860.5, 3402.75, 3118.2, 2990.0, 1200.0],
    }
)
FILTER = """# Region filter
import os

# the regions the page offers
region = st.selectbox("Region", ["All", "East", "West"], index=0, key="region_pick")
folder = os.environ.get("REPORT_FOLDER", "")"""
CHART = """# Orders by region
@st.cache_data(ttl=600)
def by_region(orders, region):
    return orders if region == "All" else orders[orders["region"] == region]


shown = by_region(orders, region)
st.metric("Orders", len(shown))
st.caption(f"Region: {region}")"""
NOTE = '# Largest\nst.dataframe(shown.nlargest(3, "amount"))'


def open_window(browser: Browser, server: dict[str, Any], path: Path, dark: bool = False) -> Page:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1500, "height": 950},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={quote(str(path))}")
    expect(page.locator(".wb-tab").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:  # noqa: F811
    close_tables(server)
    push_client.push(ORDERS, name="orders", new_grid=True)
    yield
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def app_files(server: dict[str, Any], folder: Path) -> Path:  # noqa: F811
    folder.mkdir(parents=True, exist_ok=True)
    notebook = folder / "app.ipynb"
    cells = [
        {"kind": "code", "source": FILTER, "name": "Region filter"},
        {"kind": "code", "source": CHART, "name": "Orders by region"},
        {"kind": "code", "source": NOTE, "name": "Largest"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    if STREAMLIT_PYTHON:
        call(server, "POST", "/workbench/environment", {"path": str(notebook), "python": STREAMLIT_PYTHON})
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 4, "h": None},
        {"document": str(notebook), "cell": 2, "row": 1, "column": 5, "w": 8, "h": None},
        {"document": str(notebook), "cell": 3, "row": 2, "column": 1, "w": 12, "h": None},
    ]
    app = folder / "sales.stapp.json"
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(app), "pages": [{"name": "Overview", "blocks": blocks}]},
    )
    return app


def inspect(server: dict[str, Any], block: str) -> dict[str, Any]:  # noqa: F811
    apps = call(server, "GET", "/streamlit/apps")["apps"]
    app = [a["app"] for a in apps if a["kind"] == "canvas"][-1]  # this test's: the one opened last
    return dict(call(server, "GET", f"/streamlit/apps/{app}/inspect?page=p1&block={block}"))


def until(read: Callable[[], Any], wanted: Any, seconds: float = 15.0) -> None:
    """The server holds what the page wrote (a change made in the page reaches it a moment later)."""
    end = time.monotonic() + seconds
    seen = read()
    while seen != wanted and time.monotonic() < end:
        time.sleep(0.2)
        seen = read()
    assert seen == wanted


def pane(page: Page) -> Any:
    page.locator(".wb-status").get_by_role("button", name="Properties", exact=True).click()
    props = page.locator(".wb-mode-properties")
    expect(props).to_be_visible()
    return props


def test_a_blocks_uses_its_table_beside_the_canvas_and_code_written_back(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    blocks = page.locator(".cv .cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    props = pane(page)
    blocks.nth(1).click()
    # Uses: the table (rows), the cell that makes region; the lineage's line ends at this block.
    uses = props.locator(".cp-uses")
    expect(uses.locator('[data-list="tables"] li')).to_contain_text("orders")
    expect(uses.locator('[data-list="tables"] li')).to_contain_text("6 rows")
    expect(uses.locator('[data-list="cells"] li').first).to_contain_text("region")
    expect(uses.locator(".cp-node.target")).to_have_text("this block", timeout=15000)
    # The table opens beside the canvas: its columns with types, its first rows; Open as grid.
    uses.locator('[data-list="tables"] button').click()
    table = props.locator('.cp-table[data-table="orders"]')
    expect(table.locator("thead th")).to_have_count(3, timeout=15000)
    expect(table.locator("thead th").nth(2)).to_contain_text("amount")
    expect(table.locator("tbody tr")).to_have_count(6)
    expect(table.locator("tbody tr").first).to_contain_text("10482")
    shot(page, "pane-table-preview")
    with page.expect_popup() as opened:
        table.get_by_role("button", name="Open as grid").click()
    assert "/g/" in opened.value.url
    opened.value.close()
    # The filter: its variable in Uses, what it is used by, its element's properties as a grid.
    blocks.nth(0).click()
    expect(props.locator("input[data-field=name]")).to_have_value("Region filter")
    expect(uses.locator('[data-list="variables"] li')).to_contain_text("REPORT_FOLDER")
    expect(uses.locator('[data-list="used by"] li')).to_have_count(1)
    grid = props.locator(".cp-properties .cp-grid")
    expect(grid.locator('.cp-row[data-property="label"] input')).to_have_value("Region")
    expect(grid.locator('.cp-row[data-property="options"] input')).to_have_value("All, East, West")
    expect(grid.locator('.cp-row[data-property="index"] input')).to_have_value("0")
    # A property's one line at the foot; A to Z; the search box.
    grid.locator('.cp-row[data-property="options"] input').focus()
    expect(props.locator(".cp-words")).to_have_text("The choices it offers.")
    props.get_by_role("button", name="Alphabetical").click()
    expect(props.locator(".cp-category")).to_have_count(0)
    props.get_by_role("button", name="Categorized").click()
    expect(props.locator(".cp-category").first).to_be_visible()
    props.get_by_role("searchbox", name="Search properties").fill("help")
    expect(props.locator(".cp-properties .cp-row")).to_have_count(1)
    props.get_by_role("searchbox", name="Search properties").fill("")
    shot(page, "pane-block")
    # Default: written into the cell's code (only its own characters), shown in the cell; Undo.
    default = props.locator(".cp-state input[data-field=default]")
    expect(default).to_have_value("0")
    expect(props.locator(".cp-play-first").first).to_have_text("Play the page to see its live state")
    default.fill("2")
    default.press("Enter")
    expect(props.locator(".cp-state input[data-field=default]")).to_have_value("2", timeout=15000)
    until(lambda: inspect(server, "b1")["widgets"][0]["arguments"]["index"]["value"], 2)
    held = next(d for d in window(server, "documents")["documents"] if d["title"] == "app.ipynb")
    assert held["unsaved_changes"] is True
    window(server, "canvas.undo")
    expect(props.locator(".cp-state input[data-field=default]")).to_have_value("0", timeout=15000)
    until(lambda: inspect(server, "b1")["widgets"][0]["arguments"]["index"]["value"], 0)
    window(server, "canvas.redo")
    expect(props.locator(".cp-state input[data-field=default]")).to_have_value("2", timeout=15000)
    # The cell itself shows it, comments and all, and the editor's own Undo takes it back.
    props.locator(".app-source").click()
    cell = page.locator(".wb-cell").first
    expect(cell).to_contain_text("index=2", timeout=15000)
    expect(cell).to_contain_text("# the regions the page offers")
    # A property set from the grid, and reset by its right-click menu.
    page.locator(".wb-tab", has_text="sales").first.click()
    blocks.nth(0).click()
    help_box = grid.locator('.cp-row[data-property="help"] input')
    help_box.fill("Pick a region")
    help_box.press("Enter")
    expect(grid.locator('.cp-row[data-property="help"]')).to_have_class("cp-row set", timeout=15000)
    until(
        lambda: inspect(server, "b1")["widgets"][0]["arguments"].get("help", {}).get("value"), "Pick a region"
    )
    grid.locator('.cp-row[data-property="help"]').click(button="right")
    page.get_by_role("menuitem", name="Reset to default").click()
    expect(grid.locator('.cp-row[data-property="help"]')).to_have_class("cp-row", timeout=15000)
    until(lambda: "help" in inspect(server, "b1")["widgets"][0]["arguments"], False)
    # Cache: the decorator's ttl; Cache's Now needs Play.
    blocks.nth(1).click()
    ttl = props.locator('.cp-cache[data-function="by_region"] input[data-field=ttl]')
    expect(ttl).to_have_value("600", timeout=15000)
    ttl.fill("60")
    ttl.press("Enter")
    expect(props.locator('.cp-cache[data-function="by_region"] input[data-field=ttl]')).to_have_value(
        "60", timeout=15000
    )
    until(lambda: inspect(server, "b2")["cache"][0]["settings"]["ttl"]["value"], 60)
    expect(props.get_by_role("button", name="Clear this cache")).to_be_disabled()
    # The code the page runs for it.
    props.locator(".cp-code summary").click()
    expect(props.locator("pre.cp-code")).to_contain_text("with _slot_b2:")
    expect(props.locator("pre.cp-code")).to_contain_text("@st.cache_data(ttl=60)")
    shot(page, "pane-streamlit")
    page.context.close()


def test_code_that_is_not_a_plain_value_is_read_only_and_a_handler_is_written(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    blocks = page.locator(".cv .cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    props = pane(page)
    blocks.nth(1).click()
    # st.metric("Orders", len(shown)): its value is code, shown as code with Go to cell.
    value = props.locator('.cp-properties .cp-row[data-property="value"] .cp-bound')
    expect(value).to_have_attribute("data-kind", "expression", timeout=15000)
    expect(value).to_contain_text("len(shown)")
    expect(props.locator('.cp-properties .cp-row[data-property="value"] input')).to_have_count(0)
    # Events: Add handler writes the stub and goes to it.
    blocks.nth(0).click()
    events = props.locator(".cp-events")
    expect(events.locator('.cp-row[data-event="on_change"]')).to_be_visible(timeout=15000)
    events.get_by_role("button", name="Add handler").click()
    cell = page.locator(".wb-cell").first
    expect(cell).to_contain_text("def on_region_pick_change():", timeout=15000)
    expect(cell).to_contain_text("on_change=on_region_pick_change")
    until(
        lambda: inspect(server, "b1")["widgets"][0]["events"].get("on_change", {}).get("handler"),
        "on_region_pick_change",
    )
    # Bind a property to a session state key by its right-click menu.
    page.locator(".wb-tab", has_text="sales").first.click()
    blocks.nth(0).click()
    row = props.locator('.cp-properties .cp-row[data-property="disabled"]')
    row.click(button="right")
    page.get_by_role("menuitem", name="Bind to session state…").click()
    bind = props.locator('.cp-bind[data-bind="state"] input')
    bind.fill("locked")
    bind.press("Enter")
    expect(row.locator(".cp-bound")).to_contain_text('st.session_state["locked"]', timeout=15000)
    until(lambda: inspect(server, "b1")["widgets"][0]["arguments"].get("disabled", {}).get("kind"), "state")
    page.context.close()


@needs_streamlit
def test_now_changes_the_running_page_and_clears_a_cache(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app, dark=True)
    blocks = page.locator(".cv .cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    props = pane(page)
    blocks.nth(0).click()
    window(server, "canvas.play")
    frame = page.frame_locator(".cv-frame")
    expect(frame.get_by_text("Region: All")).to_be_visible(timeout=90000)
    now = props.locator(".cp-state input[data-field=now]")
    expect(now).to_have_value("All", timeout=30000)
    now.fill("West")
    now.press("Enter")
    expect(frame.get_by_text("Region: West")).to_be_visible(timeout=60000)
    expect(props.locator(".cp-state input[data-field=now]")).to_have_value("West", timeout=30000)
    shot(page, "pane-now-dark")
    # The agent's Now, and Clear this cache on the cached function's block.
    app_id = window(server, "canvas.state")["app"]
    call(server, "POST", f"/streamlit/apps/{app_id}/now", {"key": "region_pick", "value": "East"}, agent=True)
    expect(frame.get_by_text("Region: East")).to_be_visible(timeout=60000)
    window(server, "canvas.select", block="b2")
    clear = props.get_by_role("button", name="Clear this cache")
    expect(clear).to_be_enabled(timeout=15000)
    clear.click()
    expect(frame.get_by_text("Region: East")).to_be_visible(timeout=60000)
    expect(page.locator(".error-note")).to_have_count(0)
    page.context.close()
