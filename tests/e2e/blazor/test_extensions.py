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


def test_a_new_folder_extension(browser: Browser, server: dict[str, Any]) -> None:
    """New extension… makes a made-up folder extension, loaded at once: its card says Installed (folder), its path,
    Remove and Show its folder; Remove takes it away (a folder's goes at once, no restart)."""
    page = open_page(browser, server, "extensions")
    page.click("button:has-text('New extension…')")
    dialog = page.locator(".dialog[aria-label='New extension']")
    dialog.locator("input[name=id]").fill("madeupstock")
    dialog.locator("input[name=name]").fill("Made-up stock")
    dialog.locator("button:has-text('Make it')").click()
    card = page.locator(".extension-card[data-extension=madeupstock]")
    expect(card.locator(".extension-status")).to_have_text("Installed (folder)")
    expect(card.locator(".extension-path")).to_be_visible()
    expect(card.locator("button:has-text('Show its folder')")).to_be_visible()
    card.locator("button:has-text('Remove')").click()
    asked = page.locator(".dialog[aria-label='Remove Made-up stock']")
    if asked.count():
        asked.locator("button.danger").click()
    expect(card).to_have_count(0)
    page.close()
