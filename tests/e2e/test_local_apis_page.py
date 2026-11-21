# ruff: noqa: F811
"""Local sandbox APIs in a real browser (the owner, 2026-11-21: "transform scaffold create an app then test it
out
and then reset the data changes and try again"): a made-up table added to the sandbox from its grid's Table
row;
the APIs page's sandbox and Local sandbox APIs; New endpoint from a table; Run; Try it a POST; the change log
counting it; Reset back to the baseline; then an API table widget on a canvas, played, showing the endpoint's
rows.
Screenshots (scale 2) when SAB_API_SHOTS names a folder. Made-up data."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SAB_API_SHOTS")


def shot(page: Page, name: str, where: str = ".area-page") -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(500)
        page.locator(where).first.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def shop(server: dict[str, Any], tmp_path: Path) -> Iterator[Path]:
    close_tables(server)
    folder = tmp_path / "shop"
    call(server, "POST", "/project/new", {"path": str(folder)})
    frame = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4, 5],
            "region": ["West", "East", "West", "North", "South"],
            "amount": [10.5, 7.25, 3.0, 12.0, 4.5],
        }
    )
    push_client.push(frame, name="orders", new_grid=True)
    yield folder
    try:
        call(server, "POST", "/local-api/stop", {})
    except Exception:  # noqa: S110 (already stopped)
        pass
    close_tables(server)


def open_workspace(browser: Browser, server: dict[str, Any]) -> Page:
    page = browser.new_context(viewport={"width": 1500, "height": 1100}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace#token={server['token']}")
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=30000)
    return page


def test_sandbox_new_endpoint_run_try_a_post_and_reset(
    browser: Browser,
    server: dict[str, Any],
    shop: Path,
) -> None:
    page = open_workspace(browser, server)
    # The grid's Table row: Add to sandbox (its view, after its steps).
    page.locator(".ribbon-tools button", has_text="Add to sandbox").click()
    dialog = page.get_by_role("dialog", name="Add to sandbox")
    expect(dialog.get_by_label("Its name in the sandbox")).to_have_value("orders")
    dialog.get_by_role("button", name="Add").click()
    expect(page.locator(".toast", has_text="orders is in the sandbox")).to_be_visible(timeout=20000)
    # The APIs page: the sandbox, then Local sandbox APIs.
    page.locator(".nav-rail [data-area='apis']").click()
    panel = page.locator(".sandbox-panel")
    expect(panel.locator("tr[data-table='orders']")).to_contain_text("5")
    expect(panel.locator("tr[data-table='orders']")).to_contain_text("Plain DuckDB client")
    apis = page.locator(".local-apis")
    expect(apis.get_by_role("button", name="Run")).to_be_visible()
    # New endpoint from a table: the CRUD set in API.py.
    apis.get_by_role("button", name="New endpoint from a table…").click()
    made = page.get_by_role("dialog", name="New endpoint from a table")
    expect(made.get_by_label("Its key", exact=True)).to_be_visible()
    made.get_by_label("Its key", exact=True).select_option("order_id")
    made.get_by_role("button", name="Add to API.py").click()
    expect(apis.locator(".local-api-endpoint")).to_have_count(5, timeout=20000)
    assert "def create_orders" in (shop / "API.py").read_text(encoding="utf-8")
    expect(apis.locator(".local-api-endpoint[data-endpoint='list_orders'] .local-api-data")).to_have_text(
        "The sandbox (plain DuckDB)"
    )
    # Run.
    apis.get_by_role("button", name="Run").click()
    expect(apis.locator(".local-api-status.on")).to_contain_text(
        "Running on http://127.0.0.1:", timeout=30000
    )
    shot(page, "local-sandbox-apis-running")
    # Try it: a POST with its made-up body, edited.
    create = apis.locator(".local-api-endpoint[data-endpoint='create_orders']")
    create.get_by_role("button", name="Try it").click()
    body = create.get_by_label("Body")
    expect(body).to_contain_text('"order_id"')
    body.fill(json.dumps({"order_id": 6, "region": "West", "amount": 9.75}))
    create.get_by_role("button", name="Send").click()
    expect(create.locator(".local-api-said")).to_contain_text("201", timeout=20000)
    expect(panel.locator(".sandbox-log")).to_contain_text("orders: 1 inserted", timeout=20000)
    expect(apis.locator(".local-api-log tbody tr").first).to_contain_text("POST", timeout=20000)
    shot(page, "local-sandbox-api-try-it-post")
    # Open in Grids: the write is there.
    rows = call(server, "POST", "/sandbox/tables/open", {"table": "orders"})
    until(lambda: call(server, "GET", f"/grids/{rows['grid']}/count")["row_count"], 6)
    # Reset: back to the baseline.
    panel.get_by_role("button", name="Reset", exact=True).click()
    expect(panel.locator(".sandbox-log")).to_have_text("No changes since the baseline", timeout=20000)
    until(lambda: call(server, "GET", f"/grids/{rows['grid']}/count")["row_count"], 5)
    shot(page, "sandbox-after-reset")


@needs_streamlit
def test_an_api_table_widget_on_a_canvas_shows_the_endpoints_rows(
    browser: Browser,
    server: dict[str, Any],
    shop: Path,
) -> None:
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "orders"})
    call(server, "POST", "/local-api/scaffold", {"table": "orders", "key": "order_id"})
    assert call(server, "POST", "/local-api/run", {})["running"]
    made = call(server, "POST", "/streamlit/canvases", {"name": "Orders", "folder": str(shop)})
    canvas = made["canvas"]
    call(
        server,
        "POST",
        f"/streamlit/canvases/{canvas}/command",
        {"kind": "insert_widget", "widget": "api_table"},
    )
    found = call(server, "GET", f"/streamlit/canvases/{canvas}")["model"]

    def nodes(children: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for child in children:
            yield child
            yield from nodes(child.get("children") or [])

    widget = next(c for c in nodes(found["pages"][0]["children"]) if c.get("widget") == "api_table")
    call(
        server,
        "POST",
        f"/streamlit/canvases/{canvas}/command",
        {"kind": "set_values", "id": widget["id"], "values": {"endpoint": "GET /orders", "page_size": 3}},
    )
    shapes = call(server, "GET", "/local-api/shapes")
    assert shapes["uses"][0]["problems"] == [] and shapes["ok"]
    page = open_canvas(browser, server, Path(made["path"]))
    page.locator(f".cvs-widget[data-id='{widget['id']}']").click()
    picker = page.locator(".cvs-props .wg-prop[data-property='endpoint'] select")
    expect(picker).to_have_value("GET /orders")
    assert "POST /orders" in picker.locator("option").all_inner_texts()
    page.locator(".cvs-top .cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    expect(frame.get_by_text("Page 1")).to_be_visible(timeout=120000)
    expect(frame.locator("[data-testid='stDataFrame']")).to_be_visible(timeout=60000)
    if SHOTS:
        page.wait_for_timeout(2500)
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / "canvas-api-table-playing.png"))
