"""The New query page and a query's tray on the Blazor Grids page (the classic startView.ts and queryTab.ts): Open
tables (DuckDB) opens the draft (its own tab), Run builds the table, whose tab keeps the tray to run again."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_a_new_query_builds_a_table_and_runs_again(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "grids?new=1")
    expect(page.locator(".new-query-title")).to_have_text("New query")
    page.locator(".new-query-choice", has_text="Open tables (DuckDB)").click()
    expect(page.locator(".tab-draft")).to_contain_text("query")
    tray = page.locator(".query-tray")
    expect(tray).to_contain_text("New table")
    expect(tray.get_by_label("Query from")).to_have_value("")
    page.get_by_label("Name of the new table").fill("made_up_big_orders")
    editor = tray.locator(".monaco-editor").first
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("SELECT * FROM orders WHERE amount > 100")
    tray.get_by_role("button", name="Run").click()
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("made_up_big_orders")
    expect(page.locator(".note-corner")).to_contain_text("Built made_up_big_orders")
    built = page.locator(".pane .query-tray")
    expect(built).to_contain_text("Query")
    built.get_by_role("button", name="Run").click()
    expect(built.locator(".sql-status")).to_contain_text("in made_up_big_orders (version 2)")
    page.close()
