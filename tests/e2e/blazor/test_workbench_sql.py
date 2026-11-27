""".sql files on the Scripts page and a tab's Rename… (the owner, 2026-11-24: "we should allow
renaming here" / "also we should allow .sql files" / "clicking the + in grids menu jumps to the
scripts page with an open script" / "then when you run the file, it adds the table and opens the
grid back on the grid menu"), on made-up data: the Tables page's "+" opens a new SQL file, its
Rename… names and saves it, Run file builds the table named after the file and lands on its tab; a
failure marks its line; a saved file renamed with F2; a query's table's Edit in Scripts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, name_new_file, open_page


def folder_of(server: dict[str, Any]) -> Path:
    folder = Path(server["tmp"]) / "workbench"
    folder.mkdir(exist_ok=True)
    return folder


def type_sql(page: Page, text: str) -> None:
    page.click(".wb-sql .monaco-editor .view-lines")
    page.keyboard.press("Control+A")
    page.keyboard.type(text)
    page.keyboard.press("Escape")  # a suggestion list closed


def test_the_plus_opens_a_sql_file_whose_run_lands_on_the_tables_page(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "tables")
    page.click("a.new-tab[aria-label='New query']")
    # The "+" asks the new SQL file's name on the Scripts page (the one New file dialog): no untitled tab.
    expect(page).to_have_url(re.compile(r"/blazor/scripts"))
    dialog = page.locator(".dialog[aria-label='New SQL file']")
    expect(dialog.get_by_label("Query from")).to_have_value("")  # Open tables (DuckDB)
    expect(page.locator(".wb-tab")).to_have_count(0)  # nothing is made until it is named
    name_new_file(page, "made_up_big_orders", folder_of(server))
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_big_orders.sql")
    expect(page.get_by_label("Query from")).to_have_value("")

    type_sql(page, "SELECT * FROM orders WHERE amount > 100")
    page.keyboard.press("Control+S")
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("")
    assert "amount > 100" in (folder_of(server) / "made_up_big_orders.sql").read_text()

    page.click(".wb-gcontrols button:has-text('Run file')")
    expect(page).to_have_url(re.compile(r"/blazor/tables\?grid="), timeout=60_000)
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("made_up_big_orders")
    # Its query read-only here, with Edit in Scripts: SQL is written only on the Scripts page.
    shown = page.locator(".pane .query-shown")
    expect(shown.locator(".query-shown-sql")).to_contain_text("amount > 100")
    expect(page.locator(".pane .monaco-editor")).to_have_count(0)
    page.close()


def test_a_failure_marks_its_line(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    file = folder_of(server) / "made_up_broken.sql"
    file.write_text("SELECT\n  amount,\n  made_up_nope\nFROM orders\n")
    page = open_page(browser, server, f"scripts?path={file}")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_broken.sql")
    # Run at once, before the editor may have finished loading: the mark waits for it.
    page.click(".wb-gcontrols button:has-text('Run file')")
    error = page.locator(".wb-sql-error")
    expect(error).to_contain_text("Line 3", timeout=60_000)
    expect(error).to_contain_text("made_up_nope")
    expect(page.locator(".wb-sql .monaco-editor .squiggly-error")).not_to_have_count(0)
    expect(page).to_have_url(re.compile(r"/blazor/scripts\?path="))  # it stays here
    page.close()


def test_a_saved_tab_is_renamed_with_f2(browser: Browser, server: dict[str, Any]) -> None:
    file = folder_of(server) / "made_up_q.sql"
    file.write_text("SELECT 1 AS one\n")
    page = open_page(browser, server, f"scripts?path={file}")
    tab = page.locator(".wb-tab.active")
    expect(tab.locator(".tab-label")).to_have_text("made_up_q.sql")
    tab.focus()
    page.keyboard.press("F2")
    dialog = page.locator(".dialog", has_text="Rename made_up_q.sql to")
    dialog.locator("input.question-text").fill("made_up_renamed")
    dialog.get_by_role("button", name="Rename").click()
    expect(tab.locator(".tab-label")).to_have_text("made_up_renamed.sql")
    expect(page).to_have_url(re.compile(r"made_up_renamed\.sql"))
    assert (folder_of(server) / "made_up_renamed.sql").read_text() == "SELECT 1 AS one\n"
    assert not file.exists()
    page.close()


def test_a_query_tables_edit_in_scripts_opens_its_sql_file(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    query = {"sql": "SELECT * FROM orders WHERE amount < 50"}
    built = call(server, "POST", "/datasets/made_up_cheap/query", query)
    page = open_page(browser, server, f"tables?grid={built['grid']}")
    page.locator(".pane .query-shown").get_by_role("button", name="Edit in Scripts").click()
    expect(page).to_have_url(re.compile(r"/blazor/scripts\?path=.*made_up_cheap\.sql"))
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_cheap.sql")
    expect(page.get_by_label("Query from")).to_have_value("")
    expect(page.locator(".wb-sql .view-lines")).to_contain_text("amount < 50")
    page.close()
