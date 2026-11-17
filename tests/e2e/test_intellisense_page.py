# ruff: noqa: F811
"""The Workbench editors' intelligence in the browser (workbenchIntel.ts, services/intellisense.py): the
member list with its documentation panel, parameter info with the current parameter bold, quick info on
hover, a typo's squiggle and the status bar's count, and Ctrl+. adding an import. Made-up names only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401
from tests.e2e.test_workbench_page import add_cell, new_script, open_workbench, start

SHOTS = os.environ.get("SAB_SHOTS")

WRITER = '''def write_sqlite(connection: str, table: str, rows: list, mode: str = "append") -> int:
    """Write rows to a SQLite table.

    Args:
        connection: The connection's name.
        table: The table to write.
        rows: The rows to write.
        mode: append or replace.
    """
    return len(rows)
'''


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / name))


def paste(page: Page, text: str) -> None:
    """Text into the focused editor as a paste (typed, a cell's editor would indent each line again)."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.evaluate("t => navigator.clipboard.writeText(t)", text)
    page.keyboard.press("Control+V")


def cell(workbench: Page, n: int) -> Any:
    found = workbench.locator(".wb-cell").nth(n)
    expect(found.locator(".monaco-editor")).to_be_visible(timeout=20000)
    return found


def test_the_member_list_parameter_info_and_quick_info(browser: Browser, orders_url: str) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    workbench.set_viewport_size({"width": 1280, "height": 820})
    start(workbench)
    first = cell(workbench, 0)
    first.locator(".monaco-editor").click()
    paste(workbench, WRITER)
    add_cell(workbench, "Python")
    second = cell(workbench, 1)
    second.locator(".monaco-editor").click()
    # The member list as you type, the documentation panel beside it (no kernel yet: Jedi reads the
    # cell above).
    workbench.keyboard.type("write_")
    workbench.keyboard.press("Control+Space")
    suggest = workbench.locator(".suggest-widget .monaco-list-row")
    expect(suggest.filter(has_text="write_sqlite").first).to_be_visible(timeout=10000)
    details = workbench.locator(".suggest-details")
    expect(details).to_contain_text("Write rows to a SQLite table.", timeout=10000)
    expect(details).to_contain_text("The table to write.")
    shot(workbench, "member-list.png")
    workbench.keyboard.press("Escape")
    # Parameter info: the first parameter bold, then the second after a comma.
    workbench.keyboard.type("sqlite(")
    hints = workbench.locator(".parameter-hints-widget")
    expect(hints).to_be_visible(timeout=10000)
    expect(hints.locator(".parameter.active")).to_have_text("connection: str", timeout=10000)
    expect(hints).to_contain_text("The connection's name.")
    shot(workbench, "parameter-info.png")
    workbench.keyboard.type('"Warehouse", ')
    expect(hints.locator(".parameter.active")).to_have_text("table: str", timeout=10000)
    expect(hints).to_contain_text("The table to write.")
    workbench.keyboard.press("Escape")
    # Quick info on hover: the pointer over the name. The window never scrolls sideways (a long status
    # bar once made the page wider than the window: the rail then covered the name).
    assert workbench.evaluate("document.documentElement.scrollWidth") <= 1280
    assert workbench.evaluate("scrollX") == 0
    word = second.locator(".view-line span span", has_text="write_sqlite").first
    box = word.bounding_box()
    assert box
    workbench.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    workbench.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2, steps=4)
    hover = workbench.locator(".monaco-hover:not(.hidden)").first
    expect(hover).to_contain_text("Write rows to a SQLite table.", timeout=10000)
    workbench.wait_for_timeout(300)  # its fade-in done
    shot(workbench, "quick-info.png")


def test_a_typo_is_squiggled_counted_and_ctrl_dot_adds_an_import(
    browser: Browser, orders_url: str, server: dict[str, Any]
) -> None:
    workbench = open_workbench(open_grid(browser, orders_url))
    workbench.set_viewport_size({"width": 1280, "height": 820})
    new_script(workbench, "total = 0\nprint(totl)\nframe = pd.DataFrame()\n")
    editor = workbench.locator(".wb-script-editor")
    # Within a second of the typing stopping: the squiggles and the status bar's count.
    expect(editor.locator(".squiggly-error").first).to_be_visible(timeout=3000)
    problems = workbench.locator(".wb-status .wb-problems")
    expect(problems).to_be_visible(timeout=3000)
    expect(problems).to_contain_text("2 errors")
    shot(workbench, "lint.png")
    problems.click()
    menu = workbench.get_by_role("menu", name="Problems")
    expect(menu).to_contain_text("line 2: totl is not defined (F821)")
    menu.get_by_role("menuitem").filter(has_text="pd is not defined").click()
    # Ctrl+. on the place: Add `import pandas as pd`.
    workbench.keyboard.press("Control+.")
    fix = workbench.locator(".action-widget").get_by_text("Add import pandas as pd")
    expect(fix).to_be_visible(timeout=5000)
    shot(workbench, "quick-fix.png")
    fix.click()
    expect(editor.locator(".view-lines")).to_contain_text("import pandas as pd", timeout=5000)
    expect(problems).to_contain_text("1 error", timeout=3000)
    # The agent reads the same (workbench_problems), a moment after the editor settles.
    workbench.wait_for_timeout(1500)
    seen = call(server, "GET", "/workbench/intel/problems")
    [document] = [d for d in seen["documents"] if d["document"] == "Untitled script"]
    assert [p["code"] for p in document["problems"]] == ["F821"]
