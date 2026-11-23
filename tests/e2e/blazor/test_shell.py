"""The Blazor front end's shell: the session from the token, the rail (the classic order and names), a click
moving this tab with Back and Forward, the rail's names switch kept on this computer, both themes, the
status bar, a page it does not have yet saying so with the classic page's link, and the front-end switch."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page

RAIL = ["Home", "Connections", "APIs", "Environment", "Catalog", "Grids", "ERD", "Scripts", "Notebooks"]


def test_the_rail_in_the_classic_order_and_a_click_moves_this_tab(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server)
    names = page.locator(".nav-rail-item .nav-rail-name").all_inner_texts()
    assert names[: len(RAIL)] == RAIL
    assert names[-2:] == ["Extensions", "Settings"]
    # The token is gone from the address once traded for the page's cookie.
    assert "token" not in page.url
    page.click(".nav-rail-item[data-area=settings]")
    expect(page.locator(".nav-rail-item[data-area=settings]")).to_have_attribute("aria-current", "page")
    expect(page.locator("h1")).to_contain_text("Settings")
    page.go_back()
    expect(page.locator(".nav-rail-item[data-area=projects]")).to_have_attribute("aria-current", "page")
    page.go_forward()
    expect(page.locator("h1")).to_contain_text("Settings")
    expect(page.locator("#blazor-error-ui")).to_be_hidden()
    page.close()


def test_the_rail_names_switch_is_kept_on_this_computer(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server)
    expect(page.locator("html")).to_have_class("rail-names")
    page.click(".nav-rail-toggle")
    expect(page.locator(".nav-rail-toggle")).to_have_attribute("aria-label", "Show names")
    assert call(server, "GET", "/rail") == {"labels": False}
    # Another window (the agent) turns them on: this one follows.
    call(server, "PUT", "/rail", {"labels": True})
    expect(page.locator(".nav-rail-toggle")).to_have_attribute("aria-label", "Icons only")
    page.close()


def test_both_themes_from_the_same_tokens(browser: Browser, server: dict[str, Any]) -> None:
    for dark, theme in ((False, "light"), (True, "dark")):
        page = open_page(browser, server, dark=dark)
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        background = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert background == ("rgb(18, 21, 24)" if dark else "rgb(255, 255, 255)")
        page.close()


def test_a_page_not_built_yet_links_to_the_classic_one(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "canvas")
    expect(page.locator(".not-yet")).to_contain_text("not in the Blazor front end yet")
    expect(page.locator(".not-yet a")).to_have_attribute("href", "/streamlit/canvas")
    page.close()


def test_the_front_end_switch_in_settings(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    page.check("input[name=frontend][value=blazor]")
    expect(page.locator("input[name=frontend][value=blazor]")).to_be_checked()
    assert call(server, "GET", "/app/frontend")["frontend"] == "blazor"
    page.check("input[name=frontend][value=classic]")
    expect(page.locator("input[name=frontend][value=classic]")).to_be_checked()
    assert call(server, "GET", "/app/frontend")["frontend"] == "classic"
    page.close()
