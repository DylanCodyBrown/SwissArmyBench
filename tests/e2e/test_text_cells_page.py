# ruff: noqa: F811
"""Markdown and HTML cells on the Streamlit canvas (docs/ideas.md, text cells on the canvas, 2026-11-15),
in a real browser: a Markdown cell's `{{ total }}` filled from the kernel when it runs (a value is
always text), out of date when the variable changes; the Markdown cell and an HTML KPI cell listed
under Text in the Streamlit cells pane, dragged onto a canvas, and shown by Play on the live page
(with the real Streamlit); and a Markdown starter inserted into a Markdown cell from its menu.

With SWISSARMYBENCH_SHOTS set to a folder, the tests also save screenshots there (2x). Made-up data
only."""

from __future__ import annotations

import re
import urllib.error
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_streamlit_page import LONG, open_window, orders, shot  # noqa: F401
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

FIGURES = 'total = 480\nnote = "</script><b>*x*</b>"'
SUMMARY = "## Orders\nTotal for all regions: **{{ total }}**\n\nA made-up note: {{ note }}"
CARD = (
    '<div class="kpi" style="display:inline-block;padding:12px 16px;border-radius:10px;'
    'border:1px solid #c8102e;font-family:system-ui,sans-serif">'
    '<div style="font-size:12px;text-transform:uppercase;opacity:.75">Total sales</div>'
    '<div class="kpi-value" style="font-size:28px;font-weight:650">{{ total }}</div></div>'
)


@needs_streamlit
def test_a_markdown_cell_fills_its_names_and_goes_on_a_canvas_with_an_html_cell(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    assert STREAMLIT_PYTHON is not None
    book = tmp_path / "story.ipynb"
    cells = [
        {"kind": "code", "source": FIGURES, "name": "Figures"},
        {"kind": "markdown", "source": SUMMARY},
        {"kind": "html", "source": CARD, "name": "KPI card"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(book), "cells": cells})
    call(server, "POST", "/workbench/environment", {"path": str(book), "python": STREAMLIT_PYTHON})
    workbench = open_window(browser, server, book)
    shown = workbench.locator(".wb-cell")
    summary = shown.nth(1)

    # ----- the Markdown cell shows as text: its names as written until it runs
    expect(summary).to_have_class(re.compile("rendered"))
    expect(summary.locator(".wb-text-bar .wb-design-state")).to_have_text("Not run yet")
    expect(summary.locator(".wb-markdown-view")).to_contain_text("{{ total }}")
    window(server, "run.primary")
    view = summary.locator(".wb-markdown-view")
    expect(view.locator("strong")).to_have_text("480", timeout=LONG)
    # The value is text: its markup and Markdown marks show as typed, nothing is made of them.
    expect(view).to_contain_text("A made-up note: </script><b>*x*</b>")
    expect(view.locator("b, em, script")).to_have_count(0)
    expect(summary.locator(".wb-text-bar")).to_be_hidden()  # current: nothing is said
    # The HTML cell's design is filled the same way.
    expect(shown.nth(2).frame_locator(".wb-design-frame").locator(".kpi-value")).to_have_text("480")
    # A variable it names changes: out of date, by the HTML cells' own marks.
    window(server, "console.run", code="total = 512")
    expect(summary.locator(".wb-text-bar .wb-design-state")).to_have_text(
        re.compile(r"^Out of date · total changed"), timeout=20000
    )
    summary.locator(".wb-text-bar").get_by_role("button", name="Run").click()
    expect(view.locator("strong")).to_have_text("512", timeout=20000)

    # ----- onto a canvas: the text from the pane, side by side; the figures cell by its number (onto
    # the app's tab), below them
    window(server, "file.newApp")
    tabs = workbench.locator(".wb-tab")
    expect(tabs).to_have_count(2)
    # ----- the Streamlit cells pane (the canvas's own panel) lists both under Text, each marked T
    pane = workbench.locator(".wb-st")
    expect(pane.locator(".wb-st-text-head")).to_have_text(["Text"], timeout=20000)
    texts = pane.locator(".wb-st-cell.text")
    expect(texts.locator(".wb-data-label")).to_have_text(["Orders", "KPI card"])
    expect(texts.locator(".wb-st-t")).to_have_count(2)
    expect(texts.nth(0).locator(".wb-data-meta")).to_have_text("@cell2reads total, note")
    board = workbench.locator(".cv-board")
    box = board.bounding_box()
    assert box is not None
    texts.nth(0).drag_to(board, target_position={"x": 30, "y": 30})
    expect(workbench.locator(".cv-block")).to_have_count(1)
    texts.nth(1).drag_to(board, target_position={"x": box["width"] * 0.8, "y": 30})
    tabs.nth(0).click()
    shown.nth(0).locator(".wb-number").drag_to(tabs.nth(1))
    tabs.nth(1).click()
    blocks = workbench.locator(".cv-block")
    expect(blocks).to_have_count(3)
    expect(blocks.locator(".cv-block-name")).to_have_text(["Orders", "KPI card", "Figures"])
    expect(blocks.nth(0).locator(".wb-st-t")).to_have_text("T")
    expect(blocks.nth(0).locator(".cv-block-parts")).to_have_text("reads total, note")
    expect(blocks.nth(2).locator(".wb-st-t")).to_have_count(0)
    assert [b.get_attribute("data-row") for b in blocks.all()] == ["1", "1", "2"]
    shot(workbench, "text-1-a-canvas-with-markdown-and-html-blocks")

    # ----- Play: the live page shows both, their names filled on the page by the same rules
    workbench.get_by_role("button", name="Play", exact=True).click()
    page = workbench.frame_locator(".cv-frame")
    expect(page.get_by_text("Total for all regions:")).to_be_visible(timeout=LONG)
    expect(page.locator('[data-testid="stMarkdown"] strong')).to_have_text("480")
    expect(page.get_by_text("A made-up note: </script><b>*x*</b>")).to_be_visible()
    expect(page.locator(".kpi-value")).to_have_text("480")
    shot(workbench, "text-2-the-page-after-play")
    workbench.close()


def test_a_markdown_starter_goes_into_a_markdown_cell_from_its_menu(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    workbench = open_window(browser, server)
    workbench.get_by_role("button", name="Start a notebook").click()
    expect(workbench.locator(".wb-cell .monaco-editor").first).to_be_visible(timeout=20000)
    window(server, "cell.toMarkdown")
    cell = workbench.locator(".wb-cell.kind-markdown")
    expect(cell).to_have_count(1)
    cell.get_by_role("button", name="More actions").click()
    workbench.get_by_role("menuitem", name="Insert a snippet…").click()
    picker = workbench.locator("dialog[open]")
    expect(picker.locator("h2")).to_have_text("Insert a Markdown snippet")
    picker.get_by_role("searchbox", name="Search snippets").fill("kpi sentence")
    picker.locator(".snippet-choice", has_text="Markdown KPI sentence").click()
    form = workbench.locator("dialog[open]")
    expect(form.locator("h2")).to_have_text("Markdown KPI sentence")
    expect(form.get_by_label("Label", exact=True)).to_have_value("Total for")
    form.get_by_label("Label", exact=True).fill("Sales *so far* in")
    form.get_by_role("button", name="Insert").click()
    # The text went in, the typed marks escaped; the names it reads are its own, still to run.
    expect(cell).to_have_class(re.compile("rendered"), timeout=20000)
    expect(cell.locator(".wb-markdown-view")).to_contain_text("Sales *so far* in {{ region }}:")
    expect(cell.locator(".wb-text-bar .wb-design-state")).to_have_text("Not run yet")
    shot(workbench, "text-3-a-markdown-starter-inserted")
    held = window(server, "doc.read")["cells"][0]
    assert held["kind"] == "markdown"
    assert held["source"] == "Sales \\*so far\\* in {{ region }}: **{{ total_sales }}**"
    # A snippet of another language is refused, with a short message.
    window(server, "cell.toCode")
    try:
        window(server, "snippet.insert", name="Markdown callout", values={}, number=held["number"])
    except urllib.error.HTTPError as error:  # the window's refusal comes back as the command's error
        assert "A Markdown snippet goes in a Markdown cell" in error.read().decode()
    else:
        raise AssertionError("a Markdown snippet went into a Python cell")
    workbench.close()


FLOW = "## Flow\n```mermaid\nflowchart LR\n  A[Orders] --> B[Totals]\n```"
BROKEN = "```mermaid\nflowchart LR\n  A[ --> \n```"
NAMED = "```mermaid\nflowchart LR\n  A[{{ region }}] --> B[Done]\n```"


def test_a_markdown_cells_mermaid_block_is_drawn_and_a_broken_one_says_why(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    book = tmp_path / "flow.ipynb"
    cells = [
        {"kind": "markdown", "source": FLOW},
        {"kind": "markdown", "source": BROKEN},
        {"kind": "code", "source": 'region = "East --> West"'},
        {"kind": "markdown", "source": NAMED},
    ]
    call(server, "POST", "/workbench/save", {"path": str(book), "cells": cells})
    workbench = open_window(browser, server, book)
    shown = workbench.locator(".wb-cell")
    # Drawn by the app's own Mermaid (nothing from the internet), as SVG, when not being edited.
    drawing = shown.nth(0).locator(".md-mermaid svg")
    expect(drawing).to_be_visible(timeout=20000)
    expect(drawing).to_contain_text("Orders")
    expect(drawing.locator("g.node")).to_have_count(2)
    expect(shown.nth(0).locator("h2")).to_have_text("Flow")
    # A broken diagram says why, in its place.
    broken = shown.nth(1).locator(".md-mermaid.error-text")
    expect(broken).to_contain_text("This diagram could not be drawn")
    # A name in a diagram is filled as text: the value's own arrow draws no edge (its marks full-width).
    window(server, "run.primary")
    named = shown.nth(3).locator(".md-mermaid svg")
    expect(named).to_contain_text("East －－＞ West", timeout=20000)
    expect(named.locator("g.node")).to_have_count(2)
    shot(workbench, "text-4-a-mermaid-diagram-in-a-markdown-cell")
    workbench.close()
