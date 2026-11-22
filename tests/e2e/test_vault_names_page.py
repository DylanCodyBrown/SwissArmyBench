"""A key vault's variables after a restart (the owner, 2026-11-20: "Every time I update or reopen the app my
Vault variables disappear"), in a real browser: a vault that loads every secret is read once; the server
stops and starts again; the Variables page and the ${ list have its variables at once, and a start-up read
that fails keeps them, the vault's card saying "Names from <time>" with Read again. Its own server, twice on
one state folder. Made-up names only; the made-up vault reads its names from a file."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from tests.e2e.environment_helpers import add_setting, open_settings, setting_row
from tests.e2e.test_ui import browser, call, not_now  # noqa: F401


@contextmanager
def server(tmp: Path) -> Iterator[dict[str, Any]]:
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
    (tmp / "server.json").unlink(missing_ok=True)
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
        yield info
    finally:
        process.terminate()
        process.wait(timeout=20)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_a_vaults_variables_are_there_after_a_restart(
    browser: Browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["team-key", "warehouse-password"]))
    vault = {
        "name": "Team vault",
        "kind": "vault",
        "template": "azure_key_vault",
        "variable": "get",
        "code": "import json\nfrom pathlib import Path\n\n\ndef names():\n"
        f"    return json.loads(Path(r'{listed}').read_text())\n\n\ndef get(name):\n    return 'made-up'\n",
        "vault_all": True,
        "vault_mapping": [],
    }
    with server(tmp_path) as first:
        assert call(first, "POST", "/connections", vault)["name"] == "Team vault"
        read = call(first, "POST", "/connections/vaults/secrets", {"name": "Team vault"})
        assert [n["env"] for n in read["names"]] == ["team_key", "warehouse_password"]
    listed.unlink()  # the vault cannot be read at the next start: its names are the ones kept
    with server(tmp_path) as again:
        assert {v["name"] for v in call(again, "GET", "/variables")["variables"]} >= {"team_key"}
        frame = pd.DataFrame({"region": ["North", "South"], "sales": [12, 30]})
        url = push_client.push(frame, name="regions")
        page = browser.new_context(viewport={"width": 1300, "height": 820}).new_page()
        page.goto(url)
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        found = open_settings(page)
        expect(setting_row(page, "warehouse_password")).to_contain_text("Team vault · warehouse-password")
        card = found.locator('.variables-vault-card[data-vault="Team vault"]')
        expect(card.locator(".variables-vault-count")).to_have_text("2 variables")
        # The ${ list offers them.
        value = add_setting(page).get_by_label("Value")
        value.press_sequentially("${team")
        offered = page.get_by_role("listbox", name="Variables")
        expect(offered.get_by_role("option").first).to_contain_text("team_key")
        value.press("Escape")
        page.locator("dialog").get_by_role("button", name="Cancel").click()
        # The start-up read failed: the card says when the names are from, and Read again.
        stale = found.locator(".variables-vault-stale")
        expect(stale).to_contain_text("Names from", timeout=40000)
        listed.write_text(json.dumps(["team-key", "warehouse-password", "new-key"]))
        stale.get_by_role("button", name="Read again").click()
        expect(stale).to_have_count(0, timeout=20000)
        expect(card.locator(".variables-vault-count")).to_have_text("3 variables", timeout=20000)
        page.context.close()


def owners_vault(listed: Path) -> str:
    return (
        "import json\nfrom pathlib import Path\n\n\ndef names():\n"
        f"    return json.loads(Path(r'{listed}').read_text())\n\n\ndef get(name):\n    return 'made-up'\n"
    )


def offered_for(page: Page, typed: str) -> Locator:
    """Connections, Add connection, PostgreSQL, the Password box: the dollar-brace list for `typed`."""
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").first.click()
    page.locator(".connection-type", has_text="PostgreSQL").click()
    not_now(page)
    password = dialog.get_by_label("Password", exact=True)
    password.click()
    password.press_sequentially(typed)
    return dialog.get_by_role("listbox", name="Variables")


def test_the_owners_steps_add_read_save_then_the_dollar_brace(
    browser: Browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The owner (0.0.29): "I mapped the vars in the vault, then went back to Connections and they don't show
    when I type the dollar-brace." The suggested names kept, nothing typed over them."""
    listed = tmp_path / "names.json"
    listed.write_text(json.dumps(["warehouse-password", "crm-key"]))
    with server(tmp_path) as first:
        url = push_client.push(pd.DataFrame({"region": ["North"], "sales": [12]}), name="regions")
        page = browser.new_context(viewport={"width": 1300, "height": 820}).new_page()
        page.goto(url)
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        dialog = page.locator(".area-page[data-page='connections']")
        open_settings(page).get_by_role("button", name="Add key vault").click()
        page.locator(".variables-vault-types .connection-type", has_text="Azure Key Vault").click()
        not_now(page)
        dialog.locator("summary", has_text="Python code").click()
        code = dialog.get_by_role("textbox", name="The Python this connection runs")
        code.fill(owners_vault(listed))
        code.dispatch_event("change")
        expect(dialog.locator(".vault-map tbody tr:not(.vault-new)")).to_have_count(2)  # read by itself
        dialog.locator(".area-page-foot").get_by_role("button", name="Save").click()
        expect(dialog.locator(".area-page-title")).to_contain_text("Azure Key Vault", timeout=20000)
        offered = offered_for(page, "${warehouse")
        expect(offered.get_by_role("option").first).to_contain_text("warehouse_password")
        expect(offered.get_by_role("option").first).to_contain_text("Key vault · Azure Key Vault")
        page.context.close()
        assert {v["name"] for v in call(first, "GET", "/variables")["variables"]} >= {"crm_key"}
    with server(tmp_path):  # the same after a restart
        url = push_client.push(pd.DataFrame({"region": ["North"], "sales": [12]}), name="regions")
        page = browser.new_context(viewport={"width": 1300, "height": 820}).new_page()
        page.goto(url)
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        offered = offered_for(page, "${crm")
        expect(offered.get_by_role("option").first).to_contain_text("crm_key")
        page.context.close()
