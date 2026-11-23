"""The Catalog page's tree with nothing typed (the classic dataBrowse.ts): a made-up DuckDB connection with
its state, its tables and their columns read when one opens, the open tables' section, a table's detail
beside the tree (its SQL name, where it comes from, its columns, the code that reads it), the arrow keys,
Show only this."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page
from tests.e2e.blazor.test_grid_connection_swap import add_duckdb, made_up_shop


def test_the_catalog_browses_its_tree(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    shop = made_up_shop(server["tmp"] / "browse_ledger.duckdb", 5)
    page = open_page(browser, server, "connections")
    add_duckdb(page, "BrowseBooks", shop)
    page.goto(page.url.split("/blazor/")[0] + "/blazor/catalog")
    tree = page.get_by_role("tree", name="Data")
    connection = tree.locator(".db-node.kind-connection", has_text="BrowseBooks")
    expect(connection).to_be_visible()
    if connection.get_by_role("button", name="Load").count():
        connection.get_by_role("button", name="Load").click()
    expect(connection.locator(".db-status").first).to_contain_text("table", timeout=20_000)

    # The open tables' section: a table's columns under it, its detail beside the tree.
    section = tree.locator(".db-node.kind-section", has_text="Open tables")
    customers = section.locator(".db-node.kind-table", has_text="customers").first
    customers.locator(".db-line").first.click()
    detail = page.get_by_role("complementary", name="Table")
    expect(detail).to_contain_text("customers")
    expect(detail.get_by_role("table", name="Columns")).to_contain_text("customer_id")
    expect(detail).to_contain_text("Python cell")
    page.keyboard.press("ArrowRight")
    expect(customers.locator(".db-node.kind-column", has_text="customer_id")).to_be_visible()

    # A connection's table: its columns read when it opens, its detail read from the connection.
    ledger = connection.locator(".db-node.kind-table", has_text="ledger").first
    if not ledger.is_visible():
        connection.locator(".db-caret").first.click()
    ledger.locator(".db-caret").first.click()
    expect(ledger.locator(".db-node.kind-column", has_text="entry_id")).to_be_visible()
    ledger.locator(".db-line").first.click()
    expect(detail).to_contain_text("SQL name")
    expect(detail).to_contain_text("From")
    expect(detail.get_by_role("table", name="Columns")).to_contain_text("amount")

    # Show only this: the connection picker set to it.
    connection.locator(".db-line").first.hover()
    connection.get_by_role("button", name="Show only this").first.click()
    expect(page.get_by_label("Connection", exact=True)).to_have_value("BrowseBooks")
    expect(tree.locator(".db-node.kind-section", has_text="Open tables")).to_have_count(0)
    page.close()
