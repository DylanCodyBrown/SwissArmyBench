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


def test_the_top_right_button_warns_of_the_restart_then_updates(
    browser: Browser, server: dict[str, Any], release_list: StandIn
) -> None:
    """The owner (2026-11-18): "pop up an update button in the top right when an update is available then warn
    that it will restart once updated"."""
    release_list.answer = pypi(__version__, "9.9.9")
    assert call(server, "POST", "/updates/check")["version"] == "9.9.9"
    page = grid_page(browser, server)
    try:
        corner = page.locator(".update-corner")
        expect(corner).to_have_text("Update available")
        expect(corner).to_have_attribute("title", "Update to 9.9.9")
        box = corner.bounding_box()
        size = page.viewport_size
        assert box is not None and size is not None
        assert box["y"] < 40 and box["x"] + box["width"] > size["width"] - 40  # the top-right corner
        assert page.locator(".statusbar .update-mark").count() == 0  # moved out of the status bar
        shot(page, "update-corner.png", clip={"x": size["width"] - 420, "y": 0, "width": 420, "height": 60})
        corner.click()
        dialog = page.get_by_role("dialog")
        expect(dialog.locator(".update-restart")).to_contain_text("installs 9.9.9 and opens again")
        expect(dialog.get_by_role("button", name="What's new")).to_be_visible()
        shot(page, "update-warning.png", full_page=False)
        dialog.get_by_role("button", name="Cancel").click()
        assert call(server, "GET", "/updates")["updating"] is None  # Cancel: nothing happened
        corner.click()
        # This copy runs from source, not a uv tool: the update says so and nothing stops.
        page.get_by_role("dialog").get_by_role("button", name="Update and restart").click()
        expect(page.locator(".toast", has_text="not installed with uv")).to_be_visible()
        assert call(server, "GET", "/updates")["updating"] is None

        # The Workbench window has it too, in its own top-right corner.
        workbench = page.context.new_page()
        workbench.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
        expect(workbench.locator(".update-corner")).to_have_text("Update available")

        # The same version on the list: the buttons go, live, and nothing says "up to date".
        release_list.answer = pypi(__version__)
        call(server, "POST", "/updates/check")
        expect(corner).to_be_hidden()
        expect(workbench.locator(".update-corner")).to_be_hidden()
        assert "up to date" not in page.locator("body").inner_text().lower()
        workbench.close()
    finally:
        page.context.close()


def test_settings_click_here_to_update_shows_only_when_an_update_is_available(
    browser: Browser, server: dict[str, Any], release_list: StandIn
) -> None:
    """The owner (2026-11-19): "Check for updates should be changed to Click here to update and should only
    show when an update is available, and 6 hours is a hidden setting not needed in settings"."""
    release_list.answer = pypi(__version__)
    call(server, "POST", "/updates/check")
    page = grid_page(browser, server)
    try:
        page.locator(".nav-rail [data-area='settings']").click()
        expect(page.locator(".updates-fieldset")).to_be_hidden()
        assert page.get_by_role("button", name="Check for updates").count() == 0
        assert page.get_by_label("Check every six hours").count() == 0
        # A newer one arrives: the button shows, live; its click warns of the restart first.
        release_list.answer = pypi(__version__, "9.9.9")
        call(server, "POST", "/updates/check")
        go = page.get_by_role("button", name="Click here to update")
        expect(go).to_be_visible()
        shot(page, "update-settings.png", full_page=False)
        go.click()
        warning = page.get_by_role("dialog", name="Update to 9.9.9")
        warning.get_by_role("button", name="Update and restart").click()
        expect(page.locator(".toast", has_text="not installed with uv")).to_be_visible()
    finally:
        page.context.close()
