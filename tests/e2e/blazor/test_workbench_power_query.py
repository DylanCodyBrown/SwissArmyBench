"""Power Query files on the Scripts page (the owner, 2026-11-27: "Wish I had it as a supported language" / "I just
want a run button and the power query runs"), in the browser on made-up data: New file's Power Query type, a
query typed with its colours, F5 and the table open on the Tables page with its M read-only and Show as SQL; a
query that cannot run underlined before Run and its line said after; a file of several queries, each a table;
Import Power BI queries… from a made-up template."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, name_new_file, open_page


def folder_of(server: dict[str, Any]) -> Path:
    folder = Path(server["tmp"]) / "workbench"
    folder.mkdir(exist_ok=True)
    return folder


def type_m(page: Page, text: str) -> None:
    page.click(".wb-pq .monaco-editor .view-lines")
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(text)
    page.keyboard.press("Escape")


def test_new_file_power_query_typed_and_f5_opens_its_table(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    page.click(".context-menu [role=menuitem]:has-text('Power Query (.pq)')")
    dialog = page.locator(".dialog[aria-label='New Power Query']")
    expect(dialog.get_by_label("Name")).to_have_value("query.pq")
    name_new_file(page, "made_up_big_orders", folder_of(server))
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_big_orders.pq")
    # Its starter is a let ... in over an open table, coloured as M.
    lines = page.locator(".wb-pq .view-lines")
    expect(lines).to_contain_text("Table.SelectRows")
    expect(page.locator(".wb-pq .monaco-editor .mtk1 ~ span[class*='mtk']").first).to_be_visible()

    type_m(
        page,
        'let\n    Source = orders,\n    #"Big Orders" = Table.SelectRows(Source, each [amount] > 100)\nin\n    #"Big Orders"',
    )
    page.keyboard.press("Control+S")
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("")
    page.click(".wb-pq .monaco-editor .view-lines")
    page.keyboard.press("F5")
    expect(page).to_have_url(re.compile(r"/blazor/tables\?grid="), timeout=60_000)
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("made_up_big_orders")
    # Its M read-only here, with Show as SQL and Edit in Scripts.
    shown = page.locator(".pane .query-shown")
    expect(shown.locator(".query-shown-bar strong")).to_have_text("Power Query")
    expect(shown.locator(".query-shown-sql")).to_contain_text("Table.SelectRows(Source, each [amount] > 100)")
    shown.get_by_role("button", name="Show as SQL").click()
    expect(shown.locator(".query-shown-sql")).to_contain_text('WHERE (("amount" > 100))')
    shown.get_by_role("button", name="Edit in Scripts").click()
    expect(page).to_have_url(re.compile(r"/blazor/scripts\?path=.*made_up_big_orders\.pq"))
    page.close()


def test_a_query_that_cannot_run_is_underlined_and_says_its_line(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})
    file = folder_of(server) / "made_up_broken.pq"
    file.write_text(
        "let\n    Source = orders,\n    Wrong = Table.SelectRows(Source, each [made_up_nope] > 1)\nin\n    Wrong\n",
        encoding="utf-8",
    )
    page = open_page(browser, server, f"scripts?path={file}")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_broken.pq")
    # Underlined before any run: the problems are the server's, nothing was read.
    expect(page.locator(".wb-pq .monaco-editor .squiggly-error")).not_to_have_count(0, timeout=30_000)
    page.click(".wb-gcontrols button:has-text('Run file')")
    error = page.locator(".wb-sql-error")
    expect(error).to_contain_text("Line 3", timeout=60_000)
    expect(error).to_contain_text("made_up_nope is not a column here")
    expect(page).to_have_url(re.compile(r"/blazor/scripts\?path="))  # it stays here
    page.close()


def test_a_file_of_queries_builds_each_table_and_shows_its_sql(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})
    file = folder_of(server) / "made_up_shop.pq"
    file.write_text(
        "section Shop;\n\n"
        "shared Least = 100 meta [IsParameterQuery = true];\n\n"
        "shared made_up_big = Table.SelectRows(orders, each [amount] > Least);\n\n"
        'shared made_up_by_customer = Table.Group(made_up_big, {"customer_id"}, '
        '{{"total", each List.Sum([amount]), type number}});\n',
        encoding="utf-8",
    )
    page = open_page(browser, server, f"scripts?path={file}")
    page.click(".wb-gcontrols button:has-text('Show as SQL')")
    expect(page.locator(".wb-pq-sql-query pre").first).to_contain_text("SELECT", timeout=60_000)
    page.click(".wb-gcontrols button:has-text('Run file')")
    expect(page).to_have_url(re.compile(r"/blazor/tables\?grid="), timeout=60_000)
    tabs = page.locator(".grid-tab.tab-item")
    expect(tabs.filter(has_text="made_up_big")).not_to_have_count(0)
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("made_up_by_customer")
    page.close()


def test_import_power_bi_queries_makes_one_file_of_the_datasets_queries(
    browser: Browser, server: dict[str, Any]
) -> None:
    schema = {
        "model": {
            "tables": [
                {
                    "name": "Made Up Regions",
                    "partitions": [
                        {
                            "source": {
                                "type": "m",
                                "expression": [
                                    "let",
                                    '    Source = #table(type table [Region = text, Code = Int64.Type], {{"North", 1}, {"South", 2}})',
                                    "in",
                                    "    Source",
                                ],
                            }
                        }
                    ],
                },
                {
                    "name": "Made Up Orders",
                    "partitions": [
                        {
                            "source": {
                                "type": "m",
                                "expression": 'let\n    Source = Sql.Database(Server, "Sales"),\n    T = Source{[Schema="dbo",Item="Orders"]}[Data]\nin\n    T',
                            }
                        }
                    ],
                },
            ],
            "expressions": [
                {
                    "name": "Server",
                    "kind": "m",
                    "expression": '"made-up-sql.example" meta [IsParameterQuery=true, Type="Text"]',
                }
            ],
        }
    }
    template = folder_of(server) / "MadeUpSales.pbit"
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("DataModelSchema", json.dumps(schema).encode("utf-16-le"))
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    page.click(".context-menu [role=menuitem]:has-text('Import Power BI queries')")
    dialog = page.locator(".dialog.new-file")
    dialog.get_by_label("From the file").fill(str(template))
    name_new_file(page, "made_up_dataset", folder_of(server))
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_dataset.pq")
    lines = page.locator(".wb-pq .view-lines")
    expect(lines).to_contain_text("section MadeUpSales;")
    expect(lines).to_contain_text('shared #"Made Up Regions" = let')
    # The database's query has no saved connection here: said under it before any run.
    expect(page.locator(".wb-pq .monaco-editor .squiggly-error")).not_to_have_count(0, timeout=30_000)
    text = (folder_of(server) / "made_up_dataset.pq").read_text(encoding="utf-8")
    assert 'shared Server = "made-up-sql.example" meta' in text and 'shared #"Made Up Orders" = let' in text
    page.close()
