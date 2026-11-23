"""The Blazor front end's ERD (Find relationships among the made-up sample store, Add one, the Mermaid
diagram, Delete), the Catalog's search and the Environment's tables with Open."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_find_add_and_draw_a_relationship(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store")
    page = open_page(browser, server, "erd")
    page.click("text=All tables")
    page.click("text=Find relationships")
    row = page.locator(".erd-found tr", has_text="orders.customer_id")
    row.locator("button:has-text('Add')").click()
    expect(page.locator(".erd-joins")).to_contain_text("customers")
    expect(page.locator(".erd-diagram svg")).to_be_visible()
    page.locator(".erd-joins button:has-text('Delete')").first.click()
    expect(page.locator(".erd-joins")).to_have_count(0)
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
