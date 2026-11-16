# ruff: noqa: F811
"""The app's name and version at the bottom left of every status bar (the owner, 2026-11-16). Made-up data."""

from __future__ import annotations

from typing import Any

import pandas as pd
from playwright.sync_api import Browser, expect

from swissarmybench import __version__
from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, open_grid, server  # noqa: F401


def test_every_status_bar_names_the_app_and_its_version(browser: Browser, server: dict[str, Any]) -> None:
    page = open_grid(browser, push_client.push(pd.DataFrame({"pear": [1, 2]}), new_grid=True))
    name = f"Swiss Army Bench {__version__}"
    expect(page.locator(".statusbar .version-mark")).to_have_text(name, timeout=15000)
    with page.context.expect_page() as opened:
        page.evaluate("window.open('/workbench', 'swissarmybench-workbench')")
    workbench = opened.value
    stamp = workbench.locator(".wb-status .version-mark")
    expect(stamp).to_have_text(f"Swiss Army Bench {__version__}", timeout=20000)
    page.context.close()
