"""The Blazor Notebooks and Scripts pages' tabs and commands on made-up data: two documents as tabs, Split right
into a second group, a tab closed (asked first when unsaved), the command palette (Ctrl+Shift+P) running a cell
command, a cell's More actions menu, and an HTML cell drawn as its design in its walled-off frame."""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def made_up(server: dict[str, Any], name: str, source: str) -> str:
    path = str(server["tmp"] / "workbench" / name)
    cells = [{"kind": "code", "source": source, "number": 1}]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 2})
    return path


def test_documents_are_tabs_that_split_and_close(browser: Browser, server: dict[str, Any]) -> None:
    first = made_up(server, "first.ipynb", "a = 1")
    second = made_up(server, "second.ipynb", "b = 2")
    page = open_page(browser, server, f"notebooks?path={first}")
    expect(page.locator(".wb-tab.active")).to_contain_text("first.ipynb")

    page.click("button:has-text('Open…')")
    page.fill(".dialog input", second)
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".wb-tab")).to_have_count(2)
    expect(page.locator(".wb-tab.active")).to_contain_text("second.ipynb")
    assert "second.ipynb" in page.url

    # A click on a tab brings it to the front, its cells as they were.
    page.locator(".wb-tab", has_text="first.ipynb").click()
    expect(page.locator(".wb-doc-title")).to_contain_text("first.ipynb")

    # Split right: the tab moves to a new group beside its own.
    page.click(".wb-group.focused button[aria-label='Document menu']")
    page.click(".context-menu [role=menuitem]:has-text('Split right')")
    expect(page.locator(".wb-group")).to_have_count(2)
    expect(page.locator(".wb-gsash")).to_have_count(1)

    # A tab whose group has only it cannot split: greyed out with its reason.
    page.click(".wb-group.focused button[aria-label='Document menu']")
    split = page.locator(".context-menu [role=menuitem]:has-text('Split right')")
    expect(split).to_be_disabled()
    expect(split).to_have_attribute("title", "its group has only this tab: open another first")
    page.keyboard.press("Escape")
    page.locator(".menu-shade").click()

    # An unsaved document asks before it closes; closing its group's last tab takes the group away.
    page.click(".wb-group.focused button[aria-label='Add cell']")
    page.click(".context-menu [role=menuitem]:has-text('Python')")
    expect(page.locator(".wb-group.focused .wb-tab-dirty")).to_have_text("●")
    page.click(".wb-group.focused .tab-close")
    expect(page.locator(".dialog")).to_contain_text("has changes that are not saved. Close it anyway?")
    page.click(".dialog-foot .btn.danger, .dialog-foot .btn.primary")
    expect(page.locator(".wb-group")).to_have_count(1)
    expect(page.locator(".wb-tab")).to_have_count(1)
    page.close()


def test_the_palette_and_a_cells_menu(browser: Browser, server: dict[str, Any]) -> None:
    path = made_up(server, "palette.ipynb", "x = 6 * 7")
    page = open_page(browser, server, f"notebooks?path={path}")
    page.locator(".wb-cell").first.click()
    page.keyboard.press("Control+Shift+P")
    palette = page.locator(".palette")
    expect(palette).to_be_visible()
    palette.locator("input").fill("insert below")
    expect(palette.locator(".palette-item")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(palette).to_have_count(0)
    expect(page.locator(".wb-cell")).to_have_count(2)

    # A cell's More actions: its menu, Duplicate among it.
    page.locator(".wb-cell").first.locator("button[aria-label='More actions']").click()
    menu = page.locator(".context-menu")
    expect(menu).to_contain_text("Run this cell and the ones below")
    menu.locator("[role=menuitem]:has-text('Duplicate')").click()
    expect(page.locator(".wb-cell")).to_have_count(3)
    page.close()


def test_an_html_cell_draws_its_design(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "design.ipynb")
    cells = [{"kind": "html", "source": "<h2 id='made-up'>Made-up design</h2>", "number": 1}]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 2})
    page = open_page(browser, server, f"notebooks?path={path}")
    cell = page.locator(".wb-cell.kind-html")
    frame = cell.frame_locator("iframe.wb-design-frame")
    expect(frame.locator("#made-up")).to_have_text("Made-up design")
    assert cell.locator("iframe.wb-design-frame").get_attribute("sandbox") == "allow-scripts"
    cell.locator("button[aria-label='Edit HTML']").click()
    expect(cell.locator(".monaco-editor")).to_be_visible()
    page.close()


def test_an_error_panel_with_its_values_and_coloured_traceback(browser: Browser, server: dict[str, Any]) -> None:
    source = "import json\ndef halve(x):\n    y = x * 2\n    return json.loads(y)\nhalve(3)"
    path = made_up(server, "error.ipynb", source)
    page = open_page(browser, server, f"notebooks?path={path}")
    page.locator(".wb-cell").first.locator("button[aria-label='Run cell']").click()
    panel = page.locator(".wb-err")
    expect(panel.locator(".wb-err-type")).to_have_text("TypeError", timeout=60_000)
    expect(panel).to_contain_text("In your code: cell [1], line 4")
    expect(panel.locator(".wb-err-values").last).to_contain_text("y 6 int")
    expect(panel.locator(".wb-err-stack .wb-err-lib")).to_contain_text("frame in json")
    panel.locator("summary:has-text('Traceback')").click()
    # Python's traceback keeps its terminal colours (spans the theme colours).
    expect(panel.locator(".wb-error span[class^='ansi-']").first).to_be_visible()
    panel.click(button="right")
    expect(page.locator(".context-menu")).to_contain_text("Send it with a question…")
    page.locator(".context-menu [role=menuitem]:has-text('Send this error to the agent')").click()
    inbox = call(server, "GET", "/agent/inbox")
    assert "TypeError" in json.dumps(inbox)
    page.close()
