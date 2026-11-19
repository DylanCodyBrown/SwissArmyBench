# ruff: noqa: F811
"""The Analyze page in a real browser (the owner, 2026-11-19; design principle 8.13): the toolbar of every
analysis, the one guided form (the table already picked, the columns as chips, one sentence, Run), results
that land on the board by themselves, Run again, Make it fit, Check this table, the column-first way in,
the made-up sample, and a grid page with no analysis left on it. Made-up orders only."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from swissarmybench.domain import analysis_contracts as C
from tests.analyze_data import orders
from tests.e2e.test_ui import browser, call, close_pages, grid_of, open_grid, server  # noqa: F401


@pytest.fixture
def orders_url(server: dict[str, Any]) -> Iterator[str]:
    url = push_client.push(orders(), name="orders", new_grid=True)
    yield url
    for card in call(server, "GET", "/cards")["cards"]:
        call(server, "DELETE", f"/cards/{card['id']}")
    for grid in call(server, "GET", "/grids")["grids"]:
        call(server, "DELETE", f"/grids/{grid['grid']}")


def analyze(page: Page) -> Locator:
    page.locator(".nav-rail [data-area='analyze']").click()
    panel = page.locator("#ai-panel")
    expect(panel.locator(".analyze-toolbar .analyze-btn").first).to_be_visible(timeout=20000)
    return panel


def open_form(panel: Locator, analysis: str) -> Locator:
    panel.locator(f".analyze-btn[data-analysis='{analysis}']").click()
    form = panel.locator(".analyze-side .analyze-form")
    expect(form).to_be_visible(timeout=20000)
    return form


def chip(form: Locator, slot: str) -> Locator:
    return form.locator(f".analyze-chip-row[data-slot='{slot}'] select.chip-select")


def test_the_toolbar_has_every_analysis_grouped_everyday_words_first(
    browser: Browser, orders_url: str
) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    groups = panel.locator(".analyze-toolbar .analyze-group-label")
    expect(groups).to_have_text(["Describe", "Test", "Model", "Time", "Compare", "Yours"])
    for contract in C.CONTRACTS:
        button = panel.locator(f".analyze-btn[data-analysis='{contract.id}']")
        expect(button.locator(".analyze-btn-label")).to_have_text(contract.label)
        expect(button.locator(".analyze-btn-name")).to_have_text(contract.name)  # the technical name second
    expect(panel.locator(".analyze-btn[data-analysis='columns']")).to_contain_text(
        "What can I do with a column?"
    )
    expect(page).to_have_title("Analyze")
    # the board is still there under the toolbar: free cards, pages, themes, dashboards
    for name in ("Add chart", "Add note", "Page view", "Print to PDF", "Dashboards…"):
        expect(panel.get_by_role("button", name=name)).to_be_visible()


def test_a_first_digits_test_from_the_toolbar_lands_on_the_board_by_itself(
    browser: Browser, orders_url: str
) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "benford")
    # the table is already picked, and said with its rows; the form is beside the board, not over it
    expect(form.locator(".analyze-table-name")).to_have_text("orders · 240 rows")
    expect(page.locator("dialog[open]")).to_have_count(0)
    expect(panel.locator(".analyze-board")).to_be_visible()
    # the column is picked by the app, as a chip, and only number columns are offered
    amounts = chip(form, "column")
    expect(amounts).to_have_value("amount")
    expect(form.locator(".analyze-chip-row[data-slot='column'] .chip-said")).to_have_text(
        "the likeliest, by its name"
    )
    offered = amounts.locator("option:not([disabled])")
    expect(offered).to_have_count(2)
    expect(offered.nth(0)).to_contain_text("units · number")
    expect(offered.nth(1)).to_contain_text("amount · number")
    refused = amounts.locator("optgroup[label='Does not fit'] option")
    expect(refused.filter(has_text="region: is a text column")).to_have_count(1)
    expect(refused.filter(has_text="order_date: is a date column")).to_have_count(1)
    # one sentence of what will run; the options are folded away, all defaulted
    expect(form.locator(".analyze-sentence")).to_have_text(
        "Test whether amount follows Benford's first-digit law, on 240 rows of orders."
    )
    expect(form.locator("details.analyze-more")).not_to_have_attribute("open", "")
    assert panel.locator(".analyze-board .card").count() == 0
    form.get_by_role("button", name="Run", exact=True).click()
    cards = panel.locator(".analyze-board .card")
    expect(cards).to_have_count(2, timeout=30000)  # no other click: the note and its chart
    expect(cards.nth(0)).to_contain_text("First digits: amount")
    expect(cards.nth(0)).to_have_class(__import__("re").compile(r"\blanded\b"))
    expect(cards.nth(1).locator(".figure")).to_be_visible()
    # the form stays open beside them, as it was
    expect(amounts).to_have_value("amount")
    # a second run lands above the first
    amounts.select_option("units")
    expect(form.locator(".analyze-sentence")).to_contain_text("Test whether units follows")
    form.get_by_role("button", name="Run", exact=True).click()
    expect(cards).to_have_count(4, timeout=30000)
    expect(cards.nth(0)).to_contain_text("First digits: units")
    expect(cards.nth(2)).to_contain_text("First digits: amount")


def test_a_cards_actions_show_the_math_open_as_grid_copy_code_and_run_again(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    call(
        server,
        "POST",
        "/analyze/run",
        {"analysis": "outliers", "table": "orders", "options": {"method": "iqr"}},
    )
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    first = panel.locator(".analyze-board .card").first
    actions = first.locator(".card-analysis")
    expect(actions.get_by_role("button", name="Show the math")).to_be_visible(timeout=20000)
    # Run again: the form reopens filled with what it ran with
    expect(panel.locator(".analyze-side")).to_be_hidden()
    actions.get_by_role("button", name="Run again…").click()
    form = panel.locator(".analyze-side .analyze-form")
    expect(chip(form, "column")).to_have_value("amount", timeout=20000)
    form.locator("details.analyze-more summary").click()
    expect(form.locator(".analyze-option[data-option='method'] select")).to_have_value("iqr")
    expect(panel.locator(".analyze-side h2")).to_have_text("Find unusual values")
    # Copy code: the analysis as Python on the clipboard
    page.evaluate("() => { navigator.clipboard.writeText = async (text) => { window.__copied = text; }; }")
    actions.get_by_role("button", name="Copy code").click()
    page.wait_for_function("window.__copied !== undefined", timeout=30000)
    assert "stats.outliers(" in page.evaluate("window.__copied")
    # Show the math: a note beside the result
    before = panel.locator(".analyze-board .card").count()
    actions.get_by_role("button", name="Show the math").click()
    expect(panel.locator(".analyze-board .card")).to_have_count(before + 1, timeout=20000)
    expect(panel.locator(".analyze-board")).to_contain_text("The math: Outliers on orders")
    # Open as grid: the result's rows as a table of their own
    actions.get_by_role("button", name="Open as grid").click()
    expect(page.locator(".toast").filter(has_text="Opened as orders_outliers")).to_be_visible(timeout=20000)
    assert "orders_outliers" in [g["dataset"] for g in call(server, "GET", "/grids")["grids"]]


def test_tie_out_picks_two_tables(browser: Browser, orders_url: str) -> None:
    ledger = pd.DataFrame({"region": ["West", "North", "East", "South"], "amount": [10.0, 20.0, 30.0, 40.0]})
    push_client.push(ledger, name="ledger", new_grid=True)
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "tie_out")
    expect(form.locator(".analyze-table-name")).to_contain_text("orders")
    against = chip(form, "other")
    expect(against.locator("option:checked")).to_have_text("ledger")
    expect(form.locator(".analyze-chip-row[data-slot='other'] .chip-said")).to_have_text(
        "the only other open table"
    )
    form.get_by_role("button", name="Run", exact=True).click()
    cards = panel.locator(".analyze-board .card")
    expect(cards).to_have_count(2, timeout=30000)
    expect(cards.nth(0)).to_contain_text("Tie-out: orders and ledger")
    # the other way round: Change picks the first table
    form.get_by_role("button", name="Change").click()
    page.get_by_role("menuitemradio", name="ledger").click()
    expect(form.locator(".analyze-table-name")).to_contain_text("ledger", timeout=20000)
    expect(
        chip(panel.locator(".analyze-side .analyze-form"), "other").locator("option:checked")
    ).to_have_text("orders")


def test_the_grid_page_has_no_analysis_left_on_it(browser: Browser, orders_url: str) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    ribbon = page.locator(".ribbon")
    expect(ribbon.get_by_role("button", name="Analyze")).to_have_count(0)
    expect(ribbon.get_by_role("button", name="Profile", exact=True).first).to_be_visible()  # it stays
    page.locator(".ag-header-cell[col-id='amount']").click(button="right")
    menu = page.locator(".menu")
    expect(menu).to_be_visible()
    for gone in ("Fit test…", "Outliers…", "Odds…", "Find what predicts it…"):
        expect(menu.get_by_role("menuitem", name=gone)).to_have_count(0)
    expect(menu.get_by_role("menuitem", name="Profile to Analyze")).to_be_visible()
    # a column's values still go to the board in one click: the page's own count, landed as a run
    menu.get_by_role("menuitem", name="Distinct values to Analyze").click()
    expect(page.locator(".toast")).to_contain_text("On the Analyze board", timeout=20000)


@pytest.mark.parametrize("old", ["visualizations", "sandbox"])
def test_the_old_addresses_land_on_analyze(browser: Browser, orders_url: str, old: str) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    page.goto(orders_url.split("/g/")[0] + f"/workspace?view={old}#" + orders_url.split("#")[1])
    expect(page.locator("#ai-panel .analyze-toolbar .analyze-btn").first).to_be_visible(timeout=20000)
    expect(page.locator(".nav-rail [data-area='analyze']")).to_have_attribute("aria-current", "page")
    expect(page).to_have_title("Analyze")


def almost() -> pd.DataFrame:
    n = 120
    return pd.DataFrame(
        {
            "when": [(dt.date(2023, 1, 1) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)],
            "amount": [f"{100 + (i * 37) % 900}" for i in range(n)],
            "region": [("West", "East", "North")[i % 3] for i in range(n)],
        }
    )


def test_make_it_fit_says_how_and_apply_adds_the_step(
    browser: Browser, server: dict[str, Any], orders_url: str
) -> None:
    url = push_client.push(almost(), name="sales", new_grid=True)
    page = open_grid(browser, url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "time_series")
    expect(form.locator(".analyze-table-name")).to_have_text("sales · 120 rows")
    # never a dead end: what is missing in one sentence, how to make it fit, and Change
    expect(form.locator(".error-note")).to_contain_text(
        "Nothing in sales fits dates: it needs a date column."
    )
    expect(form.get_by_role("button", name="Run", exact=True)).to_be_disabled()
    expect(form.get_by_role("button", name="Change")).to_be_visible()
    fix = form.locator(".analyze-fixes .analyze-fix").first
    expect(fix).to_contain_text("Read when as dates (year-month-day): 120 of 120 values are dates.")
    assert call(server, "GET", f"/grids/{grid_of(url)}")["steps"] == []  # nothing applied by itself
    fix.get_by_role("button", name="Apply").click()
    form = panel.locator(".analyze-side .analyze-form")
    expect(form.locator(".analyze-table-name")).to_have_text("sales, with 1 step · 120 rows", timeout=20000)
    expect(chip(form, "date")).to_have_value("when")
    expect(form.locator(".analyze-fixes .analyze-fix").filter(has_text="Read when as dates")).to_have_count(0)
    assert len(call(server, "GET", f"/grids/{grid_of(url)}")["steps"]) == 1  # a step the user can undo
    form.get_by_role("button", name="Run", exact=True).click()
    expect(panel.locator(".analyze-board .card").first).to_contain_text("Time series", timeout=30000)


def test_check_this_table_suggests_three_each_one_click(
    browser: Browser, server: dict[str, Any], orders_url: str
) -> None:
    url = push_client.push(almost(), name="sales", new_grid=True)
    page = open_grid(browser, url, width=1600, height=1000)
    panel = analyze(page)
    panel.locator(".analyze-btn[data-analysis='check']").click()
    side = panel.locator(".analyze-side")
    big = side.locator(".analyze-big-btn")
    expect(big).to_have_count(3, timeout=20000)
    first = big.filter(has_text="Spot the trend and the seasons")
    expect(first.locator(".analyze-big-verb")).to_have_text("Read when as dates and run")
    expect(first.locator(".analyze-big-reason")).to_have_text(
        "when holds dates: a trend and seasons can show."
    )
    first.click()  # its fix applied in that click, then run: the cards land
    expect(panel.locator(".analyze-board .card").first).to_contain_text("Time series", timeout=30000)
    assert len(call(server, "GET", f"/grids/{grid_of(url)}")["steps"]) == 1
    # the panel reads the table again: the time series fits now, with no fix to apply
    expect(
        side.locator(".analyze-big-btn").filter(has_text="Spot the trend").locator(".analyze-big-verb")
    ).to_have_text("Run", timeout=20000)


def test_what_can_i_do_with_a_column_shows_only_what_fits(browser: Browser, orders_url: str) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    panel.locator(".analyze-btn[data-analysis='columns']").click()
    side = panel.locator(".analyze-side")
    columns = side.locator(".analyze-column")
    expect(columns).to_have_count(6, timeout=20000)
    expect(columns.filter(has_text="order_id")).to_be_disabled()  # an identifier: nothing analyses it
    columns.filter(has_text="order_date").click()
    big = side.locator(".analyze-big-btn .analyze-big-label")
    expect(big).to_have_text(["Spot the trend and the seasons", "What comes next?"])
    side.locator(".analyze-big-btn").first.click()
    expect(panel.locator(".analyze-board .card").first).to_contain_text("Time series", timeout=30000)


def test_what_your_data_should_look_like_shows_a_sample_and_runs_on_it(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "odds")
    needs = form.locator("details.analyze-needs")
    needs.locator("summary").click()
    expect(needs.locator(".analyze-one-row")).to_contain_text("One row per chance (an order)")
    expect(needs.locator(".analyze-slots li").first).to_contain_text("Column: the column to count")
    sample = needs.locator("table.analyze-sample").first
    expect(sample.locator("thead th")).to_have_text(["order_id", "Columnregion", "Outcomelate"])
    expect(sample.locator("thead th.slot")).to_have_count(2)  # the slots' columns are marked and named
    expect(sample.locator("tbody tr")).to_have_count(8)
    needs.get_by_role("button", name="Try it on this sample").click()
    expect(panel.locator(".analyze-board .card").first).to_contain_text("region", timeout=30000)
    form = panel.locator(".analyze-side .analyze-form")
    expect(form.locator(".analyze-table-name")).to_have_text("sample_odds · 12 rows", timeout=20000)
    expect(chip(form, "outcome")).to_have_value("late")
    assert "sample_odds" in [g["dataset"] for g in call(server, "GET", "/grids")["grids"]]


def test_a_table_closed_while_its_form_is_open_is_said_in_the_form(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    other = push_client.push(almost(), name="sales", new_grid=True)
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "benford")
    expect(form.locator(".analyze-table-name")).to_have_text("orders · 240 rows")
    call(server, "DELETE", f"/grids/{grid_of(orders_url)}")
    side = panel.locator(".analyze-side")
    expect(side.locator(".error-note")).to_contain_text("is not open any more: pick another", timeout=20000)
    side.get_by_role("button", name="Change").click()  # never a dead end
    page.get_by_role("menuitemradio", name="sales").click()
    expect(side.locator(".analyze-table-name")).to_have_text("sales · 120 rows", timeout=20000)
    assert grid_of(other)


def test_an_error_stays_in_the_form_and_goes_when_it_is_fixed(browser: Browser, orders_url: str) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "forecast")
    form.locator("details.analyze-more summary").click()
    page.route(
        "**/analyze/run",
        lambda route: route.fulfill(
            status=408,
            json={
                "error": "orders is too big to analyse in 600 seconds: it was stopped. Filter it first.",
                "where": "orders",
            },
        ),
    )
    form.get_by_role("button", name="Run", exact=True).click()
    note = panel.locator(".analyze-side .error-note")
    expect(note).to_contain_text("orders is too big to analyse in 600 seconds", timeout=20000)
    assert panel.locator(".analyze-board .card").count() == 0
    page.unroute("**/analyze/run")
    panel.locator(".analyze-side .analyze-form").get_by_role("button", name="Run", exact=True).click()
    expect(panel.locator(".analyze-board .card").first).to_be_visible(timeout=30000)
    expect(note).to_have_count(0)  # it never lingers after the cause is gone


def test_a_run_is_gated_and_cancel_lands_nothing(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "regression")
    held: list[Any] = []
    before = len(call(server, "GET", "/analyze/runs")["runs"])
    page.route("**/analyze/run", lambda route: held.append(route))  # the server's answer, held back
    form.get_by_role("button", name="Run", exact=True).click()
    cover = panel.locator(".busy-cover")
    expect(cover).to_contain_text("Running…", timeout=10000)
    expect(panel.locator(".analyze-side .analyze-form")).to_have_attribute("aria-busy", "true")
    with page.expect_request("**/analyze/cancel"):
        cover.get_by_role("button", name="Cancel").click()
    expect(cover).to_have_count(0)
    expect(panel.locator(".analyze-side .error-note")).to_have_count(0)  # a Cancel is not an error
    assert panel.locator(".analyze-board .card").count() == 0
    assert len(call(server, "GET", "/analyze/runs")["runs"]) == before


def test_tools_hand_off_to_each_other_from_the_results_card(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    """8.8 on the board: find predictors hands to a regression with its columns filled; a time series hands
    to the forecast; outliers' Show these rows adds the step to the table."""
    page = open_grid(browser, orders_url, width=1600, height=1000)
    panel = analyze(page)
    form = open_form(panel, "predictors")
    expect(chip(form, "target")).to_have_value("late")
    form.get_by_role("button", name="Run", exact=True).click()
    first = panel.locator(".analyze-board .card").first
    expect(first.locator(".card-analysis")).to_be_visible(timeout=30000)
    hand_off = first.locator(".card-analysis").get_by_role("button", name="Predict it from these")
    if hand_off.count():  # the made-up orders have a column that tells about late
        hand_off.click()
        expect(panel.locator(".analyze-side h2")).to_have_text("Predict a number", timeout=20000)
        expect(chip(panel.locator(".analyze-side .analyze-form"), "target")).to_have_value("late")
    form = open_form(panel, "time_series")
    form.get_by_role("button", name="Run", exact=True).click()
    series = panel.locator(".analyze-board .card").filter(has_text="Time series").first
    expect(series).to_be_visible(timeout=30000)
    series.locator(".card-analysis").get_by_role("button", name="What comes next?").click()
    expect(panel.locator(".analyze-side h2")).to_have_text("What comes next?", timeout=20000)
    form = panel.locator(".analyze-side .analyze-form")
    expect(chip(form, "date")).to_have_value("order_date")
    expect(chip(form, "metric")).to_have_value("amount")
    # outliers: Show these rows is a step on the table, on the user's click
    body = {"analysis": "outliers", "table": "orders", "columns": {"column": "units"}}
    ran = call(server, "POST", "/analyze/run", body)
    outliers = panel.locator(f".analyze-board .card[data-card='{ran['cards'][0]}']")
    expect(outliers).to_be_visible(timeout=30000)
    show = outliers.locator(".card-analysis").get_by_role("button", name="Show these rows")
    if show.count():
        show.click()
        expect(page.locator(".toast").filter(has_text="Added a step to orders")).to_be_visible(timeout=20000)
        assert len(call(server, "GET", f"/grids/{grid_of(orders_url)}")["steps"]) == 1


BLADE = """def analyze(df, columns):
    column = columns[0] if columns else df.columns[0]
    counts = df[column].value_counts().rename_axis(column).reset_index(name="rows")
    return [f"## {column}: {len(counts)} values", counts]
"""


def test_your_own_analysis_is_on_the_toolbar_and_lands_its_cards(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    blade = {"name": "Value counts", "kind": "analysis", "code": BLADE, "variable": "analyze"}
    call(server, "POST", "/blades", blade)
    try:
        page = open_grid(browser, orders_url, width=1600, height=1000)
        panel = analyze(page)
        mine = panel.locator(".analyze-group[aria-label='Yours'] .analyze-btn")
        expect(mine.filter(has_text="Value counts")).to_be_visible(timeout=20000)
        expect(mine.filter(has_text="Make another…")).to_be_visible()
        mine.filter(has_text="Value counts").click()
        form = panel.locator(".analyze-side .analyze-form")
        expect(form.locator(".analyze-sentence")).to_have_text(
            "Run Value counts on 240 rows of orders.", timeout=20000
        )
        form.locator(".analyze-chip-row[data-slot='columns'] select.chip-add").select_option("region")
        picked = panel.locator(
            ".analyze-side .analyze-chip-row[data-slot='columns'] .chip[data-column='region']"
        )
        expect(picked).to_be_visible(timeout=20000)
        panel.locator(".analyze-side .analyze-form").get_by_role("button", name="Run", exact=True).click()
        cards = panel.locator(".analyze-board .card")
        expect(cards).to_have_count(2, timeout=60000)  # the note and its table, both landed
        expect(cards.nth(0)).to_contain_text("region: 4 values")
        expect(cards.nth(1)).to_contain_text("West")
    finally:
        call(server, "DELETE", "/blades/Value%20counts")


def test_a_columns_values_sent_from_the_grid_show_on_the_board(browser: Browser, orders_url: str) -> None:
    """The grid's plain sends stay: Distinct values to Analyze, with Show going to the card."""
    page = open_grid(browser, orders_url, width=1600, height=1000)
    page.locator(".ag-header-cell[col-id='region']").click(button="right")
    page.locator(".menu").get_by_role("menuitem", name="Distinct values to Analyze").click()
    toast = page.locator(".toast", has_text="On the Analyze board")
    expect(toast).to_be_visible(timeout=20000)
    toast.get_by_role("button", name="Show").click()
    expect(page.locator(".nav-rail [data-area='analyze']")).to_have_attribute("aria-current", "page")
    card = page.locator("#ai-panel .card").first
    expect(card).to_contain_text("region", timeout=20000)
    expect(card).to_be_in_viewport()


def test_with_no_table_open_the_form_says_so_and_is_not_a_dead_end(
    browser: Browser, server: dict[str, Any]
) -> None:
    for grid in call(server, "GET", "/grids")["grids"]:
        call(server, "DELETE", f"/grids/{grid['grid']}")
    page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?view=analyze#token={server['token']}")
    panel = page.locator("#ai-panel")
    expect(panel.locator(".analyze-toolbar .analyze-btn").first).to_be_visible(timeout=20000)
    panel.locator(".analyze-btn[data-analysis='benford']").click()
    side = panel.locator(".analyze-side")
    expect(side.locator(".error-note")).to_contain_text("No table is open: open one first.", timeout=20000)
    expect(side.locator(".analyze-table-name")).to_have_text("No table is open")
    side.get_by_role("button", name="Change").click()
    expect(page.get_by_role("menuitem", name="Find data…")).to_be_visible()
    page.keyboard.press("Escape")
    # a table that arrives is taken by the waiting form
    url = push_client.push(orders(), name="orders", new_grid=True)
    try:
        page.locator(".nav-rail [data-area='analyze']").click()
        expect(side.locator(".analyze-table-name")).to_have_text("orders · 240 rows", timeout=20000)
    finally:
        call(server, "DELETE", f"/grids/{grid_of(url)}")
