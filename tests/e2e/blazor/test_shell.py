"""The Blazor front end's shell: the session from the token, the rail (the classic order and names), a click
moving this tab with Back and Forward, the rail's names switch kept on this computer, both themes, the
status bar, a page it does not have yet saying so with the classic page's link, and the front-end switch."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page

RAIL = ["Home", "Connections", "APIs", "Environment", "Catalog", "Tables", "ERD", "Scripts", "Notebooks"]


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


def test_an_address_with_no_page_says_so_in_one_line(browser: Browser, server: dict[str, Any]) -> None:
    # Every rail area has a page; an extension's area with no panel is one line, no link anywhere else.
    page = open_page(browser, server, "x-stockroom")
    expect(page.locator(".not-yet")).to_contain_text("not a page of this app")
    expect(page.locator(".not-yet a")).to_have_count(0)
    page.close()


def test_the_status_bar_names_no_other_front_end(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    expect(page.locator(".status-frontend")).to_have_count(0)
    expect(page.locator("input[name=frontend]")).to_have_count(0)  # no Front end choice in Settings
    expect(page.locator("footer")).not_to_contain_text("Classic")
    page.close()


def test_an_old_address_lands_on_its_blazor_page(browser: Browser, server: dict[str, Any]) -> None:
    """/workspace?open=connections, /g/<grid> and a pushed grid's #grid= open their Blazor pages."""
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    base, token = f"http://127.0.0.1:{server['port']}", server["token"]
    page = browser.new_page(viewport={"width": 1360, "height": 860})
    page.goto(f"{base}/workspace?open=connections#token={token}")
    page.wait_for_url("**/blazor/connections**", timeout=60_000)
    page.wait_for_selector(".nav-rail", timeout=60_000)  # the token traded for the page's cookie first
    page.goto(f"{base}/g/{grid}")
    page.wait_for_url(f"**/blazor/tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible(timeout=60_000)
    page.goto(f"{base}/workspace#grid={grid}")
    page.wait_for_url(f"**/blazor/tables?grid={grid}", timeout=60_000)
    page.close()


def test_the_agents_navigate_moves_the_main_window(browser: Browser, server: dict[str, Any]) -> None:
    """app_navigate (POST /navigate) answered "sent" and nothing moved: no page followed the navigate notice.
    The main window goes there as a rail click would: an area, a connection's detail, a table's tab, Back."""
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = open_page(browser, server, "")
    expect(page.locator("h1.area-page-title")).to_be_visible()

    assert call(server, "POST", "/navigate", {"to": "analyze"})["sent"] == {"window": "home", "to": "analyze"}
    expect(page).to_have_url(re.compile(r"/blazor/analyze$"))
    call(server, "POST", "/navigate", {"to": f"grid:{grid}"})
    expect(page).to_have_url(re.compile(rf"/blazor/tables\?grid={grid}$"))
    expect(page.locator(".ag-row").first).to_be_visible()
    call(server, "POST", "/navigate", {"to": "back"})
    expect(page).to_have_url(re.compile(r"/blazor/analyze$"))
    call(server, "POST", "/navigate", {"to": "home"})
    expect(page).to_have_url(re.compile(r"/blazor/$"))
    page.close()


def snapshot(server: dict[str, Any], area: str) -> tuple[int, bytes, dict[str, str]]:
    """POST /snapshots as the agent asks it: the status, the bytes and the answer's headers."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{server['port']}/snapshots",
        data=json.dumps({"area": area}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
            return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read(), {k.lower(): v for k, v in refused.headers.items()}


def test_the_agents_snapshot_is_drawn_by_the_page(browser: Browser, server: dict[str, Any]) -> None:
    """app_snapshot (POST /snapshots) waited its 30 seconds and was told no page answered: no page followed
    the snapshot_request notice. The page in front draws the area and sends the PNG; an area it does not
    show is said at once."""
    page = open_page(browser, server, "")
    expect(page.locator("h1.area-page-title")).to_be_visible()

    status, picture, headers = snapshot(server, "app")
    assert status == 200 and picture.startswith(b"\x89PNG\r\n\x1a\n")
    assert headers["x-snapshot-width"] == "1360" and headers["x-snapshot-height"] == "860"

    status, words, _ = snapshot(server, "analyze")  # Home shows no Analyze board
    assert status == 502 and b"does not show the analyze area" in words
    page.close()
