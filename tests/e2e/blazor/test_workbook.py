"""The Blazor Excel canvas (the Accounting extension's Workbook page) on a made-up store: the landing lists
the project's design; sheets as tabs (New sheet, F2 and a double-click rename in place, Enter keeps, Escape
puts back, a sheet holding blocks asks before it goes); a table block added from the Blocks menu, its
Properties, Undo and Redo; a block moved and taken off with the keys; Play builds the workbook and shows
it, Download gives the .xlsx, Export workbook.py says where; Templates (Import… an existing workbook, a
cell picked and bound, Unbind) and Statements and invoices (Build only after a dry run, then Register)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import openpyxl
import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page
from tests.e2e.blazor.extension_server import extension_server


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    with extension_server(tmp_path_factory.mktemp("blazor-workbook"), ["streamlit", "accounting"]) as info:
        made = call(info, "POST", "/project/new", {"name": "Books", "type": "accounting"})
        call(info, "POST", "/samples/store", {})
        yield info | {"project": made["project"]["path"]}


def opened(browser: Browser, server: dict[str, Any]) -> Page:
    # The last window closing closes the project (the server's life): each test opens it again.
    if call(server, "GET", "/project")["project"] is None:
        call(server, "POST", "/project/open", {"path": server["project"]})
        call(server, "POST", "/samples/store", {})
    # A workbook is a tab of the Notebooks page (the classic's own place), not a rail area of its own.
    page = open_page(browser, server, "notebooks")
    expect(page.locator(".nav-rail a", has_text="Workbook")).to_have_count(0)
    page.locator(".xc-landing .cvs-landing-item", has_text="workbook").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("workbook.design.json")
    expect(page.locator(".xc-block")).not_to_have_count(0)
    return page


def menu(page: Page, button: str, line: str) -> None:
    page.click(button)
    page.locator(".context-menu .menu-item", has_text=line).click()


def test_sheets_blocks_undo_and_play(browser: Browser, server: dict[str, Any]) -> None:
    page = opened(browser, server)
    tabs = page.locator(".xc-sheet")
    expect(tabs).to_have_count(1)
    page.click(".cv-new-page")
    expect(tabs).to_have_count(2)
    tabs.nth(1).press("F2")
    box = tabs.nth(1).locator("input.cv-rename")
    box.fill("Totals")
    box.press("Enter")
    expect(tabs.nth(1)).to_contain_text("Totals")
    tabs.nth(1).dblclick()
    tabs.nth(1).locator("input.cv-rename").fill("Gone")
    tabs.nth(1).locator("input.cv-rename").press("Escape")
    expect(tabs.nth(1)).to_contain_text("Totals")
    tabs.nth(1).locator(".tab-close").click()
    expect(tabs).to_have_count(1)
    tabs.nth(0).locator(".tab-close").click()
    expect(page.locator(".dialog[aria-label='Remove the sheet Summary and its blocks?']")).to_be_visible()
    page.click(".dialog-foot button:has-text('Cancel')")
    expect(tabs).to_have_count(1)

    menu(page, ".xc-add", "Table")
    table = page.locator(".xc-block[data-kind=table]")
    expect(table).to_have_count(1)
    expect(page.locator(".xc-props h3")).to_have_text("Table · A3")
    page.fill(".xc-columns", "customer_id, name")
    page.press(".xc-columns", "Tab")
    expect(page.locator(".xc-column")).to_have_count(2)
    expect(table.locator(".xc-block-words")).to_have_text("customers: customer_id, name")
    page.click(".cv-undo")
    expect(table.locator(".xc-block-words")).to_have_text("customers")
    page.click(".cv-redo")
    expect(table.locator(".xc-block-words")).to_have_text("customers: customer_id, name")
    page.check(".xc-total-row")
    expect(table.locator(".xc-block-words")).to_contain_text("total row")

    table.focus()
    table.press("ArrowDown")
    expect(page.locator(".xc-block[data-kind=table]")).to_have_attribute("data-cell", "A4")
    page.click(".cv-play")
    played = page.locator(".xc-played .xc-grid")
    expect(played.locator("td", has_text="customer_id")).to_have_count(1)
    expect(page.locator(".xc-add")).to_be_disabled()
    with page.expect_download() as got:
        page.click(".xc-download")
    assert got.value.suggested_filename.endswith(".xlsx")
    page.click(".cv-edit")
    page.locator(".xc-block[data-kind=table]").focus()
    page.locator(".xc-block[data-kind=table]").press("Delete")
    expect(page.locator(".xc-block[data-kind=table]")).to_have_count(0)
    page.click(".xc-export")
    expect(page.locator(".note-corner")).to_contain_text("workbook.py")
    page.close()


def test_templates_and_statements(browser: Browser, server: dict[str, Any]) -> None:
    source = server["tmp"] / "statement.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Statement"
    sheet["A1"] = "Statement for"
    sheet["A3"] = "Item"
    book.save(source)
    page = opened(browser, server)
    menu(page, ".xc-more", "Templates…")
    dialog = page.locator(".dialog[aria-label='Templates']")
    expect(dialog.locator(".cv-empty")).to_have_text("Import an existing workbook: a statement, an invoice")
    dialog.locator(".xc-import").click()
    choose_path(page, source)
    expect(page.locator(".note-corner")).to_contain_text("Imported statement")
    dialog.locator("td[data-cell=B1]").click()
    expect(dialog.locator(".xc-bind h4")).to_have_text("Statement!B1")
    dialog.locator(".xc-bind-what").fill("name")
    dialog.locator(".xc-bind-go").click()
    expect(dialog.locator(".xc-bindings li")).to_contain_text("Statement!B1 ← name")
    dialog.locator("button[aria-label='Unbind Statement!B1']").click()
    expect(dialog.locator(".xc-bindings li")).to_have_count(0)
    dialog.locator("td[data-cell=B1]").click()
    dialog.locator(".xc-bind-what").fill("name")
    dialog.locator(".xc-bind-go").click()
    dialog.locator(".xc-to-build").click()

    built = page.locator(".dialog[aria-label='Statements and invoices']")
    expect(built.locator(".xc-build")).to_be_disabled()
    built.locator(".xc-b-data").select_option("customers")
    built.locator(".xc-b-group").fill("city")
    built.locator(".xc-dry-run").click()
    expect(built.locator(".xc-plan-head")).to_have_text(re.compile(r"Dry run: \d+ files in "))
    expect(built.locator(".xc-build")).to_have_text(re.compile(r"Build \d+"))
    built.locator(".xc-b-group").fill("city, name")
    expect(built.locator(".xc-build")).to_be_disabled()
    built.locator(".xc-b-group").fill("city")
    built.locator(".xc-build").click()
    expect(page.locator(".note-corner")).to_contain_text(re.compile(r"Built \d+ in "))
    built.locator(".xc-register").click()
    expect(page.locator(".note-corner")).to_contain_text("The register is open as a grid")
    page.close()


def test_new_excel_workbook_is_a_notebooks_tab(browser: Browser, server: dict[str, Any]) -> None:
    opened(browser, server).close()
    page = open_page(browser, server, "notebooks")
    page.locator(".xc-landing button", has_text="New Excel workbook").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("Untitled workbook")
    expect(page.locator(".xc-sheet")).to_have_count(1)

    # The palette's Workbook commands act on the workbook tab in front.
    page.keyboard.press("Control+Shift+P")
    palette = page.get_by_role("dialog", name="Command palette")
    palette.locator("input").fill("play the workbook")
    expect(palette.locator(".wb-palette-item").first).not_to_have_class(re.compile("off"))
    page.keyboard.press("Enter")
    expect(page.locator(".cv-play")).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Control+Shift+P")
    palette.locator("input").fill("the workbook in front")
    page.keyboard.press("Enter")
    expect(page.locator(".dialog .wb-help-text")).to_contain_text("Played.")
    page.close()
