"""Tables coming into the Blazor Grids page (the classic openFile.ts, openMenu.ts, renameTable.ts): Open file…
by a typed path, a pasted table named for the time with its Pasted as box, and the Tables list (open and
closed tables, Open, Remove asked first, the Python sessions)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page


def test_open_file_paste_and_the_tables_list(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    made_up = server["tmp"] / "made_up_regions.csv"
    made_up.write_text("region,target\nNorth,10\nSouth,20\n", encoding="utf-8")
    page = open_page(browser, server, "grids")
    page.get_by_role("button", name="Open file…").click()
    # No system dialog in a test: the page's own picker.
    choose_path(page, made_up)
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("made_up_regions")
    expect(page.locator(".status-rows")).to_contain_text("of 2")

    # Ctrl+V of a table anywhere but a box: a new table, its name in the Pasted as box.
    page.locator(".ag-root").first.click()
    page.evaluate(
        """() => {
            const data = new DataTransfer();
            data.setData('text/plain', 'city\\tvisits\\nNorthvale\\t3\\nWestmere\\t5\\n');
            document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true }));
        }"""
    )
    box = page.locator(".toast-name")
    expect(box).to_have_value(__import__("re").compile(r"^pasted_\d{6}"))
    box.fill("visits_by_city")
    box.press("Enter")
    expect(page.locator(".grid-tab.tab-item", has_text="visits_by_city")).to_be_visible()

    # The Tables list: open tables, a closed one opened again, Remove asked first.
    page.get_by_role("button", name="Tables", exact=True).click()
    tables = page.locator(".dialog")
    expect(tables).to_contain_text("tables ·")
    expect(tables.locator("#open-tables")).to_contain_text("visits_by_city")
    expect(tables).to_contain_text("No Python sessions")
    tables.get_by_role("button", name="Remove visits_by_city").click()
    page.locator(".dialog").last.get_by_role("button", name="OK").click()
    expect(page.locator(".dialog").first).not_to_contain_text("visits_by_city")
    assert not any(d["name"] == "visits_by_city" for d in call(server, "GET", "/datasets")["datasets"])
    page.close()
