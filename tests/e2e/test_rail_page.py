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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.asks import accept_asks
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401

# In the order of the work (the owner, 2026-11-17).
AREAS = [
    "projects",  # first: Home (the owner, 2026-11-21; its address open=projects)
    "connections",
    "apis",
    "environment",  # everything the project holds, in the Structures and Variables places (2026-11-22)
    "data",  # the one place to browse tables: Catalog (2026-11-21)
    "grids",
    "erd",
    "scripts",  # its Blades a pane on the right: no Blades icon (the owner, 2026-11-22)
    "notebooks",
    "canvas",
    "widgets",
    "analyze",
    "session",
    "extensions",
    "settings",
]
NAMES = [
    "Home",
    "Connections",
    "APIs",
    "Environment",
    "Catalog",
    "Grids",
    "ERD",
    "Scripts",
    "Notebooks",
    "Canvas",
    "Widgets",
    "Analyze",
    "Session",
    "Extensions",
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
    buttons = rail(page).get_by_role("toolbar").get_by_role("button")  # the names toggle sits below
    expect(buttons).to_have_count(len(AREAS))
    assert [buttons.nth(i).get_attribute("data-area") for i in range(len(AREAS))] == AREAS
    for i, name in enumerate(NAMES):
        expect(buttons.nth(i)).to_have_accessible_name(name)
    expect(current(page)).to_have_attribute("data-area", "grids")
    # 60px (the owner, 2026-11-18), 176px with its names (on by default, 2026-11-19); nothing under it.
    assert right_edge(page) <= 176.5
    for selector in (".tabbar", ".tabs-row", ".ag-header-cell:visible"):
        assert left_of(page, selector) >= right_edge(page) - 0.5, selector
    # The mark is the rail's first item, its red square kept; the icons 24px so more fit (2026-11-18).
    expect(area(page, "projects").locator('[data-icon="home"]')).to_be_visible()  # a plain icon
    expect(page.locator(".tabbar .app-mark")).to_have_count(0)
    icon = area(page, "connections").locator(".icon-svg").bounding_box()
    assert icon and round(icon["width"]) == 24 and round(icon["height"]) == 24
    item = area(page, "connections").bounding_box()
    assert item and 34 <= item["height"] <= 46
    # Settings sits at the bottom, apart from the others.
    settings = area(page, "settings").bounding_box()
    connections = area(page, "connections").bounding_box()
    assert settings and connections and settings["y"] > connections["y"] + 150
    # The code areas wear their kind colours.
    for name, kind in (("notebooks", "notebook"), ("scripts", "script")):
        expect(area(page, name)).to_have_class(re.compile(rf"\bkm-{kind}\b"))
    shot(page, "rail-home")

    # A click is a move like any other: pushed, so Back and Forward walk the areas, and a reload keeps one.
    area(page, "analyze").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(page).to_have_url(f"{base}/workspace?view=analyze")
    expect(current(page)).to_have_attribute("data-area", "analyze")
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    expect(current(page)).to_have_attribute("data-area", "erd")
    page.go_back()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(current(page)).to_have_attribute("data-area", "analyze")
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

    # Grids from Analyze: the grids, as the mark goes.
    area(page, "analyze").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    area(page, "grids").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grid")
    expect(page).to_have_url(re.compile(r"/g/"))
    page.context.close()


def test_the_keyboard_moves_along_the_rail_and_the_tip_names_each_area(
    browser: Browser, server: dict[str, Any], orchard: str
) -> None:
    # The icons alone (the names beside them are on by default: the tip is for the icon rail).
    call(server, "PUT", "/rail", {"labels": False})
    try:
        keyboard_and_tips(browser, orchard)
    finally:
        call(server, "PUT", "/rail", {"labels": True})


def keyboard_and_tips(browser: Browser, orchard: str) -> None:
    page = home_page(browser, orchard)
    expect(page.locator("html")).not_to_have_class(re.compile(r"\brail-names\b"))
    # One stop in the Tab order: the current area's.
    stops = [area(page, a).get_attribute("tabindex") for a in AREAS]
    assert stops == ["0" if a == "grids" else "-1" for a in AREAS]  # the current area's (the grids)
    area(page, "grids").focus()
    tip = area(page, "grids").locator(".nav-rail-tip")
    expect(tip).to_be_visible()  # the name shows on keyboard focus, not only on hover
    expect(tip).to_contain_text("Grids")
    page.keyboard.press("ArrowDown")  # the order of the work (2026-11-17): Grids, then the ERD
    expect(area(page, "erd")).to_be_focused()
    expect(area(page, "erd").locator(".nav-rail-tip")).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    expect(current(page)).to_have_attribute("data-area", "erd")
    area(page, "erd").focus()
    page.keyboard.press("ArrowDown")
    expect(area(page, "scripts")).to_be_focused()  # Scripts after the ERD (no Blades icon, 2026-11-22)
    for _ in range(6):
        page.keyboard.press("ArrowUp")  # the ERD, the grids, Catalog, Environment, APIs, Connections
    expect(area(page, "connections")).to_be_focused()
    page.keyboard.press("ArrowUp")  # the mark, the first (2026-11-18)
    expect(area(page, "projects")).to_be_focused()
    page.keyboard.press("ArrowUp")  # past the first: round to Settings
    expect(area(page, "settings")).to_be_focused()
    page.keyboard.press("Home")
    expect(area(page, "projects")).to_be_focused()
    expect(area(page, "projects").locator(".nav-rail-tip")).to_contain_text("Alt+Home")
    # Alt+Home is Home (the Projects page, 2026-11-18), wherever the focus is; the mark is the current one.
    area(page, "erd").focus()
    page.keyboard.press("Alt+Home")
    expect(page.locator(".area-page[data-page='projects']")).to_be_visible()
    expect(current(page)).to_have_attribute("data-area", "projects")
    # The tip on hover.
    page.evaluate("document.activeElement.blur()")
    area(page, "canvas").hover()
    expect(area(page, "canvas").locator(".nav-rail-tip")).to_be_visible()
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
    accept_asks(page)
    pages = len(page.context.pages)
    # Notebooks from the home page: this tab goes to the Notebooks page (never code in the grid page).
    area(page, "notebooks").click()
    expect(page).to_have_url(re.compile(r"/notebooks\?kind=notebook"), timeout=20000)
    expect(rail(page)).to_be_visible()
    expect(current(page)).to_have_attribute("data-area", "notebooks")
    assert len(page.context.pages) == pages
    # Its landing (2026-11-16: no menu beside the icon); New is the page's own (the explorer's "…").
    landing = page.locator(".wb-landing")
    expect(landing).to_be_visible(timeout=20000)
    expect(page.get_by_role("menu")).to_have_count(0)
    expect(page.locator(".wb-codex.page-notebooks")).to_be_visible()
    page.get_by_role("button", name="Workbench menu", exact=True).click()
    expect(page.get_by_role("menuitem", name="New script")).to_have_count(0)  # only its own kind
    page.get_by_role("menuitem", name="New notebook", exact=True).click()
    expect(page.locator(".wb-tab").first).to_be_visible(timeout=20000)
    # Scripts from the Notebooks page: the Scripts page, a window of its own (the owner, 2026-11-21:
    # "notebooks and scripts should not reuse the same page"): no notebook tab there.
    with page.context.expect_page() as opened:
        area(page, "scripts").click()
    scripts = opened.value
    expect(scripts).to_have_url(re.compile(r"/scripts\?kind=script"), timeout=20000)
    expect(current(scripts)).to_have_attribute("data-area", "scripts")
    expect(scripts.locator(".wb-codex.page-scripts")).to_be_visible(timeout=20000)
    expect(scripts.locator(".wb-tab")).to_have_count(0)
    scripts.get_by_role("button", name="Workbench menu", exact=True).click()
    scripts.get_by_role("menuitem", name="New script", exact=True).click()
    expect(scripts.locator(".wb-tab")).to_have_count(1, timeout=20000)
    expect(page.locator(".wb-tab")).to_have_count(1)  # the notebook stayed on its own page
    scripts.close()
    page.mouse.move(900, 500)
    shot(page, "rail-workbench")
    # Settings is a page in the Workbench itself.
    area(page, "settings").click()
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    page.go_back()
    expect(current(page)).to_have_attribute("data-area", "notebooks")

    # Analyze, from the Workbench: this tab goes home, at Analyze.
    area(page, "analyze").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent", timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "analyze")
    # Scripts: this tab goes to the Scripts page (its Blades a pane there: no Blades icon, 2026-11-22),
    # Scripts marked; Settings opens there; ERD comes home.
    expect(area(page, "blades")).to_have_count(0)
    area(page, "scripts").click()
    expect(page).to_have_url(re.compile(r"/scripts\?"), timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "scripts")
    expect(page.locator(".wb-status .side-toggle", has_text="Blades")).to_be_visible()
    area(page, "settings").click()
    expect(page).to_have_url(re.compile(r"open=settings"))
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    page.go_back()
    expect(current(page)).to_have_attribute("data-area", "scripts")
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd", timeout=20000)
    # Back walks the same tab back through the pages.
    page.go_back()
    expect(page).to_have_url(re.compile(r"/scripts"), timeout=20000)
    assert len(page.context.pages) == pages

    # A new window only on request: Ctrl+click, a middle click, or the right-click's menu, on every area.
    with page.context.expect_page() as clicked:
        area(page, "scripts").click(modifiers=["Control"])
    other = clicked.value
    expect(other).to_have_url(re.compile(r"/scripts\?kind=script"), timeout=20000)
    other.close()
    area(page, "analyze").click(button="right")
    with page.context.expect_page() as popped:
        page.get_by_role("menuitem", name="Open in a new window").click()
    sandbox = popped.value
    expect(sandbox.locator(".workspace")).to_have_attribute("data-view", "agent", timeout=20000)
    sandbox.close()
    with page.context.expect_page() as middle:
        area(page, "grids").click(button="middle")
    middle.value.close()
    expect(page).to_have_url(re.compile(r"/scripts"))  # this tab stayed where it was
    page.context.close()


def test_the_steps_window_is_only_the_transformations(browser: Browser, orchard: str) -> None:
    """The owner (2026-11-16): transformations "should open in a pop out window in their own window not as a
    duplicate of the entire page": no rail, no tabs, no ribbon; the grid page's row says Transformations."""
    page = home_page(browser, orchard)
    caption = page.locator(".ribbon-caption strong", has_text="Transformations")
    row = page.locator(".ribbon .ribbon-group", has=caption)
    expect(row).to_be_visible()
    captions = page.locator(".ribbon .ribbon-caption strong")
    expect(captions).to_have_text(["Table", "Transformations", "Column"])
    expect(page.locator(".titlebar")).to_be_hidden()
    with page.context.expect_page() as opened:
        row.get_by_role("button", name="View steps").click()
    steps = opened.value
    expect(steps.locator(".steps-panel .step.source")).to_be_visible(timeout=20000)
    expect(steps.locator(".steps-panel h2")).to_have_text("Transformations")
    for gone in (".nav-rail", ".tabbar", ".ribbon", ".app-row"):
        expect(steps.locator(gone)).to_have_count(0)
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
    expect(page.locator(".area-page[data-page='settings'] fieldset", has_text="Panels")).to_have_count(0)
    page.go_back()
    expect(rail(page)).to_be_visible()
    page.context.close()


def test_a_sql_step_is_written_in_a_window_of_its_own(browser: Browser, orchard: str) -> None:
    """The owner (2026-11-16): Add a SQL step and editing one open "a resizable window so the user can
    type large sql transformations"; the steps window has a Close and no Copy transformations button."""
    page = home_page(browser, orchard)
    with page.context.expect_page() as opened:
        page.get_by_role("button", name="View steps").click()
    steps = opened.value
    expect(steps.locator(".steps-panel .step.source")).to_be_visible(timeout=20000)
    expect(steps.get_by_role("button", name="Copy transformations as SQL or Python")).to_have_count(0)
    expect(steps.locator(".window-top").get_by_role("button", name="Close")).to_be_visible()
    with steps.context.expect_page() as sql_opened:
        steps.get_by_role("button", name="Add a SQL step").click()
    sql = sql_opened.value
    box = sql.get_by_role("textbox", name="SQL")
    expect(box).to_be_visible(timeout=20000)
    for gone in (".nav-rail", ".tabbar", ".ribbon"):
        expect(sql.locator(gone)).to_have_count(0)
    # The box fills the window, and grows with it.
    small = box.bounding_box()
    assert small and small["height"] > sql.viewport_size["height"] * 0.5  # type: ignore[index]
    sql.set_viewport_size({"width": 1400, "height": 1000})
    sql.wait_for_timeout(200)
    big = box.bounding_box()
    assert big and big["height"] > small["height"] + 200
    box.fill("SELECT *\nFROM grid\nWHERE true")
    with sql.expect_event("close"):
        sql.get_by_role("button", name="Add step").click()
    step = steps.locator(".step-list li").nth(1)
    expect(step).to_contain_text("SQL", timeout=20000)
    # Its pencil opens the same window, holding its SQL.
    with steps.context.expect_page() as edit_opened:
        step.get_by_role("button", name="Edit step 1").click()
    edit = edit_opened.value
    expect(edit.get_by_role("textbox", name="SQL")).to_have_value(
        "SELECT *\nFROM grid\nWHERE true", timeout=20000
    )
    edit.close()
    page.context.close()
