"""The grid page's pop-out windows (the owner's design: separate windows; the classic ?panel=steps,
?panel=keys and ?panel=connsql), the Analyze page taking an analysis in its address with the palette's
Analyze entries, and the Catalog's typed search as a narrowed tree, on the made-up sample store."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_steps_and_the_key_finder_open_in_their_own_windows(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    call(server, "POST", f"/grids/{grid}/step-ops", {"op": "add", "step": {"kind": "distinct", "params": {}}})
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".steps-strip")).to_contain_text("Keep distinct rows")
    with page.context.expect_page() as opened:
        page.locator(".steps-strip").get_by_role("button", name="View steps").click()
    steps = opened.value
    steps.wait_for_selector(".panel-window", timeout=60_000)
    expect(steps.locator(".window-top")).to_contain_text("orders")
    expect(steps.get_by_role("dialog", name="Transformations")).to_contain_text("Keep distinct rows")
    # A step taken off in the window: the grid page hears it.
    steps.get_by_role("button", name="Delete").first.click()
    expect(page.locator(".steps-strip")).not_to_contain_text("Keep distinct rows")
    steps.close()

    with page.context.expect_page() as opened:
        page.locator(".ribbon").get_by_role("button", name="Key Finder").click()
    keys = opened.value
    keys.wait_for_selector(".panel-window", timeout=60_000)
    expect(keys.get_by_role("dialog")).to_contain_text("Key Finder: orders")
    keys.close()
    page.close()


def test_the_analyze_address_and_the_palettes_analyses(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    first = call(server, "GET", "/analyze")["analyses"][0]
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()
    page.locator(".ag-root").first.click()
    page.keyboard.press("Control+Shift+P")
    palette = page.get_by_role("dialog", name="Command palette")
    page.keyboard.type(f"{first['label']} ({first['name']})")
    entry = palette.locator(".wb-palette-item").first
    expect(entry).to_contain_text(first["label"])
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/analyze?analysis={first['id']}*")
    assert f"table={grid}" in page.url
    expect(page.locator(".analyze-page")).to_contain_text(first["label"])
    page.close()


def test_the_catalogs_typed_search_narrows_the_tree(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "catalog")
    expect(page.locator(".db-tree")).to_be_visible()
    page.get_by_label("Find data: tables, columns, connections").fill("customer_id")
    tree = page.locator(".db-tree")
    expect(tree).to_be_visible()
    expect(tree.get_by_role("treeitem").filter(has_text="customer_id").first).to_be_visible()
    page.get_by_label("Find data: tables, columns, connections").fill("nothing like this at all")
    expect(page.locator(".empty-note")).to_have_text("Nothing matches")
    page.close()
