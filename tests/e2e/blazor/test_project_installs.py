"""A project opens and everything it needs is installed at once, with the setup bar on the page (the owner,
2026-11-23): a made-up project whose data.ipynb imports a made-up library and whose requirements.txt names
another, installed by the stand-in installer (tests/libraries_standin.py: nothing downloaded), a second apart
each so the bar is seen moving. The bar shows the count, its details list both with why, it ends done, and
requirements.txt holds both. Made-up data only."""

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

from tests import libraries_standin
from tests.e2e.blazor.conftest import FIRST_LOAD_MS, call

SCREENSHOT = os.environ.get("SAB_SETUP_SCREENSHOT")  # where the bar's picture goes, when asked for


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A server of its own that makes and fills a project's Python by itself (the stand-in installer)."""
    tmp = tmp_path_factory.mktemp("installs")
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(tmp / "workbench"),
        "SWISSARMYBENCH_NO_BROWSER": "1",
        "SWISSARMYBENCH_SYSTEM_DIALOGS": "off",
        "SWISSARMYBENCH_PROJECT_VENV": "on",
        "SWISSARMYBENCH_LIBRARIES_STANDIN": str(Path(libraries_standin.__file__)),
        "SWISSARMYBENCH_LIBRARIES_STANDIN_DELAY": "1.2",
        "SWISSARMYBENCH_FRONTEND": "",
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    info: dict[str, Any] | None = None
    for _ in range(150):
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


def made_up_project(folder: Path) -> Path:
    folder.mkdir(parents=True)
    cell = {"cell_type": "code", "source": "import tabulate_made_up\n", "metadata": {}, "outputs": []}
    notebook = {"cells": [cell], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (folder / "data.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    (folder / "requirements.txt").write_text("rich_made_up\n", encoding="utf-8")
    machinery = {"ipykernel": "6.29.5", "openpyxl": "3.1.5", "xlrd": "2.0.1", "streamlit": "1.50.0"}
    libraries_standin.make_venv(folder, machinery)  # its own Python, made before (without the two)
    return folder


def test_opening_a_project_installs_what_it_needs_with_the_bar(
    browser: Browser, server: dict[str, Any]
) -> None:
    folder = made_up_project(Path(server["tmp"]) / "work" / "Sales Recon")
    page = browser.new_page(viewport={"width": 1360, "height": 860}, device_scale_factor=2)
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/#token={server['token']}")
    page.wait_for_selector(".nav-rail", timeout=FIRST_LOAD_MS)
    call(server, "POST", "/project/open", {"path": str(folder), "make": True})
    bar = page.locator(".setup-bar")
    expect(bar.locator(".setup-bar-words")).to_contain_text("Setting up Sales Recon: installing")
    expect(bar.locator(".setup-bar-words")).to_contain_text("of 2")
    expect(bar.locator("fluent-progress")).to_be_visible()
    bar.get_by_role("button", name="Show details").click()
    rows = bar.locator(".setup-bar-package")
    expect(rows).to_have_count(2)
    expect(rows.filter(has_text="rich_made_up")).to_contain_text("requirements.txt")
    expect(rows.filter(has_text="tabulate_made_up")).to_contain_text("data.ipynb")
    if SCREENSHOT:
        page.screenshot(path=SCREENSHOT)
    expect(bar.locator(".setup-bar-words")).to_have_text("Installed 2 libraries · added to requirements.txt")
    expect(rows.filter(has_text="tabulate_made_up")).to_contain_text("Installed")
    requirements = (folder / "requirements.txt").read_text(encoding="utf-8").split()
    assert requirements == ["rich_made_up", "tabulate_made_up"]
    # It goes by itself a few seconds after.
    expect(bar).to_have_count(0, timeout=12_000)
    assert call(server, "GET", "/project/installs")["state"] == "done"
    page.close()
