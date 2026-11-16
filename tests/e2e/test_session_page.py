# ruff: noqa: F811
"""The token, out of sight (the owner, 2026-11-16): a page opened with #token=... keeps it and clears the
address bar; the server's cookie makes a reload and a bookmark (a new tab, no fragment) work, live updates
included; a browser with no cookie gets the words that say how to open the app. Made-up data only."""

from __future__ import annotations

from typing import Any

import pandas as pd
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, server  # noqa: F401


def test_the_address_bar_loses_the_token_and_a_bookmark_works_with_the_cookie(
    browser: Browser, server: dict[str, Any]
) -> None:
    url = push_client.push(
        pd.DataFrame({"city": ["Springfield", "Shelbyville"], "visits": [3, 5]}), name="visits", new_grid=True
    )
    assert "#token=" in url
    context = browser.new_context(viewport={"width": 1280, "height": 760})
    page = context.new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    # The fragment is gone: the address bar shows the page alone.
    expect(page).to_have_url(url.split("#")[0])
    assert "token" not in page.url
    cookies = {c["name"]: c for c in context.cookies()}
    cookie = cookies[f"sab_{server['port']}"]
    assert cookie["httpOnly"] and cookie["sameSite"] == "Strict" and cookie["value"] != server["token"]
    assert page.evaluate("document.cookie") == ""  # the page's own script cannot read it

    # A reload, with no fragment.
    page.reload()
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)

    # A bookmark: a new tab of the same browser at the bare address (no token in this tab at all).
    bookmark = context.new_page()
    bookmark.goto(f"http://127.0.0.1:{server['port']}/workspace")
    expect(bookmark.get_by_role("tab", name="visits").first).to_be_visible(timeout=20000)
    expect(bookmark.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    assert bookmark.evaluate("sessionStorage.length") == 0  # the cookie did it, not a kept token
    # Live updates reach it over the websocket, which the cookie opened.
    push_client.push(pd.DataFrame({"city": ["Capital City"], "visits": [8]}), name="visits")
    expect(bookmark.get_by_text("Capital City")).to_be_visible(timeout=20000)
    # The Workbench, bookmarked too.
    workbench = context.new_page()
    workbench.goto(f"http://127.0.0.1:{server['port']}/workbench")
    expect(workbench.locator(".wb-status")).to_be_visible(timeout=20000)
    expect(workbench.locator(".signed-out")).to_have_count(0)
    context.close()


def test_a_browser_with_no_cookie_is_told_how_to_open_the_app(
    browser: Browser, server: dict[str, Any]
) -> None:
    context = browser.new_context()
    page = context.new_page()
    try:
        for path in ("/workspace", "/workbench", "/catalog"):
            page.goto(f"http://127.0.0.1:{server['port']}{path}")
            expect(page.locator(".signed-out")).to_have_text(
                "Open Swiss Army Bench from its tray icon, or run swissarmybench open."
            )
        # A data address, bookmarked: the same words, not the data and not the 401 text.
        page.goto(f"http://127.0.0.1:{server['port']}/datasets")
        expect(page.locator("body")).to_contain_text("Open Swiss Army Bench from its tray icon")
    finally:
        context.close()
