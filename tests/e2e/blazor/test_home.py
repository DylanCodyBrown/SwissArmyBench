"""The Blazor front end's Home: with a project open its summary (its tables, documents and connections,
each a link; the window's title; the status bar's name back to it), else the Projects page: New project made
through its dialog and opened, its card, Close project, Rename through the app's own dialog (an open project
is refused, said in the one error note), the search."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page


def test_new_project_from_the_dialog_then_its_card(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server)
    page.click("text=New project")
    page.fill(".new-project-name", "Quarter review")
    page.click(".dialog-foot >> text=Create")
    # Made: Home is its summary; New project and Open project… go to the projects page (?view=projects).
    expect(page.locator(".summary-name")).to_have_text("Quarter review")
    page.get_by_role("button", name="Open project…").click()
    expect(page).to_have_url(re.compile(r"\?view=projects$"))
    card = page.locator(".explorer-card", has_text="Quarter review")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Local")
    expect(page.locator(".status-project")).to_contain_text("Quarter review")
    assert call(server, "GET", "/project")["project"]["name"] == "Quarter review"

    # An open project cannot be renamed: the server's refusal in the one error note.
    card.locator(".explorer-more").click()
    card.locator(".menu-item", has_text="Rename").click()
    page.fill(".question-text", "Quarter review 2")
    page.click(".dialog-foot >> text=Rename")
    expect(page.locator(".error-note")).to_be_visible()

    page.click("text=Close project")
    expect(page.locator(".status-project")).to_contain_text("No project open")
    card.locator(".explorer-more").click()
    card.locator(".menu-item", has_text="Rename").click()
    page.fill(".question-text", "Quarter review 2")
    page.click(".dialog-foot >> text=Rename")
    expect(page.locator(".explorer-card", has_text="Quarter review 2")).to_be_visible()

    page.fill(".explorer-search", "nothing like it")
    expect(page.locator(".explorer-none")).to_have_text("No project matches.")
    page.close()


def test_open_a_file_opens_it_as_a_grid(browser: Browser, server: dict[str, Any]) -> None:
    """Open a file… asks the server's chooser in its file mode (no system dialog in a test: the app's own box
    is the page's own picker), then the file opens on the Grids page."""
    made_up = server["tmp"] / "made_up_targets_home.csv"
    made_up.write_text("region,target\nNorth,10\nSouth,20\n", encoding="utf-8")
    page = open_page(browser, server, "")
    page.get_by_role("button", name="Open a file…").click()
    choose_path(page, made_up)
    expect(page.locator(".grid-tab.tab-item", has_text="made_up_targets_home")).to_be_visible()
    assert any(g["dataset"] == "made_up_targets_home" for g in call(server, "GET", "/grids")["grids"])
    page.close()


def test_paste_data_and_a_cards_menu(browser: Browser, server: dict[str, Any]) -> None:
    """Paste data (a pasted table opens at once on the Grids page) and a project card's menu (the classic
    projectExplorer.ts: Open, Show in folder, Copy project to…, Rename, Remove from list, Delete…)."""
    call(server, "POST", "/project/new", {"name": "made_up_menu_shop"})
    page = open_page(browser, server, "?view=projects")
    card = page.locator(".explorer-card", has_text="made_up_menu_shop")
    card.get_by_role("button", name="made_up_menu_shop: more").click()
    menu = card.locator(".explorer-menu")
    expect(menu).to_contain_text("Copy project to…")
    expect(menu).to_contain_text("Show in folder")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Paste data").click()
    page.get_by_label("Pasted table").fill("city\tvisits\nNorthvale\t3\n")
    page.locator(".dialog-foot").get_by_role("button", name="Open").click()
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("pasted_")
    page.close()


def test_open_project_asks_in_the_classic_words(browser: Browser, server: dict[str, Any]) -> None:
    """Open project… on a plain folder: "is not a project yet" (Make this folder a project?, the classic
    projectFile.ts openProject), then the folder opens as a project; then a project with unsaved changes asks
    before Close (withQuestion: "<name> has unsaved changes." and "Let them go and close the project?")."""
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    plain = server["tmp"] / "made_up_plain_folder"
    plain.mkdir(exist_ok=True)
    (plain / "notes.txt").write_text("made-up notes\n", encoding="utf-8")
    page = open_page(browser, server, "")
    page.get_by_role("button", name="Open project…").click()
    choose_path(page, plain, folder=True)
    asked = page.locator(".question-words")
    expect(asked).to_contain_text("made_up_plain_folder is not a project yet.")
    page.locator(".dialog-foot").get_by_role("button", name="OK").click()
    expect(page.locator(".status-bar")).to_contain_text("made_up_plain_folder")
    assert call(server, "GET", "/project")["project"]["name"] == "made_up_plain_folder"
    call(server, "POST", "/project/autosave", {"on": False})
    call(server, "POST", "/samples/store", {})
    page.goto(page.url.split("/blazor/")[0] + "/blazor/grids")
    page.locator(".project-group").get_by_role("button", name="Close").click()
    expect(asked).to_contain_text("made_up_plain_folder has unsaved changes.")
    expect(asked).to_contain_text("Let them go and close the project?")
    page.locator(".dialog-foot").get_by_role("button", name="OK").click()
    expect(page.locator(".project-group")).to_have_count(0)
    page.close()


def test_alt_home_goes_home(browser: Browser, server: dict[str, Any]) -> None:
    """Alt+Home from any page goes Home (the classic nav.ts), and Back returns."""
    page = open_page(browser, server, "session")
    page.keyboard.press("Alt+Home")
    expect(page.get_by_role("button", name="Open project…")).to_be_visible()
    page.go_back()
    expect(page).to_have_url(re.compile(r"/session$"))
    page.close()


def made_up_project(server: dict[str, Any], name: str) -> str:
    """A made-up project open on the server: a table from a CSV file, a notebook that reads a made-up SQLite
    connection, a script."""
    folder = str(call(server, "POST", "/project/new", {"name": name})["project"]["folder"])
    made_up = server["tmp"] / f"{name}_orders.csv"
    made_up.write_text("order_id,region,units\n1,North,3\n2,East,9\n", encoding="utf-8")
    call(server, "POST", f"/datasets/{name}_orders/load", {"path": str(made_up)})
    code = 'import sqlite3\nconn = sqlite3.connect(":memory:")\n'
    shop = {"name": f"{name}_shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    call(server, "POST", "/connections", shop)
    cell: dict[str, Any] = {
        "cell_type": "code",
        "metadata": {},
        "source": f"%%sql {name}_shop\nSELECT 1",
        "outputs": [],
        "execution_count": None,
    }
    notebook = {"cells": [cell], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    Path(folder, "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    Path(folder, "load.py").write_text("print('made-up')\n", encoding="utf-8")
    return folder


def test_home_is_the_open_projects_summary(browser: Browser, server: dict[str, Any]) -> None:
    """With a project open Home is its summary (the owner, 2026-11-24): its name at the top, its table,
    notebook, script and the connection it uses each a link to where it lives; it follows a new file by
    itself; the window's title says the project on every page; the status bar's name leads back to it; New
    project goes to the projects page and Back returns; Close project shows the Project Explorer."""
    name = "made_up_captive"
    folder = made_up_project(server, name)
    page = open_page(browser, server, "")
    expect(page.locator(".summary-name")).to_have_text(name)
    expect(page.locator("h1.area-page-title")).to_contain_text(name)
    expect(page.locator("[data-fact=folder]")).to_contain_text(folder)
    expect(page).to_have_title(f"{name} · Swiss Army Bench")

    tables = page.locator("[data-section=tables]")
    table = tables.locator("a.summary-link", has_text=f"{name}_orders")
    expect(table).to_have_attribute("href", f"tables?table={name}_orders")
    expect(tables).to_contain_text("2 rows")
    documents = page.locator("[data-section=documents]")
    notebook = documents.locator("a.summary-link", has_text="analysis.ipynb")
    expect(notebook).to_have_attribute("href", re.compile(r"^notebooks\?path=.*analysis\.ipynb$"))
    script = documents.locator("a.summary-link", has_text="load.py")
    expect(script).to_have_attribute("href", re.compile(r"^scripts\?path=.*load\.py$"))
    used = page.locator("[data-section=connections] a.summary-link", has_text=f"{name}_shop")
    expect(used).to_have_attribute("href", f"connections?name={name}_shop")

    # Live: a notebook made outside shows up with no Refresh (the file_changed notice).
    empty = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    Path(folder, "later.ipynb").write_text(json.dumps(empty), encoding="utf-8")
    expect(documents.locator("a.summary-link", has_text="later.ipynb")).to_be_visible(timeout=30_000)

    # Another page: the window's title says the page and the project; the status bar's name goes back.
    table.click()
    expect(page).to_have_url(re.compile(r"/blazor/tables\?table="))
    expect(page).to_have_title(re.compile(rf" · {name} · Swiss Army Bench$"))
    page.locator(".status-project-name").click()
    expect(page.locator(".summary-name")).to_have_text(name)

    # New project: the projects page, its own view in the address; Back returns to the summary.
    page.locator(".summary-head").get_by_role("button", name="New project").click()
    expect(page).to_have_url(re.compile(r"\?view=projects$"))
    expect(page.locator("h1.area-page-title")).to_have_text("Projects")
    expect(page).to_have_title(f"Projects · {name} · Swiss Army Bench")
    expect(page.locator(".explorer-card", has_text=name)).to_be_visible()
    page.go_back()
    expect(page.locator(".summary-name")).to_have_text(name)

    call(server, "POST", "/project/save", {})
    page.locator(".summary-head").get_by_role("button", name="Close project").click()
    expect(page.locator("h1.area-page-title")).to_have_text("Projects")
    expect(page.locator(".status-project")).to_contain_text("No project open")
    expect(page).to_have_title("Projects · Swiss Army Bench")
    page.close()


def test_a_project_opened_on_the_projects_page_lands_on_its_summary(
    browser: Browser, server: dict[str, Any]
) -> None:
    """Open on a card of the projects page (?view=projects) with another project open: its summary."""
    other = call(server, "POST", "/project/new", {"name": "made_up_other_shop"})["project"]["folder"]
    call(server, "POST", "/project/new", {"name": "made_up_first_shop"})
    page = open_page(browser, server, "?view=projects")
    expect(page.locator("h1.area-page-title")).to_have_text("Projects")
    page.locator(".explorer-card", has_text="made_up_other_shop").click()
    expect(page.locator(".summary-name")).to_have_text("made_up_other_shop")
    expect(page).not_to_have_url(re.compile(r"view=projects"))
    expect(page).to_have_title("made_up_other_shop · Swiss Army Bench")
    assert call(server, "GET", "/project")["project"]["folder"] == other
    page.close()
