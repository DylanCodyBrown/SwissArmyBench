# ruff: noqa: F811
"""The New query page (the owner, 2026-11-20, on the grid page's landing and the tab row's "+": "get rid of
all of this this should just be a new query page, with the active connections and you can click one to start a
new grid sql"), in a real browser with made-up connections: the grid page with no table open lists the
connections that run SQL; a click opens the draft with Query from set to that one, its editor ready; with
grids open the "+" shows the same page with Open tables (DuckDB) first; arrows and Enter work it; the agent's
app_navigate opens the draft on a connection. SAB_NEW_QUERY_SHOTS names a folder for its screenshots."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401


def made_up_connection(server: dict[str, Any], folder: Path, name: str, table: str) -> None:
    """A SQLite file of made-up rows, saved as a connection that runs SQL."""
    path = folder / f"{table}.sqlite"
    with sqlite3.connect(path) as made:
        made.execute(f"CREATE TABLE {table} (id INTEGER, amount REAL)")
        made.executemany(f"INSERT INTO {table} VALUES (?, ?)", [(1, 4.5), (2, 8.0), (3, 1.25)])  # noqa: S608
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    call(
        server,
        "POST",
        "/connections",
        {"name": name, "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code},
    )


def test_the_new_query_page_starts_a_query_on_a_connection(
    browser: Browser, server: dict[str, Any], tmp_path_factory: Any
) -> None:
    folder = tmp_path_factory.mktemp("new_query")
    made_up_connection(server, folder, "Harbor Sales", "harbor_orders")
    made_up_connection(server, folder, "Orchard Ledger", "orchard_entries")
    base = f"http://127.0.0.1:{server['port']}"
    context = browser.new_context(viewport={"width": 1400, "height": 800}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"{base}/workspace?view=grids#token={server['token']}")

    # No table open: the page is the connections, nothing else (no Open a file, Paste, Catalog, Projects).
    landing = page.locator(".new-query-page")
    expect(landing.get_by_role("heading", name="New query")).to_be_visible(timeout=20000)
    choices = landing.locator(".new-query-choice")
    expect(choices).to_have_count(2, timeout=15000)
    expect(choices.nth(0)).to_contain_text("Harbor Sales")
    expect(choices.nth(1)).to_contain_text("Orchard Ledger")
    expect(choices.nth(0)).to_have_attribute("data-connections", "Harbor Sales")  # it wears its colour
    for gone in ("Open a file…", "Paste", "Query", "Catalog", "Add connection"):
        expect(landing.get_by_role("button", name=gone, exact=True)).to_have_count(0)
    expect(landing.get_by_role("link", name="Projects")).to_have_count(0)
    shots = Path(os.environ.get("SAB_NEW_QUERY_SHOTS") or folder)
    shots.mkdir(parents=True, exist_ok=True)
    page.mouse.move(1300, 700)
    page.screenshot(path=str(shots / "new-query-page.png"))

    # A click: the draft, Query from already that connection, the editor ready after "FROM ".
    choices.nth(1).click()
    draft = page.locator(".tab-item.tab-draft")
    expect(draft).to_have_attribute("aria-selected", "true", timeout=15000)
    view = page.locator("#query-view")
    expect(view.get_by_role("combobox", name="Query from")).to_have_value("Orchard Ledger", timeout=15000)
    expect(view.locator(".sql-status")).to_contain_text("Runs on Orchard Ledger")
    expect(view.locator(".sql-editor .monaco-editor, .sql-editor textarea").first).to_be_visible(
        timeout=20000
    )
    page.wait_for_function("document.activeElement && document.activeElement.closest('.sql-editor') !== null")
    page.keyboard.type("orchard_entries")
    view.get_by_role("textbox", name="Name of the new table").fill("orchard_rows")
    view.get_by_role("button", name="Run", exact=True).click()
    pane = page.locator(".pane.active")
    expect(pane.locator(".ag-row")).to_have_count(3, timeout=20000)
    expect(pane.locator(".query-tray .query-from")).to_have_text("on Orchard Ledger")

    # Grids open: the "+" is the same page, Open tables (DuckDB) first; arrows move, Enter opens.
    page.get_by_role("button", name="New query").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grids")
    expect(choices).to_have_count(3)
    expect(choices.first).to_contain_text("Open tables (DuckDB)")
    expect(choices.first).to_be_focused()
    page.mouse.move(1300, 700)
    page.screenshot(path=str(shots / "new-query-page-with-grids.png"))
    page.keyboard.press("ArrowDown")
    expect(choices.nth(1)).to_be_focused()
    page.keyboard.press("Enter")
    expect(draft).to_have_attribute("aria-selected", "true", timeout=15000)
    expect(view.get_by_role("combobox", name="Query from")).to_have_value("Harbor Sales")

    # The agent, as the click: app_navigate query:<connection> (the draft on it), new_query (the page).
    call(server, "POST", "/navigate", {"to": "new_query"}, agent=True)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grids", timeout=15000)
    call(server, "POST", "/navigate", {"to": "query:Orchard Ledger"}, agent=True)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "query", timeout=15000)
    expect(view.get_by_role("combobox", name="Query from")).to_have_value("Orchard Ledger")
    context.close()
    call(server, "DELETE", "/datasets/orchard_rows")
