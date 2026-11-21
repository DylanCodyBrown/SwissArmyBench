# ruff: noqa: F811
"""A variable in any box of the app (12.7; the owner, 2026-11-19: "a right click and insert env var menu and a
auto complete when ${ is typed anywhere"), in a browser: typing a dollar-brace in a plain box on two pages
(the main page, the blades page) lists the variables and puts the pick in; right-click, Insert variable… does
the same; a SQL cell's editor offers them after a dollar-brace; a Python cell and a list's search box do not.
Made-up names and values only."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import add_cell, open_workbench, start

NAME = "SHOP_REGION"
REFERENCE = "${" + NAME + "}"


@pytest.fixture
def region(server: dict[str, Any]) -> Iterator[str]:
    call(server, "PUT", "/variables", {"name": NAME, "value": "North", "from": "value"})
    yield NAME
    call(server, "DELETE", f"/variables/{NAME}")


def floating(page: Page) -> Any:
    return page.locator(".variable-float")


def test_typing_a_dollar_brace_or_right_clicking_any_box_inserts_a_variable(
    browser: Browser, orders_url: str, region: str
) -> None:
    page = open_grid(browser, orders_url)
    page.locator('.nav-rail [data-area="variables"]').click()
    variables = page.locator('.area-page[data-page="variables"]')
    # A list's search box: no list.
    search = variables.get_by_label("Search variables")
    search.press_sequentially("${")
    page.wait_for_timeout(300)
    expect(floating(page)).to_have_count(0)
    search.fill("")
    # A plain box: typing a dollar-brace lists the variables, the name and its source, filtered as typed.
    variables.get_by_role("button", name="Add variable").click()
    value = variables.locator(".variables-form").get_by_label("Value")
    value.press_sequentially("eu-${SHOP")
    offered = page.get_by_role("listbox", name="Variables")
    expect(offered.get_by_role("option").first).to_have_text(f"{NAME}Plain value")
    expect(offered.get_by_role("option").last).to_have_text("New variable SHOP…")
    value.press("Enter")
    expect(value).to_have_value("eu-" + REFERENCE)
    expect(floating(page)).to_have_count(0)
    # Right-click: the app's menu (Cut, Copy, Paste, Insert variable…); the pick goes in at the caret.
    value.fill("")
    value.click(button="right")
    menu = page.locator(".context-menu")
    items = menu.get_by_role("menuitem")
    expect(items.nth(3)).to_have_text("Insert variable…")  # (beta mode adds Leave a note… after)
    assert items.all_inner_texts()[:4] == ["Cut", "Copy", "Paste", "Insert variable…"]
    menu.get_by_role("menuitem", name="Insert variable…").click()
    offered.get_by_role("option", name=f"{NAME} Plain value").click()
    expect(value).to_have_value(REFERENCE)
    # The keyboard's way to the same menu: Shift+F10; a selection is replaced.
    value.fill("eu-north")
    value.evaluate("box => box.setSelectionRange(3, 8)")
    value.press("Shift+F10")
    menu.get_by_role("menuitem", name="Insert variable…").click()
    offered.get_by_role("option", name=f"{NAME} Plain value").click()
    expect(value).to_have_value("eu-" + REFERENCE)
    page.close()


def test_the_blades_page_takes_one_too(browser: Browser, server: dict[str, Any], region: str) -> None:
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}")
    page.wait_for_selector(".blade-list")
    try:
        page.get_by_role("button", name="New blade").first.click()
        dialog = page.get_by_role("dialog", name="New blade")
        dialog.get_by_label("Name").fill("New table")
        dialog.get_by_role("button", name="Create").click()  # a new scaffold: Properties open by itself
        field = page.get_by_label("Its table is called")
        field.press_sequentially("${SHOP_R")
        expect(page.get_by_role("listbox", name="Variables").get_by_role("option").first).to_contain_text(
            NAME
        )
        field.press("Tab")
        expect(field).to_have_value(REFERENCE)
    finally:
        for blade in call(server, "GET", "/blades")["blades"]:
            if blade["name"] == "New table":
                call(server, "DELETE", "/blades/New%20table")
        page.close()


def test_a_sql_cell_offers_the_variables_and_a_python_cell_does_not(
    browser: Browser, orders_url: str, region: str
) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    try:
        start(workbench)
        python = workbench.locator(".wb-cell").first
        expect(python.locator(".monaco-editor")).to_be_visible(timeout=20000)
        python.locator(".monaco-editor").click()
        workbench.keyboard.type("x = '${SHOP")
        workbench.wait_for_timeout(600)
        expect(floating(workbench)).to_have_count(0)
        expect(workbench.locator(".suggest-widget .monaco-list-row", has_text=NAME)).to_have_count(0)
        add_cell(workbench, "SQL")
        sql = workbench.locator(".wb-cell").nth(1)
        expect(sql.locator(".monaco-editor")).to_be_visible(timeout=20000)
        sql.locator(".monaco-editor").click()
        workbench.keyboard.type("SELECT * FROM orders WHERE region = ${SHOP")
        row = workbench.locator(".suggest-widget .monaco-list-row", has_text=NAME)
        expect(row).to_be_visible(timeout=10000)
        workbench.keyboard.press("Enter")
        expect(sql.locator(".view-lines")).to_contain_text("region = " + REFERENCE)
        expect(floating(workbench)).to_have_count(0)
    finally:
        workbench.close()


def test_a_vault_saved_after_the_page_opened_offers_its_variables_at_once(
    browser: Browser, orders_url: str, server: dict[str, Any], region: str
) -> None:
    """The owner (2026-11-19): "I added my vault and mapped variables and I can't use them anywhere with a
    dollar-brace, they don't show up": the list was read once per window and never again. Now a vault saved
    anywhere shows in an open window's list, and the boxes have no {x} button any more."""
    page = open_grid(browser, orders_url)
    page.locator('.nav-rail [data-area="variables"]').click()
    variables = page.locator('.area-page[data-page="variables"]')
    variables.get_by_role("button", name="Add variable").click()
    value = variables.locator(".variables-form").get_by_label("Value")
    expect(variables.locator(".variable-insert")).to_have_count(0)
    # The list read once (the plain variable only)...
    value.press_sequentially("${")
    offered = page.get_by_role("listbox", name="Variables")
    expect(offered.get_by_role("option", name=f"{NAME} Plain value")).to_be_visible()
    value.fill("")
    # ...then a vault is saved elsewhere (here: by the API, as another window would).
    vault = {
        "name": "Made-up vault",
        "kind": "vault",
        "code": "def get(name):\n    return 'made-up'",
        "variable": "get",
        "vault_mapping": [{"env": "SHOP_VAULT_KEY", "secret": "shop-vault-key"}],
    }
    call(server, "POST", "/blades", vault)
    try:
        value.press_sequentially("${SHOP_V")
        expect(offered.get_by_role("option").first).to_contain_text("SHOP_VAULT_KEY")
        expect(offered.get_by_role("option").first).to_contain_text("Made-up vault")
    finally:
        call(server, "DELETE", "/blades/Made-up%20vault")
        page.close()
