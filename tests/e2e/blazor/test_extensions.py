"""The Blazor Extensions page: every packaged extension is built in (the owner, 2026-11-27), so the page lists
only what the server lists (a built-in feature's own panel, and the user's folder extensions) with no Install
and no Remove of anything built in; the rail shows Source Control and Power BI on every install."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_page_draws_what_the_server_lists_with_nothing_to_install(
    browser: Browser, server: dict[str, Any]
) -> None:
    listed = call(server, "GET", "/extensions")["extensions"]
    assert [e["status"] for e in listed] == ["builtin"]  # one panel of its own; no folder extension yet
    page = open_page(browser, server, "extensions")
    cards = page.locator(".extension-card")
    expect(cards).to_have_count(len(listed))
    card = page.locator(f".extension-card[data-extension={listed[0]['id']}]")
    expect(card).to_contain_text(listed[0]["name"])
    expect(card.locator(".extension-status")).to_have_text("Built in")
    expect(card.locator(".extension-install, .extension-remove")).to_have_count(0)
    expect(page.locator("button:has-text('New extension…')")).to_be_visible()
    expect(page.locator(".extension-card[data-extension=streamlit]")).to_have_count(0)
    page.close()


def test_the_rail_has_source_control_and_power_bi(browser: Browser, server: dict[str, Any]) -> None:
    areas = [a["area"] for a in call(server, "GET", "/app/areas")["areas"]]
    assert areas == ["scm", "powerbi"]
    page = open_page(browser, server, "home")
    rail = page.locator(".nav-rail")
    for area in call(server, "GET", "/app/areas")["areas"]:
        item = rail.locator(f".nav-rail-item[data-area={area['area']}]")
        expect(item).to_be_visible()
        expect(item.locator(".nav-rail-name")).to_have_text(area["name"])
    page.close()


def test_a_new_folder_extension(browser: Browser, server: dict[str, Any]) -> None:
    """New extension… makes a made-up folder extension, loaded at once: its card says Installed (folder), its
    path, Remove and Show its folder; Remove takes it away (a folder's goes at once, no restart)."""
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
