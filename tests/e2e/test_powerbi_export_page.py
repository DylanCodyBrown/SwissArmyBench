# ruff: noqa: F811
"""Export to Power BI… on the ERD page in a real browser: the dialog lists the ERD's tables (a pasted one says
why it cannot go, with Include its rows), the relationships, and Export writes the Power BI Project into the
open project's powerbi/. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from swissarmybench.renamed import env
from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = env("SWISSARMYBENCH_SHOTS") or None


def made_up_project(server: dict[str, Any]) -> Path:
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    folder = Path(server["tmp"]) / "Shop model"
    call(server, "POST", "/project/new", {"path": str(folder)})
    (folder / "data").mkdir()
    (folder / "data" / "orders.csv").write_text(
        "order_id,region_code,units\n1,N,3\n2,E,9\n3,S,5\n", encoding="utf-8"
    )
    (folder / "data" / "regions.csv").write_text(
        "region_code,region_name\nN,North\nE,East\nS,South\n", "utf-8"
    )
    call(server, "POST", "/datasets/orders/load", {"path": str(folder / "data" / "orders.csv")})
    call(server, "POST", "/datasets/regions/load", {"path": str(folder / "data" / "regions.csv")})
    model = {
        "name": "current",
        "relationships": [
            {
                "from": "orders",
                "from_columns": ["region_code"],
                "to": "regions",
                "to_columns": ["region_code"],
            },
            {
                "from": "targets",
                "from_columns": ["region_code"],
                "to": "regions",
                "to_columns": ["region_code"],
            },
        ],
    }
    call(server, "POST", "/relationships", {"model": model, "replace": True})
    return folder


def test_export_to_power_bi_from_the_erd(browser: Browser, server: dict[str, Any]) -> None:
    folder = made_up_project(server)
    base = f"http://127.0.0.1:{server['port']}"
    # A pasted table (no source Power Query can read): its rows go only on the tick.
    request_body = "region_code\ttarget\nN\t10\nE\t20\n"
    import urllib.request

    pasted = urllib.request.Request(  # noqa: S310 (the test's own server)
        f"{base}/datasets/targets/paste",
        data=request_body.encode(),
        method="POST",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    urllib.request.urlopen(pasted, timeout=30).read()  # noqa: S310 (the test's own server)
    context = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"{base}/workspace?view=erd#token={server['token']}")
    opener = page.get_by_role("button", name="Export to Power BI…")
    expect(opener).to_be_visible(timeout=20000)
    opener.click()
    dialog = page.locator("dialog.pbi-export")
    expect(dialog.locator(".pbi-table")).to_have_count(3, timeout=15000)
    targets = dialog.locator('.pbi-table[data-table="targets"]')
    expect(targets.locator(".pbi-why")).to_contain_text("pasted")
    expect(dialog.locator(".pbi-local").first).to_contain_text("Only works on your machine")
    expect(dialog.locator(".pbi-name")).to_have_value("Shop model")
    targets.get_by_label("Include its rows").first.check()
    expect(targets).not_to_have_class("pbi-table pbi-not", timeout=10000)
    expect(dialog.locator(".pbi-rels").first).to_contain_text("targets.region_code")
    if SHOTS:
        dialog.screenshot(path=str(Path(SHOTS) / "powerbi-export-dialog.png"))
    dialog.get_by_role("button", name="Export", exact=True).click()
    expect(dialog.locator(".pbi-written")).to_contain_text("Shop model.pbip", timeout=20000)
    expect(dialog.get_by_role("button", name="Show its folder")).to_be_visible()
    out = folder / "powerbi"
    assert (out / "Shop model.pbip").is_file()
    assert (out / "Shop model.SemanticModel" / "definition" / "tables" / "orders.tmdl").is_file()
    assert (out / "Shop model.SemanticModel" / "data" / "targets.parquet").is_file()
    assert (
        "relationship" in (out / "Shop model.SemanticModel" / "definition" / "relationships.tmdl").read_text()
    )
    if SHOTS:
        dialog.screenshot(path=str(Path(SHOTS) / "powerbi-export-done.png"))
    context.close()
