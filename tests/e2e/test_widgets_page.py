"""The Widgets window (the owner, 2026-11-21), with a Python that has Streamlit: a widget with a table and a
colour property shows both in Properties with their masks; Run turns the editor into the running widget in
place, Edit turns it back; the colour changed in Properties is written into the code; Name and Description go
into the header. Screenshots when SWISSARMYBENCH_WIDGET_SHOTS names a folder. Made-up data."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_shared import until
from tests.streamlit_helpers import needs_streamlit

SHOTS = os.environ.get("SWISSARMYBENCH_WIDGET_SHOTS")
CODE = """import altair as alt
import streamlit as st

from sab_canvas import key, table

# The table to chart
table_name = "orders"  # table
# The bars' colour
colour = "#1f77b4"
title = "Revenue by region"

frame = table(table_name)
st.subheader(title)
chart = alt.Chart(frame).mark_bar(color=colour).encode(x="region", y="sum(revenue)")
st.altair_chart(chart, key=key("chart"))
"""


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(600)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[None]:  # noqa: F811
    close_tables(server)
    frame = pd.DataFrame(
        {
            "region": ["North", "South", "East", "West"] * 3,
            "revenue": [120.0, 95.5, 143.0, 88.0] * 3,
            "units": list(range(12)),
        }
    )
    push_client.push(frame, name="orders", new_grid=True)
    yield
    for name in ("region_chart", "region_revenue"):
        try:
            call(server, "DELETE", f"/streamlit/widgets/{name}")
        except Exception:  # noqa: S110 (renamed or never made)
            pass
    close_tables(server)


def open_widgets(browser: Browser, server: dict[str, Any], name: str) -> Page:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1500, "height": 900}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    # The session's cookie first (the Widgets window opens from a page that has it: the rail's Widgets).
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    page.wait_for_load_state("networkidle")
    page.goto(f"http://127.0.0.1:{server['port']}/streamlit/widget?name={name}#token={server['token']}")
    expect(page.locator(".wg-editor .monaco-editor")).to_be_visible(timeout=30000)
    return page


@needs_streamlit
def test_write_a_widget_run_it_in_place_and_change_its_colour(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,
) -> None:
    call(
        server,
        "POST",
        "/streamlit/widgets",
        {"name": "region_chart", "description": "Revenue by region", "code": CODE},
    )
    page = open_widgets(browser, server, "region_chart")
    props = page.locator(".wg-props")
    # The list: the library's widget first, then the prebuilt ones by group.
    expect(page.locator(".wg-item[data-widget='region_chart']")).to_have_class("wg-item selected")
    expect(page.locator(".wg-item[data-widget='line_chart']")).to_be_visible()
    # Its properties with their masks: a table picker, a colour picker, a text box.
    expect(props.locator(".wg-prop[data-property='table_name']")).to_have_attribute("data-mask", "table")
    expect(props.locator(".wg-prop[data-property='colour']")).to_have_attribute("data-mask", "colour")
    expect(props.locator(".wg-prop[data-property='table_name'] select")).to_have_value("orders")
    expect(props.locator(".wg-prop[data-property='colour'] .wg-prop-help")).to_have_text("The bars' colour")
    shot(page, "widgets-window-code")
    # Run: the editor becomes the running widget, in place.
    page.locator(".wg-run").click()
    frame = page.frame_locator(".wg-frame")
    expect(frame.get_by_text("Revenue by region")).to_be_visible(timeout=120000)
    expect(page.locator(".wg-editor")).to_be_hidden()
    expect(frame.locator("[data-testid='stVegaLiteChart'], .vega-embed").first).to_be_visible(timeout=60000)
    shot(page, "widgets-window-run")
    # The colour changed in Properties: written into the code's own characters (and run again).
    colour = props.locator(".wg-prop[data-property='colour'] .wg-colour-text")
    colour.fill("not a colour")
    colour.press("Enter")
    expect(props.locator(".wg-prop[data-property='colour'] .wg-field-line")).to_contain_text("not a colour")
    colour.fill("#d62728")
    colour.press("Enter")
    until(
        lambda: 'colour = "#d62728"' in call(server, "GET", "/streamlit/widgets/region_chart")["code"],
        True,
        20,
    )
    expect(props.locator(".wg-prop[data-property='colour'] .wg-field-line")).to_be_hidden()
    # Edit (Esc): the code again, with the new colour in it.
    page.keyboard.press("Escape")
    expect(page.locator(".wg-editor")).to_be_visible()
    expect(page.locator(".wg-editor .view-lines")).to_contain_text('colour = "#d62728"')
    # Name and Description: the header only; the name checked as it is typed.
    name = props.locator(".wg-name")
    name.fill("button")
    expect(props.locator(".wg-name-line")).to_have_text("button is taken: another widget has that name.")
    name.fill("region_revenue")
    expect(props.locator(".wg-name-line")).to_have_text("region_revenue is available.")
    name.press("Enter")
    props.locator(".wg-description").fill("Revenue for each region, as bars")
    props.locator(".wg-description").blur()
    until(
        lambda: call(server, "GET", "/streamlit/widgets/region_revenue")["description"],
        "Revenue for each region, as bars",
        20,
    )
    saved = call(server, "GET", "/streamlit/widgets/region_revenue")
    assert saved["code"] == CODE.replace("#1f77b4", "#d62728")
    expect(page.locator(".wg-item[data-widget='region_revenue']")).to_be_visible()
    page.context.close()


def test_a_prebuilt_widget_is_read_only_and_copied_as_your_own(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
) -> None:
    page = open_widgets(browser, server, "kpi_row_3")
    expect(page.locator(".wg-saved")).to_have_text("Prebuilt: read-only")
    expect(page.locator(".wg-props .wg-name")).to_have_attribute("readonly", "")
    page.locator(".wg-copy").click()
    expect(page.locator(".wg-title")).to_have_text("my_kpi_row_3")
    expect(page.locator(".wg-item[data-widget='my_kpi_row_3']")).to_be_visible()
    call(server, "DELETE", "/streamlit/widgets/my_kpi_row_3")
    page.context.close()
