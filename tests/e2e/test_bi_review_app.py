# ruff: noqa: F811
"""Test app one, the BI review (examples/bi_review), played through the pages in a real browser: built once
through the agent's commands on the browser tests' server (as tests/test_bi_review_app.py builds it), then
opened as a user opens it, and each page shows what was made: the grids by connection, the ERD, the Analyze
board, the Connections page's cards, the Environment's tabs and data.ipynb in the Notebooks page. Made-up
data (Larkfield Goods, small)."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from examples.bi_review import build as app
from playwright.sync_api import Browser, Page, expect
from tools.testbed import large_company

from swissarmybench.cli.commands import execute
from tests.e2e.test_table_cells_page import open_workbench
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_bi_review_app import answer

TABLES = ("orders", "order_lines", "customers", "monthly_sales", "sales_lines", "monthly_targets")


def agent(command: str, /, **args: Any) -> Any:
    return answer(execute(command, args))


@pytest.fixture(scope="module")
def review(server: dict[str, Any]) -> Path:
    """The app built once for the module: the project's folder."""
    tmp = Path(server["tmp"])
    data = tmp / "larkfield"
    large_company.build(data, "small", duckdb_file=True)

    @contextmanager
    def allow() -> Iterator[None]:
        done = threading.Event()

        def click() -> None:
            while not done.is_set():
                for asked in call(server, "GET", "/agent/approvals")["pending"]:
                    call(server, "POST", f"/agent/approvals/{asked['id']}", {"approve": True})
                time.sleep(0.05)

        helper = threading.Thread(target=click, daemon=True)
        helper.start()
        try:
            yield
        finally:
            done.set()
            helper.join(5)

    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    return app.build(agent, allow, data, tmp / "bi_review").folder


@pytest.fixture
def opened(server: dict[str, Any], review: Path) -> dict[str, str]:
    """The project opened as the user opens it (each test's own: the browser tests close it after each)."""
    call(server, "POST", "/project/open", {"path": str(review), "discard": True})
    grids: dict[str, str] = {}
    for grid in call(server, "GET", "/grids")["grids"]:
        grids.setdefault(grid["dataset"], grid["grid"])
    return grids


def page_of(browser: Browser, server: dict[str, Any], grid: str) -> Page:
    page = browser.new_context(viewport={"width": 1500, "height": 900}).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}&grid={grid}")
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=30000)
    return page


def area(page: Page, name: str) -> Any:
    return page.locator(f".nav-rail [data-area='{name}']")


def test_the_grids_are_grouped_by_connection_and_the_erd_draws_the_model(
    browser: Browser, server: dict[str, Any], opened: dict[str, str]
) -> None:
    assert set(TABLES) <= set(opened)
    page = page_of(browser, server, opened["monthly_sales"])
    for connection in ("Larkfield Warehouse", "Larkfield Archive", "Larkfield Files", "Targets"):
        expect(page.locator(f".tab-group[data-connections='{connection}']")).to_be_visible()
    expect(page.locator(".ag-header-cell[col-id='revenue']").first).to_be_attached()
    area(page, "erd").click()
    expect(page.locator(".workspace")).to_have_attribute("data-view", "erd")
    diagram = page.locator("#erd-view .erd-diagram svg")
    expect(diagram).to_be_visible(timeout=30000)
    for table in ("orders", "order_lines", "customers", "regions"):
        expect(diagram).to_contain_text(table)
    page.context.close()


def test_the_analyze_board_holds_every_analysiss_cards_and_the_connections_page_its_five_cards(
    browser: Browser, server: dict[str, Any], opened: dict[str, str]
) -> None:
    page = page_of(browser, server, opened["sales_lines"])
    area(page, "analyze").click()
    board = page.locator("#ai-panel .analyze-board")
    expect(board).to_be_visible(timeout=20000)
    expect(board.locator(".card").nth(20)).to_be_attached(timeout=30000)  # 14 analyses, two cards each
    area(page, "connections").click()
    cards = page.locator(".area-page[data-page='connections']")
    for name in ("Larkfield Files", "Larkfield Warehouse", "Larkfield Archive", "Store List", "Targets"):
        expect(cards.locator(f".connection-card[data-connection='{name}']")).to_be_visible()
    area(page, "environment").click()
    environment = page.locator('.area-page[data-page="environment"]')
    expect(environment).to_be_visible()
    expect(environment.locator('.env-row[data-name="monthly_sales"]')).to_be_visible(timeout=20000)
    expect(environment.locator('[data-count="table"]')).to_have_text(re.compile(r"^\d+$"))
    assert int(environment.locator('[data-count="table"]').inner_text()) >= len(TABLES)
    page.context.close()


def test_data_ipynb_opens_in_the_notebooks_page_with_its_sql_python_and_html_cells(
    browser: Browser, server: dict[str, Any], review: Path, opened: dict[str, str]
) -> None:
    workbench = open_workbench(browser, server, review / "data.ipynb")
    cells = workbench.locator(".wb-cell")
    expect(cells.first).to_be_visible(timeout=30000)
    expect(workbench.locator(".wb-cell.kind-html")).to_have_count(1)
    expect(workbench.locator(".wb-cell.kind-sql")).to_have_count(2)
    expect(workbench.locator(".wb-tcell").first).to_be_attached(timeout=30000)  # the tables' read-only cells
    expect(workbench.locator(".wb-cell", has_text="best_region").first).to_be_visible()
    workbench.context.close()
