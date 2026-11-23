"""The Blazor front end's ERD (Find relationships among the made-up sample store in the Relationships window,
the Mermaid diagram, a join deleted with Undo), the Catalog's search and the Environment's tables with
Open."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_find_add_and_draw_a_relationship(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store")
    page = open_page(browser, server, "erd")
    expect(page.locator(".erd-empty")).to_contain_text("No relationships yet.")
    page.locator(".erd-empty").get_by_role("button", name="Find relationships").click()
    # The window opens with its finder running: the confident joins are added at once, with one Undo.
    window = page.locator(".dialog")
    expect(window).to_contain_text("joins across")
    expect(page.locator(".note-corner")).to_contain_text("found in the data")
    expect(window.locator(".rel-table")).to_contain_text("customers")
    window.locator(".dialog-foot").get_by_role("button", name="Close").click()
    expect(page.locator(".erd-diagram svg")).to_be_visible()
    expect(page.get_by_role("button", name="Actual size")).to_be_visible()

    # Manage relationships: one deleted, with Undo.
    page.get_by_role("button", name="Manage relationships").click()
    window = page.locator(".dialog")
    first = window.locator(".rel-table tbody tr").first
    first.get_by_role("button", name=__import__("re").compile("More for")).click()
    page.locator(".context-menu").get_by_role("menuitem", name="Delete").click()
    expect(page.locator(".note-corner")).to_contain_text("Deleted 1 relationship.")
    page.close()


def test_catalog_search_and_environment_open(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "catalog")
    page.fill(".catalog-search", "cust")
    expect(page.locator(".catalog-rows").first).to_contain_text("customers")
    page.click(".nav-rail-item[data-area=environment]")
    row = page.locator(".environment-rows tr", has_text="orders").first
    expect(row).to_contain_text("Table")
    row.locator("button:has-text('Open')").click()
    expect(page.locator(".grid-title")).to_contain_text("orders")
    page.close()


def test_the_environments_viewer_and_add_variable(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    # A structure's row says "open" in words where a table's says true: both read (a fix of part one).
    call(server, "POST", "/structures", {"kind": "object", "name": "made_up_regions", "value": {"north": 1}})
    page = open_page(browser, server, "environment?at=tables")
    page.locator(".environment-name", has_text="orders").first.click()
    viewer = page.locator(".environment-viewer")
    expect(viewer).to_contain_text("amount")
    expect(viewer).to_contain_text("Used in")

    page.goto(page.url.split("/blazor/")[0] + "/blazor/environment?at=settings")
    page.click("button:has-text('Add variable…')")
    page.fill(".dialog input[aria-label=Name]", "made_up_region")
    expect(page.locator(".dialog input[aria-label=Name]")).to_have_value("MADE_UP_REGION")
    page.fill(".dialog input[aria-label=Value]", "North")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".environment-rows")).to_contain_text("MADE_UP_REGION")
    names = [v["name"] for v in call(server, "GET", "/variables")["variables"]]
    assert "MADE_UP_REGION" in names
    page.close()
