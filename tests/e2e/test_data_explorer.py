# ruff: noqa: F811
"""The Data Explorer in a real browser (the owner, 2026-11-17: "perhaps the data pane can move to its own
pane called Data Explorer that allows us to quickly search by column names, table name, connection to
quickly find data"; and "that Data Explorer should have the option to pop it out into another tab"). The
pane beside the data notebook and a script, a search, an insert into a SQL cell and a Python cell, the
Streamlit cells in App mode, and Ctrl+K on the grid page (its Open the Data page). The pop-out is the Data
page now: tests/e2e/test_data_page.py. Made-up data only.

With SWISSARMYBENCH_EXPLORER_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_EXPLORER_SHOTS")
CATALOG = (
    "SELECT 'main' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
    "p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position "
    "FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p "
    "WHERE m.type = 'table' ORDER BY m.name, p.cid"
)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def window(server: dict[str, Any], command: str, **args: Any) -> Any:
    return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)["result"]


def workbench(browser: Browser, server: dict[str, Any]) -> Page:
    page = browser.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=2).new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(page.locator(".wb-top")).to_be_visible(timeout=20000)
    return page


@pytest.fixture
def shop(server: dict[str, Any], tmp_path: Path) -> str:
    """A made-up SQLite shop as a connection, its catalog loaded, and a pasted table beside it."""
    name = f"Shop{tmp_path.name[-6:].replace('-', '')}"
    path = tmp_path / "shop.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount REAL)")
        made.execute("INSERT INTO orders VALUES (1, 1, 9.5)")
        made.execute("CREATE TABLE customers (CustomerKey INTEGER, name TEXT)")
        made.execute("INSERT INTO customers VALUES (1, 'Ada')")
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    body = {"name": name, "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", body | {"catalog": {"language": "sql", "command": CATALOG}})
    call(server, "GET", f"/connections/{name}/tree")
    return name


def open_explorer(page: Page) -> None:
    page.keyboard.press("Control+Shift+E")
    expect(page.locator(".wb-explorer")).to_be_visible()


def search(page: Page, text: str, root: Any = None) -> None:
    box = (root or page).locator(".ex-search")
    box.fill(text)
    expect((root or page).locator(".ex").first).to_have_attribute("data-searched", text, timeout=10000)


def test_the_pane_beside_the_data_notebook_and_a_script(
    browser: Browser, server: dict[str, Any], shop: str, tmp_path: Path
) -> None:
    project = call(server, "POST", "/projects", {"folder": str(tmp_path), "name": "orchard", "app": False})
    page = workbench(browser, server)
    window(server, "project.open", folder=project["folder"])
    expect(page.locator(".wb-tab", has_text="data.ipynb")).to_be_visible(timeout=20000)
    # Off until opened; then beside the data notebook (the Data panel was never there).
    expect(page.locator(".wb-explorer")).to_be_hidden()
    open_explorer(page)
    search(page, "cust")
    groups = page.locator(".ex-group")
    expect(groups.locator("h3")).to_contain_text(["Tables", "Columns"])
    tables = page.locator(".ex-group[data-kind='tables'] .ex-result")
    expect(tables).to_have_count(1)
    expect(tables.first.locator(".ex-name")).to_have_text("customers")
    expect(tables.first.locator(".ex-path")).to_have_text(f"{shop} › main")
    columns = page.locator(".ex-group[data-kind='columns'] .ex-name")
    expect(columns).to_have_text(["customer_id", "CustomerKey"])
    expect(page.locator(".ex-group[data-kind='columns'] .ex-count")).to_have_text("2")
    shot(page, "explorer-data-notebook")

    # Insert into a SQL cell: the table's SELECT, in its connection's name.
    window(server, "cell.insertBelow", kind="sql", source="")
    tables.first.hover()
    tables.first.get_by_role("button", name="Insert").click()
    lines = page.locator(".wb-cell.selected .view-lines")
    expect(lines).to_contain_text(f"[{shop}].customers")
    assert "SELECT" in lines.inner_text() and "sab.sql" not in lines.inner_text()
    # And into a Python cell: sab.sql(...) for a connection's table.
    window(server, "cell.insertBelow", kind="code", source="")
    tables.first.hover()
    tables.first.get_by_role("button", name="Insert").click()
    expect(lines).to_contain_text("sab.sql(")
    expect(lines).to_contain_text(f"[{shop}].customers")

    # Beside a script too: the pane stays, and Insert goes to the script's cursor.
    window(server, "file.newScript")
    expect(page.locator(".wb-explorer")).to_be_visible()
    search(page, "order_id")
    column = page.locator(".ex-group[data-kind='columns'] .ex-result").first
    column.hover()
    column.click()
    page.keyboard.press("Enter")  # the first action: Copy name (no clipboard here) does not throw
    shot(page, "explorer-script")
    # Show tables with this column: across connections and the open tables.
    column.get_by_role("button", name="Show tables with this column").click()
    expect(page.locator(".ex-column-chip")).to_contain_text("Tables with order_id")
    expect(page.locator(".ex-group[data-kind='columns'] .ex-path")).to_have_text([f"{shop} › main › orders"])
    # The agent's explorer.search answers the same results.
    found = window(server, "explorer.search", text="cust", kinds=["tables"])
    assert [r["name"] for g in found["groups"] for r in g["results"]] == ["customers"]
    expect(page.locator(".ex-search")).to_have_value("cust")
    # Ctrl+Shift+E again: closed.
    page.keyboard.press("Control+Shift+E")
    expect(page.locator(".wb-explorer")).to_be_hidden()
    page.context.close()


def test_app_mode_has_the_streamlit_cells(browser: Browser, server: dict[str, Any], tmp_path: Path) -> None:
    folder = tmp_path / "views"
    folder.mkdir()
    cell: dict[str, Any] = {
        "cell_type": "code",
        "source": "# Region filter\nimport streamlit as st\nst.write('plums')",
        "metadata": {"swissarmybench": {"number": 1}},
        "outputs": [],
        "execution_count": None,
    }
    plain = {"cells": [cell], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (folder / "views.ipynb").write_text(json.dumps(plain), encoding="utf-8")
    page = workbench(browser, server)
    window(server, "file.open", path=str(folder / "views.ipynb"))
    window(server, "file.newApp")
    cells = page.locator(".wb-mode-left .wb-st")
    expect(cells).to_be_visible(timeout=20000)
    expect(cells.locator(".wb-st-cell .wb-data-label")).to_have_text(["Region filter"], timeout=20000)
    # Starters is the other left panel (one a side).
    window(server, "data.starters", show=True)
    expect(page.locator(".wb-mode-left .wb-mode-starters")).to_be_visible()
    expect(cells).to_have_count(0)
    shot(page, "explorer-app-mode")
    page.context.close()


def test_ctrl_k_on_the_grid_page(browser: Browser, server: dict[str, Any], shop: str) -> None:
    page = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    page.keyboard.press("Control+K")
    dialog = page.locator("dialog.find-data")
    expect(dialog).to_be_visible()
    search(page, "cust", dialog)
    expect(
        dialog.locator(f".ex-group[data-kind='tables'] .ex-result[data-connections='{shop}'] .ex-name")
    ).to_have_text(["customers"])
    shot(page, "explorer-find-data")
    # Open the Data page: the dialog goes, the Data page comes with the same search (2026-11-17).
    dialog.get_by_role("button", name="Open the Data page").click()
    data = page.locator(".area-page[data-page='data']")
    expect(data).to_be_visible(timeout=10000)
    expect(dialog).to_have_count(0)
    expect(data.locator(".ex-search")).to_have_value("cust")
    expect(page).to_have_url(re.compile(r"q=cust.*open=data|open=data.*q=cust"))
    page.context.close()


def test_a_structures_path_opens_at_its_node(browser: Browser, server: dict[str, Any]) -> None:
    text = '{"plums": [{"grower": {"farm_id": 7}}]}'
    call(server, "POST", "/structures/paste", {"text": text, "name": "plum crates"})
    page = workbench(browser, server)
    open_explorer(page)
    search(page, "farm_id")
    found = page.locator(".ex-group[data-kind='structures'] .ex-result").first
    expect(found.locator(".ex-name")).to_have_text("farm_id")
    expect(found.locator(".ex-path")).to_have_text("plum crates › $.plums[].grower")
    expect(found.get_by_role("button", name="Copy path")).to_have_attribute(
        "title", "$.plums[].grower.farm_id"
    )
    found.hover()
    found.get_by_role("button", name="Open at this node").click()
    shown = page.locator(".area-page[data-page='structures']")
    expect(shown).to_be_visible(timeout=20000)
    expect(shown.get_by_text("$.plums[0].grower.farm_id").first).to_be_visible(timeout=10000)
    page.context.close()
