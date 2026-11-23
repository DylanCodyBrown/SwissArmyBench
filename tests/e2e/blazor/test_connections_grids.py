"""The Blazor front end's Connections page and Grids page, on a made-up DuckDB file: Add connection's kinds,
the DuckDB form (its path written into the code by the server), Test, Save, the card and its detail with
its tables, Open a table as a grid; the grid's rows paged from the server, a column's card and its Keep
rows step, the steps strip, Undo."""

from __future__ import annotations

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
    expect(page.locator(".grid-title-row")).to_contain_text("250 rows")

    page.click(".ag-header-cell[col-id=status] .sab-header-name")
    expect(page.locator(".column-card")).to_contain_text("Distinct")
    page.select_option(".keep-rows select", "eq")
    page.fill(".keep-rows input", "open")
    page.click(".keep-rows button")
    expect(page.locator(".steps-strip")).to_contain_text("Keep rows where status equals 'open'")
    expect(page.locator(".grid-title-row")).to_contain_text("83 rows")
    grid = call(server, "GET", "/grids")["grids"][0]["grid"]
    assert any(s["kind"] == "filter" for s in call(server, "GET", f"/grids/{grid}")["steps"])

    page.click("button:has-text('Undo')")
    expect(page.locator(".steps-strip")).not_to_contain_text("Keep rows")
    page.click(".nav-rail-item[data-area=connections]")
    expect(page.locator(".connection-card[data-name=Shop]")).to_contain_text("Works")
    page.close()
