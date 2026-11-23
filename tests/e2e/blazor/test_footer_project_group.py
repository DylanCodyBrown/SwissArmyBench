"""The footer's common marks (the classic appFooter.ts: the version, the zoom, Launch Claude, the credit) and
the open project's group on the Grids page (the classic startView.ts: Save, Copy to…, Export outline,
Close, Autosave)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

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
