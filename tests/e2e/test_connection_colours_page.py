# ruff: noqa: F811
"""Connection colours in a real browser (the owner, 2026-11-16: "choose connection colors that everything
associated with that connection is painted that color, cells, grids, app cells ... I even think we need tab
groups from the grid based on connections"). A connection's colour on its card and its detail, on the grid
tabs of its tables (grouped by connection), on a notebook cell and a script cell that use it, on a canvas
block whose cell uses it, on the Data Explorer and the Session page; a change followed live. Ledger and Depot
are stood in for by SQLite files. Made-up data only.

With SAB_CONNCOLOUR_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401

SHOTS = os.environ.get("SAB_CONNCOLOUR_SHOTS")
PLAIN = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
MAGENTA, RUST = "#b3307f", "#b4521e"


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def connection(name: str, file: Path, table: str, rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    if not file.exists():
        with sqlite3.connect(file) as db:
            db.execute(f"CREATE TABLE {table} (id INTEGER, region TEXT, units INTEGER)")
            db.executemany(f"INSERT INTO {table} VALUES (?, ?, ?)", rows)  # noqa: S608 (a test's own name)
    return {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{file}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
    }


@pytest.fixture
def two(server: dict[str, Any]) -> dict[str, Any]:
    """Ledger and Depot saved, a table open from each and one from a file."""
    folder = Path(server["tmp"]) / "colours"
    folder.mkdir(exist_ok=True)
    names = {c["name"] for c in call(server, "GET", "/connections")["connections"]}
    for body in (
        connection("Ledger", folder / "ledger.sqlite", "invoices", [(1, "North", 3), (2, "East", 9)]),
        connection("Depot", folder / "depot.sqlite", "stock", [(1, "South", 5), (2, "West", 7)]),
    ):
        if body["name"] not in names:
            call(server, "POST", "/connections", body)
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    (folder / "plums.csv").write_text("id,kind\n1,Victoria\n2,Damson\n", encoding="utf-8")
    plums = call(server, "POST", "/datasets/plums/load", {"path": str(folder / "plums.csv")})
    invoices = call(server, "POST", "/connections/Ledger/open", {"schema": "main", "table": "invoices"})
    stock = call(server, "POST", "/connections/Depot/open", {"schema": "main", "table": "stock"})
    return {"folder": folder, "plums": plums, "invoices": invoices, "stock": stock}


def listed(server: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in call(server, "GET", "/connection-colours")["connections"]}


def worn(element: Locator) -> str:
    """The colour an element wears (--conn-a), lower case."""
    return str(element.evaluate("e => getComputedStyle(e).getPropertyValue('--conn-a').trim().toLowerCase()"))


WEARS = (
    "([s, c]) => { const e = document.querySelector(s);"
    " return !!e && getComputedStyle(e).getPropertyValue('--conn-a').trim().toLowerCase() === c; }"
)


def wait_worn(page: Page, selector: str, colour: str) -> None:
    """Wait until the element wears this colour."""
    page.wait_for_function(WEARS, arg=[selector, colour])


def shown(page: Page, server: dict[str, Any], name: str) -> str:
    theme = page.evaluate("document.documentElement.dataset.theme")
    return str(listed(server)[name]["themes"][theme]).lower()


def test_tabs_are_grouped_by_connection_and_wear_its_colour_live(
    browser: Browser, server: dict[str, Any], two: dict[str, Any]
) -> None:
    colours = listed(server)
    assert colours["Ledger"]["chosen"] and colours["Depot"]["chosen"]  # each new one got a free colour
    assert colours["Ledger"]["colour"] != colours["Depot"]["colour"]
    page = open_grid(browser, two["stock"]["grid_url"], 1500, 700, device_scale_factor=2)
    row = page.locator(".tabs-row")
    expect(row.locator(".tab-group")).to_have_count(3, timeout=15000)
    heads = row.locator(".tab-group-head")
    expect(heads).to_have_text(["Files", "Ledger", "Depot"])
    ledger_tab = row.locator(f".tab-item[data-grid='{two['invoices']['grid']}']")
    expect(ledger_tab).to_have_attribute("data-connections", "Ledger")
    tab_selector = f".tab-item[data-grid='{two['invoices']['grid']}']"
    wait_worn(page, tab_selector, shown(page, server, "Ledger"))
    shot(page, "1-tab-groups")
    # The keys still walk every tab, across the groups.
    first = row.locator(".tab-item").first
    first.click()
    first.press("ArrowRight")
    expect(row.locator(".tab-item.active")).to_have_attribute("data-grid", two["invoices"]["grid"])
    # A colour chosen (here by the agent) follows on the page at once.
    done = call(server, "PUT", "/connection-colours/Ledger", {"colour": RUST}, agent=True)
    assert {c["name"]: c["chosen"] for c in done["connections"]}["Ledger"] == RUST
    wait_worn(page, tab_selector, shown(page, server, "Ledger"))
    # Folding a group keeps the tab in front; the head counts the rest.
    heads.filter(has_text="Depot").click()
    expect(row.locator(".tab-group.collapsed .tab-group-count")).to_have_text("1")
    heads.filter(has_text="Depot").click()
    expect(row.locator(".tab-group.collapsed")).to_have_count(0)


def test_the_card_and_the_detail_choose_a_colour_the_rails_are_refused(
    browser: Browser, server: dict[str, Any], two: dict[str, Any]
) -> None:
    page = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?open=connections#token={server['token']}")
    card = page.locator(".connection-card[data-connection='Depot']")
    expect(card).to_be_visible(timeout=20000)
    wait_worn(page, ".connection-card[data-connection='Depot']", shown(page, server, "Depot"))
    swatch = page.get_by_role("button", name="Depot's colour").first
    swatch.click()
    palette = page.get_by_role("menu", name="Depot's colour")
    expect(palette.locator(".conn-palette-swatch")).to_have_count(8)
    shot(page, "2-card-palette")
    palette.get_by_role("menuitemradio", name="Magenta").click()
    wait_worn(page, ".connection-card[data-connection='Depot']", shown(page, server, "Depot"))
    assert listed(server)["Depot"]["chosen"] == MAGENTA
    # Its detail: the swatch beside the tools.
    card.click()
    expect(page.locator(".connection-colour .conn-swatch")).to_be_visible(timeout=15000)
    shot(page, "3-detail")
    # A rail colour (the notebooks' blue) is refused, with the reason.
    refused = page.evaluate(
        """async () => {
            const r = await fetch('/connection-colours/Depot', {method: 'PUT',
              headers: {'Content-Type': 'application/json'}, body: JSON.stringify({colour: '#1f63b0'})});
            return [r.status, await r.text()];
        }"""
    )
    assert refused[0] == 400 and "blue" in refused[1]


def test_cells_scripts_blocks_and_the_data_panel_wear_the_colour(
    browser: Browser, server: dict[str, Any], two: dict[str, Any], tmp_path: Path
) -> None:
    def code(number: int, source: str) -> dict[str, Any]:
        return {
            "cell_type": "code",
            "source": source,
            "metadata": {"swissarmybench": {"number": number}},
            "outputs": [],
            "execution_count": None,
        }

    notebook = tmp_path / "ledger checks.ipynb"
    cells = [
        code(1, "import swissarmybench as sab\nbig = sab.sql('Ledger', 'SELECT * FROM invoices')"),
        code(2, "both = sab.sql('Ledger', 'SELECT 1')\nmore = sab.sql('Depot', 'SELECT 2')"),
        code(3, "x = 1  # sab.sql('Depot') in a comment is no use"),
        code(4, "%%sql Depot\nSELECT * FROM stock"),
    ]
    notebook.write_text(json.dumps({**PLAIN, "cells": cells}), encoding="utf-8")
    script = tmp_path / "depot report.py"
    script.write_text(
        "import swissarmybench as sab\n\nstock = sab.sql('Depot', 'SELECT * FROM stock')\n", encoding="utf-8"
    )
    block = {
        "id": "b1",
        "document": "ledger checks.ipynb",
        "cell": 1,
        "row": 1,
        "column": 1,
        "w": 6,
        "h": None,
    }
    app = {
        "swissarmybench": "streamlit-app",
        "version": 1,
        "pages": [{"id": "p1", "name": "Page 1", "blocks": [block]}],
    }
    (tmp_path / "ledger.stapp.json").write_text(json.dumps(app), encoding="utf-8")

    page = browser.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=2).new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(page.locator(".wb-top")).to_be_visible(timeout=20000)

    def window(command: str, **args: Any) -> Any:
        return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)[
            "result"
        ]

    window("file.open", path=str(notebook))
    user_cells = page.locator(".wb-cell")
    expect(user_cells).to_have_count(4, timeout=20000)
    expect(user_cells.nth(0)).to_have_attribute("data-connections", "Ledger", timeout=15000)
    expect(user_cells.nth(1)).to_have_attribute("data-connections", "Ledger|Depot")
    assert "conn-two" in (user_cells.nth(1).get_attribute("class") or "")
    expect(user_cells.nth(2)).not_to_have_attribute("data-connections", "Depot")
    expect(user_cells.nth(3)).to_have_attribute("data-connections", "Depot")
    page.wait_for_function("() => document.querySelector('.wb-cell.conn-worn') !== null")
    assert worn(user_cells.nth(0)) == shown(page, server, "Ledger")
    # The Data Explorer's open tables wear their connection's colour too (plums; a file's, none).
    window("view.explorer", show=True)
    opened = page.locator(".ex-group[data-kind='tables'] .ex-result")
    expect(opened.and_(page.locator("[data-connections='Depot']"))).to_have_count(1, timeout=10000)
    window("view.explorer", show=False)
    shot(page, "4-notebook-cells")
    # Typing a connection's name into a cell marks it.
    call(server, "PUT", "/connection-colours/Ledger", {"colour": RUST})
    wait_worn(page, ".wb-cell", shown(page, server, "Ledger"))

    window("file.open", path=str(script))
    page.wait_for_function("() => document.querySelector('[class*=sab-stripe-]') !== null", timeout=20000)
    shot(page, "5-script-stripe")

    window("file.open", path=str(tmp_path / "ledger.stapp.json"))
    block_el = page.locator(".cv-block[data-block='b1']")
    expect(block_el).to_have_attribute("data-connections", "Ledger", timeout=20000)
    page.wait_for_function("() => document.querySelector('.cv-block.conn-worn') !== null")
    assert worn(block_el) == shown(page, server, "Ledger")
    shot(page, "6-canvas-block")
