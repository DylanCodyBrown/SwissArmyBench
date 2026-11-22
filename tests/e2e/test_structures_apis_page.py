# ruff: noqa: F811
"""Structures and the APIs page in a real browser (the owner, 2026-11-17): the APIs page from the rail (a
card, search across APIs, an operation's inputs and outputs, Author a call with its body edited in the
tree, Send: the answer in Structures with its lineage, Refresh's diff), and the Structures page (the tree
and the text in step, a step from a node's actions and the strip, Open as grid). Its own server; a
made-up orders service on 127.0.0.1 (tests/api_standins.py). Made-up data only.

With SWISSARMYBENCH_STRUCTURES_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.api_standins import Service
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_STRUCTURES_SHOTS")


@pytest.fixture(scope="module")
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("structures")
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
    }
    before = {name: os.environ.get(name) for name in variables}
    os.environ.update(variables)
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"])
    try:
        for _ in range(200):
            try:
                info = json.loads((tmp / "server.json").read_text())
                break
            except (OSError, ValueError):
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")
        yield info | {"tmp": tmp}
    finally:
        process.terminate()
        process.wait(timeout=20)
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def shot_of(where: Any, name: str) -> None:
    """One part of the page (the rail)."""
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        where.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def opened(browser: Browser, url: str, dark: bool = False) -> Page:
    page = browser.new_context(
        viewport={"width": 1400, "height": 900},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def test_the_apis_page_authors_a_call_into_structures(
    browser: Browser, own_server: dict[str, Any], service: Service
) -> None:
    server = own_server
    call(server, "POST", "/apis", {"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}})
    form = {
        "title": "Shop",
        "base_url": service.url + "/v1",
        "endpoints": [{"path": "/products", "table": True}, {"path": "/regions"}],
    }
    call(server, "POST", "/apis", {"form": form})
    url = push_client.push(pd.DataFrame({"region": ["North", "South"], "sales": [12, 30]}), name="regions")
    page = opened(browser, url)

    # The rail's APIs: its page, a card each; the Connections page has none of them.
    page.locator('.nav-rail [data-area="apis"]').click()
    found = page.locator('.area-page[data-page="apis"]')
    expect(found).to_be_visible()
    expect(page).to_have_url(re.compile(r"[?&]open=apis\b"))
    expect(page.locator('.nav-rail [data-area="apis"]')).to_have_attribute("aria-current", "page")
    expect(found.locator(".api-card")).to_have_count(2)
    expect(found.locator('.api-card[data-api="Orders"]')).to_contain_text("5 operations")
    shot(page, "apis-cards")
    shot_of(page.locator(".nav-rail"), "rail")

    # One search box across every API.
    found.locator(".apis-search").fill("regions")
    results = found.locator(".api-result")
    expect(results).to_have_count(2)
    expect(results.first.locator("mark").first).to_have_text(re.compile("regions", re.I))
    shot(page, "apis-search")
    found.locator(".apis-search").fill("")
    expect(found.locator(".api-card")).to_have_count(2)

    # The explorer: operations by tag down the left, the chosen one's inputs and outputs on the right.
    found.locator('.api-card[data-api="Orders"] .api-card-open').click()
    expect(found.locator(".api-op[data-operation]")).to_have_count(5)
    found.locator('.api-op[data-operation="create_order"]').click()
    detail = found.locator(".api-detail")
    expect(detail.locator(".api-op-title")).to_contain_text("/orders")
    expect(detail.locator(".api-inputs .structure-tree").first).to_contain_text("amount")
    expect(detail.locator(".api-outputs")).to_contain_text("201")
    shot(page, "apis-explorer")

    # Author a call: the body seeded from the example, edited in the tree (the text follows), checked.
    detail.locator(".api-author").click()
    screen = found.locator(".api-author-screen")
    expect(screen).to_be_visible()
    amount = screen.locator('.api-body-tree .structure-row[data-path="$.amount"] .structure-value')
    amount.dblclick()
    screen.locator(".structure-edit").fill("42.5")
    screen.locator(".structure-edit").press("Enter")
    expect(screen.locator('.api-body-tree .structure-row[data-path="$.amount"]')).to_contain_text("42.5")
    expect(screen.locator(".api-body-text")).to_contain_text("42.5", timeout=15000)
    status = screen.locator('.api-body-tree .structure-row[data-path="$.status"] .structure-value')
    status.dblclick()
    screen.locator(".structure-edit").fill("lost")
    screen.locator(".structure-edit").press("Enter")
    expect(screen.locator(".api-body-problems")).to_contain_text("$.status is one of open, shipped")
    status = screen.locator('.api-body-tree .structure-row[data-path="$.status"] .structure-value')
    status.dblclick()
    screen.locator(".structure-edit").fill("open")
    screen.locator(".structure-edit").press("Enter")
    expect(screen.locator(".api-body-problems .error-note")).to_have_count(0)
    shot(page, "apis-author")

    # Send: the answer opens in Structures, the call its origin.
    screen.locator(".api-send").click()
    structures = page.locator('.area-page[data-page="structures"]')
    expect(structures).to_be_visible(timeout=20000)
    expect(structures.locator(".structures-origin")).to_contain_text("POST /orders")
    expect(structures.locator(".structures-status")).to_have_text("201")
    expect(structures.locator('.structure-row[data-path="$.amount"]')).to_contain_text("42.5")
    shot(page, "structures-result")
    structures.locator(".structures-toolbar button", has_text="Lineage").click()
    lineage = page.locator("dialog.structures-lineage")
    expect(lineage).to_be_visible()
    expect(lineage.locator(".structures-lineage-list")).to_contain_text("POST /orders")
    expect(lineage.locator("svg").first).to_be_visible(timeout=20000)
    shot(page, "structures-lineage")
    lineage.locator(".dialog-close, button[aria-label='Close']").first.click()

    # Return as table, authored: the DuckDB query shows while it is on, and on the operation once saved.
    page.locator('.nav-rail [data-area="apis"]').click()
    found = page.locator('.area-page[data-page="apis"]')
    found.locator('.api-card[data-api="Orders"] .api-card-open').click()
    found.locator('.api-op[data-operation="list_orders"]').click()
    found.locator(".api-detail .api-author").click()
    screen = found.locator(".api-author-screen")
    expect(screen.locator(".api-conversion")).to_be_hidden()
    screen.get_by_label("Return as table").check()
    screen.get_by_label("Records path").fill("$.items")
    expect(screen.locator(".api-conversion")).to_be_visible()
    screen.get_by_role("button", name="Save as web call").click()
    expect(page.locator(".toast").last).to_contain_text("[Orders].list_orders", timeout=15000)
    screen.get_by_role("button", name="Back").click()
    found.locator('.api-op[data-operation="list_orders"]').click()
    query = found.locator(".api-detail .api-conversion")
    query.locator("summary").click()
    expect(query.get_by_label("The DuckDB query")).to_have_value(re.compile(r"response", re.S))
    shot(page, "apis-duckdb-query")

    # Refresh: what changed, before it is applied.
    changed = service.openapi()
    del changed["paths"]["/regions"]
    changed["paths"]["/orders"]["get"]["parameters"].append(
        {"name": "since", "in": "query", "schema": {"type": "string"}}
    )
    original = service.openapi
    service.openapi = lambda: changed  # type: ignore[method-assign]
    try:
        page.goto(url.split("#")[0].split("?")[0].replace("/g/", "/workspace?g=") if False else url)
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        page.locator('.nav-rail [data-area="apis"]').click()
        found = page.locator('.area-page[data-page="apis"]')
        found.locator('.api-card[data-api="Orders"] button', has_text="Refresh").click()
        diff = page.locator("dialog.api-diff")
        expect(diff).to_be_visible()
        expect(diff.locator(".api-diff-removed")).to_contain_text("list_regions")
        expect(diff.locator(".api-diff-changed")).to_contain_text("parameter since (query) added")
        shot(page, "apis-refresh-diff")
        diff.locator("button", has_text="Apply").click()
        expect(diff).to_be_hidden()
    finally:
        service.openapi = original  # type: ignore[method-assign]
    page.context.close()


def test_the_structures_page_keeps_tree_and_text_in_step(
    browser: Browser, own_server: dict[str, Any]
) -> None:
    server = own_server
    gates = server["tmp"] / "gates.json"
    gates.write_text(
        json.dumps(
            {
                "gates": [
                    {"name": "release", "on": True, "rollout": 50},
                    {"name": "beta", "on": False, "rollout": 5},
                    {"name": "dark mode", "on": True, "rollout": 100},
                ]
            }
        ),
        encoding="utf-8",
    )
    call(server, "POST", "/structures/open", {"path": str(gates)})
    url = push_client.push(pd.DataFrame({"a": [1]}), name="anything")
    for dark in (True, False):  # the dark picture first, before the steps
        page = opened(browser, url, dark)
        page.locator('.nav-rail [data-area="environment"]').click()
        page.locator('.area-page[data-page="environment"]').get_by_role(
            "tab", name=re.compile("^Structures")
        ).click()
        page.get_by_role("button", name="New, open or paste…").click()
        found = page.locator('.area-page[data-page="structures"]')
        expect(found).to_be_visible()
        expect(page).to_have_url(re.compile(r"[?&]open=structures\b"))
        found.locator(".structures-tab-name", has_text="gates").click()
        tree = found.locator(".structure-tree")
        expect(tree.locator('.structure-row[data-path="$.gates"]')).to_contain_text("list · 3")
        expect(found.locator(".structures-pane.text-pane")).to_contain_text("dark mode", timeout=15000)
        if dark:
            shot(page, "structures-dark")
            page.context.close()
            continue
        # A step from the selected node's actions: Filter the list; the text shows the result.
        tree.locator('.structure-row[data-path="$.gates"]').click()
        expect(found.locator(".structures-path")).to_have_text("$.gates")
        found.locator(".structures-node-actions button", has_text="Filter").click()
        dialog = page.locator("dialog[open]").last
        dialog.locator("input[aria-label='Field']").fill("on")
        dialog.locator("input[aria-label='Value']").fill("true")
        dialog.locator("button", has_text="Filter").last.click()
        expect(found.locator(".structures-step")).to_have_count(1)
        expect(found.locator(".structures-step")).to_contain_text("Keep $.gates where on = true")
        expect(tree.locator('.structure-row[data-path="$.gates"]')).to_contain_text("list · 2")
        expect(found.locator(".structures-pane.text-pane")).not_to_contain_text("beta", timeout=15000)
        # An edit in the tree is a step too; the text follows.
        found.locator('.structure-row[data-path="$.gates[0]"] .structure-caret').click()
        found.locator('.structure-row[data-path="$.gates[0].rollout"] .structure-value').dblclick()
        found.locator(".structure-edit").fill("75")
        found.locator(".structure-edit").press("Enter")
        expect(found.locator(".structures-step")).to_have_count(2)
        expect(found.locator(".structures-pane.text-pane")).to_contain_text("75", timeout=15000)
        shot(page, "structures-page")
        # Open as grid: the list of records as a table.
        found.locator('.structure-row[data-path="$.gates"]').click()
        found.locator(".structures-to-grid").click()
        expect(page.locator(".toast", has_text="Opened as a grid")).to_be_visible()
        datasets = {d["name"] for d in call(server, "GET", "/datasets")["datasets"]}
        assert "gates_gates" in datasets
        # A step's close button removes it.
        found.locator(".structures-step-x").last.click()
        expect(found.locator(".structures-step")).to_have_count(1)
        page.context.close()


def test_write_rows_with_a_call_dry_run_then_send(
    browser: Browser, own_server: dict[str, Any], service: Service
) -> None:
    server = own_server
    if not any(c["name"] == "Orders" for c in call(server, "GET", "/apis")["apis"]):
        call(server, "POST", "/apis", {"spec_url": service.url + "/openapi.json", "auth": {"type": "none"}})
    url = push_client.push(
        pd.DataFrame({"ref": ["a", "b"], "amount": [12.5, 3.0], "status": ["open", "shipped"]}),
        name="to_send",
    )
    page = opened(browser, url)
    page.locator('.nav-rail [data-area="apis"]').click()
    found = page.locator('.area-page[data-page="apis"]')
    found.locator('.api-card[data-api="Orders"] .api-card-open').click()
    found.locator('.api-op[data-operation="create_order"]').click()
    found.locator(".api-write").click()
    screen = found.locator(".api-write-screen")
    screen.get_by_label("The rows").select_option("to_send")
    expect(screen.locator('tr[data-field="body.amount"] select')).to_have_value("column:amount")
    before = len(service.posted)
    screen.locator(".api-dry-run").click()
    expect(screen.locator(".api-write-result")).to_contain_text("2 rows, 2 calls. Nothing was sent.")
    expect(screen.locator(".api-write-result pre").first).to_contain_text('"amount": 12.5')
    assert len(service.posted) == before
    shot(page, "apis-write-rows")
    screen.locator(".api-write-send").click()
    structures = page.locator('.area-page[data-page="structures"]')
    expect(structures).to_be_visible(timeout=20000)
    expect(structures.locator(".structures-origin")).to_contain_text("2 of 2 rows written")
    assert len(service.posted) == before + 2
    shot(page, "apis-write-rows-results")
    page.context.close()


def test_unnest_this_column_on_a_list_column(browser: Browser, own_server: dict[str, Any]) -> None:
    """A list column (as an API's answer keeps them): its right-click's Unnest this column, a SQL step."""
    answer = pd.DataFrame({"order_id": [1, 2], "lines": [["widget", "gadget"], ["bolt"]]})
    url = push_client.push(answer, name="nested_answer", new_grid=True)
    page = opened(browser, url)
    page.locator(".ag-header-cell[col-id='order_id'] .sab-header-name").click(button="right")
    expect(page.get_by_role("menuitem", name="Unnest this column")).to_have_count(0)  # not a list
    page.keyboard.press("Escape")
    page.locator(".ag-header-cell[col-id='lines'] .sab-header-name").click(button="right")
    page.get_by_role("menuitem", name="Unnest this column").click()
    expect(page.locator(".steps-strip")).to_contain_text("Unnest lines", timeout=15000)
    expect(page.locator(".ag-row[row-index='2']").first).to_contain_text("bolt", timeout=15000)
    shot(page, "unnest-a-list-column")
    page.context.close()
