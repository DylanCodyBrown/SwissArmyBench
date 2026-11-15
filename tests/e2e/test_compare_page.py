# ruff: noqa: F811
"""Compare on the page (the usability test's decision 5): Compare with… on a tab's right-click, the key
that is unique on both sides ticked to start, diff mode showing only the keys and the columns that
differ with both halves scrolling sideways together, and a compare that survives a reload. Made-up
orders and a later copy with a few prices changed and a few orders missing."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, demo_frame, open_grid, server  # noqa: F401


def two_months(name: str) -> tuple[str, str]:
    """`name` and `name`_v2: every tenth order's unit_price is one higher, every 37th order is gone."""
    first = demo_frame(400)
    later = first.copy()
    later.loc[later.order_id % 10 == 0, "unit_price"] += 1
    later = later[later.order_id % 37 != 0].reset_index(drop=True)
    push_client.push(later, name=f"{name}_v2", new_grid=True)
    return push_client.push(first, name=name, new_grid=True), f"{name}_v2"


def until(page: Page, read: Callable[[], Any], wanted: Any, seconds: float = 10) -> None:
    """Wait until `read()` gives `wanted` (the page settles after a scroll or a redraw)."""
    got = read()
    for _ in range(int(seconds * 10)):
        if got == wanted:
            return
        page.wait_for_timeout(100)
        got = read()
    assert got == wanted


HEADERS = """pane => {
  const box = c => c.getBoundingClientRect();
  const corner = pane.querySelector(".ag-header-cell[col-id='__sab_rownum']");
  const edge = box(corner).right + 2;
  return [...pane.querySelectorAll('.ag-header-cell')]
    .filter(c => !c.getAttribute('col-id').startsWith('__') && box(c).width > 0)
    .sort((a, b) => box(a).left - box(b).left)
    .map(c => ({ name: c.getAttribute('col-id'), in_view: box(c).right > edge }));
}"""


def shown_headers(pane: Locator) -> list[str]:
    """The data columns a pane shows, left to right."""
    return [str(c["name"]) for c in pane.evaluate(HEADERS)]


def first_column(pane: Locator) -> str:
    """The first data column in view in the pane, to the right of the row numbers."""
    return next((str(c["name"]) for c in pane.evaluate(HEADERS) if c["in_view"]), "")


def start_compare(page: Page, name: str) -> Locator:
    """Three actions with two tables open: right-click the tab, Compare with…, Compare (the key is
    already ticked). With more tables open there is one more: which table."""
    tabs = page.locator(".tab-item[data-grid]")
    several = tabs.count() > 2
    tabs.filter(has_text=re.compile(f"^{name}$")).click(button="right")
    page.get_by_role("menuitem", name="Compare with…").click()
    if several:
        page.get_by_role("menu", name=f"Compare {name} with").get_by_role(
            "menuitem", name=f"{name}_v2"
        ).click()
    dialog = page.locator("dialog")
    expect(dialog.locator(".compare-dialog tbody tr").first).to_contain_text("order_id", timeout=20000)
    return dialog


def test_compare_with_on_a_tabs_right_click_ticks_the_key_unique_on_both_sides(
    browser: Browser, server: dict[str, Any]
) -> None:
    url, _ = two_months("cmp_menu")
    page = open_grid(browser, url, width=1500, height=900)
    try:
        # The tab's menu: what can be done with that table's tab.
        tab = page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^cmp_menu$"))
        tab.click(button="right")
        menu = page.get_by_role("menu")
        # (and beta mode's Leave a note…, last, while it is on: test_beta_notes_page.py)
        expect(menu.get_by_role("menuitem")).to_have_text(
            ["Compare with…", "Rename", "Close", "Leave a note…"]
        )
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)

        dialog = start_compare(page, "cmp_menu")
        ticked = dialog.locator("tbody tr").filter(has=page.locator("input:checked"))
        expect(ticked).to_have_count(1)
        # quantity matches quantity on every value, but repeats: order_id is the key.
        expect(ticked.locator("td").nth(1)).to_have_text("order_id")
        expect(ticked.locator("td").nth(2)).to_have_text("order_id")
        dialog.get_by_role("button", name="Compare", exact=True).click()
        expect(page.locator(".ribbon")).to_contain_text("390 matched", timeout=20000)
        # The right-clicked table is on the left.
        panes = page.locator(".pane:not([hidden])")
        expect(panes.nth(0).locator(".pane-head strong")).to_have_text("cmp_menu")
        expect(panes.nth(1).locator(".pane-head strong")).to_have_text("cmp_menu_v2")

        # The menu's other entries: Rename opens the name in place, Close closes the tab.
        page.get_by_role("button", name="Stop compare").click()
        page.locator(".pane:not([hidden])").nth(1).get_by_role("button", name="Close this side").click()
        other = page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^cmp_menu_v2$"))
        other = page.locator(f".tab-item[data-grid='{other.get_attribute('data-grid')}']")
        other.click(button="right")
        page.get_by_role("menuitem", name="Rename").click()
        box = other.locator("input.tab-rename")
        expect(box).to_be_focused()
        box.fill("cmp_menu_later")
        box.press("Enter")
        renamed = page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^cmp_menu_later$"))
        expect(renamed).to_have_count(1, timeout=10000)
        renamed.click(button="right")
        page.get_by_role("menuitem", name="Close").click()
        expect(renamed).to_have_count(0, timeout=10000)
    finally:
        page.close()


def test_diff_shows_only_the_differing_columns_and_both_halves_scroll_together(
    browser: Browser, server: dict[str, Any]
) -> None:
    url, _ = two_months("cmp_diff")
    page = open_grid(browser, url, width=1100, height=800)  # narrow: all seven columns do not fit a half
    try:
        start_compare(page, "cmp_diff").get_by_role("button", name="Compare", exact=True).click()
        ribbon = page.locator(".ribbon")
        ribbon.get_by_role("button", name="Diff", exact=True).click()
        expect(ribbon.locator(".diff-note")).to_contain_text("39 of 390 matched rows differ", timeout=20000)
        panes = page.locator(".pane:not([hidden])")
        left, right = panes.nth(0), panes.nth(1)
        # On by default: the key and the one column that differs, on both sides.
        toggle = ribbon.get_by_role("button", name="Only differing columns")
        expect(toggle).to_have_attribute("aria-pressed", "true")
        until(page, lambda: shown_headers(left), ["order_id", "unit_price"])
        until(page, lambda: shown_headers(right), ["order_id", "unit_price"])
        expect(right.locator(".ag-row[row-index='0'] .ag-cell[col-id='unit_price']")).to_have_class(
            re.compile("cell-diff"), timeout=20000
        )

        # Off: every column, and both halves have gone to the first column that differs.
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "false")
        until(page, lambda: first_column(left), "unit_price")
        until(page, lambda: first_column(right), "unit_price")
        assert len(shown_headers(left)) > 2

        # Scrolling one half sideways takes the other with it, from either side.
        right.locator(".ag-grid-viewport").evaluate("v => { v.scrollLeft = 0; }")
        until(page, lambda: first_column(left), "order_id")
        until(page, lambda: first_column(right), "order_id")
        left.locator(".ag-grid-viewport").evaluate("v => { v.scrollLeft = v.scrollWidth; }")
        until(page, lambda: first_column(right) != "order_id", True)
        assert first_column(left) == first_column(right)

        # A column's own button (the "Diff jump"): both halves go to it, not the left alone.
        right.locator(".ag-grid-viewport").evaluate("v => { v.scrollLeft = 0; }")
        until(page, lambda: first_column(left), "order_id")
        ribbon.locator(".diff-column", has_text="unit_price").click()
        until(page, lambda: first_column(left), "unit_price")
        until(page, lambda: first_column(right), "unit_price")
    finally:
        page.close()


def test_a_compare_survives_a_reload(browser: Browser, server: dict[str, Any]) -> None:
    url, _ = two_months("cmp_reload")
    page = open_grid(browser, url, width=1500, height=900)
    try:
        start_compare(page, "cmp_reload").get_by_role("button", name="Compare", exact=True).click()
        ribbon = page.locator(".ribbon")
        ribbon.get_by_role("button", name="Diff", exact=True).click()
        expect(ribbon.locator(".diff-note")).to_contain_text("39 of 390 matched rows differ", timeout=20000)

        page.reload()
        # Back as it was, with no action: the split, the mode, the counts, the rows. No key picker.
        ribbon = page.locator(".ribbon")
        expect(ribbon.locator(".diff-note")).to_contain_text("39 of 390 matched rows differ", timeout=20000)
        expect(ribbon.get_by_role("button", name="Diff", exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(page.locator("dialog[open]")).to_have_count(0)
        panes = page.locator(".pane:not([hidden])")
        expect(panes).to_have_count(2)
        expect(panes.nth(0).locator(".pane-head strong")).to_have_text("cmp_reload")
        expect(panes.nth(1).locator(".ag-row[row-index='0'] .ag-cell[col-id='unit_price']")).to_have_class(
            re.compile("cell-diff"), timeout=20000
        )
        until(page, lambda: shown_headers(panes.nth(0)), ["order_id", "unit_price"])

        # Stopped, it stays stopped after the next reload.
        ribbon.get_by_role("button", name="Stop compare").click()
        expect(ribbon.locator(".diff-note")).to_have_count(0)
        page.reload()
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        page.wait_for_timeout(500)
        expect(page.locator(".pane:not([hidden])")).to_have_count(1)
    finally:
        page.close()
