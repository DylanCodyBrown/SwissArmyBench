# ruff: noqa: F811
"""sab.visualizations from Python: a card of no table (badged "Python"), an Altair-style Vega-Lite chart drawn
from its inline data, a key that replaces a card in place, and a table of its own rows."""

from __future__ import annotations

import json
from typing import Any

import pyarrow as pa
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client, visualizations_client
from tests.e2e.test_ui import browser, open_grid, server  # noqa: F401

SPEC = {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "mark": "bar",
    "data": {"values": [{"region": r, "sales": s} for r, s in (("North", 40), ("South", 25), ("East", 31))]},
    "encoding": {
        "x": {"field": "region", "type": "nominal"},
        "y": {"field": "sales", "type": "quantitative"},
    },
}


def test_python_cards_draw_in_the_sandbox(browser: Browser, server: dict[str, Any]) -> None:
    url = push_client.push(pa.table({"n": [1, 2, 3]}), name="python_cards", new_grid=True)
    page = open_grid(browser, url, width=1280, height=900)
    try:
        visualizations_client.add_card(SPEC, "Sales by region", key="sales")
        visualizations_client.add_card(json.dumps({"x": 1}), "First draft", key="notes", kind="markdown")
        visualizations_client.add_card("## Findings\n\nNorth sells most.", "Findings", key="notes")
        visualizations_client.add_card([{"store": "S1", "units": 3}, {"store": "S2", "units": 5}], "Stores")
        page.locator(".nav-rail [data-area='analyze']").click()
        panel = page.locator("#ai-panel")
        chart = panel.locator(".card", has_text="Sales by region")
        expect(chart.locator(".card-table")).to_have_text("Python")
        expect(chart.locator("svg .mark-rect path, svg .mark-rect rect").first).to_be_attached(timeout=20000)
        expect(chart.locator("svg text", has_text="North").first).to_be_attached()
        expect(panel.locator(".card-header h3", has_text="First draft")).to_have_count(0)  # replaced
        findings = panel.locator(".card", has_text="Findings")
        expect(findings.locator(".card-body, .card-content").first).to_contain_text("North sells most.")
        expect(panel.locator(".card", has_text="Stores").locator("tbody tr")).to_have_count(2)
    finally:
        page.close()
