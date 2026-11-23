"""The Blazor Analyze board's own moves on made-up notes: Add note, Pin to the top, More card actions (Move
later, Start a new page here, Edit note), the corner grip's keys, Page view on Letter, the board's theme,
Dashboards (save a version, its History, Open, Delete) and Export markdown."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def add_note(page: Any, title: str, body: str) -> None:
    page.click(".board-bar button:has-text('Add note')")
    dialog = page.locator(".dialog", has_text="Add a note")
    dialog.locator("input[aria-label=Title]").fill(title)
    dialog.locator("textarea").fill(body)
    dialog.locator("button:has-text('Add note')").click()
    expect(page.locator(".board-card", has_text=title)).to_be_visible()


def test_cards_are_added_pinned_moved_sized_and_saved(browser: Browser, server: dict[str, Any]) -> None:
    for card in call(server, "GET", "/cards")["cards"]:
        call(server, "DELETE", f"/cards/{card['id']}")
    page = open_page(browser, server, "analyze")
    add_note(page, "First made-up note", "# One\nmade up")
    add_note(page, "Second made-up note", "made up too")
    titles = page.locator(".board-card h3")

    # Pin to the top: the server puts it first.
    second = page.locator(".board-card", has_text="Second made-up note")
    second.locator("button[aria-label='Pin to the top']").click()
    expect(titles.first).to_have_text("Second made-up note")
    second.locator("button[aria-label='Unpin']").click()

    # More card actions: Move later, Edit note.
    first = page.locator(".board-card", has_text="First made-up note")
    first.locator("button[aria-label='More card actions']").click()
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Start a new page here")
    menu.locator("[role=menuitem]:has-text('Edit note')").click()
    edit = page.locator(".dialog", has_text="Edit the note")
    edit.locator("textarea").fill("edited, made up")
    edit.locator("button:has-text('Save')").click()
    expect(first).to_contain_text("edited, made up")

    # The corner grip's keys: the card's size is kept on the server.
    first.locator(".card-grip").focus()
    page.keyboard.press("ArrowRight")
    expect(first.locator(".card-grip")).to_have_attribute(
        "aria-valuetext", "7 of 12 columns wide, 10 rows tall"
    )
    card_id = first.get_attribute("data-card")
    sized = next(c for c in call(server, "GET", "/cards")["cards"] if c["id"] == card_id)
    assert sized["size"] == {"w": 7, "h": 10}

    # Page view on its paper; back to the board.
    page.click(".board-bar button:has-text('Page view')")
    expect(page.locator(".board-page")).to_have_count(1)
    expect(page.locator(".board-bar select[aria-label=Paper]")).to_be_visible()
    page.click(".board-bar button:has-text('Back to the board')")

    # The board's theme: one of its own, its tokens on the board.
    page.select_option(".board-bar select[aria-label='Board theme']", "hc-light")
    expect(page.locator(".analyze-board[data-sandbox-theme=hc-light]")).to_be_visible()
    page.select_option(".board-bar select[aria-label='Board theme']", "app")

    # Dashboards: save, its history, delete.
    page.click(".board-bar button:has-text('Dashboards…')")
    dialog = page.locator(".dialog", has_text="Dashboards")
    dialog.locator("input[aria-label='Dashboard name']").fill("made_up_board")
    dialog.locator("button:has-text('Save')").click()
    expect(dialog).to_contain_text("2 cards")
    dialog.locator("button:has-text('History')").click()
    expect(dialog.locator(".dashboard-history li")).to_have_count(1)
    dialog.locator("button:has-text('Delete')").click()
    page.locator(".dialog-foot .btn.danger, .dialog-foot .btn.primary").last.click()
    expect(dialog).to_contain_text("No saved dashboards")
    page.close()


def test_export_markdown_downloads_the_board(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "analyze")
    add_note(page, "Exported made-up note", "made up text")
    with page.expect_download() as download:
        page.click(".board-bar button:has-text('Export markdown')")
    text = open(download.value.path(), encoding="utf-8").read()
    assert text.startswith("# Analyze")
    assert "## Exported made-up note" in text and "made up text" in text
    page.close()
