# ruff: noqa: F811
"""Update available (the owner, 2026-11-16): with a stand-in release list on 127.0.0.1 that has a newer
version, the grid page's and the Workbench's status bars say "Update available", whose menu has Update to
X and What's new; with the same version they say nothing (never "up to date"); Settings' Check for
updates turns it off. Made-up data only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench import __version__
from swissarmybench.client import push_client
from swissarmybench.renamed import env
from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.test_updates import StandIn, pypi

SHOTS = env("SWISSARMYBENCH_SHOTS") or None


@pytest.fixture(scope="module")
def release_list() -> Iterator[StandIn]:
    found = StandIn()
    found.answer = pypi(__version__, "9.9.9")
    yield found
    found.close()


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, release_list: StandIn) -> Iterator[dict[str, Any]]:
    """A server of its own whose update check asks the stand-in."""
    tmp = tmp_path_factory.mktemp("e2e-update")
    environ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_UPDATE_FEED": release_list.url,
    }
    saved = {key: os.environ.get(key) for key in ("SWISSARMYBENCH_INFO", "SWISSARMYBENCH_STATE")}
    for key in saved:
        os.environ[key] = environ[key]
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=environ)
    for _ in range(100):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def grid_page(browser: Browser, server: dict[str, Any]) -> Page:
    url = push_client.push(
        pd.DataFrame({"region": ["North", "South"], "amount": [120, 340]}), name="sales", new_grid=True
    )
    page = browser.new_context(viewport={"width": 1400, "height": 820}, device_scale_factor=2).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str, **kwargs: Any) -> None:
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / name), **kwargs)


def test_the_status_bars_say_update_available_and_its_menu_updates(
    browser: Browser, server: dict[str, Any], release_list: StandIn
) -> None:
    release_list.answer = pypi(__version__, "9.9.9")
    assert call(server, "POST", "/updates/check")["version"] == "9.9.9"
    page = grid_page(browser, server)
    try:
        mark = page.locator(".statusbar .update-mark")
        expect(mark).to_have_text("Update available")
        expect(mark).to_have_attribute("title", "Update to 9.9.9")
        shot(page, "update-statusbar.png", clip={"x": 700, "y": 780, "width": 700, "height": 40})
        mark.click()
        menu = page.locator(".menu")
        expect(menu.get_by_role("menuitem", name="Update to 9.9.9")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="What's new")).to_be_visible()
        shot(page, "update-menu.png", clip={"x": 700, "y": 640, "width": 700, "height": 180})
        # This copy runs from source, not a uv tool: the update says so and nothing stops.
        menu.get_by_role("menuitem", name="Update to 9.9.9").click()
        expect(page.locator(".toast", has_text="not installed with uv")).to_be_visible()
        assert call(server, "GET", "/updates")["updating"] is None

        # The Workbench's status bar says the same.
        workbench = page.context.new_page()
        workbench.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
        expect(workbench.locator(".wb-status .update-mark")).to_have_text("Update available")
        shot(
            workbench, "update-workbench-statusbar.png", clip={"x": 600, "y": 780, "width": 800, "height": 40}
        )

        # The same version on the list: the marks go, live, and nothing says "up to date".
        release_list.answer = pypi(__version__)
        call(server, "POST", "/updates/check")
        expect(mark).to_be_hidden()
        expect(workbench.locator(".wb-status .update-mark")).to_be_hidden()
        assert "up to date" not in page.locator(".statusbar").inner_text().lower()
        workbench.close()
    finally:
        page.context.close()


def test_settings_check_for_updates_turns_it_off_and_on(
    browser: Browser, server: dict[str, Any], release_list: StandIn
) -> None:
    release_list.answer = pypi(__version__, "9.9.9")
    call(server, "PUT", "/updates", {"check": True})
    call(server, "POST", "/updates/check")
    page = grid_page(browser, server)
    try:
        mark = page.locator(".statusbar .update-mark")
        expect(mark).to_be_visible()
        page.locator(".app-row").get_by_role("button", name="Settings").click()
        switch = page.get_by_label("Check for updates")
        expect(switch).to_be_checked()
        shot(page, "update-settings.png", full_page=False)
        release_list.requests.clear()
        switch.uncheck()
        expect(mark).to_be_hidden()
        assert call(server, "GET", "/updates")["check"] is False
        call(server, "POST", "/updates/check")
        assert release_list.requests == []  # off: nothing is sent
        switch.check()
        expect(mark).to_be_visible()
    finally:
        call(server, "PUT", "/updates", {"check": True})
        page.context.close()
