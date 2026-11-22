# ruff: noqa: F811
"""The forms and reconciliation app (examples/forms_recon, made by the app: the owner's first app POC,
2026-11-21) in a real browser: its three canvas pages played, and one full loop through them as a user clicks
it: a form designed and saved, a small Excel workbook uploaded for a month, the month reconciled against the
copy of a Trino table in the sandbox, and the differences seen. Made-up data (Larkfield Goods, small).
Screenshots (scale 2) when SAB_APP_SHOTS names a folder."""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from playwright.sync_api import Browser, FrameLocator, Page, expect

from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit
from tests.stress.test_local_api_stress import TABLES, source_files

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "forms_recon"
SHOTS = os.environ.get("SAB_APP_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


# A reconciliation's runs: the wizard's Search pattern over recon_runs (its recon_id a filter).
RUNS = "/recon_runs/search?recon_id=sales_ledger"


def api(server: dict[str, Any], method: str, path: str, body: Any = None) -> Any:
    """The local sandbox API, called as the user's Try it calls it."""
    path, _, text = path.partition("?")
    query = dict(part.split("=", 1) for part in text.split("&") if part)
    asked = (
        {"method": method, "path": path}
        | ({"query": query} if query else {})
        | ({"body": body} if body else {})
    )
    said = call(server, "POST", "/local-api/call", asked)
    assert int(said["status"]) < 300, said
    return said["body"]


@pytest.fixture
def app(server: dict[str, Any], tmp_path: Path) -> Iterator[dict[str, Any]]:
    close_tables(server)
    folder = tmp_path / "forms_recon"
    shutil.copytree(EXAMPLE, folder, ignore=shutil.ignore_patterns("sandbox", "builds", "exports"))
    call(server, "POST", "/project/open", {"path": str(folder), "discard": True})
    # The project's own widget: its widgets/ folder, shared with the project (never the library's).
    listed = call(server, "GET", "/streamlit/widgets")["widgets"]
    bridge = next(w for w in listed if w["name"] == "api_bridge")
    assert bridge["where"] == "project" and listed[0]["where"] == "project"
    trino, _ = source_files(tmp_path, "small")
    call(server, "POST", "/sandbox/tables", {"from": "file", "path": str(trino), "name": "trino_sales_lines"})
    for spec in TABLES:
        call(server, "POST", "/sandbox/tables", spec)
    assert call(server, "POST", "/local-api/run", {})["running"]
    yield {"folder": folder, "trino": trino, "tmp": tmp_path}
    try:
        call(server, "POST", "/local-api/stop", {})
    except Exception:  # noqa: S110 (already stopped)
        pass
    close_tables(server)


def workbook(trino: Path) -> tuple[bytes, dict[str, int]]:
    """October's first 30 lines as the month's Excel workbook (two amounts off, one line Trino has not got),
    and what reconciling October must say."""
    import openpyxl

    rows = duckdb.execute(
        f"SELECT order_line_id, period, store_id, amount FROM '{trino}' WHERE period = '2026-10' AND "
        f"order_line_id IN (SELECT order_line_id FROM '{trino}' GROUP BY 1 HAVING count(*) = 1) "
        "ORDER BY order_line_id LIMIT 30"
    ).fetchall()
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "October"
    sheet.append(["Line ID", "Period", "Store ID", "Amount"])
    for at, (line, period, store, amount) in enumerate(rows):
        sheet.append([line, period, store, round(amount + (5 if at in (3, 17) else 0), 2)])
    sheet.append([999_999_999, "2026-10", 1, 12.5])
    out = io.BytesIO()
    book.save(out)
    source = duckdb.execute(
        f"SELECT count(DISTINCT order_line_id), count(*) - count(DISTINCT order_line_id) FROM '{trino}' "
        "WHERE period = '2026-10'"
    ).fetchall()[0]
    dups = duckdb.execute(
        f"SELECT count(*) FROM (SELECT order_line_id FROM '{trino}' WHERE period = '2026-10' GROUP BY 1 "
        "HAVING count(*) > 1)"
    ).fetchall()[0]
    assert source is not None and dups is not None
    want = {
        "matched": 28,
        "differences": 2,
        "only_entries": 1,
        "duplicates": int(dups[0]),
        "only_source": int(source[0]) - 30 - int(dups[0]),
    }
    return out.getvalue(), want


def to_page(frame: FrameLocator, name: str) -> None:
    frame.locator("[data-testid='stSidebarNav'] a", has_text=name).click()
    expect(frame.get_by_text(name).first).to_be_visible(timeout=60000)


@needs_streamlit
def test_design_a_form_upload_excel_reconcile_a_month_and_see_the_differences(
    browser: Browser, server: dict[str, Any], app: dict[str, Any]
) -> None:
    data, want = workbook(app["trino"])
    excel = app["tmp"] / "october.xlsx"
    excel.write_bytes(data)
    page = open_canvas(browser, server, app["folder"] / "forms_recon.canvas.json")
    expect(page.locator(".cvs-tab")).to_have_text(["Form designer", "Fill and load", "Reconcile"])
    shot(page, "canvas-form-designer")
    page.locator(".cvs-bottom button", has_text="Phone").click()
    shot(page, "canvas-form-designer-phone")
    page.locator(".cvs-bottom button", has_text="Desktop").click()
    for pane in ("Widgets", "Properties"):  # the played page gets the window's width
        page.locator(".cvs-bottom button", has_text=pane).click()
    page.locator(".cvs-top .cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    # 1. Form designer: the Sales ledger starter, its title changed, saved through the API.
    expect(frame.get_by_text("Design it")).to_be_visible(timeout=120000)
    title = frame.get_by_label("Title")
    expect(title).to_have_value("Sales ledger", timeout=60000)
    title.fill("Larkfield sales ledger")
    title.press("Enter")
    frame.get_by_role("button", name="Save form").click()
    until(
        lambda: [(f["title"], f["fields"]) for f in api(server, "GET", "/forms")],
        [("Larkfield sales ledger", 4)],
        60,
    )
    assert [f["name"] for f in api(server, "GET", "/forms/sales_ledger")["fields"]] == [
        "line_id",
        "period",
        "store_id",
        "amount",
    ]
    shot(page, "play-form-designer-saved")
    # 2. Fill and load: the month's workbook uploaded, its columns matched, its rows loaded.
    to_page(frame, "Fill and load")
    expect(frame.get_by_text("Upload the month's workbook")).to_be_visible(timeout=60000)
    frame.locator("[data-testid='stFileUploader'] input[type='file']").set_input_files(str(excel))
    expect(frame.get_by_text("31 rows, 4 columns")).to_be_visible(timeout=60000)
    # Map columns keeps the matches it guessed for its made-up sample: two chosen by hand, as a user would.
    for field, column in (("line_id", "Line ID"), ("amount", "Amount")):
        box = frame.locator("[data-testid='stSelectbox']", has_text=field).first
        box.click()
        frame.get_by_role("option", name=column, exact=True).click()
        page.wait_for_timeout(1500)
    expect(frame.get_by_text("4 of 4 fields matched")).to_be_visible(timeout=60000)
    frame.get_by_role("button", name="Load the valid rows").click()
    until(
        lambda: [b["rows"] for b in api(server, "GET", "/forms/sales_ledger/batches?period=2026-10")],
        [31],
        60,
    )
    shot(page, "play-fill-and-load-excel")
    # 3. Reconcile: the definition saved once, October run, its differences listed.
    to_page(frame, "Reconcile")
    frame.get_by_role("button", name="Save the reconciliation").click()
    until(lambda: [r["recon_id"] for r in api(server, "GET", "/recons")], ["sales_ledger"], 60)
    frame.get_by_role("button", name="Run the reconciliation").click()
    # A run's row is listed as it starts and its counts are filled as it ends: wait for the counts.
    until(
        lambda: [{k: r[k] for k in want} for r in api(server, "GET", RUNS)],
        [want],
        120,
    )
    run = api(server, "GET", RUNS)[0]
    expect(frame.locator("[data-testid='stMetric']", has_text="Differences")).to_contain_text(
        "2", timeout=60000
    )
    expect(frame.locator("[data-testid='stDataFrame']").first).to_be_visible(timeout=60000)
    shot(page, "play-reconcile-differences")
    differences = api(server, "GET", f"/runs/{run['run_id']}/results?status=difference")
    assert len(differences) == 2 and all(abs(abs(d["difference"]) - 5) < 0.01 for d in differences)
    page.locator(".cvs-top .cvs-play").click()  # Stop
