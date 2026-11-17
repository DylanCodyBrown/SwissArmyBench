# ruff: noqa: F811
"""The Accounting extension in a real browser: an Accounting project's Excel canvas (a table, a pivot and a
chart placed on a sheet, a block moved and sized), Play's preview with its chart, Download; a template
imported and its places bound by clicking its cells; statements dry-run then built; the mode (the Excel
canvas offered, the Blades page showing Excel's families first, Show all) and a project of the base's type
without any of it. Made-up data only (tests/accounting_data.py).

With SWISSARMYBENCH_SHOTS set to a folder, the screenshots are saved there (2x)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.renamed import env
from tests import accounting_data as made_up
from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.test_accounting_statements import make_template

SHOTS = env("SWISSARMYBENCH_SHOTS") or None
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """The app with the Accounting extension on (from this checkout: SWISSARMYBENCH_EXTENSIONS)."""
    tmp = tmp_path_factory.mktemp("accounting")
    source = str(ROOT / "extensions" / "accounting" / "src")
    env_ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_EXTENSIONS": "streamlit,accounting",  # Streamlit: preinstalled
        "PYTHONPATH": os.pathsep.join([source, os.environ.get("PYTHONPATH", "")]).strip(os.pathsep),
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env_)
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def push(info: dict[str, Any], name: str, frame: Any) -> None:
    import io
    import urllib.request

    import pyarrow.ipc as ipc

    table = pa.Table.from_pandas(frame, preserve_index=False)
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/datasets/{name}",
        data=sink.getvalue(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {info['token']}",
            "Content-Type": "application/vnd.apache.arrow.stream",
            "X-Source-Kind": "arrow",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        assert response.status == 200


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def workbench(browser: Browser, server: dict[str, Any], path: Path | None = None) -> Page:
    context = browser.new_context(
        viewport={"width": 1500, "height": 950}, device_scale_factor=2 if SHOTS else 1, accept_downloads=True
    )
    page = context.new_page()
    opened = f"&open={quote(str(path))}" if path else ""
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}{opened}")
    return page


def choose(page: Page, button: str, item: str) -> None:
    page.get_by_role("button", name=button, exact=True).first.click()
    page.get_by_role("menuitem", name=item, exact=True).click()


def answered(page: Page, act: Any) -> None:
    """An action whose change the server answers (the canvas draws the answer before the next step)."""
    with page.expect_response(
        lambda r: "/accounting/designs/" in r.url and r.request.method in ("PATCH", "POST", "DELETE")
    ):
        act()
    page.wait_for_timeout(150)


def prop(page: Page, selector: str, value: str) -> None:
    """A Properties field filled and committed (its change event), the answer drawn."""
    field = page.locator(f".xc-props {selector}").first
    if field.input_value() == value:
        return
    field.fill(value)
    answered(page, lambda: field.press("Tab"))


def pick(page: Page, selector: str, value: str, nth: int = 0) -> None:
    answered(page, lambda: page.locator(f".xc-props {selector}").nth(nth).select_option(value))


def test_the_excel_canvas_play_templates_and_statements(browser: Browser, server: dict[str, Any]) -> None:
    push(server, "cessions", made_up.cessions())
    push(server, "statements", made_up.statements())
    push(server, "lines", made_up.lines())
    made = call(
        server,
        "POST",
        "/projects",
        {"folder": str(server["tmp"]), "name": "Made-up Re", "type": "accounting"},
    )
    folder = Path(made["folder"])
    assert call(server, "GET", "/app/mode")["mode"]["canvases"] == ["excel"]
    page = workbench(browser, server, folder / "workbook.design.json")
    canvas = page.locator(".xc")
    expect(canvas).to_be_visible(timeout=20000)
    expect(canvas.locator(".xc-block.xc-title")).to_have_count(1)
    # A table of the cessions, its premium as currency with a total.
    answered(page, lambda: choose(page, "Add a block", "Table"))
    expect(canvas.locator(".xc-block.xc-table")).to_have_count(1)
    prop(page, ".xc-source", "cessions")
    prop(page, ".xc-columns", "cedant, treaty, premium, claims")
    pick(page, '.xc-column[data-column="premium"] select', "currency")
    pick(page, '.xc-column[data-column="premium"] select', "sum", 1)
    prop(page, ".xc-cell-at", "A3")
    expect(canvas.locator(".xc-block.xc-table")).to_have_attribute("data-cell", "A3")
    # A pivot: claims by treaty and period, DuckDB's summary.
    answered(page, lambda: choose(page, "Add a block", "Pivot"))
    prop(page, ".xc-source", "cessions")
    prop(page, ".xc-rows", "treaty")
    prop(page, ".xc-pivot-columns", "period")
    prop(page, ".xc-value-column", "claims")
    pick(page, ".xc-value select", "sum")
    expect(page.locator(".xc-value select").first).to_have_value("sum")
    prop(page, ".xc-cell-at", "G3")
    # A chart of the pivot, moved by dragging and sized by its corner.
    answered(page, lambda: choose(page, "Add a block", "Chart"))
    chart = canvas.locator(".xc-block.xc-chart")
    expect(chart).to_have_count(1)
    pick(page, ".xc-chart-kind", "combo")
    prop(page, "input[placeholder='every number column']", "2026-Q1, 2026-Q2")
    prop(page, ".xc-field:has-text('As lines') input", "2026-Q2")
    chart.scroll_into_view_if_needed()
    box = chart.bounding_box()
    assert box is not None
    start = chart.get_attribute("data-cell")
    page.mouse.move(box["x"] + 30, box["y"] + 8)
    page.mouse.down()
    page.mouse.move(box["x"] + 30 + 76 * 6, box["y"] + 8 - 24 * 2, steps=8)
    answered(page, page.mouse.up)
    expect(chart).not_to_have_attribute("data-cell", start or "")
    moved = chart.get_attribute("data-cell")
    chart.scroll_into_view_if_needed()
    g = chart.locator(".xc-grip").bounding_box()
    assert g is not None
    page.mouse.move(g["x"] + 4, g["y"] + 4)
    page.mouse.down()
    page.mouse.move(g["x"] + 4 + 76 * 2, g["y"] + 4, steps=6)
    answered(page, page.mouse.up)
    expect(chart.locator(".xc-size")).to_contain_text(f"{moved} · 10×15")
    page.locator(".xc-board").evaluate("el => el.scrollTo(0, 0)")
    shot(page, "accounting-canvas")
    # Play: the workbook built from the open tables, each sheet as Excel draws it, its chart over it.
    page.get_by_role("button", name="Play", exact=True).click()
    preview = page.locator(".xc-played .xc-grid")
    expect(preview).to_be_visible(timeout=30000)
    expect(preview.locator("td", has_text="Ashgrove Mutual").first).to_be_visible()
    expect(page.locator(".xc-played .xc-chart-holder[data-kind='combo']")).to_have_count(1)
    expect(preview.locator("td", has_text="Total").first).to_be_visible()
    shot(page, "accounting-play")
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Download", exact=True).click()
    assert downloaded.value.suggested_filename.endswith(".xlsx")
    # Saved, then Export workbook.py beside it.
    answered(page, lambda: page.get_by_role("button", name="Save", exact=True).first.click())
    page.get_by_role("button", name="Export workbook.py", exact=True).click()
    expect(page.locator(".toast", has_text="workbook.py")).to_be_visible(timeout=10000)
    design = json.loads((folder / "workbook.design.json").read_text())
    assert [b["kind"] for b in design["sheets"][0]["blocks"]] == ["title", "table", "pivot", "chart"]
    assert "Ashgrove" not in (folder / "workbook.design.json").read_text()  # the design holds no data

    # A template imported (as the agent would), shown, and its places bound by clicking its cells.
    call(
        server,
        "POST",
        "/accounting/templates/import",
        {"source": str(make_template(server["tmp"] / "Statement.xlsx")), "name": "statement"},
        agent=True,
    )
    page.get_by_role("button", name="Edit", exact=True).click()
    choose(page, "Templates and statements", "Templates…")
    dialog = page.locator("dialog.xc-templates")
    dialog.get_by_role("button", name="statement", exact=True).click()
    sheet = dialog.locator(".xc-grid")
    expect(sheet.locator("td", has_text="Made-up Re")).to_be_visible()
    sheet.locator('td[data-cell="B3"]').click()
    expect(dialog.locator(".xc-bind-place")).to_have_value("Cedant")  # its named range
    dialog.locator(".xc-bind-what").fill("cedant")
    dialog.get_by_role("button", name="Bind", exact=True).click()
    expect(sheet.locator('td[data-cell="B3"] .xc-mark')).to_have_text("cedant")
    sheet.locator('td[data-cell="B4"]').click()
    dialog.locator(".xc-bind-what").fill("period")
    dialog.get_by_role("button", name="Bind", exact=True).click()
    expect(dialog.locator(".xc-bindings li")).to_have_count(2)
    sheet.locator('td[data-cell="F3"]').click()
    dialog.locator(".xc-bind-from").select_option("number")
    dialog.get_by_role("button", name="Bind", exact=True).click()
    expect(dialog.locator(".xc-bindings li")).to_have_count(3)
    sheet.locator('td[data-cell="A12"]').click()
    dialog.locator(".xc-bind-kind").select_option("table")
    dialog.locator(".xc-bind-what").fill("treaty, premium, claims, commission, balance")
    dialog.get_by_role("button", name="Bind", exact=True).click()
    expect(dialog.locator(".xc-bindings li")).to_have_count(4)
    shot(page, "accounting-template")
    # Statements: the dry run lists the files and writes nothing; then Build.
    dialog.get_by_role("button", name="Statements and invoices…").click()
    build = page.locator("dialog.xc-statements")
    build.locator(".xc-b-data").select_option("statements")
    build.locator(".xc-b-lines").select_option("lines")
    build.locator(".xc-b-group").fill("cedant, period")
    build.locator(".xc-b-name").fill("{cedant} {period}.xlsx")
    build.locator(".xc-b-start").fill("101")
    build.locator(".xc-b-pattern").fill("ST-{n:04d}")
    expect(build.get_by_role("button", name="Build", exact=True)).to_be_disabled()
    build.get_by_role("button", name="Dry run", exact=True).click()
    plan = build.locator(".xc-plan-table tbody tr")
    expect(plan).to_have_count(6)
    expect(plan.first).to_contain_text("Ashgrove Mutual 2026-Q1.xlsx")
    expect(plan.first).to_contain_text("ST-0101")
    assert not (folder / "statements").exists()
    shot(page, "accounting-dry-run")
    build.get_by_role("button", name="Build 6", exact=True).click()
    expect(build.locator(".xc-plan-head")).to_contain_text("Built: 6", timeout=20000)
    assert len(list((folder / "statements").glob("*.xlsx"))) == 6
    build.get_by_role("button", name="Register", exact=True).click()
    expect(page.locator(".toast", has_text="register")).to_be_visible()
    page.context.close()


def test_the_mode_sets_the_canvas_and_the_families(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/projects", {"folder": str(server["tmp"]), "name": "Books", "type": "accounting"})
    page = workbench(browser, server)
    expect(page.get_by_role("button", name="New Excel workbook")).to_be_visible(timeout=20000)
    # The Blades page: Excel's families first, Show all for the rest.
    blades = page.context.new_page()
    blades.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}")
    expect(blades.locator('.starter-family-row[data-family="Excel"]')).to_be_visible(timeout=20000)
    expect(blades.locator('.starter-family-row[data-family="DAX"]')).to_have_count(0)
    shot(blades, "accounting-blades")
    blades.get_by_role("button", name="Show all", exact=True).click()
    expect(blades.locator('.starter-family-row[data-family="DAX"]')).to_be_visible()
    # A project of the base's type: none of it.
    call(server, "POST", "/projects", {"folder": str(server["tmp"]), "name": "Analysis"})
    other = workbench(browser, server)
    expect(other.get_by_role("button", name="Start an app")).to_be_visible(timeout=20000)
    expect(other.get_by_role("button", name="New Excel workbook")).to_have_count(0)
    blades.reload()
    expect(blades.locator('.starter-family-row[data-family="DAX"]')).to_be_visible(timeout=20000)
    expect(blades.get_by_role("button", name="Show all", exact=True)).to_have_count(0)
    page.context.close()
    other.context.close()
