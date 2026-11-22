# ruff: noqa: F811
"""Test app two, the field service app (examples/field_service, made by the app through the agent's commands:
tests/test_field_service_app.py), in a real browser: its three canvas pages played, and one loop through them
as a dispatcher clicks it: the visits to do listed for everyone, one marked done with a note (an Event that
calls the app's own endpoint, sets a page value and reruns), the work order changed in the sandbox, the
page value seen on the second page, the invoices that differ counted on the third. Made-up data (Brightline
Field Services, tests/field_service_data.py). Screenshots (scale 2) when SAB_APP_SHOTS names a folder."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, FrameLocator, Page, expect

from tests import field_service_data as data
from tests.api_standins import Service
from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.field_service_app import CANVAS, EXAMPLE, Agent, Approver, depot_connection, fill_sandbox
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SAB_APP_SHOTS")
# The first visit to do (scheduled) in the work orders' own order: the one the visit card picks first.
FIRST, SECOND = [o for o in data.work_orders() if o["status"] == "scheduled"][:2]


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def api(server: dict[str, Any], method: str, path: str) -> Any:
    """The local sandbox API, called as the user's Try it calls it."""
    said = call(server, "POST", "/local-api/call", {"method": method, "path": path})
    assert int(said["status"]) < 300, said
    return said["body"]


@pytest.fixture
def app(server: dict[str, Any], tmp_path: Path) -> Iterator[dict[str, Any]]:
    close_tables(server)
    folder = tmp_path / "field_service"
    shutil.copytree(EXAMPLE, folder, ignore=shutil.ignore_patterns("sandbox", "builds", "exports"))
    agent = Agent()  # the e2e server's door (SWISSARMYBENCH_INFO names it)
    approver = Approver(server["port"], server["token"]).start()
    orders = Service().start()  # the other API the third page reads
    try:
        names = {c["name"] for c in agent("connections_list")["connections"]}
        if "Depot" not in names:
            agent("connections_create", **depot_connection(tmp_path, keyring=False))
        agent("connections_api_add", spec_url=orders.url + "/openapi.json", auth={"type": "none"})
        agent("project_open", path=str(folder), discard=True)
        listed = call(server, "GET", "/streamlit/widgets")["widgets"]
        assert next(w for w in listed if w["name"] == "visit_card")["where"] == "project"
        for name in ("technicians", "customers"):
            agent("datasets_load", name=name, path=str(folder / "source" / f"{name}.csv"))
        fill_sandbox(agent, folder)
        assert agent("api", action="run")["running"]
        yield {"folder": folder, "agent": agent}
    finally:
        try:
            agent("api", action="stop")
        except Exception:  # noqa: S110 (already stopped)
            pass
        close_tables(server)
        approver.stop()
        orders.stop()


def no_failures(frame: FrameLocator) -> None:
    """No widget on the page failed in its place ("input_text (w13) failed: ..."): each one drew."""
    page_frame = frame.locator("body")
    expect(page_frame).not_to_contain_text(re.compile(r"\(w\d+\) failed:"), timeout=30000)


def to_page(frame: FrameLocator, name: str) -> None:
    frame.locator("[data-testid='stSidebarNav'] a", has_text=name).click()
    expect(frame.get_by_text(name).first).to_be_visible(timeout=60000)


@needs_streamlit
def test_dispatch_marks_a_visit_done_and_the_other_pages_follow(
    browser: Browser, server: dict[str, Any], app: dict[str, Any]
) -> None:
    key = FIRST["work_order_id"]
    assert api(server, "GET", f"/work_orders/{key}")["status"] == "scheduled"
    page = open_canvas(browser, server, app["folder"] / CANVAS)
    expect(page.locator(".cvs-tab")).to_have_text(["Dispatch", "Work order", "Parts and billing"])
    shot(page, "canvas-dispatch")
    page.locator(".cvs-bottom button", has_text="Phone").click()
    shot(page, "canvas-dispatch-phone")
    page.locator(".cvs-bottom button", has_text="Desktop").click()
    for pane in ("Widgets", "Properties"):  # the played page gets the window's width
        page.locator(".cvs-bottom button", has_text=pane).click()
    page.locator(".cvs-top .cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    # 1. Dispatch: the title, the visits to do for everyone (the viewer named), one marked done with a note.
    expect(frame.get_by_text("Brightline dispatch")).to_be_visible(timeout=120000)
    expect(frame.get_by_text("Visits to do")).to_be_visible(timeout=60000)
    expect(frame.get_by_text("technician: All")).to_be_visible(timeout=60000)
    visit = frame.get_by_role("combobox", name="Visit")
    expect(visit).to_have_value(str(key), timeout=60000)
    note = frame.get_by_label("Note")
    note.fill("filter swapped")
    note.press("Enter")
    page.wait_for_timeout(1000)
    shot(page, "play-dispatch")
    frame.get_by_role("button", name="Mark done").click()
    # The Event called POST /visits/done: the sandbox's work order is done, its note in the summary.
    until(lambda: api(server, "GET", f"/work_orders/{key}")["status"], "done", 60)
    assert api(server, "GET", f"/work_orders/{key}")["summary"].endswith("(filter swapped)")
    # ... then reran: the visit is no longer one to do (the next one is picked).
    expect(visit).to_have_value(str(SECOND["work_order_id"]), timeout=60000)
    no_failures(frame)
    shot(page, "play-dispatch-done")
    # Play follows live data: the next visit marked done from elsewhere (no click on the page) and the page
    # runs again by itself, its visit card reading the sandbox's work orders as they are now.
    done = {"work_order_id": SECOND["work_order_id"], "technician": "All", "note": "by phone"}
    said = call(server, "POST", "/local-api/call", {"method": "POST", "path": "/visits/done", "body": done})
    assert int(said["status"]) < 300, said
    expect(visit).not_to_have_value(str(SECOND["work_order_id"]), timeout=60000)
    expect(frame.get_by_text("technician: All")).to_be_visible(timeout=60000)
    # 2. Work order: the page value the Event set (last_visit), shown in its read-only box.
    to_page(frame, "Work order")
    expect(frame.get_by_label("Last visit marked done")).to_have_value(str(key), timeout=60000)
    no_failures(frame)
    shot(page, "play-work-order")
    # 3. Parts and billing: the reconciliation's metric, the two invoices off by 10.00.
    to_page(frame, "Parts and billing")
    expect(frame.locator("[data-testid='stMetric']", has_text="Invoices that differ")).to_contain_text(
        str(len(data.OFF)), timeout=60000
    )
    no_failures(frame)
    shot(page, "play-parts-and-billing")
    page.locator(".cvs-top .cvs-play").click()  # Stop
