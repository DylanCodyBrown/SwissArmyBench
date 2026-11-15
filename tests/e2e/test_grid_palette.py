# ruff: noqa: F811
"""The grid page from the keyboard (the usability test's decision 18): Ctrl+Shift+P opens a command
palette that lists every action of the page, and Enter or F2 on a cell opens the value viewer."""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, demo_frame, open_grid, server  # noqa: F401


def palette(page: Page, words: str) -> None:
    """Three actions, none with the mouse: Ctrl+Shift+P, a few letters, Enter."""
    page.keyboard.press("Control+Shift+P")
    box = page.get_by_role("combobox", name="Command")
    expect(box).to_be_focused()
    box.fill(words)
    expect(page.locator(".wb-palette-item.active")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(page.locator(".wb-palette")).to_have_count(0)


def test_the_palette_lists_every_action_of_the_page_and_runs_them(
    browser: Browser, server: dict[str, Any]
) -> None:
    push_client.push(demo_frame(60), name="palette_other", new_grid=True)
    url = push_client.push(demo_frame(600), name="palette_orders", new_grid=True)
    page = open_grid(browser, url, width=1700, height=900)
    try:
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.keyboard.press("Control+Shift+P")
        listed = page.locator(".wb-palette-item")
        expect(listed.first).to_be_visible()
        titles = {
            (str(group), str(title))
            for group, title in listed.evaluate_all(
                "rows => rows.map(r => [r.querySelector('.wb-palette-group').textContent,"
                " r.querySelector('.wb-palette-title').textContent])"
            )
        }
        # Every button of the ribbon's rows and of the steps strip is a command, under its row's name.
        on_page = page.evaluate(
            """() => {
              const shown = b => b.getClientRects().length > 0;
              const name = b => (b.getAttribute('aria-label') || b.textContent).trim();
              const found = [];
              // The tour bubble's two buttons are a one-time offer, not commands.
              for (const b of document.querySelectorAll('.app-row button'))
                if (shown(b) && !b.closest('.tour-bubble')) found.push(['Application', name(b)]);
              for (const row of document.querySelectorAll('.ribbon .ribbon-group')) {
                const group = row.querySelector('.ribbon-caption strong').textContent.trim();
                for (const b of row.querySelectorAll('button'))
                  if (shown(b) && b.getAttribute('aria-haspopup') !== 'menu') found.push([group, name(b)]);
              }
              for (const b of document.querySelectorAll('.steps-strip button'))
                if (shown(b) && !b.classList.contains('steps-count')) found.push(['Steps', name(b)]);
              for (const b of document.querySelectorAll('.tabs-row > button')) found.push(['Tabs', name(b)]);
              return found;
            }"""
        )
        assert len(on_page) > 35
        missing = [pair for pair in on_page if (pair[0], pair[1]) not in titles]
        assert not missing, f"buttons with no command: {missing}"
        assert ("Application", "Not now") not in titles  # the tour bubble's dismiss is not a command
        # And what has no button of its own: the Analyze menu's entries, the tabs, the cell's menu.
        for wanted in (
            ("Analyze", "Odds…"),
            ("Analyze", "Regression…"),
            ("Analyze", "Forecast…"),
            ("Tabs", "Go to Sandbox"),
            ("Tabs", "Go to palette_other"),
            ("Tabs", "Compare palette_orders with…"),
            ("Tabs", "Rename palette_orders"),
            ("Tabs", "Close palette_orders"),
            ("Cell", "View value"),
            ("Cell", "Keep these"),
            ("Application", "Zoom 100%"),
        ):
            assert wanted in titles, wanted
        # A command that cannot run now is greyed, and says why; each shows its keys.
        undo = listed.filter(has_text=re.compile("^Steps")).filter(has_text="Undo")
        expect(undo).to_have_class(re.compile("off"))
        expect(undo).to_have_attribute("title", "Nothing to undo")
        expect(undo.locator("kbd")).to_have_text("Ctrl+Z")
        page.keyboard.press("Escape")
        expect(page.locator(".wb-palette")).to_have_count(0)

        # Typing filters; Enter runs. A step form opens from the palette as from its button.
        palette(page, "table filter")
        dialog = page.locator("dialog")
        dialog.get_by_label("Column", exact=True).select_option("region")
        dialog.get_by_label("Condition").select_option("eq")
        dialog.get_by_label("Value", exact=True).fill("North")
        dialog.get_by_role("button", name="Add step").click()
        expect(page.locator("#status")).to_contain_text("of 100")
        palette(page, "steps undo")
        expect(page.locator("#status")).to_contain_text("of 600")
        # The cell's menu on the cell in front: Keep these (the selected value).
        palette(page, "cell keep")
        expect(page.locator("#status")).to_contain_text("of 100")
        # Tabs and analyses.
        palette(page, "go to sandbox")
        expect(page.locator(".tab-agent")).to_have_class(re.compile("active"))
        palette(page, "go to palette_orders")
        expect(page.locator(".tab-item.active .tab-label")).to_have_text("palette_orders")
        palette(page, "analyze outliers")
        expect(page.locator("dialog").get_by_label("Column", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        palette(page, "compare palette_orders with")
        expect(page.locator("dialog .compare-dialog")).to_be_visible(timeout=20000)
    finally:
        page.close()


def test_enter_or_f2_on_a_cell_opens_the_value_viewer(browser: Browser, server: dict[str, Any]) -> None:
    url = push_client.push(demo_frame(600), name="keys_orders", new_grid=True)
    page = open_grid(browser, url)
    try:
        viewer = page.locator("dialog")
        # The mouse puts the cursor on a cell; from there the keys alone: arrows move, Enter opens.
        page.locator(".ag-row[row-index='3'] .ag-cell[col-id='product']").click()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")  # row 4's note: 700 characters, cut in the grid
        expect(viewer).to_be_visible()
        expect(viewer).to_contain_text("note")
        expect(viewer).to_contain_text("x" * 300)
        page.keyboard.press("Escape")
        expect(viewer).to_have_count(0)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("F2")
        expect(viewer).to_be_visible()
        expect(viewer).to_contain_text("note 4")
        page.keyboard.press("Escape")
        # On a header the keys keep their own meaning: no viewer.
        page.locator(".ag-header-cell[col-id='region'] .sab-header-name").click()
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        expect(viewer).to_have_count(0)
    finally:
        page.close()
