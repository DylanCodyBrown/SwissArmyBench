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
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
    # The grid's Table row: Make a sandbox variant (its view, after its steps), named by the user.
    page.locator(".ribbon-tools button", has_text="Make a sandbox variant").click()
    dialog = page.get_by_role("dialog", name="Make a sandbox variant")
    expect(dialog.get_by_label("Its name")).to_have_attribute("placeholder", "orders · sandbox")
    dialog.get_by_label("Its name").fill("orders")
    dialog.get_by_role("button", name="Make").click()
    expect(page.locator(".toast", has_text="orders is in the sandbox")).to_be_visible(timeout=20000)
    # The APIs page: the sandbox, then Local sandbox APIs.
    page.locator(".nav-rail [data-area='apis']").click()
    panel = page.locator(".sandbox-panel")
    expect(panel.locator("tr[data-table='orders']")).to_contain_text("5")
    expect(panel.locator("tr[data-table='orders']")).to_contain_text("Plain DuckDB client")
    apis = page.locator(".local-apis")
    expect(apis.get_by_role("button", name="Run")).to_be_visible()
    # One slim bar (the blade IDE's): Properties closed until asked for, its target there; the rest in "…".
    bar = apis.locator(".local-api-bar")
    expect(bar.get_by_role("button")).to_have_count(4)  # Run, Open API.py, Properties, More
    expect(apis.locator(".local-api-props")).to_be_hidden()
    bar.get_by_role("button", name="Properties").click()
    expect(apis.locator(".local-api-props").get_by_label("Its target")).to_be_visible()
    shot(page, "api-slim-bar-properties", ".local-apis")
    bar.get_by_role("button", name="Properties").click()
    # New endpoint from a table (the bar's "…"): the CRUD set in API.py.
    bar.get_by_role("button", name="More").click()
    page.get_by_role("menuitem", name="New endpoint from a table…").click()
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


def test_a_refusal_in_place_a_try_it_kept_over_a_restart_and_api_py_on_the_scripts_page(
    browser: Browser,
    server: dict[str, Any],
    shop: Path,
) -> None:
    """The critic's fixes (2026-11-21): Try it's refusal is the one error note with API.py's line; an open Try
    it keeps what was typed when API.py is saved and the API starts again; an export with no rows warns in the
    dialog; API.py on the Scripts page takes no Tables group (its header stays its first line) and its main
    Run is Run API."""
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "orders"})
    call(server, "POST", "/local-api/scaffold", {"table": "orders", "key": "order_id"})
    assert call(server, "POST", "/local-api/run", {})["running"]
    page = open_workspace(browser, server)
    page.locator(".nav-rail [data-area='apis']").click()
    apis = page.locator(".local-apis")
    create = apis.locator(".local-api-endpoint[data-endpoint='create_orders']")
    create.get_by_role("button", name="Try it").click()
    # The made-up body is the server's (the endpoint's `try`), from its model.
    state = call(server, "GET", "/local-api")
    made_up = next(e for e in state["endpoints"] if e["name"] == "create_orders")["try"]["body"]
    assert json.loads(create.get_by_label("Body").input_value()) == made_up
    # A refusal: the error note, where in API.py, Go to line; the answer's JSON behind Details.
    create.get_by_label("Body").fill('{"order_id": "seven"}')
    create.get_by_role("button", name="Send").click()
    note = create.locator(".error-note")
    # The body is checked against its model before the endpoint runs: 422 naming the field.
    expect(note).to_contain_text("row.order_id is a whole number, not 'seven'.", timeout=20000)
    expect(note).to_contain_text(re.compile(r"API\.py line \d+"))
    expect(note.get_by_role("button", name="Go to line")).to_be_visible()
    expect(create.locator(".local-api-said.bad")).to_contain_text("422")
    expect(apis.locator(".local-api-log tbody tr").first).to_contain_text("whole number", timeout=20000)
    shot(page, "try-it-refusal-in-place")
    # API.py saved from elsewhere: the API starts again, and the open Try it keeps what was typed.
    create.get_by_label("Body").fill('{"order_id": 77, "region": "North"}')
    was = call(server, "GET", "/local-api")["running"]["port"]
    api_py = shop / "API.py"
    api_py.write_text(api_py.read_text(encoding="utf-8") + "\n# a note\n", encoding="utf-8")
    until(lambda: (call(server, "GET", "/local-api")["running"] or {}).get("port", was) != was, True, 30)
    page.wait_for_timeout(1500)  # the page's redraw after the notice
    expect(create.get_by_label("Body")).to_have_value('{"order_id": 77, "region": "North"}')
    expect(create.locator(".local-api-try")).to_be_visible()
    create.get_by_role("button", name="Send", exact=True).click()
    expect(create.locator(".local-api-said")).to_contain_text("201", timeout=20000)
    expect(create.locator(".error-note")).to_have_count(0)
    # Export with no rows: the warning is in the dialog, not only in README.md.
    apis.locator(".local-api-bar").get_by_role("button", name="More").click()
    page.get_by_role("menuitem", name="Export…").click()
    dialog = page.locator("dialog[open]")
    # Its target is asked once (New, or Properties): said here, never asked again.
    chosen = call(server, "GET", "/local-api")["settings"]["target"]
    label = next(
        t["label"] for t in call(server, "GET", "/local-api/targets")["targets"] if t["id"] == chosen
    )
    expect(dialog.locator(".local-api-target")).to_contain_text(label)
    expect(dialog.locator("select")).to_have_count(0)
    dialog.get_by_role("button", name="Export", exact=True).click()
    expect(dialog.locator(".error-note.warning")).to_contain_text("has no rows in this export", timeout=20000)
    shot(page, "export-warns-of-no-rows", "dialog[open]")
    # API.py on the Scripts page, a table open: no Tables group, not changed, Run API.
    before = api_py.read_text(encoding="utf-8")
    scripts = page.context.new_page()
    scripts.goto(
        f"http://127.0.0.1:{server['port']}/scripts?path={quote(str(api_py))}#token={server['token']}"
    )
    run = scripts.get_by_role("button", name="Run API")
    expect(run).to_be_visible(timeout=30000)
    scripts.wait_for_timeout(2500)  # the tables' arrangement would have come by now
    expect(scripts.locator(".view-lines").first).to_contain_text("swissarmybench-api")
    expect(scripts.locator(".view-lines").first).not_to_contain_text("region Tables")
    expect(scripts.locator(".line-numbers").first).to_have_text("1")
    expect(scripts.get_by_role("button", name="Run as scheduled")).to_have_count(0)
    # Try it beside the code: API.py's Endpoints panel, closed until its toggle opens it.
    expect(scripts.locator(".wb-mode-endpoints")).to_have_count(0)
    scripts.locator(".wb-mode-toggle-endpoints").click()
    pane = scripts.locator(".wb-mode-endpoints")
    expect(pane.locator(".local-api-endpoint")).to_have_count(5, timeout=20000)
    listing = pane.locator(".local-api-endpoint[data-endpoint='list_orders']")
    listing.get_by_role("button", name="Try it").click()
    listing.get_by_role("button", name="Send", exact=True).click()
    expect(listing.locator(".local-api-said")).to_contain_text("200", timeout=20000)
    if SHOTS:
        scripts.wait_for_timeout(500)
        scripts.screenshot(path=str(Path(SHOTS) / "api-py-endpoints-beside-the-code.png"))
    call(server, "POST", "/local-api/stop", {})
    run.click()
    expect(scripts.locator(".toast", has_text="Running on http://127.0.0.1:")).to_be_visible(timeout=30000)
    assert call(server, "GET", "/local-api")["running"]
    assert api_py.read_text(encoding="utf-8") == before
    if SHOTS:
        scripts.wait_for_timeout(500)
        scripts.screenshot(path=str(Path(SHOTS) / "api-py-run-api-on-the-scripts-page.png"))


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
