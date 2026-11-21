# ruff: noqa: F811
"""The built-in starter pack (docs/ideas.md, the starter pack), in a real browser: the pack in the blade
list, grouped by family; a starter copied as your own; a DAX snippet dragged onto a DAX cell, its form
prefilled from the cell's dataset (the Power BI stand-in), and its text inserted; one dropped on a cell
of another language refused; an HTML KPI row inserted from an HTML cell's menu and drawn; a Streamlit
piece dropped into a notebook naming its cell, listed by name in the Streamlit cells pane and dragged
onto a canvas; and the user guide's page of five pieces, played live (with Streamlit).

With SWISSARMYBENCH_SHOTS set to a folder, the tests also save screenshots there (2x). Made-up data
only."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from swissarmybench.server.blade_templates import POWERBI_VAULT
from tests import powerbi_standin as made_up
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server, steady_box  # noqa: F401
from tests.e2e.test_workbench_page import wait_until
from tests.e2e.workbench_helpers import open_window, shot

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
ORDERS = pd.DataFrame(
    {
        "region": ["North", "South", "East", "West"] * 6,
        "product": ["Widget", "Gadget", "Gizmo"] * 8,
        "order_date": pd.date_range("2026-01-01", periods=24, freq="5D"),
        "amount": [round(20 + (i * 13.7) % 180, 2) for i in range(24)],
    }
)


@pytest.fixture(scope="module", autouse=True)
def standin() -> Iterator[made_up.StandIn]:
    """Power BI, stood in for on this computer, before this module's server starts."""
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


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:
    close_tables(server)
    push_client.push(ORDERS, name="orders", new_grid=True)
    yield
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def blades(page: Page) -> Locator:
    """The Workbench's blade list (+ Blade, in the Data Explorer's head), opened when it is not."""
    if not page.locator(".wb-flyout:not([hidden])").count():
        if not page.locator(".wb-explorer:not([hidden])").count():
            page.keyboard.press("Control+Shift+E")
        page.get_by_role("button", name="Add a blade").click()
    return page.locator(".wb-flyout .blade-list")


def family(listed: Locator, name: str) -> None:
    toggle = listed.locator(".starter-family", has_text=name)
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def finance_workspace(server: dict[str, Any]) -> None:
    """A Power BI workspace connection on the stand-in (its app registration from a vault), loaded."""
    if any(c["name"] == "Finance" for c in call(server, "GET", "/catalogs")["catalogs"]):
        return
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    call(server, "POST", "/connections", vault)
    code = POWERBI_VAULT.replace("my-workspace-id", made_up.WORKSPACE)
    for secret, entry in (
        ("tenant id", "powerbi-tenant-id"),
        ("client id", "powerbi-client-id"),
        ("client secret", "powerbi-client-secret"),
    ):
        body = {"code": code, "secret": secret, "from": "vault", "vault": "Team vault", "vault_secret": entry}
        code = call(server, "POST", "/connections/source", body)["code"]
    template = next(t for t in call(server, "GET", "/blades/templates")["templates"] if t["id"] == "powerbi")
    body = {"name": "Finance", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
    call(server, "POST", "/connections", body | {"variable": "conn", "catalog": template["catalog"]})
    call(server, "POST", "/blades/Finance/refresh", {})
    wait_until(lambda: any(c["name"] == "Finance" for c in call(server, "GET", "/catalogs")["catalogs"]))


def test_the_pack_is_in_the_blade_list_by_family_and_a_starter_copies_as_your_own(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = browser.new_context(viewport={"width": 1400, "height": 950}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}")
    listed = page.locator(".blade-list")
    expect(listed.locator(".blade-group", has_text="Starters")).to_be_visible(timeout=20000)
    # Each family folds to one line with its count, in the pack's order.
    expect(listed.locator(".starter-family")).to_have_text(
        [
            "Power BI13",
            "Dataverse2",
            "SharePoint5",
            "Excel12",
            "Files3",
            "DAX11",
            "HTML10",
            "Markdown10",
            "Streamlit29",
            "Controllers5",
            "Text and layout9",
            "Components9",
            "Write74",  # the lakes' and SharePoint's 14 (branch lakes-sharepoint)
        ]
    )
    expect(listed.locator(".starter-item")).to_have_count(0)
    family(listed, "Streamlit")
    listed.evaluate("list => (list.scrollTop = 0)")
    shot(page, "1-the-pack-in-the-blade-list")
    listed.locator(".starter-family", has_text="Streamlit").click()  # folded again
    family(listed, "Power BI")
    family(listed, "Excel")
    expect(listed.locator(".starter-item")).to_have_count(25)
    expect(listed.locator(".starter-item").first.locator(".blade-kind")).to_have_text("Python")
    # A search opens the families it finds something in.
    page.get_by_role("searchbox", name="Search blades").fill("toast")
    expect(listed.locator(".starter-item")).to_have_text(["StreamlitStreamlit toast"])
    page.get_by_role("searchbox", name="Search blades").fill("")
    # A starter opens read-only; Copy as your own makes the user's copy and opens it.
    listed.locator(".starter-item", has_text="Power BI refresh dataset").locator(".blade-name").click()
    detail = page.locator("#detail")
    expect(detail.get_by_text("Power BI starter: read-only")).to_be_visible()
    expect(detail.locator(".blade-code .monaco-editor")).to_be_visible(timeout=20000)  # read-only
    shot(page, "2-a-power-bi-action")
    detail.get_by_role("button", name="Copy as your own").click()
    expect(detail.locator("h2")).to_have_text("Blade: Power BI refresh dataset copy")
    expect(detail.get_by_text("starter: read-only")).to_have_count(0)
    expect(detail.get_by_role("button", name="Save", exact=True)).to_be_visible()
    mine = [b["name"] for b in call(server, "GET", "/blades")["blades"]]
    assert "Power BI refresh dataset copy" in mine
    expect(
        listed.locator(".blade-item:not(.starter-item)", has_text="Power BI refresh dataset copy")
    ).to_be_visible()
    call(server, "DELETE", "/blades/Power%20BI%20refresh%20dataset%20copy")
    page.close()


def test_a_dax_snippet_dragged_onto_a_dax_cell_fills_its_form_from_the_dataset(
    browser: Browser, server: dict[str, Any]
) -> None:
    finance_workspace(server)
    close_tables(server)
    workbench = open_window(browser, server)
    workbench.get_by_role("button", name="Start a notebook").click()
    expect(workbench.locator(".wb-cell .monaco-editor").first).to_be_visible(timeout=20000)
    window(server, "cell.addDax", dataset="Finance/Sales model")
    dax = workbench.locator(".wb-cell.kind-dax")
    expect(dax.locator(".monaco-editor")).to_be_visible(timeout=20000)
    listed = blades(workbench)
    family(listed, "DAX")
    item = listed.locator(".starter-item", has_text="DAX year to date")
    expect(item).to_be_visible()
    steady_box(workbench, item)  # the flyout has finished sliding in
    form = workbench.locator("dialog[open]")
    for attempt in range(2):  # a drag that started before the editor took drops is tried once more
        item.drag_to(dax.locator(".monaco-editor"))
        try:
            expect(form.locator("h2")).to_have_text("DAX year to date", timeout=20000)
            break
        except AssertionError:
            if attempt:
                raise
    # Prefilled from the dataset's catalog: a measure, the table it is on, the date table and its date.
    measure = form.get_by_label("Measure", exact=True)
    expect(measure).to_have_value("Customer Count", timeout=20000)
    expect(form.get_by_label("Table", exact=True)).to_have_value("Customer")
    expect(form.get_by_label("Date table", exact=True)).to_have_value("Date")
    expect(form.get_by_label("Date column", exact=True)).to_have_value("Date")
    expect(form.locator("datalist").first.locator("option")).to_have_count(3)  # the dataset's measures
    measure.fill("Total Sales")  # another measure: the table follows it
    expect(form.get_by_label("Table", exact=True)).to_have_value("Sales")
    shot(workbench, "4a-a-dax-snippets-form")
    form.get_by_role("button", name="Insert").click()
    expect(form).to_have_count(0)
    expect(dax.locator(".view-lines")).to_contain_text("TOTALYTD ( [Total Sales], 'Date'[Date] )")
    cells = window(server, "doc.read")["cells"]
    source = next(c["source"] for c in cells if c["kind"] == "dax")
    assert "MEASURE 'Sales'[Total Sales YTD] =" in source and "<<" not in source
    shot(workbench, "4b-the-inserted-dax")
    # A snippet of another language is refused, with a short message; the cell stays as it was.
    family(listed if workbench.locator(".wb-flyout:not([hidden])").count() else blades(workbench), "HTML")
    blades(workbench).locator(".starter-item", has_text="HTML KPI tile").drag_to(
        dax.locator(".monaco-editor")
    )
    expect(workbench.locator(".error-note")).to_contain_text(
        re.compile("An HTML snippet goes in an HTML cell")
    )
    assert next(c["source"] for c in window(server, "doc.read")["cells"] if c["kind"] == "dax") == source
    workbench.close()


def test_python_starters_dropped_on_a_cell_are_each_a_line_of_their_own(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The test bed's use case 4: three Excel starters dragged onto a cell came out as one line,
    `copy_template = sab.blade("Excel copy template")$0set_values = sab.write_table = ...`: Monaco's
    own drop left a snippet's `$0` behind, and the next drop landed inside the line before."""
    close_tables(server)
    workbench = open_window(browser, server)
    workbench.get_by_role("button", name="Start a notebook").click()
    editor = workbench.locator(".wb-cell").first.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    for name in ("Excel copy template", "Excel set cell values", "Excel write table"):
        listed = blades(workbench)
        family(listed, "Excel")
        listed.locator(".starter-item", has_text=name).drag_to(editor.locator(".view-lines"))
    expected = (
        'copy_template = sab.blade("Excel copy template")\n'
        'set_values = sab.blade("Excel set cell values")\n'
        'write_table = sab.blade("Excel write table")'
    )
    wait_until(lambda: window(server, "doc.read")["cells"][-1]["source"] == expected)
    workbench.close()


def test_a_pieces_column_is_never_an_identifier_when_another_fits(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The test bed's use case 11: a selectbox filter on invoices offered invoice_id, the first column."""
    close_tables(server)
    made_up = pd.DataFrame(
        {
            "invoice_id": ["A-1", "A-2"],
            "customerId": [7, 8],
            "region": ["North", "South"],
            "amount": [5.0, 7.5],
        }
    )
    push_client.push(made_up, name="statements", new_grid=True)
    workbench = open_window(browser, server)
    workbench.get_by_role("button", name="Start a notebook").click()
    editor = workbench.locator(".wb-cell").first.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    for name, label, column in (
        ("Streamlit selectbox filter", "Column", "region"),
        ("Streamlit metric row", "Value column", "amount"),
    ):
        listed = blades(workbench)
        family(listed, "Streamlit")
        listed.locator(".starter-item", has_text=name).drag_to(editor)
        form = workbench.locator("dialog[open]")
        expect(form.get_by_label(label, exact=True)).to_have_value(column, timeout=20000)
        form.get_by_role("button", name="Cancel").click()
    workbench.close()
    close_tables(server)


def test_an_html_kpi_row_is_inserted_from_the_cells_menu_and_drawn(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    workbench = open_window(browser, server)
    workbench.get_by_role("button", name="Start a notebook").click()
    expect(workbench.locator(".wb-cell .monaco-editor").first).to_be_visible(timeout=20000)
    window(server, "html.add")
    cell = workbench.locator(".wb-cell.kind-html")
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.get_by_role("button", name="More actions").click()
    workbench.get_by_role("menuitem", name="Insert a snippet…").click()
    picker = workbench.locator("dialog[open]")
    expect(picker.locator("h2")).to_have_text("Insert an HTML snippet")
    picker.get_by_role("searchbox", name="Search snippets").fill("kpi row")
    picker.locator(".snippet-choice", has_text="HTML KPI row").click()
    form = workbench.locator("dialog[open]")
    expect(form.locator("h2")).to_have_text("HTML KPI row")
    expect(form.get_by_label("First label", exact=True)).to_have_value("Revenue")
    form.get_by_label("Second value", exact=True).fill("3,481")
    form.get_by_role("button", name="Insert").click()
    # Drawn in the cell's walled-off frame, with nothing from the internet.
    design = cell.frame_locator(".wb-design-frame")
    expect(design.get_by_text("Revenue")).to_be_visible(timeout=20000)
    expect(design.get_by_text("3,481")).to_be_visible()
    shot(workbench, "5-an-html-kpi-row-drawn")
    workbench.close()


def test_in_a_script_a_snippet_is_a_cell_of_its_own(
    browser: Browser, server: dict[str, Any], orders: None
) -> None:
    workbench = open_window(browser, server)
    window(server, "file.newScript")
    expect(workbench.locator(".wb-script-editor .monaco-editor")).to_be_visible(timeout=20000)
    window(
        server,
        "snippet.insert",
        name="Streamlit toggle filter",
        values={"table": "orders", "flag column": "region"},
    )
    window(server, "snippet.insert", name="HTML badge", values={})
    text = window(server, "doc.read")["text"]
    assert re.search(r"^# %% (\[\d+\] )?Only shipped switch$", text, re.MULTILINE), text
    assert "only_region = orders[" in text and re.search(r"^# %% (\[\d+\] )?\[html\]", text, re.MULTILINE)
    workbench.close()


# The user guide's page (docs/user-guide.md, "Learning Streamlit with the starter pieces").
GUIDE: list[tuple[str, dict[str, str]]] = [
    ("Streamlit selectbox filter", {"table": "orders", "column": "region", "name": "by_region"}),
    ("Streamlit date range filter", {"table": "by_region", "date column": "order_date", "name": "in_dates"}),
    ("Streamlit metric row", {"table": "in_dates", "value column": "amount"}),
    ("Streamlit bar chart", {"table": "in_dates", "x column": "product", "y column": "amount"}),
    (
        "Streamlit formatted table",
        {"table": "in_dates", "value column": "amount", "date column": "order_date"},
    ),
]
