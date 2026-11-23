"""The Blazor Grids page's tabs, split and compare (the classic panes.ts, compare.ts, compareDialog.ts and the
ribbon's Compare row) on the made-up sample store: a tab's menu, Compare with… putting two grids side by side, the
key picker (the Key Finder's pairs, the suggested key ticked), the grids lined up and scrolling together, the modes,
Stop compare and Close this side; a tab closed and reopened with Undo; a tab renamed in place."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def store(server: dict[str, Any]) -> dict[str, str]:
    made = call(server, "POST", "/samples/store", {})
    return {t["name"].split("_")[0]: t["grid"] for t in made["tables"]}


def test_compare_with_lines_two_grids_up(browser: Browser, server: dict[str, Any]) -> None:
    grids = store(server)
    page = open_page(browser, server, f"grids?grid={grids['orders']}")
    page.set_viewport_size({"width": 1500, "height": 900})
    orders_tab = page.locator(f".grid-tab[data-grid='{grids['orders']}']")
    orders_tab.click(button="right")
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Compare with…")
    expect(menu).to_contain_text("Rename")
    menu.get_by_role("menuitem", name="Compare with…").click()
    page.locator(".context-menu").get_by_role("menuitem", name="customers").first.click()

    # The key picker: the Key Finder's pairs, the suggested key ticked.
    dialog = page.locator(".dialog")
    expect(dialog).to_contain_text("Compare orders with customers")
    expect(dialog).to_contain_text("column pairs share values")
    expect(dialog.get_by_label("Use customer_id = customer_id as a key")).to_be_checked()
    expect(page.locator(".pane")).to_have_count(2)
    expect(page.locator(".ribbon")).to_contain_text("orders and customers side by side")
    dialog.get_by_role("button", name="Compare", exact=True).click()

    ribbon = page.locator(".ribbon")
    expect(ribbon).to_contain_text("120 matched · 0 only in orders · 0 only in customers")
    expect(page.locator("[data-tool=cmp-outer]")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".note-corner")).to_contain_text("Aligned on customer_id")
    compare = call(server, "GET", "/compares")["compares"][0]
    assert compare["keys"] == [["customer_id", "customer_id"]] and compare["mode"] == "outer"

    # Aligned: the two grids keep one vertical position.
    scrollers = page.locator(".pane .ag-grid-viewport")
    scrollers.nth(0).evaluate("e => { e.scrollTop = 600; e.dispatchEvent(new Event('scroll')); }")
    page.wait_for_function("() => document.querySelectorAll('.pane .ag-grid-viewport')[1].scrollTop >= 590")

    # A mode, and the anti join's sides.
    page.click("[data-tool=cmp-anti]")
    expect(page.locator("[data-tool=cmp-anti]")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("[data-tool=cmp-side-left]")).to_contain_text("Only in orders")
    page.click("[data-tool=cmp-diff]")
    expect(ribbon).to_contain_text("matched rows differ")
    expect(page.locator("[data-tool=cmp-options]")).to_be_visible()
    page.click("[data-tool=cmp-options]")
    expect(page.locator(".dialog")).to_contain_text("How values compare")
    page.get_by_label("Ignore letter case").check()
    page.locator(".dialog-foot").get_by_role("button", name="Apply").click()
    page.wait_for_function("() => !document.querySelector('.dialog')")
    assert call(server, "GET", "/compares")["compares"][0]["diff"]["ignore_case"] is True

    page.click("[data-tool=cmp-stop]")
    expect(ribbon).to_contain_text("orders and customers side by side")
    assert call(server, "GET", "/compares")["compares"] == []

    # Close this side: back to one grid.
    page.locator(".pane").first.get_by_role("button", name="Close this side").click()
    expect(page.locator(".pane")).to_have_count(1)
    expect(page.locator(".ribbon")).not_to_contain_text("Compare")
    page.close()


def test_a_tab_closes_with_undo_and_renames_in_place(browser: Browser, server: dict[str, Any]) -> None:
    grids = store(server)
    page = open_page(browser, server, f"grids?grid={grids['products']}")
    tab = page.locator(f".grid-tab[data-grid='{grids['products']}']")
    expect(tab).to_be_visible()
    tab.get_by_role("button", name="Close products").click()
    expect(page.locator(".note-corner")).to_contain_text("Closed products")
    page.locator(".note-corner").get_by_role("button", name="Undo").click()
    expect(page.locator(".grid-tab.tab-item", has_text="products").first).to_be_visible()

    # F2 on a tab renames its table in place; Enter keeps the new name.
    reopened = page.locator(".grid-tab.tab-item", has_text="products").first
    reopened.click()
    reopened.press("F2")
    box = page.get_by_label("New name for products")
    box.fill("products_renamed")
    box.press("Enter")
    expect(page.locator(".grid-tab.tab-item", has_text="products_renamed")).to_be_visible()
    assert any(g["dataset"] == "products_renamed" for g in call(server, "GET", "/grids")["grids"])
    page.close()
