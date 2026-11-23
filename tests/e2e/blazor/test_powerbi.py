"""The Blazor pages of the Power BI extension on made-up data: the ERD's Export to Power BI… (an extension's
page action: the tables with why Power Query cannot read one and Include its rows, the relationships that
go, the Name, Export into the open project's powerbi/ and its Open or Show its folder button) and the Power
BI rail area's page drawn from its panel data."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page
from tests.e2e.blazor.extension_server import extension_server


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    with extension_server(tmp_path_factory.mktemp("blazor-powerbi"), ["streamlit", "powerbi"]) as info:
        yield info


def test_export_to_power_bi_from_the_erd(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/project/new", {"name": "Sales model", "type": "bi"})
    call(server, "POST", "/samples/store", {})
    found = call(server, "POST", "/relationships/find", {"tables": ["customers", "orders", "products"]})
    joins = [
        {k: s[k] for k in ("from", "from_columns", "to", "to_columns")}
        | {"kind": s.get("kind", "many-to-one")}
        for s in found["suggestions"]
    ]
    call(server, "POST", "/relationships", {"model": {"relationships": joins}})
    page = open_page(browser, server, "erd")
    page.click("button:has-text('All tables')")
    page.click("button[data-action=powerbi_export]")
    dialog = page.locator(".dialog[aria-label='Export to Power BI']")
    expect(dialog.locator(".pbi-table[data-table=orders]")).to_be_visible(timeout=20_000)
    expect(dialog.locator(".pbi-table[data-table=orders] .pbi-why")).to_contain_text(
        "Power Query cannot read it"
    )
    expect(dialog.locator("h3", has_text="Relationships")).to_contain_text("Relationships (")
    expect(dialog.locator(".pbi-name")).to_have_value("Sales model")
    for table in ("customers", "orders", "products"):
        dialog.locator(f".pbi-table[data-table={table}] .pbi-rows input").check()
    expect(dialog.locator(".pbi-table[data-table=orders] .pbi-rows")).to_contain_text(
        "Include its rows (120)"
    )
    expect(dialog.locator(".pbi-drop")).to_contain_text("Use an existing report's pages")
    dialog.locator(".dialog-foot button:has-text('Export')").click()
    expect(dialog.locator(".pbi-written")).to_contain_text("files written", timeout=30_000)
    expect(dialog.locator(".pbi-done button")).to_contain_text("Show its folder")
    assert (server["tmp"] / "projects" / "Sales model" / "powerbi").is_dir()
    page.close()


def test_the_power_bi_page_is_drawn_from_its_panel(browser: Browser, server: dict[str, Any]) -> None:
    said = call(server, "GET", "/powerbi/panel")
    page = open_page(browser, server, "x-powerbi")
    expect(page.locator(".area-page-title")).to_contain_text("Power BI")
    expect(page.locator(".extension-panel-line").first).to_have_text(said["lines"][0]["text"])
    page.close()
