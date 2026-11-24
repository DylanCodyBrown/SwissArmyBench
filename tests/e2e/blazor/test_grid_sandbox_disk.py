"""A sandbox table's grid and a file changed on disk on the Blazor Grids page (the classic sandboxGrid.ts and
fileChanged.ts): the sandbox bar with its designation, a cell edited in place, Add row, Delete rows and
Reset; a table read from a file that changed on disk, its tab's dot and its pane's Reload and Not now."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_a_sandbox_grid_edits_adds_deletes_and_resets(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    call(server, "POST", "/project/new", {"name": "made_up_sandbox_shop"})
    made = call(server, "POST", "/sandbox/tables/variant", {"from": "grid", "table": "products"})
    call(server, "POST", "/sandbox/tables/open", {"table": made["added"]})
    grid = next(
        g["grid"]
        for g in call(server, "GET", "/grids")["grids"]
        if g["dataset"] == f"sandbox_{made['added']}"
    )
    page = open_page(browser, server, f"tables?grid={grid}")
    bar = page.locator(".sandbox-bar")
    expect(bar).to_contain_text("products · sandbox")
    expect(bar).to_contain_text("Local test data, never live")
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("products · sandbox")

    # A cell edited in place: Enter writes it.
    cell = page.locator(".ag-row[row-index='0'] .ag-cell[col-id=product]")
    expect(cell).not_to_have_text("")
    cell.dblclick()
    box = page.get_by_label("product, row 1")
    box.fill("Made-up widget")
    box.press("Enter")
    expect(cell).to_have_text("Made-up widget")

    # Add row, then Delete rows with none selected says what to do.
    bar.get_by_role("button", name="Add row").click()
    dialog = page.locator(".dialog")
    expect(dialog).to_contain_text(f"Add a row to {made['added']}")
    dialog.get_by_label("product", exact=True).fill("Made-up gadget")
    dialog.locator(".dialog-foot").get_by_role("button", name="Add").click()
    expect(page.locator(".status-rows")).to_contain_text("of 9")
    page.keyboard.press("Escape")
    bar.get_by_role("button", name="Delete rows").click()
    expect(page.locator(".error-note")).to_contain_text("Select the rows to delete first")

    bar.get_by_role("button", name=f"Reset {made['added']}").click()
    expect(page.locator(".status-rows")).to_contain_text("of 8")
    expect(cell).not_to_have_text("Made-up widget")
    page.close()


def test_a_file_changed_on_disk_offers_reload(browser: Browser, server: dict[str, Any]) -> None:
    made_up = server["tmp"] / "made_up_targets.csv"
    made_up.write_text("region,target\nNorth,10\n", encoding="utf-8")
    call(server, "POST", "/datasets/made_up_targets/load", {"path": str(made_up)})
    grid = next(
        g["grid"] for g in call(server, "GET", "/grids")["grids"] if g["dataset"] == "made_up_targets"
    )
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".status-rows")).to_contain_text("of 1")
    # The server looks at a watched file every few seconds: its first look keeps the file as it was read.
    page.wait_for_timeout(4_000)
    made_up.write_text("region,target\nNorth,10\nSouth,20\n", encoding="utf-8")
    bar = page.locator(".file-changed")
    expect(bar).to_contain_text("Changed on disk", timeout=30_000)
    expect(page.locator(".grid-tab.tab-item.current .tab-changed")).to_be_visible()
    bar.get_by_role("button", name="Reload").click()
    expect(page.locator(".status-rows")).to_contain_text("of 2")
    expect(page.locator(".file-changed")).to_have_count(0)
    expect(page.locator(".note-corner")).to_contain_text("made_up_targets updated to version")
    # A link to a grid that closed since says so (a Session entry's Go to it).
    call(server, "DELETE", f"/grids/{grid}")
    page.goto(page.url)
    expect(page.locator(".note-corner")).to_contain_text("It is not open any more.")
    page.close()
