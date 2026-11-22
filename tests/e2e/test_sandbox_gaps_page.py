# ruff: noqa: F811
"""The sandbox's approved gaps in a real browser (the owner, 2026-11-21): a grid table made a sandbox variant
(its designation and origin shown in its tab and bar), one of its cells edited in the grid then Reset, a bad
value refused in place; the sandbox list sorted by a heading; Mocked as a connection; Try it's body kept as
its example; the Sandbox on the Connections page. Screenshots (scale 2) when SAB_API_SHOTS names a folder.
Made-up data only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_local_apis_page import open_workspace, shop, shot  # noqa: F401
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.test_local_api import API_PY


def _amounts(server: dict[str, Any]) -> list[float]:
    """The sandbox's rows as a local sandbox API reads them: the adapter's query on its door."""
    from swissarmybench.adapters import adapter

    door = adapter.Remote(
        f"http://127.0.0.1:{server['port']}/sandbox/adapter",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    read = adapter.query(door, "SELECT amount FROM orders_sandbox ORDER BY order_id")
    return [float(r["amount"]) for r in read.read_all().to_pylist()]


def test_a_grid_table_made_a_variant_edited_in_its_grid_then_reset(
    browser: Browser, server: dict[str, Any], shop: Path
) -> None:
    page = open_workspace(browser, server)
    page.locator(".ribbon-tools button", has_text="Make a sandbox variant").click()
    dialog = page.get_by_role("dialog", name="Make a sandbox variant")
    dialog.get_by_role("button", name="Make").click()
    expect(page.locator(".toast", has_text="orders · sandbox is in the sandbox")).to_be_visible(timeout=20000)
    call(server, "POST", "/sandbox/tables/open", {"table": "orders_sandbox"})
    tab = page.locator(".tab-item", has_text="orders · sandbox")
    expect(tab).to_be_visible(timeout=20000)
    expect(tab.locator(".tab-sandbox")).to_be_visible()
    tab.click()
    pane = page.locator(".pane:not([hidden])")
    bar = pane.locator(".sandbox-bar")
    expect(bar.locator(".sandbox-designation")).to_have_text("orders · sandbox", timeout=20000)
    expect(bar.locator(".sandbox-origin")).to_contain_text("A sandbox variant of orders, copied ")
    expect(bar).to_contain_text("Local test data, never live")
    # A cell edited in place: a sandbox write, counted.
    cell = pane.locator(".ag-row[row-index='0'] .ag-cell[col-id='amount']")
    expect(cell).to_have_text("10.5", timeout=20000)
    cell.dblclick()
    box = page.locator(".sandbox-cell-input")
    expect(box).to_have_value("10.5")
    box.fill("abc")
    box.press("Enter")
    expect(page.locator(".error-note", has_text="'abc' is not a number")).to_be_visible(timeout=20000)
    shot(page, "sandbox-grid-edit-refused", ".pane:not([hidden])")
    box.fill("42.5")
    box.press("Enter")
    expect(box).to_have_count(0, timeout=20000)
    expect(cell).to_have_text("42.5", timeout=20000)
    assert call(server, "GET", "/sandbox")["log"]["orders_sandbox"]["updated"] == 1
    shot(page, "sandbox-variant-grid-edited", ".pane:not([hidden])")
    # Reset this table: the edit is undone; the origin was never written.
    bar.get_by_role("button", name="Reset orders_sandbox").click()
    expect(cell).to_have_text("10.5", timeout=20000)
    until(lambda: _amounts(server)[0], 10.5)


def test_the_sandbox_list_sorts_mocks_and_the_connections_page_shows_the_sandbox(
    browser: Browser, server: dict[str, Any], shop: Path, tmp_path: Path
) -> None:
    database = tmp_path / "crm.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE accounts (account_id INTEGER, name TEXT)")
        made_up.executemany("INSERT INTO accounts VALUES (?, ?)", [(i, f"Account {i}") for i in range(1, 8)])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    try:
        call(server, "DELETE", "/blades/CRM")
    except Exception:  # noqa: S110 (not there yet)
        pass
    crm = {"name": "CRM", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", crm)
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "orders"})
    cols = [{"name": "id", "type": "integer", "key": True}, {"name": "note", "type": "text"}]
    call(server, "POST", "/sandbox/tables", {"from": "columns", "name": "notes", "columns": cols})
    page = open_workspace(browser, server)
    page.evaluate("localStorage.removeItem('swissarmybench.sandbox.sort')")
    page.locator(".nav-rail [data-area='apis']").click()
    panel = page.locator(".sandbox-panel")
    names = panel.locator("tbody tr")
    expect(names).to_have_count(2, timeout=20000)
    expect(names.first).to_have_attribute("data-table", "notes")  # by name: notes before orders
    panel.locator("th button", has_text="Rows").click()
    expect(names.first).to_have_attribute("data-table", "notes", timeout=20000)  # 0 rows first
    panel.locator("th button", has_text="Rows").click()
    expect(names.first).to_have_attribute("data-table", "orders", timeout=20000)  # then the other way
    expect(panel.locator("th[aria-sort='descending']")).to_contain_text("Rows")
    shot(page, "sandbox-list-sorted-by-rows", ".sandbox-panel")
    # Mocked as a connection: the notes table answers as CRM.
    picker = panel.locator("tr[data-table='notes'] select.sandbox-mock")
    picker.select_option("CRM")

    def mocked() -> Any:
        tables = call(server, "GET", "/sandbox")["tables"]
        return next(t for t in tables if t["name"] == "notes")["client"].get("connection")

    until(mocked, "CRM")
    expect(panel.locator("tr[data-table='notes'] select.sandbox-mock")).to_have_value("CRM", timeout=20000)
    shot(page, "sandbox-mocked-as", ".sandbox-panel")
    # The Connections page: the project's Sandbox, local test data, its tables and Reset.
    page.locator(".nav-rail [data-area='connections']").click()
    card = page.locator(".connection-card.fam-sandbox")
    expect(card).to_contain_text("Sandbox · 2 tables", timeout=20000)
    expect(card).to_contain_text("Local test data, never live")
    shot(page, "connections-sandbox-card")
    card.click()
    expect(page.locator(".area-page .sandbox-panel tbody tr")).to_have_count(2, timeout=20000)
    reset = page.locator(".area-page .sandbox-panel").get_by_role("button", name="Reset", exact=True)
    expect(reset).to_be_visible()
    shot(page, "connections-sandbox-page")
    call(server, "DELETE", "/blades/CRM")


def test_try_its_body_kept_as_its_example(browser: Browser, server: dict[str, Any], shop: Path) -> None:
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "orders"})
    (shop / "API.py").write_text(API_PY, encoding="utf-8")
    page = open_workspace(browser, server)
    page.locator(".nav-rail [data-area='apis']").click()
    post = page.locator(".local-api-endpoint[data-endpoint='add_order']")
    post.get_by_role("button", name="Try it").click()
    kept = {"order_id": 77, "region": "South", "amount": 5.5}
    post.get_by_label("Body").fill(json.dumps(kept))
    post.get_by_role("button", name="Keep as its example").click()
    expect(page.locator(".toast", has_text="Kept as POST /orders's example")).to_be_visible(timeout=20000)
    stored = json.loads((shop / ".sab" / "api_examples.json").read_text(encoding="utf-8"))
    assert stored["examples"]["POST /orders"] == kept
    shot(page, "try-it-keep-as-example", ".local-apis")
    # Opened again, Try it starts from it.
    page.reload()
    expect(page.locator(".local-api-endpoint[data-endpoint='add_order']")).to_be_visible(timeout=30000)
    post = page.locator(".local-api-endpoint[data-endpoint='add_order']")
    post.get_by_role("button", name="Try it").click()
    expect(post.get_by_label("Body")).to_contain_text('"order_id": 77')
