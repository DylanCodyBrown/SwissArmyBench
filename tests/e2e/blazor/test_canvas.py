"""The Blazor Canvas on a made-up project (the Streamlit extension on): the landing's canvases and New canvas;
the page tabs (New page, Rename…, Delete page); a container drawn on the grid and its right-click menu
(Insert widget ▸ with its picker, Scrollable, the run group); a widget's Properties (its properties,
Inputs, SIZE, LAYOUT) and a value kept by the server's check; the bottom bar (Desktop | Phone, the preview
width, Snap, Undo, the panes, Wiring, the zoom); the Widgets pane's search and Insert; Builds…; Play in
place and back to Edit."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page

# Play needs a Python with Streamlit (the scratch one on this machine; skipped where there is none).
STREAMLIT = os.environ.get("SWISSARMYBENCH_STREAMLIT_PYTHON", "")


def made_up_canvas(server: dict[str, Any], name: str) -> str:
    call(server, "POST", "/project/new", {"name": name, "type": "streamlit"})
    listed = call(server, "GET", "/streamlit/canvases")
    return str(listed["canvases"][0]["path"])


def open_canvas(browser: Browser, server: dict[str, Any], path: str) -> Page:
    page = open_page(browser, server, f"canvas?path={quote(path)}")
    page.set_viewport_size({"width": 1600, "height": 900})
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    return page


def saved_nodes(path: str) -> list[dict[str, Any]]:
    """Every container and widget the canvas file holds (read from the file: opening it again over the routes
    would be another window's open)."""
    found: list[dict[str, Any]] = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            found.append(item)
            walk(item.get("children") or [])

    for page in json.loads(Path(path).read_text())["pages"]:
        walk(page["children"])
    return found


def draw_container(page: Page, x: int, y: int, w: int, h: int) -> None:
    box = page.locator(".cvs-board").bounding_box()
    assert box
    page.mouse.move(box["x"] + x, box["y"] + y)
    page.mouse.down()
    page.mouse.move(box["x"] + x + w / 2, box["y"] + y + h / 2, steps=4)
    page.mouse.move(box["x"] + x + w, box["y"] + y + h, steps=4)
    page.mouse.up()


def test_the_landing_lists_the_canvases(browser: Browser, server: dict[str, Any]) -> None:
    path = made_up_canvas(server, "Landing")
    page = open_page(browser, server, "canvas")
    expect(page.locator(".cvs-landing h1")).to_have_text("Canvas")
    expect(page.locator(".cvs-landing-item")).to_contain_text(Path(path).name.split(".")[0])
    page.click("button:has-text('New canvas')")
    page.locator(".dialog input").fill("Second")
    page.keyboard.press("Enter")
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    assert any(c["name"].lower() == "second" for c in call(server, "GET", "/streamlit/canvases")["canvases"])
    page.close()


def test_page_tabs_and_a_drawn_container_and_its_menu(browser: Browser, server: dict[str, Any]) -> None:
    path = made_up_canvas(server, "Tabs")
    page = open_canvas(browser, server, path)
    expect(page.locator(".cvs-tab")).to_have_text(["Page 1"])
    page.click("button[aria-label='New page']")
    expect(page.locator(".cvs-tab")).to_have_count(2)
    page.locator(".cvs-tab").nth(1).dblclick()
    page.locator(".dialog input").fill("Reports")
    page.keyboard.press("Enter")
    expect(page.locator(".cvs-tab").nth(1)).to_have_text("Reports")
    page.locator(".cvs-tab").nth(1).click(button="right")
    page.click(".cvs-menu-item:has-text('Delete page')")
    expect(page.locator(".cvs-tab")).to_have_count(1)
    page.locator(".cvs-tab").first.click(button="right")
    expect(page.locator(".cvs-menu-item:has-text('Delete page')")).to_be_disabled()
    page.keyboard.press("Escape")

    expect(page.locator(".cvs-empty")).to_contain_text("Drag on the grid to draw a container")
    draw_container(page, 60, 60, 300, 200)
    expect(page.locator(".cvs-container")).to_have_count(1)
    expect(page.locator(".cvs-props-section h3").first).to_have_text("CONTAINER")
    assert [n["kind"] for n in saved_nodes(path)] == ["container"]

    page.locator(".cvs-container").click(button="right", position={"x": 40, "y": 40})
    menu = page.locator(".cvs-menu[role=menu]")
    for words in (
        "Insert widget",
        "Insert container",
        "Scrollable",
        "Resizable by viewers",
        "Delete",
        "Play",
        "Launch",
        "Export…",
    ):
        expect(menu.locator(".cvs-menu-item", has_text=words).first).to_be_visible()
    menu.locator(".cvs-menu-item", has_text="Scrollable").click()
    expect(page.locator(".cvs-container.scrollable")).to_have_count(1)
    page.locator(".cvs-container").click(button="right", position={"x": 40, "y": 40})
    page.locator(".cvs-menu-item", has_text="Insert widget").hover()
    picker = page.locator(".cvs-widget-menu")
    picker.locator("input").fill("status badge")
    picker.locator(".cvs-menu-item[data-widget=status_badge]").click()
    expect(page.locator(".cvs-container .cvs-widget[data-widget=status_badge]")).to_have_count(1)
    page.close()


def test_a_widgets_properties_and_the_bottom_bar(browser: Browser, server: dict[str, Any]) -> None:
    path = made_up_canvas(server, "Props")
    page = open_canvas(browser, server, path)
    page.fill(".cvs-gallery-search", "kpi row")
    card = page.locator(".cvs-card[data-widget=sales_kpi_row]")
    expect(card).to_have_count(1)
    card.dblclick()
    widget = page.locator(".cvs-widget[data-widget=sales_kpi_row]")
    expect(widget).to_have_count(1)
    widget.click()
    pane = page.locator(".cvs-props")
    expect(pane.locator(".cvs-widget-title")).to_have_text("sales_kpi_row")
    for heading in ("WIDGET", "PROPERTIES", "INPUTS", "SIZE", "LAYOUT"):
        expect(pane.locator("h3", has_text=heading)).to_have_count(1)
    currency = pane.locator("[data-property=currency] input")
    currency.fill("CHF")
    currency.press("Tab")
    expect(pane.locator("[data-property=currency] .wg-reset")).to_be_visible()
    widgets = [n for n in saved_nodes(path) if n["kind"] == "widget"]
    assert widgets[0]["values"]["currency"] == "CHF"
    expect(pane.locator(".cvs-source").first).to_contain_text("Not wired")

    bottom = page.locator(".cvs-bottom")
    undo = bottom.locator("button[aria-label=Undo]")
    expect(undo).to_be_enabled()
    page.click("button[data-layout=phone]")
    expect(bottom.locator(".cvs-preview-width")).to_have_value("390")
    page.click("button[data-layout=desktop]")
    page.click("button[aria-label='Zoom in']")
    expect(bottom.locator(".cvs-zoom-label")).to_have_text("125%")
    page.click(".cvs-zoom-label")
    expect(bottom.locator(".cvs-zoom-label")).to_have_text("100%")
    page.click(".cvs-bottom button:has-text('Properties')")
    expect(page.locator(".cvs-props")).to_have_count(0)
    page.click(".cvs-bottom button:has-text('Properties')")
    page.click(".cvs-bottom button:has-text('Wiring')")
    expect(page.locator(".cvs-wires")).to_have_count(1)
    page.click(".cvs-play-more")
    page.click(".cvs-menu-item:has-text('Builds…')")
    expect(page.locator(".dialog[aria-label=Builds]")).to_contain_text("No build yet: Launch makes the first")
    page.keyboard.press("Escape")

    # Narrow, the bottom bar wraps onto a second line: every tool stays on screen, none cut off.
    page.set_viewport_size({"width": 760, "height": 900})
    expect(bottom.locator(".cvs-fit")).to_be_in_viewport()
    assert bottom.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    within = bottom.evaluate(
        "e => [...e.children].every(c => c.getBoundingClientRect().right"
        " <= e.getBoundingClientRect().right + 1)"
    )
    assert within
    page.close()


def test_the_panes_hide_move_and_stack_and_are_kept(browser: Browser, server: dict[str, Any]) -> None:
    """The Canvas's Widgets and Properties panes in the same dock as the Widgets window: Widgets on the
    left and Properties on the right at first; hidden from a header and back from the bottom bar; moved to the
    other side and stacked there; kept after a reload."""
    path = made_up_canvas(server, "Docked")
    page = open_canvas(browser, server, path)
    expect(page.locator(".cvs-gallery")).to_have_attribute("data-side", "left")
    expect(page.locator(".cvs-props")).to_have_attribute("data-side", "right")
    page.click("button[aria-label='Hide Widgets']")
    expect(page.locator(".cvs-gallery")).to_have_count(0)
    expect(page.locator(".cvs-bottom button[data-pane=widgets]")).to_have_attribute("aria-pressed", "false")
    page.click(".cvs-bottom button[data-pane=widgets]")
    expect(page.locator(".cvs-gallery")).to_have_count(1)

    page.locator(".cvs-gallery .dock-pane-head").click(button="right")
    page.locator(".menu-item", has_text="Move to right").click()
    expect(page.locator(".dock-right .dock-pane")).to_have_count(2)
    expect(page.locator(".dock-left")).to_have_count(0)
    expect(page.locator(".cvs-board")).to_be_visible()

    page.reload()
    expect(page.locator(".cvs-board")).to_be_visible(timeout=60_000)
    expect(page.locator(".cvs-gallery")).to_have_attribute("data-side", "right")
    expect(page.locator(".dock-right .dock-split")).to_have_count(1)
    page.close()


def test_play_shows_the_page_in_place(browser: Browser, server: dict[str, Any]) -> None:
    if not Path(STREAMLIT).is_file():
        import pytest

        pytest.skip("No Python with Streamlit here (SWISSARMYBENCH_STREAMLIT_PYTHON).")
    path = made_up_canvas(server, "Plays")
    page = open_canvas(browser, server, path)
    page.click(".cvs-play")
    expect(page.locator(".cvs-live-frame")).to_be_visible(timeout=90_000)
    expect(page.locator(".cvs-play")).to_contain_text("Stop")
    page.click(".cvs-edit")
    expect(page.locator(".cvs-board")).to_be_visible()
    expect(page.locator(".cvs-play")).to_contain_text("Play")
    page.close()


def test_a_widget_dragged_from_the_widgets_pane_lands_where_it_is_dropped(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The owner's screenshot, 2026-11-23: a drop said "There is no widget called _dragging." (the board was
    handed the word, not the widget being dragged). Dropped into a container and onto the bare page (a wide
    one near the right edge slid left to fit), the dragged widget goes in, and no error shows."""
    path = made_up_canvas(server, "Dragged")
    page = open_canvas(browser, server, path)
    draw_container(page, 60, 60, 420, 260)
    expect(page.locator(".cvs-container")).to_have_count(1)
    page.fill(".cvs-gallery-search", "status badge")
    page.locator(".cvs-card[data-widget=status_badge]").drag_to(
        page.locator(".cvs-container"), target_position={"x": 60, "y": 60}
    )
    expect(page.locator(".cvs-container .cvs-widget[data-widget=status_badge]")).to_have_count(1)
    page.fill(".cvs-gallery-search", "kpi row")
    page.locator(".cvs-card[data-widget=sales_kpi_row]").drag_to(
        page.locator(".cvs-board"), target_position={"x": 900, "y": 380}
    )
    expect(page.locator(".cvs-widget[data-widget=sales_kpi_row]")).to_have_count(1)
    expect(page.locator(".error-note")).to_have_count(0)
    placed = {n.get("widget") for n in saved_nodes(path) if n["kind"] == "widget"}
    assert placed == {"status_badge", "sales_kpi_row"}
    page.close()
