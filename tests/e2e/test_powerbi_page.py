# ruff: noqa: F811
"""A Power BI workspace in a real browser, against the stand-in on this computer (tests/powerbi_standin.py;
no real tenant, made-up data). The connection is per workspace (the owner, 2026-11-15): its form asks
for the workspace and the sign-in, never a dataset; the catalog shows the workspace's datasets, each
with its tables (one that cannot be read is marked on itself); a table of the second dataset opens as a
grid; one dataset's relationships are imported and drawn in the Diagram; and a DAX cell in the
Workbench picks a dataset, completes DAX and the dataset's names, and runs."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests import powerbi_standin as made_up
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import open_workbench, wait_until

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

DATASETS = ["Finance/Broken model", "Finance/Budget model", "Finance/Sales model"]


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


def test_a_power_bi_workspace_is_added_browsed_opened_its_relationships_drawn_and_queried_in_a_dax_cell(
    browser: Browser, orders_url: str, server: dict[str, Any], standin: made_up.StandIn
) -> None:
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    call(server, "POST", "/connections", vault)
    page = open_grid(browser, orders_url)
    dialog = page.locator("dialog")

    # The form: the workspace's id and the sign-in. No dataset is asked for.
    page.locator(".app-row").get_by_role("button", name="Connections").click()
    page.get_by_role("button", name="Add connection").click()
    page.locator(".connection-type", has_text="Power BI workspace").click()
    expect(dialog.get_by_role("combobox", name="Sign in")).to_have_value("0")  # the app registration first
    dialog.get_by_role("textbox", name="Name").fill("Finance")
    box = dialog.get_by_role("textbox", name="Workspace id")
    box.fill(made_up.WORKSPACE)
    box.press("Tab")
    expect(dialog.get_by_role("textbox", name="Dataset id")).to_have_count(0)
    code = dialog.locator("textarea.connection-code")
    expect(code).to_have_value(re.compile(re.escape(f'workspace_id = "{made_up.WORKSPACE}"')))
    assert "dataset_id" not in code.input_value()
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
        "It works: signed in and found 3 datasets.", timeout=60000
    )
    token = next(r for r in standin.requests if r["what"] == "token")
    assert token["form"]["client_secret"] == made_up.SECRET and token["tenant"] == made_up.TENANT
    assert made_up.SECRET not in dialog.inner_text() and made_up.SECRET not in code.input_value()
    dialog.get_by_role("button", name="Save").click()
    row = dialog.locator(".connection-row", has_text="Finance")
    expect(row.locator(".badge")).to_have_text("Power BI workspace")
    # Relationships are a dataset's: the row offers none (the catalog does, on each dataset).
    expect(row.get_by_role("button", name="Import its relationships")).to_have_count(0)
    # Saved: its catalog loads itself.
    wait_until(lambda: any(c["name"] == "Finance" for c in call(server, "GET", "/catalogs")["catalogs"]))

    # The catalog: the workspace's datasets, each with its tables; the one that could not be read is
    # marked on itself only.
    catalog = page.context.new_page()
    catalog.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}&catalog=Finance")
    catalog.wait_for_selector('[role="treeitem"]')

    def item(label: str, level: int = 1) -> Any:
        return catalog.locator(
            f'[role="treeitem"][aria-level="{level}"]',
            has=catalog.locator(f':scope > .node > .node-label:text-is("{label}")'),
        )

    expect(catalog.locator('[role="treeitem"][aria-level="1"] > .node > .node-label')).to_have_text(
        ["Broken model", "Budget model", "Sales model"]
    )
    broken = item("Broken model")
    expect(broken.locator(".node-error")).to_have_attribute(
        "title", re.compile(r"^Could not be read: .*being refreshed")
    )
    expect(catalog.locator(".node-error")).to_have_count(1)  # the other two are not marked
    assert broken.get_attribute("aria-expanded") is None  # nothing under it to open
    broken.locator(":scope > .node .node-label").click()
    detail = catalog.locator("#detail")
    expect(detail.locator(".status-error")).to_contain_text("The dataset is being refreshed")
    expect(detail.get_by_role("button", name="Import its relationships")).to_have_count(0)
    # The second dataset: its own tables (a Date of its own), and its page.
    budget = item("Budget model")
    budget.locator(":scope > .node .node-label").click()  # its page, and its tables under it
    expect(detail.locator("p.hint").first).to_have_text("Dataset in Finance · DAX")
    expect(detail.get_by_role("button", name="Import its relationships")).to_be_visible()
    expect(budget).to_have_attribute("aria-expanded", "true")
    expect(budget.locator('[role="treeitem"][aria-level="2"] > .node > .node-label')).to_have_text(
        ["Budget", "Date", "Department"]
    )
    item("Budget", 2).locator(":scope > .node .node-label").click()
    expect(detail.locator("pre")).to_have_text("EVALUATE TOPN(100, 'Budget')")
    expect(detail.locator("p.hint").first).to_have_text(
        "Budget model in Finance · 4 columns, 1 measure · DAX"
    )
    measure = detail.locator(".columns-table").first.locator("tr", has_text="Total Planned")
    expect(measure.locator("td").nth(1)).to_have_text("measure, Decimal")
    expect(detail.locator(".preview-table tbody tr")).to_have_count(24, timeout=60000)  # its first rows

    # Open as grid, from the second dataset; the toast offers that dataset's relationships.
    detail.get_by_role("button", name="Open as grid").click()
    opened = catalog.locator(".toast", has_text="Budget is open as a grid.")
    expect(opened).to_be_visible(timeout=60000)
    assert standin.queries("Budget model")[-2] == "EVALUATE TOPN(10000, 'Budget')"
    opened.get_by_role("button", name="Import its relationships").click()
    expect(
        catalog.locator(".toast", has_text="2 relationships from Budget model are in the model.")
    ).to_be_visible(timeout=60000)
    # Both datasets have a Date: this one opens under its dataset's name too (the menu on its node).
    item("Date", 2).locator(":scope > .node").click(button="right")
    catalog.get_by_role("menuitem", name="Open as grid").click()
    expect(catalog.locator(".toast", has_text="Budget_model_Date is open as a grid.")).to_be_visible(
        timeout=60000
    )
    call(server, "POST", "/connections/Finance/open", {"schema": "Budget model", "table": "Department"})
    catalog.close()

    # The grid page: the second dataset's table is a tab, a date read as a date.
    page.bring_to_front()
    dialog.get_by_role("button", name="Close").last.click()
    page.locator(".tab-item[data-grid]").filter(has_text=re.compile("^Budget$")).click()
    pane = page.locator(".pane:not([hidden])")
    expect(pane.locator(".ag-header-cell[col-id='Planned']")).to_be_visible(timeout=30000)
    expect(pane.locator(".ag-row[row-index='0'] [col-id='Month']")).to_have_text("2026-02-01")
    expect(pane.locator(".ag-row[row-index='0'] [col-id='Planned']")).to_have_text("1250")

    # The Diagram draws that one dataset's joins, its Date under the name its grid has.
    page.locator(".tab-erd").click()
    erd = page.locator("#erd-view")
    expect(erd.locator(".erd-diagram svg")).to_be_visible(timeout=60000)
    drawn = erd.locator(".erd-diagram svg")
    for name in ("Budget", "Department", "Budget_model_Date"):
        expect(drawn.get_by_text(name, exact=True).first).to_be_visible()
    model = call(server, "GET", "/relationships")
    assert len(model["relationships"]) == 2  # the Sales model's were not asked for
    assert model["tables"]["Budget"]["source"] == "Finance/Budget model (Power BI)"

    # The Workbench: a DAX cell. Its picker lists only the workspace's datasets; a SQL cell's, none.
    workbench = open_workbench(page)
    workbench.get_by_role("button", name="New notebook").first.click()
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.get_by_label("Cell kind").select_option("sql")
    assert not any(
        "Finance" in o for o in cell.get_by_label("Connection").locator("option").all_inner_texts()
    )
    cell.get_by_label("Cell kind").select_option("dax")
    picker = cell.get_by_label("Dataset")
    expect(picker.locator("option")).to_have_text(DATASETS)
    picker.select_option("Finance/Sales model")
    # Completion: DAX's words, then that dataset's tables, columns and measures. No SQL words.
    cell.locator(".monaco-editor").click()
    suggest = workbench.locator(".suggest-widget .monaco-list-row")
    workbench.keyboard.type("EVAL")
    workbench.keyboard.press("Control+Space")
    expect(suggest.filter(has_text="EVALUATE").first).to_be_visible(timeout=10000)
    workbench.keyboard.press("Enter")
    workbench.keyboard.type(" SUMMARIZECOLUMNS('Cust")
    workbench.keyboard.press("Control+Space")
    expect(suggest.filter(has_text="Customer").first).to_be_visible(timeout=10000)
    expect(suggest.filter(has_text="Budget")).to_have_count(0)  # the other dataset's tables are not offered
    workbench.keyboard.press("Enter")
    workbench.keyboard.type("[Reg")
    workbench.keyboard.press("Control+Space")
    expect(suggest.filter(has_text="Region").first).to_be_visible(timeout=10000)
    workbench.keyboard.press("Enter")
    workbench.keyboard.type(', "Total Sales", [Tot')
    workbench.keyboard.press("Control+Space")
    expect(suggest.filter(has_text="Total Sales").first).to_be_visible(timeout=10000)
    workbench.keyboard.press("Enter")
    workbench.keyboard.press("Control+End")
    workbench.keyboard.type(" -- WHER")
    workbench.keyboard.press("Control+Space")
    workbench.wait_for_timeout(500)
    expect(suggest.filter(has_text="WHERE")).to_have_count(0)  # SQL's word; SELECTCOLUMNS is DAX's
    workbench.keyboard.press("Escape")
    for _ in " -- WHER":
        workbench.keyboard.press("Backspace")
    workbench.keyboard.press("Control+Enter")
    frame = cell.frame_locator("iframe.wb-html")
    expect(frame.locator("th", has_text="Total Sales")).to_be_visible(timeout=90000)
    expect(frame.locator("tbody tr")).to_have_count(4)  # North, South, East and no region
    assert standin.queries("Sales model")[-1] == (
        """EVALUATE SUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales])"""
    )

    # The agent does the same through the window: a DAX cell on the other dataset, run, and read.
    def window(command: str, **args: Any) -> Any:
        return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)[
            "result"
        ]

    added = window("cell.addDax", dataset="Finance/Budget model", source="EVALUATE TOPN(3, 'Budget')")
    assert added["dataset"] == "Finance/Budget model"
    second = workbench.locator(".wb-cell").nth(1)
    expect(second.get_by_label("Dataset")).to_have_value("Finance/Budget model")
    assert window("run.cell", index=added["index"]) is True  # its place among every cell, the tables' too
    expect(second.frame_locator("iframe.wb-html").locator("tbody tr")).to_have_count(3, timeout=90000)
    read = window("doc.read")["cells"]
    assert [(c["kind"], c["connection"]) for c in read if c["kind"] == "dax"] == [
        ("dax", "Finance/Sales model"),
        ("dax", "Finance/Budget model"),
    ]
    # Jupyter's key: X makes the selected cell a DAX cell (S: SQL).
    workbench.get_by_role("button", name="Python", exact=True).click()
    third = workbench.locator(".wb-cell").nth(2)
    expect(third.locator(".monaco-editor")).to_be_visible(timeout=20000)
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("x")
    expect(third.get_by_label("Cell kind")).to_have_value("dax")
    expect(third.get_by_label("Dataset")).to_have_value(DATASETS[0])
