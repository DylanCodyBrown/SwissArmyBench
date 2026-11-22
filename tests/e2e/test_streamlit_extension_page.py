# ruff: noqa: F811
"""The Streamlit extension in a real browser: with it (as every install has it) the rail's Apps area and the
Extensions card saying Preinstalled with Remove; the BI base without it: no Apps area, no New Streamlit app in
the Workbench, the card Available with Install. Made-up data only.

With SWISSARMYBENCH_SHOTS set to a folder, the screenshots are saved there (2x)."""

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
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None


def start(tmp: Path, extensions: str) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    env_ = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_EXTENSIONS": extensions,
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env_)
    for _ in range(150):
        try:
            return process, json.loads((tmp / "server.json").read_text())
        except (OSError, ValueError):
            time.sleep(0.1)
    process.kill()
    raise AssertionError("server did not start")


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    process, info = start(tmp_path_factory.mktemp("base"), "-streamlit")
    yield info
    process.terminate()
    process.wait(timeout=20)


@pytest.fixture(scope="module")
def full(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    process, info = start(tmp_path_factory.mktemp("full"), "streamlit")
    yield info
    process.terminate()
    process.wait(timeout=20)


def open_page(browser: Browser, info: dict[str, Any], path: str) -> Page:
    page = browser.new_context(
        viewport={"width": 1400, "height": 820}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{info['port']}{path}#token={info['token']}")
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / name))


def test_with_it_apps_are_on_the_rail_and_the_card_says_preinstalled(
    browser: Browser, full: dict[str, Any]
) -> None:
    page = open_page(browser, full, "/workspace?open=extensions")
    card = page.locator(".extension-card[data-extension='streamlit']")
    expect(card.locator(".extension-status")).to_have_text("Preinstalled", timeout=15000)
    expect(card.get_by_role("button", name="Remove")).to_be_visible()
    expect(page.locator(".nav-rail [data-area='canvas']")).to_be_visible()
    shot(page, "streamlit-preinstalled.png")
    page.context.close()


def test_the_bi_base_has_no_apps_and_offers_the_extension(browser: Browser, base: dict[str, Any]) -> None:
    page = open_page(browser, base, "/workspace?open=extensions")
    card = page.locator(".extension-card[data-extension='streamlit']")
    expect(card.locator(".extension-status")).to_have_text("Available", timeout=15000)
    expect(card.get_by_role("button", name="Install")).to_be_visible()
    expect(page.locator(".nav-rail [data-area='notebooks']")).to_be_visible()
    expect(page.locator(".nav-rail [data-area='canvas']")).to_be_hidden()
    shot(page, "streamlit-off-extensions.png")
    page.context.close()
    # The Workbench: notebooks and scripts, no Apps.
    work = open_page(browser, base, "/workbench?kind=notebook&view=list")
    expect(work.locator(".nav-rail [data-area='scripts']")).to_be_visible(timeout=15000)
    expect(work.locator(".nav-rail [data-area='canvas']")).to_be_hidden()
    shot(work, "streamlit-off-workbench.png")
    work.context.close()


def test_a_streamlit_projects_code_pages_open_without_asking_for_its_canvas(
    browser: Browser, full: dict[str, Any], tmp_path: Path
) -> None:
    """The sweep, 2026-11-22: opening a Streamlit project's Notebooks (or Scripts) page asked the Workbench
    to open the project's <app>.canvas.json, which it refused in an error box naming the old .stapp.json.
    The canvas is the Canvas page's: the code pages leave it, and opening it from one goes there."""
    from tests.e2e.test_ui import call

    made = call(full, "POST", "/project/new", {"path": str(tmp_path / "shop"), "type": "streamlit"})
    canvas = next(f for f in made["files"] if f.endswith(".canvas.json"))
    try:
        for path, tab in (("/notebooks", "data.ipynb"), ("/scripts", "Local sandbox API")):
            page = open_page(browser, full, path)
            refused: list[str] = []

            def note(response: Any, seen: list[str] = refused) -> None:
                if response.status >= 400:
                    seen.append(response.url)

            page.on("response", note)
            if tab == "data.ipynb":
                expect(page.locator(".wb-tab", has_text=tab)).to_be_visible(timeout=20000)
            else:
                expect(page.locator(".wb-codex-body")).to_contain_text(tab, timeout=20000)
            page.wait_for_load_state("networkidle")
            expect(page.locator(".error-note")).to_have_count(0)
            assert not [u for u in refused if "/workbench/open" in u], refused
            page.context.close()
        # Asked for by its path (the agent's workbench_open, a link): one sentence that says where it opens.
        asked = call_refused(full, "/workbench/open", {"path": canvas})
        assert "Canvas page" in asked and ".stapp.json" not in asked
    finally:
        call(full, "POST", "/project/close", {"discard": True})


def call_refused(info: dict[str, Any], path: str, body: Any) -> str:
    """A POST the server refuses: its one sentence."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=60)  # noqa: S310
    except urllib.error.HTTPError as error:
        return str(json.loads(error.read())["error"])
    raise AssertionError("it was not refused")
