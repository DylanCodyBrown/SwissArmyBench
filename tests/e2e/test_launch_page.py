"""Launch, build history and the Performance Analyzer in the Workbench window (the owner, 2026-11-19), with a
Python that has Streamlit: Launch opens the app in a window of its own and a build appears in the project's
builds/; the analyzer, opened, attached to it, records a widget's change as a rerun with its trigger, a slow
block and the web socket's dataframe message, and says the big uncached table; a block changed and launched
again, Compare shows the change. Screenshots when SWISSARMYBENCH_CANVAS_SHOTS names a folder. Made-up data."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_canvas_pane_page import open_window, shot, until
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

FILTER = '# Region filter\nregion = st.selectbox("Region", ["East", "West", "North"], key="region_pick")'
SLOW = '# Totals\nimport time\n\ntime.sleep(0.12)\nst.write("totals")'
TABLE = '# Orders\nst.dataframe(big[big["region"] == region])'


@pytest.fixture
def big(server: dict[str, Any]) -> Iterator[None]:  # noqa: F811
    close_tables(server)
    rows = 150_000
    made_up = np.random.default_rng(7)
    frame = pd.DataFrame(
        {
            "order_id": np.arange(rows),
            "region": np.array(["East", "West", "North"])[np.arange(rows) % 3],
            "amount": made_up.random(rows) * 1000,
            "cost": made_up.random(rows) * 900,
            "note": [f"made-up order {i}" for i in range(rows)],
        }
    )
    push_client.push(frame, name="big", new_grid=True)
    yield
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}/launch")
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def launch_app(server: dict[str, Any], folder: Path, slow: str = SLOW) -> Path:  # noqa: F811
    folder.mkdir(parents=True, exist_ok=True)
    notebook = folder / "app.ipynb"
    cells = [
        {"kind": "code", "source": FILTER, "name": "Region filter"},
        {"kind": "code", "source": slow, "name": "Totals"},
        {"kind": "code", "source": TABLE, "name": "Orders"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    call(server, "POST", "/workbench/environment", {"path": str(notebook), "python": STREAMLIT_PYTHON})
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 4, "h": None},
        {"document": str(notebook), "cell": 2, "row": 1, "column": 5, "w": 8, "h": None},
        {"document": str(notebook), "cell": 3, "row": 2, "column": 1, "w": 12, "h": None},
    ]
    app = folder / "orders.stapp.json"
    call(
        server, "POST", "/workbench/save", {"path": str(app), "pages": [{"name": "Orders", "blocks": blocks}]}
    )
    return app


def _app_id(server: dict[str, Any]) -> str:  # noqa: F811
    apps = call(server, "GET", "/streamlit/apps")["apps"]
    return str([a["app"] for a in apps if a["kind"] == "canvas"][-1])


@needs_streamlit
def test_launch_a_build_the_analyzer_and_compare(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    big: None,
    tmp_path: Path,
) -> None:
    project = tmp_path / "shop"
    app = launch_app(server, project)
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    expect(board.locator(".cv-block")).to_have_count(3, timeout=20000)
    # Launch: the app in a window of its own, titled with its build; a build in the project's builds/.
    with page.expect_popup(timeout=120000) as opened:
        page.locator(".cv-launch-go").click()
    launched = opened.value
    expect(launched).to_have_title("orders · build 1", timeout=120000)
    expect(launched.get_by_text("totals")).to_be_visible(timeout=60000)
    build = project / "builds" / "orders" / "1"
    assert json.loads((build / "build.json").read_text(encoding="utf-8"))["result"] == "started"
    shot(page, "launch-canvas")
    # The analyzer: its own window, attached while it is open.
    with page.expect_popup(timeout=30000) as analyzer_opened:
        page.locator(".cv-analyzer").click()
    analyzer = analyzer_opened.value
    expect(analyzer.locator(".pf-state")).to_have_text("Recording", timeout=30000)
    app_id = _app_id(server)
    # A widget changes in the launched app: a rerun, its trigger, each block's time, the socket's dataframe.
    # Each a region not shown before: its table is sent whole (a region shown before, the browser keeps).
    for region in ("West", "North", "East"):
        launched.get_by_role("combobox").first.click()
        launched.get_by_role("option", name=region).click()
        launched.wait_for_timeout(1500)

    def picks() -> int:
        session = call(server, "GET", f"/streamlit/apps/{app_id}/perf")
        return len([r for r in session["reruns"] if r["trigger"] == "region_pick"])

    until(lambda: picks() >= 1, True, 60)
    session = call(server, "GET", f"/streamlit/apps/{app_id}/perf")
    rerun = next(r for r in reversed(session["reruns"]) if r["trigger"] == "region_pick")
    times = {b["title"]: b["ms"] for b in rerun["blocks"]}
    assert times["Totals"] >= 100  # the slow block
    assert rerun["socket"]["elements"]["dataframe"]["size"] > 1_000_000
    rules = {h["rule"]: h["words"] for h in session["hints"]}
    assert rules["big_table"].startswith("Orders: ") and "each rerun: cache it" in rules["big_table"]
    assert rules["needless_rerun"].startswith("Totals reruns each time region_pick changes")
    expect(analyzer.locator(".pf-rerun[data-trigger=region_pick]").first).to_be_visible(timeout=15000)
    shot(analyzer, "analyzer-timeline")
    analyzer.get_by_role("button", name="Web socket").click()
    expect(analyzer.locator(".pf-socket-view")).to_contain_text("dataframe")
    shot(analyzer, "analyzer-socket")
    analyzer.get_by_role("button", name="Hints (2)").click()
    expect(analyzer.locator(".pf-hint")).to_have_count(2)
    shot(analyzer, "analyzer-hints")
    analyzer.close()
    until(lambda: call(server, "GET", f"/streamlit/apps/{app_id}/perf")["recording"], False, 15)
    # A block changes; Launch again (Ctrl+F5); Compare in the Builds dialog shows the change.
    call(
        server,
        "POST",
        "/workbench/save",
        {
            "path": str(project / "app.ipynb"),
            "cells": [
                {"kind": "code", "source": FILTER, "name": "Region filter"},
                {"kind": "code", "source": SLOW.replace("0.12", "0.01"), "name": "Totals"},
                {"kind": "code", "source": TABLE, "name": "Orders"},
            ],
        },
    )
    # Ctrl+F5: the same window shows build 2 (a launch replaces the running one).
    board.click(position={"x": 20, "y": 600})
    page.keyboard.press("Control+F5")
    expect(launched).to_have_title("orders · build 2", timeout=120000)
    until(lambda: (project / "builds" / "orders" / "2" / "build.json").is_file(), True, 60)
    page.locator(".cv-builds").click()
    dialog = page.get_by_role("dialog", name="Builds")
    expect(dialog.locator(".bd-row")).to_have_count(2, timeout=15000)
    expect(dialog.locator('.bd-row[data-build="2"] .bd-changed')).to_contain_text(
        "Totals (app.ipynb @cell2) changed."
    )
    dialog.get_by_role("checkbox", name="Build 1").check()
    dialog.get_by_role("checkbox", name="Build 2").check()
    dialog.get_by_role("button", name="Compare").click()
    expect(dialog.locator(".bd-file.bd-changed").first).to_be_visible(timeout=15000)
    expect(dialog.locator(".bd-diff .monaco-diff-editor")).to_be_visible(timeout=30000)
    # The changed page first, its old line in the diff; the new side holds the new one.
    expect(dialog.locator(".bd-file.selected")).to_have_attribute("data-file", "app_pages/orders.py")
    expect(dialog.locator(".bd-diff")).to_contain_text("time.sleep(0.12)", timeout=15000)
    compared = call(server, "GET", f"/streamlit/apps/{app_id}/builds/compare?a=1&b=2")["files"]
    page_diff = next(f for f in compared if f["file"] == "app_pages/orders.py")
    assert page_diff["status"] == "changed" and "time.sleep(0.01)" in page_diff["after"]
    assert not any(f["file"] == "app.py" and f["status"] == "changed" for f in compared)
    shot(page, "builds-compare")
    page.context.close()
