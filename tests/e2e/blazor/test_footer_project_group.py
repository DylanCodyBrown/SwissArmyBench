"""The footer's common marks (the classic appFooter.ts: the version, the zoom, Launch Claude, the credit) and
the open project's group on the Grids page (the classic startView.ts: Save, Copy to…, Export outline,
Close, Autosave)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.e2e.blazor.conftest import call, open_page


def test_the_footer_zooms_and_the_project_group_saves(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    call(server, "POST", "/project/new", {"name": "made_up_footer_shop"})
    page = open_page(browser, server, "grids")
    footer = page.locator(".status-bar")
    expect(footer).to_contain_text("Swiss Army Bench")
    expect(footer).to_contain_text("Created by Dylan Brown")
    expect(footer.get_by_role("button", name="Launch Claude")).to_be_visible()
    zoom = footer.get_by_role("group", name="Zoom")
    expect(zoom).to_contain_text("100%")
    zoom.get_by_role("button", name="Zoom in").click()
    expect(zoom).to_contain_text("110%")
    page.keyboard.press("Control+0")
    expect(zoom).to_contain_text("100%")

    group = page.locator(".project-group")
    expect(group).to_contain_text("made_up_footer_shop")
    group.get_by_role("button", name="Export outline").click()
    expect(page.locator(".note-corner")).to_contain_text("ARCHITECTURE.md")
    group.get_by_role("button", name="Save").click()
    # The made-up store's pushed tables have no source to read again: Keep its rows is asked (once a table on
    # this server, so another test may have answered it already), left unticked.
    asked = page.get_by_role("dialog", name="Save project")
    try:
        asked.wait_for(timeout=3_000)
        asked.get_by_role("button", name="Save").click()
    except PlaywrightTimeoutError:
        pass
    expect(group).not_to_contain_text("●")
    expect(page.locator(".note-corner")).to_contain_text("Saved")
    group.get_by_label("Private").check()
    expect(group.get_by_label("Private")).to_be_checked()
    assert call(server, "GET", "/project")["project"]["private"] is True
    group.get_by_label("Autosave").uncheck()
    assert call(server, "GET", "/project")["project"]["autosave"] is False
    group.get_by_role("button", name="Close").click()
    expect(page.locator(".project-group")).to_have_count(0)
    page.close()


def test_save_asks_keep_its_rows_once(browser: Browser, server: dict[str, Any]) -> None:
    """A pasted table has no source to read again: Save asks Keep its rows once (the classic chooseRows)."""
    call(server, "POST", "/project/new", {"name": "made_up_rows_shop", "discard": True})
    page = open_page(browser, server, "")
    page.get_by_role("button", name="Paste data").click()
    page.get_by_label("Pasted table").fill("city\tvisits\nNorthvale\t3\n")
    page.locator(".dialog-foot").get_by_role("button", name="Open").click()
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("pasted_")
    page.locator(".project-group").get_by_role("button", name="Save").click()
    asked = page.get_by_role("dialog", name="Save project")
    expect(asked).to_contain_text("Keep its rows")
    asked.locator("input[type=checkbox]").first.check()
    asked.get_by_role("button", name="Save").click()
    expect(page.locator(".note-corner")).to_contain_text("Saved")
    tables = call(server, "GET", "/project")["project"]["tables"]
    assert any(t["keep_rows"] for t in tables if t["name"].startswith("pasted_"))
    # Asked once: the next Save goes straight through.
    page.locator(".project-group").get_by_role("button", name="Save").click()
    expect(page.get_by_role("dialog", name="Save project")).to_have_count(0)
    page.close()
