"""The Collaboration panel in the browser (Layout/Collaboration): shown and hidden on two pages (Ctrl+Shift+M
and the status bar's button) floating over the page without moving it; a note posted with an `@cell`
reference picked from the `@` list, its link clicked through to the notebook's cell; a reply, a reaction and
a resolve; a second author's files written on disk (as a Pull brings them) showing up live with the unread
count; Collaborate on a table's tab. Made-up people and data only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page, unnamed_controls


def _project(server: dict[str, Any], name: str) -> Path:
    folder = Path(server["tmp"]) / "projects" / name
    call(server, "POST", "/project/new", {"path": str(folder)})
    call(server, "PUT", "/collaboration/profile", {"name": "Avery Lin"})
    cells = [
        {
            "cell_type": "code",
            "metadata": {"swissarmybench": {"number": n}},
            "source": [f"monthly_total_{n} = {n * 100}\n"],
            "outputs": [],
            "execution_count": None,
        }
        for n in (1, 2)
    ]
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (folder / "returns.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    return folder


def _panel(page: Page) -> Any:
    return page.locator(".collab-panel")


def _write_note(page: Page, text: str) -> None:
    box = _panel(page).locator(".collab-composer textarea")
    box.click()
    box.press_sequentially(text)


def test_shown_and_hidden_on_two_pages_over_the_page(browser: Browser, server: dict[str, Any]) -> None:
    _project(server, "Panel shown")
    page = open_page(browser, server, "tables")
    main = page.locator(".page-main")
    before = main.bounding_box()
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page)).to_be_visible()
    expect(_panel(page).locator(".collab-title")).to_have_text("Collaboration")
    assert main.bounding_box() == before  # it floats: the page keeps its place and size
    assert _panel(page).evaluate("e => getComputedStyle(e).position") == "fixed"
    assert [c for c in unnamed_controls(page) if "collab" in c] == []  # every control of the panel is named
    _panel(page).get_by_role("button", name="Hide the Collaboration panel").click()
    expect(_panel(page)).to_have_count(0)

    page.goto(page.url.replace("/blazor/tables", "/blazor/notebooks"))
    page.wait_for_selector(".nav-rail")
    button = page.locator(".status-collab")
    button.click()
    expect(_panel(page)).to_be_visible()
    expect(button).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page)).to_have_count(0)
    page.close()


def test_a_note_with_a_cell_reference_reply_react_resolve(browser: Browser, server: dict[str, Any]) -> None:
    folder = _project(server, "Panel notes")
    page = open_page(browser, server, "tables")
    page.keyboard.press("Control+Shift+M")
    panel = _panel(page)
    expect(panel.locator(".collab-empty-words")).to_be_visible()
    _write_note(page, "Please check @cell")
    popup = panel.locator(".collab-popup")
    expect(popup.get_by_role("option", name=re.compile("returns.ipynb cell 2"))).to_be_visible()
    popup.get_by_role("option", name=re.compile("returns.ipynb cell 2")).click()
    panel.locator(".collab-composer textarea").press_sequentially("totals **twice**")
    panel.locator(".collab-composer textarea").press("Enter")
    thread = panel.locator(".collab-item.thread")
    expect(thread).to_have_count(1)
    expect(thread.locator("strong", has_text="twice")).to_be_visible()
    files = list((folder / ".sab" / "collaboration").glob("t-*/*.md"))
    assert len(files) == 1 and "sab:cell/returns.ipynb#2" in files[0].read_text(encoding="utf-8")

    # A reply, a reaction and a resolve, each in the thread.
    thread.locator(".collab-replies").click()
    expect(panel.locator(".collab-thread")).to_be_visible()
    panel.locator(".collab-composer textarea").press_sequentially("Fixed it in the second cell.")
    panel.locator(".collab-composer textarea").press("Enter")
    expect(panel.locator(".collab-thread .collab-message")).to_have_count(2)
    first = panel.locator(".collab-thread .collab-message").first
    first.get_by_role("button", name="Add a reaction").click()
    first.get_by_role("menuitem", name="React 👍").click()
    expect(first.locator(".collab-reaction.mine")).to_contain_text("1")
    panel.get_by_role("button", name="Resolve").click()
    expect(panel.locator(".collab-resolved-line")).to_contain_text("Resolved by avery-lin")
    assert list((folder / ".sab" / "collaboration").glob("t-*/_events/*.toml"))

    # The reference opens the notebook at its cell.
    first.locator("a.collab-ref").click()
    expect(page).to_have_url(re.compile(r"/blazor/notebooks\?path=.*returns\.ipynb&cell=2"))
    expect(page.locator('.wb-cell[data-number="2"]')).to_be_visible(timeout=30_000)
    page.close()


def test_a_second_authors_files_show_up_live(browser: Browser, server: dict[str, Any]) -> None:
    folder = _project(server, "Panel live")
    page = open_page(browser, server, "tables")
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page).locator(".collab-empty-words")).to_be_visible()
    # Sam's computer wrote these (as a Pull brings them): a thread and its first message.
    thread = folder / ".sab" / "collaboration" / "t-5a7e0001"
    thread.mkdir(parents=True)
    (thread / "thread.toml").write_text(
        'id = "t-5a7e0001"\ntitle = "Returns look high"\nchannel = "general"\n'
        'created = "2026-11-25T09:00:00.000000Z"\npinned = false\n\n'
        '[created_by]\nname = "Sam Ortiz"\nlogin = "sam-ortiz"\n',
        encoding="utf-8",
    )
    (thread / "20261125T090000.000000Z-sam-ortiz-5a7e0002.md").write_text(
        '+++\nid = "5a7e0002"\nthread = "t-5a7e0001"\nkind = "note"\ntime = "2026-11-25T09:00:00.000000Z"\n'
        'edited = ""\ndeleted = false\nmentions = ["avery-lin"]\n\n[author]\nname = "Sam Ortiz"\n'
        'login = "sam-ortiz"\n+++\n\n@avery-lin returns look high this month.\n',
        encoding="utf-8",
    )
    item = _panel(page).locator(".collab-item.thread", has_text="Sam Ortiz")
    expect(item).to_be_visible(timeout=20_000)
    expect(item).to_contain_text("returns look high")
    expect(page.locator(".status-collab .collab-badge")).to_have_text("1")
    page.close()


def test_collaborate_on_a_tables_tab(browser: Browser, server: dict[str, Any]) -> None:
    _project(server, "Panel tab")
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "tables")
    tab = page.locator(".grid-tab.tab-item").first
    expect(tab).to_be_visible()
    tab.click(button="right")
    page.locator(".menu-item", has_text="Collaborate").click()
    panel = _panel(page)
    expect(panel).to_be_visible()
    expect(panel.locator(".collab-composer textarea")).to_have_attribute(
        "placeholder", re.compile("A note on ")
    )
    page.close()
