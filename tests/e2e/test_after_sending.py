# ruff: noqa: F811
"""After sending a result somewhere (the usability test's decision 8): Send to Sandbox leaves the
window open and its toast has Show, which closes the window and goes to the card; Open as grid
closes its window and shows the new tab. Made-up orders."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, demo_frame, open_grid, server  # noqa: F401


def test_send_to_sandbox_keeps_the_window_and_show_goes_to_the_card(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(demo_frame(400), name="send_orders", new_grid=True)
    page = open_grid(browser, url, width=1440, height=1000)
    try:
        page.locator(".ag-header-cell[col-id='region'] .sab-header-name").click()
        page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Analyze").click()
        page.get_by_role("menuitem", name="Odds…").click()
        dialog = page.locator("dialog")
        expect(dialog.locator(".odds-table tbody tr").first).to_be_visible(timeout=20000)

        dialog.get_by_role("button", name="Send to Sandbox").click()
        toast = page.locator(".toast", has_text="In the Sandbox")
        expect(toast).to_be_visible()
        # The window stays, with its result, so the next thing can be sent from it.
        expect(dialog).to_be_visible()
        expect(dialog.locator(".odds-table tbody tr").first).to_be_visible()
        # One action from here: Show closes the window and the Sandbox has the card in view.
        toast.get_by_role("button", name="Show").click()
        expect(page.locator("dialog[open]")).to_have_count(0)
        expect(page.locator(".nav-rail [data-area='sandbox']")).to_have_attribute("aria-current", "page")
        card = page.locator("#ai-panel .card.arrived")
        expect(card).to_have_count(1, timeout=10000)
        expect(card).to_be_in_viewport()
        expect(card.locator("h3")).to_contain_text("Odds: region")
    finally:
        page.close()


def test_open_as_grid_closes_its_window_and_shows_the_new_tab(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(demo_frame(400), name="grid_orders", new_grid=True)
    page = open_grid(browser, url, width=1440, height=1000)
    try:
        page.locator(".ag-header-cell[col-id='region'] .sab-header-name").click()
        page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Analyze").click()
        page.get_by_role("menuitem", name="Odds…").click()
        dialog = page.locator("dialog")
        expect(dialog.locator(".odds-table tbody tr").first).to_be_visible(timeout=20000)
        # One action: the window is gone and the result's table is the tab in front.
        dialog.get_by_role("button", name="Open as grid").click()
        expect(page.locator("dialog[open]")).to_have_count(0, timeout=20000)
        tab = page.locator(".tabs-row .tab-item.active")
        expect(tab).to_contain_text("grid_orders_odds_region", timeout=20000)
        header = page.locator(".pane:not([hidden]) .ag-header-cell[col-id='value']")
        expect(header).to_be_visible(timeout=20000)
    finally:
        page.close()
