"""The Blazor front end's Connections page and Grids page, on a made-up DuckDB file: Add connection's kinds,
the DuckDB form (its path written into the code by the server), Test, Save, the card and its detail with
its tables, Open a table as a grid; the grid's rows paged from the server, a column's card and its Keep
rows step, the steps strip, Undo."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def made_up_shop(folder: Path) -> Path:
    path = folder / "shop.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute(
            "CREATE TABLE orders AS SELECT i AS order_id, 1 + i % 7 AS customer_id,"
            " round(5 + i * 2.5, 2) AS amount,"
            " CASE WHEN i % 3 = 0 THEN 'open' ELSE 'shipped' END AS status FROM range(1, 251) t(i)"
        )
    return path


def test_add_a_connection_then_open_its_table_as_a_grid(browser: Browser, server: dict[str, Any]) -> None:
    shop = made_up_shop(server["tmp"])
    page = open_page(browser, server, "connections")
    page.click("text=Add connection")
    page.click(".kind-card[data-kind=duckdb]")
    page.fill(".connection-name", "Shop")
    path = page.locator(".connection-field[data-field=path]")
    path.fill(str(shop))
    path.press("Tab")  # the change: the server writes the path into the code
    expect(page.locator(".connection-code pre")).to_contain_text("shop.duckdb")
    page.click("button:has-text('Test')")
    expect(page.locator(".status-ok")).to_contain_text("It works")
    page.click("button:has-text('Save')")
    expect(page.locator("h1")).to_contain_text("Shop")
    expect(page.locator(".connection-tables")).to_contain_text("[Shop].orders")

    page.locator(".connection-tables tr", has_text="orders").locator("button:has-text('Open')").click()
    expect(page.locator(".grid-title")).to_contain_text("orders")
    expect(page.locator(".ag-row").first).to_be_visible()
    expect(page.locator(".status-rows")).to_contain_text("of 250")

    # A column's profile (the header menu's Profile…); a value clicked there filters to it.
    page.click(".ag-header-cell[col-id=status] .sab-header-name", button="right")
    page.click(".context-menu .menu-item:has-text('Profile…')")
    expect(page.locator(".dialog")).to_contain_text("Profile of status")
    expect(page.locator(".dialog .stat-grid")).to_contain_text("Distinct")
    page.locator(".dialog .bar-row", has_text="open").first.click()
    expect(page.locator(".steps-strip")).to_contain_text("status")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".status-rows")).to_contain_text("of 83 (")
    grid = call(server, "GET", "/grids")["grids"][0]["grid"]
    assert any(s["kind"] == "filter" for s in call(server, "GET", f"/grids/{grid}")["steps"])

    page.click("[data-tool=undo]")
    expect(page.locator(".steps-strip")).not_to_contain_text("status")
    page.click(".nav-rail-item[data-area=connections]")
    expect(page.locator(".connection-card[data-name=Shop]")).to_contain_text("Works")
    page.close()


def test_a_python_connections_three_boxes(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "connections?kind=python")
    form = page.locator(".python-form")
    expect(form.locator(".python-box .monaco-editor")).to_have_count(3)
    expect(form.locator("[data-box=connect] .monaco-editor")).to_contain_text("class Api")
    # The variables the starter's code reads, each not set on this computer yet.
    expect(form.locator(".python-variable[data-variable=ORDERS_API_URL]")).to_contain_text("Not set")
    form.locator(".connection-name").fill("Made-up shop")
    form.locator("button:has-text('Save')").click()
    expect(page).to_have_url(re.compile(r"connections\?name=Made-up(%20| )shop"))
    saved = call(server, "GET", "/connections/Made-up shop".replace(" ", "%20"))
    assert "class Api" in saved["code"] and saved["read"]["command"]
    page.close()
