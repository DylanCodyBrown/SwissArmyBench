"""The Blazor front end's accessibility, page by page on made-up data: every visible control has an
accessible name (conftest.UNNAMED, our own check: axe-core is not among web/'s packages), a dialog closes on
Escape, a menu moves with the arrow keys, and focus shows (the :focus-visible outline)."""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page, unnamed_controls

PAGES = [
    "",
    "connections",
    "catalog",
    "environment",
    "grids",
    "grids?new=1",
    "erd",
    "session",
    "settings",
    "notebooks?new=1",
    "scripts?new=1",
    "analyze",
]


@pytest.mark.parametrize("path", PAGES, ids=[p or "home" for p in PAGES])
def test_every_control_on_the_page_has_a_name(browser: Browser, server: dict[str, Any], path: str) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, path)
    page.wait_for_timeout(1200)  # the page's answers drawn
    assert unnamed_controls(page) == []
    page.close()


def test_the_grid_page_keyboard_paths(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = open_page(browser, server, f"grids?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()

    # A step's editor: named controls, Escape closes it.
    page.click("[data-tool=sort]")
    expect(page.locator(".dialog")).to_be_visible()
    assert unnamed_controls(page) == []
    page.keyboard.press("Escape")
    expect(page.locator(".dialog")).to_have_count(0)

    # The cell menu: the first line takes focus, the arrows move it, Escape closes it.
    page.locator(".ag-row[row-index='0'] .ag-cell[col-id=order_id]").click(button="right")
    menu = page.locator(".context-menu")
    expect(menu).to_be_visible()
    assert unnamed_controls(page) == []
    expect(menu.locator(".menu-item").first).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(menu.locator(".menu-item").nth(1)).to_be_focused()
    page.keyboard.press("End")
    expect(menu.locator(".menu-item").last).to_be_focused()
    page.keyboard.press("Escape")
    expect(menu).to_have_count(0)

    # Tab walks the ribbon's buttons in order, and the focus shows.
    page.locator("[data-tool=matching]").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.tool") == "filter"
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
    page.close()
