"""The Blazor Analyze page's side and board, on the made-up sample store: a slot's chips (Add to… and x),
the table line's Change with its tables and Find data…, Check this table's ranking and its one-click
buttons, What can I do with a column?, the panel's dock, maximize and collapse buttons; Add chart, a
chart card (Vega-Lite) with Open large, its menu (Download image, Download as HTML, Copy as Python) and
the cross-filter."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_chips_change_and_find_data(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "analyze")
    page.click("[data-analysis=together]")
    form = page.locator(".analyze-form[data-analysis=together]")
    form.locator(".analyze-change").click()
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Find data…")
    page.click(".context-menu [role=menuitem]:has-text('orders')")
    row = form.locator(".analyze-chip-row").first
    expect(row.locator(".chip-label")).to_be_visible()
    add = form.locator("select.chip-add").first
    if add.count():
        before = form.locator(".chip[data-column]").count()
        options = add.locator("option:not([disabled])")
        if options.count() > 1:
            add.select_option(index=1)
            expect(form.locator(".chip[data-column]")).to_have_count(before + 1)
            form.locator(".chip[data-column] .chip-remove").last.click()
            expect(form.locator(".chip[data-column]")).to_have_count(before)
    form.locator(".analyze-change").click()
    page.click(".context-menu [role=menuitem]:has-text('Find data…')")
    page.wait_for_url("**/catalog")
    page.close()


def test_check_this_table_and_a_column(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "analyze")
    page.click("[data-analysis=check]")
    check = page.locator(".analyze-check")
    expect(check.locator(".analyze-table-name")).not_to_be_empty()
    expect(check.locator(".analyze-big-btn").first).to_be_visible(timeout=30_000)
    check.locator(".analyze-rest summary").click()
    expect(check.locator(".analyze-ranked li").first).to_be_visible()
    check.locator("button:has-text('Put this check on the board')").click()
    expect(page.locator(".board-card").first).to_be_visible(timeout=60_000)

    page.click("[data-analysis=columns]")
    columns = page.locator(".analyze-by-column")
    expect(columns.locator(".analyze-column").first).to_be_visible()
    columns.locator(".analyze-column:not([disabled])").first.click()
    expect(columns.locator(".analyze-big-btn").first).to_be_visible()
    page.locator(".analyze-side-head button[aria-label=Close]").click()
    expect(columns).to_have_count(0)
    page.close()


def test_the_panel_buttons(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "analyze")
    page.click("button[aria-label='Dock the panel below the grid']")
    expect(page.locator(".analyze-page.dock-bottom")).to_be_visible()
    page.click("button[aria-label='Dock the panel to the right']")
    page.click("button[aria-label='Maximize the panel']")
    expect(page.locator(".analyze-side")).to_be_hidden()
    page.click("button[aria-label='Restore the panel']")
    page.click("button[aria-label='Collapse the panel']")
    expect(page.locator(".analyze-toolbar")).to_have_count(0)
    page.click("button[aria-label='Open the analysis panel']")
    expect(page.locator(".analyze-toolbar")).to_be_visible()
    page.close()


def test_add_chart_and_its_card(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "analyze")
    page.click(".board-bar button:has-text('Add chart')")
    dialog = page.locator(".dialog[aria-label='Add a chart']")
    dialog.locator("select[aria-label=Table]").select_option(label="orders")
    expect(dialog.locator("select[aria-label='X axis'] option").first).to_be_attached()
    dialog.locator("select[aria-label='X axis']").select_option("status")
    expect(dialog.locator("select[aria-label='Y axis']")).to_be_disabled()
    dialog.locator("input[aria-label=Title]").fill("Made-up statuses")
    dialog.locator("button:has-text('Add chart')").click()
    card = page.locator(".board-card[data-kind=chart]", has_text="Made-up statuses")
    expect(card.locator(".vega-host svg")).to_be_visible(timeout=30_000)

    card.locator("button[aria-label='More card actions']").click()
    expect(page.locator(".context-menu")).to_contain_text("Download image (PNG)")
    expect(page.locator(".context-menu")).to_contain_text("Download as HTML")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.click(".context-menu [role=menuitem]:has-text('Copy as Python (Altair)')")
    expect(page.locator(".toast", has_text="Copied the Altair code.")).to_be_visible()

    card.locator("button[aria-label='Open large']").click()
    large = page.locator(".dialog.wide")
    expect(large.locator(".vega-host svg")).to_be_visible()
    large.locator("button:has-text('Close')").last.click()

    card.locator(".vega-host svg path.mark-rect, .vega-host svg .mark-rect path").first.click()
    expect(page.locator(".toast", has_text="Filtered the grid to status")).to_be_visible()
    page.close()
