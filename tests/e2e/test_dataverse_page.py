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
from tests.e2e.test_ui import browser, call, not_now, open_grid, orders_url, server  # noqa: F401
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
    dialog = page.locator(".area-page[data-page='connections']")  # the Connections page (2026-11-16)

    # The form: the environment's address and the sign-in; the app registration comes first (it runs on a
    # Function App or a hosted Streamlit app too; as you, this machine's only, last: the owner, 2026-11-17).
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").first.click()
    tile = page.locator(".connection-type", has_text="Dataverse")
    expect(tile.locator("svg")).to_have_count(1)  # its own icon
    tile.click()
    not_now(page)  # its SQL endpoint needs python-tds, which this Python may lack
    sign_in = dialog.get_by_role("combobox", name="Sign in")
    expect(sign_in).to_have_value("0")
    expect(sign_in.locator("option")).to_have_text(
        [
            "App registration, its secret from a key vault",
            "Managed identity (in Azure: a Function App, App Service or VM)",
            "As you (Azure command line or browser)",
        ]
    )
    expect(dialog.locator(".sign-in-local .local-only")).to_have_count(0)
    sign_in.select_option("2")  # as you: said, amber
    expect(dialog.locator(".sign-in-local .local-only")).to_contain_text(
        "Only works on your machine: it signs in as you"
    )
    not_now(page)  # as you needs azure-identity too
    sign_in.select_option("0")
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
    # One box (12.7): the vault's secret by its variable's name, a dollar-brace; no source or entry pickers.
    expect(dialog.get_by_role("combobox", name="Where Client secret comes from")).to_have_count(0)
    secret_box = dialog.get_by_label("Client secret", exact=True)
    secret_box.fill("${crm_client_secret}")
    secret_box.press("Tab")
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
    typed = code.input_value()
    dialog.get_by_role("button", name="Save").click()
    saved = dialog.locator(".connection-config")  # its detail
    expect(saved).to_contain_text("Dataverse")
    expect(saved.locator(".connection-in-code")).to_contain_text('sab.read("Sales CRM", table)')
    # The form saves it on the SQL endpoint (the owner, 2026-11-17), which needs python-tds and a real TDS
    # endpoint (tests/test_connection_kinds.py stands in for it at its cursor). The rest of this test is a
    # connection saved for the Web API before then: it keeps working, and its detail offers the switch.
    old: dict[str, Any] = {
        "name": "Sales CRM",
        "kind": "sql",
        "template": "dataverse",
        "dialect": "dataverse",
        "code": typed,
    }
    old |= {"variable": "conn", "catalog": {"language": "python", "command": "catalog = conn.catalog()"}}
    call(server, "PUT", "/connections/Sales%20CRM", old)
    page.locator(".nav-rail [data-area='connections']").click()
    dialog.locator(".connection-card[data-connection='Sales CRM']").click()
    expect(dialog.get_by_role("button", name="Web API (switch to the SQL endpoint)")).to_be_visible()
    wait_until(lambda: any(c["name"] == "Sales CRM" for c in call(server, "GET", "/catalogs")["catalogs"]))

    # The catalog (the blades page's catalog panel went, 2026-11-17: read through its routes, and the
    # Connections page's tree): one schema, its tables; a display name where it says more than the name.
    schemas = call(server, "GET", "/catalogs/Sales%20CRM/schemas")["schemas"]
    assert [x["schema"] for x in schemas] == ["dbo"]
    listed = call(server, "GET", "/catalogs/Sales%20CRM/tables?schema=dbo")["tables"]
    assert [t["table"] for t in listed] == ["account", "contact", "opportunity", "systemuser"]
    assert {t["table"]: t.get("title") for t in listed}["systemuser"] == "User"
    columns = call(server, "GET", "/catalogs/Sales%20CRM/columns?schema=dbo&table=opportunity")["columns"]
    stage = next(c for c in columns if c["column"] == "salesstage")
    assert stage["type"] == "Picklist" and stage["description"] == "Sales Stage"
    tree = dialog.locator(".connection-tables")
    opportunity = tree.locator(".conn-tree-table[data-table='opportunity']")
    expect(opportunity).to_be_visible(timeout=60000)
    opportunity.get_by_role("button", name="Open").click()
    expect(page.locator(".toast", has_text="opportunity")).to_be_visible(timeout=60000)

    # The grid: every opportunity (fewer than Rows to open), its choice columns as their labels.
    page.bring_to_front()
    page.locator(".nav-rail [data-area='grids']").click()  # the page makes way for the grids
    page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^opportunity$")).click()
    pane = page.locator(".pane:not([hidden])")
    expect(pane.locator(".ag-header-cell[col-id='salesstage']")).to_be_visible(timeout=30000)
    expect(pane.locator(".ag-row[row-index='0'] [col-id='salesstage']")).to_have_text("Develop")
    expect(pane.locator(".ag-row[row-index='0'] [col-id='statecode']")).to_have_text("Won")
    expect(page.locator(".tab-item[data-grid]", has_text="opportunity")).to_be_visible()
