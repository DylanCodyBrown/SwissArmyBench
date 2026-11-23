"""The Blazor front end's app-wide parts (the classic fileChooser.ts, variableAnywhere.ts, tour.ts,
tourButton.ts, projectImport.ts, betaNotes.ts and desktopApp.ts), on made-up data only."""

from __future__ import annotations

import json
import re
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page

# The tour's own made-up tables open now (the page's fetch rides on its cookie).
TOUR_TABLES = "(await (await fetch('/datasets')).json()).datasets.filter(d => d.name.startsWith('tour_'))"


def test_the_pages_own_file_picker(browser: Browser, server: dict[str, Any]) -> None:
    """Open project… with no system dialog: the page's own picker (Places, the breadcrumb, Filter, New folder,
    Hidden files, Up), a folder made in it, then Choose this folder."""
    root = server["tmp"] / "made_up_picker"
    (root / "inner").mkdir(parents=True, exist_ok=True)
    (root / "readme.txt").write_text("made-up\n", encoding="utf-8")
    page = open_page(browser, server, "")
    page.get_by_role("button", name="Open project…").click()
    picker = page.locator(".dialog.file-chooser")
    expect(picker.locator(".file-places")).to_contain_text("Places")
    picker.get_by_label("Folder", exact=True).fill(str(root))
    picker.get_by_label("Folder", exact=True).press("Enter")
    expect(picker.locator(".file-crumb.current")).to_have_text("made_up_picker")
    expect(picker.locator(".file-row.folder", has_text="inner")).to_be_visible()
    expect(picker.locator("[role=status]")).to_contain_text("1 folder, 1 file")
    picker.get_by_label("Filter").fill("inn")
    expect(picker.locator(".file-row")).to_have_count(1)
    picker.get_by_label("Filter").press("Escape")
    expect(picker.locator(".file-row")).to_have_count(2)
    expect(picker).to_be_visible()
    picker.get_by_role("button", name="New folder").click()
    picker.get_by_label("New folder's name").fill("made_up_new")
    picker.get_by_label("New folder's name").press("Enter")
    expect(picker.locator(".file-crumb.current")).to_have_text("made_up_new")
    assert (root / "made_up_new").is_dir()
    picker.get_by_role("button", name="Up", exact=True).click()
    expect(picker.locator(".file-crumb.current")).to_have_text("made_up_picker")
    picker.locator(".file-row", has_text="inner").dblclick()
    expect(picker.locator(".file-crumb.current")).to_have_text("inner")
    picker.get_by_role("button", name="Choose this folder").click()
    expect(page.locator(".question-words")).to_contain_text("inner is not a project yet.")
    page.locator(".dialog-foot").get_by_role("button", name="Cancel").click()
    page.close()


def test_a_variable_in_any_box(browser: Browser, server: dict[str, Any]) -> None:
    """Typing ${ in a text box lists the variables (names and sources, never a value); Enter puts one in; the
    right-click Text menu (Cut, Copy, Paste, Insert variable…); New variable… opens Add variable."""
    call(server, "PUT", "/variables", {"name": "MADE_UP_REGION", "value": "north", "from": "value"})
    page = open_page(browser, server, "")
    page.get_by_role("button", name="New project").click()
    box = page.locator(".dialog input").first
    box.click()
    box.press_sequentially("x ${MADE_UP")
    listed = page.get_by_role("listbox", name="Variables")
    expect(listed.locator("[data-name=MADE_UP_REGION]")).to_be_visible()
    expect(listed).not_to_contain_text("north")
    box.press("Enter")
    expect(box).to_have_value("x ${MADE_UP_REGION}")
    box.fill("y ")
    box.click(button="right")
    menu = page.get_by_role("menu", name="Text")
    for words in ("Cut", "Copy", "Paste", "Insert variable…"):
        expect(menu.get_by_role("menuitem", name=words)).to_be_visible()
    menu.get_by_role("menuitem", name="Insert variable…").click()
    expect(listed).to_be_visible()
    listed.locator("[data-name=MADE_UP_REGION]").dispatch_event("mousedown")
    expect(box).to_have_value("y ${MADE_UP_REGION}")
    box.fill("")
    box.press_sequentially("${MADE_UP_NEW")
    listed.locator(".variable-new").dispatch_event("mousedown")
    adding = page.locator(".dialog", has_text="Add variable")
    expect(adding.get_by_label("Name")).to_have_value("MADE_UP_NEW")
    adding.get_by_label("Value").fill("made-up")
    adding.get_by_role("button", name="Add").click()
    expect(box).to_have_value("${MADE_UP_NEW}")
    call(server, "DELETE", "/variables/MADE_UP_NEW")
    call(server, "DELETE", "/variables/MADE_UP_REGION")
    page.close()


def test_the_tour(browser: Browser, server: dict[str, Any]) -> None:
    """The Projects page's Tour (New here? until seen): a card per place, its two made-up tables staged and
    closed again; the keys (Right, Left, Escape); back where it started."""
    page = open_page(browser, server, "")
    expect(page.get_by_role("button", name="New here? Take the tour")).to_be_visible()
    page.get_by_role("button", name="Not now").click()
    expect(page.get_by_role("button", name="New here? Take the tour")).to_have_count(0)
    page.locator(".area-page-actions").get_by_role("button", name="Tour").click()
    tour = page.get_by_role("dialog", name="Tour")
    expect(tour.locator(".tour-word")).to_have_text("Hi!")
    expect(tour.get_by_role("button", name="Back")).to_have_count(0)
    page.wait_for_function(f"async () => ({TOUR_TABLES}).length === 2")
    page.keyboard.press("ArrowRight")
    expect(tour.locator(".tour-word")).to_have_text("Home")
    tour.get_by_role("button", name="Next").click()
    expect(tour.locator(".tour-word")).to_have_text("Connections")
    expect(page).to_have_url(re.compile(r"/blazor/connections"))
    page.keyboard.press("ArrowLeft")
    expect(tour.locator(".tour-word")).to_have_text("Home")
    page.keyboard.press("Escape")
    expect(tour).to_have_count(0)
    page.wait_for_function(f"async () => ({TOUR_TABLES}).length === 0")
    page.close()


def test_import_from_another_project(browser: Browser, server: dict[str, Any]) -> None:
    """Import… on Home (the classic projectImport.ts): another project's notebook, ticked and imported."""
    source = call(server, "POST", "/project/new", {"name": "made_up_import_source"})["project"]["folder"]
    with open(f"{source}/made_up_notes.ipynb", "w", encoding="utf-8") as made:
        json.dump({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}, made)
    call(server, "POST", "/project/new", {"name": "made_up_import_target"})
    page = open_page(browser, server, "")
    page.locator(".area-page-actions").get_by_role("button", name="Import…").click()
    page.get_by_role("menuitem", name="Notebooks, scripts and apps…").click()
    dialog = page.locator(".dialog.import-dialog")
    expect(dialog.get_by_role("button", name="Import")).to_be_disabled()
    dialog.get_by_role("button", name="Another project…").click()
    picker = page.locator(".dialog.file-chooser")
    picker.get_by_label("Folder", exact=True).fill(source)
    picker.get_by_label("Folder", exact=True).press("Enter")
    picker.get_by_role("button", name="Choose this folder").click()
    dialog.locator("input[data-name='made_up_notes.ipynb']").check()
    dialog.get_by_role("button", name="Import").click()
    expect(dialog).to_have_count(0)
    documents = call(server, "GET", "/project/documents")["documents"]
    assert any(d["path"] == "made_up_notes.ipynb" for d in documents)
    page.close()


def test_leave_a_note_in_every_right_click_menu(browser: Browser, server: dict[str, Any]) -> None:
    """Beta mode on: a right-click menu ends with Leave a note…, whose words go to the beta log."""
    call(server, "PUT", "/beta", {"on": True})
    try:
        page = open_page(browser, server, "")
        page.get_by_role("button", name="New project").click()
        page.locator(".dialog input").first.click(button="right")
        menu = page.get_by_role("menu", name="Text")
        menu.get_by_role("menuitem", name="Leave a note…").click()
        form = page.locator(".dialog", has_text="Leave a note")
        # The note is about the element right-clicked (the classic betaNotes.ts describe: the field's label),
        # outlined while the form is open, and it offers the window's picture.
        expect(form.locator(".beta-note-where")).to_have_text("label: Name")
        expect(page.locator(".beta-outline")).to_have_count(1)
        form.get_by_label("What is wrong").fill("made-up note about the menu")
        form.locator(".beta-note-picture").check()
        form.get_by_role("button", name="Save").click()
        expect(form).to_have_count(0)
        notes = call(server, "GET", "/beta/notes")["notes"]
        note = next(n for n in notes if n["text"] == "made-up note about the menu")
        assert note["element"]["tag"] == "label"
        assert note["element"]["path"]
        assert note.get("picture")
        page.close()
    finally:
        call(server, "PUT", "/beta", {"on": False})


def test_the_desktop_apps_keys(browser: Browser, server: dict[str, Any]) -> None:
    """In the desktop app (window.sabApp) Ctrl+Tab goes round the tabs and Ctrl+W closes one; in a browser
    those keys stay the browser's."""
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = browser.new_page(viewport={"width": 1360, "height": 860})
    page.add_init_script("window.sabApp = { app: true, close: () => { window.sabClosed = true; } };")
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/grids?grid={grid}#token={server['token']}")
    page.wait_for_selector(".nav-rail", timeout=60_000)
    current = page.locator(".grid-tab.tab-item.current")
    expect(current).to_have_attribute("data-grid", grid)
    # The browser keeps Ctrl+Tab and Ctrl+W for itself under a test's driver: the page hears them as the
    # desktop app's window hands them over.
    press = "key => document.dispatchEvent(new KeyboardEvent('keydown', {key, ctrlKey: true, bubbles: true}))"
    page.evaluate(press, "Tab")
    expect(current).not_to_have_attribute("data-grid", grid)
    before = page.locator(".grid-tab.tab-item").count()
    page.evaluate(press, "w")
    expect(page.locator(".grid-tab.tab-item")).to_have_count(before - 1)
    page.close()
