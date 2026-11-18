# ruff: noqa: F811
"""Ghost text in the Workbench's editors from the provider the backend declares, in a real browser, with the
GitHub Copilot extension on and GitHub's Copilot Language Server stood in for (tests/copilot_standin.py): a
notebook cell's and a script's ghost text, Tab accepts, Esc lets it go, the status bar's item, the Extensions
card's panel (the device flow's code), Settings' panel and the project's Private switch. Made-up code only.

With SWISSARMYBENCH_COPILOT_SHOTS set to a folder, the tests also save screenshots there (2x)."""

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

from tests.e2e.test_ui import browser, call  # noqa: F401
from tests.e2e.test_workbench_page import add_cell, start

SHOTS = os.environ.get("SWISSARMYBENCH_COPILOT_SHOTS")
ROOT = Path(__file__).resolve().parents[2]
STANDIN = ROOT / "tests" / "copilot_standin.py"


def launch(tmp: Path, signed_in: bool) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    state = tmp / "state"
    state.mkdir(parents=True, exist_ok=True)
    if signed_in:
        (tmp / "account.json").write_text(json.dumps({"user": "made-up-octocat"}))
        (state / "copilot.json").write_text(json.dumps({"on": True, "login": "made-up-octocat"}))
    env = os.environ | {
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(state),
        "SWISSARMYBENCH_PROJECTS_DIR": str(tmp / "projects"),
        "SWISSARMYBENCH_EXTENSIONS": "copilot",
        "SWISSARMYBENCH_COPILOT_STANDIN": str(STANDIN),
        "COPILOT_STANDIN_LOG": str(tmp / "standin.log"),
        "COPILOT_STANDIN_STATE": str(tmp / "account.json"),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "extensions" / "copilot" / "src"), str(ROOT / "src")]),
        "SWISSARMYBENCH_NO_BROWSER": "1",
    }
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(200):
        try:
            return process, json.loads((tmp / "server.json").read_text()) | {"tmp": tmp}
        except (OSError, ValueError):
            time.sleep(0.1)
    process.kill()
    raise AssertionError("server did not start")


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    process, info = launch(tmp_path_factory.mktemp("copilot-e2e"), signed_in=True)
    yield info
    process.terminate()
    process.wait(timeout=20)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def page_at(browser: Browser, info: dict[str, Any], path: str) -> Page:
    page = browser.new_context(
        viewport={"width": 1440, "height": 900}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{info['port']}{path}#token={info['token']}")
    return page


def workbench(browser: Browser, info: dict[str, Any]) -> Page:
    page = page_at(browser, info, "/workbench")
    expect(page.locator(".wb-welcome")).to_be_visible(timeout=20000)
    return page


def sent(info: dict[str, Any]) -> list[str]:
    log = info["tmp"] / "standin.log"
    return (
        [json.loads(line).get("method", "") for line in log.read_text().splitlines()] if log.exists() else []
    )


GHOST = ".ghost-text-decoration, .ghost-text, .ghost-text-decoration-preview"


def test_ghost_text_in_a_notebook_cell_tab_takes_it(browser: Browser, server: dict[str, Any]) -> None:
    page = workbench(browser, server)
    start(page)
    cell = page.locator(".wb-cell").first
    editor = cell.locator(".monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    # A new line: no member list in the way (the provider's made-up suggestion for an empty line).
    page.keyboard.type("orders = 1")
    page.keyboard.press("Enter")
    ghost = cell.locator(GHOST)
    expect(ghost.first).to_be_visible(timeout=15000)
    expect(cell.locator(".view-lines")).to_contain_text("print('made-up suggestion')")
    # The status bar's item draws the provider's name the backend gave.
    item = page.locator(".inline-status")
    expect(item).to_have_text("Completions: GitHub Copilot · on")
    shot(page, "notebook-ghost-text")
    page.keyboard.press("Tab")
    expect(cell.locator(".view-lines")).to_contain_text("print('made-up suggestion')", timeout=5000)
    expect(ghost).to_have_count(0)
    # The notebook went as a notebook: its code cells, the cell being edited asked in.
    methods = sent(server)
    assert "notebookDocument/didOpen" in methods and "textDocument/inlineCompletion" in methods
    for _ in range(50):  # the accept is told back
        if "workspace/executeCommand" in sent(server):
            break
        time.sleep(0.1)
    assert "workspace/executeCommand" in sent(server)
    # A second cell with the first as its context: SQL too.
    add_cell(page, "SQL")
    second = page.locator(".wb-cell").nth(1)
    expect(second.locator(".monaco-editor")).to_be_visible(timeout=20000)
    second.locator(".monaco-editor").click()
    page.keyboard.type("SELECT region,")
    expect(second.locator(GHOST).first).to_be_visible(timeout=15000)
    expect(second.locator(".view-lines")).to_contain_text("sum(amount) AS total")
    # Esc lets it go and keeps the cell in edit mode (a second Esc is the cell's own).
    page.keyboard.press("Escape")
    expect(second.locator(GHOST)).to_have_count(0)
    expect(second.locator(".view-lines")).to_contain_text("SELECT region,")
    assert "sum(amount)" not in (second.locator(".view-lines").text_content() or "")


def test_ghost_text_in_a_script_and_the_off_switch(browser: Browser, server: dict[str, Any]) -> None:
    page = workbench(browser, server)
    start(page, "New script")
    editor = page.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    editor.click()
    page.keyboard.insert_text("def total_by_region(orders):")
    page.keyboard.press("End")
    page.keyboard.type(" ")
    page.keyboard.press("Backspace")
    host = page.locator(".wb-script-editor")
    expect(host.locator(GHOST).first).to_be_visible(timeout=15000)
    expect(host.locator(".monaco-editor")).to_contain_text("groupby")  # a second line: Monaco's own zone
    shot(page, "script-ghost-text")
    page.keyboard.press("Tab")
    expect(host.locator(".view-lines")).to_contain_text("return orders.groupby('region')['amount'].sum()")
    # The status bar's item turns it off: nothing more is asked.
    item = page.locator(".inline-status")
    item.click()
    expect(item).to_have_text("Completions: GitHub Copilot · off", timeout=10000)
    before = sent(server).count("textDocument/inlineCompletion")
    editor.click()
    page.keyboard.press("Control+End")
    page.keyboard.press("Enter")
    page.keyboard.type("import pan")
    page.wait_for_timeout(1500)
    expect(host.locator(".view-lines")).to_contain_text("import pan")
    expect(host.locator(GHOST)).to_have_count(0)
    assert sent(server).count("textDocument/inlineCompletion") == before
    item.click()
    expect(item).to_have_text("Completions: GitHub Copilot · on", timeout=10000)
    assert call(server, "GET", "/copilot")["on"] is True


def test_a_private_project_sends_nothing(browser: Browser, server: dict[str, Any]) -> None:
    folder = server["tmp"] / "projects" / "ledger"
    call(server, "POST", "/project/new", {"path": str(folder)})
    home = page_at(browser, server, "/workspace")
    switch = home.get_by_role("switch", name="Private")
    expect(switch).to_be_visible(timeout=20000)
    expect(switch).not_to_be_checked()
    switch.click()
    expect(switch).to_be_checked(timeout=10000)
    for _ in range(100):
        if json.loads((folder / ".sab" / "project.json").read_text()).get("private") is True:
            break
        time.sleep(0.1)
    assert json.loads((folder / ".sab" / "project.json").read_text())["private"] is True
    shot(home, "private-switch")
    page = workbench(browser, server)
    item = page.locator(".inline-status")
    expect(item).to_have_text("Completions: GitHub Copilot · private", timeout=10000)
    start(page, "New script")
    editor = page.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible(timeout=20000)
    before = len(sent(server))
    editor.click()
    page.keyboard.type("import pan")
    page.wait_for_timeout(1500)
    expect(page.locator(".wb-script-editor .view-lines")).to_contain_text("import pan")
    expect(page.locator(".wb-script-editor").locator(GHOST)).to_have_count(0)
    after = sent(server)[before:]
    assert "textDocument/didOpen" not in after and "textDocument/inlineCompletion" not in after
    call(server, "POST", "/project/private", {"on": False})
    call(server, "POST", "/project/close", {"discard": True})


def test_the_extensions_card_signs_in_with_the_device_flow(browser: Browser, tmp_path: Path) -> None:
    process, info = launch(tmp_path, signed_in=False)
    try:
        page = page_at(browser, info, "/workspace?open=extensions")
        # GitHub's device page is opened, never reached: a test sends nothing out.
        page.context.route("https://github.com/**", lambda route: route.fulfill(body="made-up device page"))
        card = page.locator(".extension-card[data-extension='copilot']")
        expect(card).to_be_visible(timeout=20000)
        expect(card.locator(".extension-panel")).to_contain_text("Not signed in", timeout=20000)
        card.get_by_role("button", name="Sign in to GitHub").click()
        expect(card.locator(".extension-panel-usercode")).to_have_text("MADE-UP1", timeout=15000)
        shot(page, "extensions-card-code")
        with page.context.expect_page() as opened:
            card.get_by_role("button", name="Open github.com/login/device").click()
        assert opened.value.url.startswith("https://github.com/login/device")
        opened.value.close()
        expect(card.locator(".extension-panel")).to_contain_text(
            "Signed in as made-up-octocat.", timeout=20000
        )
        expect(card.get_by_role("switch", name="On")).to_be_checked()
        shot(page, "extensions-card-signed-in")
        # Settings draws the same panel.
        settings = page_at(browser, info, "/workspace?open=settings")
        fieldset = settings.locator(".extension-settings-fieldset[data-extension='copilot']")
        expect(fieldset).to_contain_text("Signed in as made-up-octocat.", timeout=20000)
        fieldset.get_by_role("switch", name="On").click()
        expect(fieldset.get_by_role("switch", name="On")).not_to_be_checked(timeout=10000)
        assert call(info, "GET", "/copilot")["on"] is False
        shot(settings, "settings-panel")
    finally:
        process.terminate()
        process.wait(timeout=20)
