"""The Blazor Environment page against the classic one's elements, on made-up data: the tabs and their
counts, the one search over every tab with its hint, the Columns menu, a row's menu and the viewer's
actions (Copy name, Rename by F2, Remove asked first), Clear…, Install a library…, the Settings and
secrets tab's pointer to the key vaults (on the Connections page) and Add a setting…; and the Structures
page a structure's row opens into: its steps (Filter…, Undo), the node's actions, Lineage, Save as…."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page


def note(page: Page, words: str) -> None:
    expect(page.locator(".note-corner").filter(has_text=words).first).to_be_visible()


def test_the_environments_tabs_search_and_rows(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "environment")
    expect(page.locator(".env-tab[data-kind=table]")).to_have_attribute("aria-selected", "true")
    expect(page.locator(".env-tab[data-kind=table] i")).not_to_have_text("0")
    # The search: a match in another tab is named in the hint.
    page.fill("input[aria-label='Search the environment']", "pandas")
    expect(page.locator(".env-hint")).to_contain_text("Also matches in Libraries")
    page.locator(".env-hint button[data-go=library]").click()
    expect(page.locator(".env-tab[data-kind=library]")).to_have_attribute("aria-selected", "true")
    expect(page.locator(".env-row[data-name=pandas] mark")).to_have_text("pandas")
    page.fill("input[aria-label='Search the environment']", "")
    page.locator(".env-tab[data-kind=table]").click()
    # The Columns menu hides a column (kept for the tab).
    page.click("button[aria-label=Columns]")
    page.locator(".context-menu [role=menuitem]", has_text="From").click()
    expect(page.locator(".env-head")).not_to_contain_text("From")
    page.click("button[aria-label=Columns]")
    page.locator(".context-menu [role=menuitem]", has_text="From").click()
    expect(page.locator(".env-head")).to_contain_text("From")
    # A row's menu and the viewer.
    row = page.locator(".env-row[data-name=orders]").first
    row.locator(".env-more").click()
    menu = page.locator(".context-menu[aria-label='Actions for orders']")
    expect(menu).to_contain_text("Open in Grids")
    menu.locator("[role=menuitem]", has_text="Copy name").click()
    note(page, "Copied its name.")
    row.click()
    page.keyboard.press("F2")
    rename = page.locator(".dialog[aria-label='Rename orders']")
    expect(rename.locator("input[aria-label='New name']")).to_have_value("orders")
    rename.locator("button:has-text('Cancel')").click()
    row.click()
    page.keyboard.press("Delete")
    remove = page.locator(".dialog[aria-label='Remove orders']")
    expect(remove).to_contain_text("its source is not touched")
    remove.locator("button:has-text('Cancel')").click()
    page.click("button:has-text('Clear…')")
    expect(page.locator(".dialog[aria-label='Clear the environment']")).to_contain_text(
        "Kept tables, settings and libraries stay."
    )
    page.locator(".dialog[aria-label='Clear the environment'] button:has-text('Cancel')").click()
    page.locator(".env-tab[data-kind=library]").click()
    page.click("button:has-text('Install a library…')")
    expect(
        page.locator(".dialog[aria-label='Install a library'] input[aria-label=Library]")
    ).to_have_attribute("placeholder", "polars")
    page.locator(".dialog[aria-label='Install a library'] button:has-text('Cancel')").click()
    page.locator(".env-tab[data-kind=setting]").click()
    # Key vaults live on the Connections page now (the owner, 2026-11-23): here only the pointer.
    expect(page.locator("button:has-text('Add key vault')")).to_have_count(0)
    expect(page.locator(".env-vaults-moved a[href='connections']")).to_have_text("Connections page")
    page.close()


def test_a_structures_steps_and_actions(browser: Browser, server: dict[str, Any]) -> None:
    made = call(
        server,
        "POST",
        "/structures/paste",
        {"text": '{"orders": [{"id": 1, "total": 2.5}, {"id": 2, "total": 9}]}', "name": "made_up_orders"},
    )
    page = open_page(browser, server, f"structures?id={made['id']}")
    tree = page.locator(".structure-tree")
    tree.locator(".structure-row[data-path='$.orders']").click()
    actions = page.locator(".structures-node-actions")
    for words in ("Pick", "Filter…", "Sort…", "Flatten", "Open as grid", "Make a sandbox variant", "Remove"):
        expect(actions.locator(f"button:has-text('{words}')")).to_be_visible()
    actions.locator("button:has-text('Filter…')").click()
    dialog = page.locator(".dialog[aria-label=Filter]")
    expect(dialog.locator("input[aria-label=Field]")).to_have_value("id")
    dialog.locator("select[aria-label=Test]").select_option(">")
    dialog.locator("input[aria-label=Value]").fill("1")
    dialog.locator(".dialog-foot button.primary").click()
    expect(page.locator(".structures-steps")).to_contain_text("id")
    page.click("button[aria-label=Undo]")
    expect(page.locator(".structures-steps")).to_contain_text("No steps")
    page.click("button:has-text('Lineage')")
    expect(page.locator(".dialog[aria-label='Lineage · made_up_orders']")).to_be_visible()
    page.locator(".dialog[aria-label='Lineage · made_up_orders'] button[aria-label=Close]").click()
    page.click("button:has-text('Save as…')")
    save = page.locator(".dialog[aria-label='Save as']")
    expect(save.locator("input[aria-label=Name]")).to_have_value("made_up_orders")
    save.locator("button:has-text('Cancel')").click()
    page.close()
