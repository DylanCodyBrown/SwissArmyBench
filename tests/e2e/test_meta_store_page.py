# ruff: noqa: F811
"""The meta store in a real browser (the owner, 2026-11-17/18: "a shared meta store on GitHub" / "Meta store
folder in settings" / "minimal setup is required for new people" / "local projects and shared projects"):
Settings' Meta store folder with the shared catalog's counts and Set up from the meta store (a vault that
cannot be read, a value typed once); a teammate's table on the Data page, "not connected here"; Settings'
Local and Shared projects folders; the Project Explorer's Local and Shared marks and filter; New project's
Where; Make a local copy of a shared project, opened, its card saying where it came from. Its own server,
a made-up team meta store laid out before it starts. Made-up names and values only. The app never runs git."""

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

from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_METASTORE_SHOTS")
LOCKED_VAULT = """def names():
    raise RuntimeError("DefaultAzureCredential failed: please run 'az login' to set up an account.")


def get(name):
    raise RuntimeError("not signed in")
"""
TEAMMATE = {
    "format": 1,
    "connection": "Finance Captive",
    "kind": "database",
    "template": "sqlserver",
    "tables": {
        "dbo.Invoices": {
            "name": "Invoices",
            "schema": "dbo",
            "database": "",
            "kind": "table",
            "columns": [
                {"name": "InvoiceId", "type": "INT", "key": "primary"},
                {"name": "CedantId", "type": "INT"},
            ],
            "primary_key": ["InvoiceId"],
            "relationships": [],
            "used_by": ["Cession statements"],
            "state": "present",
        }
    },
}


def _team_meta_store(library: Path) -> None:
    (library / "catalog").mkdir(parents=True)
    (library / "catalog" / "finance_captive.json").write_text(
        json.dumps(TEAMMATE, indent=2), encoding="utf-8"
    )
    (library / "variables.toml").write_text(
        'format = 1\n\n[variables.SHOP_TOKEN]\nfrom = "keyring"\n', encoding="utf-8"
    )


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("metastore")
    _team_meta_store(tmp / "state" / "library")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "home" / "Projects here"),
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


def open_page(browser: Browser, server: dict[str, Any], view: str = "") -> Page:
    context = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{view}#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def test_settings_meta_store_and_its_setup_checklist(browser: Browser, own_server: dict[str, Any]) -> None:
    server = own_server
    vault: dict[str, Any] = {
        "name": "Locked Vault",
        "kind": "vault",
        "template": "azure_key_vault",
        "code": LOCKED_VAULT,
    }
    vault |= {"variable": "get", "vault_mapping": [{"env": "LEDGER_PASSWORD", "secret": "ledger-password"}]}
    call(server, "POST", "/connections", vault)
    page = open_page(browser, server)
    page.locator('.nav-rail [data-area="settings"]').click()
    section = page.locator(".library-fieldset")
    expect(section.locator("legend")).to_have_text("Meta store folder")
    expect(section).to_contain_text("point it at your clone of the team's GitHub repository")
    expect(section.locator(".library-catalog")).to_contain_text("Shared catalog: 1 connection · 1 table")
    setup = section.locator(".library-setup")
    expect(setup.locator(".setup-heading")).to_contain_text("Set up from the meta store", timeout=30000)
    expect(setup.locator(".setup-heading .chip")).to_have_text("2 things to set up", timeout=30000)
    expect(setup.locator(".setup-item", has_text="Locked Vault")).to_contain_text("Sign in to Azure")
    token = setup.locator(".setup-item", has_text="SHOP_TOKEN")
    expect(token).to_be_visible()
    section.scroll_into_view_if_needed()
    shot(page, "meta-store-setup")
    token.locator("input").fill("made-up-t0ken")
    token.get_by_role("button", name="Save").click()
    expect(setup.locator(".setup-heading .chip")).to_have_text("1 thing to set up", timeout=20000)
    expect(setup.locator(".setup-item", has_text="SHOP_TOKEN")).to_have_count(0)
    # Settings' two projects folders.
    folders = page.locator(".projects-folder-fieldset")
    expect(folders.locator(".projects-folder-label")).to_have_text(
        ["Local projects folder", "Shared projects folder"]
    )
    expect(folders.locator(".projects-shared")).to_have_text("None")
    folders.scroll_into_view_if_needed()
    shot(page, "projects-folders-settings")
    page.context.close()


def test_a_teammates_table_on_the_data_page(browser: Browser, own_server: dict[str, Any]) -> None:
    page = open_page(browser, own_server)
    page.locator('.nav-rail [data-area="data"]').click()
    data = page.locator(".area-page[data-page='data']")
    section = data.locator(".db-node.kind-section[data-key='section/shared']")
    expect(section).to_be_visible(timeout=20000)
    expect(section).to_contain_text("Invoices")
    expect(section).to_contain_text("From the shared catalog: not connected here")
    data.locator(".ex-search").fill("invoices")
    expect(data.locator(".db-node", has_text="Invoices").first).to_be_visible(timeout=20000)
    data.locator(".db-node.kind-table", has_text="Invoices").first.locator(":scope > .db-line").click()
    expect(data.locator(".db-shared")).to_have_text(
        "From the shared catalog: not connected here · used by Cession statements"
    )
    shot(page, "data-page-shared-catalog")
    page.context.close()


def test_local_and_shared_projects_and_a_local_copy(browser: Browser, own_server: dict[str, Any]) -> None:
    server = own_server
    shared = Path(server["tmp"]) / "team-projects"
    shared.mkdir()
    call(server, "POST", "/projects/folder", {"which": "shared", "folder": str(shared)})
    call(server, "POST", "/project/new", {"name": "Cession close", "where": "shared"})
    call(server, "POST", "/project/close", {"discard": True})
    call(server, "POST", "/project/new", {"name": "Q3 review"})
    call(server, "POST", "/project/close", {"discard": True})
    page = open_page(browser, server, "?open=projects")
    start = page.locator('.area-page[data-page="projects"]')
    close = start.locator(".explorer-card", has_text="Cession close")
    expect(close.locator(".explorer-where-mark")).to_have_text("Shared", timeout=20000)
    expect(
        start.locator(".explorer-card", has_text="Q3 review").locator(".explorer-where-mark")
    ).to_have_text("Local")
    shot(page, "project-explorer-local-shared")
    start.locator(".explorer-where").select_option("shared")
    expect(start.locator(".explorer-card")).to_have_count(1)
    start.locator(".explorer-where").select_option("")
    # New project asks where: Local or Shared.
    start.get_by_role("button", name="New project", exact=True).click()
    dialog = page.locator("dialog.new-project")
    expect(dialog.get_by_role("radio", name="Local")).to_have_attribute("aria-checked", "true")
    dialog.get_by_role("radio", name="Shared").click()
    expect(dialog.locator(".new-project-where")).to_have_text(str(shared.resolve()))
    shot(page, "new-project-where")
    dialog.get_by_role("button", name="Cancel").click()
    # Make a local copy of the shared one: opened, its card says where it came from.
    close.get_by_role("button", name="Cession close: more").click()
    close.get_by_role("menuitem", name="Make a local copy").click()
    expect(page.locator(".project-group .project-name")).to_have_text("Cession close", timeout=20000)
    local = Path(os.environ["SWISSARMYBENCH_PROJECTS_DIR"]) / "Cession close"
    assert json.loads((local / ".sab" / "project.json").read_text())["copied_from"] == "Cession close"
    call(server, "POST", "/project/close", {"discard": True})
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=projects#token={server['token']}")
    mine = start.locator(".explorer-card", has=page.locator(".explorer-copied"))
    expect(mine).to_contain_text("Copied from Cession close", timeout=20000)
    expect(mine.locator(".explorer-where-mark")).to_have_text("Local")
    shot(page, "project-explorer-copied-from")
    page.context.close()
