"""The Blazor Extensions page: a card per extension with what it adds and its status in the classic words,
the Install button on an available one and Remove asked first on an installed one (neither clicked: a
change hands over to the update's helper)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_extension_cards(browser: Browser, server: dict[str, Any]) -> None:
    listed = call(server, "GET", "/extensions")["extensions"]
    page = open_page(browser, server, "extensions")
    for ext in listed:
        card = page.locator(f".extension-card[data-extension={ext['id']}]")
        expect(card).to_contain_text(ext["name"])
        if ext["status"] == "available":
            expect(card.locator("button:has-text('Install')")).to_be_visible()
    streamlit = page.locator(".extension-card[data-extension=streamlit]")
    expect(streamlit).to_contain_text("The Canvas")
    page.close()
