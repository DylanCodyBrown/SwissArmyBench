"""What the merge wired into the Notebooks and Scripts pages (the classic workbenchPage.ts): the Environment
as the right-hand pane (the status bar's Environment opens it, remembered; its Hide closes it), API.py's
Endpoints beside its code (the status bar's Endpoints in place of a script's Run settings), and the one
command palette carrying the Settings and Environment pages' commands. Made-up data only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_the_environment_pane_beside_the_code(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_pane.py")
    call(server, "POST", "/workbench/save", {"path": path, "text": "made_up_total = 42\n"})
    page = open_page(browser, server, f"scripts?path={path}")
    toggle = page.locator(".wb-status .wb-environment-toggle")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    toggle.click()
    pane = page.locator(".wb-vars.wb-environment")
    expect(pane).to_be_visible()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    page.reload()
    page.wait_for_selector(".nav-rail")
    expect(page.locator(".wb-vars.wb-environment")).to_be_visible()  # remembered for the page
    page.locator(".wb-vars.wb-environment").get_by_role("button", name="Hide Environment").click()
    expect(page.locator(".wb-vars.wb-environment")).to_have_count(0)
    page.close()


def test_api_py_shows_its_endpoints_beside_it(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/project/new", {"name": "made_up_endpoints"})
    api = Path(made["project"]["path"]) / "API.py"
    assert api.is_file()
    page = open_page(browser, server, f"scripts?path={api}")
    expect(page.locator(".wb-run-api")).to_be_visible()
    expect(page.locator(".wb-status .wb-mode-toggle-runSettings")).to_have_count(0)
    page.locator(".wb-status .wb-mode-toggle-endpoints").click()
    side = page.locator("aside.wb-endpoints")
    expect(side.locator(".local-api-pane")).to_be_visible()
    side.get_by_role("button", name="Close").click()
    expect(side).to_have_count(0)
    call(server, "POST", "/project/close", {})
    page.close()


def test_the_settings_and_environment_commands_in_the_palette(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "settings")
    page.keyboard.press("Control+Shift+P")
    palette = page.get_by_role("dialog", name="Command palette")
    palette.locator("input").fill("theme: dark")
    expect(palette.locator(".wb-palette-item").first).to_contain_text("Theme: Dark")
    page.keyboard.press("Enter")
    expect(page.locator("input[name=theme][value=dark]")).to_be_checked()
    page.keyboard.press("Control+Shift+P")
    palette.locator("input").fill("theme: light")
    page.keyboard.press("Enter")

    page.goto(page.url.split("/blazor/")[0] + "/blazor/environment")
    page.wait_for_selector(".nav-rail")
    page.keyboard.press("Control+Shift+P")
    palette.locator("input").fill("show libraries")
    expect(palette.locator(".wb-palette-item").first).to_contain_text("Show Libraries")
    page.keyboard.press("Enter")
    expect(page.get_by_role("tab", name=re.compile("^Libraries"))).to_have_attribute("aria-selected", "true")
    page.close()
