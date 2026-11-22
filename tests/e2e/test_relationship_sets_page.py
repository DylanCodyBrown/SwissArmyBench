# ruff: noqa: F811
"""Relationship sets (tangs until 2026-11-17), the relationship finder, and the joins in use managed, in a
real browser, on made-up tables only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from examples.sample_store import make_store
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from swissarmybench.domain.relationships import read_set

# The grid tests' fixtures (browser, server) are imported by name, which pytest needs and ruff reads
# as a redefinition in every test that takes them.
from tests.e2e.asks import answer_ask
from tests.e2e.test_ui import browser, call, grid_of, open_grid, server  # noqa: F401

# Screenshots of the dialog, when a folder is named (SAB_SHOTS=<folder>): PNG at device scale 2.
SHOTS = os.environ.get("SAB_SHOTS", "")


def test_find_accept_check_and_share_a_set(browser: Browser, server: dict[str, Any], tmp_path: Path) -> None:
    urls = [push_client.push(frame, name=name, new_grid=True) for name, frame in make_store().items()]
    team = tmp_path / "team"
    team.mkdir()
    call(server, "PUT", "/blades/folders", {"folders": [str(team)]})
    call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    page = open_grid(browser, urls[0], width=1440)
    try:
        page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Relationships").click()
        dialog = page.locator("dialog")
        expect(dialog).to_contain_text("No saved sets yet")
        assert "tang" not in dialog.inner_text().lower()
        dialog.get_by_role("button", name="Find relationships").click()
        suggestions = dialog.locator(".suggestion")
        expect(suggestions).to_have_count(10, timeout=60000)
        expect(dialog.locator(".suggestion", has_text="ship_date")).to_contain_text("inactive")
        expect(dialog.locator(".suggestion input:checked")).to_have_count(10)
        # Added at once (no Accept step), drawn beside the list; Undo takes them out, a tick adds one back.
        expect(dialog.locator(".rel-found-diagram svg")).to_be_visible(timeout=30000)
        page.locator(".toast", has_text="Added 10 joins").get_by_role("button", name="Undo").click()
        expect(dialog.locator(".suggestion input:checked")).to_have_count(0, timeout=20000)
        expect(dialog.locator(".rel-table tbody tr")).to_have_count(0)
        dialog.get_by_role("button", name="Find again").click()
        current = dialog.locator(".rel-table tbody tr")
        expect(current).to_have_count(10, timeout=20000)
        expect(dialog.locator(".suggestion.known")).to_have_count(10, timeout=60000)  # now in use
        dialog.get_by_role("button", name="Check against the open tables").click()
        expect(dialog.locator(".rel-table tr.run-orphans")).to_have_count(
            1, timeout=60000
        )  # orders -> customers
        expect(dialog.locator(".rel-table tr.run-holds")).to_have_count(9)
        # Save it where the team sees it.
        dialog.get_by_role("button", name="Save as a set…").click()
        save = page.locator("dialog").last
        save.get_by_label("Set name").fill("Sample store")
        save.get_by_label("Tags").fill("sales, made-up")
        save.get_by_label("Save it in").select_option(str(team))
        save.get_by_role("button", name="Save").click()
        expect(page.locator(".toast").last).to_contain_text("Saved Sample store in the shared folder")
        listed = dialog.locator(".set-item", has_text="Sample store")
        expect(listed.locator(".set-where")).to_have_text("Shared")
        expect(listed).to_contain_text("10 joins")
        saved = read_set((team / "sample_store.relationships.json").read_text(encoding="utf-8"))
        assert saved.tags == ("sales", "made-up") and len(saved.relationships) == 10
        # Its menu: rename it, then delete it.
        listed.get_by_role("button", name="More for Sample store").click()
        page.locator(".menu").get_by_text("Rename…").click()
        rename = page.locator("dialog").last
        rename.get_by_label("New name").fill("Sample store 2026")
        rename.get_by_role("button", name="Rename").click()
        renamed = dialog.locator(".set-item", has_text="Sample store 2026")
        expect(renamed).to_be_visible()
        assert (team / "sample_store_2026.relationships.json").is_file()
        assert not (team / "sample_store.relationships.json").exists()
        renamed.get_by_role("button", name="More for Sample store 2026").click()
        page.locator(".menu").get_by_text("Delete").click()
        answer_ask(page)
        expect(dialog.locator(".set-item")).to_have_count(0)
        assert not (team / "sample_store_2026.relationships.json").exists()
    finally:
        page.close()
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        call(server, "PUT", "/blades/folders", {"folders": []})
        for url in urls:
            call(server, "DELETE", f"/grids/{grid_of(url)}")


def forty() -> dict[str, Any]:
    """About 40 made-up foreign keys with long names, as a database's import brings them."""
    return {
        "name": "FI-Atlas foreign keys",
        "relationships": [
            {
                "from": f"general_ledger_entry_line_{i:02d}",
                "from_columns": ["posting_account_identifier", "company_code"],
                "to": f"chart_of_accounts_dimension_{i % 4}",
                "to_columns": ["account_identifier", "company_code"],
                "note": "foreign key FK_general_ledger_entry_line_chart_of_accounts_with_a_long_name",
            }
            for i in range(40)
        ],
    }


def open_dialog(page: Page) -> Any:
    page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Relationships").click()
    dialog = page.locator("dialog.rel-dialog")
    expect(dialog.locator(".rel-table tbody tr")).to_have_count(40, timeout=20000)
    return dialog


def no_sideways_scroll(dialog: Any) -> None:
    sizes = dialog.evaluate(
        """d => [d, ...['.dialog-body', '.rel-scroll', '.dialog-foot'].map(s => d.querySelector(s))]
            .map(e => [e.scrollWidth, e.clientWidth])"""
    )
    for scroll_width, client_width in sizes:
        assert scroll_width <= client_width, sizes
    box = dialog.bounding_box()
    viewport = dialog.page.viewport_size
    assert box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"]
    assert box["y"] >= 0 and box["y"] + box["height"] <= viewport["height"]


@pytest.mark.parametrize("width", [700, 1600])
def test_forty_relationships_fit_the_window_and_are_managed(
    browser: Browser, server: dict[str, Any], width: int
) -> None:
    url = push_client.push(pd.DataFrame({"x": [1, 2]}), name="rel_manage", new_grid=True)
    call(server, "POST", "/relationships", {"model": forty(), "replace": True})
    page = open_grid(browser, url, width=width, height=900, device_scale_factor=2)
    try:
        dialog = open_dialog(page)
        no_sideways_scroll(dialog)
        run_header = dialog.locator(".rel-table thead th", has_text="Run")
        expect(run_header).to_be_visible()
        cell = dialog.locator(".rel-table tbody tr").first.locator(".rel-col-from")
        assert cell.get_attribute("title") == "general_ledger_entry_line_00"  # cut, all of it in its tooltip
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / f"relationships-{width}.png"))

        # Select all, Delete selected, then the toast's Undo brings all 40 back.
        dialog.get_by_label("Select all").check()
        expect(dialog.locator(".rel-count")).to_have_text("40 selected")
        dialog.get_by_role("button", name="Delete selected").click()
        expect(dialog).to_contain_text("No joins in use yet.")
        toast = page.locator(".toast", has_text="Deleted 40 relationships")
        expect(toast).to_be_visible()
        toast.get_by_role("button", name="Undo").click()
        expect(dialog.locator(".rel-table tbody tr")).to_have_count(40)
        assert len(call(server, "GET", "/relationships")["relationships"]) == 40

        # Filter by a table, select a shift-click range, bulk Run off.
        dialog.get_by_label("Filter relationships").fill("dimension_1")
        rows = dialog.locator(".rel-table tbody tr")
        expect(rows).to_have_count(10)
        expect(dialog.locator(".rel-count")).to_have_text("10 of 40")
        rows.nth(0).locator(".rel-col-pick input").click()
        rows.nth(3).locator(".rel-col-pick input").click(modifiers=["Shift"])
        expect(dialog.locator(".rel-count")).to_have_text("4 selected")
        dialog.get_by_role("button", name="Run off").click()
        expect(dialog.locator(".rel-table tbody tr.rel-off")).to_have_count(4)
        model = call(server, "GET", "/relationships")
        assert sum(1 for r in model["relationships"] if r.get("active") is False) == 4

        # Select all takes only the filtered rows.
        dialog.get_by_label("Select all").check()
        expect(dialog.locator(".rel-count")).to_have_text("10 selected")
        dialog.get_by_label("Select all").uncheck()

        # A row's Kind and Run in place.
        first = rows.first
        first.locator(".rel-kind").select_option("one-to-one")
        expect(page.locator(".toast", has_text="Kind one-to-one")).to_be_visible()
        first.locator(".rel-run-switch").check()
        expect(dialog.locator(".rel-table tbody tr.rel-off")).to_have_count(3)
        changed = call(server, "GET", "/relationships")["relationships"]
        assert {r["kind"] for r in changed if r["from"] == "general_ledger_entry_line_01"} == {"one-to-one"}

        # Sort by From, descending; group by From table.
        dialog.get_by_label("Filter relationships").fill("")
        expect(rows).to_have_count(40)
        dialog.locator(".rel-table thead").get_by_role("button", name="From").click()
        dialog.locator(".rel-table thead").get_by_role("button", name="From").click()
        expect(rows.first.locator(".rel-col-from")).to_have_text("general_ledger_entry_line_39")
        dialog.get_by_role("button", name="Group by From table").click()
        expect(dialog.locator(".rel-table tr.rel-group")).to_have_count(40)

        # A row's own menu deletes it alone.
        rows = dialog.locator(".rel-table tbody tr:not(.rel-group)")
        rows.first.get_by_role("button", name="More for general_ledger_entry_line_39").click()
        page.locator(".menu").get_by_text("Delete").click()
        expect(rows).to_have_count(39)
        no_sideways_scroll(dialog)
    finally:
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        call(server, "DELETE", f"/grids/{grid_of(url)}")
        page.close()


def test_deleting_a_connection_says_how_many_relationships_went(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    csv = tmp_path / "made-up.csv"
    csv.write_text("a\n1\n", encoding="utf-8")
    blade = {
        "name": "FI-Atlas",
        "kind": "other",
        "template": "csv",
        "code": f'from pathlib import Path\npath = Path(r"{csv}")',
    }
    call(server, "POST", "/connections", blade)
    model = forty()
    model["tables"] = {r["from"]: {"source": "connection:FI-Atlas"} for r in model["relationships"]}
    call(server, "POST", "/relationships", {"model": model, "replace": True})
    url = push_client.push(pd.DataFrame({"x": [1, 2]}), name="rel_conn", new_grid=True)
    page = open_grid(browser, url, width=1400, height=900)
    try:
        page.locator(".nav-rail [data-area='connections']").click()
        page.locator(".connection-card", has_text="FI-Atlas").first.click()
        page.locator(".connection-detail-tools").get_by_role("button", name="Remove").click()
        answer_ask(page)
        expect(
            page.locator(".toast", has_text="Removed 40 relationships that came from FI-Atlas")
        ).to_be_visible()
        assert call(server, "GET", "/relationships")["relationships"] == []
    finally:
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        call(server, "DELETE", f"/grids/{grid_of(url)}")
        page.close()


def test_the_erd_draws_the_tables_the_project_uses_with_a_switch(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    import json

    tables = [f"fi_table_{i:02d}" for i in range(36)] + [
        "gl_entry",
        "gl_account",
        "dbo_Vendor",
        "cost_center",
    ]
    model = {
        "name": "FI-Atlas foreign keys",
        "tables": {t: {"source": "connection:FI-Atlas"} for t in tables},
        "relationships": [
            {"from": "gl_entry", "from_columns": ["account"], "to": "gl_account", "to_columns": ["id"]},
            {"from": "gl_entry", "from_columns": ["cc"], "to": "cost_center", "to_columns": ["id"]},
            *(
                {"from": f"fi_table_{i:02d}", "from_columns": ["k"], "to": "gl_account", "to_columns": ["id"]}
                for i in range(36)
            ),
        ],
    }
    call(server, "POST", "/relationships", {"model": model, "replace": True})
    folder = tmp_path / "ledger"
    call(server, "POST", "/project/new", {"path": str(folder)})
    cell = {
        "cell_type": "code",
        "source": "%%sql FI-Atlas\nSELECT * FROM [FI-Atlas].gl_entry JOIN gl_account ON 1=1",
    }
    (folder / "report.ipynb").write_text(
        json.dumps(
            {
                "cells": [cell | {"metadata": {}, "outputs": []}],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    url = push_client.push(pd.DataFrame({"x": [1, 2]}), name="rel_scope", new_grid=True)
    page = open_grid(browser, url, width=1400, height=900, device_scale_factor=2)
    try:
        page.locator(".nav-rail [data-area='erd']").click()
        erd = page.locator("#erd-view")
        expect(erd.get_by_role("button", name="Tables in this project")).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(erd.locator(".erd-hidden")).to_have_text(
            "38 more tables from FI-Atlas are not used in this project."
        )
        diagram = erd.locator(".erd-diagram svg")
        expect(diagram).to_be_visible(timeout=30000)
        expect(diagram.get_by_text("gl_entry", exact=True).first).to_be_visible()
        assert diagram.get_by_text("cost_center", exact=True).count() == 0  # one end not used: not drawn
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / "erd-project-tables.png"))
        erd.get_by_role("button", name="All tables").click()
        expect(erd.get_by_role("button", name="All tables")).to_have_attribute("aria-pressed", "true")
        expect(erd.locator(".erd-diagram svg").get_by_text("cost_center", exact=True).first).to_be_visible(
            timeout=30000
        )
        # The Relationships window: the project's joins by default, all on the switch.
        erd.get_by_role("button", name="Manage relationships").click()
        dialog = page.locator("dialog.rel-dialog")
        expect(dialog.locator(".rel-table tbody tr")).to_have_count(1, timeout=20000)
        expect(dialog.locator(".rel-hidden")).to_contain_text("38 more tables from FI-Atlas")
        dialog.get_by_role("button", name="All tables").click()
        expect(dialog.locator(".rel-table tbody tr")).to_have_count(38)
        assert len(call(server, "GET", "/relationships")["relationships"]) == 38  # the model keeps them all
    finally:
        call(server, "POST", "/project/close", {"discard": True})  # its grids close with it
        call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
        page.close()
