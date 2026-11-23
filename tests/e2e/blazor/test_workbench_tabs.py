"""The Blazor Notebooks and Scripts pages' tabs and commands on made-up data: two documents as tabs, Split
right into a second group, a tab closed (asked first when unsaved), the command palette (Ctrl+Shift+P)
running a cell command, a cell's More actions menu, and an HTML cell drawn as its design in its walled-off
frame."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page


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
    choose_path(page, second)
    expect(page.locator(".wb-tab")).to_have_count(2)
    expect(page.locator(".wb-tab.active")).to_contain_text("second.ipynb")
    assert "second.ipynb" in page.url

    # A click on a tab brings it to the front, its cells as they were.
    page.locator(".wb-tab", has_text="first.ipynb").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("first.ipynb")

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
    expect(page.locator(".context-menu")).to_have_count(0)  # Escape is the menu's, not the page's

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
    palette = page.locator(".wb-palette")
    expect(palette).to_be_visible()
    palette.locator("input").fill("insert below")
    expect(palette.locator(".wb-palette-item")).to_have_count(1)
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


def test_an_error_panel_with_its_values_and_coloured_traceback(
    browser: Browser, server: dict[str, Any]
) -> None:
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


def test_the_scripts_ide_definition_rename_format_and_search(
    browser: Browser, server: dict[str, Any]
) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_tools.py")
    text = "def double_it(x):\n    return x*2\n\n\nprint(double_it(21))\n"
    call(server, "POST", "/workbench/save", {"path": path, "text": text})
    page = open_page(browser, server, f"scripts?path={path}")
    editor = page.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible()
    page.wait_for_timeout(500)
    # F12 on the call: the cursor goes to the definition's line.
    editor.locator(".view-line", has_text="print(double_it(21))").locator(
        "span", has_text="double_it"
    ).last.click()
    page.keyboard.press("F12")
    expect(page.locator(".monaco-editor .line-numbers.active-line-number")).to_have_text("1", timeout=15_000)

    # Shift+Alt+F: Ruff's format, or why not (either way the page says so).
    page.keyboard.press("Shift+Alt+F")
    formatted = page.locator(".wb-script-editor .view-line", has_text="return x * 2")
    said = page.locator(".note-corner .note, .error-note")
    expect(formatted.or_(said).first).to_be_visible(timeout=30_000)

    # Ctrl+Shift+F: Search in scripts, each result a line.
    page.keyboard.press("Control+Shift+F")
    dialog = page.locator(".dialog", has_text="Search in scripts")
    dialog.locator("input[type=search]").fill("double_it")
    expect(dialog.locator(".ide-count")).to_contain_text("result", timeout=15_000)
    page.close()


def test_a_notebooks_outline(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "outline.ipynb")
    cells = [
        {"kind": "markdown", "source": "# Made-up report\n## Totals", "number": 1},
        {"kind": "code", "source": "total = 1", "number": 2, "name": "made_up_loader"},
    ]
    call(server, "POST", "/workbench/save", {"path": path, "cells": cells, "next_cell": 3})
    page = open_page(browser, server, f"notebooks?path={path}")
    page.click(".wb-status button:has-text('Outline')")
    outline = page.locator(".wb-mode-panel[aria-label=Outline]")
    expect(outline.locator(".wb-outline-item.heading")).to_have_count(2)
    expect(outline.locator(".wb-outline-item.cell")).to_have_text("made_up_loader")
    outline.locator(".wb-outline-item.cell").click()
    expect(page.locator(".wb-cell.selected")).to_have_attribute("data-number", "2")
    outline.locator("button[aria-label='Close Outline']").click()
    expect(outline).to_have_count(0)
    page.close()


def test_the_debugger_stops_at_a_breakpoint(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_debug.py")
    text = "total = 0\nfor n in range(3):\n    total += n\nprint('made up', total)\n"
    call(server, "POST", "/workbench/save", {"path": path, "text": text})
    page = open_page(browser, server, f"scripts?path={path}")
    editor = page.locator(".wb-script-editor .monaco-editor")
    expect(editor).to_be_visible()
    page.wait_for_timeout(500)
    # A click in the gutter at line 4 puts a breakpoint there.
    line = editor.locator(".line-numbers", has_text="4").first
    box = line.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] - 8, box["y"] + box["height"] / 2)
    expect(editor.locator(".sab-breakpoint")).to_have_count(1)
    # A right click: Breakpoints at line 4.
    page.mouse.click(box["x"] - 8, box["y"] + box["height"] / 2, button="right")
    expect(page.locator(".context-menu")).to_contain_text("Add conditional breakpoint…")
    page.locator(".menu-shade").click()

    page.click("button[aria-label='Start debugging']")
    debug = page.locator(".wb-debug")
    expect(debug.locator(".wb-debug-status")).to_contain_text("Paused", timeout=90_000)
    expect(debug.locator(".wb-debug-vars")).to_contain_text("total")
    debug.locator("input[aria-label='Watch expression']").fill("total * 10")
    page.keyboard.press("Enter")
    expect(debug.locator(".wb-debug-watch")).to_contain_text("30")
    debug.locator("button[aria-label=Continue]").click()
    expect(debug.locator(".wb-debug-status")).to_contain_text("Ended", timeout=60_000)
    expect(debug.locator(".wb-debug-program")).to_contain_text("made up 3")
    page.close()


def test_a_file_changed_elsewhere_is_followed_or_asked_about(
    browser: Browser, server: dict[str, Any]
) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_followed.py")
    call(server, "POST", "/workbench/save", {"path": path, "text": "first = 1\n"})
    page = open_page(browser, server, f"scripts?path={path}")
    lines = page.locator(".wb-script-editor .view-lines")
    expect(lines).to_contain_text("first = 1")
    # Changed elsewhere with nothing unsaved here: followed in place.
    call(server, "POST", "/workbench/save", {"path": path, "text": "second = 2\n"})
    expect(lines).to_contain_text("second = 2", timeout=20_000)
    # With unsaved edits here: the bar asks.
    page.click(".wb-script-editor .monaco-editor .view-lines")
    page.keyboard.press("End")
    page.keyboard.type("  # mine")
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("●")
    call(server, "POST", "/workbench/save", {"path": path, "text": "third = 3\n"})
    bar = page.locator(".wb-elsewhere")
    expect(bar).to_contain_text("Changed elsewhere.", timeout=20_000)
    bar.locator("button:has-text('Keep mine')").click()
    expect(bar).to_have_count(0)
    expect(lines).to_contain_text("# mine")
    page.close()


def test_the_files_pane_finds_outlines_and_duplicates(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/project/new", {"name": "made_up_files"})
    folder = Path(made["project"]["path"])
    (folder / "scripts").mkdir(exist_ok=True)
    text = "def helper():\n    return 1\n\n\nclass MadeUpThing:\n    def go(self):\n        pass\n"
    call(server, "POST", "/workbench/save", {"path": str(folder / "scripts" / "tools.py"), "text": text})
    page = open_page(browser, server, "scripts")
    pane = page.locator(".files-pane")
    pane.locator("input[aria-label=Find]").fill("MadeUpThing")
    row = pane.locator(".wb-codex-file-row", has_text="tools")
    expect(row).to_have_count(1)
    expect(pane.locator(".wb-codex-symbol[data-symbol=MadeUpThing]")).to_be_visible()
    pane.locator(".wb-codex-symbol[data-symbol=MadeUpThing]").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("tools.py")
    expect(page.locator(".monaco-editor .line-numbers.active-line-number")).to_have_text("5", timeout=15_000)

    pane.locator("input[aria-label=Find]").fill("")
    pane.locator(".files-item", has_text="tools").click(button="right")
    page.locator(".context-menu [role=menuitem]:has-text('Duplicate')").click()
    expect(page.locator(".wb-tab.active")).to_contain_text("tools_copy", timeout=15_000)
    call(server, "POST", "/project/close", {"discard": True})
    page.close()


def test_the_palettes_other_commands(browser: Browser, server: dict[str, Any]) -> None:
    path = str(server["tmp"] / "workbench" / "made_up_console.py")
    call(server, "POST", "/workbench/save", {"path": path, "text": "print('made up')\n"})
    page = open_page(browser, server, f"scripts?path={path}")
    expect(page.locator(".wb-script-editor .monaco-editor")).to_be_visible()

    def run(words: str) -> None:
        page.keyboard.press("Control+Shift+P")
        page.locator(".wb-palette input").fill(words)
        expect(page.locator(".wb-palette-item").first).to_contain_text(words, ignore_case=True)
        page.keyboard.press("Enter")

    run("run code in the console")
    page.locator(".dialog input").fill("6 * 7")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".wb-console-body")).to_contain_text("42", timeout=60_000)
    run("what is open")
    expect(page.locator(".dialog .wb-help-text")).to_contain_text("made_up_console.py")
    page.locator(".dialog-foot button:has-text('Close')").click()
    run("keyboard shortcuts")
    sheet = page.get_by_role("dialog", name="Keyboard shortcuts")
    expect(sheet).to_contain_text("Ctrl+Shift+P")
    sheet.get_by_role("button", name="Close").click()
    run("clear the console")
    expect(page.locator(".wb-console-body")).not_to_contain_text("42")
    page.close()
