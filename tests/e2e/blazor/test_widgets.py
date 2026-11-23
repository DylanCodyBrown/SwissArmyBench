"""The Blazor Widgets window on made-up widgets: the list's groups (Library, the starter packs) and search; a
prebuilt widget read-only with Copy as your own; New widget; a property's default written into the code by
the server's check; the header's Name (checked as typed, kept on Enter) and Description; Code | Preview
(the widget run alone) and Esc back; the Library folded with Ctrl+B; Delete widget asked first. The Library
a navigator by title (a widget's description only once it is chosen); the Library and Properties panes hidden,
moved and stacked, kept after a reload; a Python without Streamlit popping up the one install prompt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, Route, expect

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
    expect(page.locator("[data-dock-pane=library]")).to_have_count(0)
    page.keyboard.press("Control+b")
    expect(page.locator("[data-dock-pane=library]")).to_have_count(1)
    page.close()


def test_the_library_is_a_navigator_by_title(browser: Browser, server: dict[str, Any]) -> None:
    """One line a widget, its title only, under plain headings; a click opens it and shows its description
    under it; the arrow keys walk the list and Enter opens one."""
    page = open_widgets(browser, server, "status_badge")
    library = page.locator("[data-dock-pane=library]")
    expect(library.locator(".wg-pack-desc")).to_have_count(0)
    expect(library.locator(".wg-item:not(.selected) .wg-item-desc")).to_have_count(0)
    expect(library.locator(".wg-item.selected .wg-item-desc")).to_have_count(1)
    expect(library.locator(".wg-item.selected .wg-item-desc")).not_to_be_empty()
    target = library.locator(".wg-item[data-widget=sales_kpi_row]")
    target.click()
    expect(page.locator(".ide-name")).to_have_text("sales_kpi_row")
    expect(target).to_have_attribute("aria-selected", "true")
    expect(target.locator(".wg-item-desc")).to_have_count(1)
    expect(library.locator(".wg-item[data-widget=status_badge] .wg-item-desc")).to_have_count(0)
    target.focus()
    page.keyboard.press("ArrowDown")
    following = page.evaluate("document.activeElement.dataset.widget")
    assert following and following != "sales_kpi_row"
    page.keyboard.press("Enter")
    expect(page.locator(".ide-name")).to_have_text(following)
    page.close()


def test_the_panes_hide_move_and_stack_and_are_kept(browser: Browser, server: dict[str, Any]) -> None:
    """Library and Properties: each hidden from its header and brought back by the bar's toggle; moved to
    the other side from its header's menu, the two stacked one over the other there; the places kept after a
    reload."""
    page = open_widgets(browser, server, "status_badge")
    expect(page.locator("[data-dock-pane=library]")).to_have_attribute("data-side", "left")
    expect(page.locator("[data-dock-pane=properties]")).to_have_attribute("data-side", "right")

    page.click("button[aria-label='Hide Properties']")
    expect(page.locator("[data-dock-pane=properties]")).to_have_count(0)
    toggle = page.locator(".ide-props-toggle")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    toggle.click()
    expect(page.locator("[data-dock-pane=properties]")).to_have_count(1)

    page.click("button[aria-label='Library pane: move or hide']")
    page.locator(".menu-item", has_text="Move to right").click()
    right = page.locator(".dock-right .dock-pane")
    expect(right).to_have_count(2)
    assert [right.nth(i).get_attribute("data-dock-pane") for i in range(2)] == ["properties", "library"]
    expect(page.locator(".dock-left")).to_have_count(0)
    split = page.locator(".dock-right .dock-split")
    expect(split).to_have_count(1)
    above = page.locator("[data-dock-pane=properties]").bounding_box()
    below = page.locator("[data-dock-pane=library]").bounding_box()
    assert above and below and above["y"] + above["height"] <= below["y"] + 1
    before = above["height"]
    split.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    after = page.locator("[data-dock-pane=properties]").bounding_box()
    assert after and after["height"] > before

    page.reload()
    page.wait_for_selector(".dock-right .dock-pane", timeout=60_000)
    expect(page.locator(".dock-right .dock-pane")).to_have_count(2)
    expect(page.locator("[data-dock-pane=library]")).to_have_attribute("data-side", "right")

    page.click("button[aria-label='Library pane: move or hide']")
    page.locator(".menu-item", has_text="Move to left").click()
    expect(page.locator("[data-dock-pane=library]")).to_have_attribute("data-side", "left")
    page.close()


def test_a_missing_package_pops_up_its_install(
    browser: Browser, server: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Preview in a Python without Streamlit (a bare made-up environment; nothing is installed): the one
    install prompt pops up with what is missing, never an error sentence; Not now leaves the Install button in
    the Preview, which opens the prompt again."""
    bare = tmp_path_factory.mktemp("bare") / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], check=True)  # noqa: S603
    python = bare / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    page = open_widgets(browser, server, "status_badge")

    def in_the_bare_python(route: Route) -> None:
        body = json.loads(route.request.post_data or "{}")
        route.continue_(post_data=json.dumps(body | {"python": str(python)}))

    page.route("**/streamlit/widgets/status_badge/run", in_the_bare_python)
    page.click("button[data-mode=preview]")
    prompt = page.locator(".dialog.missing-packages")
    expect(prompt).to_be_visible(timeout=60_000)
    expect(prompt.locator(".dialog-head h2")).to_contain_text("streamlit")
    expect(prompt.locator(".missing-sentence")).to_contain_text("Streamlit widgets will not work without")
    expect(page.locator(".wg-preview-error")).to_have_count(0)
    prompt.get_by_role("button", name="Not now").click()
    expect(prompt).to_have_count(0)
    reminder = page.locator(".wg-missing .missing-reminder button")
    expect(reminder).to_contain_text("Install streamlit")
    reminder.click()
    expect(prompt).to_be_visible()
    prompt.get_by_role("button", name="Not now").click()
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
