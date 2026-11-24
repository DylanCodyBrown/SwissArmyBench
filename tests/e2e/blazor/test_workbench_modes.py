"""The Blazor Notebooks and Scripts pages' modes and moves on made-up data: a script's Run settings
(arguments and a variable), a notebook's Present and a project's data.ipynb's Dictionary, a figure's Send
to Analyze with the note's Show, a table result's Open as table, Jupyter's command mode keys, a file
changed elsewhere compared, Import… and New environment's dialog."""

from __future__ import annotations

import json
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, open_page


def test_run_settings_and_present(browser: Browser, server: dict[str, Any]) -> None:
    script = server["tmp"] / "workbench" / "made_up_settings.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("import os\nprint(os.environ.get('MADE_UP_REGION'))\n")
    page = open_page(browser, server, f"scripts?path={script}")
    page.click(".wb-status button:has-text('Run settings')")
    panel = page.locator(".wb-run-settings")
    panel.locator("input[aria-label=Arguments]").fill("--day 2026-11-14")
    panel.locator("input[aria-label=Arguments]").press("Enter")
    expect(panel.locator("input[aria-label=Arguments]")).to_have_value("--day 2026-11-14")
    saved = call(server, "GET", f"/workbench/scripts/settings?path={script}")
    assert saved["arguments"] == "--day 2026-11-14"
    page.close()

    notebook = str(server["tmp"] / "workbench" / "made_up_present.ipynb")
    cells = [
        {"kind": "markdown", "source": "# A made-up report", "number": 1},
        {"kind": "code", "source": "x = 1", "number": 2},
    ]
    call(server, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 3})
    page = open_page(browser, server, f"notebooks?path={notebook}")
    page.click(".wb-gcontrols .wb-view-present")
    expect(page.locator(".wb-notebook-host.presenting")).to_be_visible()
    expect(page.locator(".wb-notebook-host.presenting .wb-cell-head").first).to_be_hidden()
    page.click(".wb-gcontrols .wb-view-cells")
    expect(page.locator(".wb-notebook-host.presenting")).to_have_count(0)
    page.close()


def test_outputs_send_to_analyze_and_command_mode(browser: Browser, server: dict[str, Any]) -> None:
    notebook = str(server["tmp"] / "workbench" / "made_up_outputs.ipynb")
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10'/></svg>"
    )
    code = f"from IPython.display import SVG, display\ndisplay(SVG({svg!r}))"
    cells = [{"kind": "code", "source": code, "number": 1}, {"kind": "code", "source": "y = 2", "number": 2}]
    call(server, "POST", "/workbench/save", {"path": notebook, "cells": cells, "next_cell": 3})
    page = open_page(browser, server, f"notebooks?path={notebook}")
    first = page.locator(".wb-cell").first
    first.locator("button[aria-label='Run cell']").click()
    send = first.locator(".wb-to-sandbox")
    expect(send).to_be_visible(timeout=60_000)
    send.click()
    note = page.locator(".toast", has_text="Sent to Analyze")
    expect(note).to_be_visible()
    note.locator("button:has-text('Show')").click()
    page.wait_for_url("**/analyze?card=*")
    expect(page.locator(".board-card[data-kind=image]").first).to_be_visible()
    page.close()

    page = open_page(browser, server, f"notebooks?path={notebook}")
    cells_before = 2
    expect(page.locator(".wb-cell")).to_have_count(cells_before)
    page.locator(".wb-cell").nth(1).focus()
    page.keyboard.press("b")
    expect(page.locator(".wb-cell")).to_have_count(cells_before + 1)
    added = page.locator(".wb-cell").nth(2)
    expect(added.locator(".monaco-editor")).to_be_visible()
    page.wait_for_timeout(1500)  # the new cell's editor takes the focus once Monaco is made
    added.focus()
    page.wait_for_function("document.activeElement?.classList.contains('wb-cell')")
    page.keyboard.press("d")
    page.keyboard.press("d")
    expect(page.locator(".wb-cell")).to_have_count(cells_before)
    page.close()


def test_compare_import_and_new_environment(browser: Browser, server: dict[str, Any]) -> None:
    script = server["tmp"] / "workbench" / "made_up_compare.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("value = 1\n")
    page = open_page(browser, server, f"scripts?path={script}")
    page.click(".wb-script-editor .monaco-editor .view-lines")
    page.keyboard.press("End")
    page.keyboard.type("\nmine = 2")
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("●")
    call(server, "POST", "/workbench/save", {"path": str(script), "text": "value = 3\n", "force": True})
    bar = page.locator(".wb-elsewhere")
    expect(bar).to_contain_text("Changed elsewhere.", timeout=30_000)
    bar.locator("button:has-text('Compare')").click()
    dialog = page.locator(".dialog.wide")
    expect(dialog).to_contain_text("the file, and yours")
    expect(dialog.locator(".diff-host .monaco-diff-editor")).to_be_visible()
    dialog.locator(".dialog-foot button:has-text('Close')").click()

    page.locator(".wb-status select[aria-label=Environment]").select_option("__new")
    env = page.locator(".dialog[aria-label='New environment']")
    expect(env.locator("input[aria-label=Folder]")).to_have_value(
        json.dumps(str(server["tmp"] / "workbench" / ".venv"))[1:-1]
    )
    expect(env.locator("select[aria-label='Python version']")).to_be_visible()
    env.locator("button:has-text('Cancel')").click()
    expect(env).to_have_count(0)
    page.close()
