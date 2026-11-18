# ruff: noqa: F811
"""The rail's Extensions icon and its page (the owner, 2026-11-17): above Settings at the bottom; a card per
extension (Streamlit Preinstalled with Remove, Accounting and Power Apps Available); Install's progress with
the install itself stood in (a made-up "Ledger" extension, the server's answers routed in the browser); the
version mark's tooltip naming the installed extensions. Made-up data only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Page, Route, expect

from swissarmybench import __version__
from swissarmybench.client import push_client
from swissarmybench.renamed import env
from tests.e2e.test_ui import browser, server  # noqa: F401

SHOTS = env("SWISSARMYBENCH_SHOTS") or None
DEVELOPMENT = "This copy is a development checkout, not the installed app: uv pip install sab-ledger"


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / name))


def grid_page(browser: Browser) -> Page:
    url = push_client.push(
        pd.DataFrame({"region": ["North", "South"], "amount": [120, 340]}), name="sales", new_grid=True
    )
    page = browser.new_context(viewport={"width": 1400, "height": 820}, device_scale_factor=2).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def ext(ident: str, name: str, status: str, *adds: str) -> dict[str, Any]:
    """A card as GET /extensions lists it (made up)."""
    return {
        "id": ident,
        "name": name,
        "description": f"A made-up {name.lower()} extension.",
        "adds": list(adds),
        "status": status,
        "package": f"sab-{ident}",
        "version": __version__,
    }


def test_the_rail_has_extensions_above_settings_and_its_page_shows_each_kind(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = grid_page(browser)
    areas = page.locator(".nav-rail-item").evaluate_all("(items) => items.map((i) => i.dataset.area)")
    assert areas[-2:] == ["extensions", "settings"]
    page.locator(".nav-rail [data-area='extensions']").click()
    expect(page).to_have_url(re.compile("open=extensions"))
    cards = page.locator(".extension-card")
    expect(cards).to_have_count(5, timeout=10000)  # Streamlit, Accounting, Power Apps, GitHub Copilot, Git
    streamlit = page.locator(".extension-card[data-extension='streamlit']")
    expect(streamlit.locator(".extension-status")).to_have_text("Preinstalled")
    expect(streamlit.locator(".extension-version")).to_have_text(__version__)
    # Its own package, installed with every install: Remove is there (it asks first).
    expect(streamlit.get_by_role("button", name="Remove")).to_be_visible()
    for available in ("accounting", "powerapps", "copilot", "git"):
        card = page.locator(f".extension-card[data-extension='{available}']")
        expect(card.locator(".extension-status")).to_have_text("Available")
        expect(card.locator(".extension-version")).to_have_text(__version__)
        expect(card.get_by_role("button", name="Install")).to_be_visible()
    expect(page.locator(".nav-rail [data-area='extensions']")).to_have_attribute("aria-current", "page")
    # The version mark's tooltip lists the installed extensions.
    expect(page.locator(".statusbar .version-mark")).to_have_attribute(
        "title", f"Swiss Army Bench {__version__}\nExtensions: Streamlit"
    )
    shot(page, "extensions-page.png")
    page.context.close()


def test_install_shows_its_progress_through_the_restart(browser: Browser, server: dict[str, Any]) -> None:
    page = grid_page(browser)
    listing = {
        "extensions": [
            ext("streamlit", "Streamlit", "preinstalled", "The Apps area"),
            ext("ledger", "Ledger", "available", "Ledger pages"),
            ext("maps", "Maps", "installed"),
        ],
        "installable": True,
        "changing": None,
    }
    posted: list[Any] = []
    health = {"n": 0}

    def extensions(route: Route) -> None:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(listing))

    def install(route: Route) -> None:
        posted.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"changing": {"id": "ledger", "action": "install"}}),
        )

    def answer_health(route: Route) -> None:
        # Answering at first, then stopped (the helper at work), then a new server (its own token).
        health["n"] += 1
        status = 503 if health["n"] <= 3 else 401
        route.fulfill(status=status, content_type="application/json", body="{}")

    page.route("**/extensions", extensions)
    page.route("**/extensions/install", install)
    page.locator(".nav-rail [data-area='extensions']").click()
    ledger = page.locator(".extension-card[data-extension='ledger']")
    expect(ledger.locator(".extension-status")).to_have_text("Available", timeout=10000)
    expect(page.locator(".extension-card[data-extension='maps'] .extension-remove")).to_be_visible()
    shot(page, "extensions-available.png")
    page.route("**/health", answer_health)
    ledger.locator(".extension-install").click()
    expect(ledger.locator(".extension-progress")).to_be_visible()
    expect(page.locator(".extension-card[data-extension='maps'] .extension-remove")).to_be_disabled()
    assert posted == [{"id": "ledger", "confirmed": False}]
    expect(ledger.locator(".extension-stage")).to_contain_text("the app stopped", timeout=15000)
    shot(page, "extensions-installing.png")
    expect(ledger.locator(".extension-stage")).to_contain_text("Ledger is installed", timeout=20000)
    page.context.close()


def test_a_development_checkout_says_what_to_run(browser: Browser, server: dict[str, Any]) -> None:
    page = grid_page(browser)
    listing = {
        "extensions": [ext("ledger", "Ledger", "available")],
        "installable": False,
        "changing": None,
    }
    page.route(
        "**/extensions",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(listing)),
    )
    # The real server answers Install: ledger is not in its catalog, so this asks the real service's words.
    page.route(
        "**/extensions/install",
        lambda r: r.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps({"error": DEVELOPMENT}),
        ),
    )
    page.locator(".nav-rail [data-area='extensions']").click()
    page.locator(".extension-card[data-extension='ledger'] .extension-install").click()
    said = page.locator(".extension-card[data-extension='ledger'] .extension-said")
    expect(said).to_contain_text("development checkout")
    expect(page.locator(".extension-progress")).to_have_count(0)
    page.context.close()
