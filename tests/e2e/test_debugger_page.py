"""The Scripts page's debugger in a real browser (2026-11-21): breakpoints in the gutter (a conditional one
and a log point), Start debugging, paused at the line with the call stack, variables, a watch and the debug
console, a step, continue to the end. Made-up code only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.asks import accept_asks
from tests.e2e.test_scripts_ide_page import shop, tree_file  # noqa: F401
from tests.e2e.test_ui import browser, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SCRIPTS_SHOTS")
SCRIPT = (
    "loaves = 0\n"
    "def bake(n):\n"
    "    total = n * 2\n"
    "    return total\n"
    "for day in range(1, 4):\n"
    "    loaves += bake(day)\n"
    "print('baked', loaves)\n"
)


def test_a_script_paused_at_a_breakpoint_read_stepped_and_continued(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,  # noqa: F811
) -> None:
    (shop / "scripts" / "bake.py").write_text(SCRIPT, encoding="utf-8")
    context = browser.new_context(
        viewport={"width": 1500, "height": 900}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    answers = ["n == 2", "day {day}"]
    page.on("dialog", lambda d: d.accept())
    accept_asks(page, lambda _words: answers.pop(0) if answers else None)  # a condition, then a log line
    page.goto(f"http://127.0.0.1:{server['port']}/scripts#token={server['token']}")
    tree_file(page, "scripts/bake.py").click()
    tab = page.locator(".wb-tab", has_text="bake.py")
    expect(tab).to_be_visible(timeout=20000)
    page.wait_for_timeout(500)
    tab.click()
    editor = page.locator(".wb-script-editor:visible .monaco-editor").first
    expect(editor).to_contain_text("def bake", timeout=20000)
    numbers = editor.locator(".line-numbers")
    # A conditional breakpoint (line 3) and a log point (line 6), from the gutter's right-click.
    numbers.filter(has_text=re.compile(r"^3$")).click(button="right")
    page.get_by_role("menuitem", name="Add conditional breakpoint…").click()
    numbers.filter(has_text=re.compile(r"^6$")).click(button="right")
    page.get_by_role("menuitem", name="Add log point…").click()
    expect(editor.locator(".sab-breakpoint")).to_have_count(2)
    expect(editor.locator(".sab-breakpoint.bp-condition")).to_have_count(1)
    expect(editor.locator(".sab-breakpoint.bp-log")).to_have_count(1)
    # Start debugging: paused at line 3 with n == 2 (the condition), the log point's words already out.
    page.get_by_role("button", name="Start debugging").click()
    panel = page.locator(".wb-debug:visible")
    expect(panel.locator(".wb-debug-status")).to_have_text("Paused in bake, line 3", timeout=60000)
    expect(editor.locator(".sab-paused-line")).to_have_count(1)
    expect(panel.locator(".wb-debug-frame").first).to_contain_text("bake")
    expect(panel.locator(".wb-debug-var[data-name='n'] .wb-debug-value")).to_have_text("2", timeout=20000)
    expect(panel.locator(".wb-debug-program")).to_contain_text("day 1")
    panel.get_by_label("Watch expression").fill("n * 10")
    panel.get_by_label("Watch expression").press("Enter")
    expect(panel.locator(".wb-debug-watch .wb-debug-value")).to_have_text("20", timeout=20000)
    panel.get_by_label("Debug console", exact=True).fill("n + 40")
    panel.get_by_label("Debug console", exact=True).press("Enter")
    expect(panel.locator(".wb-debug-out").last).to_contain_text("42", timeout=20000)
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / "debugger-paused.png"))
    # Step over (F10): line 4; continue (F5): to the end.
    page.keyboard.press("F10")
    expect(panel.locator(".wb-debug-status")).to_have_text("Paused in bake, line 4", timeout=30000)
    page.keyboard.press("F5")
    expect(panel.locator(".wb-debug-status")).to_have_text("Ended", timeout=30000)
    expect(panel.locator(".wb-debug-program")).to_contain_text("baked 12", timeout=20000)
    expect(editor.locator(".sab-paused-line")).to_have_count(0)
    context.close()
