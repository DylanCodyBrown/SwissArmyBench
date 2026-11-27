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
    expect(page.locator(".erd-empty")).to_contain_text("No relationships yet")
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
    # Typed on the Catalog page: the same tree, narrowed to what matches (the classic dataBrowse.ts).
    expect(page.locator(".db-tree")).to_contain_text("customers")
    page.click(".nav-rail-item[data-area=environment]")
    row = page.locator(".env-row[data-name=orders]").first
    expect(row).to_contain_text("In 1 tab")
    row.dblclick()
    expect(page.locator(".grid-title")).to_contain_text("orders")
    page.close()


def test_the_environments_viewer_and_add_variable(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    # A structure's row says "open" in words where a table's says true: both read (a fix of part one).
    call(server, "POST", "/structures", {"kind": "object", "name": "made_up_regions", "value": {"north": 1}})
    page = open_page(browser, server, "environment?at=tables")
    page.locator(".env-row[data-name=orders]").first.click()
    viewer = page.locator(".env-side")
    expect(viewer).to_contain_text("orders")
    expect(viewer).to_contain_text("Used in")
    page.locator(".env-row[data-name=orders] .env-twist").first.click()
    expect(page.locator(".env-child").first).to_be_visible()

    page.goto(page.url.split("/blazor/")[0] + "/blazor/environment?at=settings")
    page.click("button:has-text('Add a setting…')")
    page.fill(".dialog input[aria-label=Name]", "made_up_region")
    expect(page.locator(".dialog input[aria-label=Name]")).to_have_value("MADE_UP_REGION")
    page.fill(".dialog input[aria-label=Value]", "North")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".env-list")).to_contain_text("MADE_UP_REGION")
    names = [v["name"] for v in call(server, "GET", "/variables")["variables"]]
    assert "MADE_UP_REGION" in names
    page.close()


def test_the_pages_say_tab_and_catalog(browser: Browser, server: dict[str, Any]) -> None:
    """Words a person reads (the owner, 2026-11-23: Grids is Tables, a view of a table is a tab; 2026-11-21:
    the Data page is the Catalog): the Environment's Used in marks a table's tab as Tab, never Grid, and Find
    data's way to the Catalog page says Catalog."""
    made = call(server, "POST", "/samples/store")
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = open_page(browser, server, "environment")
    page.locator(".env-row[data-name=orders]").first.click()
    mark = page.locator(
        ".env-tag", has=page.locator("xpath=following-sibling::button[@data-used-kind='grid']")
    )
    expect(mark.first).to_have_text("Tab")
    page.close()

    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()
    page.keyboard.press("Control+k")
    way = page.locator(".dialog .dialog-foot a[href=catalog]")
    expect(way).to_have_text("Open the Catalog page")
    expect(way).to_have_attribute("title", "The Catalog page, with this search")
    page.close()
