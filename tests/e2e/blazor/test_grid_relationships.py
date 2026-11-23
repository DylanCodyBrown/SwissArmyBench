"""The Relationships window from the Blazor Grids ribbon (the classic relationshipsDialog.ts) on the made-up sample
store: Find relationships, the joins in use managed (filter, select, Run off, Kind, Delete selected, Undo), Save as
a set…, the saved set's Check and Apply, Export."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_relationships_window_finds_manages_and_saves(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = open_page(browser, server, f"grids?grid={grid}")
    page.click("[data-tool=relationships]")
    window = page.locator(".dialog")
    expect(window).to_contain_text("Saved sets")
    expect(window).to_contain_text("No saved sets yet.")
    expect(window).to_contain_text("No joins in use yet.")
    window.get_by_role("button", name="Find relationships").click()
    expect(window).to_contain_text("joins across")
    rows = window.locator(".rel-table tbody tr")
    expect(rows.first).to_be_visible()

    # The joins in use: filtered, one selected, Run off, then Undo from the note.
    window.get_by_label("Filter relationships").fill("customers")
    expect(window.locator(".rel-count")).to_contain_text("of")
    row = window.locator(".rel-table tbody tr", has_text="customers").first
    row.locator(".rel-col-pick input").click()
    expect(window.locator(".rel-count")).to_contain_text("1 selected")
    window.get_by_role("button", name="Run off").click()
    expect(page.locator(".note-corner")).to_contain_text("Run off: 1 relationship.")
    joins = call(server, "GET", "/relationships")["relationships"]
    assert any(j["to"] == "customers" and j.get("active") is False for j in joins)
    page.locator(".note-corner").get_by_role("button", name="Undo").last.click()
    expect(page.locator(".note-corner")).to_contain_text("Undone.")

    # Save as a set…, then it is listed with Check and Apply.
    window.locator(".dialog-foot").get_by_role("button", name="Save as a set…").click()
    page.get_by_label("Set name").fill("made_up_store_joins")
    page.locator(".dialog").last.get_by_role("button", name="Save").click()
    expect(page.locator(".note-corner")).to_contain_text("Saved made_up_store_joins in your saved sets.")
    saved = window.locator(".set-item", has_text="made_up_store_joins")
    expect(saved).to_be_visible()
    saved.get_by_role("button", name="Check").click()
    expect(page.locator(".dialog").last).to_contain_text("Check made_up_store_joins")
    page.locator(".dialog").last.locator(".dialog-foot").get_by_role("button", name="Close").click()
    saved.get_by_role("button", name="Apply").click()
    expect(page.locator(".note-corner")).to_contain_text("Applied made_up_store_joins")
    page.close()
