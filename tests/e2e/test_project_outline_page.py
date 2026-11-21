# ruff: noqa: F811
"""The project's outline in a real browser (the owner, 2026-11-17): Export outline in the project's group
writes ARCHITECTURE.md and offers its Download (the same bytes); both of its Mermaid diagrams (the
erDiagram and the flowchart) drawn by the app's own Mermaid (lazy/diagram.ts) without an error; the
Workbench's project menu has Export outline too. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x)."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None


def outline_text(server: dict[str, Any]) -> str:
    request = urllib.request.Request(
        f"http://127.0.0.1:{server['port']}/project/outline",
        headers={"Authorization": f"Bearer {server['token']}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return str(response.read().decode("utf-8"))


def made_up_project(server: dict[str, Any]) -> Path:
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    folder = Path(server["tmp"]) / "Outline demo"
    call(server, "POST", "/project/new", {"path": str(folder)})
    (folder / "README.md").write_text(
        "# Outline demo\n\nA made-up shop's orders by region, for the outline's browser test.\n",
        encoding="utf-8",
    )
    (folder / "data").mkdir()
    (folder / "data" / "orders.csv").write_text(
        "order_id,region_code,units\n1,N,3\n2,E,9\n3,S,5\n", encoding="utf-8"
    )
    (folder / "data" / "regions.csv").write_text(
        "region_code,region_name\nN,North\nE,East\nS,South\n", "utf-8"
    )
    grid = call(server, "POST", "/datasets/orders/load", {"path": str(folder / "data" / "orders.csv")})[
        "grid"
    ]
    call(server, "POST", "/datasets/regions/load", {"path": str(folder / "data" / "regions.csv")})
    step = {"kind": "filter", "params": {"column": "units", "op": "gt", "value": 2}}
    call(server, "POST", f"/grids/{grid}/steps", {"steps": [step]})
    model = {
        "name": "current",
        "relationships": [
            {
                "from": "orders",
                "from_columns": ["region_code"],
                "to": "regions",
                "to_columns": ["region_code"],
            }
        ],
    }
    call(server, "POST", "/relationships", {"model": model, "replace": True})
    return folder


def test_export_outline_writes_architecture_md_offers_it_and_its_diagrams_draw(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    folder = made_up_project(server)
    context = browser.new_context(
        viewport={"width": 1400, "height": 900}, device_scale_factor=2, accept_downloads=True
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace?view=grids#token={server['token']}")
    export = page.get_by_role("button", name="Export outline")
    expect(export).to_be_visible(timeout=20000)
    export.click()
    toast = page.locator(".toast", has_text="ARCHITECTURE.md written")
    expect(toast).to_be_visible()
    written = (folder / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert written == outline_text(server)
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "export-outline.png"))
    with page.expect_download() as got:
        toast.get_by_role("button", name="Download").click()
    download = got.value
    assert download.suggested_filename == "ARCHITECTURE.md"
    saved = tmp_path / "downloaded.md"
    download.save_as(saved)
    assert saved.read_text(encoding="utf-8") == written
    # A second Export changes no byte, and says so.
    page.get_by_role("button", name="Export outline").click()
    expect(page.locator(".toast", has_text="ARCHITECTURE.md is up to date")).to_be_visible()

    # Both Mermaid blocks, drawn by the app's own Mermaid: an SVG each, no error.
    blocks = re.findall(r"```mermaid\n(.*?)\n```", written, re.DOTALL)
    assert [b.split("\n", 1)[0] for b in blocks] == ["erDiagram", "flowchart LR"]
    # And the golden outline's (a store of five tables, its lineage through cells to an app).
    golden = Path(__file__).parents[1] / "golden" / "project_outline" / "store_analysis.md"
    blocks += re.findall(r"```mermaid\n(.*?)\n```", golden.read_text(encoding="utf-8"), re.DOTALL)
    page.evaluate("document.querySelector('.toasts')?.remove()")
    drawn = page.evaluate(
        """async (blocks) => {
          const m = await import("/static/build/lazy/diagram.js");
          const out = [];
          for (const text of blocks) {
            const host = document.createElement("div");
            host.className = "outline-check";
            host.style.cssText = "width:900px;height:600px;background:#fff";
            document.body.append(host);
            let error = "";
            try {
              await m.drawDiagram(host, text, false);
            } catch (e) {
              error = String(e && e.message ? e.message : e);
            }
            out.push({ svg: !!host.querySelector("svg"), error });
          }
          return out;
        }""",
        blocks,
    )
    assert drawn == [{"svg": True, "error": ""}] * 4, drawn
    if SHOTS:
        page.locator(".outline-check").first.screenshot(path=str(Path(SHOTS) / "outline-erdiagram.png"))
        page.locator(".outline-check").nth(1).screenshot(path=str(Path(SHOTS) / "outline-flowchart.png"))
        page.locator(".outline-check").nth(2).screenshot(path=str(Path(SHOTS) / "store-erdiagram.png"))
        page.locator(".outline-check").nth(3).screenshot(path=str(Path(SHOTS) / "store-flowchart.png"))
    context.close()

    # The Workbench: its project.outline command (the project menu's Export outline) does the same.
    (folder / "ARCHITECTURE.md").unlink()
    work = browser.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    wb = work.new_page()
    wb.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(wb.locator(".wb-codex")).to_be_visible(timeout=20000)  # its explorer (no top bar, 2026-11-21)
    for _ in range(50):  # the window's socket joins a moment after its page draws
        try:
            call(server, "POST", "/workbench/window", {"command": "project.outline", "args": {}}, agent=True)
            break
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            wb.wait_for_timeout(200)
    expect(wb.locator(".toast", has_text="ARCHITECTURE.md written")).to_be_visible()
    assert (folder / "ARCHITECTURE.md").read_text(encoding="utf-8") == written
    work.close()
    call(server, "POST", "/project/close", {"discard": True})
