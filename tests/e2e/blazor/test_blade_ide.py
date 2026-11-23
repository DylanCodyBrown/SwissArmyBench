"""The Blazor Scripts page's blade IDE on a made-up blade: New blade (its name checked, its kind), the IDE as
a tab (Save, Run with its Result table, Properties), the Blades pane (Open, Pin, Copy the sab.blade line),
Save as…, a starter's Copy as your own, and Remove."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_new_blade_run_save_as_and_remove(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "scripts")
    page.click(".wb-status button:has-text('Blades')")
    pane = page.locator(".blades-pane")
    pane.locator("button[aria-label='New blade']").click()
    dialog = page.locator(".dialog", has_text="New blade")
    dialog.locator("input[aria-label=Name]").fill("made_up_orders")
    expect(dialog.locator("input[type=radio][value=table]")).to_be_checked()
    dialog.locator("button:has-text('Create')").click()
    ide = page.locator(".blade-ide")
    expect(ide.locator(".ide-name")).to_have_text("made_up_orders")
    expect(page.locator(".wb-tab.active")).to_contain_text("made_up_orders")
    expect(ide.locator(".ide-props")).to_be_visible()  # a new blade: Properties open

    ide.locator(".ide-bar button:has-text('Run')").click()
    expect(ide.locator(".ide-run")).to_contain_text("It made a table: 3 rows", timeout=60_000)
    expect(ide.locator(".ide-run table")).to_contain_text("Ada Lane")

    ide.locator("textarea[aria-label=Description]").fill("Made-up orders")
    ide.locator(".ide-bar button:has-text('Save')").first.click()
    expect(ide.locator(".dirty-dot")).to_have_count(0)
    assert call(server, "GET", "/blades/made_up_orders")["description"] == "Made-up orders"

    ide.locator(".ide-bar button:has-text('Save as…')").click()
    save_as = page.locator(".dialog", has_text="Save as")
    save_as.locator("input[aria-label='New name']").fill("made_up_orders_two")
    save_as.locator("button:has-text('Save')").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("made_up_orders_two")

    item = pane.locator(".blade-item", has_text="made_up_orders_two")
    item.locator("button[aria-label=Pin]").click()
    expect(item.locator("button[aria-label=Unpin]")).to_be_visible()

    ide.locator(".ide-bar button[aria-label=More]").click()
    page.locator(".context-menu [role=menuitem]:has-text('Remove')").click()
    page.locator(".dialog-foot .btn.danger, .dialog-foot .btn.primary").last.click()
    expect(page.locator(".wb-tab", has_text="made_up_orders_two")).to_have_count(0)
    page.close()


def test_a_starter_is_copied_as_your_own(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "scripts")
    page.click(".wb-status button:has-text('Blades')")
    pane = page.locator(".blades-pane")
    pane.locator("input[aria-label='Search blades']").fill("Power BI list datasets")
    item = pane.locator(".blade-item", has_text="Power BI list datasets").first
    item.locator("button[aria-label='Copy as your own']").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("Power BI list datasets", timeout=15_000)
    expect(page.locator(".blade-ide .ide-readonly")).to_have_count(0)
    page.close()


def test_insert_a_snippet_fills_its_placeholders(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "snippets.ipynb")
    cells = [{"kind": "dax", "source": "", "number": 1}]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 2})
    page = open_page(browser, server, f"notebooks?path={path}")
    cell = page.locator(".wb-cell").first
    cell.locator("button[aria-label='More actions']").click()
    page.locator(".context-menu [role=menuitem]:has-text('Insert a snippet…')").click()
    picker = page.locator(".dialog", has_text="Insert a DAX snippet")
    picker.locator("input[aria-label='Search snippets']").fill("date table checks")
    picker.locator(".snippet-choice").first.click()
    form = page.locator(".dialog", has_text="DAX date table checks")
    form.locator("input[aria-label='Date table']").fill("MadeUpDates")
    form.locator("input[aria-label='Date column']").fill("Day")
    form.locator("button:has-text('Insert')").click()
    expect(cell.locator(".view-lines")).to_contain_text("MadeUpDates", timeout=15_000)
    page.close()
