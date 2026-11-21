# ruff: noqa: F811
"""The canvas's gaps in a real browser (the owner approved them, 2026-11-21): a widget Hidden in the app is
absent from the played page (faded with an eye-off mark on the canvas); an In wired to another page's Out (a
stub with that page's name in the Wiring view); a sandbox table feeding a table widget; the Wiring view's
lines from the exact Out port to the In port; a project's own widget listed first; a long container title.
Screenshots (scale 2) when SAB_GAPS_SHOTS names a folder. Made-up data only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_canvas_page import open_canvas
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widget_wiring_page import canvas_with, play, project  # noqa: F401
from tests.e2e.test_widgets_page import open_widgets
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SAB_GAPS_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(800)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def command(server: dict[str, Any], canvas: str, kind: str, **body: Any) -> dict[str, Any]:
    found: dict[str, Any] = call(
        server, "POST", f"/streamlit/canvases/{canvas}/command", {"kind": kind, **body}
    )
    return found


def select(page: Page, instance: str) -> Any:
    page.locator(f".cvs-widget[data-id='{instance}']").click()
    return page.locator(".cvs-props")


@needs_streamlit
def test_a_hidden_widget_is_absent_from_the_played_page(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    made, (metric, shown) = canvas_with(
        server, project, ("metric", 0, {"label": "Orders"}), ("data_table", 300, {})
    )
    page = open_canvas(browser, server, Path(made["path"]))
    pane = select(page, metric)
    hidden = pane.get_by_label("Hidden in the app")
    expect(hidden).not_to_be_checked()
    hidden.check()
    widget = page.locator(f".cvs-widget[data-id='{metric}']")
    expect(widget).to_have_class(re.compile("app-hidden"))
    expect(widget.locator(".cvs-hidden-mark")).to_be_visible()
    shot(page, "hidden-on-the-canvas")
    frame = play(page)
    expect(frame.locator(f".st-key-sab-{shown} [role='grid']")).to_be_attached(timeout=60000)
    expect(frame.locator(f".st-key-sab-{shown}")).to_be_visible()
    expect(frame.locator(f".st-key-sab-{metric}")).to_be_attached()  # it ran
    expect(frame.locator(f".st-key-sab-{metric}")).to_be_hidden()  # it takes no space
    shot(page, "hidden-played")


def test_an_in_reads_another_pages_out_and_the_wiring_view_shows_its_stub(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    made, (editor,) = canvas_with(server, project, ("input_data_editor", 0, {}))
    canvas = made["canvas"]
    second = command(server, canvas, "add_page", name="Reports")["made"]
    command(server, canvas, "add_container", page=second, x=0, y=0, w=1200, h=600)
    reader = command(server, canvas, "insert_widget", page=second, parent="c2", widget="data_table")["made"]
    page = open_canvas(browser, server, Path(made["path"]))
    page.locator(f".cvs-tab[data-page='{second}']").click()
    pane = select(page, reader)
    source = pane.locator(".cvs-port[data-port='table_name'] select.cvs-source")
    group = source.locator("optgroup[data-page]")
    expect(group).to_have_attribute("label", re.compile(r"\(another page\)"))
    source.select_option(f"out:{editor}.value")
    until(
        lambda: call(server, "GET", f"/streamlit/canvases/{canvas}")["wiring"]["sources"][reader].get(
            "table_name"
        ),
        {"out": f"{editor}.value"},
    )
    page.locator(".cvs-wiring-toggle").click()
    stub = page.locator(f".cvs-wires .cvs-wire-stub.cross[data-to='{reader}.table_name']")
    expect(stub).to_have_count(1)
    expect(page.locator(".cvs-wires .cvs-wire-label").first).to_have_text(re.compile("Page 1|Overview|Page"))
    shot(page, "cross-page-stub")
    # its producer deleted: the stub is marked broken like any other wire
    command(server, canvas, "delete", id=editor)
    page.reload()
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30000)
    page.locator(f".cvs-tab[data-page='{second}']").click()
    expect(page.locator(".cvs-wires .cvs-wire-stub.broken")).to_have_count(1, timeout=15000)
    expect(page.locator(f".cvs-widget[data-id='{reader}']")).to_have_class(re.compile("wire-broken"))


@needs_streamlit
def test_a_sandbox_table_feeds_a_table_widget(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    push_client.push(
        pd.DataFrame({"order_id": [1, 2, 3], "store": ["Larkfield Shop", "Marshby Depot", "Fernhaven Shop"]}),
        name="shop_orders",
        new_grid=True,
    )
    call(server, "POST", "/sandbox/tables", {"from": "grid", "table": "shop_orders"})
    made, (shown,) = canvas_with(server, project, ("data_table", 0, {}))
    page = open_canvas(browser, server, Path(made["path"]))
    pane = select(page, shown)
    source = pane.locator(".cvs-port[data-port='table_name'] select.cvs-source")
    expect(
        source.locator("optgroup[label='Sandbox'] option[value='table:[Sandbox].shop_orders']")
    ).to_have_count(1)
    source.select_option("table:[Sandbox].shop_orders")
    until(
        lambda: call(server, "GET", f"/streamlit/canvases/{made['canvas']}")["wiring"]["sources"][shown].get(
            "table_name"
        ),
        {"table": "[Sandbox].shop_orders"},
    )
    shot(page, "sandbox-table-source")
    frame = play(page)
    grid = frame.locator(f".st-key-sab-{shown} [role='grid']")
    expect(grid).to_have_attribute("aria-rowcount", "4", timeout=60000)  # 3 rows and the header


def test_the_wiring_view_draws_from_the_out_port_to_the_in_port(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    made, (upload, shown) = canvas_with(server, project, ("excel_upload", 0, {}), ("data_table", 700, {}))
    command(server, made["canvas"], "wire", id=shown, port="table_name", wire={"out": f"{upload}.uploaded"})
    page = open_canvas(browser, server, Path(made["path"]))
    page.locator(".cvs-wiring-toggle").click()
    line = page.locator(f".cvs-wires path.cvs-wire[data-from='{upload}.uploaded']")
    expect(line).to_have_count(1)
    start = page.locator(f".cvs-wires circle.cvs-port-dot[data-port='{upload}.uploaded']")
    end = page.locator(f".cvs-wires circle.cvs-port-dot[data-port='{shown}.table_name']")
    expect(start).to_have_count(1)
    expect(end).to_have_count(1)
    d = line.get_attribute("d") or ""
    head = re.match(r"M ([\d.]+) ([\d.]+) C .*, ([\d.]+) ([\d.]+)$", d)
    assert head, d
    assert (float(head.group(1)), float(head.group(2))) == (
        float(start.get_attribute("cx") or 0),
        float(start.get_attribute("cy") or 0),
    )
    assert (float(head.group(3)), float(head.group(4))) == (
        float(end.get_attribute("cx") or 0),
        float(end.get_attribute("cy") or 0),
    )
    # the Out's dot on its widget's right edge, the In's on its left
    box = page.locator(f".cvs-widget[data-id='{upload}']").bounding_box()
    dot = start.bounding_box()
    assert box and dot and abs((dot["x"] + dot["width"] / 2) - (box["x"] + box["width"])) < 3
    shot(page, "wiring-port-to-port")


def test_a_projects_own_widget_is_listed_first(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    (project / "widgets").mkdir(exist_ok=True)
    (project / "widgets" / "shop_banner.widget.py").write_text(
        '# /// swissarmybench-widget\n# format = 1\n# name = "shop_banner"\n# description = "The shop\'s own '
        'banner"\n# framework = "streamlit"\n# group = "Text"\n# ///\nimport streamlit as st\n\n'
        'st.title("Larkfield")\n',
        encoding="utf-8",
    )
    page = open_widgets(browser, server, "shop_banner")
    first = page.locator(".wg-items .wg-group").first
    expect(first).to_have_text("This project")
    expect(page.locator(".wg-items .wg-item").first).to_have_attribute("data-widget", "shop_banner")
    expect(page.locator(".wg-copy-place")).to_have_text("Copy to library")
    shot(page, "project-widget-first")
    page.locator(".wg-copy-place").click()
    until(
        lambda: (
            Path(call(server, "GET", "/streamlit/widgets")["folder"]) / "shop_banner.widget.py"
        ).is_file(),
        True,
    )
    expect(page.locator(".wg-item[data-widget='shop_banner'] .wg-item-hides")).to_have_text(
        "Instead of the library's"
    )


@needs_streamlit
def test_a_long_container_title_never_covers_its_first_widget(
    browser: Browser, server: dict[str, Any], project: Path
) -> None:
    made, (metric,) = canvas_with(server, project, ("metric", 36, {"label": "Orders"}))
    title = "Reconciliation results for every month and every store, signed off by the team"
    command(server, made["canvas"], "set_container", id="c1", props={"title": title})
    page = open_canvas(browser, server, Path(made["path"]))
    frame = play(page)
    heading = frame.locator(".st-key-sab-c1 .sab-title")
    widget = frame.locator(f".st-key-sab-{metric}")
    expect(widget).to_be_visible(timeout=60000)
    one = heading.bounding_box()
    assert one is not None and abs(one["height"] - 28) <= 2, one  # one line: the canvas's reserved 28 px
    first_top = (widget.bounding_box() or {})["y"]
    assert first_top >= one["y"] + one["height"] - 1, (one, first_top)
    page.set_viewport_size({"width": 420, "height": 900})  # a narrow page: the title wraps
    page.wait_for_timeout(1500)
    wrapped = heading.bounding_box()
    below = widget.bounding_box()
    assert wrapped and below and wrapped["height"] > 30, wrapped
    assert below["y"] >= wrapped["y"] + wrapped["height"] - 1, (wrapped, below)
    shot(page, "long-title-narrow")
