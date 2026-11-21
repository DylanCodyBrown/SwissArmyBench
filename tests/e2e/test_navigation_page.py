# ruff: noqa: F811
"""Getting around (the owner, 2026-11-16: "there is no navigation in the app to get back to the home page
or go back anywhere. No back buttons."), in a real browser: the mark goes home (and brings the home window
forward from the Workbench), the browser's Back and Forward move between views and stay in the app, a
reload keeps the view, the Back buttons say where they go, the breadcrumbs work, and the titles name the
place. Made-up data only."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401


@pytest.fixture
def two_tables(server: dict[str, Any]) -> Iterator[tuple[str, str]]:
    first = push_client.push(
        pd.DataFrame({"city": ["Springfield", "Shelbyville"], "visits": [3, 5]}),
        name="nav_visits",
        new_grid=True,
    )
    second = push_client.push(
        pd.DataFrame({"fruit": ["Apple", "Pear", "Plum"], "crates": [4, 2, 9]}),
        name="nav_crates",
        new_grid=True,
    )
    yield first, second
    for url in (first, second):
        try:
            call(server, "DELETE", f"/grids/{grid_of(url)}")
        except Exception:  # noqa: S110 (closed by the test)
            pass


def home_page(browser: Browser, url: str) -> Page:
    page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def view_of(page: Page) -> str | None:
    return page.locator(".workspace").get_attribute("data-view")


def test_the_home_pages_tabs_are_in_the_address_and_back_moves_between_them(
    browser: Browser, server: dict[str, Any], two_tables: tuple[str, str]
) -> None:
    first, second = two_tables
    page = home_page(browser, first)
    base = f"http://127.0.0.1:{server['port']}"
    # The mark is the rail's first item (the owner, 2026-11-18), no longer in the tab bar.
    mark = page.locator(".nav-rail-item").first
    expect(mark).to_have_attribute("data-area", "projects")
    expect(mark.locator('[data-icon="home"]')).to_be_visible()  # a plain icon (2026-11-21)
    expect(page.locator(".tabbar .app-mark")).to_have_count(0)
    expect(page).to_have_url(f"{base}/g/{grid_of(first)}")
    expect(page).to_have_title("nav_visits")

    page.locator(".nav-rail [data-area='analyze']").click()
    expect(page).to_have_url(f"{base}/workspace?view=analyze")
    expect(page).to_have_title("Analyze")
    page.locator(".nav-rail [data-area='erd']").click()
    expect(page).to_have_url(f"{base}/workspace?view=erd")
    expect(page).to_have_title("ERD")
    page.locator(f".tab-item[data-grid='{grid_of(second)}']").click()
    expect(page).to_have_url(f"{base}/g/{grid_of(second)}")
    expect(page).to_have_title("nav_crates")

    # The browser's Back and Forward: one view at a time, never out of the app.
    page.go_back()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    expect(page).to_have_title("ERD")
    page.go_back()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    page.go_back()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grid")
    expect(page.locator(f".tab-item.active[data-grid='{grid_of(first)}']")).to_be_visible()
    page.go_forward()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    page.go_forward()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")

    # A reload keeps the view (the cookie keeps the session; the token is never in the address).
    page.reload()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd", timeout=20000)
    expect(page).to_have_title("ERD")
    assert "token" not in page.url

    # The mark goes home: the Projects page (2026-11-18), the grids under it; Back returns; Alt+Home too.
    projects = page.locator('.area-page[data-page="projects"]')
    mark.click()
    expect(projects).to_be_visible()
    expect(projects.locator(".explorer-head")).to_be_visible()
    # The grid page is not shown: Projects covers everything right of the rail.
    assert (
        page.evaluate("document.elementFromPoint(700, 430).closest('.area-page')?.dataset.page") == "projects"
    )
    expect(page).to_have_url(re.compile(r"/workspace\?view=erd&open=projects$"))
    expect(page).to_have_title("Home")
    expect(mark).to_have_attribute("aria-current", "page")
    page.go_back()
    expect(projects).to_have_count(0)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    page.locator(".nav-rail [data-area='analyze']").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    page.keyboard.press("Alt+Home")
    expect(projects).to_be_visible()
    page.locator(".nav-rail [data-area='grids']").click()
    expect(projects).to_have_count(0)
    # The old Start view's address lands on Projects, in its place in the history.
    page.goto(f"{base}/workspace?view=start")
    expect(projects).to_be_visible(timeout=20000)
    expect(page).to_have_url(re.compile(r"\?open=projects$"))  # over the table in front
    page.locator(".nav-rail [data-area='grids']").click()
    # A reload on a table keeps that table in front.
    page.locator(f".tab-item[data-grid='{grid_of(second)}']").click()
    expect(page).to_have_url(re.compile(grid_of(second)))
    page.reload()
    expect(page.locator(f".tab-item.active[data-grid='{grid_of(second)}']")).to_be_visible(timeout=20000)
    page.context.close()


def test_connections_forms_are_in_the_address_with_back_buttons_and_a_trail(
    browser: Browser, server: dict[str, Any], two_tables: tuple[str, str]
) -> None:
    page = home_page(browser, two_tables[0])
    # The Connections page (2026-11-16: a page over the grids, not a dialog), at the dialog's addresses.
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    expect(page).to_have_url(re.compile(r"open=connections"))
    expect(page).to_have_title("Connections")
    dialog.locator(".area-page-actions").get_by_role("button", name="Add connection").click()
    expect(page).to_have_url(re.compile(r"open=connections&at=types"))
    expect(page).to_have_title("Connections › Add connection")
    expect(dialog.get_by_role("button", name="Back to Connections")).to_be_visible()
    page.locator(".connection-type", has_text="PostgreSQL").click()
    expect(page).to_have_url(re.compile(r"at=form&type="))
    trail = dialog.get_by_role("navigation", name="Breadcrumb")
    expect(trail.locator("li")).to_have_text(["Connections", "Add connection", "PostgreSQL"])
    expect(page).to_have_title("Connections › Add connection › PostgreSQL")
    # Without its driver in this Python the form asks for it at once (missingPackages.ts): not this test's.
    if dialog.locator(".install-note").count():
        page.locator("dialog.missing-packages").get_by_role("button", name="Not now").click()
    back = dialog.get_by_role("button", name="Back to Add connection")
    expect(back).to_contain_text("Add connection")

    # A reload comes back to the same form.
    page.reload()
    expect(dialog.get_by_role("heading", name="New PostgreSQL connection")).to_be_visible(timeout=20000)
    expect(dialog.get_by_role("navigation", name="Breadcrumb")).to_be_visible()

    # The visible Back goes to the place it names; the browser's Back walks out one view at a time.
    dialog.get_by_role("button", name="Back to Add connection").click()
    expect(dialog.locator(".connection-type").first).to_be_visible()
    expect(page).to_have_url(re.compile(r"at=types"))
    page.go_forward()
    expect(dialog.get_by_role("heading", name="New PostgreSQL connection")).to_be_visible()
    # A crumb is a link to its place.
    dialog.get_by_role("navigation", name="Breadcrumb").get_by_role("link", name="Connections").click()
    expect(dialog.locator(".area-page-actions").get_by_role("button", name="Add connection")).to_be_visible()
    expect(page).to_have_url(re.compile(r"open=connections$"))
    page.go_back()
    expect(dialog.get_by_role("heading", name="New PostgreSQL connection")).to_be_visible()
    page.go_back()
    page.go_back()
    expect(
        dialog.locator(".area-page-actions").get_by_role("button", name="Add connection")
    ).to_be_visible()  # the list
    page.go_back()
    expect(dialog).to_have_count(0)  # Back past the list takes the page away, and stays on the grids
    expect(page).to_have_url(re.compile(r"/g/"))
    page.go_forward()
    expect(dialog.locator(".area-page-actions").get_by_role("button", name="Add connection")).to_be_visible()
    # Grids on the rail: the page makes way, the table in front again.
    page.locator(".nav-rail [data-area='grids']").click()
    expect(dialog).to_have_count(0)
    expect(page).not_to_have_url(re.compile(r"open="))
    expect(page).to_have_title("nav_visits")

    # Settings is in the address too; Back closes it.
    page.locator(".nav-rail [data-area='settings']").click()
    expect(page).to_have_url(re.compile(r"open=settings"))
    expect(page).to_have_title("Settings")
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    page.go_back()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(page).to_have_title("nav_visits")
    page.context.close()


def test_back_closes_a_plain_dialog_and_never_leaves_the_page_under_it(
    browser: Browser, server: dict[str, Any], two_tables: tuple[str, str]
) -> None:
    first, second = two_tables
    page = home_page(browser, first)
    page.locator(f".tab-item[data-grid='{grid_of(second)}']").click()
    expect(page).to_have_url(re.compile(grid_of(second)))
    page.locator(".tabbar").get_by_role("button", name="Tables").click()
    tables = page.locator("dialog")
    expect(tables).to_be_visible()
    page.go_back()  # the dialog closes; the table in front stays
    expect(tables).to_have_count(0)
    expect(page.locator(f".tab-item.active[data-grid='{grid_of(second)}']")).to_be_visible()
    # Closed by its own Close: its entry goes too, so the next Back is the tab before.
    page.locator(".tabbar").get_by_role("button", name="Tables").click()
    expect(tables).to_be_visible()
    tables.get_by_role("button", name="Close").first.click()
    expect(tables).to_have_count(0)
    # Its entry is taken away (the page's own history.back, a moment later).
    page.wait_for_function("history.state && history.state.sab && history.state.sab.dialogs.length === 0")
    page.go_back()
    expect(page.locator(f".tab-item.active[data-grid='{grid_of(first)}']")).to_be_visible()
    page.context.close()


def test_the_old_blades_pages_addresses_land_on_the_scripts_pages_blades(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The blades page went (2026-11-21): /catalog is the Scripts page's Blades pane, ?blade=<name> that
    blade's tab there (the word leaves the address once shown), ?blade= New blade; a blade that is not there
    is said in its tab."""
    base = f"http://127.0.0.1:{server['port']}"
    call(server, "POST", "/blades", {"name": "Made-up loaves", "kind": "other", "code": "loaves = 12\n"})
    page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
    try:
        page.goto(f"{base}/catalog#token={server['token']}")
        expect(page).to_have_url(re.compile(r"/scripts\?pane=blades"), timeout=20000)
        expect(page.locator(".wb-codex-lower.lower-blades .blade-list")).to_be_visible(timeout=20000)
        expect(page.locator(".nav-rail-item").first).to_have_attribute("data-area", "projects")
        page.goto(f"{base}/catalog?blade=Made-up%20loaves")
        tab = page.locator(".wb-tab[data-kind='blade']", has_text="Made-up loaves")
        expect(tab).to_be_visible(timeout=20000)
        expect(page).not_to_have_url(re.compile("blade=Made-up"))
        page.goto(f"{base}/catalog?blade=")
        expect(page.get_by_role("dialog", name="New blade")).to_be_visible(timeout=20000)
        page.keyboard.press("Escape")
        page.goto(f"{base}/scripts?pane=blades&blade=Gone")
        expect(page.locator(".code-ide-missing, .wb-doc .error-note").first).to_contain_text(
            "Gone", timeout=20000
        )
    finally:
        call(server, "DELETE", "/blades/Made-up%20loaves")
        page.context.close()


def test_the_workbenchs_mark_brings_the_home_window_forward(
    browser: Browser, server: dict[str, Any], two_tables: tuple[str, str]
) -> None:
    page = home_page(browser, two_tables[0])
    page.evaluate("window.__still_here = 1")  # gone if the home page were opened again
    with page.context.expect_page() as opened:
        page.evaluate("window.open('/workbench', 'swissarmybench-workbench')")
    workbench = opened.value
    expect(workbench.locator(".wb-status, .wb-welcome").first).to_be_visible(timeout=20000)
    expect(workbench).to_have_title(re.compile(r"^Notebooks"))  # the Notebooks page (2026-11-21)
    # The mark: the rail's first item (2026-11-18), named Projects, Alt+Home its key; not in the top row.
    mark = workbench.locator(".nav-rail-item").first
    expect(mark).to_have_attribute("data-area", "projects")
    expect(mark).to_have_attribute("aria-keyshortcuts", "Alt+Home")
    expect(workbench.locator(".wb-top .app-mark")).to_have_count(0)
    # The rail's arrow keys reach it: Home from the stop the Tab key lands on.
    workbench.locator(".nav-rail-item[tabindex='0']").focus()
    workbench.keyboard.press("Home")
    expect(mark).to_be_focused()
    pages = len(page.context.pages)
    mark.click()
    # The home window it found by its name: the same page, not a second one, and not reloaded; showing
    # Projects.
    expect(page.locator('.area-page[data-page="projects"]')).to_be_visible()
    assert len(page.context.pages) == pages
    assert page.evaluate("window.__still_here") == 1
    assert page.evaluate("window.name") == "sab-home"
    page.locator(".nav-rail [data-area='grids']").click()
    expect(page.locator('.area-page[data-page="projects"]')).to_have_count(0)
    # The agent's nav.home does the same, through workbench_window.
    answer = call(server, "POST", "/workbench/window", {"command": "nav.home", "args": {}}, agent=True)
    assert "result" in answer
    page.wait_for_timeout(300)
    assert len(page.context.pages) == pages
    assert "/notebooks" in workbench.url  # never the Workbench window sent away instead
    # With the home window closed, the mark opens it again (once the Workbench sees it closed: a window
    # still closing is found by its name and brought forward, and no new one opens).
    page.close()
    # (Until the browser has it closed, the window that opened this one still answers: wait for that.)
    workbench.wait_for_function("!window.opener || window.opener.closed")
    workbench.bring_to_front()
    with workbench.context.expect_page() as again:
        workbench.keyboard.press("Alt+Home")
    home = again.value
    expect(home.locator('.area-page[data-page="projects"]')).to_be_visible(timeout=20000)
    assert home.url.endswith("?open=projects")  # over the table in front, if one is open
    workbench.context.close()


def test_the_agent_moves_the_home_window(
    browser: Browser, server: dict[str, Any], two_tables: tuple[str, str]
) -> None:
    page = home_page(browser, two_tables[0])
    call(server, "POST", "/navigate", {"to": "erd"}, agent=True)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    expect(page).to_have_url(re.compile(r"view=erd"))
    call(server, "POST", "/navigate", {"to": "analyze"}, agent=True)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    expect(page).to_have_url(re.compile(r"view=analyze"))
    call(server, "POST", "/navigate", {"to": "add_connection"}, agent=True)
    expect(page.locator(".area-page .connection-type").first).to_be_visible()
    call(server, "POST", "/navigate", {"to": "back"}, agent=True)
    expect(page.locator(".area-page")).to_have_count(0)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    call(server, "POST", "/navigate", {"to": f"grid:{grid_of(two_tables[1])}"}, agent=True)
    expect(page.locator(f".tab-item.active[data-grid='{grid_of(two_tables[1])}']")).to_be_visible()
    call(server, "POST", "/navigate", {"to": "home"}, agent=True)
    projects = page.locator('.area-page[data-page="projects"]')
    expect(projects).to_be_visible()
    call(server, "POST", "/navigate", {"to": "grids"}, agent=True)
    expect(projects).to_have_count(0)
    # The Projects page by its name, and by the Start view's old one (2026-11-18).
    call(server, "POST", "/navigate", {"to": "projects"}, agent=True)
    expect(projects).to_be_visible()
    expect(page).to_have_url(re.compile(r"open=projects"))
    call(server, "POST", "/navigate", {"to": "back"}, agent=True)
    expect(projects).to_have_count(0)
    call(server, "POST", "/navigate", {"to": "start"}, agent=True)
    expect(projects).to_be_visible()
    page.context.close()
