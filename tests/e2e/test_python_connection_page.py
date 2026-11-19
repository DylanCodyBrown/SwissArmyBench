# ruff: noqa: F811
"""A connection from your own Python in a real browser, over the tiny made-up web service
(tests/orders_service.py; made-up data, a made-up API key in a made-up vault): the connection is added
with its form (the three code boxes, one variable a plain value and one an entry of the vault), Test
shows the first table's rows, it is saved, its catalog shows the tables, and a table opens as a grid
with its note."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, demo_frame, grid_of, open_grid, server  # noqa: F401
from tests.e2e.test_workbench_page import wait_until
from tests.orders_service import API_KEY, VAULT_CODE, Service

# Typed into the boxes in place of the starter's: a DataFrame for the catalog, and a read of its own.
# (No indented lines: the editor indents typed lines by itself, as it does for a person.)
TABLES = """import pandas as pd

found = [(t["name"], c["name"], c["type"]) for t in conn.get("/tables") for c in t["columns"]]
frame = pd.DataFrame(found, columns=["table", "column", "type"])
frame.assign(schema="api", description="made up")"""
READ = """page = conn.get("/tables/" + table + "/rows" + ("?limit=" + str(limit) if limit else ""))
(page["rows"], page["total"])"""


@pytest.fixture(scope="module")
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


@pytest.fixture
def january_url(server: dict[str, Any]) -> Iterator[str]:
    """A grid to start from, under a name the service's own tables do not have."""
    url = push_client.push(demo_frame(40), name="january", new_grid=True)
    yield url
    call(server, "DELETE", f"/grids/{grid_of(url)}")


def type_into(page: Page, box: Locator, code: str) -> None:
    """Replace a code box's text, as typing does (the Workbench's editor)."""
    box.locator(".monaco-editor").click()
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(code)


def test_a_python_connection_is_added_tested_saved_browsed_and_opened(
    browser: Browser, january_url: str, server: dict[str, Any], service: Service
) -> None:
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    mapping = [{"env": "OTHER", "secret": "other"}, {"env": "ORDERS_API_KEY", "secret": "orders-api-key"}]
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_mapping": mapping}
    call(server, "POST", "/connections", vault)
    if any(v["name"] == "ORDERS_API_URL" for v in call(server, "GET", "/variables")["variables"]):
        call(server, "DELETE", "/variables/ORDERS_API_URL")
    page = open_grid(browser, january_url)
    dialog = page.locator(".area-page[data-page='connections']")  # the Connections page (2026-11-16)

    # Add connection: its own group, and a form of three code boxes.
    page.locator(".nav-rail [data-area='connections']").click()
    page.get_by_role("button", name="Add connection").click()
    expect(dialog.locator("h3", has_text="Your own code")).to_be_visible()
    page.locator(".connection-type", has_text="Python (your own code)").click()
    boxes = dialog.locator(".python-box")
    expect(boxes.locator("h4")).to_have_text(["Connect", "List the tables", "Read a table"])
    expect(boxes.locator(".monaco-editor")).to_have_count(3, timeout=30000)  # the Workbench's editor
    expect(boxes.nth(0).locator(".view-lines")).to_contain_text('os.environ["ORDERS_API_KEY"]')
    dialog.get_by_role("textbox", name="Name").fill("Orders API")
    type_into(page, boxes.nth(1), TABLES)
    type_into(page, boxes.nth(2), READ)

    # The variables the code reads, found by themselves, each with what it reads here (12.7): no source
    # pickers (the Variables page keeps where a value comes from); one not set is the one error, Set it.
    variables = dialog.locator(".python-variable")
    expect(variables.locator("code")).to_have_text(["ORDERS_API_URL", "ORDERS_API_KEY"])
    expect(dialog.locator(".python-variable select")).to_have_count(0)
    expect(variables.nth(0).locator(".error-note")).to_contain_text(
        "ORDERS_API_URL is not set on this computer"
    )
    expect(variables.nth(1).locator(".variable-preview")).to_have_text("••••••••")  # the vault's entry
    variables.nth(0).get_by_role("button", name="Set it").click()
    form = page.locator("dialog .variables-form")
    expect(form.get_by_label("Name")).to_have_value("ORDERS_API_URL")
    form.get_by_label("Value").fill(service.url)
    page.locator("dialog").get_by_role("button", name="Add").click()
    expect(variables.nth(0).locator(".variable-preview")).to_have_text(service.url)
    dialog.get_by_role("spinbutton", name="Rows to open").fill("10")

    # Test: Connect, List the tables, the first table's first rows.
    dialog.get_by_role("button", name="Test connection").click()
    result = dialog.locator(".connection-result")
    expect(result.locator(".status-ok")).to_have_text("It works: 2 tables, 3 columns.", timeout=60000)
    expect(result.locator("p.hint")).to_have_text("api.orders: the first 20 of 30 rows")
    expect(result.locator(".connection-preview th")).to_have_text(["order_id", "amount"])
    expect(result.locator(".connection-preview tbody tr")).to_have_count(20)
    assert API_KEY not in dialog.inner_text()

    # Save: one connection, listed under its own heading; what was typed is what was saved.
    dialog.get_by_role("button", name="Save").click()
    row = dialog  # its detail
    expect(row.locator(".connection-config")).to_contain_text("Python (your own code)")
    saved = call(server, "GET", "/connections/Orders%20API")
    assert saved["catalog"]["command"] == TABLES and saved["read"]["command"] == READ
    assert saved["row_limit"] == 10 and not saved.get("variables")
    assert API_KEY not in str(saved)
    # Its catalog loads itself; the row's Test shows the rows under it.
    wait_until(lambda: any(c["name"] == "Orders API" for c in call(server, "GET", "/catalogs")["catalogs"]))
    row.locator(".connection-detail-tools").get_by_role("button", name="Test", exact=True).click()
    expect(row.locator(".connection-tested tbody tr")).to_have_count(20, timeout=60000)

    # The catalog (the blades page's catalog panel went, 2026-11-17: its routes, and the Connections
    # page's tree): a table's columns with their descriptions; Open from the tree.
    listed = call(server, "GET", "/catalogs/Orders%20API/tables?schema=api")["tables"]
    assert [t["table"] for t in listed] == ["clients", "orders"]
    columns = call(server, "GET", "/catalogs/Orders%20API/columns?schema=api&table=orders")["columns"]
    amount = next(c for c in columns if c["column"] == "amount")
    assert amount["type"] == "number" and amount["description"] == "made up"
    orders = row.locator(".connection-tables .conn-tree-table[data-table='orders']")
    expect(orders).to_be_visible(timeout=60000)
    # Open as grid: the first Rows to open rows, the note, and the rest one click away.
    orders.get_by_role("button", name="Open").click()
    page.bring_to_front()
    page.locator(".nav-rail [data-area='grids']").click()  # the page makes way for the grids
    page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^orders$")).click()
    note = page.locator(".opened-note")
    expect(note).to_contain_text("First 10 of 30 rows", timeout=30000)
    pane = page.locator(".pane:not([hidden])")
    expect(pane.locator(".ag-row[row-index='0'] [col-id='amount']")).to_have_text("2.5")
    note.get_by_role("button", name="Load all rows").click()
    expect(page.locator(".opened-note")).to_have_count(0, timeout=60000)
    expect(pane.locator(".ag-row[row-index='29'] [col-id='order_id']")).to_have_text("30", timeout=30000)
