# ruff: noqa: F811
"""A Dataverse connection in a real browser, against the stand-in on this computer
(tests/dataverse_standin.py; no real tenant, made-up data): it is added through the form (its address,
the app registration's sign-in, its client secret from a key vault and never typed), tested, saved; its
catalog shows the environment's tables in one schema, each with its display name where it says more;
a table's page reads it with sab.read; and the table opens as a grid, its choice columns as labels."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests import dataverse_standin as made_up
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import wait_until

VAULT_CODE = f"""values = {{"crm-client-secret": "{made_up.SECRET}"}}


def names():
    return list(values)


def get(name):
    return values[name]
"""


@pytest.fixture(scope="module", autouse=True)
def standin() -> Iterator[made_up.StandIn]:
    """The stand-in, and the variables that point the sign-ins at it, set before this module's server
    starts (its child processes read them)."""
    running = made_up.StandIn().start()
    before = {name: os.environ.get(name) for name in running.environment()}
    os.environ.update(running.environment())
    yield running
    running.stop()
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def test_a_dataverse_environment_is_added_through_the_form_browsed_and_opened_as_a_grid(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    call(server, "POST", "/connections", vault)
    page = open_grid(browser, orders_url)
    dialog = page.locator("dialog")

    # The form: the environment's address and the sign-in; As you comes first.
    page.locator(".app-row").get_by_role("button", name="Connections").click()
    page.get_by_role("button", name="Add connection").click()
    tile = page.locator(".connection-type", has_text="Dataverse")
    expect(tile.locator("svg")).to_have_count(1)  # its own icon
    tile.click()
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    expect(sign_in).to_have_value("0")
    expect(sign_in.locator("option")).to_have_text(
        [
            "As you (Azure command line or browser)",
            "Managed identity (in Azure: a Function App, App Service or VM)",
            "App registration, its secret from a key vault",
        ]
    )
    sign_in.select_option("2")
    expect(dialog.get_by_role("textbox", name="Tenant id", exact=True)).to_be_visible()  # its own fields
    dialog.get_by_role("textbox", name="Name").fill("Sales CRM")
    code = dialog.locator("textarea.connection-code")
    for label, key, value in (
        ("Address", "url", standin.url),
        ("Tenant id", "tenant_id", made_up.TENANT),
        ("Client id", "client_id", made_up.CLIENT),
    ):
        box = dialog.get_by_role("textbox", name=label, exact=True)
        box.fill(value)
        box.press("Tab")
        expect(code).to_have_value(re.compile(re.escape(f'{key} = "{value}"')))  # written into its code
    # Its client secret: a key vault's (or an environment variable's), never typed into the app.
    expect(dialog.locator("legend", has_text="App registration")).to_be_visible()
    row = dialog.locator(".connection-password").filter(has_text="Client secret comes from")
    source = row.get_by_role("combobox", name="Where Client secret comes from")
    expect(source).to_have_value("vault")
    expect(source.locator("option")).to_have_text(["An environment variable", "A key vault"])
    expect(dialog.locator('input[type="password"]')).to_have_count(0)
    picker = row.get_by_role("combobox", name="Entry in the vault")
    expect(picker.locator("option", has_text="crm-client-secret")).to_have_count(1, timeout=30000)
    picker.select_option("crm-client-secret")
    expect(code).to_have_value(re.compile(re.escape('client_secret = secret("crm_client_secret")')))
    dialog.get_by_role("button", name="Test connection").click()
    result = dialog.locator(".connection-result")
    expect(result.locator(".status-ok")).to_have_text(
        "It works: signed in and found 4 tables.", timeout=60000
    )
    expect(result.locator(".connection-preview tbody tr")).to_have_count(12)  # account's first rows
    token = next(r for r in standin.requests if r["what"] == "token")
    assert token["form"]["client_secret"] == made_up.SECRET and token["tenant"] == made_up.TENANT
    assert made_up.SECRET not in dialog.inner_text() and made_up.SECRET not in code.input_value()
    dialog.get_by_role("button", name="Save").click()
    saved = dialog.locator(".connection-row", has_text="Sales CRM")
    expect(saved.locator(".badge")).to_have_text("Dataverse")
    expect(saved.locator("code")).to_contain_text('sab.read("Sales CRM", table)')
    wait_until(lambda: any(c["name"] == "Sales CRM" for c in call(server, "GET", "/catalogs")["catalogs"]))

    # The catalog: one schema, its tables; a display name shows where it says more than the name.
    catalog = page.context.new_page()
    catalog.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}&catalog=Sales%20CRM")
    catalog.wait_for_selector('[role="treeitem"]')
    expect(catalog.locator('[role="treeitem"][aria-level="1"] > .node > .node-label')).to_have_text(["dbo"])
    tables = catalog.locator('[role="treeitem"][aria-level="2"]')
    expect(tables.locator(":scope > .node > .node-label")).to_have_text(
        ["account", "contact", "opportunity", "systemuser"]
    )
    expect(tables.locator(":scope > .node > .node-kind")).to_have_text(["User"])  # Account for account: no
    tables.filter(has=catalog.locator(':scope > .node > .node-label:text-is("opportunity")')).locator(
        ":scope > .node .node-label"
    ).first.click()
    detail = catalog.locator("#detail")
    expect(detail.locator("pre")).to_have_text('sab.read("Sales CRM", "opportunity")')
    stage = detail.locator(".columns-table").first.locator("tr", has_text="salesstage")
    expect(stage.locator("td").nth(1)).to_have_text("Picklist")
    expect(stage.locator("td").nth(3)).to_have_text("Sales Stage")
    expect(detail.locator(".preview-table tbody tr")).to_have_count(50, timeout=60000)  # its first rows
    detail.get_by_role("button", name="Open as grid").click()
    expect(catalog.locator(".toast", has_text="opportunity is open as a grid.")).to_be_visible(timeout=60000)
    catalog.close()

    # The grid: every opportunity (fewer than Rows to open), its choice columns as their labels.
    page.bring_to_front()
    dialog.get_by_role("button", name="Close").last.click()
    page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^opportunity$")).click()
    pane = page.locator(".pane:not([hidden])")
    expect(pane.locator(".ag-header-cell[col-id='salesstage']")).to_be_visible(timeout=30000)
    expect(pane.locator(".ag-row[row-index='0'] [col-id='salesstage']")).to_have_text("Develop")
    expect(pane.locator(".ag-row[row-index='0'] [col-id='statecode']")).to_have_text("Won")
    expect(page.locator(".tab-item[data-grid]", has_text="opportunity")).to_be_visible()
