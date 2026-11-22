# ruff: noqa: F811
"""What api_adapter learns of an API, on the APIs page, (Plans/api-adapter.plan.md): a made-up
specification uploaded (tests/api_standins.py) in a real browser, Discover answered with Allow, each
endpoint's learned shape and what it maps to, Build a widget on a canvas, and a drift (a field the API no
longer answers) said on its endpoint and marked on its field. Every row is made up."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.api_standins import Service
from tests.e2e.test_ui import browser, call, demo_frame, grid_of, open_grid, server  # noqa: F401

SHOTS = Path(os.environ.get("SAB_SHOTS") or tempfile.mkdtemp(prefix="sab-api-learned-shots-"))


@pytest.fixture(scope="module")
def service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.locator(".area-page").screenshot(path=str(SHOTS / name))


def test_discover_learn_build_and_a_drift(
    browser: Browser, server: dict[str, Any], service: Service, tmp_path: Path
) -> None:
    from swissarmybench.client import push_client

    folder = tmp_path / "shop"
    call(server, "POST", "/project/new", {"path": str(folder), "type": "streamlit"})
    if not call(server, "GET", "/streamlit/canvases")["canvases"]:
        call(server, "POST", "/streamlit/canvases", {"name": "app"})
    spec = tmp_path / "shop.openapi.json"
    spec.write_text(
        json.dumps(service.openapi() | {"servers": [{"url": service.url + "/v1"}]}), encoding="utf-8"
    )
    call(server, "POST", "/apis", {"spec_path": str(spec), "name": "Shop", "auth": {"type": "none"}})
    url = push_client.push(demo_frame(5), name="jan", new_grid=True)
    page = open_grid(browser, url, width=1500, height=1300, device_scale_factor=2)
    try:
        apis = page.locator(".area-page[data-page='apis']")
        page.locator(".nav-rail [data-area='apis']").click()
        apis.locator(".api-card[data-api='Shop'] .api-card-open").click()
        learned = apis.locator(".api-learned[data-action='list_orders']")
        expect(learned.locator(".api-learned-kind.declared")).to_have_text("records")  # as declared, at first
        before = len(service.seen)
        apis.get_by_role("button", name="Discover").click()
        expect(page.locator(".approval")).to_be_visible(timeout=15000)
        expect(page.locator(".approval pre")).to_contain_text("read-only calls")
        page.get_by_role("button", name="Allow").click()
        expect(learned.locator(".api-learned-kind.learned")).to_have_text("records", timeout=60000)
        assert {s["method"] for s in service.seen[before:]} == {"GET"}  # nothing that writes
        expect(learned).to_contain_text("maps to a table or a grid")
        expect(learned.locator("[data-field='amount']")).to_contain_text("number")
        expect(apis.locator(".api-op[data-operation='get_order'] .api-op-kind")).to_have_text("record")
        shot(page, "api-learned.png")
        # Build: a widget on the project's canvas page (its records as a table: [Shop].list_orders).
        learned.get_by_role("button", name="Widget on a canvas").click()
        expect(page.locator(".toast", has_text="Put data_table on")).to_be_visible()
        canvas = call(server, "GET", "/streamlit/canvases")["canvases"][0]["path"]
        made = json.dumps(call(server, "POST", "/streamlit/canvases", {"path": canvas})["model"])
        assert '"data_table"' in made and "[Shop].list_orders" in made
        # Build: a notebook cell, put into the project's data.ipynb and opened on the Notebooks page there.
        from swissarmybench.domain import notebooks

        data = folder / "data.ipynb"
        cells_before = len(notebooks.read_notebook(data.read_text(encoding="utf-8")))
        with page.context.expect_page(timeout=30000) as opened:
            learned.get_by_role("button", name="Notebook cell").click()
        notebook_page = opened.value
        cells = notebooks.read_notebook(data.read_text(encoding="utf-8"))
        assert len(cells) == cells_before + 1 and 'sab.run("Shop", "list_orders"' in cells[-1].source
        expect(notebook_page.locator(".wb-cell", has_text='sab.run("Shop", "list_orders"')).to_be_visible(
            timeout=60000
        )
        notebook_page.screenshot(path=str(SHOTS / "api-built-cell.png"))
        notebook_page.close()
        # Build: a script function, into the script the user picks (a new one here), opened on Scripts.
        with page.context.expect_page(timeout=30000) as opened:
            learned.get_by_role("button", name="Script function").click()
            picker = page.get_by_role("dialog", name="Put the function in a script")
            expect(picker.get_by_label("New script")).to_have_value("api_functions.py")
            picker.screenshot(path=str(SHOTS / "api-built-function-pick.png"))
            picker.get_by_role("button", name="Put it there").click()
        script_page = opened.value
        script = (folder / "api_functions.py").read_text(encoding="utf-8")
        assert "def list_orders(" in script and 'sab.run("Shop", "list_orders"' in script
        expect(script_page.locator(".monaco-editor").first).to_be_visible(timeout=60000)
        script_page.close()
        # A drift: the kept shape had a field the API no longer answers. Run says it and marks the field.
        library = Path(call(server, "GET", "/library")["folder"])
        kept = library / "apis" / "Shop" / "shapes" / "list_orders.json"
        shape = json.loads(kept.read_text(encoding="utf-8"))
        assert "shipped" not in kept.read_text(encoding="utf-8")  # types only, never a value
        shape["returned"]["fields"]["region"] = {"type": "text", "format": "", "empty": False}
        shape["returned"]["fingerprint"] = "older"
        kept.write_text(json.dumps(shape), encoding="utf-8")
        learned.get_by_role("button", name="Run").click()
        expect(learned.locator(".error-note")).to_contain_text("1 field missing since", timeout=30000)
        expect(learned.locator("[data-field='region'] .api-learned-mark")).to_have_text("missing")
        expect(apis.locator(".api-op[data-operation='list_orders'].drifted")).to_have_count(
            0
        )  # the list's mark on a redraw
        shot(page, "api-drift.png")
    finally:
        call(server, "DELETE", f"/grids/{grid_of(url)}")
        page.context.close()
