# ruff: noqa: F811
"""The Write starters (docs/ideas.md, "Writing data"), in a real browser: the Write family in the
Workbench's blade list; a SQLite upsert dragged into a notebook's cell, its form offering the SQLite
connection first and the key column an id; the cell run as a dry run (nothing written, what it would do
said), then with dry_run=False (the rows written); and the Connections page's cards saying Writes or
Read-only, the detail saying which starters.

With SWISSARMYBENCH_SHOTS set to a folder, the tests also save screenshots there (2x). Made-up data
only."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_starters_page import blades, family
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import wait_until
from tests.e2e.workbench_helpers import open_window, saved_notebook, shot

ORDERS = pd.DataFrame(
    {"order_id": [1, 2, 3], "region": ["North", "South", "East"], "amount": [12.5, 40.0, 7.25]}
)
MAKES_ORDERS = (
    "import pandas as pd\n\n"
    'orders = pd.DataFrame({"order_id": [1, 2, 3], "region": ["North", "South", "East"], '
    '"amount": [12.5, 40.0, 7.25]})'
)


@pytest.fixture
def shop(server: dict[str, Any], tmp_path: Path) -> Iterator[Path]:
    """A made-up shop's SQLite file as a saved connection (opened read-only, as the form makes it), and a
    DuckDB file's (read-only: no Write starters)."""
    file = tmp_path / "shop.sqlite"
    with sqlite3.connect(file) as db:
        db.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, region TEXT, amount REAL)")
        db.execute("INSERT INTO orders VALUES (1, 'North', 10.0)")
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f"path = Path(r{str(file)!r})\n"
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)'
    )
    body = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", body | {"variable": "conn"})
    planning = {"name": "Planning", "kind": "sql", "template": "duckdb", "dialect": "duckdb"}
    planning |= {"code": "import duckdb\nconn = duckdb.connect(':memory:')", "variable": "conn"}
    call(server, "POST", "/connections", planning)
    close_tables(server)
    push_client.push(ORDERS, name="orders", new_grid=True)
    yield file
    close_tables(server)
    for name in ("Shop", "Planning"):
        call(server, "DELETE", f"/blades/{name}")


def test_a_write_starter_goes_into_a_cell_runs_dry_then_writes(
    browser: Browser, server: dict[str, Any], shop: Path, tmp_path: Path
) -> None:
    book = tmp_path / "writes.ipynb"
    saved_notebook(server, book, None, [MAKES_ORDERS, ""])
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    expect(cells.nth(1).locator(".monaco-editor")).to_be_visible(timeout=20000)
    listed = blades(workbench)
    expect(listed.locator(".starter-family", has_text="Write")).to_have_text("Write37", timeout=20000)
    family(listed, "Write")
    upsert = listed.locator(".starter-item", has_text="SQLite write")
    expect(upsert.locator(".blade-kind")).to_have_text("Python")
    shot(workbench, "1-the-write-family")
    upsert.drag_to(cells.nth(1).locator(".monaco-editor"))
    form = workbench.locator("dialog[open]")
    expect(form.locator("h2")).to_have_text("SQLite write")
    expect(form.get_by_label("Connection", exact=True)).to_have_value("Shop", timeout=20000)  # its kind first
    expect(form.get_by_label("Table", exact=True)).to_have_value("orders")
    expect(form.get_by_label("Key column", exact=True)).to_have_value("order_id")  # an id: a key
    expect(form.get_by_label("Target", exact=True)).to_have_value("orders")
    expect(form.get_by_label("Mode", exact=True)).to_have_value("append")  # one call a target: its mode
    form.get_by_label("Mode", exact=True).fill("upsert")
    shot(workbench, "2-its-form")
    form.get_by_role("button", name="Insert").click()
    expect(form).to_have_count(0)
    source = window(server, "doc.read")["cells"][1]["source"]
    assert (
        source.startswith("# SQLite write:")
        and 'mode="upsert"' in source
        and '    "Shop",' in source
        and "    orders,  # a DataFrame" in source
        and 'write_sqlite = sab.blade("Write to SQLite")' in source
    )
    if workbench.locator(".wb-flyout:not([hidden])").count():
        workbench.get_by_role("button", name="Add a blade").click()  # the blade list folded away
    window(server, "run.primary")
    outputs = cells.nth(1).locator(".wb-outputs")
    expect(outputs).to_contain_text("Dry run: nothing was written.", timeout=90000)
    expect(outputs).to_contain_text("Would     update 1 row, insert 2 rows")
    outputs.scroll_into_view_if_needed()
    shot(workbench, "3-the-dry-run")
    with sqlite3.connect(shop) as db:
        assert db.execute("SELECT count(*) FROM orders").fetchone() == (1,)
    # The user said to write: dry_run=False, and the cell again.
    line = cells.nth(1).locator(".view-line", has_text="dry_run=True")
    line.locator("span", has_text="True").last.dblclick()
    workbench.keyboard.type("False")
    workbench.keyboard.press("Escape")  # the completion's list closed
    wait_until(lambda: "    dry_run=False," in window(server, "doc.read")["cells"][1]["source"])
    window(server, "run.primary")
    expect(outputs).to_contain_text("Wrote orders on Shop: updated 1 row, inserted 2 rows", timeout=90000)
    outputs.scroll_into_view_if_needed()
    shot(workbench, "4-written")
    with sqlite3.connect(shop) as db:
        assert db.execute("SELECT region FROM orders ORDER BY order_id").fetchall() == [
            ("North",),
            ("South",),
            ("East",),
        ]
    workbench.close()


def test_a_connections_detail_says_what_it_writes(
    browser: Browser, server: dict[str, Any], shop: Path
) -> None:
    page = browser.new_context(viewport={"width": 1300, "height": 900}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=connections#token={server['token']}")
    shop_card = page.locator(".connection-card", has_text="Shop")
    expect(shop_card).to_be_visible(timeout=20000)
    # No Writes or Read-only tag on the cards (the owner, 2026-11-18: "we dont need that"); the detail says.
    expect(page.locator(".connection-card .connection-writes")).to_have_count(0)
    shop_card.click()
    detail = page.locator(".connection-config")
    expect(detail.locator("dt", has_text="Writes")).to_be_visible(timeout=20000)
    expect(detail).to_contain_text("append, create, replace, upsert, delete")
    shot(page, "6-a-connections-writes")
    wait_until(lambda: True)
    page.close()
