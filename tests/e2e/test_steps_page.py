# ruff: noqa: F811
"""The steps on the grid page (the usability test's decision 17): Ctrl+Z undoes the last step change
and Ctrl+Y or Ctrl+Shift+Z redoes it, unless the cursor is in a text box; the strip counts a header
sort as a step; and hovering "N steps" lists the steps in plain words, each with a remove button."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import (  # noqa: F401
    browser,
    call,
    demo_frame,
    grid_of,
    open_grid,
    server,
    wait_for_cell,
)


def keep_north(page: Page) -> None:
    page.locator(".ribbon").get_by_role("button", name="Filter", exact=True).click()
    dialog = page.locator("dialog")
    dialog.get_by_label("Column", exact=True).select_option("region")
    dialog.get_by_label("Condition").select_option("eq")
    dialog.get_by_label("Value", exact=True).fill("North")
    dialog.get_by_role("button", name="Add step").click()
    expect(page.locator("#status")).to_contain_text("of 100")


def test_undo_redo_keys_a_header_sort_counted_and_the_steps_listed_on_hover(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(demo_frame(600), name="steps_orders", new_grid=True)
    page = open_grid(browser, url)
    strip = page.locator(".steps-strip")
    count = strip.locator(".steps-count")
    status = page.locator("#status")
    try:
        keep_north(page)
        expect(count).to_have_text("1 step")
        # A sort made by clicking a header is a step, and the strip counts it.
        sort = page.locator(".ag-header-cell[col-id='order_id'] .sab-header-sort")
        sort.click()
        sort.click()
        wait_for_cell(page, 0, "order_id", "595")
        expect(count).to_have_text("2 steps")

        # Hovering the count lists the steps in plain words, each with a remove button.
        count.hover()
        listed = strip.locator(".steps-list li")
        expect(listed).to_have_count(2)
        expect(listed.locator(".steps-words")).to_have_text(
            ["Keep rows where region equals 'North'", "Sort by order_id descending"]
        )
        # One action on the list: its remove button takes that step out, and the list stays for the next.
        listed.first.get_by_role("button", name="Remove: Keep rows where region equals 'North'").click()
        expect(status).to_contain_text("of 600")
        expect(count).to_have_text("1 step")
        wait_for_cell(page, 0, "order_id", "600")

        # Ctrl+Z takes back the last change to the steps, whatever it was: here, the removal.
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.keyboard.press("Control+z")
        expect(count).to_have_text("2 steps")
        expect(status).to_contain_text("of 100")
        page.keyboard.press("Control+z")  # the header's second click: back to ascending
        expect(page.locator(".ag-header-cell[col-id='order_id']")).to_have_attribute("aria-sort", "ascending")
        expect(count).to_have_text("2 steps")
        page.keyboard.press("Control+z")  # its first click: no header sort
        expect(count).to_have_text("1 step")
        wait_for_cell(page, 0, "order_id", "1")
        expect(page.locator(".ag-header-cell[col-id='order_id']")).to_have_attribute("aria-sort", "none")
        page.keyboard.press("Control+z")  # the filter
        expect(count).to_have_count(0)
        expect(status).to_contain_text("of 600")
        page.keyboard.press("Control+z")  # nothing left to undo: nothing happens, nothing is said
        expect(strip.get_by_role("button", name="Undo", exact=True)).to_be_disabled()
        expect(page.locator(".toast.error")).to_have_count(0)

        # Ctrl+Y and Ctrl+Shift+Z redo.
        page.keyboard.press("Control+y")
        expect(count).to_have_text("1 step")
        expect(status).to_contain_text("of 100")
        page.keyboard.press("Control+Shift+z")
        expect(count).to_have_text("2 steps")
        page.keyboard.press("Control+Shift+z")
        wait_for_cell(page, 0, "order_id", "595")
        expect(strip.get_by_role("button", name="Redo", exact=True)).to_be_enabled()  # the removal
        # The strip's buttons do the same.
        header = page.locator(".ag-header-cell[col-id='order_id']")
        strip.get_by_role("button", name="Undo", exact=True).click()
        expect(header).to_have_attribute("aria-sort", "ascending")
        strip.get_by_role("button", name="Redo", exact=True).click()
        expect(header).to_have_attribute("aria-sort", "descending")
        expect(count).to_have_text("2 steps")

        # In a text box the keys are the box's own: the steps stay as they are.
        tab = page.locator(f".tab-item[data-grid='{grid_of(url)}']")
        tab.locator(".tab-label").dblclick()
        box = tab.locator("input.tab-rename")
        box.press_sequentially("x")
        box.press("Control+z")
        page.wait_for_timeout(400)
        expect(count).to_have_text("2 steps")
        box.press("Escape")
        steps = call(server, "GET", f"/grids/{grid_of(url)}")["steps"]
        assert [s["kind"] for s in steps] == ["filter", "sort"]
    finally:
        page.close()
