"""A table read from another connection on the Blazor Grids page (the classic swapConnection.ts): the Table
row's Connection: name opens the chooser, another connection reads the table with its steps kept, the
note's Undo puts it back. Two made-up DuckDB files, each with the same table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import open_page


def made_up_shop(path: Path, rows: int) -> Path:
    with duckdb.connect(str(path)) as db:
        db.execute(
            "CREATE TABLE ledger AS SELECT i AS entry_id, round(i * 1.5, 2) AS amount "
            "FROM range(1, ? + 1) t(i)",
            [rows],
        )
    return path


def add_duckdb(page: Page, name: str, path: Path) -> None:
    page.click("text=Add connection")
    page.click(".kind-card[data-kind=duckdb]")
    page.fill(".connection-name", name)
    field = page.locator(".connection-field[data-field=path]")
    field.fill(str(path))
    field.press("Tab")
    expect(page.locator(".connection-code pre")).to_contain_text(path.name)
    page.click("button:has-text('Save')")
    expect(page.locator("h1")).to_contain_text(name)


def test_a_table_reads_from_another_connection_and_back(browser: Browser, server: dict[str, Any]) -> None:
    north = made_up_shop(server["tmp"] / "north_ledger.duckdb", 30)
    south = made_up_shop(server["tmp"] / "south_ledger.duckdb", 12)
    page = open_page(browser, server, "connections")
    add_duckdb(page, "NorthBooks", north)
    page.goto(page.url.split("/blazor/")[0] + "/blazor/connections")
    page.wait_for_selector(".nav-rail")
    add_duckdb(page, "SouthBooks", south)
    page.goto(page.url.split("/blazor/")[0] + "/blazor/connections?name=NorthBooks")
    page.locator(".connection-tables tr", has_text="ledger").locator("button:has-text('Open')").click()
    expect(page.locator(".status-rows")).to_contain_text("of 30")

    page.click("[data-tool=connection]")
    chooser = page.locator(".dialog")
    expect(chooser).to_contain_text("Connection: ")
    expect(chooser.locator(".swap-current")).to_contain_text("NorthBooks")
    chooser.get_by_role("button", name="SouthBooks").click()
    expect(page.locator(".note-corner")).to_contain_text(": SouthBooks")
    expect(page.locator(".status-rows")).to_contain_text("of 12")
    expect(page.locator("[data-tool=connection]")).to_contain_text("Connection: SouthBooks")

    page.locator(".note-corner").get_by_role("button", name="Undo").first.click()
    expect(page.locator(".status-rows")).to_contain_text("of 30")
    page.close()
