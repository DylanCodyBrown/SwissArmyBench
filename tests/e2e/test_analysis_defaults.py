# ruff: noqa: F811
"""What the analysis forms start on, in a real browser: never an identifier column. Time series and
Forecast start on the row count, the others on the first number column that is not an identifier, and
a regression starts with every column but its target and the identifiers ticked. Made-up orders whose
first column is order_id."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, Locator, Page, expect

from swissarmygrid.client import push_client
from tests.e2e.test_ui import browser, demo_frame, open_grid, server  # noqa: F401
from tests.test_regression import orders


def analyze(page: Page, entry: str) -> Locator:
    """Two clicks: Analyze, then the entry. The form is open and filled; nothing else is needed."""
    page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Analyze").click()
    page.get_by_role("menuitem", name=entry).click()
    return page.locator("dialog")


def test_the_forms_never_start_on_an_identifier(browser: Browser, server: dict[str, Any]) -> None:
    url = push_client.push(demo_frame(400), name="defaults_orders", new_grid=True)
    page = open_grid(browser, url, width=1440, height=1000)
    try:
        for entry, label in (("Odds…", "Column"), ("Outliers…", "Column"), ("Find predictors…", "Target")):
            dialog = analyze(page, entry)
            expect(dialog.get_by_label(label, exact=True)).to_have_value("quantity", timeout=20000)
            dialog.get_by_role("button", name="Close").last.click()

        dialog = analyze(page, "Fit test…")
        expect(dialog.get_by_label("Columns to test")).to_have_values(["quantity"], timeout=20000)
        dialog.get_by_role("button", name="Close").last.click()

        for entry in ("Time series…", "Forecast…"):
            dialog = analyze(page, entry)
            expect(dialog.get_by_label("Metric")).to_have_value("", timeout=20000)  # (row count)
            expect(dialog.get_by_label("Date column")).to_have_value("order_date")
            dialog.get_by_role("button", name="Close").last.click()

        # A column the user selected is theirs, identifier or not.
        page.locator(".ag-header-cell[col-id='unit_price'] .sag-header-name").click()
        dialog = analyze(page, "Odds…")
        expect(dialog.get_by_label("Column", exact=True)).to_have_value("unit_price", timeout=20000)
        dialog.get_by_role("button", name="Close").last.click()
    finally:
        page.close()


def test_a_regression_starts_with_every_column_but_the_target_and_the_identifiers(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(orders(2000), name="defaults_regression", new_grid=True)
    page = open_grid(browser, url, width=1440, height=1000)
    try:
        dialog = analyze(page, "Regression…")
        expect(dialog.get_by_label("Target", exact=True)).to_have_value("units", timeout=20000)
        boxes = dialog.locator(".analysis-checks input[type=checkbox]")

        def ticked() -> list[str]:
            return [str(v) for v in boxes.evaluate_all("all => all.filter(b => b.checked).map(b => b.value)")]

        def listed() -> list[str]:
            return [str(v) for v in boxes.evaluate_all("all => all.map(b => b.value)")]

        # order_id is offered, and not ticked; the target is not offered.
        assert listed() == ["order_id", "region", "amount", "late"]
        assert ticked() == ["region", "amount", "late"]
        # Another target: the old one is ticked in its place, since no box was touched.
        dialog.get_by_label("Target", exact=True).select_option("amount")
        assert ticked() == ["region", "units", "late"]
        # The third action after Analyze and Regression: Fit, with nothing to tick first.
        dialog.get_by_role("button", name="Fit", exact=True).click()
        expect(dialog.locator(".analysis-summary")).to_contain_text("explains", timeout=30000)
        # A box the user changed stays as they left it when the target changes again.
        boxes.and_(dialog.locator("[value=late]")).uncheck()
        dialog.get_by_label("Target", exact=True).select_option("units")
        assert ticked() == ["region"]
    finally:
        page.close()
