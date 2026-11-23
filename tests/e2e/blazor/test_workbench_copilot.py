"""The Blazor Notebooks and Scripts pages' ghost text from the provider the mode declares, here GitHub
Copilot's routes over the made-up Copilot Language Server (tests/copilot_standin.py): the ghost text in a
notebook cell and a script, Tab taking it, and the status bar's "Completions: GitHub Copilot · on" turning
it off."""

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

from tests.e2e.blazor.conftest import open_page

ROOT = Path(__file__).resolve().parents[3]
STANDIN = ROOT / "tests" / "copilot_standin.py"
GHOST = ".ghost-text-decoration, .ghost-text, .ghost-text-decoration-preview"


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server with the Copilot extension on, signed in to the made-up Copilot."""
    tmp = tmp_path_factory.mktemp("blazor-copilot")
    state = tmp / "state"
    state.mkdir()
    (tmp / "account.json").write_text(json.dumps({"user": "made-up-octocat"}))
    (state / "copilot.json").write_text(json.dumps({"on": True, "login": "made-up-octocat"}))
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(state),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_EXTENSIONS": "copilot",
        "SWISSARMYBENCH_COPILOT_STANDIN": str(STANDIN),
        "COPILOT_STANDIN_LOG": str(tmp / "standin.log"),
        "COPILOT_STANDIN_STATE": str(tmp / "account.json"),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "extensions" / "copilot" / "src"), str(ROOT / "src")]),
        "SWISSARMYBENCH_NO_BROWSER": "1",
        "SWISSARMYBENCH_SYSTEM_DIALOGS": "off",
        "SWISSARMYBENCH_PROJECT_VENV": "off",
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    info: dict[str, Any] | None = None
    for _ in range(200):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    if info is None:
        process.kill()
        raise AssertionError("the server did not start")
    yield info | {"tmp": tmp}
    process.terminate()
    process.wait(timeout=20)


def test_ghost_text_in_a_cell_and_a_script_and_the_switch(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "notebooks?new=1")
    page.click(".wb-gcontrols button[aria-label='Add cell']")
    page.click(".context-menu [role=menuitem]:has-text('Python')")
    cell = page.locator(".wb-cell").first
    cell.locator(".monaco-editor").click()
    page.keyboard.type("orders = 1")
    page.keyboard.press("Enter")
    expect(cell.locator(GHOST).first).to_be_visible(timeout=15_000)
    item = page.locator(".wb-inline-status")
    expect(item).to_have_text("Completions: GitHub Copilot · on")
    page.keyboard.press("Tab")
    expect(cell.locator(".view-lines")).to_contain_text("print('made-up suggestion')")

    # The status bar's item turns it off (its word follows the provider's answer).
    item.click()
    expect(item).to_have_attribute("data-on", "false")
    item.click()
    expect(item).to_have_attribute("data-on", "true")
    page.close()

    page = open_page(browser, server, "scripts?new=1")
    page.click(".wb-script-editor .monaco-editor .view-lines")
    page.keyboard.type("total = 1")
    page.keyboard.press("Enter")
    expect(page.locator(".wb-script-editor").locator(GHOST).first).to_be_visible(timeout=15_000)
    page.close()
