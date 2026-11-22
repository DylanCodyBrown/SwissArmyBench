"""The app's own question (web/src/dom.ts askYesNo: never the browser's confirm()), in a real browser: its
words as the dialog's heading, the primary button focused, Escape for no, Enter for yes, focus and the
document as they were after a no. Made-up text only."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401


def test_closing_an_unsaved_script_asks_on_the_apps_dialog(browser: Browser, server: dict[str, Any]) -> None:  # noqa: F811
    page = browser.new_context(viewport={"width": 1300, "height": 800}).new_page()
    seen: list[str] = []

    def browsers_own(dialog: Any) -> None:  # the browser's own dialog: none may open
        seen.append(dialog.type)
        dialog.dismiss()

    page.on("dialog", browsers_own)
    page.goto(f"http://127.0.0.1:{server['port']}/scripts#token={server['token']}")
    expect(page.locator(".wb-codex")).to_be_visible(timeout=20000)
    call(server, "POST", "/workbench/window", {"command": "file.newScript", "args": {}}, agent=True)
    tab = page.locator(".wb-tab").first
    expect(tab).to_be_visible(timeout=20000)
    page.locator(".monaco-editor").first.click()
    page.keyboard.type("x = 1")
    tab.get_by_role("button").first.click()
    asked = page.locator("dialog.ask[open]")
    expect(asked).to_be_visible()
    expect(asked.locator("h2")).to_contain_text("has changes that are not saved. Close it anyway?")
    expect(asked.locator("button.ask-ok")).to_be_focused()
    expect(asked.locator("button.ask-ok")).to_have_text("Close it")
    # Escape says no: the question goes, the document stays with its text.
    page.keyboard.press("Escape")
    expect(asked).to_have_count(0)
    expect(tab).to_be_visible()
    # Cancel says no too.
    tab.get_by_role("button").first.click()
    asked.locator("button.ask-cancel").click()
    expect(asked).to_have_count(0)
    expect(tab).to_be_visible()
    # Enter on the focused primary button says yes: it closes.
    tab.get_by_role("button").first.click()
    expect(asked.locator("button.ask-ok")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator(".wb-tab")).to_have_count(0)
    assert seen == []
