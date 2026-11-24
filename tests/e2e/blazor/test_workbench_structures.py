"""The Blazor Notebooks and Scripts pages, more of them on made-up data: a JSON file as a structure's tab
beside the code (the tree and the text, the search with Next, a node's menu and an edit of the file,
Transform's steps, Save), a script opened at a line and a notebook at a cell (?line=, ?cell=), a cell's
lineage, the Tables group's lines (their fold and Run), the Data Explorer pane, the status bar's Problems
list and F1's help."""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_a_structure_tab_beside_the_code(browser: Browser, server: dict[str, Any]) -> None:
    path = server["tmp"] / "workbench" / "made_up_orders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"orders": [{"id": 1, "city": "Northby"}, {"id": 2, "city": "Southby"}]}))
    page = open_page(browser, server, f"scripts?path={path}")
    doc = page.locator(".structure-doc")
    expect(doc.locator(".sd-tree")).to_contain_text("orders")
    doc.locator(".sd-search").fill("by")
    expect(doc.locator(".sd-count")).to_have_text("1 of 2")
    doc.locator(".sd-search").press("Enter")
    expect(doc.locator(".sd-count")).to_have_text("2 of 2")
    expect(doc.locator(".sd-path-text")).to_have_text("$.orders[1].city")
    doc.locator(".sd-search").press("Escape")
    expect(doc.locator(".sd-count")).to_have_text("")

    doc.locator(".tree-row", has_text="[0]").first.click(button="right")
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Move down")
    page.click(".context-menu [role=menuitem]:has-text('Duplicate')")
    expect(doc.locator(".tree-row", has_text="[2]")).to_be_visible()
    expect(doc.locator(".dirty-dot")).to_be_visible()

    doc.locator(".tree-row:has(.tree-key:text-is('orders'))").click()
    doc.locator(".sd-transform").click()
    page.click(".context-menu [role=menuitem]:has-text('Sort…')")
    dialog = page.locator(".dialog[aria-label='Sort…']")
    dialog.locator("select[aria-label=Order]").select_option("Largest first")
    dialog.locator("button:has-text('Sort')").last.click()
    expect(doc.locator(".structures-step")).to_have_count(1)
    doc.locator("button[aria-label='Remove step 1']").click()
    expect(doc.locator(".structures-step")).to_have_count(0)

    doc.locator(".sd-view-btn[data-view=both]").click()
    expect(doc.locator(".sd-text .monaco-editor")).to_be_visible()
    doc.locator(".ide-bar button:has-text('Save')").first.click()
    expect(doc.locator(".dirty-dot")).to_have_count(0)
    assert len(json.loads(path.read_text())["orders"]) == 3
    page.close()


def test_a_script_at_a_line_and_a_notebook_at_a_cell(browser: Browser, server: dict[str, Any]) -> None:
    script = server["tmp"] / "workbench" / "made_up_lines.py"
    script.write_text("".join(f"value_{n} = {n}\n" for n in range(1, 81)))
    page = open_page(browser, server, f"scripts?path={script}&line=60")
    expect(page.locator(".wb-script-editor .monaco-editor .view-lines")).to_contain_text("value_60")
    expect(page.locator(".wb-script-editor .monaco-editor .current-line").first).to_be_attached()
    page.close()

    notebook = str(server["tmp"] / "workbench" / "made_up_cells.ipynb")
    cells = [{"kind": "code", "source": f"cell_{n} = {n}", "number": n} for n in range(1, 13)]
    call(server, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 13})
    page = open_page(browser, server, f"notebooks?path={notebook}&cell=11")
    expect(page.locator(".wb-cell.selected")).to_contain_text("cell_11")
    page.close()


def test_a_cells_lineage_and_the_problems_list(browser: Browser, server: dict[str, Any]) -> None:
    notebook = str(server["tmp"] / "workbench" / "made_up_lineage.ipynb")
    cells = [
        {"kind": "code", "source": "base = 20", "number": 1},
        {"kind": "code", "source": "total = base * 2\nimport os", "number": 2},
    ]
    call(server, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 3})
    page = open_page(browser, server, f"notebooks?path={notebook}")
    second = page.locator(".wb-cell", has_text="total = base").first
    second.locator("button[aria-label='More actions']").click()
    page.click(".context-menu [role=menuitem]:has-text('Lineage')")
    lineage = page.locator(".wb-lineage[role=dialog]")
    expect(lineage.locator(".wb-lin-card").first).to_be_visible(timeout=30_000)
    expect(lineage).to_contain_text("total")
    page.keyboard.press("Escape")
    expect(lineage).to_have_count(0)

    page.locator(".wb-problems").click()
    expect(page.locator(".context-menu[aria-label=Problems]")).to_be_visible()
    page.keyboard.press("Escape")
    page.close()


def test_the_tables_group_and_the_data_explorer(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    path = str(server["tmp"] / "workbench" / "data.ipynb")
    call(server, "POST", "/workbench/save", {"path": path, "cells": [], "next_cell": 1})
    page = open_page(browser, server, f"notebooks?path={path}")
    heading = page.locator(".wb-table-line.role-tables")
    expect(heading).to_contain_text("Tables")
    table_line = page.locator(".wb-table-line.role-table").first
    expect(table_line.locator(".wb-run-table")).to_be_visible()
    before = page.locator(".wb-tcell", has_text="follows the Tables page").count()
    heading.locator(".wb-fold").click()
    expect(page.locator(".wb-tcell", has_text="follows the Tables page")).to_have_count(0)
    heading.locator(".wb-fold").click()
    expect(page.locator(".wb-tcell", has_text="follows the Tables page")).to_have_count(before)

    page.click(".wb-status button:has-text('Data Explorer')")
    explorer = page.locator(".wb-explorer")
    explorer.locator(".wb-explorer-search").fill("orders")
    expect(explorer.locator(".wb-explorer-row", has_text="orders").first).to_be_visible()
    explorer.locator("button:has-text('Table')").click()
    expect(page.locator(".context-menu")).to_contain_text("Open file…")
    page.keyboard.press("Escape")
    explorer.locator("button[aria-label='Close the Data Explorer']").click()
    expect(explorer).to_have_count(0)
    page.close()
