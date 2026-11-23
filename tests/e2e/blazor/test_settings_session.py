"""The Blazor front end's Settings (the theme remembered by this browser, Follow the agent kept on this
computer) and the Session page (the agent's entries live, the rail's count, Me and Both)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_settings_theme_and_follow(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    page.check("input[name=theme][value=dark]")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.check("input[name=theme][value=system]")
    follow = page.locator(".follow-fieldset input[type=checkbox]")
    follow.uncheck()
    expect(follow).not_to_be_checked()
    assert call(server, "GET", "/session-log")["follow"] is False
    follow.check()
    expect(page.locator(".mcp-prompt")).to_contain_text("swissarmybench-mcp")
    page.close()


def test_session_shows_the_agents_work_live(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server)
    call(server, "POST", "/samples/store")  # not the agent: the user's own
    page.click(".nav-rail-item[data-area=session]")
    expect(page.locator("h1")).to_contain_text("Session")
    page.click("button:has-text('Me')")
    expect(page.locator(".session-log")).to_contain_text("Opened orders")
    page.click("button:has-text('Both')")
    expect(page.locator(".session-log tbody tr").first).to_be_visible()
    page.close()
