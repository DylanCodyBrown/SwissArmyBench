# ruff: noqa: F811
"""The Data page in a real browser (the owner, 2026-11-17: "yea I said a long time ago we needed a
standalone DATA rail icon and page" / "we dont even need catalog if its just tables"): the one place to
browse and find tables. The rail's Data after Variables lands on it (open=data; Back takes it away); with
nothing typed it browses every connection and its tables (a made-up SQLite shop, loaded; a made-up ledger
whose catalog is not, with Load), the open tables, Structures; a table's detail (columns, SQL name, code);
a search narrows the tree; Open as grid, Copy SQL name, Query in a notebook, Insert and a drag into a
Workbench cell; the keyboard; the Workbench pane's Pop out opening the Data page; the old pop-out
window's address sent here. Made-up data only.

With SWISSARMYBENCH_DATA_SHOTS set to a folder, the tests also save screenshots there (2x), light and
dark."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.asks import accept_asks
from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_DATA_SHOTS")
CATALOG = (
    "SELECT 'main' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
    "p.type AS data_type, CASE WHEN p.\"notnull\" THEN 'NO' ELSE 'YES' END AS is_nullable, "
    "p.cid + 1 AS ordinal_position "
    "FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p "
    "WHERE m.type = 'table' ORDER BY m.name, p.cid"
)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def sqlite_connection(server: dict[str, Any], folder: Path, name: str, tables: dict[str, Any]) -> None:
    path = folder / f"{name}.sqlite"
    with sqlite3.connect(path) as made:
        for table, (columns, rows) in tables.items():
            made.execute(f"CREATE TABLE {table} ({columns})")
            marks = ", ".join("?" for _ in rows[0])
            made.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)  # noqa: S608 (made-up tables)
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    body = {"name": name, "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", body | {"catalog": {"language": "sql", "command": CATALOG}})


@pytest.fixture
def shop(server: dict[str, Any], tmp_path: Path) -> dict[str, str]:
    """Made-up connections: an orchard shop (its catalog loaded) and a ledger (not loaded), a pasted table
    and a structure beside them."""
    tag = tmp_path.name[-6:].replace("-", "")
    shop, ledger = f"Orchard{tag}", f"Ledger{tag}"
    sqlite_connection(
        server,
        tmp_path,
        shop,
        {
            "orders": ("order_id INTEGER NOT NULL, customer_id INTEGER, amount REAL", [(1, 1, 9.5)]),
            "customers": ("CustomerKey INTEGER, name TEXT", [(1, "Ada")]),
        },
    )
    sqlite_connection(server, tmp_path, ledger, {"invoices": ("invoice_id INTEGER, total REAL", [(7, 3.5)])})
    call(server, "GET", f"/connections/{shop}/tree")
    # A saved connection's catalog loads itself: the ledger's is taken away again, so it is not loaded.
    call(server, "GET", f"/connections/{ledger}/tree")
    call(server, "DELETE", f"/catalogs/{ledger}")
    return {"shop": shop, "ledger": ledger}


def home(browser: Browser, server: dict[str, Any], dark: bool = False) -> Page:
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    )
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    accept_asks(page)
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def node(page: Page, key_part: str) -> Any:
    return page.locator(f".db-node[data-key*='{key_part}']").first


def connection(page: Page, name: str) -> Any:
    return page.locator(f".db-node.kind-connection[data-key='connection/{name}']")


def table(root: Any, name: str) -> Any:
    return root.locator(
        ".db-node.kind-table", has=root.page.locator(f":scope > .db-line .db-name:text-is('{name}')")
    )


def test_the_rails_data_lands_on_the_page_and_browses(
    browser: Browser, server: dict[str, Any], shop: dict[str, str]
) -> None:
    call(server, "POST", "/structures/paste", {"text": '{"crates": [{"grower_id": 7}]}', "name": "crates"})
    page = home(browser, server)
    rail_data = page.locator('.nav-rail [data-area="data"]')
    # After the Environment, with its own icon.
    areas = page.locator(".nav-rail-item").evaluate_all("(els) => els.map((e) => e.dataset.area)")
    assert areas[areas.index("environment") + 1] == "data"
    expect(rail_data.locator("svg")).to_have_attribute("data-icon", "data")
    rail_data.click()
    expect(page).to_have_url(re.compile(r"open=data"))
    data = page.locator(".area-page[data-page='data']")
    expect(data).to_be_visible()
    expect(page.locator(".nav-rail-item[aria-current='page']")).to_have_attribute("data-area", "data")
    expect(data.locator(".ex-search")).to_be_focused()
    # Back takes the page away; Forward brings it again.
    page.go_back()
    expect(page.locator(".area-page[data-page='data']")).to_have_count(0, timeout=10000)
    expect(page).not_to_have_url(re.compile(r"open=data"))
    expect(rail_data).not_to_have_attribute("aria-current", "page")
    page.go_forward()
    expect(data).to_be_visible()

    # Nothing typed: every connection with its status, then the open tables and Structures.
    expect(connection(page, shop["shop"]).locator(".db-status")).to_have_text("2 tables", timeout=20000)
    ledger = connection(page, shop["ledger"])
    expect(ledger.locator(".db-status")).to_have_text("Not loaded")
    expect(data.locator(".db-node.kind-section[data-key='section/structures']")).to_be_visible()
    # The shop: its schema, then its tables; a table's columns and types when it opens.
    orchard = connection(page, shop["shop"])
    orchard.locator(":scope > .db-line").click()
    expect(orchard).to_have_attribute("aria-expanded", "true")
    expect(table(orchard, "orders")).to_be_visible()
    expect(table(orchard, "customers")).to_be_visible()
    orders = table(orchard, "orders")
    orders.locator(":scope > .db-line .db-caret").click()
    columns = orders.locator(".db-node.kind-column")
    expect(columns.locator(".db-name")).to_have_text(["order_id", "customer_id", "amount"])
    expect(columns.locator(".db-type")).to_have_text(["INTEGER", "INTEGER", "REAL"])

    # The detail side: columns (nulls), where it comes from, its SQL name, the code that reads it.
    orders.locator(":scope > .db-line .db-name").click()
    detail = data.locator(".db-detail")
    expect(detail).to_be_visible()
    expect(detail.locator(".db-sql")).to_have_text(f"[{shop['shop']}].orders")
    expect(detail.locator(".db-columns tbody tr")).to_have_count(3)
    expect(detail.locator(".db-columns tbody tr").first).to_contain_text("No")  # order_id is NOT NULL
    expect(detail.locator(".db-code pre").first).to_have_text(
        f"%%sql\nSELECT *\nFROM [{shop['shop']}].orders\nLIMIT 100"
    )
    expect(detail.locator(".db-where").last).to_have_text(f"{shop['shop']} › main")
    shot(page, "data-page-light")

    # Copy SQL name (the clipboard), Open as grid (a tab here).
    detail.get_by_role("button", name="Copy SQL name").first.click()
    assert page.evaluate("navigator.clipboard.readText()") == f"[{shop['shop']}].orders"
    detail.get_by_role("button", name="Open as grid").click()
    expect(page.locator(".tab-item", has_text="orders").first).to_be_visible(timeout=20000)

    # A connection whose catalog is not loaded: Load, then its tables.
    ledger.locator(":scope > .db-line").hover()
    ledger.get_by_role("button", name="Load").click()
    expect(ledger.locator(".db-status")).to_have_text("1 table", timeout=30000)

    # A search narrows the tree: the shop's matches under its schema, a column under its table.
    page.locator(".area-page[data-page='data'] .ex-search").fill("cust")
    expect(data.locator(".ex")).to_have_attribute("data-searched", "cust", timeout=10000)
    expect(connection(page, shop["ledger"])).to_have_count(0)
    narrowed = connection(page, shop["shop"])
    expect(narrowed.locator(".db-node.kind-table > .db-line .db-name")).to_have_text(["customers", "orders"])
    expect(narrowed.locator(".db-node.kind-column .db-name")).to_have_text(["CustomerKey", "customer_id"])
    shot(page, "data-page-search-light")
    page.context.close()


def test_the_keyboard_and_slash(browser: Browser, server: dict[str, Any], shop: dict[str, str]) -> None:
    page = home(browser, server)
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=data#token={server['token']}")
    data = page.locator(".area-page[data-page='data']")
    expect(connection(page, shop["shop"]).locator(".db-status")).to_have_text("2 tables", timeout=20000)
    data.locator(".ex-search").fill(f"{shop['shop']}")
    expect(data.locator(".ex")).to_have_attribute("data-searched", shop["shop"], timeout=10000)
    # Down from the search into the tree; Right opens; Down to a table; Enter: Open as grid.
    data.locator(".ex-search").press("ArrowDown")
    first = connection(page, shop["shop"])
    expect(first).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(first).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("ArrowDown")  # its schema
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowDown")  # its first table
    focused = page.locator(".db-node:focus")
    expect(focused).to_have_attribute("data-kind", "table")
    name = focused.locator(":scope > .db-line .db-name").inner_text()
    page.keyboard.press("Enter")
    expect(page.locator(".tab-item", has_text=name).first).to_be_visible(timeout=20000)
    # / focuses the search, from anywhere on the page but a box.
    first.locator(":scope > .db-line").click()
    page.keyboard.press("/")
    expect(data.locator(".ex-search")).to_be_focused()
    page.context.close()


def test_query_insert_and_drag_into_a_workbench_cell_and_the_pop_out(
    browser: Browser, server: dict[str, Any], shop: dict[str, str]
) -> None:
    page = home(browser, server)
    bench = page.context.new_page()
    bench.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(bench.locator(".wb-codex")).to_be_visible(timeout=20000)  # its explorer (2026-11-21)

    def window(command: str, **args: Any) -> Any:
        body = {"command": command, "args": args, "page": "notebooks"}  # this window's page (2026-11-21)
        return call(server, "POST", "/workbench/window", body, agent=True)["result"]

    bench.wait_for_timeout(1000)  # the page's start (its restore) settles first
    window("file.newNotebook")
    expect(bench.locator(".wb-tab", has_text="Untitled notebook")).to_be_visible(timeout=20000)
    window("cell.insertBelow", kind="sql", source="")
    page.bring_to_front()
    page.locator('.nav-rail [data-area="data"]').click()
    data = page.locator(".area-page[data-page='data']")
    orchard = connection(page, shop["shop"])
    expect(orchard.locator(".db-status")).to_have_text("2 tables", timeout=20000)
    orchard.locator(":scope > .db-line").click()
    customers = table(orchard, "customers")
    customers.locator(":scope > .db-line .db-name").click()
    detail = data.locator(".db-detail")
    # Insert shows while the Workbench has a document in front; it goes into its selected cell.
    expect(detail.get_by_role("button", name="Insert")).to_be_visible(timeout=10000)
    detail.get_by_role("button", name="Insert").click()
    lines = bench.locator(".wb-cell.selected .view-lines")
    expect(lines).to_contain_text(f"[{shop['shop']}].customers", timeout=10000)
    # Query in a notebook: a new %%sql cell there.
    detail.get_by_role("button", name="Query in a notebook").click()
    expect(bench.locator(".wb-cell.selected .view-lines")).to_contain_text("LIMIT 100", timeout=10000)

    # A drag of a column from the page into a cell of the Workbench's notebook (Playwright cannot drag
    # between two windows; the browser carries the data, so it is carried here as it would be).
    customers.locator(":scope > .db-line .db-caret").click()
    column = customers.locator(".db-node.kind-column").first
    expect(column).to_be_visible()
    carried = column.evaluate(
        """(li) => {
            const dt = new DataTransfer();
            li.dispatchEvent(new DragEvent("dragstart", { dataTransfer: dt, bubbles: true }));
            return Object.fromEntries(dt.types.map((t) => [t, dt.getData(t)]));
        }"""
    )
    assert json.loads(carried["application/x-sab-explorer"]) == {
        "sql": "CustomerKey",
        "python": '"CustomerKey"',
    }
    table_carried = customers.evaluate(
        """(li) => {
            const dt = new DataTransfer();
            li.dispatchEvent(new DragEvent("dragstart", { dataTransfer: dt, bubbles: true }));
            return Object.fromEntries(dt.types.map((t) => [t, dt.getData(t)]));
        }"""
    )
    window("cell.insertBelow", kind="sql", source="")
    editor = bench.locator(".wb-cell.selected .monaco-editor").first
    editor.evaluate(
        """(node, carried) => {
            const dt = new DataTransfer();
            for (const [type, value] of Object.entries(carried)) dt.setData(type, value);
            const box = node.getBoundingClientRect();
            const at = { clientX: box.left + 20, clientY: box.top + 10, bubbles: true, cancelable: true };
            node.dispatchEvent(new DragEvent("dragover", { ...at, dataTransfer: dt }));
            node.dispatchEvent(new DragEvent("drop", { ...at, dataTransfer: dt }));
        }""",
        table_carried,
    )
    expect(bench.locator(".wb-cell.selected .view-lines")).to_contain_text(f"[{shop['shop']}].customers")

    # The Workbench pane's Pop out: the Data page in a window of its own, with the pane's search.
    bench.bring_to_front()
    bench.keyboard.press("Control+Shift+E")
    expect(bench.locator(".wb-explorer")).to_be_visible()
    bench.locator(".wb-explorer .ex-search").fill("orders")
    expect(bench.locator(".wb-explorer .ex")).to_have_attribute("data-searched", "orders", timeout=10000)
    with bench.context.expect_page() as popped:
        bench.locator(".wb-explorer").get_by_role("button", name="Pop out").click()
    out = popped.value
    expect(out).to_have_url(re.compile(r"/workspace\?open=data&q=orders"), timeout=20000)
    expect(out.locator(".area-page[data-page='data'] .ex-search")).to_have_value("orders", timeout=20000)
    expect(bench.locator(".wb-explorer")).to_be_hidden()
    expect(table(connection(out, shop["shop"]), "orders")).to_be_visible(timeout=20000)
    # The agent's explorer.popOut does the same.
    with bench.context.expect_page() as again:
        window("explorer.popOut")
    expect(again.value).to_have_url(re.compile(r"open=data"), timeout=20000)
    page.context.close()


def test_the_old_explorer_window_address_lands_on_the_data_page(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = home(browser, server)
    page.goto(f"http://127.0.0.1:{server['port']}/workbench?panel=explorer#token={server['token']}")
    expect(page).to_have_url(re.compile(r"/workspace\?open=data"), timeout=20000)
    expect(page.locator(".area-page[data-page='data']")).to_be_visible(timeout=20000)
    page.context.close()


def test_the_page_fills_the_window_in_the_dark(
    browser: Browser, server: dict[str, Any], shop: dict[str, str]
) -> None:
    page = home(browser, server, dark=True)
    page.locator('.nav-rail [data-area="data"]').click()
    orchard = connection(page, shop["shop"])
    expect(orchard.locator(".db-status")).to_have_text("2 tables", timeout=20000)
    orchard.locator(":scope > .db-line").click()
    orders = table(orchard, "orders")
    orders.locator(":scope > .db-line .db-caret").click()
    orders.locator(":scope > .db-line .db-name").click()
    expect(page.locator(".db-detail .db-columns")).to_be_visible()
    # It fills the window right of the rail: no strip under it, nothing cut off at the side.
    box = page.locator(".area-page[data-page='data']").bounding_box()
    assert box and box["height"] >= 899 and box["x"] + box["width"] >= 1439
    main = page.locator(".db-main").bounding_box()
    assert main and main["y"] + main["height"] >= 880
    shot(page, "data-page-dark")
    page.locator(".area-page[data-page='data'] .ex-search").fill("cust")
    expect(page.locator(".area-page[data-page='data'] .ex")).to_have_attribute(
        "data-searched", "cust", timeout=10000
    )
    shot(page, "data-page-search-dark")
    page.context.close()
