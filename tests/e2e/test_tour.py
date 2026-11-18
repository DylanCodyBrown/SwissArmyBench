# ruff: noqa: F811
"""The tour: offered on the Projects page only (the rail's mark, 2026-11-18; the Start view before it; the
owner, 2026-11-16: "new here take a tour should be on the project page and no where else"); guided since
2026-11-18 ("the tutorial needs to move and highlight the
item it is talking about, so the tutorial might need to stage a couple tables in the grid then remove them.
it will need to navigate to pages as it goes"): each card goes to its place and lights up the real control,
two made-up tables are staged and closed again, and the game still ends it."""

from __future__ import annotations

import re
import time
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401


def datasets(server: dict[str, Any]) -> set[str]:
    return {d["name"] for d in call(server, "GET", "/datasets")["datasets"]}


def to_word(page: Page, tour: Locator, word: str) -> None:
    """Next (the Right key) until the card says `word`."""
    for _ in range(40):
        if tour.locator(".tour-word").inner_text() == word:
            return
        page.keyboard.press("ArrowRight")
    raise AssertionError(f"no card {word!r}")


def lights_up(tour: Locator, target: Locator) -> None:
    """The spotlight sits on `target` (6 pixels round it), once it has moved there."""
    spot = tour.locator(".tour-spot")
    expect(spot).to_be_visible(timeout=6000)
    expect(tour.locator(".tour-missing")).to_be_hidden()
    deadline = time.monotonic() + 6
    while True:
        box, want = spot.bounding_box(), target.bounding_box()
        assert want
        expected = (want["x"] - 6, want["y"] - 6, want["width"] + 12, want["height"] + 12)
        if box and all(
            abs(a - b) < 2
            for a, b in zip((box["x"], box["y"], box["width"], box["height"]), expected, strict=True)
        ):
            return
        assert time.monotonic() < deadline, (box, want)
        time.sleep(0.1)


def test_the_tour_goes_to_each_place_with_its_own_tables_and_ends_with_a_game(
    browser: Browser, server: dict[str, Any]
) -> None:
    # The user's own table, with the name the tour would like: the tour's takes another, and this one stays.
    frame = pd.DataFrame({"order_id": [1, 2, 3], "item": ["Anvil", "Bolt", "Cog"]})  # made up
    url = push_client.push(frame, name="tour_orders", new_grid=True)
    page = open_grid(browser, url, width=1440)
    try:
        # Not in the Application row: Home (the Projects page, the rail's mark) has it.
        expect(page.locator(".app-row .tour-btn")).to_have_count(0)
        page.locator('.nav-rail [data-area="projects"]').click()
        row = page.locator('.area-page[data-page="projects"]')
        expect(row).to_be_visible()
        bubble = row.locator(".tour-bubble")
        expect(bubble).to_contain_text("New here?")  # a first visit
        row.get_by_role("button", name="Tour", exact=True).click()
        tour = page.get_by_role("dialog", name="Tour")
        expect(tour).to_contain_text("Hi!")
        expect(bubble).to_have_count(0)  # seen: gone for good
        expect(tour).to_have_class("tour tour-dim")  # the welcome card has nothing to point at
        # Projects: this page, its mark on the rail lit up.
        to_word(page, tour, "Projects")
        expect(row).to_be_visible()
        lights_up(tour, page.locator('.nav-rail [data-area="projects"]'))

        # Its two made-up tables arrive as tabs, beside the user's.
        tabs = page.locator(".tabs-row .tab-item")
        expect(tabs.filter(has_text="tour_customers")).to_have_count(1)
        expect(tabs.filter(has_text="tour_orders_2")).to_have_count(1)
        assert {"tour_orders", "tour_orders_2", "tour_customers"} <= datasets(server)

        # A rail page: it goes there and lights up the page's own button.
        to_word(page, tour, "Connections")
        expect(page.locator('.area-page[data-page="connections"]')).to_be_visible()
        lights_up(
            tour,
            page.locator('.area-page[data-page="connections"]').get_by_role("button", name="Add connection"),
        )
        # The grids: its orders table in front, its tab lit up.
        to_word(page, tour, "Grid")
        expect(page.locator('.area-page[data-page="connections"]')).to_be_hidden()
        orders_tab = tabs.filter(has_text="tour_orders_2")
        expect(orders_tab).to_have_class(re.compile(r"\bactive\b"))
        lights_up(tour, orders_tab)
        to_word(page, tour, "Steps")
        expect(page.locator(".steps-strip")).to_contain_text("1 step")  # the tour's sort, on its own table
        lights_up(tour, page.locator(".steps-strip"))
        # Compare: the tour's two tables side by side.
        to_word(page, tour, "Compare")
        expect(page.locator(".panes")).to_have_attribute("data-split", "on")
        lights_up(tour, page.locator('.ribbon-group[aria-label^="Compare tools"]'))
        # Back: the previous card's place again (one table, no compare).
        page.keyboard.press("ArrowLeft")
        expect(tour.locator(".tour-word")).to_have_text("Analyze")
        expect(page.locator(".panes")).to_have_attribute("data-split", "off")
        lights_up(tour, page.locator('.ribbon [aria-label="Analyze"]'))
        # The ERD, and a code area (another window): its rail icon, with the page left as it was.
        to_word(page, tour, "ERD")
        expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
        to_word(page, tour, "Notebooks")
        lights_up(tour, page.locator('.nav-rail [data-area="notebooks"]'))
        expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
        # Settings, scrolled to its Claude section.
        to_word(page, tour, "Agent")
        lights_up(tour, page.locator(".claude-fieldset"))

        # Escape mid-tour: back to the Projects page, the tour's tables closed and only those.
        page.keyboard.press("Escape")
        expect(tour).to_have_count(0)
        expect(row).to_be_visible()
        expect(page.locator('.area-page[data-page="settings"]:visible')).to_have_count(0)
        expect(tabs.filter(has_text="tour_")).to_have_count(1)
        expect(tabs.filter(has_text="tour_orders")).to_have_text("tour_orders")
        deadline = time.monotonic() + 5
        while datasets(server) & {"tour_orders_2", "tour_customers"} and time.monotonic() < deadline:
            time.sleep(0.1)
        assert "tour_orders" in datasets(server)
        assert not datasets(server) & {"tour_orders_2", "tour_customers"}

        # Again, to the end: the game, then the Projects page with the tables gone.
        page.reload()
        expect(row.locator(".tour-btn")).to_be_visible()
        expect(row.locator(".tour-bubble")).to_have_count(0)  # remembered in this browser
        row.get_by_role("button", name="Tour", exact=True).click()
        expect(tabs.filter(has_text="tour_customers")).to_have_count(1)
        to_word(page, tour, "Agent")
        tour.get_by_role("button", name="Play").click()
        for round_number in range(1, 6):
            expect(tour.locator(".tour-kicker")).to_have_text(f"Round {round_number} of 5")
            tour.locator(".tour-choice").first.click()
            expect(tour.locator(".tour-choice.right")).to_have_count(1)
        expect(tour.locator(".tour-word")).to_contain_text("of 5.", timeout=5000)
        expect(tour.locator(".tour-code")).to_contain_text("sab.push(df)")
        tour.get_by_role("button", name="Start").click()
        expect(tour).to_have_count(0)
        expect(row).to_be_visible()
        expect(tabs.filter(has_text="tour_")).to_have_count(1)
        deadline = time.monotonic() + 5
        while datasets(server) & {"tour_orders_2", "tour_customers"} and time.monotonic() < deadline:
            time.sleep(0.1)
        assert datasets(server) & {"tour_orders", "tour_orders_2", "tour_customers"} == {"tour_orders"}
    finally:
        page.close()
