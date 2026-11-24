"""The command palette (Ctrl+Shift+P), the keyboard shortcuts (?) and Find data (Ctrl+K) on the Blazor Grids
page (the classic workbenchCommands.ts, gridCommands.ts and dataExplorer.ts), on the made-up sample store."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_palette_shortcuts_and_find_data(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()
    page.locator(".ag-root").first.click()
    page.keyboard.press("Control+Shift+P")
    palette = page.get_by_role("dialog", name="Command palette")
    expect(palette).to_contain_text("Keep first rows")
    page.keyboard.type("distinct rows")
    expect(palette.locator(".wb-palette-item").first).to_contain_text("Distinct rows")
    page.keyboard.press("Enter")
    expect(page.locator(".steps-strip")).to_contain_text("Keep distinct rows")
    # A command that cannot run now says why in its row.
    page.keyboard.press("Control+Shift+P")
    page.keyboard.type("steps redo")
    expect(page.locator(".wb-palette-why").first).to_contain_text("Nothing to redo")
    page.keyboard.press("Escape")
    # The cell in front: its right-click menu's entries, under Cell; Zoom 100% under Application.
    page.locator(".ag-cell").nth(1).click()
    page.keyboard.press("Control+Shift+P")
    page.keyboard.type("copy as markdown")
    expect(palette.locator(".wb-palette-item").first).to_contain_text("Copy as Markdown")
    page.keyboard.press("Escape")
    page.locator(".status-bar").get_by_role("button", name="Zoom in").click()
    page.keyboard.press("Control+Shift+P")
    page.keyboard.type("zoom 100")
    page.keyboard.press("Enter")
    expect(page.locator(".status-bar").get_by_role("group", name="Zoom")).to_contain_text("100%")

    page.locator(".ag-root").first.click()
    page.keyboard.press("?")
    sheet = page.get_by_role("dialog", name="Keyboard shortcuts")
    expect(sheet).to_contain_text("Show every command")
    page.get_by_label("Find a shortcut").fill("nothing like this")
    expect(sheet).to_contain_text("No shortcut matches.")
    page.keyboard.press("Escape")

    page.keyboard.press("Control+K")
    find = page.locator(".dialog", has_text="Find data")
    page.get_by_label("Find data: tables, columns, connections").fill("cust")
    result = find.locator(".ex-result", has_text="customers").first
    expect(result).to_be_visible()
    result.get_by_role("button", name="Open as table").click()
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("customers")
    page.close()
