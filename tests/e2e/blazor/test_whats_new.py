"""What's New in the browser (Layout/WhatsNewHost.razor): a server whose computer last saw an older version
opens the window by itself over the page, each release's New features and Bug fixes apart; closing it marks
the version seen, so a reload stays closed; Home's What's new and the status bar's version open it again."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page, serve


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server on a computer that last saw 0.0.36: the first start after an update."""
    tmp = tmp_path_factory.mktemp("whats-new")
    (tmp / "state").mkdir()
    (tmp / "state" / "whats_new.json").write_text(json.dumps({"version": "0.0.36"}), encoding="utf-8")
    yield from serve(tmp)


def test_it_opens_after_an_update_closes_and_opens_again(browser: Browser, server: dict[str, Any]) -> None:
    told = call(server, "GET", "/whats-new")
    assert told["open"] is True and told["seen"] == "0.0.36"
    page = open_page(browser, server)
    window = page.get_by_role("dialog", name="What's new")
    expect(window).to_be_visible()
    releases = window.locator("details.whatsnew-release")
    expect(releases).to_have_count(len(told["releases"]))
    expect(releases.first).to_have_attribute("open", "")
    expect(releases.first.locator("summary")).to_contain_text(told["releases"][0]["version"])
    expect(releases.first.locator(".whatsnew-section.features h3")).to_have_text("New features")
    expect(releases.first.locator(".whatsnew-section.fixes h3")).to_have_text("Bug fixes")
    expect(releases.nth(1)).not_to_have_attribute("open", "")
    # The focus is inside, and Tab keeps it there.
    assert page.evaluate("() => !!document.activeElement.closest('.whatsnew')")
    for _ in range(6):
        page.keyboard.press("Tab")
        assert page.evaluate("() => !!document.activeElement.closest('.whatsnew')")

    page.keyboard.press("Escape")
    expect(window).to_have_count(0)
    for _ in range(50):  # the close's POST lands just after the window goes
        if call(server, "GET", "/whats-new")["open"] is False:
            break
        page.wait_for_timeout(100)
    assert call(server, "GET", "/whats-new")["open"] is False

    page.reload()
    page.wait_for_selector(".nav-rail")
    page.wait_for_timeout(500)
    expect(window).to_have_count(0)

    # Home's What's new: every release, the newest unfolded; Got it closes it.
    page.get_by_role("button", name="What's new").click()
    expect(window).to_be_visible()
    every = call(server, "GET", "/whats-new?all=1")["releases"]
    expect(window.locator("details.whatsnew-release")).to_have_count(len(every))
    window.get_by_role("button", name="Got it").click()
    expect(window).to_have_count(0)

    # The status bar's version opens it too; a click outside closes it.
    page.locator(".status-bar .version-mark").click()
    expect(window).to_be_visible()
    page.mouse.click(8, 8)
    expect(window).to_have_count(0)
    page.close()


def test_the_agent_opens_it_on_the_main_window(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "tables")
    window = page.get_by_role("dialog", name="What's new")
    expect(window).to_have_count(0)
    call(server, "POST", "/whats-new/open", {})
    expect(window).to_be_visible()
    window.get_by_role("button", name="Close").click()
    expect(window).to_have_count(0)
    page.close()
