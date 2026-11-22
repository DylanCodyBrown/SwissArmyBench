# ruff: noqa: F811
"""SQL sees the open tables, and the polish bugs (feel-a, 2026-11-19), in a real browser: a notebook's DuckDB
SQL cell reads an open grid by its name; a missing table's error is said once, without DuckDB's own-table
guess; a Python cell's missing open table offers its table cell; every grid tab is as wide as its name;
the palette's "No matches" sits in the list's inset; one Escape closes Find data and Ctrl+Shift+P then works;
Settings' boxes keep their lines at the top, the agent prompt names the app; the Variables page's search
box looks like the other inputs; the ERD's status bar says ERD only; a cell's kind and connection pickers
are the app's own. Made-up data only."""

from __future__ import annotations

from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401
from tests.e2e.test_workbench_feedback import close_tables, window, workbench

ORDERS = pd.DataFrame({"order_id": [1, 2, 3, 4], "store": ["North", "South", "North", "East"]})


def home(browser: Browser, server: dict[str, Any], query: str, width: int = 1440) -> Page:
    page = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{query}#token={server['token']}")
    return page


def run_cell(page: Page, kind: str, text: str) -> Any:
    cell = page.locator(".wb-cell:visible").first
    expect(cell).to_be_visible(timeout=20000)
    if kind == "sql":
        cell.get_by_role("combobox", name="Cell kind").select_option(label="SQL")
    cell.locator(".monaco-editor").first.click()
    page.keyboard.type(text)
    page.keyboard.press("Control+Enter")
    return cell


def test_a_sql_cell_reads_an_open_grid_and_a_missing_table_is_said_once(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    push_client.push(ORDERS, name="feel_orders", new_grid=True)
    page = workbench(browser, server)
    try:
        window(server, "file.newNotebook")
        cell = run_cell(
            page, "sql", "SELECT store, count(*) AS n FROM feel_orders GROUP BY ALL ORDER BY n DESC"
        )
        expect(cell).to_contain_text("feel_orders: the open table in Grids, 4 rows", timeout=60000)
        expect(cell.frame_locator("iframe").locator("table")).to_contain_text("North")
        # The cell's pickers are the app's own (no browser box), with their chevron drawn.
        picker = cell.get_by_role("combobox", name="Cell kind")
        assert picker.evaluate("e => getComputedStyle(e).appearance") == "none"

        window(server, "file.newNotebook")
        typo = run_cell(page, "sql", "SELECT * FROM feel_ordrs")
        panel = typo.locator(".wb-err")
        expect(panel).to_be_visible(timeout=60000)
        expect(panel).to_contain_text("cannot see: 'feel_ordrs'")
        expect(typo).not_to_contain_text("pg_")
        expect(typo).not_to_contain_text("below")
        # Said once: the panel only, not the raw text above it too.
        assert typo.inner_text().count("Table with name feel_ordrs does not exist") == 1
    finally:
        page.context.close()
        close_tables(server)


def test_a_python_cells_missing_open_table_offers_its_table_cell(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    push_client.push(ORDERS, name="feel_stores", new_grid=True)
    page = workbench(browser, server)
    try:
        window(server, "file.newNotebook")
        cell = run_cell(page, "python", 'import duckdb\nduckdb.sql("SELECT count(*) FROM feel_stores")')
        fix = cell.get_by_role("button", name="feel_stores is open in Grids: add its table cell")
        expect(fix).to_be_visible(timeout=60000)
        fix.click()
        expect(page.locator(".wb-tcell").filter(has_text="feel_stores").first).to_be_visible(timeout=20000)
    finally:
        page.context.close()
        close_tables(server)


def test_every_tab_is_as_wide_as_its_name(browser: Browser, server: dict[str, Any]) -> None:
    close_tables(server)
    names = ["regions", "stores", "customers", "categories", "products", "calendar", "orders", "order_lines"]
    for name in names:
        push_client.push(ORDERS, name=f"t_{name}", new_grid=True)
    url = push_client.push(ORDERS, name="t_returns", new_grid=True)
    page = open_grid(browser, url, width=1024)
    try:
        tabs = page.locator(".tabs-row .tab-item")
        expect(tabs).to_have_count(9)
        # Each tab is as wide as its whole name (the owner, 2026-11-21): no name is cut.
        cut = page.locator(".tabs-row .tab-label").evaluate_all(
            "ls => ls.filter(l => l.scrollWidth > l.clientWidth).map(l => l.textContent)"
        )
        assert cut == [], cut
        # A tab keeps its width when hovered (the close button keeps its room).
        other_width = tabs.filter(has_text="t_regions").evaluate("e => e.getBoundingClientRect().width")
        # The others' close buttons show on hover; the front one's always.
        expect(page.locator(".tab-item.active .tab-close")).to_be_visible()
        other = tabs.filter(has_text="t_regions")
        expect(other.locator(".tab-close")).to_be_hidden()
        other.hover()
        expect(other.locator(".tab-close")).to_be_visible()
        assert abs(other.evaluate("e => e.getBoundingClientRect().width") - other_width) < 1
        # The ERD's status bar is the ERD's, not the grid's behind it.
        page.locator(".nav-rail [data-area='erd']").click()
        expect(page.locator(".statusbar #status")).to_have_text("ERD")
    finally:
        page.context.close()
        close_tables(server)


def test_the_palette_find_data_and_their_keys(browser: Browser, server: dict[str, Any]) -> None:
    url = push_client.push(ORDERS, name="feel_keys", new_grid=True)
    page = open_grid(browser, url, width=1440)
    try:
        page.keyboard.press("Control+Shift+P")
        page.get_by_role("combobox", name="Command").fill("zzzz nothing like it")
        empty = page.locator(".wb-palette-list > li.hint")
        expect(empty).to_have_text("No matches")
        assert empty.evaluate("e => getComputedStyle(e).paddingLeft") == "12px"
        page.keyboard.press("Escape")
        # Find data: one Escape closes it, words typed or not, and the palette's keys work at once.
        page.keyboard.press("Control+K")
        search = page.locator("dialog.find-data .ex-search")
        expect(search).to_be_focused()
        page.keyboard.type("orders")
        page.keyboard.press("Escape")
        expect(page.locator("dialog.find-data")).to_have_count(0)
        page.keyboard.press("Control+K")
        expect(search).to_be_focused()
        page.keyboard.press("Control+Shift+P")
        expect(page.locator("dialog.find-data")).to_have_count(0)
        expect(page.get_by_role("combobox", name="Command")).to_be_focused()
    finally:
        page.context.close()


def test_settings_boxes_and_the_variables_search(browser: Browser, server: dict[str, Any]) -> None:
    page = home(browser, server, "?open=settings")
    try:
        radios = page.locator(".settings-page input[type='radio']")
        expect(radios.first).to_be_visible(timeout=20000)
        first, third = (radios.nth(i).bounding_box() for i in (0, 2))
        assert first and third and third["y"] - first["y"] < 60, (first, third)  # rows, not a tall spread
        expect(page.locator(".mcp-prompt")).to_contain_text("Swiss Army Bench MCP server")
        expect(page.locator(".mcp-prompt")).not_to_contain_text("grid MCP server")
        # The settings' search is the Environment's one search (the Variables page folded in, 2026-11-22).
        page.locator(".nav-rail [data-area='environment']").click()
        box = page.locator(".area-page[data-page='environment'] .env-search")
        expect(box).to_be_visible(timeout=20000)
        assert box.evaluate("e => getComputedStyle(e).borderTopLeftRadius") == "6px"
    finally:
        page.context.close()
