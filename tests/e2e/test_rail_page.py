# ruff: noqa: F811
"""The rail (the owner, 2026-11-16: "this app needs a navigation pane somehow"; a slim icon rail down the
left of every page and window), in a real browser: on every page and window, each area goes to its place
(this page's view, a page of its own: Settings, Connections, a kind's landing page in the Workbench),
the current area is marked and follows Back, Forward and a reload, the keyboard moves along it,
Notebooks, Scripts and Apps land on their kind's page in the Workbench (an app chosen there comes with
the Streamlit cells pane beside its canvas) or open a window of their own, and nothing sits under it.
Made-up data only.

With SWISSARMYBENCH_RAIL_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import os
import re
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import window
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401

AREAS = [
    "grids",
    "visualizations",
    "erd",
    "notebooks",
    "scripts",
    "apps",
    "blades",
    "connections",
    "settings",
]
NAMES = [
    "Grids",
    "Visualizations",
    "ERD",
    "Notebooks",
    "Scripts",
    "Apps",
    "Blades",
    "Connections",
    "Settings",
]
SHOTS = os.environ.get("SWISSARMYBENCH_RAIL_SHOTS")
FILTER = '# Region filter\nregion = st.selectbox("Region", ["North", "South"], key="rail_region")'
TOTAL = '# Apples\nst.metric("Apples", 49)'


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orchard(server: dict[str, Any]) -> Iterator[str]:
    url = push_client.push(
        pd.DataFrame({"orchard": ["North", "South", "East"], "apples": [12, 7, 30]}),
        name="rail_orchard",
        new_grid=True,
    )
    yield url
    try:
        call(server, "DELETE", f"/grids/{grid_of(url)}")
    except Exception:  # noqa: S110 (closed by the test)
        pass
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")


def rail(page: Page) -> Any:
    return page.get_by_role("navigation", name="Areas")


def area(page: Page, name: str) -> Any:
    return rail(page).locator(f"[data-area='{name}']")


def current(page: Page) -> Any:
    return rail(page).locator("[aria-current='page']")


def right_edge(page: Page) -> float:
    box = rail(page).bounding_box()
    assert box is not None
    return float(box["x"] + box["width"])


def left_of(page: Page, selector: str) -> float:
    found = page.locator(selector).first
    found.wait_for(timeout=10000)
    box = found.bounding_box()
    assert box is not None, selector
    return float(box["x"])


def home_page(browser: Browser, url: str, dark: bool = False) -> Page:
    page = browser.new_context(
        viewport={"width": 1300, "height": 820},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def test_the_rail_goes_to_each_area_and_marks_the_current_one(
    browser: Browser, server: dict[str, Any], orchard: str
) -> None:
    page = home_page(browser, orchard)
    base = f"http://127.0.0.1:{server['port']}"
    # Every area, in the rail's order, each named (the tip is not read twice: aria-hidden).
    buttons = rail(page).get_by_role("button")
    expect(buttons).to_have_count(len(AREAS))
    assert [buttons.nth(i).get_attribute("data-area") for i in range(len(AREAS))] == AREAS
    for i, name in enumerate(NAMES):
        expect(buttons.nth(i)).to_have_accessible_name(name)
    expect(current(page)).to_have_attribute("data-area", "grids")
    # 48px, and nothing under it: the mark, the tabs and the grid's first column start right of it.
    assert right_edge(page) <= 48.5
    for selector in (".tabbar > a.app-mark", ".tabs-row", ".ag-header-cell:visible"):
        assert left_of(page, selector) >= right_edge(page) - 0.5, selector
    # Settings sits at the bottom, apart from the others.
    settings = area(page, "settings").bounding_box()
    connections = area(page, "connections").bounding_box()
    assert settings and connections and settings["y"] > connections["y"] + 150
    # The code areas wear their kind colours.
    for name, kind in (("notebooks", "notebook"), ("scripts", "script"), ("apps", "app")):
        expect(area(page, name)).to_have_class(re.compile(rf"\bkm-{kind}\b"))
    shot(page, "rail-home")

    # A click is a move like any other: pushed, so Back and Forward walk the areas, and a reload keeps one.
    area(page, "visualizations").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(page).to_have_url(f"{base}/workspace?view=visualizations")
    expect(current(page)).to_have_attribute("data-area", "visualizations")
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    expect(current(page)).to_have_attribute("data-area", "erd")
    page.go_back()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(current(page)).to_have_attribute("data-area", "visualizations")
    page.go_forward()
    expect(current(page)).to_have_attribute("data-area", "erd")
    page.reload()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd", timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "erd")
    # The tab bar's own tabs move the mark too.
    page.locator(f".tab-item[data-grid='{grid_of(orchard)}']").click()
    expect(current(page)).to_have_attribute("data-area", "grids")

    # Connections and Settings are pages over this one, in the address (2026-11-16: no dialogs); Back
    # takes them away and moves the mark back.
    area(page, "connections").click()
    expect(page).to_have_url(re.compile(r"open=connections"))
    expect(page.locator(".area-page[data-page='connections']")).to_be_visible()
    expect(page.locator("dialog[open]")).to_have_count(0)
    expect(current(page)).to_have_attribute("data-area", "connections")
    page.go_back()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(current(page)).to_have_attribute("data-area", "grids")
    area(page, "settings").click()
    expect(page).to_have_url(re.compile(r"open=settings"))
    expect(current(page)).to_have_attribute("data-area", "settings")
    page.go_back()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(current(page)).to_have_attribute("data-area", "grids")

    # Grids from Visualizations: the grids, as the mark goes.
    area(page, "visualizations").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    area(page, "grids").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grid")
    expect(page).to_have_url(re.compile(r"/g/"))
    page.context.close()


def test_the_keyboard_moves_along_the_rail_and_the_tip_names_each_area(
    browser: Browser, orchard: str
) -> None:
    page = home_page(browser, orchard)
    # One stop in the Tab order: the current area's.
    assert [area(page, a).get_attribute("tabindex") for a in AREAS] == ["0"] + ["-1"] * 8
    area(page, "grids").focus()
    tip = area(page, "grids").locator(".nav-rail-tip")
    expect(tip).to_be_visible()  # the name shows on keyboard focus, not only on hover
    expect(tip).to_contain_text("Grids")
    page.keyboard.press("ArrowDown")
    expect(area(page, "visualizations")).to_be_focused()
    expect(area(page, "visualizations").locator(".nav-rail-tip")).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(current(page)).to_have_attribute("data-area", "visualizations")
    area(page, "visualizations").focus()
    page.keyboard.press("ArrowDown")
    expect(area(page, "erd")).to_be_focused()
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")  # past the first: round to Settings
    expect(area(page, "settings")).to_be_focused()
    page.keyboard.press("Home")
    expect(area(page, "grids")).to_be_focused()
    # Alt+Home is Home (the Start view, 2026-11-16), wherever the focus is; the rail marks no area there.
    page.keyboard.press("Alt+Home")
    expect(page.locator(".workspace")).to_have_attribute("data-view", "start")
    expect(current(page)).to_have_count(0)
    # The tip on hover.
    page.evaluate("document.activeElement.blur()")
    area(page, "apps").hover()
    expect(area(page, "apps").locator(".nav-rail-tip")).to_be_visible()
    shot(page, "rail-tip")
    page.mouse.move(700, 400)
    page.context.close()


def test_a_rail_click_moves_this_tab_and_a_new_window_is_only_on_request(
    browser: Browser, server: dict[str, Any], orchard: str
) -> None:
    """The owner (2026-11-16): "the rail icons is opening a new tab every time instead of navigating the
    current page, the open in new tab is optional"."""
    page = home_page(browser, orchard)
    page.on("dialog", lambda d: d.accept())  # leaving a Workbench with unsaved edits asks first
    pages = len(page.context.pages)
    # Notebooks from the home page: this tab goes to the Workbench (code still never sits in the grid page).
    area(page, "notebooks").click()
    expect(page).to_have_url(re.compile(r"/workbench\?kind=notebook"), timeout=20000)
    expect(rail(page)).to_be_visible()
    expect(current(page)).to_have_attribute("data-area", "notebooks")
    assert len(page.context.pages) == pages
    assert left_of(page, ".wb-top") >= right_edge(page) - 0.5
    # The notebooks' landing page (2026-11-16: no menu beside the icon): New is on its own panel.
    landing = page.locator(".wb-landing")
    expect(landing).to_be_visible(timeout=20000)
    expect(page.get_by_role("menu")).to_have_count(0)
    landing.get_by_role("button", name="New notebook").click()
    expect(page.locator(".wb-tab").first).to_be_visible(timeout=20000)
    # Scripts, inside the Workbench: its page, New script; Notebooks lands on its page again, pushed.
    area(page, "scripts").click()
    expect(page).to_have_url(re.compile(r"kind=script"))
    landing.get_by_role("button", name="New script").click()
    expect(page.locator(".wb-tab")).to_have_count(2, timeout=20000)
    area(page, "notebooks").click()
    expect(current(page)).to_have_attribute("data-area", "notebooks")
    page.go_back()
    expect(current(page)).to_have_attribute("data-area", "scripts")
    page.mouse.move(900, 500)
    shot(page, "rail-workbench")
    # Settings is a page in the Workbench itself.
    area(page, "settings").click()
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    page.go_back()
    expect(current(page)).to_have_attribute("data-area", "scripts")

    # Visualizations, from the Workbench: this tab goes home, at Visualizations.
    area(page, "visualizations").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent", timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "visualizations")
    # Blades: this tab goes to the blades page, Blades marked; Settings opens there; ERD comes home.
    area(page, "blades").click()
    expect(page).to_have_url(re.compile(r"/catalog"), timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "blades")
    assert left_of(page, ".cat-top") >= right_edge(page) - 0.5
    area(page, "settings").click()
    expect(page).to_have_url(re.compile(r"open=settings"))
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    page.go_back()
    expect(current(page)).to_have_attribute("data-area", "blades")
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd", timeout=20000)
    # Back walks the same tab back through the pages.
    page.go_back()
    expect(page).to_have_url(re.compile(r"/catalog"), timeout=20000)
    assert len(page.context.pages) == pages

    # A new window only on request: Ctrl+click, a middle click, or the right-click's menu, on every area.
    with page.context.expect_page() as clicked:
        area(page, "scripts").click(modifiers=["Control"])
    other = clicked.value
    expect(other).to_have_url(re.compile(r"/workbench\?kind=script"), timeout=20000)
    other.close()
    area(page, "visualizations").click(button="right")
    with page.context.expect_page() as popped:
        page.get_by_role("menuitem", name="Open in a new window").click()
    sandbox = popped.value
    expect(sandbox.locator(".workspace")).to_have_attribute("data-view", "agent", timeout=20000)
    sandbox.close()
    with page.context.expect_page() as middle:
        area(page, "grids").click(button="middle")
    middle.value.close()
    expect(page).to_have_url(re.compile(r"/catalog"))  # this tab stayed where it was
    page.context.close()


def test_apps_shows_the_streamlit_cells_pane_beside_the_canvas(
    browser: Browser, server: dict[str, Any], orchard: str, tmp_path: Path
) -> None:
    """The owner (2026-11-16): "do we still get a cell navigator to help build the streamlit app page?"
    Apps on the rail: the Data panel shows, its Streamlit cells pane unfolded, side by side with the
    rail and the canvas; a cell from it drags onto the page."""
    book = tmp_path / "rail mockups.ipynb"
    cells = [{"kind": "code", "source": FILTER}, {"kind": "code", "source": TOTAL}]
    call(server, "POST", "/workbench/save", {"path": str(book), "cells": cells})
    workbench = browser.new_context(
        viewport={"width": 1400, "height": 860}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    workbench.goto(
        f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={quote(str(book))}"
    )
    expect(workbench.locator(".wb-tab")).to_have_count(1, timeout=20000)
    # The Data panel folded and the pane folded, as a person may have left them.
    window(server, "view.toggleSidebar", collapsed=True)
    expect(workbench.locator(".wb-data.collapsed")).to_be_visible()
    area(workbench, "apps").click()
    expect(workbench.get_by_role("menu")).to_have_count(0)
    workbench.locator(".wb-landing").get_by_role("button", name="New Streamlit app").click()
    board = workbench.locator(".cv-board")
    expect(board).to_be_visible(timeout=20000)
    expect(current(workbench)).to_have_attribute("data-area", "apps")
    data = workbench.locator(".wb-data")
    expect(data).not_to_have_class(re.compile(r"\bcollapsed\b"))
    pane = workbench.locator(".wb-st")
    expect(pane.locator(".wb-st-cell")).to_have_count(2, timeout=20000)
    # Side by side: the rail, then the Data panel, then the canvas.
    assert left_of(workbench, ".wb-data") >= right_edge(workbench) - 0.5
    data_box = data.bounding_box()
    assert data_box is not None and left_of(workbench, ".cv-board") >= data_box["x"] + data_box["width"] - 1
    # The Starters switch stays.
    expect(workbench.locator(".wb-data").get_by_role("button", name=re.compile("Starters"))).to_have_count(1)
    pane.locator(".wb-st-cell").nth(1).drag_to(board)
    expect(workbench.locator(".cv-block")).to_have_count(1, timeout=10000)
    expect(workbench.locator(".cv-block .cv-block-where")).to_have_text("rail mockups.ipynb @cell2")
    expect(pane.locator(".wb-st-cell.placed")).to_have_count(1)
    shot(workbench, "rail-apps-cells-pane")
    # Folded again, the app chosen on the Apps page unfolds it again (no menu anywhere).
    pane.locator("#wb-data-streamlit").click()
    expect(pane.locator(".wb-st-list")).to_be_hidden()
    area(workbench, "notebooks").click()
    area(workbench, "apps").click()
    expect(workbench.get_by_role("menu")).to_have_count(0)
    workbench.locator(".wb-landing-card").first.click()
    expect(board).to_be_visible()
    expect(pane.locator(".wb-st-list")).to_be_visible()
    workbench.context.close()


def test_the_steps_window_has_the_rail_and_grids_brings_the_home_window_forward(
    browser: Browser, orchard: str
) -> None:
    page = home_page(browser, orchard)
    with page.context.expect_page() as opened:
        page.evaluate("window.open(location.pathname + '?panel=steps', 'steps-rail', 'width=520,height=820')")
    steps = opened.value
    expect(steps.locator(".steps-panel .step.source")).to_be_visible(timeout=20000)
    expect(rail(steps)).to_be_visible()
    expect(current(steps)).to_have_attribute("data-area", "grids")
    assert left_of(steps, ".window-top") >= right_edge(steps) - 0.5
    pages = len(page.context.pages)
    # A rail click moves this tab (2026-11-16: "the open in new tab is optional"): the steps window
    # itself goes to the grids; the home window stays where it was.
    page.locator(".nav-rail [data-area='visualizations']").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    area(steps, "grids").click()
    expect(steps.locator(".workspace")).to_have_attribute("data-view", "grid", timeout=20000)
    expect(current(steps)).to_have_attribute("data-area", "grids")
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    assert len(page.context.pages) == pages
    page.context.close()


def test_the_rail_has_no_switch_and_nothing_repeats_it(
    browser: Browser, server: dict[str, Any], orchard: str
) -> None:
    page = home_page(browser, orchard, dark=True)
    shot(page, "rail-dark")
    # The owner (2026-11-16): the rail is how you get around, so it is always there, and the top tabs and
    # the Application row no longer repeat it.
    for gone in (".tab-agent", ".tab-erd", ".tab-workbench"):
        expect(page.locator(gone)).to_have_count(0)
    for name in ("Settings", "Connections", "Blades and catalog"):
        expect(page.locator(".app-row").get_by_role("button", name=name, exact=True)).to_have_count(0)
    page.locator(".nav-rail [data-area='settings']").click()
    panels = page.locator(".area-page[data-page='settings'] fieldset", has_text="Panels")
    expect(panels.get_by_role("group", name="Grid page")).to_be_visible()
    expect(panels.get_by_label("Navigation rail")).to_have_count(0)
    with pytest.raises(urllib.error.HTTPError):
        call(server, "PUT", "/panels", {"app.rail": False}, agent=True)
    page.go_back()
    expect(rail(page)).to_be_visible()
    page.context.close()
