# ruff: noqa: F811
"""The Power BI project in a real browser: a made-up .pbix imported (pbixray stood in for), the Power BI page
drawn
from its data (the target, To finish setting up, Read Power BI from, App registration, the measures, the big
buttons), the first-open pop-up once, the gates (a closed area's rail item hidden, its address saying so in
one
line with Open every feature), and Edit in Power BI Desktop's dry run (a running Desktop stood in for).
Made-up
data only.

With SWISSARMYBENCH_SHOTS set to a folder, the test also saves screenshots there (2x, light and dark)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.renamed import env
from tests import powerbi_pbix_fake as fake
from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = env("SWISSARMYBENCH_SHOTS") or None
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("powerbi_project")
    source = str(ROOT / "extensions" / "powerbi" / "src")
    env_ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_EXTENSIONS": "streamlit,powerbi",
        "SWISSARMYBENCH_PBIX_STANDIN": "tests.powerbi_pbix_fake",
        "SWISSARMYBENCH_PBI_DESKTOP_STANDIN": "tests.powerbi_live_fake",
        "PYTHONPATH": os.pathsep.join([source, str(ROOT), os.environ.get("PYTHONPATH", "")]).strip(
            os.pathsep
        ),
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


def test_the_power_bi_project_page_gates_and_edit(browser: Browser, server: dict[str, Any]) -> None:
    tmp = Path(server["tmp"])
    pbix = fake.fake_pbix(tmp)
    body = {"path": str(pbix), "folder": str(tmp / "projects"), "dataset": {"none": True}}
    done = call(server, "POST", "/powerbi/import", body)
    assert done["type"] == "powerbi"
    base = f"http://127.0.0.1:{server['port']}"
    for scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1400, "height": 900}, device_scale_factor=2, color_scheme=scheme
        )
        page = context.new_page()
        page.goto(f"{base}/workspace?open=powerbi#token={server['token']}")
        if scheme == "light":  # the first-open pop-up, once per project
            first = page.locator("dialog.gates-first")
            expect(first).to_contain_text("This Power BI project keeps some features closed", timeout=20000)
            expect(first).to_contain_text("Analyze")
            if SHOTS:
                page.screenshot(path=str(Path(SHOTS) / "powerbi-first-open.png"))
            first.get_by_role("button", name="Got it").click()
            expect(first).to_have_count(0)
        panel = page.locator('.area-page[data-page="powerbi"] .extension-panel')
        expect(panel).to_contain_text("Sales model.pbix", timeout=20000)
        expect(panel).to_contain_text("Total Sales (KPIs) = SUM(Sales[Amount])")
        if scheme == "light":
            expect(panel.locator('[data-row="registration"]')).to_be_visible()
        expect(panel.get_by_label("Read Power BI from")).to_be_visible()
        expect(panel.get_by_role("button", name="Edit in Power BI Desktop")).to_be_visible()
        # The gates: Analyze's rail item hidden; Power BI's shown.
        expect(page.locator('.nav-rail-item[data-area="powerbi"]')).to_be_visible()
        expect(page.locator('.nav-rail-item[data-area="analyze"]')).to_be_hidden()
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"powerbi-page-{scheme}.png"))
        if scheme == "light":
            # A To finish row's fix clears it: the app registration is chosen as None (sign in as you).
            panel.get_by_label("App registration").select_option("none")
            expect(panel.locator('[data-row="registration"]')).to_have_count(0, timeout=15000)
            # Edit in Power BI Desktop's dry run (the agent's door; the page's button points to it).
            planned = call(server, "POST", "/powerbi/live/plan", {})
            assert [c["words"] for c in planned["changes"]][-1] == "Add the measure Sales[Total Sales]"
            # An address naming a closed area: one line, Open every feature.
            page.goto(f"{base}/workspace?view=analyze#token={server['token']}")
            line = page.locator(".gate-line")
            expect(line).to_contain_text("This Power BI project keeps Analyze closed.", timeout=20000)
            if SHOTS:
                page.screenshot(path=str(Path(SHOTS) / "powerbi-gate-line.png"))
            line.get_by_role("button", name="Open every feature").click()
            expect(line).to_have_count(0)
            expect(page.locator('.nav-rail-item[data-area="analyze"]')).to_be_visible()
            call(server, "POST", "/app/gates", {"every": False})
        context.close()
