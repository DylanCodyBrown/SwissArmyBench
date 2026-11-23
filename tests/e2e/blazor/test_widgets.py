"""The Blazor Widgets window on made-up widgets: the list's groups (Library, the starter packs) and search; a
prebuilt widget read-only with Copy as your own; New widget; a property's default written into the code by
the server's check; the header's Name (checked as typed, kept on Enter) and Description; Code | Preview
(the widget run alone) and Esc back; the list folded with Ctrl+B; Delete widget asked first."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page


def open_widgets(browser: Browser, server: dict[str, Any], name: str = "") -> Page:
    page = open_page(browser, server, f"widgets{f'?name={name}' if name else ''}")
    page.set_viewport_size({"width": 1500, "height": 900})
    expect(page.locator(".wg-item").first).to_be_visible(timeout=30_000)
    return page


def test_the_list_and_a_prebuilt_widget(browser: Browser, server: dict[str, Any]) -> None:
    page = open_widgets(browser, server, "sales_kpi_row")
    expect(page.locator(".wg-group", has_text="Library")).to_have_count(1)
    expect(page.locator(".wg-group", has_text="Sales dashboard")).to_have_count(1)
    expect(page.locator(".wg-empty")).to_have_text("None yet: New widget, or Copy as your own.")
    expect(page.locator(".ide-name")).to_have_text("sales_kpi_row")
    expect(page.locator(".wg-saved")).to_have_text("Prebuilt: read-only")
    expect(page.locator(".wg-contract[data-section=inputs] .wg-port")).to_have_count(2)
    page.fill(".wg-search", "status badge")
    expect(page.locator(".wg-item")).to_have_count(1)
    page.fill(".wg-search", "")
    page.click("button:has-text('Copy as your own')")
    expect(page.locator(".wg-saved")).not_to_have_text("Prebuilt: read-only")
    copied = page.locator(".ide-name").inner_text()
    assert copied != "sales_kpi_row"
    page.keyboard.press("Control+b")
    expect(page.locator(".wg")).to_have_class("wg wg-page no-list")
    page.keyboard.press("Control+b")
    page.close()


def test_a_new_widgets_properties_and_header(browser: Browser, server: dict[str, Any]) -> None:
    page = open_widgets(browser, server)
    page.click("button:has-text('New widget')")
    expect(page.locator(".wg-item.selected .wg-item-name")).to_have_text("my_widget")
    name = "my_widget"
    title = page.locator("[data-property=title] input")
    expect(title).to_have_value("New widget")
    title.fill("Made-up sales")
    title.press("Tab")
    expect(page.locator(".monaco-editor")).to_contain_text("Made-up sales")
    assert call(server, "GET", f"/streamlit/widgets/{name}")["code"].count('"Made-up sales"') == 1

    box = page.locator(".wg-name")
    box.fill("not a name!")
    expect(page.locator(".wg-name-line")).not_to_be_empty()
    box.fill("made_up_metric")
    box.press("Enter")
    expect(page.locator(".ide-name")).to_have_text("made_up_metric")
    page.fill(".wg-description", "A made-up metric")
    page.locator(".wg-description").blur()
    expect(page.locator(".wg-item.selected .wg-item-desc")).to_have_text("A made-up metric")

    page.click(".wg-props-foot button:has-text('Delete widget')")
    page.click(".dialog-foot button:has-text('Delete')")
    expect(page.locator(".wg-item[data-widget=made_up_metric]")).to_have_count(0)
    page.close()


def test_preview_runs_the_widget_in_place(browser: Browser, server: dict[str, Any]) -> None:
    if not Path(os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON", "")).is_file():
        pytest.skip("No Python with Streamlit here (SWISSARMYBENCH_STREAMLIT_PYTHON).")
    page = open_widgets(browser, server, "status_badge")
    page.click("button[data-mode=preview]")
    expect(page.locator(".wg-frame")).to_be_visible(timeout=90_000)
    expect(page.locator("button[data-mode=preview]")).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Escape")
    expect(page.locator(".wg-frame")).to_have_count(0)
    expect(page.locator("button[data-mode=code]")).to_have_attribute("aria-pressed", "true")
    page.close()


def test_the_panel_under_the_code_and_its_problems(browser: Browser, server: dict[str, Any]) -> None:
    """The IDE's Output | Result | Problems panel under the code (the classic codeIde.ts runPanel): folded to
    its tabs until wanted, Problems the lint's, each a link to its line."""
    page = open_widgets(browser, server)
    page.click("button:has-text('New widget')")
    panel = page.locator(".wg-main .ide-run")
    expect(panel).to_have_class("ide-run folded")
    expect(panel.get_by_role("tab", name="Output")).to_be_visible()
    panel.get_by_role("tab", name="Result").click()
    expect(panel.locator(".ide-result")).to_contain_text("Nothing ran yet.")
    page.locator(".wg-main .monaco-editor .view-lines").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\nprint(undefined_made_up_name)\n")
    expect(panel.locator(".ide-count")).to_be_visible(timeout=20_000)
    panel.get_by_role("tab", name="Problems").click()
    expect(panel.locator(".ide-problem").first).to_contain_text("undefined_made_up_name")
    panel.get_by_role("button", name="Fold the panel").click()
    expect(panel).to_have_class("ide-run folded")
    page.click(".wg-props-foot button:has-text('Delete widget')")
    page.click(".dialog-foot button:has-text('Delete')")
    page.close()
