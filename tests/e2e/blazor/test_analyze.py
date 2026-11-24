"""The Blazor Analyze page on the made-up sample store: the toolbar of every analysis by group, the one form
the server plans (the table, a slot's columns, the sentence of what will run), Run, the result's cards
landing on the board (a note and its Plotly figure), Show the math, Open as table, a card removed, and Try it
on this sample."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_an_analysis_runs_from_its_form_and_lands_on_the_board(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "analyze")
    expect(page.locator(".analyze-group", has_text="Describe")).to_be_visible()
    page.click("[data-analysis=outliers]")
    form = page.locator(".analyze-form[data-analysis=outliers]")
    expect(form).to_contain_text("Find unusual values")
    form.locator(".analyze-change").click()
    page.click(".context-menu [role=menuitem]:has-text('orders')")
    expect(form.locator(".analyze-table-name")).to_contain_text("orders")
    expect(form.locator(".analyze-sentence")).to_contain_text("Find the unusual values of amount")
    rejected = form.locator(".analyze-chip-row[data-slot=column] optgroup[label='Does not fit'] option")
    expect(rejected.first).to_be_attached()

    form.locator(".analyze-run").click()
    note = page.locator(".board-card[data-kind=note]", has_text="Unusual values of amount").first
    expect(note).to_be_visible(timeout=60_000)
    expect(page.locator(".board-card[data-kind=plotly] .plotly-host .main-svg").first).to_be_visible()

    note.locator("button:has-text('Show the math')").click()
    expect(page.locator(".dialog")).to_contain_text("The math")
    page.keyboard.press("Escape")

    page.locator(".board-card[data-kind=plotly]").first.locator("button[aria-label^=Remove]").click()
    expect(page.locator(".board-card[data-kind=plotly]", has_text="Unusual values of amount")).to_have_count(
        0
    )

    note.locator("button:has-text('Open as table')").click()
    expect(page.locator(".grid-title")).to_contain_text("outliers")
    page.close()


def test_try_it_on_this_sample(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "analyze")
    page.click("[data-analysis=benford]")
    form = page.locator(".analyze-form[data-analysis=benford]")
    expect(form).to_be_visible()
    form.locator(".analyze-needs summary").click()
    form.locator("button:has-text('Try it on this sample')").click()
    expect(page.locator(".board-card[data-kind=note]").first).to_be_visible(timeout=60_000)
    expect(form.locator(".analyze-table-name")).to_contain_text("sample_benford")
    page.close()
