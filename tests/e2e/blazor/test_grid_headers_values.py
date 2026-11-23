"""The Blazor Grids page's headers, values and steps (the classic gridView.ts headers, headerCard.ts,
valueViewer.ts, cellMenu.ts, profileView.ts, stepsStrip.ts, stepsPanel.ts) on the made-up sample store."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, ViewportSize, expect

from tests.e2e.blazor.conftest import call, open_page

WIDE: ViewportSize = {"width": 1900, "height": 900}


def orders(server: dict[str, Any]) -> str:
    made = call(server, "POST", "/samples/store", {})
    return str(next(t["grid"] for t in made["tables"] if t["name"].startswith("orders")))


def test_a_header_rests_renames_and_the_corner_selects_all(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.set_viewport_size(WIDE)
    header = page.locator(".ag-header-cell[col-id=status] .sab-header")
    expect(header).to_be_visible()
    header.hover()
    card = page.locator(".header-card")
    expect(card).to_contain_text("status")
    expect(card).to_contain_text("Distinct")
    page.mouse.move(5, 5)
    expect(card).to_have_count(0)

    # The corner: Select all, and the column profiles in the headers.
    page.click(".sab-corner")
    expect(page.locator(".status-selection")).to_contain_text("Count")
    page.click(".sab-corner-profiles")
    expect(page.locator(".ag-header-cell[col-id=status] .sab-header-stats")).to_contain_text("distinct")
    page.click(".sab-corner-profiles")

    # A double-click on a name renames it there: a rename step.
    header.dblclick()
    box = page.get_by_label("New name for status")
    box.fill("state")
    box.press("Enter")
    expect(page.locator(".steps-strip")).to_contain_text("state")
    step = call(server, "GET", f"/grids/{grid}")["steps"][-1]
    assert step["kind"] == "rename" and step["params"]["mapping"] == {"status": "state"}
    page.close()


def test_a_cells_value_and_the_analyze_sends(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.set_viewport_size(WIDE)
    cell = page.locator(".ag-row[row-index='0'] .ag-cell[col-id=status]")
    expect(cell).not_to_have_text("")
    cell.dblclick()
    viewer = page.locator(".dialog")
    expect(viewer).to_contain_text("status, row 1")
    expect(viewer.locator(".badge")).to_contain_text("Text")
    viewer.get_by_role("button", name="Send to Analyze").click()
    expect(page.locator(".note-corner")).to_contain_text("On the Analyze board: a note.")
    viewer.locator(".dialog-foot").get_by_role("button", name="Close").click()

    cell.click(button="right")
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Send the row to Analyze")
    menu.get_by_role("menuitem", name="Send the row to Analyze").click()
    expect(page.locator(".note-corner")).to_contain_text("On the Analyze board")

    # A header's menu: Profile… opens the column's profile; Profile to Analyze sends it.
    page.click(".ag-header-cell[col-id=amount] .sab-header-name", button="right")
    page.get_by_role("menuitem", name="Profile…").click()
    profile = page.locator(".dialog")
    expect(profile).to_contain_text("Profile of amount")
    expect(profile.locator(".stat-grid")).to_contain_text("Median")
    expect(profile).to_contain_text("Distribution")
    profile.get_by_label("Column to profile").select_option("status")
    expect(profile).to_contain_text("Profile of status")
    profile.get_by_role("button", name="Send to Analyze").click()
    expect(page.locator(".note-corner")).to_contain_text("On the Analyze board")
    cards = call(server, "GET", f"/grids/{grid}/cards")
    assert any(
        "Profile of status" in str(c)
        for c in (cards.get("cards", cards) if isinstance(cards, dict) else cards)
    )
    page.close()


def test_the_steps_panel_previews_and_undo_brings_a_step_back(
    browser: Browser, server: dict[str, Any]
) -> None:
    grid = orders(server)
    call(
        server,
        "POST",
        f"/grids/{grid}/step-ops",
        {"op": "add", "step": {"kind": "limit", "params": {"n": 10}}},
    )
    page = open_page(browser, server, f"grids?grid={grid}")
    strip = page.locator(".steps-strip")
    expect(strip).to_contain_text("Keep the first 10 rows")
    page.click("[data-tool=view-steps]")
    panel = page.locator(".dialog")
    expect(panel).to_contain_text("Source: orders")
    expect(panel).to_contain_text("(120 rows, version")
    expect(panel).to_contain_text("120 → 10 rows")
    panel.locator(".step:not(.source) .text").first.click()
    expect(page.locator(".preview-banner")).to_contain_text("Previewing")
    expect(page.locator(".status-rows")).to_contain_text("previewing after step 1")
    panel.locator(".dialog-foot").get_by_role("button", name="Close").click()
    page.get_by_role("button", name="Back to the full view").click()
    expect(page.locator(".preview-banner")).to_have_count(0)

    # A step removed says so, with Undo; Clear the steps too.
    strip.get_by_role("button", name="Remove: Keep the first 10 rows").click()
    expect(page.locator(".note-corner")).to_contain_text("Removed the step: Keep the first 10 rows")
    page.locator(".note-corner").get_by_role("button", name="Undo").click()
    expect(strip).to_contain_text("Keep the first 10 rows")
    page.click("[data-tool=clear-steps]")
    expect(page.locator(".note-corner")).to_contain_text("Cleared the step")
    assert call(server, "GET", f"/grids/{grid}")["steps"] == []
    page.close()


def test_the_key_finder_finds_as_it_opens(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.click("[data-tool=keyfinder]")
    dialog = page.locator(".dialog")
    expect(dialog).to_contain_text("Most distinct column combination in")
    expect(dialog).to_contain_text("tells every one of all 120 rows apart")
    expect(dialog).to_contain_text("column pairs share values")
    row = dialog.locator(".kf-row", has_text="customer_id").first
    row.click()
    expect(dialog.locator(".kf-sample")).to_contain_text("shared")
    row.get_by_role("button", name="Add as relationship").click()
    expect(row.get_by_role("button", name="Add as relationship")).to_be_disabled()
    assert any(
        r["from_columns"] == ["customer_id"] for r in call(server, "GET", "/relationships")["relationships"]
    )
    dialog.get_by_role("button", name="Send to Analyze").click()
    expect(page.locator(".note-corner")).to_contain_text("On the Analyze board")
    page.close()
