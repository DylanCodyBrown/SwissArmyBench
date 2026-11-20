# ruff: noqa: F811
"""Find connections on this computer in a real browser (the owner, 2026-11-20: "Is it possible to scan the
computer's common apps for connections and import them. DBeaver, SSMS, ODBC, etc."): the Connections page's
button, the list of what a made-up home folder's tools keep (merged, a kind with no connection, the amber
note), tick two, Import, the two cards appear; no made-up password ever reaches the page.

With SAB_FIND_SHOTS set to a folder, the test also saves screenshots there (2x)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests import found_fixtures as fx
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SAB_FIND_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture(scope="module")
def finding(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server of its own whose Find connections looks only in a made-up Windows home folder."""
    tmp = tmp_path_factory.mktemp("find")
    home = fx.windows_home(tmp / "fakehome")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_FIND_HOME": str(home),
        "SWISSARMYBENCH_FIND_SYSTEM": "windows",
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(150):
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


def test_find_tick_two_import_and_the_cards_appear(browser: Browser, finding: dict[str, Any]) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{finding['port']}/workspace?open=connections#token={finding['token']}")
    page.get_by_role("button", name="Find connections on this computer…").click()
    dialog = page.locator("dialog.find-connections")
    rows = dialog.locator(".find-row")
    expect(rows.first).to_be_visible(timeout=20000)
    expect(dialog.locator(".find-row", has_text="Shop (dev)")).to_contain_text("DBeaver, pgAdmin 4")
    events = dialog.locator(".find-row", has_text="Events")
    expect(events).to_contain_text("Swiss Army Bench has no MongoDB connection yet")
    expect(events.locator("input[type=checkbox]")).to_be_disabled()
    expect(dialog.locator(".find-row", has_text="Finance ledger").locator(".error-mark")).to_be_visible()
    searched = dialog.locator(".find-row", has_text="Orders on orders-sql07")
    expect(searched).to_contain_text("found by searching")
    shot(page, "find-connections-list")
    html = dialog.inner_html()
    assert [p for p in fx.PASSWORDS if p in html] == []

    # The search box narrows the rows; Select all ticks only what can be imported.
    dialog.get_by_role("searchbox").fill("shop")
    expect(events).to_be_hidden()
    expect(dialog.locator(".find-row", has_text="Shop (dev)")).to_be_visible()
    dialog.get_by_role("searchbox").fill("")
    dialog.locator(".find-row", has_text="Shop (dev)").locator("input[type=checkbox]").check()
    dialog.locator(".find-row", has_text="Sales warehouse").locator("input[type=checkbox]").check()
    dialog.get_by_role("button", name="Import 2").click()
    expect(dialog).to_have_count(0, timeout=20000)

    cards = page.locator(".connection-card")
    expect(cards.filter(has_text="Shop dev")).to_be_visible(timeout=20000)
    expect(cards.filter(has_text="Sales warehouse")).to_be_visible()
    shot(page, "find-connections-imported")
    names = {c["name"] for c in call(finding, "GET", "/connections")["connections"]}
    assert {"Shop dev", "Sales warehouse"} <= names
    variables = {v["name"] for v in call(finding, "GET", "/variables")["variables"]}
    assert {"SHOP_DEV_PASSWORD", "SALES_WAREHOUSE_PASSWORD"} <= variables

    # Found again: those two are Already added.
    page.get_by_role("button", name="Find connections on this computer…").click()
    again = page.locator("dialog.find-connections")
    sales = again.locator(".find-row", has_text="Sales warehouse")
    expect(sales).to_contain_text("Already added", timeout=20000)
    expect(sales.locator("input[type=checkbox]")).to_be_disabled()
    again.get_by_role("button", name="Cancel").click()
    context.close()
