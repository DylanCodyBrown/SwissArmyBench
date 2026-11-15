# ruff: noqa: F811
"""A Power BI dataset in a real browser, against the stand-in on this computer (tests/powerbi_standin.py;
no real tenant, made-up data): the connection is added with its form from a made-up key vault, its
catalog shows the tables with their measures, a table opens as a grid, and the dataset's relationships
are imported and drawn in the Diagram."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, expect

from tests import powerbi_standin as made_up
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import wait_until

VAULT_CODE = f"""values = {{
    "powerbi-tenant-id": "{made_up.TENANT}",
    "powerbi-client-id": "{made_up.CLIENT}",
    "powerbi-client-secret": "{made_up.SECRET}",
}}


def names():
    return list(values)


def get(name):
    return values[name]
"""


@pytest.fixture(scope="module", autouse=True)
def standin() -> Iterator[made_up.StandIn]:
    """The stand-in, and the two variables that point a connection's code at it, set before this
    module's server starts (its child processes read them)."""
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


def test_a_power_bi_dataset_is_added_from_the_vault_browsed_opened_and_its_relationships_drawn(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    call(server, "POST", "/connections", vault)
    page = open_grid(browser, orders_url)
    dialog = page.locator("dialog")
    # The form: the two ids, then the app registration, each of its three values an entry of the vault.
    page.locator(".app-row").get_by_role("button", name="Connections").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="Power BI dataset").click()
    expect(dialog.get_by_role("combobox", name="Sign in")).to_have_value("0")  # the app registration first
    dialog.get_by_role("textbox", name="Name").fill("Sales model")
    for label, value in (("Workspace id", made_up.WORKSPACE), ("Dataset id", made_up.DATASET)):
        box = dialog.get_by_role("textbox", name=label)
        box.fill(value)
        box.press("Tab")
    code = dialog.locator("textarea.connection-code")
    expect(code).to_have_value(re.compile(re.escape(f'dataset_id = "{made_up.DATASET}"')))
    for label, entry in (
        ("Tenant id", "powerbi-tenant-id"),
        ("Client id", "powerbi-client-id"),
        ("Client secret", "powerbi-client-secret"),
    ):
        row = dialog.locator(".connection-password").filter(has_text=f"{label} comes from")
        expect(row.get_by_role("combobox", name=f"Where {label} comes from")).to_have_value("vault")
        picker = row.get_by_role("combobox", name="Entry in the vault")
        expect(picker.locator("option", has_text=entry)).to_have_count(
            1, timeout=30000
        )  # read from the vault
        picker.select_option(entry)
        expect(code).to_have_value(re.compile(re.escape(f'secret("{entry.replace("-", "_")}")')))
    dialog.get_by_role("button", name="Test connection").click()
    expect(dialog.locator(".connection-result")).to_have_text(
        "It works: signed in and reached the dataset.", timeout=60000
    )
    token = next(r for r in standin.requests if r["what"] == "token")
    assert token["form"]["client_secret"] == made_up.SECRET and token["tenant"] == made_up.TENANT
    assert made_up.SECRET not in dialog.inner_text() and made_up.SECRET not in code.input_value()
    dialog.get_by_role("button", name="Save").click()
    row = dialog.locator(".connection-row", has_text="Sales model")
    expect(row.locator(".badge")).to_have_text("Power BI dataset")
    # Saved: its catalog loads itself.
    wait_until(lambda: any(c["name"] == "Sales model" for c in call(server, "GET", "/catalogs")["catalogs"]))

    # The catalog: the model, its tables, a table's columns and measures, and a first EVALUATE.
    catalog = page.context.new_page()
    catalog.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}&catalog=Sales%20model")
    catalog.wait_for_selector('[role="treeitem"]')

    def item(label: str) -> Any:
        return catalog.locator(
            '[role="treeitem"]', has=catalog.locator(f':scope > .node > .node-label:text-is("{label}")')
        )

    expect(item("Model")).to_have_attribute("aria-expanded", "true")
    expect(catalog.locator('[role="treeitem"][aria-level="2"] > .node > .node-label')).to_have_text(
        ["Customer", "Date", "Product", "Sales"]
    )
    item("Sales").locator(":scope > .node .node-label").click()
    detail = catalog.locator("#detail")
    expect(detail.locator("pre")).to_have_text("EVALUATE TOPN(100, 'Sales')")
    expect(detail.get_by_role("button", name="Copy the EVALUATE")).to_be_visible()
    expect(detail.locator("p.hint").first).to_have_text("Model in Sales model · 7 columns, 2 measures · DAX")
    measure = detail.locator(".columns-table").first.locator("tr", has_text="Total Sales")
    expect(measure.locator("td").nth(1)).to_have_text("measure, Decimal")
    expect(detail.locator(".preview-table tbody tr")).to_have_count(40, timeout=60000)  # its first rows

    # Open as grid; the toast offers the dataset's relationships, which then land in the model.
    detail.get_by_role("button", name="Open as grid").click()
    opened = catalog.locator(".toast", has_text="Sales is open as a grid.")
    expect(opened).to_be_visible(timeout=60000)
    opened.get_by_role("button", name="Import its relationships").click()
    expect(
        catalog.locator(".toast", has_text="4 relationships from Sales model are in the model.")
    ).to_be_visible(timeout=60000)
    for table in ("Customer", "Product", "Date"):
        call(server, "POST", f"/connections/{quote('Sales model')}/open", {"table": table})
    catalog.close()

    # The grid page: the table is a tab, with clean column names and a date read as a date.
    page.bring_to_front()
    dialog.get_by_role("button", name="Close").last.click()
    page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^Sales$")).click()
    pane = page.locator(".pane:not([hidden])")
    expect(pane.locator(".ag-header-cell[col-id='Order Date']")).to_be_visible(timeout=30000)
    expect(pane.locator(".ag-row[row-index='0'] [col-id='Order Date']")).to_have_text("2026-01-02")
    expect(pane.locator(".ag-row[row-index='0'] [col-id='Amount']")).to_have_text("24.5")

    # The Diagram draws the dataset's joins: four tables, the inactive one said so.
    page.locator(".tab-erd").click()
    erd = page.locator("#erd-view")
    expect(erd.locator(".erd-diagram svg")).to_be_visible(timeout=60000)
    drawn = erd.locator(".erd-diagram svg")
    for table in ("Sales", "Customer", "Product", "Date"):
        expect(drawn.get_by_text(table, exact=True).first).to_be_visible()
    expect(drawn.get_by_text("inactive", exact=True)).to_be_visible()
    expect(drawn.get_by_text("filters both ways", exact=True)).to_be_visible()
    assert len(call(server, "GET", "/relationships")["relationships"]) == 4
