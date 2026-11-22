"""The settings (the owner, 2026-11-16: "add new local env variables from the page easily and browse
what is there and for variables that are not from the key vault you can see their current values"), in a real
browser, where they live since the Variables page folded into the Environment (2026-11-22): its Settings and
secrets tab from the rail, Add a setting, a plain value in plain sight, a key vault's entry without its
value and its vault's card, Show on a keyring secret, the old address landing there. Its own server,
with a keyring kept in a temporary file (this container has none). Made-up names and values only."""

from __future__ import annotations

import json
import os
import re
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
from tests.e2e.environment_helpers import add_setting, open_settings, setting_row
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_VARIABLES_SHOTS")
SECRET = "made-up-token-4471"


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("variables")
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


def test_the_variables_page(browser: Browser, own_server: dict[str, Any]) -> None:  # noqa: F811
    server = own_server
    vault = {
        "name": "Team vault",
        "kind": "vault",
        "code": "def get(name):\n    return 'made-up'",
        "variable": "get",
        "vault_mapping": [{"env": "WAREHOUSE_PASSWORD", "secret": "warehouse-password"}],
    }
    call(server, "POST", "/blades", vault)
    warehouse = {
        "name": "Warehouse",
        "kind": "sql",
        "dialect": "sqlite",
        "code": "import sqlite3\npw = secret('WAREHOUSE_PASSWORD')\ntoken = secret('SHOP_API_TOKEN')\n"
        "conn = sqlite3.connect(':memory:')\n",
    }
    call(server, "POST", "/blades", warehouse)
    # The agent keeps a secret in the keyring: never answered back.
    secret_body = {"name": "SHOP_API_TOKEN", "value": SECRET, "from": "keyring"}
    kept = call(server, "PUT", "/variables", secret_body, agent=True)
    assert SECRET not in json.dumps(kept)
    call(server, "PUT", "/variables", {"name": "EXPORT_FOLDER", "value": "/made/up/exports", "local": True})
    url = push_client.push(pd.DataFrame({"region": ["North", "South"], "sales": [12, 30]}), name="regions")

    for dark in (False, True):
        page = browser.new_context(
            viewport={"width": 1300, "height": 820},
            device_scale_factor=2 if SHOTS else 1,
            color_scheme="dark" if dark else "light",
        ).new_page()
        page.goto(url)
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        found = open_settings(page)
        expect(found).to_be_visible()
        expect(page).to_have_url(re.compile(r"[?&]open=environment\b"))
        expect(page.locator('.nav-rail [data-area="environment"]')).to_have_attribute("aria-current", "page")
        side = found.locator(".env-side")
        # A key vault's entry: the vault and the secret's name, never a value; used by the connection.
        vaulted = setting_row(page, "WAREHOUSE_PASSWORD")
        expect(vaulted).to_contain_text("Team vault · warehouse-password")
        vaulted.click()
        expect(side.locator(".env-used")).to_contain_text("Warehouse · Password")  # the box it fills
        expect(side.get_by_role("button", name="Show", exact=True)).to_have_count(0)
        # Its vault is listed above the settings it gives.
        expect(found.locator('.variables-vault-card[data-vault="Team vault"]')).to_be_visible()
        if dark:
            shot(page, "variables-dark")
            page.context.close()
            continue
        # Add a setting: the name in capitals as typed, a plain value in plain sight.
        form = add_setting(page)
        form.get_by_label("Name").fill("sales_region")
        expect(form.get_by_label("Name")).to_have_value("SALES_REGION")
        form.get_by_label("Value").fill("North")
        shot(page, "variables-add")
        page.locator("dialog").get_by_role("button", name="Add", exact=True).click()
        added = setting_row(page, "SALES_REGION")
        expect(added.locator(".env-val")).to_have_text("North")
        assert call(server, "GET", "/variables?source=value")["variables"][-1]["value"] == "North"
        # This computer only: said where it comes from.
        expect(setting_row(page, "EXPORT_FOLDER")).to_contain_text("this computer only")
        # A keyring secret: dots, then Show (the user's click), then Hide.
        secret = setting_row(page, "SHOP_API_TOKEN")
        expect(secret.locator(".env-val")).to_contain_text("••••••••")
        assert SECRET not in found.inner_text()
        secret.click()
        side.get_by_role("button", name="Show", exact=True).click()
        expect(secret.locator(".env-shown")).to_have_text(SECRET)
        shot(page, "variables-light")
        side.get_by_role("button", name="Hide", exact=True).click()
        expect(secret.locator(".env-val")).to_contain_text("••••••••")
        assert SECRET not in found.inner_text()
        # The one search keeps a source's settings, and finds a setting by the connection that uses it.
        search = found.get_by_role("searchbox", name="Search the environment")
        rows = found.locator(".env-row[data-name]")
        search.fill("key vault")
        expect(rows).to_have_count(1)
        search.fill("warehouse")
        expect(rows).to_have_count(2)
        search.fill("")
        # Remove: what uses it shown first.
        secret.click()
        side.get_by_role("button", name="Remove…").click()
        asked = page.locator("dialog.env-dialog")
        expect(asked).to_contain_text("Warehouse")
        asked.get_by_role("button", name="Cancel").click()
        # The Variables page's old address lands on this tab, at the setting it named.
        page.goto(
            f"http://127.0.0.1:{server['port']}/workspace?open=variables&name=SALES_REGION#token={server['token']}"
        )
        expect(page).to_have_url(re.compile(r"[?&]open=environment\b"))
        expect(page).to_have_url(re.compile(r"[?&]at=settings?\b"))
        expect(page.locator('.area-page[data-page="variables"]')).to_have_count(0)
        expect(setting_row(page, "SALES_REGION")).to_have_class(re.compile(r"\bsel\b"))
        page.context.close()
