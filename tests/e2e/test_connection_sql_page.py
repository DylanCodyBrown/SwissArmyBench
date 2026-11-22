# ruff: noqa: F811
"""A connection's tables, easy to get (the owner, 2026-11-17: "the app needs to make it easy for me as the
user to use that connection to get those tables"), in a real browser with made-up data: the Connections
page's tree on a database connection (Open, Open all, Copy name, Preview), and a %%sql cell with no
connection naming that connection's table ([Shop].orders), its head showing the connection and its
completion offering connections, then their tables. Pictures go to SAB_SHOTS when it is set."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.asks import answer_ask
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import open_workbench, start, wait_until
from tests.test_connection_tables import CATALOG


def shot(page: Page, name: str, target: Any = None) -> None:
    folder = os.environ.get("SAB_SHOTS")
    if not folder:
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    (target or page).screenshot(path=str(Path(folder) / name))


def shop(server: dict[str, Any], folder: Path) -> None:
    path = folder / "shop_sql_page.sqlite"
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount REAL)")
        made.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)", [(1, "North", 10.5), (2, "South", 7.0), (3, "North", 2.5)]
        )
        made.execute("CREATE TABLE regions (region TEXT, manager TEXT)")
        made.executemany("INSERT INTO regions VALUES (?, ?)", [("North", "Ann"), ("South", "Bo")])
        made.execute("CREATE TABLE returns (order_id INTEGER, reason TEXT)")
        made.executemany("INSERT INTO returns VALUES (?, ?)", [(2, "Damaged")])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    body = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", body | {"catalog": {"language": "sql", "command": CATALOG}})
    wait_until(lambda: any(c["name"] == "Shop" for c in call(server, "GET", "/catalogs")["catalogs"]))


def test_the_connections_tree_opens_copies_and_a_sql_cell_names_the_connection(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path_factory: Any
) -> None:
    shop(server, tmp_path_factory.mktemp("shop"))
    page = open_grid(browser, orders_url)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.locator(".nav-rail [data-area='connections']").click()
    dialog = page.locator(".area-page[data-page='connections']")
    dialog.locator(".connection-card[data-connection='Shop']").click()
    tree = dialog.locator(".connection-tables")
    expect(tree.locator(".conn-tree-table")).to_have_count(3, timeout=30000)
    expect(tree.locator("h2 .count")).to_have_text("3")
    # Search.
    tree.get_by_role("searchbox", name="Search tables").fill("reg")
    expect(tree.locator(".conn-tree-table")).to_have_count(1)
    tree.get_by_role("searchbox", name="Search tables").fill("")
    orders = tree.locator(".conn-tree-table[data-table='orders']")
    orders.get_by_role("button", name="Preview").click()
    expect(orders.locator(".connection-preview tbody tr")).to_have_count(3, timeout=30000)
    shot(page, "connection-tree.png", dialog)
    # Copy name: how DuckDB SQL names it.
    orders.get_by_role("button", name="Copy name").click()
    expect(page.locator(".toast", has_text="Copied [Shop].orders")).to_be_visible()
    assert page.evaluate("navigator.clipboard.readText()") == "[Shop].orders"
    # Open all: a confirm with the count, each its own grid.
    asked: list[str] = []
    tree.get_by_role("button", name="Open all").click()
    asked.append(answer_ask(page))
    expect(page.locator(".toast", has_text="3 tables of main are open.")).to_be_visible(timeout=60000)
    assert asked and "Open all 3 tables of main" in asked[0]
    names = {d["name"] for d in call(server, "GET", "/datasets")["datasets"]}
    assert {"orders", "regions", "returns"} <= names or {"Shop_orders", "regions", "returns"} <= names

    # The Workbench: a SQL cell with no connection names Shop's table; its head shows Shop.
    workbench = open_workbench(page)
    start(workbench)
    cell = workbench.locator(".wb-cell").first
    expect(cell.locator(".monaco-editor")).to_be_visible(timeout=20000)
    cell.get_by_label("Cell kind").select_option("sql")
    cell.get_by_label("Connection").select_option("")  # DuckDB here
    expect(cell.get_by_label("Connection").locator("option:checked")).to_have_text("DuckDB")
    cell.locator(".monaco-editor").click()
    workbench.keyboard.type("SELECT region, sum(amount) AS amount FROM [Sh")
    workbench.keyboard.press("Control+Space")
    suggest = workbench.locator(".suggest-widget .monaco-list-row")
    expect(suggest.filter(has_text="[Shop]").first).to_be_visible(timeout=10000)
    workbench.keyboard.press("Enter")  # [Shop].
    workbench.keyboard.type("ord")
    workbench.keyboard.press("Control+Space")
    expect(suggest.filter(has_text="orders").first).to_be_visible(timeout=10000)
    workbench.keyboard.press("Enter")
    workbench.keyboard.type(" GROUP BY ALL ORDER BY 1")
    expect(cell.locator(".wb-sql-conn[data-connection='Shop']")).to_be_visible()
    cell.get_by_role("button", name="Run cell").click()
    expect(cell.get_by_role("button", name="Open as grid")).to_be_visible(timeout=60000)  # a DataFrame
    expect(cell.locator(".wb-outputs")).not_to_contain_text("Error")
    shot(workbench, "sql-cell-names-a-connection.png", cell)
