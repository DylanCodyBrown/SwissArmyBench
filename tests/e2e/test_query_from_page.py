# ruff: noqa: F811
"""The new table's Query from (the owner, 2026-11-17: "when I start a new query I should be able to add a
connection and query from that connection or choose Grids to query local"), in a real browser with made-up
data: Grids by default; a connection picked, its own SQL run there, the table built and its tray saying where
it runs; Run again goes back to the connection; Add a connection opens the Connections page's types."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_connection_sql_page import shop
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401


def test_a_new_query_runs_on_the_grids_or_on_a_connection(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path_factory: Any
) -> None:
    shop(server, tmp_path_factory.mktemp("shop_query_from"))
    page = open_grid(browser, orders_url)
    page.get_by_role("button", name="New table from a query").click()
    view = page.locator("#query-view")
    source = view.get_by_role("combobox", name="Query from")
    expect(source).to_have_value("")  # Grids, the open tables
    expect(source.locator("option", has_text="Shop")).to_have_count(1)

    # Add a connection…: the Connections page's types; the picker stays where it was.
    source.select_option(label="Add a connection…")
    types = page.locator(".area-page[data-page='connections']")
    expect(types).to_be_visible(timeout=10000)
    page.go_back()  # the page closes as the browser's Back closes every page of the rail's
    expect(types).to_be_hidden(timeout=10000)
    expect(source).to_have_value("")

    # A connection: its own SQL, run there.
    source.select_option("Shop")
    expect(view.locator(".sql-status")).to_contain_text("Runs on Shop")
    view.get_by_role("textbox", name="Name of the new table").fill("shop_north")
    editor = view.locator(".sql-editor .monaco-editor, .sql-editor textarea").first
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("SELECT order_id, amount FROM orders WHERE region = 'North' ORDER BY order_id")
    view.get_by_role("button", name="Run", exact=True).click()

    tab = page.locator(".tab-item", has_text="shop_north")
    expect(tab).to_have_attribute("aria-selected", "true", timeout=20000)
    pane = page.locator(".pane.active")
    expect(pane.locator(".ag-row")).to_have_count(2, timeout=15000)
    expect(pane.locator(".query-tray .query-from")).to_have_text("on Shop")

    # Run again runs on Shop, not the grids (orders is Shop's table, not an open grid's name).
    tray_editor = pane.locator(
        ".query-tray .sql-editor .monaco-editor, .query-tray .sql-editor textarea"
    ).first
    tray_editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("SELECT order_id FROM orders")
    pane.get_by_role("button", name="Run", exact=True).click()
    expect(pane.locator(".ag-row")).to_have_count(3, timeout=15000)
    call(server, "DELETE", "/datasets/shop_north")
