"""The Environment page (the owner, 2026-11-21/22; Plans/environment.plan.md), in a real browser: the rail's
Environment, a tab for each kind, one search over every tab, a table that unfolds to its columns, Used in
links that go there, Remove with the "Also delete it in Python" tick, and the Libraries tab's Pin, Update and
Install against a made-up package index and made-up installs (tests/libraries_standin.py). Its own server.
Made-up names and values only."""

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
from tests import libraries_standin
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_ENVIRONMENT_SHOTS")
SECRET = "made-up-word-8842"


def _cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None}


NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {},
    "cells": [
        _cell("import duckdb\nimport pandas as pd"),
        _cell("late = orders[orders.amount > 50]"),
        _cell("%%sql\nSELECT region, count(*) FROM customers GROUP BY region"),
    ],
}


@pytest.fixture(scope="module")
def own_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("environment")
    index = libraries_standin.Index({"duckdb": "1.4.3", "pandas": "2.3.3", "polars": "1.36.0"})
    variables = {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "home" / "SwissArmyBench"),
        "PYTHON_KEYRING_BACKEND": "tests.file_keyring.FileKeyring",
        "SAB_TEST_KEYRING_FILE": str(tmp / "keyring.json"),
        "SWISSARMYBENCH_PACKAGE_INDEX": index.url,
        "SWISSARMYBENCH_LIBRARIES_STANDIN": str(Path(libraries_standin.__file__).resolve()),
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
        yield info | {"tmp": tmp, "index": index}
    finally:
        try:
            call(info, "POST", "/project/close", {"discard": True})
        except Exception:  # noqa: S110 (the server is going anyway)
            pass
        process.terminate()
        process.wait(timeout=20)
        index.close()
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def row(page: Page, name: str) -> Any:
    return page.locator(f'.env-row[data-name="{name}"]')


def test_the_environment_page(browser: Browser, own_server: dict[str, Any]) -> None:  # noqa: F811
    server = own_server
    project = server["tmp"] / "work" / "month_end"
    call(server, "POST", "/project/new", {"path": str(project)})
    (project / "analysis.ipynb").write_text(json.dumps(NOTEBOOK), encoding="utf-8")
    libraries_standin.make_venv(project, {"duckdb": "1.4.2", "pandas": "2.3.3", "pip": "25.0"})
    (project / "requirements.txt").write_text("duckdb\npandas\n", encoding="utf-8")
    orders = pd.DataFrame(
        {
            "order_id": [100001, 100002, 100003],
            "customer_id": [4417, 2093, None],
            "amount": [12.5, 9840.0, 77.25],
        }
    )
    customers = pd.DataFrame(
        {"customer_id": [4417, 2093], "name": ["Avery Lane", "Brook Tide"], "region": ["North", "South"]}
    )
    push_client.push(customers, name="customers")
    push_client.push(pd.DataFrame({"note": ["made up"]}), name="scratch")
    url = push_client.push(orders, name="orders")
    call(server, "PUT", "/variables", {"name": "CUSTOMER_API", "value": "https://api.larkfield.example"})
    call(server, "PUT", "/variables", {"name": "WAREHOUSE_PASSWORD", "value": SECRET, "from": "keyring"})
    # A Python session holds scratch too (its watcher's report): the row is "In Python".
    session = {
        "label": "analysis.ipynb",
        "pid": 4242,
        "tables": [{"name": "scratch", "kind": "dataframe", "rows": 1, "columns": 1}],
        "variables": [{"name": "tax_rate", "type": "float", "size": ""}],
        "ran": 1,
    }
    call(server, "POST", "/processes/s1/sync", session)

    page = browser.new_context(
        viewport={"width": 1360, "height": 860}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)

    # ----- the rail's Environment: one page, a tab for each kind -----
    page.locator('.nav-rail [data-area="environment"]').click()
    found = page.locator('.area-page[data-page="environment"]')
    expect(found).to_be_visible()
    expect(page).to_have_url(re.compile(r"[?&]open=environment\b"))
    expect(page.locator('.nav-rail [data-area="environment"]')).to_have_attribute("aria-current", "page")
    expect(page.locator('.nav-rail [data-area="variables"]')).to_have_count(0)
    expect(page.locator('.nav-rail [data-area="structures"]')).to_have_count(0)
    tabs = found.get_by_role("tab")
    expect(tabs).to_have_text(
        [
            re.compile("^Tables"),
            re.compile("^Variables"),
            re.compile("^Structures"),
            re.compile("^Settings and secrets"),
            re.compile("^Libraries"),
        ]
    )
    expect(found.locator('[data-count="table"]')).to_have_text("3")
    expect(found.locator(".env-head")).to_contain_text("Rows by columns")
    expect(row(page, "orders")).to_contain_text("3 × 3")
    expect(row(page, "orders")).to_contain_text("In 1 grid")  # a grid is a view of the table, never a copy
    expect(row(page, "scratch")).to_contain_text("In Python")
    expect(found).to_contain_text("Updates by itself as your code runs")
    expect(found.get_by_role("button", name="Refresh")).to_have_count(0)  # it follows the notices by itself
    shot(page, "environment-tables-light")

    # ----- it follows the app by itself: a table that arrives is listed with no Refresh -----
    push_client.push(pd.DataFrame({"region": ["North"], "target": [180000]}), name="targets")
    expect(row(page, "targets")).to_be_visible(timeout=15000)
    expect(found.locator('[data-count="table"]')).to_have_text("4")

    # ----- one search over every tab: the counts light up, a line names the other tabs -----
    search = found.get_by_role("searchbox", name="Search the environment")
    search.fill("cust")
    expect(found.locator('[data-count="table"]')).to_have_text("2")
    expect(found.locator('[data-count="table"]')).to_have_class(re.compile("hot"))
    expect(found.locator(".env-hint")).to_have_text("Also matches in Settings and secrets (1)")
    expect(row(page, "customers").locator(".env-name mark")).to_have_text("cust")
    # orders matched in its look and inside: its column is one of the rows that matched.
    expect(row(page, "targets")).to_have_count(0)
    shot(page, "environment-search-light")
    found.locator(".env-hint").get_by_role("button").click()
    expect(found.get_by_role("tab", name=re.compile("^Settings and secrets"))).to_have_attribute(
        "aria-selected", "true"
    )
    expect(row(page, "CUSTOMER_API")).to_contain_text("https://api.larkfield.example")
    search.fill("")
    # A secret is masked, and its value is nowhere on the page.
    expect(row(page, "WAREHOUSE_PASSWORD")).to_contain_text("••••••••")
    assert SECRET not in page.content()
    shot(page, "environment-settings-light")

    # ----- a table unfolds in place to its columns: type, range, blanks -----
    found.get_by_role("tab", name=re.compile("^Tables")).click()
    row(page, "orders").locator(".env-twist").click()
    kids = found.locator('.env-child[data-parent="table:orders"]')
    expect(kids).to_have_count(3)
    expect(kids.nth(1)).to_contain_text("customer_id")
    expect(kids.nth(1)).to_contain_text("2093.0 to 4417.0 · 1 blank", timeout=15000)
    # The keys: Left closes, Right opens, Down moves.
    row(page, "orders").click()
    page.keyboard.press("ArrowLeft")
    expect(kids).to_have_count(0)
    page.keyboard.press("ArrowRight")
    expect(kids).to_have_count(3)

    # ----- Used in: every place that uses it, each a link that goes there -----
    side = found.locator(".env-side")
    expect(side.locator(".env-side-name")).to_have_text("orders")
    used = side.locator(".env-used")
    expect(used).to_contain_text("analysis.ipynb · cell 2")
    expect(used.locator('[data-used-kind="grid"]')).to_have_text("orders")
    shot(page, "environment-viewer-light")
    # The viewer folds away with Ctrl+B and comes back.
    page.keyboard.press("Control+b")
    expect(found.locator(".env")).to_have_class(re.compile("env-folded"))
    page.keyboard.press("Control+b")
    expect(side.locator(".env-used")).to_be_visible()
    used.locator('[data-used-kind="grid"]').click()
    expect(found).to_be_hidden()
    expect(page.locator(".ag-row[row-index='0']:visible").first).to_be_visible()
    page.locator('.nav-rail [data-area="environment"]').click()
    expect(found).to_be_visible()

    # ----- Remove, with the tick for a table Python holds too -----
    row(page, "scratch").click()
    page.keyboard.press("Delete")
    dialog = page.locator("dialog.env-dialog[open]")
    expect(dialog).to_contain_text("Remove scratch")
    tick = dialog.get_by_label("Also delete it in Python")
    expect(tick).not_to_be_checked()  # off by default
    tick.check()
    with page.expect_request(lambda r: r.url.endswith("/environment/remove")) as sent:
        dialog.get_by_role("button", name="Remove").click()
    assert sent.value.post_data_json == {"kind": "table", "name": "scratch", "python": True}
    expect(dialog).to_be_hidden()
    assert "scratch" not in [d["name"] for d in call(server, "GET", "/datasets")["datasets"]]

    # ----- Libraries: Pin, Update (a made-up index, asked when the tab opens), Install a library… -----
    found.get_by_role("tab", name=re.compile("^Libraries")).click()
    expect(row(page, "duckdb")).to_contain_text("1.4.2")
    update = row(page, "duckdb").get_by_role("button", name="→ 1.4.3")
    expect(update).to_be_visible(timeout=15000)  # the index was asked when the tab opened
    expect(row(page, "pandas")).to_contain_text("latest")
    expect(row(page, "pandas")).to_contain_text("1 place")  # imported in analysis.ipynb
    expect(row(page, "pip")).to_have_count(0)  # nobody chose it
    assert "duckdb" in server["index"].asked
    shot(page, "environment-libraries-light")
    row(page, "duckdb").get_by_role("button", name="Pin").click()
    expect(row(page, "duckdb").locator(".env-pin")).to_have_text("Pinned")
    assert (project / "requirements.txt").read_text() == "duckdb==1.4.2\npandas\n"
    expect(found.get_by_role("button", name=re.compile("Update all not pinned"))).to_have_count(0)  # pinned
    update.click()
    prompt = page.locator("dialog.missing-packages[open]")
    expect(prompt).to_contain_text("duckdb==1.4.3")
    prompt.get_by_role("button", name="Install now").click()
    expect(row(page, "duckdb")).to_contain_text("1.4.3", timeout=20000)
    expect(row(page, "duckdb").get_by_role("button", name="→ 1.4.3")).to_have_count(0)
    assert (
        project / "requirements.txt"
    ).read_text() == "duckdb==1.4.3\npandas\n"  # pinned at its new version
    found.get_by_role("button", name="Install a library…").click()
    asking = page.locator("dialog.env-dialog[open]")
    asking.get_by_label("Library").fill("polars")
    asking.get_by_role("button", name="Install…").click()
    prompt = page.locator("dialog.missing-packages[open]")
    prompt.get_by_role("button", name="Install now").click()
    expect(row(page, "polars")).to_contain_text("1.36.0", timeout=20000)
    assert (project / "requirements.txt").read_text() == "duckdb==1.4.3\npandas\npolars\n"

    # ----- the address keeps the tab and the row; the old Variables address still opens its page -----
    expect(page).to_have_url(re.compile(r"[?&]at=library\b"))
    page.reload()
    expect(
        page.locator('.area-page[data-page="environment"]').get_by_role("tab", name=re.compile("^Libraries"))
    ).to_have_attribute("aria-selected", "true", timeout=20000)

    if SHOTS:  # the same page in the dark theme
        dark = browser.new_context(
            viewport={"width": 1360, "height": 860}, device_scale_factor=2, color_scheme="dark"
        ).new_page()
        dark.goto(url)
        expect(dark.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        dark.locator('.nav-rail [data-area="environment"]').click()
        expect(row(dark, "orders")).to_be_visible()
        row(dark, "orders").locator(".env-twist").click()
        expect(dark.locator('.env-child[data-parent="table:orders"]').nth(1)).to_contain_text(
            "blank", timeout=15000
        )
        shot(dark, "environment-tables-dark")
        dark.get_by_role("tab", name=re.compile("^Libraries")).click()
        expect(row(dark, "duckdb")).to_be_visible()
        shot(dark, "environment-libraries-dark")
        dark.get_by_role("tab", name=re.compile("^Settings and secrets")).click()
        expect(row(dark, "WAREHOUSE_PASSWORD")).to_be_visible()
        shot(dark, "environment-settings-dark")
