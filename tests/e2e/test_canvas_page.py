"""The Canvas page (the owner, 2026-11-21), with a Python that has Streamlit: the Widgets pane's cards with
their rendered previews; draw two containers on the grid (snapped to the step), make one scrollable by
right-click, Insert widget from the menu, set its property in Properties, drag a card into the other
container, double-click a card into the selected container, hide and show the panes, undo, Play, and the
played page's boxes where the canvas put them (within 1 px); the exported app run headless; a widget's
description changed in the Widgets window shows on its card. Screenshots when SWISSARMYBENCH_WIDGET_SHOTS
names a folder. Made-up data."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SWISSARMYBENCH_WIDGET_SHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(600)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:  # noqa: F811
    close_tables(server)
    frame = pd.DataFrame(
        {"region": ["North", "South", "East", "West"] * 3, "revenue": [120.0, 95.5, 143.0, 88.0] * 3}
    )
    push_client.push(frame, name="orders", new_grid=True)
    yield
    try:
        call(server, "DELETE", "/streamlit/widgets/region_kpi")
    except Exception:  # noqa: S110 (never made)
        pass
    close_tables(server)


def open_canvas(browser: Browser, server: dict[str, Any], path: Path) -> Page:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1600, "height": 950}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    page.wait_for_load_state("networkidle")
    page.goto(
        f"http://127.0.0.1:{server['port']}/streamlit/canvas?path={quote(str(path))}#token={server['token']}"
    )
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30000)
    return page


def model(server: dict[str, Any], canvas: str) -> dict[str, Any]:  # noqa: F811
    found: dict[str, Any] = call(server, "GET", f"/streamlit/canvases/{canvas}")["model"]
    return found


def node(found: dict[str, Any], node_id: str) -> dict[str, Any]:
    def look(children: list[dict[str, Any]]) -> dict[str, Any] | None:
        for child in children:
            if child["id"] == node_id:
                return child
            inner = look(child.get("children") or [])
            if inner:
                return inner
        return None

    for p in found["pages"]:
        hit = look(p["children"])
        if hit:
            return hit
    raise AssertionError(f"no {node_id}")


def drag(page: Page, x1: float, y1: float, x2: float, y2: float) -> None:
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=4)
    page.mouse.move(x2, y2, steps=6)
    page.mouse.up()


@needs_streamlit
def test_build_a_page_on_the_canvas_and_play_it(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    project = tmp_path / "shop"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Sales", "folder": str(project)})
    canvas = made["canvas"]
    path = Path(made["path"])
    call(server, "POST", f"/streamlit/canvases/{canvas}/command", {"kind": "sizing", "step": 8})
    page = open_canvas(browser, server, path)
    gallery = page.locator(".cvs-gallery")
    # The Widgets pane: a card per widget, grouped, with its rendered preview (a placeholder until made).
    expect(gallery.locator(".cvs-card")).to_have_count(
        len(call(server, "GET", "/streamlit/widgets")["widgets"])
    )
    expect(gallery.locator(".cvs-card[data-widget='metric'] .cvs-card-name")).to_have_text("metric")
    expect(gallery.locator(".cvs-card img").first).to_be_visible(timeout=180000)
    # Draw two containers on the empty grid: snapped to the 8 px step.
    box = page.locator(".cvs-board").bounding_box()
    assert box
    drag(page, box["x"] + 23, box["y"] + 21, box["x"] + 405, box["y"] + 260)
    expect(page.locator(".cvs-container")).to_have_count(1)
    drag(page, box["x"] + 450, box["y"] + 20, box["x"] + 900, box["y"] + 300)
    expect(page.locator(".cvs-container")).to_have_count(2)
    found = model(server, canvas)
    c1, c2 = node(found, "c1"), node(found, "c2")
    assert all(v % 8 == 0 for v in (c1["x"], c1["y"], c2["x"], c2["y"]))
    # Right-click the first: Scrollable; then Insert widget ▸ metric.
    first = page.locator(".cvs-container[data-id='c1']")
    first.click(button="right", position={"x": 60, "y": 60})
    page.locator(".cvs-menu-item", has_text="Scrollable").click()
    until(lambda: node(model(server, canvas), "c1")["props"]["scrollable"], True)
    first.click(button="right", position={"x": 60, "y": 60})
    page.locator(".cvs-menu-item", has_text="Insert widget").hover()
    shot(page, "canvas-right-click-insert")
    page.locator(".cvs-widget-menu .cvs-menu-search").fill("metric")
    page.locator(".cvs-widget-menu .cvs-menu-item[data-widget='metric']").click()
    expect(page.locator(".cvs-widget[data-widget='metric']")).to_have_count(1)
    # Its properties, in the Properties pane: the label changed there is the instance's own value.
    props = page.locator(".cvs-props")
    expect(props.locator(".wg-prop[data-property='label']")).to_be_visible()
    label = props.locator(".wg-prop[data-property='label'] input")
    label.fill("Orders this month")
    label.press("Enter")
    until(lambda: node(model(server, canvas), "w1")["values"], {"label": "Orders this month"})
    shot(page, "canvas-selected-widget-properties")
    # Drag a card into the second container; double-click another into the selected container.
    page.locator(".cvs-card[data-widget='data_table']").drag_to(
        page.locator(".cvs-container[data-id='c2']"), target_position={"x": 30, "y": 40}
    )
    expect(page.locator(".cvs-widget[data-widget='data_table']")).to_have_count(1)
    table = next(c for c in node(model(server, canvas), "c2")["children"] if c["widget"] == "data_table")
    # Another window's change (the agent's here): this window says so and shows the canvas as it is now.
    call(
        server,
        "POST",
        f"/streamlit/canvases/{canvas}/command",
        {"kind": "set_values", "id": table["id"], "values": {"table_name": "orders"}},
    )
    expect(page.locator(".cvs-notice")).to_contain_text("changed in another window")
    page.locator(".cvs-container[data-id='c1']").click(position={"x": 380, "y": 230})
    page.locator(".cvs-card[data-widget='callout_info']").dblclick()
    until(
        lambda: sorted(c["widget"] for c in node(model(server, canvas), "c1")["children"]),
        ["callout_info", "metric"],
        20,
    )
    # Undo takes the last change back (and Redo brings it again).
    page.keyboard.press("Control+z")
    until(lambda: sorted(c["widget"] for c in node(model(server, canvas), "c1")["children"]), ["metric"], 20)
    page.keyboard.press("Control+y")
    until(lambda: len(node(model(server, canvas), "c1")["children"]), 2, 20)
    # The panes hide completely and come back.
    page.locator(".cvs-toggle", has_text="Widgets").click()
    expect(gallery).to_be_hidden()
    page.locator(".cvs-toggle", has_text="Properties").click()
    expect(props).to_be_hidden()
    page.locator(".cvs-toggle", has_text="Widgets").click()
    page.locator(".cvs-toggle", has_text="Properties").click()
    expect(gallery).to_be_visible()
    page.keyboard.press("Escape")
    shot(page, "canvas-widgets-pane")
    # Play: the page live in place; its boxes where the canvas put them.
    page.locator(".cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    expect(frame.get_by_text("Orders this month")).to_be_visible(timeout=120000)
    played = page.frame_locator(".cvs-live-frame").locator(".st-key-sab-page")
    expect(played).to_be_visible()
    found = model(server, canvas)
    for c in found["pages"][0]["children"]:
        for each in [c, *c["children"]]:
            expect(played.locator(f".st-key-sab-{each['id']}")).to_be_attached(timeout=60000)
    page.wait_for_timeout(1500)  # the last element drawn, its box settled
    placed = played.evaluate(
        """(root) => {
          const at = root.getBoundingClientRect();
          const out = {};
          for (const el of root.querySelectorAll('[class*="st-key-sab-"]')) {
            const name = [...el.classList].find((c) => c.startsWith('st-key-sab-'));
            const key = name.slice('st-key-sab-'.length);
            const r = el.getBoundingClientRect();
            out[key] = [r.left - at.left, r.top - at.top, r.width, r.height];
          }
          return out;
        }"""
    )
    for c in found["pages"][0]["children"]:
        x, y, w, h = placed[c["id"]]
        assert abs(x - c["x"]) <= 1 and abs(y - c["y"]) <= 1 and abs(w - c["w"]) <= 1, (
            c["id"],
            placed[c["id"]],
            c,
        )
        assert abs(h - c["h"]) <= 1 or (not c["props"]["scrollable"] and h >= c["h"] - 1)
        for child in c["children"]:
            cx, cy, cw, ch = placed[child["id"]]
            assert abs(cx - (c["x"] + child["x"])) <= 1 and abs(cy - (c["y"] + child["y"])) <= 1, child
            assert abs(cw - child["w"]) <= 1 and abs(ch - child["h"]) <= 1, child
    shot(page, "canvas-play")
    page.locator(".cvs-live .cvs-edit").click()
    expect(page.locator(".cvs-viewport")).to_be_visible()
    # The exported app, run headless with AppTest: every widget draws without its own error.
    out = tmp_path / "exported"
    call(server, "POST", f"/streamlit/canvases/{canvas}/export", {"folder": str(out)})
    assert (out / "app.py").is_file() and (out / "data" / "orders.parquet").is_file()
    checked = call(server, "POST", f"/streamlit/canvases/{canvas}/check", {})
    assert checked["ok"], checked
    assert json.loads(path.read_text())["pages"][0]["children"][0]["props"]["scrollable"] is True
    page.context.close()


@needs_streamlit
def test_a_widgets_description_changed_in_its_window_shows_on_its_card(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    call(
        server,
        "POST",
        "/streamlit/widgets",
        {
            "name": "region_kpi",
            "description": "Revenue",
            "code": 'import streamlit as st\n\nlabel = "Revenue"\n\nst.metric(label, 42)\n',
        },
    )
    project = tmp_path / "shop2"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Board", "folder": str(project)})
    page = open_canvas(browser, server, Path(made["path"]))
    card = page.locator(".cvs-card[data-widget='region_kpi']")
    expect(card.locator(".cvs-card-desc")).to_have_text("Revenue")
    # Hovering a card: its larger preview, with its name and description.
    card.hover()
    expect(page.locator(".cvs-big-preview .cvs-card-name")).to_have_text("region_kpi")
    page.mouse.move(5, 5)
    expect(page.locator(".cvs-big-preview")).to_have_count(0)
    window = page.context.new_page()
    window.goto(f"http://127.0.0.1:{server['port']}/streamlit/widget?name=region_kpi#token={server['token']}")
    description = window.locator(".wg-props .wg-description")
    expect(description).to_have_value("Revenue")
    description.fill("Revenue for each region this month")
    description.blur()
    expect(card.locator(".cvs-card-desc")).to_have_text("Revenue for each region this month", timeout=20000)
    page.context.close()
