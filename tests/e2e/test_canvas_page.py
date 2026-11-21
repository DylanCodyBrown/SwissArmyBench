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
import re
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
    # The board drawn at its layout's width (it is sized once the canvas's state has come)
    page.wait_for_function("document.querySelector('.cvs-board').offsetWidth >= 390", timeout=30000)
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


def placed_in(server: dict[str, Any], canvas: str, layout: str = "desktop") -> dict[str, Any]:  # noqa: F811
    """Each item's place in pixels at the layout's design width (desktop 1200, phone 390), by id."""
    state = call(server, "GET", f"/streamlit/canvases/{canvas}")
    out: dict[str, Any] = {}

    def walk(children: list[dict[str, Any]]) -> None:
        for child in children:
            out[child["id"]] = child
            walk(child.get("children") or [])

    for views in state["views"].values():
        walk(views[layout])
    return out


def boxes(played: Any) -> dict[str, list[float]]:
    found: dict[str, list[float]] = played.evaluate(
        """(root) => {
          const at = root.getBoundingClientRect();
          const out = {};
          for (const el of root.querySelectorAll('[class*="st-key-sab-"]')) {
            const name = [...el.classList].find((c) => c.startsWith('st-key-sab-'));
            const r = el.getBoundingClientRect();
            const key = name.slice('st-key-sab-'.length);
            out[key] = [r.left - at.left, r.top - at.top, r.width, r.height, at.width];
          }
          return out;
        }"""
    )
    return found


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
    at = placed_in(server, canvas)
    c1, c2 = at["c1"], at["c2"]
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
    if SHOTS:  # the gallery's previews as they come (made one at a time in the background)
        page.wait_for_function("document.querySelectorAll('.cvs-card img').length >= 8", timeout=300000)
        gallery.locator(".cvs-cards").evaluate("(e) => e.parentElement.scrollTo(0, 0)")
    shot(page, "canvas-widgets-pane")
    # Play: the page live in place; its boxes where the canvas put them.
    # The run group is at the bottom of every right-click menu: a widget's, a container's, the empty grid's.
    assert page.locator(".cvs-bottom").get_by_role("button", name="Play").count() == 0
    run_group = ["Play", "Launch", "Launch with the Performance Analyzer", "Builds…", "Export…"]
    # The top row's far right: Play (with its ▾: Launch, with the analyzer, Builds) and Export, always shown.
    expect(page.locator(".cvs-top .cvs-run .cvs-play")).to_have_text("Play")
    expect(page.locator(".cvs-top .cvs-run .cvs-export")).to_have_text("Export")
    page.locator(".cvs-top .cvs-play-more").click()
    expect(page.locator(".cvs-menu .cvs-menu-item")).to_have_count(3)
    expect(page.locator(".cvs-menu .cvs-menu-item .cvs-menu-key")).to_have_text(["Ctrl+F5", "Ctrl+Shift+F5"])
    page.keyboard.press("Escape")
    page.locator(".cvs-widget[data-widget='metric']").click(button="right")
    items = page.locator(".cvs-menu .cvs-menu-item")
    expect(items.last).to_contain_text("Export…")
    texts = items.all_inner_texts()
    assert texts[-5].startswith("Play") and texts[0].startswith("Edit")
    page.keyboard.press("Escape")
    page.locator(".cvs-container[data-id='c1']").dispatch_event(
        "contextmenu", {"clientX": 300, "clientY": 300, "button": 2}
    )
    expect(page.locator(".cvs-menu .cvs-menu-item").first).to_contain_text("Insert widget")
    expect(page.locator(".cvs-menu .cvs-menu-item").last).to_contain_text("Export…")
    page.keyboard.press("Escape")
    board = page.locator(".cvs-board").bounding_box()
    assert board
    page.locator(".cvs-board").dispatch_event(
        "contextmenu", {"clientX": board["x"] + 300, "clientY": board["y"] + 400, "button": 2}
    )
    texts = [t.split("\n")[0].strip() for t in page.locator(".cvs-menu .cvs-menu-item").all_inner_texts()]
    assert texts[:2] == ["Insert container", "Insert widget"] and texts[-5:] == run_group, texts
    keys = page.locator(".cvs-menu .cvs-menu-item .cvs-menu-key").all_inner_texts()
    assert keys[-4:] == ["F5", "Ctrl+F5", "Ctrl+Shift+F5", "Ctrl+Shift+E"], keys
    shot(page, "canvas-right-click-run-group")
    page.keyboard.press("Escape")
    page.locator(".cvs-top .cvs-play").click()
    frame = page.frame_locator(".cvs-live-frame")
    expect(frame.get_by_text("Orders this month")).to_be_visible(timeout=120000)
    played = page.frame_locator(".cvs-live-frame").locator(".st-key-sab-page")
    expect(played).to_be_visible()
    top = placed_in(server, canvas)
    found = state_page(server, canvas)
    for c in found:
        for each in [c, *c["children"]]:
            expect(played.locator(f".st-key-sab-{each['id']}")).to_be_attached(timeout=60000)
    page.wait_for_timeout(1500)  # the last element drawn, its box settled
    placed = boxes(played)
    assert_placed(placed, found, top, 1200)

    shot(page, "canvas-play")
    # While it plays, the menu says Stop playing instead of Play.
    page.locator(".cvs-live-bar").click(button="right")
    expect(page.locator(".cvs-menu .cvs-menu-item").first).to_contain_text("Stop playing")
    page.locator(".cvs-live-bar span").first.click()  # the menu closed (Esc would stop the page)
    expect(page.locator(".cvs-menu")).to_have_count(0)
    # Play is Stop while the page plays.
    expect(page.locator(".cvs-top .cvs-play")).to_have_text("Stop")
    page.locator(".cvs-top .cvs-play").click()
    expect(page.locator(".cvs-top .cvs-play")).to_have_text("Play")
    expect(page.locator(".cvs-viewport")).to_be_visible()
    # The exported app, run headless with AppTest: every widget draws without its own error.
    out = tmp_path / "exported"
    call(server, "POST", f"/streamlit/canvases/{canvas}/export", {"folder": str(out)})
    assert (out / "app.py").is_file() and (out / "data" / "orders.parquet").is_file()
    checked = call(server, "POST", f"/streamlit/canvases/{canvas}/check", {})
    assert checked["ok"], checked
    assert json.loads(path.read_text())["pages"][0]["children"][0]["props"]["scrollable"] is True
    page.context.close()


def state_page(server: dict[str, Any], canvas: str, layout: str = "desktop") -> list[dict[str, Any]]:  # noqa: F811
    state = call(server, "GET", f"/streamlit/canvases/{canvas}")
    first = state["model"]["pages"][0]["id"]
    children: list[dict[str, Any]] = state["views"][first][layout]
    return children


def assert_placed(
    placed: dict[str, list[float]], children: list[dict[str, Any]], at: dict[str, Any], design: int
) -> None:
    """The built page's boxes where the canvas put them: x and w as fractions of the page's width (scaled from
    the layout's design width), y and h in pixels; within 1 px (a nested item within 1.5: two roundings)."""
    for c in children:
        x, y, w, h, width = placed[c["id"]]
        scale = width / design
        assert abs(x - c["x"] * scale) <= 1 and abs(y - c["y"]) <= 1 and abs(w - c["w"] * scale) <= 1, (
            c["id"],
            placed[c["id"]],
            c,
            scale,
        )
        assert abs(h - c["h"]) <= 1 or (not at[c["id"]]["props"].get("scrollable") and h >= c["h"] - 1)
        for child in c.get("children") or []:
            cx, cy, cw, ch, _ = placed[child["id"]]
            assert abs(cx - (c["x"] + child["x"]) * scale) <= 1.5, (child, placed[child["id"]], scale)
            assert abs(cy - (c["y"] + child["y"])) <= 1 and abs(cw - child["w"] * scale) <= 1.5, child
            assert abs(ch - child["h"]) <= 1, child


@needs_streamlit
def test_phone_and_desktop_layouts(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    """Two layouts (the owner, 2026-11-21): a container drawn on Desktop is stacked at full width on Phone;
    Show on hides an item in one layout; the frame's right edge previews another width (the items reflow);
    the built page shows Desktop at 1280 px and Phone at 375 px, each where its layout put it."""
    project = tmp_path / "phones"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Field", "folder": str(project)})
    canvas = made["canvas"]
    page = open_canvas(browser, server, Path(made["path"]))
    box = page.locator(".cvs-board").bounding_box()
    assert box
    drag(page, box["x"] + 600, box["y"] + 40, box["x"] + 1000, box["y"] + 240)
    expect(page.locator(".cvs-container")).to_have_count(1)
    page.locator(".cvs-container[data-id='c1']").click(button="right", position={"x": 60, "y": 60})
    page.locator(".cvs-menu-item", has_text="Insert widget").hover()
    page.locator(".cvs-widget-menu .cvs-menu-search").fill("metric")
    page.locator(".cvs-widget-menu .cvs-menu-item[data-widget='metric']").click()
    expect(page.locator(".cvs-widget[data-widget='metric']")).to_have_count(1)
    drag(page, box["x"] + 40, box["y"] + 300, box["x"] + 400, box["y"] + 420)
    expect(page.locator(".cvs-container")).to_have_count(2)
    desktop = placed_in(server, canvas)
    phone = placed_in(server, canvas, "phone")
    assert desktop["c1"]["x"] >= 592 and phone["c1"]["x"] == 0 and phone["c1"]["w"] == 390
    assert phone["c2"]["w"] == 390 and phone["c2"]["y"] > phone["c1"]["y"]  # stacked in reading order
    # The switch: Phone draws the phone layout at 390 px.
    page.locator(".cvs-layouts [data-layout='phone']").click()
    expect(page.locator(".cvs-layouts [data-layout='phone']")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".cvs-width-label")).to_have_text("390 px")
    first = page.locator(".cvs-container[data-id='c1']").bounding_box()
    assert first and abs(first["width"] - 390) <= 1
    shot(page, "canvas-phone-layout")
    # Dragging the frame's right edge previews a wider phone: the items reflow with it.
    grip = page.locator(".cvs-width-handle").bounding_box()
    assert grip
    drag(page, grip["x"] + 5, grip["y"] + 40, grip["x"] + 5 + 110, grip["y"] + 40)
    expect(page.locator(".cvs-width-label")).to_have_text("500 px")
    wider = page.locator(".cvs-container[data-id='c1']").bounding_box()
    assert wider and abs(wider["width"] - 500) <= 1
    # Show on: Desktop only hides c2 from the built phone page (faded here).
    page.locator(".cvs-container[data-id='c2']").click(position={"x": 20, "y": 20})
    page.locator(".cvs-props .cvs-show").select_option("desktop")
    until(lambda: node(model(server, canvas), "c2").get("show"), "desktop")
    expect(page.locator(".cvs-container[data-id='c2']")).to_have_class(re.compile("hidden-here"))
    page.locator(".cvs-layouts [data-layout='desktop']").click()
    expect(page.locator(".cvs-container[data-id='c2']")).not_to_have_class(re.compile("hidden-here"))
    # The built page: Desktop at 1280 px, Phone at 375 px (a media query: no rerun), each where it was put.
    played = call(server, "POST", f"/streamlit/canvases/{canvas}/play", {})
    assert played["ok"], played
    for width, layout in ((1280, "desktop"), (375, "phone")):
        view = page.context.new_page()
        view.set_viewport_size({"width": width, "height": 900})
        view.goto(f"http://127.0.0.1:{server['port']}{played['url']}")
        root = view.locator(".st-key-sab-page")
        expect(root.locator(".st-key-sab-w1")).to_be_attached(timeout=120000)
        view.wait_for_timeout(1500)
        placed = boxes(root)
        shown = [
            c for c in state_page(server, canvas, layout) if (c.get("show") or "both") in ("both", layout)
        ]
        assert_placed(placed, shown, placed_in(server, canvas, layout), 1200 if layout == "desktop" else 390)
        c2 = view.locator(".st-key-sab-c2")
        display = c2.evaluate("(e) => getComputedStyle(e).display")
        assert display in (("none",) if layout == "phone" else ("block", "flex"))
        if SHOTS:
            view.screenshot(path=str(Path(SHOTS) / f"built-{layout}-{width}.png"))
        view.close()
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


@needs_streamlit
def test_launch_with_the_analyzer_then_compare_and_restore_builds(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
    tmp_path: Path,
) -> None:
    """Ctrl+Shift+F5 launches a build with the Performance Analyzer's window beside it, recording the launched
    page's reruns by widget; a second launch (Ctrl+F5) after a change; Builds…: tick two and Compare (Monaco's
    diff editor, canvas.json changed), then Restore build 1 (the label back) and Ctrl+Z (forward again)."""
    project = tmp_path / "shop"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Sales", "folder": str(project)})
    canvas = made["canvas"]

    def send(kind: str, **body: Any) -> Any:
        return call(server, "POST", f"/streamlit/canvases/{canvas}/command", {"kind": kind, **body})

    send("add_container", x=0, y=0, w=600, h=300)
    widget = send("insert_widget", parent="c1", widget="metric", values={"label": "Orders made up"})["made"]
    page = open_canvas(browser, server, Path(made["path"]))
    context = page.context
    expect(page.locator(".cvs-widget[data-widget='metric']")).to_have_count(1)
    page.locator(".cvs-board").focus()
    with context.expect_page(timeout=60000) as first_window:
        page.keyboard.press("Control+Shift+F5")
    windows = [first_window.value]
    # Both windows opened at once (about:blank), each sent on once the build has started (Playwright hears
    # their navigations only while it is asked something: wait_for_timeout).
    for _ in range(600):
        if len(context.pages) >= 3 and any("/streamlit/perf" in p.url for p in context.pages):
            break
        page.wait_for_timeout(200)
    analyzer = next(p for p in context.pages if "/streamlit/perf" in p.url)
    app = next(p for p in context.pages if p not in (page, analyzer))
    expect(app.get_by_text("Orders made up")).to_be_visible(timeout=120000)
    expect(analyzer.locator(".pf-tabs")).to_be_visible(timeout=60000)
    until(
        lambda: call(server, "GET", f"/streamlit/canvases/{canvas}/perf")["reruns"] != [], True, seconds=120
    )
    del windows
    reruns = call(server, "GET", f"/streamlit/canvases/{canvas}/perf")["reruns"]
    assert reruns[0]["trigger"] == "first load"
    assert any(b["title"] == f"metric ({widget})" for r in reruns for b in r["blocks"]), reruns
    expect(analyzer.get_by_text(f"metric ({widget})").first).to_be_visible(timeout=30000)
    shot(analyzer, "canvas-performance-analyzer")
    # A change, then Ctrl+F5: build 2, with what changed in words.
    send("set_values", id=widget, values={"label": "Revenue made up"})
    page.locator(".cvs-board").focus()
    page.keyboard.press("Control+F5")
    until(lambda: len(call(server, "GET", f"/streamlit/canvases/{canvas}/builds")["builds"]), 2, seconds=120)
    # Builds…: from Play's ▾.
    page.locator(".cvs-top .cvs-play-more").click()
    page.locator(".cvs-menu-item", has_text="Builds…").click()
    dialog = page.locator(".bd")
    expect(dialog.locator(".bd-row")).to_have_count(2, timeout=30000)
    expect(dialog.locator(".bd-row[data-build='2'] .bd-changed")).to_contain_text("label changed")
    dialog.get_by_label("Build 1").check()
    dialog.get_by_label("Build 2").check()
    page.locator(".bd-compare").click()
    expect(page.locator(".bd-diff .monaco-diff-editor")).to_be_visible(timeout=60000)
    expect(page.locator(".bd-file[data-file='canvas.json']")).to_be_visible()
    shot(page, "canvas-builds-compare")
    dialog.locator(".bd-row[data-build='1'] .bd-restore").click()
    until(lambda: node(model(server, canvas), widget)["values"]["label"], "Orders made up", seconds=30)
    page.keyboard.press("Escape")  # the dialog goes
    page.locator(".cvs-board").focus()
    page.keyboard.press("Control+z")
    until(lambda: node(model(server, canvas), widget)["values"]["label"], "Revenue made up", seconds=30)
    call(server, "DELETE", f"/streamlit/canvases/{canvas}/launch")
    context.close()
