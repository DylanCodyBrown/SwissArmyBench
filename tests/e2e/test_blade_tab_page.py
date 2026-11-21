"""The Scripts page's blade tab in a real browser (the owner, 2026-11-21: "the blade format requires extra
stuff so we should add those properties to the ide experience along with the option to save the blade. we
should scaffold a blank blade for the user"). Made-up rows only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_scripts_ide_page import page_of, shot
from tests.e2e.test_ui import browser, call, server, until  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_SCRIPTS_SHOTS")


def test_new_blade_is_a_blank_working_scaffold_with_its_properties(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
) -> None:
    page = page_of(browser, server, "scripts?pane=blades")
    blades = page.locator(".wb-codex-lower.lower-blades")
    expect(blades).to_be_visible(timeout=20000)
    blades.get_by_role("button", name="New blade").click()
    dialog = page.get_by_role("dialog", name="New blade")
    dialog.get_by_label("Name").fill("Made-up orders")
    dialog.get_by_role("radio", name=re.compile("^Table")).check()
    dialog.get_by_role("button", name="Create").click()
    tab = page.locator(".wb-tab[data-kind='blade']", has_text="Made-up orders")
    expect(tab).to_be_visible(timeout=20000)
    ide = page.locator(".code-ide:visible")
    # Properties open by itself on a brand-new scaffold, with the table blade's own fields.
    props = ide.locator(".ide-props")
    expect(props).to_be_visible(timeout=20000)
    expect(props.get_by_label("Its table is called")).to_be_visible()
    expect(props.get_by_label("It hands back")).to_have_value("make_table")
    expect(props.get_by_label("SQL dialect")).to_have_count(0)  # not a connection's
    # The editor shows the body only: no header lines.
    lines = ide.locator(".ide-editor .view-lines")
    expect(lines).to_contain_text("def make_table", timeout=20000)
    expect(lines).not_to_contain_text("swissarmybench-blade")
    # Run works at once: the made-up rows as the Result.
    ide.get_by_role("button", name="Run").click()
    expect(ide.locator(".ide-row-count")).to_have_text(re.compile("3 rows"), timeout=60000)
    if SHOTS:
        shot(page, "blade-new-scaffold")
    # A header field saved with the code: the file has it.
    props.get_by_label("Family").fill("Made-up shop")
    ide.get_by_role("button", name="Save", exact=True).click()
    expect(ide.locator(".ide-dirty")).to_be_hidden(timeout=20000)
    detail = call(server, "GET", "/blades/Made-up%20orders")
    assert 'family = "Made-up shop"' in Path(detail["file"]).read_text(encoding="utf-8")
    call(server, "DELETE", "/blades/Made-up%20orders")


def test_the_blade_tab_never_crowds_the_code(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
) -> None:
    """Design principle 8.14: Properties closed (it opened by itself only on the new scaffold), the panel
    folded to its tabs until a problem appears, then about 30% of the area; no minimap."""
    call(server, "POST", "/blades/new", {"name": "Made-up loaves", "kind": "table"})
    try:
        page = page_of(browser, server, "scripts?pane=blades&blade=Made-up%20loaves")
        ide = page.locator(".code-ide:visible")
        expect(ide.locator(".ide-editor .monaco-editor")).to_be_visible(timeout=20000)
        expect(ide.locator(".ide-props")).to_be_hidden()
        panel = ide.locator(".ide-panel")
        expect(panel).to_have_class(re.compile(r"\bfolded\b"))
        expect(ide.locator(".minimap")).to_be_hidden()  # Monaco keeps the element, with no width
        ide.locator(".ide-editor .view-lines").click()
        page.keyboard.press("Control+End")
        page.keyboard.insert_text("\nmissing_name + 1\n")
        expect(panel).not_to_have_class(re.compile(r"\bfolded\b"), timeout=20000)
        expect(ide.get_by_role("tab", name=re.compile("Problems"))).to_have_attribute("aria-selected", "true")
        share = page.evaluate(
            "() => { const c = document.querySelector('.code-ide .ide-center');"
            " const p = c.querySelector('.ide-panel');"
            " return p.getBoundingClientRect().height / c.getBoundingClientRect().height; }"
        )
        assert 0.2 < share < 0.4, share
    finally:
        call(server, "DELETE", "/blades/Made-up%20loaves")
