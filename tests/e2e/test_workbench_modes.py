# ruff: noqa: F811
"""The Workbench's modes and kind colours (2026-11-15), in a real browser: app pages violet, notebooks
blue, scripts green on tabs, the group's band, the Streamlit cells pane and canvas blocks; App mode
(Properties for a block and the page settings, the wiring, undo, duplicate, align, zoom, the starter
gallery, Play's preview and the State panel); Notebook mode (run order, edited and out-of-date cells,
the Outline, Run up to here, Present); Script mode (run settings, Run as scheduled, run history); Data
mode (data.ipynb's Cells | Lineage | Dictionary). Made-up data only.

With SWISSARMYBENCH_MODES_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import re
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from swissarmybench.renamed import env
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server, until  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

SHOTS = env("SWISSARMYBENCH_MODES_SHOTS") or None
ORDERS = pd.DataFrame(
    {
        "order_id": [10482, 10377, 10611, 10295, 10540, 10123],
        "region": ["East", "West", "East", "North", "West", "East"],
        "status": ["shipped", "delivered", "shipped", "returned", "shipped", "shipped"],
        "amount": [4120.0, 3860.5, 3402.75, 3118.2, 2990.0, 1200.0],
    }
)
FILTER = (
    '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()), key="region_pick")'
)
TOTAL = '# Total sales\nst.metric("Total sales", int(orders[orders["region"] == region]["amount"].sum()))'
LARGEST = '# Largest orders\nst.dataframe(orders[orders["region"] == region].nlargest(5, "amount"))'


def open_window(
    browser: Browser, server: dict[str, Any], path: Path | None = None, dark: bool = False
) -> Page:
    context = browser.new_context(
        viewport={"width": 1500, "height": 950},
        device_scale_factor=2 if SHOTS else 1,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    opened = f"&open={quote(str(path))}" if path else ""
    # A .py on the Scripts page, anything else on the Notebooks page (2026-11-21).
    where = "scripts" if path and path.suffix == ".py" else "notebooks"
    page.goto(f"http://127.0.0.1:{server['port']}/{where}#token={server['token']}{opened}")
    expect(page.locator(".wb-tab" if path else ".wb-codex").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:
    close_tables(server)
    push_client.push(ORDERS, name="orders", new_grid=True)
    yield
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def colour(page: Page, selector: str, prop: str = "color") -> str:
    return str(page.locator(selector).first.evaluate(f"e => getComputedStyle(e).{prop}"))


def token(page: Page, name: str) -> str:
    return str(
        page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('--kind-{name}').trim()")
    )


def rgb(hex_colour: str) -> str:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgb({r}, {g}, {b})"


def app_files(server: dict[str, Any], folder: Path) -> Path:
    """A saved notebook of three Streamlit cells, and a saved app linking them (two rows)."""
    folder.mkdir(parents=True, exist_ok=True)
    notebook = folder / "app mockups.ipynb"
    cells = [
        {"kind": "code", "source": FILTER, "name": "Region filter"},
        {"kind": "code", "source": TOTAL, "name": "Total sales"},
        {"kind": "code", "source": LARGEST, "name": "Largest orders"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    if STREAMLIT_PYTHON:
        call(server, "POST", "/workbench/environment", {"path": str(notebook), "python": STREAMLIT_PYTHON})
    page = {
        "name": "Overview",
        "blocks": [
            {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 4, "h": None},
            {"document": str(notebook), "cell": 2, "row": 1, "column": 5, "w": 4, "h": None},
            {"document": str(notebook), "cell": 3, "row": 2, "column": 1, "w": 12, "h": None},
        ],
    }
    app = folder / "sales app.stapp.json"
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(app), "pages": [page, {"name": "Products", "blocks": []}]},
    )
    return app


def test_kind_colours_on_tabs_menus_and_settings(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    script = tmp_path / "sales" / "daily_sales.py"
    script.write_text("import os\nprint(os.getenv('REPORT_FOLDER', 'reports'))\n", encoding="utf-8")
    page = open_window(browser, server, app)
    window(server, "file.open", path=str(tmp_path / "sales" / "app mockups.ipynb"))
    tabs = page.locator(".wb-tab")
    expect(tabs).to_have_count(2, timeout=20000)
    marks = {t.inner_text().strip("●× \n"): t.get_attribute("class") or "" for t in tabs.all()}
    assert "mark-app" in marks["sales app.stapp.json"]
    assert "mark-notebook" in marks["app mockups.ipynb"]
    # Violet, blue, green: the tokens, on the tab's icon; the group wears its front document's. A script is
    # the Scripts page's (2026-11-21): green there.
    assert colour(page, ".wb-tab.mark-app .wb-tab-icon") == rgb(token(page, "app"))
    scripts = open_window(browser, server, script)
    expect(scripts.locator(".wb-tab.mark-script")).to_be_visible()
    assert colour(scripts, ".wb-tab.mark-script .wb-tab-icon") == rgb(token(scripts, "script"))
    scripts.context.close()
    expect(page.locator(".wb-group").first).to_have_attribute("data-mark", "notebook")
    # The Streamlit cells panel (the canvas's own, on its left): each cell by its source document's colour.
    page.locator(".wb-tab.mark-app").click()
    expect(page.locator(".wb-st-doc.km-notebook .wb-st-cell")).to_have_count(3, timeout=20000)
    # Settings' Kind colours, shared by every window: the agent chooses one, every window follows.
    window(server, "palette")  # (the palette opens and closes: a smoke of the window's commands)
    page.keyboard.press("Escape")
    chosen = call(server, "PUT", "/kind-colours", {"script": "#227744"})["kinds"][2]
    shown = chosen["themes"]["light"]  # made readable on the light theme (a little darker)
    until(lambda: token(page, "script") == shown)  # the notice reaches the page
    assert token(page, "script") == shown
    menu_button = page.get_by_role("button", name="Workbench menu", exact=True)
    menu_button.click()
    page.get_by_role("menuitem", name="Settings…", exact=True).click()
    section = page.locator(".kind-colours-fieldset")
    expect(section).to_be_visible()
    expect(section.locator(".kind-colour")).to_have_count(3)
    expect(section.get_by_role("button", name="Default")).to_have_count(1)
    shot(page, "kind-colours-settings")
    section.get_by_role("button", name="Default").click()
    until(lambda: token(page, "script") != shown)
    assert token(page, "script") == "" or token(page, "script") != shown
    page.keyboard.press("Escape")
    page.context.close()


def test_app_mode_properties_wiring_tools_and_page_settings(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    canvas = page.locator(".cv")
    blocks = canvas.locator(".cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    # The status bar: State and Properties in place of the console and Variables.
    bar = page.locator(".wb-status")
    expect(bar.get_by_role("button", name="Properties", exact=True)).to_be_visible()
    expect(bar.get_by_role("button", name="State", exact=True)).to_be_visible()
    expect(bar.get_by_role("button", name="Console", exact=True)).to_be_hidden()
    bar.get_by_role("button", name="Properties", exact=True).click()
    props = page.locator(".wb-mode-properties")
    expect(props).to_be_visible()
    # No block selected: the page settings.
    expect(props.get_by_role("heading", name="Theme colours")).to_be_visible()
    title = props.locator("input[data-field=title]")
    title.fill("Sales")
    title.press("Enter")
    assert until(lambda: window(server, "canvas.settings")["title"] == "Sales")
    props.get_by_role("button", name="Centred").click()
    assert until(lambda: window(server, "canvas.settings")["layout"] == "centered")
    # A block selected: its name, size, source cell (blue: a notebook's), makes, reads, feeds.
    blocks.nth(0).click()
    expect(blocks.nth(0)).to_have_class(re.compile(r"\bselected\b"))
    expect(props.locator("input[data-field=name]")).to_have_value("Region filter")
    expect(props.locator("input[data-field=width]")).to_have_value("4")
    expect(props.locator(".app-source")).to_contain_text("app mockups.ipynb @cell1")
    assert colour(page, ".app-source") == rgb(token(page, "notebook"))
    expect(props.locator(".app-chip").first).to_have_text("region")
    expect(props.locator(".app-feeds li")).to_have_count(2)
    # Its controller (domain/controllers.py): a filter that makes region; and Lineage… opens the overlay.
    expect(props.locator(".app-role")).to_have_text("Filter")
    expect(props.locator('.app-make[data-name="region"]')).to_be_visible()
    props.get_by_role("button", name="Lineage…").click()
    overlay = page.get_by_role("dialog", name="Lineage")
    expect(overlay.locator(".wb-lin-card.target")).to_contain_text("Region filter", timeout=20000)
    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)
    # The wiring: a violet arrow to each block it feeds, the name it makes under it.
    expect(canvas.locator(".cv-wires path[data-to]")).to_have_count(2)
    expect(canvas.locator(".cv-wire-name")).to_have_text("region")
    shot(page, "app-properties-wiring")
    # Width from Properties; undo and redo.
    props.locator("input[data-field=width]").fill("5")
    props.locator("input[data-field=width]").press("Enter")
    expect(props.locator("input[data-field=width]")).to_have_value("5", timeout=10000)
    expect(blocks.nth(0)).to_have_attribute("data-w", "5", timeout=10000)
    window(server, "canvas.undo")
    expect(props.locator("input[data-field=width]")).to_have_value("4", timeout=10000)
    window(server, "canvas.redo")
    expect(props.locator("input[data-field=width]")).to_have_value("5", timeout=10000)
    # Duplicate, align, zoom.
    canvas.page.get_by_role("button", name="Duplicate", exact=True).click()
    expect(blocks).to_have_count(4, timeout=10000)
    window(server, "canvas.align", how="right")
    state = window(server, "canvas.state")
    front = next(p for p in state["pages"] if p["id"] == state["page"])
    selected = window(server, "canvas.properties")["block"]
    placed = next(b for b in front["blocks"] if b["id"] == selected["id"])
    assert placed["column"] + placed["w"] == 13
    assert window(server, "canvas.zoom", percent=80) == {"percent": 80}
    expect(page.locator(".cv-zoom-level")).to_have_text("80%")
    window(server, "canvas.zoom", percent=100)
    # The agent reads Properties too; Escape puts the selection away.
    blocks.nth(0).click()
    page.keyboard.press("Escape")
    expect(props.get_by_role("heading", name="Theme colours")).to_be_visible()
    # Saved: the settings are in the app's file.
    window(server, "file.save")
    held = json.loads(app.read_text(encoding="utf-8"))
    assert held["settings"] == {"title": "Sales", "layout": "centered"}
    page.context.close()


def test_the_starter_gallery_writes_a_named_cell_and_places_it(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    expect(page.locator(".cv-block")).to_have_count(3, timeout=20000)
    # Starters is the canvas's other left panel (the status bar's Starters, or data.starters).
    page.locator(".wb-status").get_by_role("button", name="Starters", exact=True).click()
    gallery = page.locator(".wb-starters-panel")
    expect(gallery.locator(".wb-starter-family")).to_have_count(5, timeout=20000)
    listed = window(server, "data.starterList")
    assert [f["family"] for f in listed] == ["Filters", "Displays", "Layout", "Interaction", "Feedback"]
    assert sum(len(f["starters"]) for f in listed) == 29
    assert "pieces" not in page.locator(".wb-mode-left").inner_text().lower()
    shot(page, "app-starters")
    done = window(
        server,
        "canvas.addStarter",
        name="Streamlit metric with change",
        values={"table": "orders", "column": "amount", "label": "Total"},
    )
    assert done["document"].endswith("app mockups.ipynb")
    expect(page.locator(".cv-block")).to_have_count(4, timeout=20000)
    saved = json.loads((tmp_path / "sales" / "app mockups.ipynb").read_text(encoding="utf-8"))
    assert len(saved["cells"]) == 4
    page.context.close()


def test_notebook_mode_run_order_outline_run_up_to_here_and_present(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    path = tmp_path / "analysis.ipynb"
    cells = [
        {"kind": "markdown", "source": "# Monthly sales\nShipped orders only."},
        {"kind": "code", "source": "shipped = sales[sales['status'] == 'shipped']", "name": "shipped"},
        {
            "kind": "code",
            "source": "monthly = shipped.groupby('region')['amount'].sum().reset_index()\nmonthly",
            "name": "monthly",
        },
        {"kind": "markdown", "source": "## By region"},
        {
            "kind": "code",
            "source": "by_region = shipped.groupby('region')['amount'].sum()",
            "name": "by_region",
        },
    ]
    first = (
        "import pandas as pd\nsales = pd.DataFrame({'region': ['East', 'West', 'East'], "
        "'status': ['shipped', 'shipped', 'returned'], 'amount': [10.0, 20.0, 5.0]})"
    )
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(path), "cells": [{"kind": "code", "source": first}, *cells]},
    )
    page = open_window(browser, server, path)
    expect(page.locator(".wb-cell")).to_have_count(6, timeout=20000)

    for number in (1, 3, 4, 6):
        window(
            server, "run.cell", index=[c["number"] for c in window(server, "doc.read")["cells"]].index(number)
        )
    states = {c["number"]: c["state"] for c in window(server, "notebook.runOrder")}
    assert states[3] == states[4] == states[6] == "current"
    # Edit the first: it says "edited", and the cells that read what it makes "out of date".
    window(server, "cell.select", index=2)
    page.locator(".wb-cell").nth(2).locator(".monaco-editor").click()
    page.keyboard.press("End")
    page.keyboard.type("  # shipped only")
    order: dict[int, Any] = {}
    for _ in range(20):  # the run order follows the typing after a short pause
        page.wait_for_timeout(300)
        order = {c["number"]: c for c in window(server, "notebook.runOrder")}
        if order[4]["state"] == "outOfDate":
            break
    assert (
        order[3]["state"] == "edited"
        and order[4]["state"] == "outOfDate"
        and order[4]["because"] == ["shipped"]
    )
    expect(page.locator(".wb-cell").nth(2).locator(".wb-flow")).to_have_text("edited")
    expect(page.locator(".wb-cell").nth(3).locator(".wb-flow")).to_have_text("out of date")
    # The Outline: the headings and the named cells, the stale ones marked.
    page.locator(".wb-status").get_by_role("button", name="Outline", exact=True).click()
    outline = page.locator(".wb-mode-outline")
    expect(outline.locator(".wb-outline-item.heading")).to_have_text(["Monthly sales", "By region"])
    expect(outline.locator(".wb-outline-item.cell")).to_have_count(3)
    expect(outline.locator(".wb-outline-stale")).to_have_count(3)
    # Open as grid on a DataFrame's output; Run up to here.
    expect(page.locator(".wb-cell").nth(3).get_by_role("button", name="Open as grid")).to_be_visible()
    page.locator(".wb-cell").nth(5).click()
    shot(page, "notebook-outline-runorder")
    window(server, "run.upToHere", number=6)
    states = {c["number"]: c["state"] for c in window(server, "notebook.runOrder")}
    assert states[3] == states[4] == states[6] == "current"
    expect(outline.locator(".wb-outline-stale")).to_have_count(0)
    # Present: the text and outputs, no code.
    page.get_by_role("button", name="Present", exact=True).click()
    expect(page.locator(".wb-cells.presenting")).to_be_visible()
    expect(page.locator(".wb-cells.presenting .wb-editor").first).to_be_hidden()
    expect(page.locator(".wb-markdown-view h1")).to_have_text("Monthly sales")
    shot(page, "notebook-present")
    assert window(server, "notebook.present", on=False) == {"presenting": False}
    page.context.close()


SCRIPT = """\
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="all")
options = parser.parse_args()
host = os.getenv("WAREHOUSE_HOST", "none")
folder = os.environ.get("REPORT_FOLDER", "reports")
print(f"region {options.region} host {host} folder {folder}")
"""


def test_script_mode_run_settings_run_as_scheduled_and_history(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    path = tmp_path / "daily_sales.py"
    path.write_text(SCRIPT, encoding="utf-8")
    page = open_window(browser, server, path)
    bar = page.locator(".wb-status")
    expect(bar.get_by_role("button", name="Run settings", exact=True)).to_be_visible(timeout=20000)
    bar.get_by_role("button", name="Run settings", exact=True).click()
    settings = page.locator(".wb-mode-runSettings")
    expect(settings.locator(".wb-run-var")).to_have_count(2, timeout=10000)
    expect(settings.locator(".wb-run-var").first).to_contain_text("WAREHOUSE_HOST")
    args = settings.locator(".wb-run-args")
    args.fill("--region East")
    args.press("Enter")
    settings_url = f"/workbench/scripts/settings?path={quote(str(path))}"
    until(lambda: call(server, "GET", settings_url)["arguments"] == "--region East")  # kept
    host = settings.locator('.wb-run-var[data-variable="WAREHOUSE_HOST"] select')
    host.select_option("value")
    value = settings.locator('.wb-run-var[data-variable="WAREHOUSE_HOST"] input')
    expect(value).to_be_visible()
    value.fill("db1.example.test")
    value.press("Enter")
    until(
        lambda: any(
            v["name"] == "WAREHOUSE_HOST" and v["words"] == "Plain value"
            for v in call(server, "GET", settings_url)["variables"]
        )
    )
    held = call(server, "GET", settings_url)
    assert held["arguments"] == "--region East"
    assert any(v["name"] == "WAREHOUSE_HOST" and v["words"] == "Plain value" for v in held["variables"])
    shot(page, "script-run-settings")
    # Run as scheduled: a fresh process; its run in the history, with its exit code and log.
    window(server, "script.runScheduled")
    history = page.locator(".wb-mode-runHistory")
    expect(history.locator(".wb-runs tbody tr")).to_have_count(1, timeout=30000)
    expect(history.locator(".wb-run-log")).to_contain_text("region East host db1.example.test folder reports")
    expect(history.locator(".wb-runs tbody tr").first).to_contain_text("Run as scheduled")
    # Run file (the kernel's) joins the history.
    window(server, "run.primary")
    expect(history.locator(".wb-runs tbody tr")).to_have_count(2, timeout=30000)
    expect(history.locator(".wb-runs tbody tr").first).to_contain_text("Run file")
    history.locator(".wb-runs tbody tr").nth(1).click()
    expect(history.locator(".wb-run-detail")).to_contain_text("Run as scheduled")
    shot(page, "script-history")
    page.context.close()


def test_data_mode_cells_lineage_and_the_dictionary(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    page = open_window(browser, server)
    window(server, "project.new", folder=str(tmp_path), name="sales", notebooks=["analysis"], app=False)
    data_tab = page.locator(".wb-tab", has_text="data.ipynb")
    expect(data_tab).to_be_visible(timeout=20000)
    data_tab.click()
    switch = page.locator(".wb-view-switch")
    expect(switch.get_by_role("button", name="Dictionary", exact=True)).to_be_visible()
    assert window(server, "data.view", view="dictionary") == {"view": "dictionary"}
    view = page.locator(".wb-data-view")
    expect(view.locator(".dict-columns tbody tr")).to_have_count(4, timeout=20000)
    expect(view.locator('tr[data-column="amount"] td').nth(1)).to_have_text("Decimal")
    expect(view.locator('tr[data-column="order_id"] td').nth(1)).to_have_text("Whole number")
    status = view.locator('tr[data-column="status"] input')
    status.fill("Shipped, delivered or returned")
    status.press("Enter")
    page.wait_for_timeout(400)
    window(server, "dictionary.describe", table="orders", text="One row per order line, shipped orders only.")
    shot(page, "data-dictionary")
    window(server, "file.save")
    saved = json.loads((tmp_path / "sales" / "data.ipynb").read_text(encoding="utf-8"))
    said = saved["metadata"]["swissarmybench"]["dictionary"]["orders"]
    assert said == {
        "description": "One row per order line, shipped orders only.",
        "columns": {"status": "Shipped, delivered or returned"},
    }
    window(server, "project.exportData")
    assert "#     status: Shipped, delivered or returned" in (tmp_path / "sales" / "data.py").read_text(
        encoding="utf-8"
    )
    # Lineage: the lineage overlay's own flow, drawn in place (data.ipynb's last cell: the orders
    # table's), its edges in the kind colours; a double-click on a node goes back to the cells.
    window(server, "data.view", view="lineage")
    placed = view.locator(".wb-lineage.in-place")
    expect(placed).to_be_visible(timeout=20000)
    expect(page.get_by_role("dialog", name="Lineage")).to_have_count(0)
    expect(placed.locator(".wb-lin-card.target")).to_contain_text("orders", timeout=20000)
    expect(placed.locator(".wb-lin-chart svg")).to_be_visible(timeout=20000)
    assert placed.evaluate("e => getComputedStyle(e).getPropertyValue('--lineage-notebook').trim()") == token(
        page, "notebook"
    )
    shot(page, "data-lineage")
    window(server, "data.view", view="cells")
    expect(page.locator(".wb-cells").first).to_be_visible()
    expect(view).to_be_hidden()
    page.context.close()


def test_a_panel_turned_off_in_settings_is_gone(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    expect(page.locator(".cv-block")).to_have_count(3, timeout=20000)
    bar = page.locator(".wb-status")
    expect(bar.get_by_role("button", name="Properties", exact=True)).to_be_visible()
    call(server, "PUT", "/panels", {"workbench.properties": False})
    try:
        expect(bar.get_by_role("button", name="Properties", exact=True)).to_have_count(0, timeout=10000)
        try:
            window(server, "mode.panel", panel="properties")
            raise AssertionError("the panel opened")
        except urllib.error.HTTPError as error:
            assert "turned off" in error.read().decode() or "none" in str(error)
    finally:
        call(server, "PUT", "/panels", {"workbench.properties": True})
    page.context.close()


@needs_streamlit
def test_play_preview_phone_dark_and_the_state_panel(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    expect(page.locator(".cv-block")).to_have_count(3, timeout=20000)
    window(server, "canvas.play")
    frame = page.frame_locator(".cv-frame")
    expect(frame.locator('[data-testid="stMetricValue"]')).to_be_visible(timeout=60000)
    window(server, "canvas.preview", device="phone", theme="dark")
    expect(page.locator(".cv-device.cv-phone")).to_be_visible()
    assert "dark_theme" in str(page.locator(".cv-frame").get_attribute("src"))
    page.locator(".wb-status").get_by_role("button", name="State", exact=True).click()
    state = page.locator(".wb-mode-state")
    expect(state.locator('tr[data-key="region_pick"]')).to_be_visible(timeout=30000)
    expect(state.locator('tr[data-key="region_pick"] td').nth(2)).to_have_text("Region filter")
    rows = window(server, "canvas.session")
    assert any(r["key"] == "region_pick" and r["block"] == "Region filter" for r in rows)
    shot(page, "app-state-preview")
    window(server, "canvas.resetState")
    page.context.close()


def test_two_groups_keep_their_own_panels(
    browser: Browser, server: dict[str, Any], orders: None, tmp_path: Path
) -> None:
    app = app_files(server, tmp_path / "sales")
    notebook = tmp_path / "sales" / "analysis.ipynb"
    call(
        server,
        "POST",
        "/workbench/save",
        {
            "path": str(notebook),
            "cells": [
                {"kind": "markdown", "source": "# Monthly sales"},
                {"kind": "code", "source": "x = 1", "name": "x"},
            ],
        },
    )
    page = open_window(browser, server, notebook)
    window(server, "file.open", path=str(app))
    expect(page.locator(".wb-tab")).to_have_count(2, timeout=20000)
    window(server, "group.splitRight")
    expect(page.locator(".wb-group")).to_have_count(2)
    window(server, "mode.panel", panel="properties", show=True)
    window(server, "canvas.select", block=window(server, "canvas.state")["pages"][0]["blocks"][0]["id"])
    window(server, "group.focus", group=0)
    window(server, "mode.panel", panel="outline", show=True)
    expect(page.locator(".wb-group").nth(0).locator(".wb-mode-outline")).to_be_visible()
    expect(page.locator(".wb-group").nth(1).locator(".wb-mode-properties")).to_be_visible()
    shot(page, "side-by-side")
    page.context.close()
