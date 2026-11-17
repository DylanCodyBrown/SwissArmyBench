# ruff: noqa: F811
"""A table's connection swapped in a real browser (the owner, 2026-11-16: "we also need button the the
table row to swap a tables connection ... I deleted the edp but need its queries to run on the other"):
the Table row's Connection: EDP, its chooser, the other connection's tables to pick, the SQL window for a
query, the strip's Use another connection… for a deleted connection, and Point these at Trino for the
code. EDP and Trino are stood in for by SQLite files. Made-up data only."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401

STEPS = [
    {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "East"}},
    {"kind": "sort", "params": {"keys": [["units", "desc"]]}},
]
ROWS = [(1, "North", 3), (2, "East", 9), (3, "South", 5), (4, "North", 7)]
SHOTS = os.environ.get("SAB_SWAP_SHOTS")  # a folder: the screenshots for the report


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def made_up(folder: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    folder.mkdir(exist_ok=True)
    edp_file, trino_file, sales_file = folder / "edp.sqlite", folder / "trino.sqlite", folder / "sales.sqlite"
    if not edp_file.exists():
        with sqlite3.connect(edp_file) as db:
            db.execute("CREATE TABLE ORDERS (order_id INTEGER, region TEXT, units INTEGER)")
            db.executemany("INSERT INTO ORDERS VALUES (?, ?, ?)", ROWS)
            db.execute("CREATE TABLE sales_items (item_id INTEGER, name TEXT)")
            db.execute("INSERT INTO sales_items VALUES (1, 'Pear')")
        with sqlite3.connect(trino_file) as db:
            db.execute("CREATE TABLE placeholder (x INTEGER)")
        with sqlite3.connect(sales_file) as db:
            db.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, units INTEGER)")
            db.executemany("INSERT INTO orders VALUES (?, ?, ?)", [*ROWS, (5, "West", 2)])
            db.execute("CREATE TABLE items (item_id INTEGER, name TEXT)")
            db.execute("INSERT INTO items VALUES (1, 'Pear'), (2, 'Plum')")
    edp = {
        "name": "EDP",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{edp_file}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
    }
    catalog = (
        "SELECT 'sales' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
        "p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position "
        "FROM sales.sqlite_master AS m JOIN pragma_table_info(m.name, 'sales') AS p "
        "WHERE m.type = 'table' ORDER BY m.name, p.cid"
    )
    trino = {
        "name": "Trino",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{trino_file}")\n'
            f'sales = Path(r"{sales_file}").resolve().as_uri() + "?mode=ro"\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
            'conn.execute("ATTACH DATABASE ? AS sales", (sales,))\n'
        ),
        "catalog": {"language": "sql", "command": catalog},
    }
    return edp, trino


@pytest.fixture
def both(server: dict[str, Any]) -> dict[str, Any]:
    """EDP and Trino saved (again), no project and no table open."""
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    edp, trino = made_up(Path(server["tmp"]) / "swap")
    names = {c["name"] for c in call(server, "GET", "/connections")["connections"]}
    for body in (edp, trino):
        if body["name"] not in names:
            call(server, "POST", "/connections", body)
    return {"edp": edp, "trino": trino}


def open_orders(server: dict[str, Any], table: str = "ORDERS") -> dict[str, Any]:
    opened = call(server, "POST", "/connections/EDP/open", {"schema": "main", "table": table})
    call(server, "POST", f"/grids/{opened['grid']}/steps", {"steps": STEPS})
    return dict(opened)


def ids(server: dict[str, Any], grid: str) -> list[Any]:
    return [r[0] for r in call(server, "GET", f"/grids/{grid}/rows")["rows"]]


def test_the_table_rows_connection_moves_a_table_with_its_steps_and_undoes(
    browser: Browser, server: dict[str, Any], both: dict[str, Any]
) -> None:
    opened = open_orders(server)
    page = open_grid(browser, opened["grid_url"], 1500, 860, device_scale_factor=2)
    tool = page.get_by_role("button", name="Connection: EDP")
    expect(tool).to_be_visible(timeout=15000)
    tool.click()
    chooser = page.locator("dialog[open]")
    expect(chooser.locator(".swap-current")).to_contain_text("EDP")
    expect(chooser.get_by_role("button", name="Trino")).to_be_visible()
    shot(page, "1-chooser")
    chooser.get_by_role("button", name="Trino").click()
    expect(page.get_by_role("button", name="Connection: Trino")).to_be_visible(timeout=20000)
    assert ids(server, opened["grid"]) == [4, 3, 1, 5]  # the same steps on Trino's rows
    strip = page.locator(".project-fix.swap-done")
    expect(strip).to_contain_text("EDP → Trino")
    shot(page, "2-swapped-strip")
    strip.get_by_role("button", name="Undo").click()
    expect(page.get_by_role("button", name="Connection: EDP")).to_be_visible(timeout=20000)
    assert ids(server, opened["grid"]) == [4, 3, 1]


def test_a_table_trino_names_differently_is_picked_from_its_catalog_or_written_as_a_query(
    browser: Browser, server: dict[str, Any], both: dict[str, Any]
) -> None:
    opened = open_orders(server, "sales_items")
    call(server, "POST", f"/grids/{opened['grid']}/steps", {"steps": []})
    page = open_grid(browser, opened["grid_url"], 1500, 860, device_scale_factor=2)
    page.get_by_role("button", name="Connection: EDP").click()
    chooser = page.locator("dialog[open]")
    chooser.get_by_role("button", name="Trino").click()
    expect(chooser.locator(".swap-was")).to_contain_text("main.sales_items")
    chooser.get_by_role("button", name="sales", exact=True).click()
    expect(chooser.get_by_role("button", name="items", exact=True)).to_be_visible(timeout=10000)
    shot(page, "3-pick-from-catalog")
    # Write a query… opens the SQL window holding a first query for the table.
    with page.expect_popup() as popup:
        chooser.get_by_role("button", name="Write a query…").click()
    window = popup.value
    box = window.locator("dialog[open] textarea.code-input")
    expect(box).to_have_value(re.compile("sales_items"), timeout=15000)
    box.fill("SELECT item_id, upper(name) AS name FROM sales.items")
    window.set_viewport_size({"width": 960, "height": 680})
    if SHOTS:
        window.screenshot(path=str(Path(SHOTS) / "4-sql-window.png"))
    with window.expect_event("close"):
        window.get_by_role("button", name="Run on Trino").click()
    state = call(server, "GET", f"/tables/{opened['dataset']}/connection")
    assert state["connection"] == "Trino" and state["how"] == "query"
    expect(page.get_by_role("button", name="Connection: Trino")).to_be_visible(timeout=20000)


def test_a_deleted_connections_tables_move_from_the_strip_and_the_code_follows_where_ticked(
    browser: Browser, server: dict[str, Any], both: dict[str, Any]
) -> None:
    folder = Path(server["tmp"]) / "swap"
    target = folder / "work"
    call(server, "POST", "/project/new", {"path": str(target), "discard": True})
    for body in (both["edp"], both["trino"]):
        try:
            call(server, "POST", "/connections", body)
        except urllib.error.HTTPError:
            pass  # carried in with the project already
    open_orders(server)
    book = Path(call(server, "GET", "/project")["project"]["folder"]) / "orders.ipynb"
    cells = [
        {"kind": "sql", "source": "SELECT * FROM ORDERS", "connection": "EDP"},
        {"kind": "code", "source": "import swissarmybench as sab\nlate = sab.sql('EDP', 'SELECT 1')"},
        {"kind": "code", "source": "note = 'EDP'"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(book), "cells": cells})
    call(server, "DELETE", "/blades/EDP")
    call(server, "POST", "/project/save", {})
    call(server, "POST", "/project/close", {"discard": True})
    call(server, "POST", "/project/open", {"path": str(target)})
    # Opened again: a new working folder, the notebook in it.
    book = Path(call(server, "GET", "/project")["project"]["folder"]) / "orders.ipynb"
    call(server, "POST", "/workbench/open", {"path": str(book)})
    page = browser.new_context(viewport={"width": 1500, "height": 860}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    fix = page.locator(".project-fix[data-table='ORDERS']:visible").first
    expect(fix).to_contain_text("No connection EDP", timeout=20000)
    shot(page, "5-strip-use-another")
    fix.get_by_role("button", name="Use another connection…").click()
    page.locator("dialog[open]").get_by_role("button", name="Trino").click()
    repoint = page.locator("dialog[open].wide, dialog[open]").filter(has_text="Point these at Trino")
    expect(repoint.locator(".swap-ref")).to_have_count(2, timeout=20000)
    repoint.locator(".swap-ref").nth(1).locator("input").uncheck()
    shot(page, "6-point-the-code")
    repoint.get_by_role("button", name="Point these at Trino").click()
    expect(page.locator(".project-fix[data-table='ORDERS']").filter(has_text="No connection")).to_have_count(
        0
    )

    def written() -> list[str]:
        return ["".join(c["source"]) for c in json.loads(book.read_text(encoding="utf-8"))["cells"]]

    # The page's toast comes before the file is written: wait for the file itself.
    for _ in range(100):
        if written()[0].startswith("%%sql Trino"):
            break
        page.wait_for_timeout(100)
    saved = written()
    assert saved[0].startswith("%%sql Trino") and "sab.sql('EDP'" in saved[1] and saved[2] == "note = 'EDP'"
    state = call(server, "GET", "/tables/ORDERS/connection")
    assert state["connection"] == "Trino" and state["open"] is True
    call(server, "POST", "/project/close", {"discard": True})
