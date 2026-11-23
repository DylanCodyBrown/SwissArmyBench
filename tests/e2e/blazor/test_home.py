"""The Blazor front end's Home (the Projects page): New project made through its dialog and opened, its
card, Close project, Rename through the app's own dialog (an open project is refused, said in the one
error note), the search."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_new_project_from_the_dialog_then_its_card(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server)
    page.click("text=New project")
    page.fill(".new-project-name", "Quarter review")
    page.click(".dialog-foot >> text=Create")
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
    takes the path), then the file opens on the Grids page."""
    made_up = server["tmp"] / "made_up_targets_home.csv"
    made_up.write_text("region,target\nNorth,10\nSouth,20\n", encoding="utf-8")
    page = open_page(browser, server, "")
    page.get_by_role("button", name="Open a file…").click()
    page.fill(".question-text", str(made_up))
    page.locator(".dialog-foot").get_by_role("button", name="Choose").click()
    expect(page.locator(".grid-tab.tab-item", has_text="made_up_targets_home")).to_be_visible()
    assert any(g["dataset"] == "made_up_targets_home" for g in call(server, "GET", "/grids")["grids"])
    page.close()


def test_paste_data_and_a_cards_menu(browser: Browser, server: dict[str, Any]) -> None:
    """Paste data (a pasted table opens at once on the Grids page) and a project card's menu (the classic
    projectExplorer.ts: Open, Show in folder, Copy project to…, Rename, Remove from list, Delete…)."""
    call(server, "POST", "/project/new", {"name": "made_up_menu_shop"})
    page = open_page(browser, server, "")
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
    page.fill(".question-text", str(plain))
    page.locator(".dialog-foot").get_by_role("button", name="Choose").click()
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
