"""The Blazor Code App page (the Power Apps extension's) on this machine's tools: the strip (each tool with
its version or Install), who is signed in asked on click; the tabs (Run live and Push need a code app
open); New code app's dialog (name, environment, folder); Custom connector's API picker and its empty
words; Runs this session; the rail's Code App area while the extension is on."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page
from tests.e2e.blazor.extension_server import extension_server


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    with extension_server(tmp_path_factory.mktemp("blazor-codeapp"), ["streamlit", "powerapps"]) as info:
        yield info


def test_the_strip_the_tabs_and_new_code_app(browser: Browser, server: dict[str, Any]) -> None:
    tools = call(server, "GET", "/powerapps")["tools"]["tools"]
    page = open_page(browser, server, "codeapp")
    expect(page.locator(".nav-rail a", has_text="Code App")).to_have_count(1)
    expect(page.locator(".area-page-title")).to_have_text("Code App")
    for tool in tools:
        if tool["id"] == "dotnet" and any(t["id"] == "pac" and t["ok"] for t in tools):
            continue
        chip = page.locator(f".ca-tool[data-tool={tool['id']}]")
        expect(chip).to_contain_text(tool["name"])
        if not tool["ok"] and tool["phase"] == 1:
            expect(chip.locator(".ca-install")).to_have_text("Install")
    expect(page.locator(".ca-account button")).to_have_text("Who is signed in?")
    expect(page.locator(".ca-tab[data-tab=live]")).to_be_disabled()
    expect(page.locator(".ca-tab[data-tab=push]")).to_be_disabled()
    expect(page.locator(".ca-empty")).to_contain_text("No code app is open.")

    page.click("button:has-text('New code app')")
    dialog = page.locator(".dialog[aria-label='New code app']")
    expect(dialog.locator('input[aria-label="The app\'s name"]')).to_be_visible()
    expect(dialog.locator("select[aria-label='The environment']")).to_contain_text("Another (its id)…")
    expect(dialog.locator("input[aria-label='The folder it goes in']")).to_be_visible()
    dialog.locator(".dialog-foot button:has-text('Cancel')").click()
    expect(dialog).to_have_count(0)

    page.click(".ca-tab[data-tab=custom]")
    expect(page.locator(".ca-custom")).to_contain_text("No APIs yet: add one on the APIs page.")
    page.click(".ca-tab[data-tab=runs]")
    expect(page.locator(".ca-panel")).to_contain_text("No runs this session.")
    page.close()
