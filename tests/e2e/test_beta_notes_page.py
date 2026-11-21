# ruff: noqa: F811
"""Beta notes (the owner, 2026-11-15): right-click anything, "Leave a note…", and the note is in the beta
log with a description of what was clicked, never its data. A ribbon button, a grid cell, a Workbench
tab and a code editor each take a note; a text box keeps its own menu and copy and paste;
the picture is there only when ticked; beta mode off takes the item away at once, on brings it back.
Made-up data only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import Browser, Locator, Page, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import menu

VALUE = "Globex-Acme-77"  # a made-up cell value that must never reach the log
SHOTS = os.environ.get("SWISSARMYBENCH_SHOTS", "") or None


def notes(server: dict[str, Any]) -> list[dict[str, Any]]:
    return list(call(server, "GET", "/beta/notes")["notes"])


def log_text(server: dict[str, Any]) -> str:
    return json.dumps(call(server, "GET", "/beta/log?limit=5000")["events"])


def leave_note(
    page: Page, target: Locator, words: str, picture: bool = False, shot: str | None = None
) -> None:
    """Right-click `target`, choose Leave a note…, type `words`, Save; the toast says Saved."""
    target.click(button="right")
    page.get_by_role("menuitem", name="Leave a note…").click()
    form = page.locator("dialog.beta-note-form")
    expect(form).to_be_visible()
    expect(form.locator(".beta-outline")).to_be_visible()  # the element, outlined while the form is open
    expect(form.get_by_label("Attach a picture of this window")).not_to_be_checked()
    expect(form).to_contain_text("the picture shows your data")
    form.get_by_label("What is wrong").fill(words)
    if picture:
        form.get_by_label("Attach a picture of this window").check()
    if shot:
        page.wait_for_timeout(300)
        page.screenshot(path=shot)
    form.get_by_role("button", name="Save").click()
    expect(form).to_have_count(0)
    expect(page.locator(".toast", has_text="Saved")).to_be_visible()


def test_notes_on_a_ribbon_button_and_a_grid_cell_and_a_text_box_keeps_its_menu(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    call(server, "PUT", "/beta", {"on": True})
    call(server, "DELETE", "/beta/log")
    url = push_client.push(
        pd.DataFrame({"client": [VALUE, "Initech"], "amount": [100, 250]}), name="clients", new_grid=True
    )
    context = browser.new_context(viewport={"width": 1400, "height": 860}, device_scale_factor=2)
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page.goto(url)
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    try:
        # The quiet mark: beta mode is recording.
        expect(page.locator(".statusbar .beta-mark")).to_have_text("Beta")

        # ----- a ribbon button: no menu of its own, so a small one with only the item
        settings = page.locator(".nav-rail [data-area='settings']")
        shot = str(Path(SHOTS) / "beta-note-form.png") if SHOTS else None
        leave_note(page, settings, "Settings opens too slowly", shot=shot)
        first = notes(server)[-1]
        assert first["text"] == "Settings opens too slowly" and first["page"] == "grid"
        assert first["element"]["role"] == "button" and first["element"]["name"] == "Settings"
        assert "nav-rail" in first["element"]["path"] and first["element"]["box"]["w"] > 0
        assert "picture" not in first and first["window"] == "main"

        # ----- a grid cell: its own menu keeps its entries and gets the item; the cell's text is not kept
        cell = page.locator(".ag-row[row-index='0'] .ag-cell[col-id='client']")
        cell.click(button="right")
        expect(page.get_by_role("menuitem", name="Send value to Analyze")).to_be_visible()
        page.keyboard.press("Escape")
        leave_note(page, cell, "This value should be bold", picture=True)
        second = notes(server)[-1]
        assert second["element"]["role"] == "gridcell" and "text" not in second["element"]
        assert 'col-id="col#' in second["element"]["path"]  # the column by its alias
        assert second["picture"].startswith("pictures/")  # ticked: the only way data enters
        assert any(a.startswith("click:") for a in second["actions"])  # what was clicked before it
        assert VALUE not in log_text(server)

        # ----- a text box's right-click is the text menu (Cut, Copy, Paste, Insert variable…: the owner,
        # 2026-11-19, design principle 12.7), and copy and paste by the keyboard still work
        page.locator(".ag-header-cell[col-id='client']").click()
        page.locator(".ribbon").get_by_role("button", name="Filter…").click()
        # A text column starts on its values to tick (feel-b, 2026-11-19): "equals" gives the one text box.
        page.locator("dialog[open]").get_by_label("Condition").select_option("eq")
        box = page.locator("dialog[open] input[type=text], dialog[open] input:not([type])").first
        expect(box).to_be_visible()
        box.fill("Initech")
        box.click(button="right")
        menu = page.locator(".menu")
        expect(menu.get_by_role("menuitem", name="Insert variable…")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Paste")).to_be_visible()
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        box.press("Control+a")
        box.press("Control+c")
        box.fill("")
        box.press("Control+v")
        expect(box).to_have_value("Initech")
        page.keyboard.press("Escape")
    finally:
        context.close()
        close_tables(server)


def test_notes_on_a_workbench_tab_a_canvas_block_and_the_editor_then_beta_mode_off_and_on(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    call(server, "PUT", "/beta", {"on": True})
    book = tmp_path / "sales.ipynb"
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(book), "cells": [{"kind": "code", "source": "# Total\ntotal = 1"}]},
    )
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={quote(str(book))}")
    tabs = page.locator(".wb-tab")
    expect(tabs.first).to_be_visible(timeout=20000)
    try:
        expect(page.locator(".wb-status .beta-mark")).to_be_visible()
        # ----- a Workbench tab: its own right-click menu (the moves, Close) gets the item
        tabs.first.click(button="right")
        expect(page.get_by_role("menuitem", name="Close")).to_be_visible()
        page.keyboard.press("Escape")
        leave_note(page, tabs.first, "The tab's name is cut short")
        tab_note = notes(server)[-1]
        assert tab_note["page"] == "workbench" and "wb-tab" in tab_note["element"]["path"]
        assert "notebook" in tab_note["tabs"]

        # ----- the code editor: Monaco's own menu has the item
        editor = page.locator(".wb-cell .monaco-editor").first
        expect(editor).to_be_visible(timeout=20000)
        editor.click(button="right")
        item = page.locator(".monaco-menu .action-label", has_text="Leave a note…")
        expect(item).to_be_visible()
        page.wait_for_timeout(400)  # Monaco's menu ignores a click right as it opens
        item.click()
        form = page.locator("dialog.beta-note-form")
        form.get_by_label("What is wrong").fill("Completion is slow here")
        form.get_by_role("button", name="Save").click()
        expect(form).to_have_count(0)
        assert "monaco" in notes(server)[-1]["element"]["path"] and "text" not in notes(server)[-1]["element"]

        # ----- beta mode off, from the Workbench's "…": no mark, no item, at once
        menu(page, "Workbench menu", "Turn beta mode off")
        expect(page.locator(".wb-status .beta-mark")).to_be_hidden()
        assert call(server, "GET", "/beta")["on"] is False
        tabs.nth(0).click()
        editor.click(button="right")
        expect(page.locator(".monaco-menu .action-label", has_text="Send to the agent").first).to_be_visible()
        expect(page.locator(".monaco-menu .action-label", has_text="Leave a note…")).to_have_count(0)
        page.keyboard.press("Escape")
        before = len(notes(server))

        # ----- on again, from the palette: everything works at once, no restart, no reload
        page.keyboard.press("Control+Shift+P")
        page.keyboard.insert_text("Turn beta mode on")
        page.keyboard.press("Enter")
        expect(page.locator(".wb-status .beta-mark")).to_be_visible()
        leave_note(page, tabs.first, "Back on")
        assert len(notes(server)) == before + 1
    finally:
        context.close()
        call(server, "PUT", "/beta", {"on": True})
