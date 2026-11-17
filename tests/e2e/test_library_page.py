"""The library in a real browser (Plans/library.plan.md; the owner, 2026-11-17): this computer's older stores
moved into it once and said on the page; Settings' Library (the folder, what is in it); the key vaults on the
Variables page and not on the Connections page. Its own server, with older stores laid out in its state
folder and a keyring kept in a temporary file. Made-up names and values only."""

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

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_LIBRARY_SHOTS")


def _older_stores(state: Path) -> None:
    """What an older version kept: blades as JSON, variables.json, colours.toml."""
    (state / "blades").mkdir(parents=True)
    vault = {
        "name": "Team vault",
        "kind": "vault",
        "code": "def get(name):\n    return 'made-up'",
        "variable": "get",
        "vault_mapping": [{"env": "WAREHOUSE_PASSWORD", "secret": "warehouse-password"}],
    }
    warehouse = {
        "name": "Warehouse",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "variable": "conn",
        "code": "import sqlite3\npw = secret('WAREHOUSE_PASSWORD')\nconn = sqlite3.connect(':memory:')\n",
    }
    for i, blade in enumerate((vault, warehouse)):
        (state / "blades" / f"blade-{i}.json").write_text(json.dumps(blade), encoding="utf-8")
    shared = {"format": 1, "variables": [{"name": "SALES_REGION", "from": "value", "value": "North"}]}
    (state / "variables.json").write_text(json.dumps(shared), encoding="utf-8")


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("library")
    _older_stores(tmp / "state")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
    }
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"])
    try:
        for _ in range(200):
            try:
                info = json.loads((tmp / "server.json").read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")
        yield info | {"tmp": tmp}
    finally:
        process.terminate()
        process.wait(timeout=20)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def test_the_library_in_the_page(browser: Browser, own_server: dict[str, Any]) -> None:  # noqa: F811
    server = own_server
    library = server["tmp"] / "state" / "library"
    url = push_client.push(pd.DataFrame({"region": ["North", "South"], "sales": [12, 30]}), name="regions")
    page = browser.new_context(
        viewport={"width": 1300, "height": 820}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    # The move into the library, said once.
    notice = page.locator(".toast", has_text="Your connections and blades now live in your library folder")
    expect(notice).to_be_visible(timeout=10000)
    expect(notice).to_contain_text("2 connections and blades")
    shot(page, "library-moved-notice")
    assert (library / "vaults" / "team_vault.blade.py").is_file()
    assert (library / "connections" / "warehouse.blade.py").is_file()
    assert call(server, "POST", "/library/notices")["notices"] == []  # the page took it

    # Settings' Library: where it is, what is in it.
    page.locator('.nav-rail [data-area="settings"]').click()
    section = page.locator(".library-fieldset")
    expect(section).to_be_visible()
    expect(section.locator(".library-folder code")).to_have_text(str(library))
    expect(section.locator(".library-counts")).to_contain_text("1 connections · 1 key vaults")
    expect(section.get_by_role("button", name="Change…")).to_be_visible()
    expect(section.get_by_role("button", name="Default")).to_have_count(0)
    section.scroll_into_view_if_needed()
    shot(page, "library-settings")

    # The key vaults: on the Variables page, not on the Connections page.
    page.locator('.nav-rail [data-area="variables"]').click()
    variables = page.locator('.area-page[data-page="variables"]')
    expect(variables.locator('.variables-vault-card[data-vault="Team vault"]')).to_be_visible()
    expect(variables.locator(".variable-row", has_text="SALES_REGION")).to_contain_text("North")
    variables.get_by_role("button", name="Add key vault").click()
    expect(variables.locator(".variables-vault-types .connection-type").first).to_be_visible()
    shot(page, "library-variables-vaults")
    variables.get_by_role("button", name="Cancel").click()
    variables.locator('.variables-vault-card[data-vault="Team vault"]').click()
    expect(page.locator('.area-page[data-page="connections"]')).to_be_visible()
    expect(page.locator(".connection-detail, .area-page[data-page='connections']").first).to_contain_text(
        "Team vault"
    )
    page.locator('.nav-rail [data-area="connections"]').click()
    connections = page.locator('.area-page[data-page="connections"]')
    expect(connections.locator('.connection-card[data-connection="Warehouse"]')).to_be_visible()
    expect(connections.locator('.connection-card[data-connection="Team vault"]')).to_have_count(0)
    connections.get_by_role("button", name="Add connection").click()
    expect(connections.locator(".connection-type").first).to_be_visible()
    expect(connections.locator("h3", has_text="Key vaults")).to_have_count(0)
    page.context.close()
