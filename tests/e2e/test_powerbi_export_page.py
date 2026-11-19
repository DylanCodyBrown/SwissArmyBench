# ruff: noqa: F811
"""Export to Power BI… on the ERD page in a real browser: the dialog lists the ERD's tables (a pasted one says
why it cannot go, with Include its rows), the relationships, and Export writes the Power BI Project into the
open project's powerbi/. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.renamed import env
from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.e2e.test_ui import server as plain_server  # noqa: F401

SHOTS = env("SWISSARMYBENCH_SHOTS") or None
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """The app with the Power BI extension on (from this checkout: SWISSARMYBENCH_EXTENSIONS)."""
    tmp = tmp_path_factory.mktemp("powerbi")
    source = str(ROOT / "extensions" / "powerbi" / "src")
    env_ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_EXTENSIONS": "streamlit,powerbi",
        "PYTHONPATH": os.pathsep.join([source, os.environ.get("PYTHONPATH", "")]).strip(os.pathsep),
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env_)
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def made_up_project(server: dict[str, Any]) -> Path:
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    folder = Path(server["tmp"]) / "Shop model"
    shutil.rmtree(folder, ignore_errors=True)
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


def test_without_the_extension_the_erd_has_no_power_bi_button(
    browser: Browser, plain_server: dict[str, Any]
) -> None:
    made_up_project(plain_server)
    context = browser.new_context(viewport={"width": 1200, "height": 800})
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{plain_server['port']}/workspace?view=erd#token={plain_server['token']}")
    expect(page.get_by_role("button", name="Manage relationships")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Export to Power BI…")).to_have_count(0)
    context.close()


def test_drop_a_report_map_one_field_by_hand_and_export(browser: Browser, server: dict[str, Any]) -> None:
    """A made-up .pbit dropped on the dialog: its fields mapped (one by hand), its pages in the export."""
    import base64

    from tests.test_powerbi_report_swap import pbit

    folder = made_up_project(server)
    sales = folder / "data" / "Sales.csv"
    sales.write_text("Region,Amount,Channel\nN,10.5,web\nE,3.0,shop\n", encoding="utf-8")
    call(server, "POST", "/datasets/Sales/load", {"path": str(sales)})
    link = {"from": "Sales", "from_columns": ["Region"], "to": "regions", "to_columns": ["region_code"]}
    call(
        server,
        "POST",
        "/relationships",
        {"model": {"name": "current", "relationships": [link]}, "replace": True},
    )
    base = f"http://127.0.0.1:{server['port']}"
    context = browser.new_context(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"{base}/workspace?view=erd#token={server['token']}")
    page.get_by_role("button", name="Export to Power BI…").click()
    dialog = page.locator("dialog.pbi-export")
    expect(dialog.locator(".pbi-drop")).to_be_visible(timeout=15000)
    encoded = base64.b64encode(pbit()).decode()
    dialog.locator(".pbi-drop").evaluate(
        """(zone, encoded) => {
          const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
          const data = new DataTransfer();
          data.items.add(new File([bytes], "Made-up sales.pbit"));
          zone.dispatchEvent(new DragEvent("drop", { dataTransfer: data, bubbles: true, cancelable: true }));
        }""",
        encoded,
    )
    expect(dialog.locator(".pbi-report-head")).to_contain_text("Made-up sales.pbit", timeout=15000)
    region = dialog.locator('.pbi-field[data-field="Sales.Region"] select')
    expect(region).to_have_value("Sales.Region")
    year = dialog.locator('.pbi-field[data-field="Calendar.Year"] select')
    expect(year).to_have_value("")
    year.select_option("regions.region_name")
    expect(dialog.locator('.pbi-field[data-field="Calendar.Year"] select')).to_have_value(
        "regions.region_name", timeout=10000
    )
    if SHOTS:
        dialog.screenshot(path=str(Path(SHOTS) / "powerbi-report-mapping.png"))
    dialog.get_by_role("button", name="Export", exact=True).click()
    expect(dialog.locator(".pbi-written")).to_contain_text("Shop model.pbip", timeout=20000)
    layout = (folder / "powerbi" / "Shop model.Report" / "report.json").read_text(encoding="utf-8")
    assert "regions.region_name" in layout and "Calendar.Year" not in layout
    tables = folder / "powerbi" / "Shop model.SemanticModel" / "definition" / "tables"
    assert "measure 'Total Sales' = SUM(Sales[Amount])" in (tables / "Sales.tmdl").read_text(encoding="utf-8")
    context.close()
