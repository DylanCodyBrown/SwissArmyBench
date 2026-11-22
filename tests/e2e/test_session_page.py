"""The Session page and Follow the agent (the owner, 2026-11-16: "when the agent is driving the app and adding
things, I want to see objects that were created in a log make that a new page called Session on the rail
... lets make it so the AI agent can activate things on the page, so when it working on a diagram I can
what it in realtime"), in a real browser, the agent's calls made as the agent (X-Actor: agent).

- Follow on: a relationship the agent adds brings the ERD to the front, its line highlighted; a card it
  adds brings Analyze, the card scrolled to and pulsed.
- Follow off: nothing moves; the rail's Session icon counts them; the Session page lists both, and each
  link goes to its object.
- Typing in a box is never interrupted: the move waits until the user leaves it.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, grid_of, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SESSION_SHOTS")
ORDERS = "session_orders"
CUSTOMERS = "session_customers"


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def tables(server: dict[str, Any]) -> Iterator[str]:  # noqa: F811
    """Two made-up tables, Follow on, no relationships and no cards; all put back afterwards."""
    call(server, "PUT", "/session-log/follow", {"on": True})
    call(server, "POST", "/relationships", {"model": {}, "replace": True})
    customers = push_client.push(
        pd.DataFrame({"id": [1, 2, 3], "name": ["Ada", "Bo", "Cy"]}), name=CUSTOMERS, new_grid=True
    )
    orders = push_client.push(
        pd.DataFrame({"order_id": [10, 11, 12, 13], "customer_id": [1, 2, 2, 3], "amount": [5, 8, 13, 21]}),
        name=ORDERS,
        new_grid=True,
    )
    yield orders
    call(server, "PUT", "/session-log/follow", {"on": True})
    call(server, "POST", "/relationships", {"model": {}, "replace": True})
    for card in call(server, "GET", "/cards").get("cards", []):
        call(server, "DELETE", f"/cards/{card['id']}")
    for url in (orders, customers):
        try:
            call(server, "DELETE", f"/grids/{grid_of(url)}")
        except Exception:  # noqa: S110 (closed by the test)
            pass


def home(browser: Browser, url: str) -> Page:  # noqa: F811
    page = browser.new_context(
        viewport={"width": 1300, "height": 820}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def add_relationship(server: dict[str, Any]) -> None:  # noqa: F811
    model = {
        "relationships": [
            {"from": ORDERS, "from_columns": ["customer_id"], "to": CUSTOMERS, "to_columns": ["id"]}
        ]
    }
    call(server, "POST", "/relationships", {"model": model}, agent=True)


def add_card(server: dict[str, Any], title: str = "Made-up note") -> str:  # noqa: F811
    card = {"kind": "note", "title": title, "body": "Nothing real."}
    made = call(server, "POST", "/cards", card, agent=True)
    return str(made["card"])


def view(page: Page) -> Any:
    return page.locator(".workspace")


def test_following_the_agent_brings_the_erd_and_visualizations_to_the_front(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tables: str,
) -> None:
    page = home(browser, tables)
    expect(view(page)).to_have_attribute("data-view", "grid")
    add_relationship(server)
    # The ERD comes to the front, the new relationship's line highlighted as it is drawn.
    expect(view(page)).to_have_attribute("data-view", "erd", timeout=10000)
    expect(page).to_have_url(re.compile(r"view=erd"))
    line = page.locator("#erd-view path.relationshipLine[data-followed]")
    expect(line).to_have_count(1, timeout=10000)
    assert line.get_attribute("data-followed") == f"{ORDERS}.customer_id -> {CUSTOMERS}.id"
    expect(line).to_have_class(re.compile(r"follow-pulse"))
    shot(page, "follow-erd")
    # A card: Analyze, the card scrolled into view and pulsed.
    card = add_card(server)
    expect(view(page)).to_have_attribute("data-view", "agent", timeout=10000)
    shown = page.locator(f".card[data-card='{card}']")
    expect(shown).to_be_in_viewport(timeout=10000)
    expect(shown).to_have_class(re.compile(r"follow-pulse"))
    shot(page, "follow-card")
    # A step on a grid: the grid comes back to the front.
    grid = grid_of(tables)
    step = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 6}}
    call(server, "POST", f"/grids/{grid}/step-ops", {"op": "add", "step": step}, agent=True)
    expect(view(page)).to_have_attribute("data-view", "grid", timeout=10000)
    expect(page).to_have_url(re.compile(rf"/g/{grid}"))
    # Followed, so nothing is counted on the rail.
    expect(page.locator(".nav-rail-count")).to_be_hidden()


def test_with_follow_off_nothing_moves_and_the_session_page_lists_both_with_links(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tables: str,
) -> None:
    page = home(browser, tables)
    # The switch in Settings is the same one.
    page.locator(".nav-rail [data-area='settings']").click()
    switch = page.locator(".area-page[data-page='settings'] [data-follow]")
    expect(switch).to_be_checked()
    switch.click()
    expect(switch).not_to_be_checked()
    # The box changes at once; the server hears the switch a moment later.
    deadline = time.monotonic() + 5
    while call(server, "GET", "/session-log")["follow"] is not False and time.monotonic() < deadline:
        time.sleep(0.1)
    assert call(server, "GET", "/session-log")["follow"] is False
    page.go_back()
    expect(page.locator(".area-page")).to_have_count(0)
    before = page.url
    add_relationship(server)
    card = add_card(server)
    # Nothing moves; the rail counts the two.
    count = page.locator(".nav-rail [data-area='session'] .nav-rail-count")
    expect(count).to_have_text("2", timeout=10000)
    assert page.url == before
    expect(view(page)).to_have_attribute("data-view", "grid")
    shot(page, "rail-count")
    # The Session page: newest first, the agent's (the default filter), each a link.
    page.locator(".nav-rail [data-area='session']").click()
    expect(page).to_have_url(re.compile(r"open=session"))
    session = page.locator(".area-page[data-page='session']")
    expect(session).to_be_visible()
    expect(count).to_be_hidden()
    rows = session.locator(".session-entry")
    expect(rows.first).to_contain_text("Added a note card on Analyze")
    expect(session.locator(".session-entry[data-action='relationships']").first).to_contain_text(
        f"Added the relationship {ORDERS}.customer_id -> {CUSTOMERS}.id"
    )
    expect(session.locator(".session-entry.by-user")).to_have_count(0)
    expect(session.locator("[data-follow]")).not_to_be_checked()
    shot(page, "session-page")
    # Both: the user's own entries too (the tables pushed).
    session.locator("[data-who='both']").click()
    expect(session.locator(".session-entry.by-user").first).to_be_visible()
    session.locator("[data-who='agent']").click()
    # A link: the relationship's ERD, its line highlighted; then the card's Analyze.
    session.locator(".session-entry[data-action='relationships'] .session-link").first.click()
    expect(view(page)).to_have_attribute("data-view", "erd", timeout=10000)
    expect(page.locator(".area-page")).to_have_count(0)
    expect(page.locator("#erd-view path.relationshipLine[data-followed]")).to_have_count(1, timeout=10000)
    page.go_back()
    expect(session).to_be_visible()
    session.locator(".session-entry[data-action='add_card'] .session-link").first.click()
    expect(view(page)).to_have_attribute("data-view", "agent", timeout=10000)
    expect(page.locator(f".card[data-card='{card}']")).to_be_in_viewport(timeout=10000)


def test_changes_shows_only_what_changed_something_with_its_words(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tables: str,
) -> None:
    """The change log's events on the Session page (Plans/changes.plan.md): a step the agent adds says what
    it changed under its line; Changes hides the lines that changed nothing (a card added)."""
    call(server, "PUT", "/session-log/follow", {"on": False})
    page = home(browser, tables)
    grid = grid_of(tables)
    step = {"kind": "filter", "params": {"column": "amount", "op": ">", "value": 6}}
    call(server, "POST", f"/grids/{grid}/steps", {"steps": [step]}, agent=True)
    add_card(server)
    page.locator(".nav-rail [data-area='session']").click()
    session = page.locator(".area-page[data-page='session']")
    steps = session.locator(".session-entry[data-action='steps']").first
    expect(steps.locator(".session-change")).to_contain_text(f"{ORDERS}: steps added 1 filter")
    expect(session.locator(".session-entry[data-action='add_card']").first).to_be_visible()
    session.locator(".session-changes").click()
    expect(session.locator(".session-changes")).to_have_attribute("aria-pressed", "true")
    expect(session.locator(".session-entry[data-action='add_card']")).to_have_count(0)
    expect(session.locator(".session-entry[data-action='steps']").first).to_be_visible()
    shot(page, "session-changes")
    session.locator(".session-changes").click()  # put back: remembered in this browser
    expect(session.locator(".session-entry[data-action='add_card']").first).to_be_visible()
    last = call(server, "GET", f"/changes?action=last&object=table:{ORDERS}")["change"]
    assert last["who"] == "agent" and last["diff"]["steps"]["added"] == ["1 filter"]


def test_typing_in_a_box_is_never_interrupted(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tables: str,
) -> None:
    page = home(browser, tables)
    # A text box of the page's (the Rename of a table is a dialog; a plain box stands in for any).
    page.evaluate(
        "() => { const box = document.createElement('input'); box.id = 'typing'; box.type = 'text';"
        " document.querySelector('.tabbar').append(box); }"
    )
    box = page.locator("#typing")
    box.click()
    page.keyboard.type("half a sentence")
    card = add_card(server, "While typing")
    # The rail says it arrived; nothing moved, the box keeps the focus and its words.
    expect(page.locator(".nav-rail [data-area='session'] .nav-rail-count")).to_have_text("1", timeout=10000)
    page.wait_for_timeout(800)
    expect(view(page)).to_have_attribute("data-view", "grid")
    expect(box).to_be_focused()
    page.keyboard.type(" and the rest")
    expect(box).to_have_value("half a sentence and the rest")
    # The user leaves the box: the move that waited happens.
    box.blur()
    expect(view(page)).to_have_attribute("data-view", "agent", timeout=10000)
    expect(page.locator(f".card[data-card='{card}']")).to_be_in_viewport(timeout=10000)
