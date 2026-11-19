# ruff: noqa: F811
"""Everyday comforts (feel-b, 2026-11-19) in a real browser: the filter's checklist of values, the
keyboard shortcuts on ? and Ctrl+/, the palette's order (the table first, one Undo, why a command is off,
the recently used first), Undo after closing a tab and removing a column, a column's numbers on hovering
its header, the status bar's Sum without ids, Copy with headers and as Markdown, and a notebook cell's
run time with "Starting Python…" gated over it. Made-up data only.

With SWISSARMYBENCH_FEELB_SHOTS set to a folder, the tests also save light and dark screenshots there (2x)."""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401
from tests.e2e.test_workbench_page import open_workbench, start

SHOTS = os.environ.get("SWISSARMYBENCH_FEELB_SHOTS")


def shot(page: Page, name: str) -> None:
    """The page as it is, light then dark (the app follows the system's scheme)."""
    if not SHOTS:
        return
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    for scheme in ("light", "dark"):
        page.emulate_media(color_scheme=scheme)
        page.wait_for_timeout(150)
        page.screenshot(path=str(Path(SHOTS) / f"{name}_{scheme}.png"))
    page.emulate_media(color_scheme="light")


def orchards(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "orchard_id": range(1, rows + 1),
            "region": [("North", "South", "East", "West", "North", "North")[i % 6] for i in range(rows)],
            "variety": [("Bramley", "Gala", "Pippin")[i % 3] for i in range(rows)],
            "crates": [(i * 7) % 40 + 1 for i in range(rows)],
            "price": [round(1.25 + (i % 9) * 0.5, 2) for i in range(rows)],
        }
    )


@pytest.fixture
def orchard_url(server: dict[str, Any]) -> Iterator[str]:
    url = push_client.push(orchards(), name="orchards", new_grid=True)
    yield url
    with contextlib.suppress(Exception):  # a test closed it itself
        call(server, "DELETE", f"/grids/{grid_of(url)}")


def grid_page(browser: Browser, url: str, **context: Any) -> Page:
    page = browser.new_context(
        viewport={"width": 1440, "height": 900}, device_scale_factor=2, **context
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    # The rows drawn (the status bar counts them once they are): pictures show a filled grid.
    page.locator(".ag-row[row-index='0'] .ag-cell[col-id='crates']").hover()
    expect(page.locator("#status")).to_contain_text("Rows ", timeout=20000)
    page.mouse.move(5, 5)
    return page


def header(page: Page, column: str) -> Any:
    return page.locator(f".ag-header-cell[col-id='{column}'] .sab-header-name")


def test_filter_starts_on_the_selected_column_with_its_values_to_tick(
    browser: Browser, orchard_url: str
) -> None:
    page = grid_page(browser, orchard_url)
    try:
        header(page, "region").click()
        page.locator(".ribbon").get_by_role("button", name="Filter", exact=True).click()
        dialog = page.locator("dialog[open]")
        expect(dialog.get_by_label("Column", exact=True)).to_have_value("region")
        expect(dialog.get_by_label("Condition")).to_have_value("in")
        values = dialog.locator(".filter-value")
        expect(values).to_have_count(4, timeout=20000)
        # Most common first, each with its count.
        expect(values.first.locator(".filter-value-text")).to_have_text("North")
        expect(values.first.locator(".filter-value-count")).to_have_text("30")
        shot(page, "filter_checklist")
        search = dialog.get_by_label("Search values")
        expect(search).to_be_focused()
        search.fill("st")
        expect(values).to_have_count(2)  # East, West
        values.filter(has_text="West").locator("input").check()
        search.fill("")
        expect(values).to_have_count(4)
        values.filter(has_text="South").locator("input").check()
        expect(dialog.locator(".filter-values-foot")).to_contain_text("2 selected")
        dialog.get_by_role("button", name="Add step").click()
        expect(page.locator("#status")).to_contain_text("of 20")
    finally:
        page.close()


def test_shortcuts_open_on_question_mark_and_ctrl_slash(browser: Browser, orchard_url: str) -> None:
    page = grid_page(browser, orchard_url)
    try:
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.keyboard.press("?")
        sheet = page.get_by_role("dialog", name="Keyboard shortcuts")
        expect(sheet).to_be_visible()
        expect(sheet.locator(".shortcuts-group", has_text="Steps")).to_contain_text("Ctrl+Z")
        expect(sheet.locator(".shortcuts-group", has_text="Help")).to_contain_text("Show every command")
        sheet.get_by_label("Find a shortcut").fill("zoom")
        expect(sheet.locator(".shortcuts-group")).to_have_count(1)
        sheet.get_by_label("Find a shortcut").fill("")
        shot(page, "shortcuts")
        page.keyboard.press("Escape")
        expect(sheet).to_have_count(0)
        page.locator(".ag-row[row-index='1'] .ag-cell[col-id='region']").click()
        page.keyboard.press("Control+/")
        expect(page.get_by_role("dialog", name="Keyboard shortcuts")).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        page.close()


def test_palette_leads_with_the_table_lists_undo_once_and_puts_the_recent_first(
    browser: Browser, orchard_url: str
) -> None:
    page = grid_page(browser, orchard_url)
    try:
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.keyboard.press("Control+Shift+P")
        items = page.locator(".wb-palette-item")
        expect(items.first).to_be_visible()
        assert items.first.locator(".wb-palette-group").text_content() in ("Table", "Column", "Steps", "Cell")
        groups = items.locator(".wb-palette-group").all_text_contents()
        assert groups.index("Application") > groups.index("Table")
        undo = items.filter(has=page.locator(".wb-palette-title", has_text=re.compile("^Undo$")))
        expect(undo).to_have_count(1)
        # Why it cannot run now, in the row.
        expect(undo.locator(".wb-palette-why")).to_have_text("Nothing to undo")
        shot(page, "palette")
        page.get_by_role("combobox", name="Command").fill("zoom 100")
        page.keyboard.press("Enter")
        page.keyboard.press("Control+Shift+P")
        expect(items.first.locator(".wb-palette-title")).to_have_text("Zoom 100%")
        page.keyboard.press("Escape")
    finally:
        page.close()


def test_removing_a_column_and_closing_a_tab_say_so_with_undo(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(orchards(), name="orchards_undo", new_grid=True)
    page = grid_page(browser, url)
    try:
        header(page, "variety").click(button="right")
        page.get_by_role("menuitem", name="Remove").click()
        expect(page.locator(".ag-header-cell[col-id='variety']")).to_have_count(0)
        toast = page.locator(".toast", has_text="Removed the column variety")
        expect(toast).to_be_visible()
        shot(page, "undo_toast")
        toast.get_by_role("button", name="Undo").click()
        expect(page.locator(".ag-header-cell[col-id='variety']")).to_have_count(1)
        # Closing the tab: Undo reopens it, its steps kept.
        page.locator(".tab-item.active").get_by_role("button", name=re.compile("^Close")).click()
        closed = page.locator(".toast", has_text="Closed orchards_undo")
        expect(closed).to_be_visible()
        closed.get_by_role("button", name="Undo").click()
        expect(page.locator(".tab-item .tab-label", has_text="orchards_undo")).to_be_visible(timeout=20000)
    finally:
        page.close()
        for g in call(server, "GET", "/grids")["grids"]:
            if g["dataset"] == "orchards_undo":
                call(server, "DELETE", f"/grids/{g['grid']}")


def test_a_header_shows_its_numbers_on_hover_and_ids_are_never_summed(
    browser: Browser, orchard_url: str
) -> None:
    page = grid_page(browser, orchard_url)
    try:
        header(page, "crates").hover()
        card = page.locator(".header-card")
        expect(card).to_be_visible(timeout=10000)
        expect(card).to_contain_text("crates")
        expect(card).to_contain_text("Range")
        expect(card.locator(".header-card-bars span")).to_have_count(20)
        shot(page, "header_card")
        page.mouse.move(5, 5)
        expect(card).to_have_count(0)
        header(page, "region").hover()
        expect(card.locator(".header-card-top li").first).to_contain_text("North")
        page.mouse.move(5, 5)
        # An id column is counted, never summed; a price is summed to its scale.
        header(page, "orchard_id").click()
        status = page.locator(".statusbar")
        expect(status).to_contain_text("Count 60")
        expect(status).not_to_contain_text("Sum")
        header(page, "price").click()
        total = sum(orchards()["price"])
        expect(status).to_contain_text(f"Sum {total:,.2f}")
        shot(page, "status_bar")
    finally:
        page.close()


def test_copy_with_headers_and_as_markdown(browser: Browser, orchard_url: str) -> None:
    page = grid_page(browser, orchard_url, permissions=["clipboard-read", "clipboard-write"])
    try:
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.locator(".ag-row[row-index='1'] .ag-cell[col-id='variety']").click(modifiers=["Shift"])
        page.locator(".ag-row[row-index='1'] .ag-cell[col-id='variety']").click(button="right")
        expect(page.locator(".statusbar")).to_contain_text("4 cells selected")
        expect(page.get_by_role("menuitem", name="Copy as Markdown")).to_be_visible()
        shot(page, "cell_menu")
        page.get_by_role("menuitem", name="Copy as Markdown").click()
        expect(page.locator(".toast", has_text="as Markdown")).to_be_visible()
        text = page.evaluate("navigator.clipboard.readText()")
        assert text.splitlines() == [
            "| region | variety |",
            "| --- | --- |",
            "| North | Bramley |",
            "| South | Gala |",
        ]
        page.locator(".ag-row[row-index='0'] .ag-cell[col-id='region']").click()
        page.locator(".ag-row[row-index='1'] .ag-cell[col-id='variety']").click(modifiers=["Shift"])
        expect(page.locator(".statusbar")).to_contain_text("4 cells selected")
        page.locator(".ag-row[row-index='1'] .ag-cell[col-id='variety']").click(button="right")
        page.get_by_role("menuitem", name="Copy with headers").click()
        expect(page.locator(".toast", has_text="with headers")).to_be_visible()
        text = page.evaluate("navigator.clipboard.readText()")
        assert text.splitlines() == ["region\tvariety", "North\tBramley", "South\tGala"]
    finally:
        page.close()


def test_a_notebook_cell_says_how_long_it_ran_and_keeps_its_name_box(
    browser: Browser, orchard_url: str
) -> None:
    grid = grid_page(browser, orchard_url)
    workbench = open_workbench(grid)
    try:
        start(workbench)
        editor = workbench.locator(".wb-cell .monaco-editor").first
        expect(editor).to_be_visible(timeout=20000)
        editor.click()
        workbench.keyboard.type("import time\ntime.sleep(1.5)\nanswer = 6 * 7\nanswer")
        workbench.locator(".wb-cell").first.get_by_role("button", name="Run cell").click()
        # The first run starts Python: the cell is gated with words until it is up.
        expect(workbench.locator(".busy-cover", has_text="Starting Python…")).to_be_visible(timeout=20000)
        elapsed = workbench.locator(".wb-cell").first.locator(".wb-elapsed")
        expect(elapsed).to_have_text(re.compile(r"^Running… \d+ s$"), timeout=60000)
        expect(elapsed).to_have_text(re.compile(r"^\d+\.\d s$"), timeout=60000)
        expect(workbench.locator(".wb-cell").first.locator(".wb-count")).to_have_text("[1]")
        # Its name box stays once it has run, whichever cell is selected.
        workbench.locator(".wb-cell").first.locator(".wb-number").click()
        workbench.keyboard.press("Escape")
        name = workbench.locator(".wb-cell").first.locator(".wb-cell-name")
        expect(workbench.locator(".wb-cell").first).to_have_class(re.compile("has-run"))
        assert float(name.evaluate("e => getComputedStyle(e).opacity")) > 0.3
        shot(workbench, "run_time")
    finally:
        workbench.close()
        grid.close()
