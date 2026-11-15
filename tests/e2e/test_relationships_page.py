# ruff: noqa: F811
"""Relationships on the page (the usability test's decision 20): the diagram fits the window when it
is drawn and has a Fit button; a Key Finder row has Compare on these and Add as relationship; and the
relationship file is imported under one name everywhere, Import relationships. Made-up orders, order
lines and customers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401


def tables(prefix: str) -> tuple[str, dict[str, Any]]:
    """Three made-up tables and the model that joins them. Returns the orders grid's address."""
    customers = pd.DataFrame({"customer_id": range(1, 41), "name": [f"Customer {i}" for i in range(1, 41)]})
    orders = pd.DataFrame(
        {
            "order_id": range(1, 201),
            "customer": [i % 40 + 1 for i in range(200)],
            "amount": [round(10 + i * 1.5, 2) for i in range(200)],
        }
    )
    lines = pd.DataFrame(
        {
            "line_id": range(1, 601),
            "order": [i % 200 + 1 for i in range(600)],
            "units": [i % 7 + 1 for i in range(600)],
        }
    )
    push_client.push(customers, name=f"{prefix}_customers", new_grid=True)
    push_client.push(lines, name=f"{prefix}_lines", new_grid=True)
    url = push_client.push(orders, name=f"{prefix}_orders", new_grid=True)
    model = {
        "name": f"{prefix} shop",
        "tables": {
            f"{prefix}_orders": {"primary_key": ["order_id"]},
            f"{prefix}_customers": {"primary_key": ["customer_id"]},
            f"{prefix}_lines": {"primary_key": ["line_id"]},
        },
        "relationships": [
            {
                "from": f"{prefix}_orders",
                "from_columns": ["customer"],
                "to": f"{prefix}_customers",
                "to_columns": ["customer_id"],
            },
            {
                "from": f"{prefix}_lines",
                "from_columns": ["order"],
                "to": f"{prefix}_orders",
                "to_columns": ["order_id"],
            },
        ],
    }
    return url, model


def boxes(page: Page) -> dict[str, float]:
    found: dict[str, float] = page.evaluate(
        """() => { const view = document.querySelector('#erd-view').getBoundingClientRect();
             const svg = document.querySelector('#erd-view .erd-diagram svg').getBoundingClientRect();
             return { view_bottom: view.bottom, view_right: view.right, view_left: view.left,
                      bottom: svg.bottom, right: svg.right, left: svg.left, width: svg.width,
                      height: svg.height }; }"""
    )
    return found


def test_the_diagram_fits_the_window_when_drawn_and_fit_puts_it_back(
    browser: Browser, server: dict[str, Any]
) -> None:
    url, model = tables("fit")
    call(server, "POST", "/relationships", {"model": model, "replace": True})
    page = open_grid(browser, url, width=900, height=520)  # a small window: the diagram is larger
    try:
        page.locator(".tab-erd").click()
        erd = page.locator("#erd-view")
        expect(erd.locator(".erd-diagram[data-fitted='true'] svg")).to_be_visible(timeout=30000)
        fitted = boxes(page)
        # All of it shows, with no scrolling: nothing below or beside the view.
        assert fitted["bottom"] <= fitted["view_bottom"] + 1 and fitted["right"] <= fitted["view_right"] + 1
        assert fitted["left"] >= fitted["view_left"] - 1 and fitted["width"] > 50
        assert erd.evaluate("v => v.scrollHeight <= v.clientHeight + 1")
        # Its own size is larger than this window; Fit (one action) puts it back.
        erd.get_by_role("button", name="Actual size").click()
        expect(erd.locator(".erd-diagram[data-fitted='false']")).to_be_visible()
        actual = boxes(page)
        assert actual["height"] > fitted["height"] and actual["bottom"] > actual["view_bottom"]
        erd.get_by_role("button", name="Fit", exact=True).click()
        again = boxes(page)
        assert again["height"] == fitted["height"] and again["bottom"] <= again["view_bottom"] + 1
        # A fitted diagram follows the window.
        page.set_viewport_size({"width": 900, "height": 420})
        page.wait_for_timeout(400)
        smaller = boxes(page)
        assert smaller["height"] < fitted["height"] and smaller["bottom"] <= smaller["view_bottom"] + 1
    finally:
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        page.close()


def test_a_key_finder_row_compares_on_its_columns_and_becomes_a_relationship(
    browser: Browser, server: dict[str, Any]
) -> None:
    url, _ = tables("kf")
    call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    page = open_grid(browser, url, width=1500, height=900)
    try:
        with page.expect_popup() as popup:
            page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Key Finder").click()
        finder = popup.value
        panel = finder.locator(".keys-window")
        row = panel.locator(".kf-row").filter(has_text="kf_customers").filter(has_text="customer_id").first
        expect(row).to_be_visible(timeout=30000)
        expect(row.locator(".known-pair")).to_have_count(0)

        # One action: the pair is a relationship, the row wears the crown, and the button says so.
        row.get_by_role("button", name="Add as relationship").click()
        expect(row.locator(".known-pair")).to_have_count(1, timeout=10000)
        expect(row.get_by_role("button", name="Add as relationship")).to_be_disabled()
        expect(row.get_by_role("button", name="Add as relationship")).to_have_attribute(
            "title", "Already a relationship"
        )
        expect(panel.locator(".kf-sample")).to_have_count(0)  # the row's own click was left alone
        joins = call(server, "GET", "/relationships")["relationships"]
        assert [(j["from"], j["from_columns"], j["to"], j["to_columns"], j["kind"]) for j in joins] == [
            ("kf_orders", ["customer"], "kf_customers", ["customer_id"], "many-to-one")
        ]

        # One action: the two tables are side by side in the grid window, lined up on the pair.
        row.get_by_role("button", name="Compare on these").click()
        expect(finder.locator(".toast")).to_contain_text("side by side in the grid window")
        panes = page.locator(".pane:not([hidden])")
        expect(panes).to_have_count(2, timeout=20000)
        expect(panes.nth(0).locator(".pane-head strong")).to_have_text("kf_orders")
        expect(panes.nth(1).locator(".pane-head strong")).to_have_text("kf_customers")
        expect(page.locator(".ribbon")).to_contain_text("customer = customer_id")
        expect(page.locator(".ribbon")).to_contain_text(re.compile(r"\d+ matched"))
        expect(page.locator("dialog[open]")).to_have_count(0)  # no key picker: the keys were chosen
    finally:
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        page.close()


def test_import_relationships_is_one_name_and_takes_a_model_or_a_tang(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    url, model = tables("imp")
    call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    as_json = tmp_path / "shop.json"
    as_json.write_text(json.dumps(model), encoding="utf-8")
    page = open_grid(browser, url, width=1500, height=900)
    try:
        # The Diagram tab: a model as JSON is applied as it is.
        page.locator(".tab-erd").click()
        erd = page.locator("#erd-view")
        expect(erd).to_contain_text("No relationships yet")
        with page.expect_file_chooser() as chooser:
            erd.get_by_role("button", name="Import relationships").click()
        chooser.value.set_files(str(as_json))
        expect(erd.locator(".erd-diagram svg")).to_be_visible(timeout=30000)
        expect(erd.locator(".erd-diagram")).to_contain_text("customer_id")

        # The same name in the Relationships window, and nowhere another name for it.
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        erd.get_by_role("button", name="Manage relationships").click()
        dialog = page.locator("dialog")
        expect(dialog.get_by_role("button", name="Import relationships")).to_be_visible()
        assert page.get_by_role("button", name=re.compile("Import a")).count() == 0
        # A tang from here or from the Diagram tab is reviewed first, then applied.
        saved = tmp_path / "shop.tang"
        saved.write_text(tang_text(server, model), encoding="utf-8")
        with page.expect_file_chooser() as chooser:
            dialog.get_by_role("button", name="Import relationships").click()
        chooser.value.set_files(str(saved))
        review = page.locator("dialog", has_text="Only adds; changes nothing.")
        expect(review).to_contain_text("2 joins")
        review.get_by_role("button", name="Apply").click()
        expect(page.locator(".toast", has_text="Applied imp shop")).to_be_visible()
        assert len(call(server, "GET", "/relationships")["relationships"]) == 2
    finally:
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        page.close()


def tang_text(server: dict[str, Any], model: dict[str, Any]) -> str:
    """The model as a .tang file, written by the app itself (domain/relationships.py write_tang)."""
    from swissarmybench.domain.relationships import parse_model, write_tang

    return write_tang(parse_model(model))
