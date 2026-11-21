# ruff: noqa: F811
"""The widget contract on the Canvas in a real browser (the owner, 2026-11-21): a select's choices from a
table's column; an Excel upload's Out[Table] wired into a table widget's In[Table]; a form's Save event wired
to an API.py endpoint, the row landing in the project's sandbox. Each wire is made in the Properties pane's
Inputs and Events, then played. Screenshots (scale 2) when SAB_WIRING_SHOTS names a folder. Made-up data."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from swissarmybench_streamlit.domain import canvas_layouts as layouts
from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SAB_WIRING_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(800)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def project(server: dict[str, Any], tmp_path: Path) -> Iterator[Path]:
    close_tables(server)
    folder = tmp_path / "wired"
    call(server, "POST", "/project/new", {"path": str(folder)})
    yield folder
    try:
        call(server, "POST", "/local-api/stop", {})
    except Exception:  # noqa: S110 (not running)
        pass
    close_tables(server)


def canvas_with(
    server: dict[str, Any], folder: Path, *widgets: tuple[str, int, dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    made = call(server, "POST", "/streamlit/canvases", {"name": "Wired", "folder": str(folder)})
    canvas = made["canvas"]
    call(
        server,
        "POST",
        f"/streamlit/canvases/{canvas}/command",
        {"kind": "add_container", "x": 0, "y": 0, "w": 1200, "h": 1400},
    )
    ids = []
    for widget, y, values in widgets:
        state = call(
            server,
            "POST",
            f"/streamlit/canvases/{canvas}/command",
            {"kind": "insert_widget", "widget": widget, "parent": "c1", "x": 0, "y": y, "values": values},
        )
        ids.append(state["made"])
    return made, ids


def node(server: dict[str, Any], canvas: str, instance: str) -> dict[str, Any]:
    found: dict[str, Any] = layouts.find(
        call(server, "GET", f"/streamlit/canvases/{canvas}")["model"], instance
    )[2]
    return found


def props_of(page: Page, instance: str) -> Any:
    page.locator(f".cvs-widget[data-id='{instance}']").click()
    pane = page.locator(".cvs-props")
    expect(
        pane.locator("h3", has_text="INPUTS").or_(pane.locator("h3", has_text="EVENTS")).first
    ).to_be_visible()
    return pane


def play(page: Page) -> Any:
    page.locator(".cvs-top .cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    try:
        expect(frame.locator(".st-key-sab-page")).to_be_attached(timeout=120000)
    except AssertionError:
        shot(page, "wiring-play-failed")
        raise
    return frame


@needs_streamlit
def test_a_select_takes_its_choices_from_a_tables_column(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    push_client.push(
        pd.DataFrame({"store": ["Marshby Depot", "Fernhaven Shop", "Larkfield Shop", "Fernhaven Shop"]}),
        name="stores",
        new_grid=True,
    )
    made, (select,) = canvas_with(server, project, ("input_select", 0, {"label": "Store"}))
    page = open_canvas(browser, server, Path(made["path"]))
    pane = props_of(page, select)
    source = pane.locator(".cvs-port[data-port='options_table'] select.cvs-source")
    expect(source.locator("option[value='table:stores']")).to_have_count(1)
    source.select_option("table:stores")
    expect(
        pane.locator(".wg-prop[data-property='options_column'] select option[value='store']")
    ).to_have_count(1, timeout=15000)
    pane.locator(".wg-prop[data-property='options_column'] select").select_option("store")
    until(lambda: node(server, made["canvas"], select)["values"].get("options_column"), "store")
    wired = call(server, "GET", f"/streamlit/canvases/{made['canvas']}")
    assert wired["wiring"]["sources"][select]["options_table"] == {"table": "stores"}
    shot(page, "wiring-select-from-a-table")
    frame = play(page)
    frame.locator("[data-testid='stSelectbox']").first.click()
    options = frame.locator("[role='option']")
    expect(options.first).to_be_visible(timeout=60000)
    # Distinct and sorted.
    assert options.all_inner_texts()[:3] == ["Fernhaven Shop", "Larkfield Shop", "Marshby Depot"]


@needs_streamlit
def test_an_excel_upload_feeds_a_table_widget_through_its_out(
    browser: Browser, server: dict[str, Any], project: Path, tmp_path: Path
) -> None:
    pytest.importorskip("openpyxl")
    made, (upload, shown) = canvas_with(server, project, ("excel_upload", 0, {}), ("data_table", 700, {}))
    page = open_canvas(browser, server, Path(made["path"]))
    pane = props_of(page, shown)
    source = pane.locator(".cvs-port[data-port='table_name'] select.cvs-source")
    # Not wired by itself (another name), so wired by hand: the Page values group holds the upload's Out.
    option = source.locator(f"option[value='out:{upload}.uploaded']")
    expect(option).to_have_count(1)
    source.select_option(f"out:{upload}.uploaded")
    until(
        lambda: call(server, "GET", f"/streamlit/canvases/{made['canvas']}")["wiring"]["readers"].get(
            f"{upload}.uploaded"
        ),
        [f"{shown}.table_name"],
    )
    page.locator(".cvs-wiring-toggle").click()
    expect(page.locator(".cvs-wires .cvs-wire")).to_have_count(1)
    expect(page.locator(f".cvs-widget[data-id='{upload}']")).to_have_class(re.compile("wire-source"))
    page.locator(f".cvs-widget[data-id='{upload}']").click()
    expect(page.locator(".cvs-props .cvs-port[data-port='uploaded'] .cvs-readers")).to_have_text(
        f"Read by {shown} data_table · table_name"
    )
    shot(page, "wiring-upload-into-a-table")
    workbook = tmp_path / "parts.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame({"Part": ["Quillon bolt", "Tarrow hinge"], "Qty": [3, 9]}).to_excel(writer, index=False)
    frame = play(page)
    expect(frame.locator(f".st-key-sab-{shown} [role='grid']")).to_have_attribute(
        "aria-rowcount", "13", timeout=60000
    )
    frame.locator("[data-testid='stFileUploader'] input[type='file']").set_input_files(str(workbook))
    expect(frame.get_by_text("2 rows, 2 columns")).to_be_visible(timeout=60000)
    # The table widget shows the upload's rows: 2 and the header (the made-up sample before: 12).
    grid = frame.locator(f".st-key-sab-{shown} [role='grid']")
    expect(grid).to_have_attribute("aria-rowcount", "3", timeout=60000)
    shot(page, "wiring-upload-played")


@needs_streamlit
def test_a_forms_save_event_calls_an_api_endpoint_and_the_row_lands_in_the_sandbox(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    push_client.push(
        pd.DataFrame(
            {
                "visit_id": [1, 2],
                "store": ["Larkfield Shop", "Marshby Depot"],
                "visitor": ["Ada Ashdown", "Bram Brookfield"],
            }
        ),
        name="visits",
        new_grid=True,
    )
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "visits"})
    call(server, "POST", "/local-api/scaffold", {"table": "visits", "key": "visit_id"})
    assert call(server, "POST", "/local-api/run", {})["running"]
    endpoints = call(server, "GET", "/streamlit/widgets/context")["endpoints"]
    create = next(e for e in endpoints if e.startswith("POST "))
    definition = {
        "name": "visit",
        "title": "Site visit",
        "fields": [
            {"name": "visit_id", "label": "Visit", "type": "number", "required": True},
            {"name": "store", "label": "Store", "type": "text", "required": True},
            {"name": "visitor", "label": "Visitor", "type": "text", "required": True},
        ],
    }
    made, (form,) = canvas_with(server, project, ("form_fill", 0, {"definition": definition}))
    page = open_canvas(browser, server, Path(made["path"]))
    pane = props_of(page, form)
    event = pane.locator(".cvs-port[data-port='saved']")
    event.locator("select.cvs-action-add").select_option("call")
    expect(event.locator(".cvs-action[data-action='call']")).to_be_visible(timeout=15000)

    def actions() -> Any:
        return call(server, "GET", f"/streamlit/canvases/{made['canvas']}")["wiring"]["sources"][form].get(
            "saved"
        )

    if event.locator(".cvs-action select").first.input_value() != create:
        event.locator(".cvs-action select").first.select_option(create)
    until(lambda: (actions() or {}).get("actions", [{}])[0].get("endpoint"), create)
    page.wait_for_timeout(300)  # the pane drawn again from the canvas's state
    body = page.locator(".cvs-props .cvs-port[data-port='saved']").get_by_label("Body", exact=True)
    expect(body).to_be_visible(timeout=15000)
    body.fill("values")
    body.press("Enter")

    until(actions, {"actions": [{"do": "call", "endpoint": create, "body": "values"}]})
    shot(page, "wiring-form-event")
    frame = play(page)
    frame.get_by_test_id("stNumberInputField").fill("3")
    frame.get_by_label("Store", exact=False).first.fill("Fernhaven Shop")
    frame.get_by_label("Visitor", exact=False).fill("Cleo Calloway")
    frame.get_by_role("button", name="Submit").click()
    expect(frame.get_by_text("Thank you")).to_be_visible(timeout=60000)
    opened = call(server, "POST", "/sandbox/tables/open", {"table": "visits"})
    until(lambda: call(server, "GET", f"/grids/{opened['grid']}/count")["row_count"], 3, seconds=30)
    shot(page, "wiring-form-row-landed")
