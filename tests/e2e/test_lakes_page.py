# ruff: noqa: F811
"""Lakes and SharePoint in a real browser, against the stand-ins on this computer (tests/lake_standins.py;
made-up data, no real tenant): the Connections page's Lakes and SharePoint group, each kind's form with
its own sign-ins, a SharePoint lists connection added through the form (signed in by username and
password, its tenant from an environment variable, its password kept in the keyring), and the trees of a
data lake and a document library. Pictures go to SAB_SHOTS when it is set."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests import lake_standins as made_up
from tests.e2e.test_ui import browser, call, not_now, open_grid, orders_url, server  # noqa: F401
from tests.test_lakes import SITE, datalake_code, sharepoint_code

# This computer has no keyring here: the passwords come from environment variables.
MORE = {"SHAREPOINT_PASSWORD": made_up.PASSWORD, "DATALAKE_CLIENT_SECRET": made_up.SECRET}
FOLDER = Path(tempfile.mkdtemp(prefix="sab-lakes-page-"))


def shot(page: Page, name: str, target: Any = None) -> None:
    folder = os.environ.get("SAB_SHOTS")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (target or page).screenshot(path=str(Path(folder) / name))


@pytest.fixture(scope="module", autouse=True)
def standin() -> Iterator[made_up.StandIn]:
    """The stand-in and the variables that point the connections at it, set before this module's server
    starts (its child processes read them)."""
    made_up.make_lake(FOLDER)
    running = made_up.StandIn(FOLDER).start()
    before = {name: os.environ.get(name) for name in [*running.environment(), *MORE]}
    os.environ.update(running.environment() | MORE)
    yield running
    running.stop()
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def saved(server: dict[str, Any], name: str, template: str, code: str, secrets: dict[str, str]) -> None:
    body: dict[str, Any] = {
        "name": name,
        "kind": "sql",
        "template": template,
        "dialect": template,
        "code": code,
    }
    body |= {"variable": "conn", "catalog": {"language": "python", "command": "catalog = conn.catalog()"}}
    call(server, "POST", "/connections", body | ({"secrets": secrets} if secrets else {}))


def test_a_sharepoint_list_connection_is_added_through_the_form_and_its_tables_browsed(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    page = open_grid(browser, orders_url, height=1000, device_scale_factor=2)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    group = dialog.locator("h3", has_text="Lakes and SharePoint")
    expect(group).to_be_visible()
    tiles = dialog.locator(".connection-types").nth(1).locator(".connection-type")
    expect(tiles).to_have_text(
        [
            "Microsoft Fabric OneLake",
            "Azure Data Lake Storage",
            "Delta Lake",
            "SharePoint lists",
            "SharePoint documents",
        ]
    )
    expect(tiles.first.locator("svg")).to_have_count(1)  # each its own icon
    shot(page, "lakes-types.png", dialog)

    # Each kind's form: its own sign-ins.
    for label, first in (
        ("Microsoft Fabric OneLake", "As you (Azure command line or browser)"),
        ("Azure Data Lake Storage", "As you (Azure command line or browser)"),
        ("Delta Lake", "A folder on this computer"),
    ):
        dialog.locator(".connection-type", has_text=label).click()
        not_now(page, 2)
        expect(dialog.get_by_role("combobox", name="Sign in").locator("option").first).to_have_text(first)
        page.go_back()

    dialog.locator(".connection-type", has_text="SharePoint lists").click()
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    expect(sign_in.locator("option").first).to_have_text("Username and password (ROPC)")
    expect(sign_in).to_have_value("0")
    dialog.get_by_role("textbox", name="Name", exact=True).fill("Team")
    code = dialog.locator("textarea.connection-code")
    for label, key, value in (
        ("Site", "site_url", SITE),
        ("Client id", "client_id", made_up.CLIENT),
        ("Username", "username", made_up.USERNAME),
        ("Tenant id", "tenant_id", made_up.TENANT),
    ):
        box = dialog.get_by_role("textbox", name=label, exact=True)
        box.fill(value)
        box.press("Tab")
        expect(code).to_have_value(re.compile(re.escape(f'{key} = "{value}"')))
    # The tenant from an environment variable, its name suggested, this computer's value its default.
    dialog.get_by_role("combobox", name="Tenant id from").select_option("env")
    expect(dialog.get_by_role("textbox", name="Tenant id variable")).to_have_value("SHAREPOINT_TENANT_ID")
    expect(code).to_have_value(
        re.compile(re.escape(f'tenant_id = os.environ.get("SHAREPOINT_TENANT_ID", "{made_up.TENANT}")'))
    )
    # The password: kept in this computer's keyring, never in the code.
    dialog.locator('input[type="password"]').first.fill(made_up.PASSWORD)
    dialog.get_by_role("button", name="Test connection").click()
    result = dialog.locator(".connection-result")
    expect(result.locator(".status-ok")).to_have_text(
        "It works: signed in and found 2 tables.", timeout=60000
    )
    expect(result.locator(".connection-preview tbody tr")).to_have_count(10)
    assert made_up.PASSWORD not in code.input_value()
    # Saved: the password from an environment variable (this computer has no keyring here), its name offered.
    dialog.get_by_role("combobox", name="Where Password comes from").select_option("env")
    variable = dialog.get_by_role("textbox", name="Password: the variable's name")
    expect(variable).to_have_attribute("placeholder", "SHAREPOINT_PASSWORD")
    variable.fill("SHAREPOINT_PASSWORD")
    dialog.get_by_role("button", name="Use it").click()
    expect(code).to_have_value(re.compile(re.escape('password = secret("SHAREPOINT_PASSWORD")')))
    shot(page, "lakes-sharepoint-form.png", dialog)
    dialog.get_by_role("button", name="Save").click()
    tree = dialog.locator(".connection-tables")
    expect(tree.locator(".conn-tree-table")).to_have_count(2, timeout=60000)
    expect(tree.locator(".conn-tree-name")).to_have_text([re.compile("^Customers"), re.compile("^Tasks")])
    expect(dialog.locator(".connection-in-code")).to_contain_text('sab.read("Team", table)')
    shot(page, "lakes-sharepoint-tree.png", dialog)


def test_a_data_lake_and_a_document_library_show_their_tables_by_folder(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    lake = datalake_code().replace('secret("client secret")', 'secret("DATALAKE_CLIENT_SECRET")')
    saved(server, "Sales Lake", "datalake", lake, {})
    docs = sharepoint_code("sharepoint_docs").replace('secret("password")', 'secret("SHAREPOINT_PASSWORD")')
    saved(server, "Team Docs", "sharepoint_docs", docs, {})
    page = open_grid(browser, orders_url, height=1000, device_scale_factor=2)
    dialog = page.locator(".area-page[data-page='connections']")
    page.locator(".nav-rail [data-area='connections']").click()
    lakes = dialog.locator("ul.connection-cards[aria-label='Lakes and SharePoint']")
    expect(lakes.locator(".connection-card")).to_have_count(3, timeout=30000)  # Team, from the test before
    shot(page, "lakes-cards.png", dialog)

    lakes.locator(".connection-card[data-connection='Sales Lake']").click()
    tree = dialog.locator(".connection-tables")
    orders = tree.locator(".conn-tree-table[data-table='orders']")
    expect(orders.locator(".conn-tree-title")).to_have_text(
        "Delta v1 · 3.2 KB · partitioned by region", timeout=60000
    )
    expect(tree.locator(".conn-tree-title", has_text="partitioned by day")).to_have_count(1)
    orders.get_by_role("button", name="Preview").click()
    expect(orders.locator(".conn-tree-preview tbody tr")).to_have_count(5, timeout=60000)
    shot(page, "lakes-datalake-tree.png", dialog)

    page.locator(".nav-rail [data-area='connections']").click()
    lakes.locator(".connection-card[data-connection='Team Docs']").click()
    tree = dialog.locator(".connection-tables")
    expect(tree.locator(".conn-tree-group[data-group='Documents/Finance'] .conn-tree-table")).to_have_count(
        5, timeout=60000
    )  # the workbook's three sheets and named table, and the CSV
    tree.locator(".conn-tree-group[data-group='Documents/Finance'] summary").click()
    sheet = tree.locator(".conn-tree-table[data-table='Budget 2026.xlsx/Summary']")
    expect(sheet.locator(".conn-tree-title")).to_have_text("a workbook's sheet")
    shot(page, "lakes-documents-tree.png", dialog)
    sheet.get_by_role("button", name="Open").click()
    expect(page.locator(".toast", has_text="is open as a grid")).to_be_visible(timeout=60000)
