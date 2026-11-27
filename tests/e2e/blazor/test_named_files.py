"""Every new file is named first (the owner, 2026-11-27: "Everything should get a name or the file is not
created and yes every file should go scaffolding file on the back. The list of follow-ups available should
change with projects"), in the browser on made-up projects: every way to make a file opens the one New file
dialog with its type preset, Cancel makes nothing and leaves no tab, and a Streamlit project's list has its
own types (a widget, a canvas), made by the extension."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, name_new_file, open_page


def project(server: dict[str, Any], name: str, kind: str | None = None) -> Path:
    body = {"path": str(server["tmp"] / "projects" / name)} | ({"type": kind} if kind else {})
    state = call(server, "POST", "/project/new", body)
    return Path(state.get("folder") or state["project"]["folder"])


def files_of(folder: Path) -> list[str]:
    """The project's own files (the app's state folder and its Python left out)."""
    skip = (".sab", ".venv", "__pycache__")
    return sorted(
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if p.is_file() and not any(part in skip for part in p.relative_to(folder).parts)
    )


def cancelled(page: Page, title: str) -> None:
    """The New file dialog is up for this type; Cancel: it goes, and no tab was made."""
    dialog = page.locator(f".dialog[aria-label='{title}']")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("Name")).not_to_have_value("")
    dialog.locator(".new-file-cancel").click()
    expect(dialog).to_have_count(0)


def test_every_entry_point_asks_a_name_and_cancel_makes_nothing(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})
    folder = project(server, "made_up_named")
    before = files_of(folder)
    page = open_page(browser, server, "scripts")
    tabs = page.locator(".wb-tab")

    # The Scripts page: the top bar's New file, the landing page's New script, the Files pane's "+".
    page.click(".wb-top-new")
    page.click(".context-menu [role=menuitem]:has-text('Python script')")
    cancelled(page, "New Python script")
    page.locator(".wb-landing button", has_text="New script").click()
    cancelled(page, "New Python script")
    page.click(".files-pane .wb-codex-new")
    cancelled(page, "New Python script")
    # The palette's New script and New SQL file.
    for words, title in (("New script", "New Python script"), ("New SQL file", "New SQL file")):
        page.keyboard.press("Control+Shift+P")
        palette = page.get_by_role("dialog", name="Command palette")
        palette.locator("input").fill(words)
        page.keyboard.press("Enter")
        cancelled(page, title)
    # An address that asks for one: the dialog, never an untitled tab; the address goes back to the page's.
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/scripts?new=1#token={server['token']}")
    cancelled(page, "New Python script")
    expect(page).to_have_url(re.compile(r"/blazor/scripts$|/blazor/scripts#"))
    expect(tabs).to_have_count(0)

    # The tab strip's "+" (a tab open first: the project's README).
    page.locator(".files-pane .files-item[data-path='README.md']").click()
    expect(tabs).to_have_count(1)
    page.click(".wb-tab-new")
    page.click(".context-menu [role=menuitem]:has-text('SQL file')")
    cancelled(page, "New SQL file")
    expect(tabs).to_have_count(1)
    page.close()

    # The Notebooks page's New notebook, on its top bar and its landing page.
    page = open_page(browser, server, "notebooks")
    expect(page.locator(".wb-top-new")).to_have_text(re.compile("New notebook"))
    page.click(".wb-top-new")
    cancelled(page, "New Notebook")
    page.locator(".wb-landing button", has_text="New notebook").click()
    cancelled(page, "New Notebook")
    expect(page.locator(".wb-tab")).to_have_count(0)
    page.close()

    # The Tables page: the "+" and the palette's New query go to the Scripts page's dialog for a SQL file.
    page = open_page(browser, server, "tables")
    page.click("a.new-tab[aria-label='New query']")
    cancelled(page, "New SQL file")
    expect(page.locator(".wb-tab")).to_have_count(0)
    page.close()
    page = open_page(browser, server, "scripts?new=sql")  # what Ctrl+T, Ctrl+N and New query open
    cancelled(page, "New SQL file")
    page.close()

    # The Structures page's New: a JSON file, named first.
    page = open_page(browser, server, "structures")
    page.locator(".structures-new").first.click()
    cancelled(page, "New JSON")
    page.close()

    assert files_of(folder) == before  # Cancel made nothing, anywhere

    # And Create makes exactly the file named, written by the server before its tab opens.
    page = open_page(browser, server, "notebooks?new=1")
    name_new_file(page, "made_up_explore")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_explore.ipynb")
    assert files_of(folder) == sorted([*before, "made_up_explore.ipynb"])
    page.close()


def test_a_streamlit_projects_list_shows_its_types_and_makes_them(
    browser: Browser, server: dict[str, Any]
) -> None:
    plain = project(server, "made_up_plain")
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    lines = page.locator(".context-menu [role=menuitem]")
    expect(lines.filter(has_text="Python script")).to_have_count(1)
    expect(lines.filter(has_text="Widget")).to_have_count(0)  # a plain project has none of them
    expect(lines.filter(has_text="Canvas")).to_have_count(0)
    page.keyboard.press("Escape")
    page.close()
    assert plain.is_dir()
    call(server, "POST", "/project/close", {"discard": True})

    folder = project(server, "made_up_app", "streamlit")
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    lines = page.locator(".context-menu [role=menuitem]")
    expect(lines.filter(has_text="Python script")).to_have_count(1)
    expect(lines.get_by_text("Widget (.widget.py)", exact=True)).to_be_visible()
    expect(lines.get_by_text("Canvas (.canvas.json)", exact=True)).to_be_visible()
    lines.get_by_text("Widget (.widget.py)", exact=True).click()

    dialog = page.locator(".dialog[aria-label='New Widget']")
    expect(dialog.get_by_label("Name")).to_have_value("my_widget.widget.py")
    expect(dialog.get_by_label("Folder", exact=True)).to_have_count(0)  # it asks a name only
    expect(dialog.locator(".new-file-check")).to_have_text("Makes widgets/my_widget.widget.py")
    dialog.get_by_label("Name").fill("Not A Name")
    expect(dialog.locator(".new-file-check.error")).to_contain_text("Not a valid name")
    dialog.get_by_label("Name").fill("made_up_tile")
    expect(dialog.locator(".new-file-check")).to_have_text("Makes widgets/made_up_tile.widget.py")
    dialog.locator(".new-file-create").click()
    # Made by the extension's own New widget, in the project's widgets/, and opened in the Widgets window.
    expect(page).to_have_url(re.compile(r"/blazor/widgets\?name=made_up_tile"))
    text = (folder / "widgets" / "made_up_tile.widget.py").read_text(encoding="utf-8")
    assert "swissarmybench-widget" in text
    page.close()
