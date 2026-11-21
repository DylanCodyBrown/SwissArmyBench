# ruff: noqa: F811
"""Every rail icon lands on a page (the owner, 2026-11-16: "the same for others clicking the rail should
land on a page not open a form"; "every time I click the rail it pops out a box from the icon to create
something get rid of that"), in a real browser: no dialog and no menu from any area; the Workbench's
landing page for a kind (its documents as cards; New and Open… in the top bar); the Connections
page's cards and a card's detail (a reference opens its cell in the Workbench); Settings as a page;
Back and Forward across them; the old dialog addresses still land on the pages. Made-up data only.

With SWISSARMYBENCH_RAILPAGES_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_RAILPAGES_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def plums(server: dict[str, Any]) -> Iterator[str]:
    url = push_client.push(
        pd.DataFrame({"orchard": ["North", "South", "East"], "plums": [14, 9, 31]}),
        name="rail_plums",
        new_grid=True,
    )
    yield url
    try:
        call(server, "DELETE", f"/grids/{grid_of(url)}")
    except Exception:  # noqa: S110 (closed by the test)
        pass


@pytest.fixture
def orchard_db(server: dict[str, Any], tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A made-up sqlite connection, a notebook whose SQL cell and Python cell use it, and a script."""
    database = tmp_path / "orchard.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE harvest (orchard TEXT, plums INTEGER)")
        made_up.executemany("INSERT INTO harvest VALUES (?, ?)", [("North", 14), ("South", 9)])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    name = "Orchard records"
    call(
        server,
        "POST",
        "/connections",
        {"name": name, "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code},
    )
    book = tmp_path / "harvest notes.ipynb"
    cells = [
        {"kind": "markdown", "source": "# Harvest"},
        {"kind": "sql", "source": "SELECT * FROM harvest", "connection": name},
        {"kind": "code", "source": f"import swissarmybench as sab\ntotals = sab.sql({name!r}, 'SELECT 1')"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(book), "cells": cells})
    script = tmp_path / "harvest totals.py"
    call(server, "POST", "/workbench/save", {"path": str(script), "text": "x = 1\n"})
    for path in (script, book):
        call(server, "POST", "/workbench/open", {"path": str(path)})  # recent files: the landing's cards
    yield {"name": name, "book": book, "script": script}
    call(server, "DELETE", f"/blades/{name.replace(' ', '%20')}")


def rail(page: Page) -> Any:
    return page.get_by_role("navigation", name="Areas")


def area(page: Page, name: str) -> Any:
    return rail(page).locator(f"[data-area='{name}']")


def current(page: Page) -> Any:
    return rail(page).locator("[aria-current='page']")


def no_box(page: Page) -> None:
    """A page, never a dialog or a menu beside the icon."""
    expect(page.locator("dialog[open]")).to_have_count(0)
    expect(page.get_by_role("menu")).to_have_count(0)


def home(browser: Browser, url: str) -> Page:
    page = browser.new_context(
        viewport={"width": 1300, "height": 820}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    page.on("dialog", lambda d: d.accept())
    return page


def test_each_rail_icon_lands_on_a_page_and_back_and_forward_walk_them(
    browser: Browser, server: dict[str, Any], plums: str, orchard_db: dict[str, Any]
) -> None:
    page = home(browser, plums)
    base = f"http://127.0.0.1:{server['port']}"
    area(page, "analyze").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "agent")
    no_box(page)
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    no_box(page)
    # Connections: a page over the grids, a card each.
    area(page, "connections").click()
    connections = page.locator(".area-page[data-page='connections']")
    expect(connections).to_be_visible()
    expect(page).to_have_url(re.compile(r"open=connections"))
    expect(current(page)).to_have_attribute("data-area", "connections")
    no_box(page)
    # Settings: a page too; its sections, no Close.
    area(page, "settings").click()
    settings = page.locator(".area-page[data-page='settings']")
    expect(settings).to_be_visible()
    expect(connections).to_have_count(0)
    expect(settings.locator("fieldset", has_text="Theme")).to_be_visible()
    expect(settings.get_by_role("button", name="Close")).to_have_count(0)
    no_box(page)
    # Back: Connections again; Back: the ERD, the page gone; Forward: Connections.
    page.go_back()
    expect(connections).to_be_visible()
    expect(current(page)).to_have_attribute("data-area", "connections")
    page.go_back()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    page.go_forward()
    expect(connections).to_be_visible()
    # The grids, from a page: the page makes way.
    area(page, "grids").click()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grid")
    # Notebooks: this tab goes to the Workbench's page of notebooks, never a menu beside the icon.
    area(page, "notebooks").click()
    expect(page).to_have_url(f"{base}/notebooks?kind=notebook&view=list", timeout=20000)
    landing = page.locator(".wb-landing")
    expect(landing).to_be_visible(timeout=20000)
    no_box(page)
    # The page's creator (no top bar, 2026-11-21); its explorer says no project is open.
    expect(landing.get_by_role("button", name="New notebook")).to_be_visible()
    expect(page.locator(".wb-top")).to_be_hidden()
    expect(page.locator(".wb-codex.page-notebooks")).to_contain_text("No project is open.")
    shot(page, "notebooks-landing")
    # Scripts: a page of its own, another window; its creator makes a script there.
    with page.context.expect_page() as opened:
        area(page, "scripts").click()
    scripts = opened.value
    expect(scripts).to_have_url(re.compile(r"/scripts\?kind=script&view=list"), timeout=20000)
    scripts_landing = scripts.locator(".wb-landing")
    expect(scripts_landing.get_by_role("button", name="New script")).to_be_visible(timeout=20000)
    no_box(scripts)
    scripts_landing.get_by_role("button", name="New script").click()
    expect(scripts.locator(".wb-tab", has_text="Untitled script")).to_be_visible(timeout=20000)
    scripts.close()
    # Canvas: its own page (the Streamlit extension's).
    area(page, "canvas").click()
    expect(page).to_have_url(re.compile(r"/streamlit/canvas"), timeout=20000)
    page.go_back()
    expect(landing).to_be_visible(timeout=20000)
    # Settings and Connections are pages in the Workbench too.
    area(page, "settings").click()
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible()
    no_box(page)
    area(page, "notebooks").click()
    expect(page.locator(".area-page")).to_have_count(0)
    expect(landing).to_be_visible()
    # Blades: the Scripts page's Blades pane (2026-11-21), the Scripts window brought forward.
    with page.context.expect_page() as opened:
        area(page, "blades").click()
    scripts = opened.value
    expect(scripts).to_have_url(re.compile(r"/scripts\?.*pane=blades"), timeout=20000)
    expect(scripts.locator(".wb-codex-lower.lower-blades")).to_be_visible(timeout=20000)
    no_box(scripts)
    area(scripts, "connections").click()
    expect(scripts.locator(".area-page[data-page='connections']")).to_be_visible()
    area(scripts, "blades").click()
    expect(scripts.locator(".area-page")).to_have_count(0)
    page.context.close()


def test_the_connections_page_cards_a_cards_detail_and_a_reference_opening_its_cell(
    browser: Browser, server: dict[str, Any], plums: str, orchard_db: dict[str, Any]
) -> None:
    name = orchard_db["name"]
    # A call this session: its table opened as a grid through the app.
    call(server, "POST", f"/connections/{name.replace(' ', '%20')}/open", {"table": "harvest"})
    page = home(browser, plums)
    area(page, "connections").click()
    card = page.locator(f".connection-card[data-connection='{name}']")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Works")
    expect(card.locator(".connection-card-calls")).to_contain_text(re.compile(r"\d+ calls?"))
    expect(page.locator(".area-page-actions").get_by_role("button", name="Add connection")).to_be_visible()
    shot(page, "connections-cards")
    card.click()
    expect(page).to_have_url(re.compile(r"at=detail&name=Orchard"))
    detail = page.locator(".area-page[data-page='connections']")
    expect(detail.locator(".area-page-title")).to_contain_text(name)
    used = detail.locator(".connection-used")
    mine = used.locator(f".connection-ref[data-kind='notebook'][title='{orchard_db['book']}']")
    expect(mine).to_have_count(2)
    expect(used.locator(".connection-ref[data-kind='grid']")).to_have_count(1)
    expect(mine.filter(has_text="%%sql")).to_contain_text("@cell2")
    config = detail.locator(".connection-config")
    expect(config).to_contain_text("Type")
    calls = detail.locator(".connection-calls")
    expect(calls).to_contain_text("Table reads")
    for label in ("Edit", "Test", "Remove"):
        expect(detail.locator(".connection-detail-tools").get_by_role("button", name=label)).to_be_visible()
    no_box(page)
    shot(page, "connection-detail")
    if SHOTS:
        page.emulate_media(color_scheme="dark")
        shot(page, "connection-detail-dark")
        page.locator(".nav-rail [data-area='connections']").click()
        expect(card).to_be_visible()
        shot(page, "connections-cards-dark")
        page.go_back()
        page.emulate_media(color_scheme="light")
    # Back to the cards, Forward to the detail; a reload keeps it.
    page.go_back()
    expect(card).to_be_visible()
    page.go_forward()
    expect(used).to_be_visible()
    page.reload()
    expect(mine).to_have_count(2, timeout=20000)
    # A reference opens its cell in the Workbench window (opened for it: there is none yet).
    with page.context.expect_page() as opened:
        mine.filter(has_text="%%sql").click()
    workbench = opened.value
    expect(workbench.locator(".wb-tab", has_text="harvest notes.ipynb")).to_be_visible(timeout=20000)
    expect(
        workbench.locator(".wb-cell.selected, .wb-cell.wb-selected, .wb-cell[aria-selected='true']").first
    ).to_be_visible(timeout=10000)
    # Edit from the detail: the form, and Back to the detail.
    page.bring_to_front()
    page.locator(".connection-detail-tools").get_by_role("button", name="Edit").click()
    expect(page).to_have_url(re.compile(r"at=edit"))
    page.go_back()
    expect(page.locator(".connection-used")).to_be_visible()
    page.context.close()


def test_the_old_dialog_addresses_land_on_the_pages(
    browser: Browser, server: dict[str, Any], plums: str
) -> None:
    page = home(browser, plums)
    base = f"http://127.0.0.1:{server['port']}"
    page.goto(f"{base}/workspace?open=settings")
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible(timeout=20000)
    no_box(page)
    page.goto(f"{base}/workspace?open=connections&at=types")
    expect(page.locator(".area-page[data-page='connections'] .connection-type").first).to_be_visible(
        timeout=20000
    )
    no_box(page)
    shot(page, "settings-page")
    page.goto(f"{base}/catalog?open=settings")
    expect(page.locator(".area-page[data-page='settings']")).to_be_visible(timeout=20000)
    expect(current(page)).to_have_attribute("data-area", "settings")
    page.context.close()
