"""The screen state in the browser (the owner, 2026-11-27): every window keeps the server told of what it
shows, and `app_screen` (GET /screen) answers from the server's memory within a second of the change: the
Tables page's table in front with its sort and selection, a script's cursor line, an open dialog's title; two
windows told apart, a closed one gone. Names only: a cell's value and a script's text never reach it. Made-up
data only."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Browser, ViewportSize, expect

from tests.e2e.blazor.conftest import call, open_page

WIDE: ViewportSize = {"width": 1900, "height": 900}
# "app_screen says so within a second".
WITHIN_SECONDS = 1.0
# A made-up string that is only ever in a script's text.
ONLY_IN_THE_CODE = "larkfield_marker_4417"


def orders(server: dict[str, Any]) -> str:
    made = call(server, "POST", "/samples/store", {})
    return str(next(t["grid"] for t in made["tables"] if t["name"].startswith("orders")))


def said(
    server: dict[str, Any],
    window: str,
    holds: Callable[[dict[str, Any]], bool],
    within: float = WITHIN_SECONDS,
) -> dict[str, Any]:
    """`app_screen(window)` as the agent reads it, once `holds` is true of it: asked again until `within`
    seconds have passed (each ask is answered from memory at once)."""
    deadline = time.monotonic() + within
    while True:
        try:
            state: dict[str, Any] = call(server, "GET", f"/screen/{window}" if window else "/screen")
        except OSError:  # no such window yet (404)
            state = {}
        if state and holds(state):
            return state
        assert time.monotonic() < deadline, (
            f"app_screen did not say so within {within} s: {json.dumps(state)}"
        )
        time.sleep(0.05)


def test_the_tables_page_says_its_table_sort_and_selection(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders(server)
    page = open_page(browser, server, f"tables?grid={grid}")
    page.set_viewport_size(WIDE)
    expect(page.locator(".ag-row[row-index='0'] .ag-cell[col-id=status]")).not_to_have_text("")
    # The first report after the page's load may take the load's time; every change after it, a second.
    opened = said(server, "tables", lambda s: s.get("table", {}).get("showing", {}).get("first") == 1, 15)
    assert opened["kind"] == "tables" and opened["page"] == "tables" and opened["reported"] is True
    assert opened["address"] == f"tables?grid={grid}" and opened["width"] == WIDE["width"]
    table = opened["table"]
    assert table["grid"] == grid and table["name"].startswith("orders") and table["rows"] > 0
    names = [c["name"] for c in table["columns"]]
    assert {"status", "amount"} <= set(names) and "sort" not in table

    # Sort: the column's header, then the Column row's Sort descending.
    page.click(".ag-header-cell[col-id=amount] .sab-header-name")
    page.click("[data-tool=col-sort-desc]")
    expect(page.locator(".steps-strip")).to_contain_text("Sort by amount descending")
    sorted_now = said(server, "tables", lambda s: bool(s["table"].get("sort")))
    assert sorted_now["table"]["sort"] == [{"column": "amount", "direction": "descending"}]
    assert sorted_now["table"]["steps"][-1].endswith("Sort by amount descending")

    # Select: one cell, by its row and column number.
    cell = page.locator(".ag-row[row-index='2'] .ag-cell[col-id=status]")
    expect(cell).not_to_have_text("")  # the rows read again after the sort
    value = cell.inner_text().strip()
    cell.click()
    expect(cell).to_have_class(re.compile("cell-selected"))
    picked = said(server, "tables", lambda s: s["table"].get("selection", {}).get("kind") == "cells")
    selection = picked["table"]["selection"]
    assert selection["rows"] == [{"first": 3, "last": 3}] and selection["columns"] == ["status"]
    assert selection["column_numbers"] == [names.index("status") + 1]

    # Names only: the cell's own value is nowhere in what the agent reads, in full or in brief.
    assert value and value not in json.dumps(picked)
    brief = call(server, "GET", "/screen")
    assert value not in json.dumps(brief)
    assert "sorted by amount descending" in brief["windows"][0]["shows"]
    page.close()


def test_a_dialog_says_its_title(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders(server)
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ribbon")).to_contain_text("Table")
    said(server, "tables", lambda s: "table" in s, 15)
    page.click("[data-tool=limit]")
    expect(page.locator(".dialog")).to_contain_text("Add step: Keep first rows")
    opened = said(server, "tables", lambda s: bool(s.get("dialogs")))
    assert opened["dialogs"] == ["Add step: Keep first rows"]
    assert "dialog Add step: Keep first rows" in call(server, "GET", "/screen")["windows"][0]["shows"]
    page.keyboard.press("Escape")
    expect(page.locator(".dialog")).to_have_count(0)
    said(server, "tables", lambda s: "dialogs" not in s)
    page.close()


def test_a_script_says_its_cursors_line(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_screen.py")
    text = f"first = 1\nsecond = 2\nthird = '{ONLY_IN_THE_CODE}'\nfourth = 4\nfifth = 5\n"
    call(server, "POST", "/workbench/save", {"path": path, "text": text})
    page = open_page(browser, server, f"scripts?path={path}")
    editor = page.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible()
    editor.locator(".view-line", has_text="first = 1").click()
    page.keyboard.press("Control+Home")
    opened = said(server, "scripts", lambda s: s.get("cursor", {}).get("line") == 1, 15)
    assert opened["kind"] == "scripts"
    assert opened["tab"] == {"title": "made_up_screen.py", "path": path, "kind": "script", "dirty": False}
    assert opened["script"]["language"] == "python" and "Files" in opened["panes"]

    for _ in range(3):
        page.keyboard.press("ArrowDown")
    expect(page.locator(".monaco-editor .line-numbers.active-line-number")).to_have_text("4")
    moved = said(server, "scripts", lambda s: s.get("cursor", {}).get("line") == 4)
    assert moved["cursor"] == {"line": 4, "column": 1} and "selection" not in moved

    # Two lines selected: the range, never the text.
    page.keyboard.press("Shift+ArrowDown")
    ranged = said(server, "scripts", lambda s: "selection" in s)
    assert ranged["selection"] == {"from_line": 4, "to_line": 5}
    assert ONLY_IN_THE_CODE not in json.dumps(ranged)
    assert "cursor at line 5" in call(server, "GET", "/screen")["windows"][0]["shows"]

    # Typing makes it unsaved: the tab says so.
    page.keyboard.press("End")
    page.keyboard.type("  # mine")
    assert said(server, "scripts", lambda s: s["tab"]["dirty"] is True, 3)["tab"]["path"] == path
    page.close()


def test_two_windows_are_told_apart_and_a_closed_one_is_gone(
    browser: Browser, server: dict[str, Any]
) -> None:
    grid = orders(server)
    said(server, "", lambda s: s["windows"] == [], 5)  # the tests before closed their windows
    tables = open_page(browser, server, f"tables?grid={grid}")
    settings = open_page(browser, server, "settings")
    both = said(server, "", lambda s: len(s["windows"]) == 2 and all(w["reported"] for w in s["windows"]), 15)
    by_kind = {w["kind"]: w for w in both["windows"]}
    assert set(by_kind) == {"tables", "settings"} and by_kind["tables"]["id"] != by_kind["settings"]["id"]
    assert by_kind["tables"]["shows"].startswith("table orders")
    full = said(server, "settings", lambda s: "sections" in s.get("settings", {}), 5)
    assert "Theme" in full["settings"]["sections"] and full["settings"]["section"] == "Theme"
    assert "table" not in full
    assert call(server, "GET", f"/screen/{by_kind['tables']['id']}")["table"]["grid"] == grid

    settings.close()
    one = said(server, "", lambda s: len(s["windows"]) == 1)
    assert one["windows"][0]["kind"] == "tables"
    tables.close()
    said(server, "", lambda s: s["windows"] == [] and "note" in s)


def test_a_notebook_and_the_canvas_say_their_own_parts(browser: Browser, server: dict[str, Any]) -> None:
    from tests.e2e.blazor.test_canvas import draw_container, made_up_canvas, open_canvas

    notebook = str(server["tmp"] / "workbench" / "made_up_screen.ipynb")
    cells = [
        {"kind": "code", "source": f"x = '{ONLY_IN_THE_CODE}'", "number": 1, "name": "load"},
        {"kind": "markdown", "source": "# A made-up heading", "number": 2},
        {"kind": "sql", "source": "select 1", "number": 3},
    ]
    call(server, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 4})
    page = open_page(browser, server, f"notebooks?path={notebook}")
    page.locator("section.wb-cell[data-number='3'] .monaco-editor").click()
    shown = said(server, "notebooks", lambda s: s.get("notebook", {}).get("focused") == 3, 15)
    assert shown["tab"]["kind"] == "notebook" and shown["tab"]["path"] == notebook
    assert shown["notebook"]["cells"] == 3
    assert [(c["number"], c["kind"], c["state"]) for c in shown["notebook"]["visible"]] == [
        (1, "code", "not run"),
        (2, "markdown", "not run"),
        (3, "sql", "not run"),
    ]
    assert shown["notebook"]["visible"][0]["name"] == "load"
    assert ONLY_IN_THE_CODE not in json.dumps(shown) and "made-up heading" not in json.dumps(shown)
    page.close()

    path = made_up_canvas(server, "Screen")
    canvas = open_canvas(browser, server, path)
    opened = said(server, "canvas", lambda s: s.get("canvas", {}).get("path") == path, 15)
    assert opened["canvas"]["layout"] == "desktop" and opened["canvas"]["full_screen"] is False
    assert opened["canvas"]["page"] in opened["canvas"]["pages"] and opened["project"] == "Screen"
    draw_container(canvas, 60, 60, 420, 260)
    expect(canvas.locator(".cvs-container")).to_have_count(1)
    drawn = said(server, "canvas", lambda s: s["canvas"].get("items") == 1, 3)
    assert [item["kind"] for item in drawn["canvas"].get("selection", [])] in ([], ["container"])
    canvas.close()
