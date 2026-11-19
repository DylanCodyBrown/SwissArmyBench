"""The canvas's remaining work in the Workbench window (2026-11-19): a SQL query from the Toolbox makes its
%%sql cell and its block; the pane's query section shows its connection, the page value its query names and
the block that gives it, and Show as turns its result into a chart. Screenshots when
SWISSARMYBENCH_CANVAS_SHOTS names a folder. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_canvas_designer_page import block, front
from tests.e2e.test_canvas_pane_page import open_window, orders, pane, shot, until  # noqa: F401
from tests.e2e.test_table_cells_page import window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_connections import sqlite_connection

FILTER = '# Region filter\nregion = st.selectbox("Region", ["East", "West"], key="region_pick")'
QUERY = "-- Orders in the region\nSELECT order_id, amount FROM orders WHERE region = {{ region }}"


def _shop(server: dict[str, Any], folder: Path) -> None:  # noqa: F811
    database = folder / "shop.sqlite"
    with sqlite3.connect(database) as made:
        made.execute("CREATE TABLE IF NOT EXISTS orders (order_id INTEGER, region TEXT, amount INTEGER)")
        made.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(1, "East", 100), (2, "West", 250)])
    call(server, "POST", "/connections", sqlite_connection(database))


def query_app(server: dict[str, Any], folder: Path) -> Path:  # noqa: F811
    folder.mkdir(parents=True, exist_ok=True)
    _shop(server, folder)
    notebook = folder / "app.ipynb"
    cells = [
        {"kind": "code", "source": FILTER, "name": "Region filter"},
        {"kind": "sql", "source": QUERY, "connection": "Shop -> by_region", "name": "by_region"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 4, "h": None},
        {"document": str(notebook), "cell": 2, "row": 1, "column": 5, "w": 8, "h": None},
    ]
    app = folder / "orders.stapp.json"
    call(
        server, "POST", "/workbench/save", {"path": str(app), "pages": [{"name": "Orders", "blocks": blocks}]}
    )
    return app


def test_a_sql_block_its_query_section_and_a_query_from_the_toolbox(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    app = query_app(server, tmp_path / "shop")
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    blocks = board.locator(".cv-block")
    expect(blocks).to_have_count(2, timeout=20000)
    expect(board.locator(".cv-query")).to_have_text("SQL")
    props = pane(page)
    blocks.nth(1).click()
    section = props.locator('[data-section="query"]')
    expect(section).to_be_visible(timeout=15000)
    expect(section.locator("select[data-field=connection]")).to_have_value("Shop")
    param = section.locator('[data-param="region"]')
    expect(param).to_contain_text("Region filter")
    shot(page, "query-block-pane")
    # Show as a bar chart: the block's view, and the code the page runs.
    section.locator("select[data-field=as]").select_option("bar")
    until(lambda: block(server, "b2").get("view", {}).get("as"), "bar")
    expect(props.locator("pre.cp-code")).to_contain_text("st.bar_chart(by_region", timeout=15000)
    # The page value's link selects the block that gives it.
    props.locator('[data-param="region"]').click()
    until(lambda: window(server, "canvas.state")["selected"], ["b1"])
    # The Toolbox's SQL query: its %%sql cell in the app notebook and its block.
    assert window(server, "canvas.panel", panel="toolbox") == {"open": True}
    toolbox = page.locator(".wb-mode-toolbox")
    toolbox.get_by_role("searchbox", name="Search the Toolbox").fill("SQL")
    toolbox.locator('.tb-item[data-tool="sql_query"]').click()
    expect(blocks).to_have_count(3, timeout=30000)
    until(lambda: any(b["name"] == "query_1" for b in front(server)["blocks"]), True)
    saved = json.loads((tmp_path / "shop" / "app.ipynb").read_text(encoding="utf-8"))
    assert any(c["source"] and "".join(c["source"]).startswith("%%sql") for c in saved["cells"])
    shot(page, "query-block-toolbox")
    page.context.close()
