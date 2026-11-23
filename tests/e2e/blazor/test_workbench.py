"""The Blazor Notebooks and Scripts pages on made-up data: a notebook opened from its address, a Python cell
typed in Monaco and run in the Python session (its output as it arrives, its run number), a SQL cell over an
open table, Save; the Tables group's read-only cells; a script's Run file and the console's line; Save as
through the app's own typed path; the Files pane; a blade's line inserted from the Blades pane."""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page


def made_up_notebook(server: dict[str, Any], name: str) -> str:
    path = str(server["tmp"] / "workbench" / name)
    cells = [{"kind": "markdown", "source": "# Made-up sums", "number": 1}]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 2})
    return path


def type_in_new_cell(page: Page, kind: str, code: str) -> None:
    page.click(".wb-gcontrols button[aria-label='Add cell']")
    page.click(f".context-menu [role=menuitem]:has-text('{kind}')")
    page.locator(".wb-cell.selected .monaco-editor").last.wait_for()
    page.wait_for_timeout(300)  # the editor takes the focus once Monaco is made
    page.keyboard.type(code)


def test_a_notebook_cell_runs_and_the_notebook_saves(browser: Browser, server: dict[str, Any]) -> None:
    path = made_up_notebook(server, "sums.ipynb")
    page = open_page(browser, server, f"notebooks?path={path}")
    expect(page.locator(".wb-doc-title")).to_contain_text("sums.ipynb")
    expect(page.locator(".wb-cell .wb-markdown")).to_contain_text("Made-up sums")

    type_in_new_cell(page, "Python", "total = 6 * 7\nprint('made up', total)\ntotal")
    page.keyboard.press("Shift+Enter")
    first = page.locator(".wb-cell").nth(1)
    expect(first.locator(".wb-outputs")).to_contain_text("made up 42", timeout=60_000)
    expect(first.locator(".wb-outputs")).to_contain_text("42")
    expect(first.locator(".wb-cell-number")).to_have_text("[1]")
    expect(page.locator(".wb-session")).to_contain_text("Ready")
    expect(page.locator(".wb-doc-title .dirty-dot")).to_be_visible()

    page.click(".wb-doc-bar button:has-text('Save')")
    expect(page.locator(".wb-doc-title .dirty-dot")).to_have_count(0)
    saved = json.loads((server["tmp"] / "workbench" / "sums.ipynb").read_text())
    sources = ["".join(c["source"]) for c in saved["cells"]]
    assert "total = 6 * 7\nprint('made up', total)\ntotal" in sources
    page.close()


def test_a_sql_cell_and_the_tables_group(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    path = made_up_notebook(server, "data.ipynb")  # a data.ipynb holds the tables no document made
    page = open_page(browser, server, f"notebooks?path={path}")
    expect(page.locator(".wb-tcell", has_text="follows the grid").first).to_be_visible()
    table_cell = page.locator(".wb-tcell", has_text="follows the grid").first
    expect(table_cell.locator(".wb-cell-kind")).to_have_count(0)  # the app's cell: no kind to change

    type_in_new_cell(page, "SQL", "select count(*) as order_count from orders")
    page.keyboard.press("Control+Enter")
    sql = page.locator(".wb-cell.kind-sql")
    expect(sql.locator(".wb-cell-number")).not_to_have_text("[ ]", timeout=60_000)
    frame = sql.frame_locator("iframe.wb-html")
    expect(frame.locator("table")).to_contain_text("order_count")
    page.close()


def test_a_script_runs_its_file_and_a_console_line(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "scripts?new=1")
    expect(page.locator(".wb-doc-title")).to_contain_text("Untitled script")
    page.click(".wb-script-editor .monaco-editor .view-lines")
    page.keyboard.type("answer = 6 * 7\nprint('made up script', answer)\n")
    page.click("button:has-text('Run file')")
    expect(page.locator(".wb-console-body")).to_contain_text("made up script 42", timeout=60_000)

    page.fill(".wb-console-line input", "answer + 1")
    page.keyboard.press("Enter")
    expect(page.locator(".wb-console-body")).to_contain_text("43")

    # Save as: the page's own picker (no system dialog in a test).
    (server["tmp"] / "workbench").mkdir(exist_ok=True)
    page.click("button:has-text('Save as')")
    choose_path(page, server["tmp"] / "workbench" / "made_up_script", save=True)
    expect(page.locator(".wb-doc-title")).to_contain_text("made_up_script.py")
    assert "made up script" in (server["tmp"] / "workbench" / "made_up_script.py").read_text()
    page.close()


def test_the_blades_pane_inserts_a_line(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "scripts?new=1")
    page.click(".wb-status button:has-text('Blades')")
    pane = page.locator(".blades-pane")
    expect(pane).to_be_visible()
    pane.locator("input[type=search]").fill("Excel")
    first = pane.locator(".blade-item").first
    expect(first).to_be_visible()
    name = first.locator(".blade-name").inner_text()
    first.locator("button[aria-label^=Insert]").click()
    expect(page.locator(".wb-script-editor .view-lines")).to_contain_text(name.split(" ")[0])
    expect(page.locator(".files-pane")).to_be_visible()
    page.close()
