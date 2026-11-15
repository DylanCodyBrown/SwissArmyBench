# ruff: noqa: F811
"""Streamlit pieces and the page designer (docs/ideas.md, 2026-11-15), in a real browser and with the
real Streamlit: two pieces live in their cells, pushed to a page, arranged in the page designer (the
filter BELOW the total), the filter driving the total on the live page, a second page, a grid step
making the pieces out of date, and the export run on its own.

Streamlit is not this app's dependency: these tests run when SWISSARMYGRID_STREAMLIT_PYTHON names a
Python with streamlit, pandas and pyarrow, and are skipped otherwise. Made-up data only."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, FrameLocator, Locator, Page, expect

from swissarmygrid.client import push_client
from tests.e2e.test_table_cells_page import close_tables, open_workbench, type_cell, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'
ORDERS = pd.DataFrame(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [100, 250, 40, 75, 10, 5],
    }
)
LONG = 60000  # Streamlit's first start, in milliseconds


def piece(cell: Locator) -> FrameLocator:
    return cell.frame_locator(".wb-piece-frame")


def metric(frame: FrameLocator) -> Locator:
    return frame.locator('[data-testid="stMetricValue"]')


def pick(frame: FrameLocator, page: Page, option: str) -> None:
    """Choose a selectbox's option in a live Streamlit page."""
    frame.locator('[data-testid="stSelectbox"] input').click()
    frame.get_by_role("option", name=option).click()
    page.wait_for_timeout(200)


def is_above(upper: Locator, lower: Locator) -> bool:
    above, below = upper.bounding_box(), lower.bounding_box()
    return above is not None and below is not None and above["y"] + above["height"] <= below["y"]


def wait_until(page: Page, check: Any, seconds: float = 30) -> None:
    """Wait for something no locator says (where two things sit)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        page.wait_for_timeout(100)
    raise AssertionError("it did not happen in time")


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[str]:
    close_tables(server)
    url = push_client.push(ORDERS, name="orders", new_grid=True)
    yield url.rsplit("/g/", 1)[1].split("#")[0]
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def notebook_with_python(server: dict[str, Any], path: Path, python: str | None) -> None:
    """An empty saved notebook whose environment is `python` (None: this app's own)."""
    call(server, "POST", "/workbench/save", {"path": str(path), "cells": [{"kind": "code", "source": ""}]})
    if python:
        call(server, "POST", "/workbench/environment", {"path": str(path), "python": python})


def add_piece(workbench: Page, index: int, code: str) -> Locator:
    workbench.locator(".wb-toolbar").get_by_role("button", name="Streamlit", exact=True).click()
    cell = workbench.locator(".wb-cell").nth(index)
    expect(cell).to_have_class(re.compile("kind-streamlit"))
    type_cell(workbench, index, code)
    return cell


@needs_streamlit
def test_pieces_live_in_their_cells_assembled_on_a_page_and_exported(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    assert STREAMLIT_PYTHON is not None
    book = tmp_path / "sales.ipynb"
    notebook_with_python(server, book, STREAMLIT_PYTHON)
    workbench = open_workbench(browser, server, book)

    # ----- two pieces: a region selectbox (making `region`), a total that reads orders and region
    filter_cell = add_piece(workbench, 1, FILTER)
    total_cell = add_piece(workbench, 2, TOTAL)
    # Not run yet: said, with Run. Its code shows.
    expect(total_cell.locator(".wb-design-state")).to_have_text("Not run yet")
    expect(total_cell.locator(".monaco-editor")).to_be_visible()
    workbench.keyboard.press("Control+Enter")
    # Each live in its own cell, with working widgets.
    expect(piece(filter_cell).locator('[data-testid="stSelectbox"]')).to_be_visible(timeout=LONG)
    expect(metric(piece(total_cell))).to_have_text("145", timeout=LONG)  # East: 100 + 40 + 5
    expect(total_cell.locator(".wb-design-state")).to_be_hidden()  # current: nothing is said
    expect(total_cell.locator(".monaco-editor")).to_be_hidden()
    # The total alone still has its input: the piece that makes `region`, above it.
    expect(piece(total_cell).get_by_text("region comes from the piece in cell")).to_be_visible()
    pick(piece(total_cell), workbench, "West")
    expect(metric(piece(total_cell))).to_have_text("260")
    # The uses line names the table the piece reads, and its part says what links it.
    cells = window(server, "streamlit.list")
    assert [(c["name"], c["makes"], c["tables"], c["state"]) for c in cells["cells"]] == [
        ("Region filter", ["region"], ["orders"], "current"),
        ("Total", [], ["orders"], "current"),
    ]
    assert cells["cells"][1]["reads"] == ["region"]
    expect(total_cell.locator(".wb-part")).to_have_text("reads orders, region")
    # A click on the cell's head opens the code again; leaving shows the piece.
    total_cell.locator(".wb-number").click()
    expect(total_cell.locator(".monaco-editor")).to_be_visible()
    workbench.keyboard.press("Escape")
    expect(total_cell.locator(".monaco-editor")).to_be_hidden()

    # ----- push both to a new page
    filter_cell.get_by_role("button", name="Push to page").click()
    workbench.locator(".wb-push-menu").get_by_role("menuitem", name="New page").click()
    expect(filter_cell.locator(".wb-piece-page")).to_have_text("Page 1")
    total_cell.get_by_role("button", name="Push to page").click()
    workbench.locator(".wb-push-menu").get_by_role("menuitem", name="Page 1").click()
    expect(total_cell.locator(".wb-piece-page")).to_have_text("Page 1")
    expect(workbench.locator(".wb-tabs .tab-item.active")).to_contain_text("●")  # the pages are the file's

    # ----- the page designer: a window of its own
    with workbench.expect_popup() as opened:
        total_cell.locator(".wb-piece-page").click()
    designer = opened.value
    expect(designer.locator(".dz-card")).to_have_count(2)
    expect(designer.locator(".dz-card").nth(0)).to_contain_text("Region filter")
    expect(designer.locator(".dz-card").nth(0)).to_contain_text("makes region")
    expect(designer.locator(".dz-card").nth(1)).to_contain_text("reads orders, region")
    live = designer.frame_locator(".dz-frame")
    expect(metric(live)).to_have_text("145", timeout=LONG)
    # Place the filter BELOW the total: the total first (dragged before the filter), the whole width.
    designer.locator(".dz-card", has_text="Total").drag_to(
        designer.locator(".dz-card", has_text="Region filter"), target_position={"x": 5, "y": 10}
    )
    expect(designer.locator(".dz-card").nth(0)).to_contain_text("Total")
    grip = designer.locator(".dz-card", has_text="Total").locator(".dz-grip")
    grip.focus()
    for width in range(7, 13):
        designer.keyboard.press("ArrowRight")
        expect(designer.locator(".dz-card", has_text="Total")).to_have_attribute("data-w", str(width))
    layout = call(server, "GET", f"/streamlit/apps/{cells['app']}")["pages"][0]
    assert [(p["cell"], p["w"]) for p in layout["pieces"]] == [(3, 12), (2, 6)]
    assert len(layout["rows"]) == 2 and layout["order"] == [
        layout["pieces"][1]["id"],
        layout["pieces"][0]["id"],
    ]
    # The live page follows: the total on top, the filter under it, and the filter still drives it.
    expect(metric(live)).to_have_text("145", timeout=LONG)
    expect(live.locator('[data-testid="stSelectbox"]')).to_be_visible()
    wait_until(designer, lambda: is_above(metric(live), live.locator('[data-testid="stSelectbox"]')))
    pick(live, designer, "West")
    expect(metric(live)).to_have_text("260")
    pick(live, designer, "North")
    expect(metric(live)).to_have_text("75")

    # ----- a name for the page, and a second page
    designer.locator(".dz-tab").first.dblclick()
    designer.locator(".dz-rename").fill("Sales overview")
    designer.keyboard.press("Enter")
    expect(designer.locator(".dz-tab").first).to_contain_text("Sales overview")
    designer.get_by_role("button", name="New page").click()
    expect(designer.locator(".dz-tab")).to_have_count(2)
    expect(designer.locator(".dz-tab.active")).to_contain_text("Page 2")
    designer.locator(".dz-piece", has_text="Region filter").get_by_role("button", name="Add").click()
    expect(designer.locator(".dz-card")).to_have_count(1)
    expect(designer.frame_locator(".dz-frame").locator('[data-testid="stSelectbox"]')).to_be_visible(
        timeout=LONG
    )
    expect(filter_cell.locator(".wb-piece-page")).to_have_text(["Sales overview", "Page 2"])
    # The pages are saved inside the notebook's file.
    workbench.bring_to_front()
    workbench.keyboard.press("Control+s")
    expect(workbench.locator(".wb-tabs .tab-item.active")).not_to_contain_text("●")
    kept = json.loads(book.read_text())["metadata"]["swissarmygrid"]["streamlit"]["pages"]
    assert [(p["name"], [(s["cell"], s["w"]) for s in p["pieces"]]) for p in kept] == [
        ("Sales overview", [(3, 12), (2, 6)]),
        ("Page 2", [(2, 6)]),
    ]
    assert ["".join(c["source"]).split("\n")[0] for c in json.loads(book.read_text())["cells"]][1:] == [
        "# %% [streamlit]",
        "# %% [streamlit]",
    ]

    # ----- a grid step: the pieces go out of date; run: the new data
    step = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 50}}
    call(server, "POST", f"/grids/{orders}/steps", {"steps": [step]})
    expect(total_cell.locator(".wb-design-state")).to_have_text("Out of date · orders changed")
    expect(filter_cell.locator(".wb-design-state")).to_have_text("Out of date · orders changed")
    expect(total_cell).to_have_class(re.compile("stale"))
    designer.locator(".dz-tab").first.click()
    expect(designer.locator(".dz-run")).to_have_text("Out of date · Run")
    expect(metric(designer.frame_locator(".dz-frame"))).to_have_text(
        "145", timeout=LONG
    )  # nothing ran by itself
    total_cell.locator(".wb-design-run").click()
    expect(total_cell.locator(".wb-design-state")).to_be_hidden(timeout=LONG)
    # The piece kept its widget's choice (West, picked above) and reads the new data: 250, not 260.
    expect(metric(piece(total_cell))).to_have_text("250", timeout=LONG)
    expect(metric(designer.frame_locator(".dz-frame"))).to_have_text("100", timeout=LONG)  # East, over 50
    expect(designer.locator(".dz-run")).not_to_have_text("Out of date · Run")

    # ----- the whole app in its own window
    with designer.expect_popup() as app_window:
        designer.get_by_role("button", name="Open app").click()
    app = app_window.value
    whole = app.frame_locator(".dz-frame")
    expect(metric(whole)).to_have_text("100", timeout=LONG)
    expect(whole.locator('[data-testid="stSidebar"]').get_by_text("Page 2")).to_be_visible()
    whole.locator('[data-testid="stSidebar"]').get_by_text("Page 2").click()
    expect(metric(whole)).to_have_count(0)
    expect(whole.locator('[data-testid="stSelectbox"]')).to_be_visible()
    app.close()

    # ----- export as Streamlit app, into a folder picked with the file chooser
    target = tmp_path / "exported"
    target.mkdir()
    workbench.get_by_role("button", name="Streamlit app").click()
    workbench.get_by_role("menuitem", name="Export as Streamlit app…").click()
    folder = workbench.locator(".file-chooser input[aria-label=Folder]")
    folder.fill(str(target))
    folder.press("Enter")
    expect(workbench.locator(".file-chooser [role=status]")).to_have_text("0 folders, 0 files")
    workbench.get_by_role("button", name="Choose this folder").click()
    expect(workbench.locator(".toast", has_text="streamlit run app.py")).to_be_visible(timeout=LONG)
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "README.txt",
        "app.py",
        "app_pages/page_2.py",
        "app_pages/sales_overview.py",
        "data/orders.parquet",
        "requirements.txt",
    ]
    assert pd.read_parquet(target / "data" / "orders.parquet")["amount"].tolist() == [100, 250, 75]
    assert (target / "requirements.txt").read_text().split() == ["streamlit>=1.36", "pandas", "pyarrow"]
    # The exported app runs with nothing of this app beside it, and its pages answer.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("SWISSARMYGRID", "PYTHONPATH"))}
    process = subprocess.Popen(  # noqa: S603 (the exported app, in the test's own Streamlit Python)
        [
            STREAMLIT_PYTHON,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        cwd=target,
        env=environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(300):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as answer:
                    if answer.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        for path in ("", "sales_overview", "page_2"):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/{path}", timeout=20) as answer:
                assert answer.status == 200 and b"<title>" in answer.read()
        exported = browser.new_context(viewport={"width": 1200, "height": 800}).new_page()
        exported.goto(f"http://127.0.0.1:{port}/")
        expect(exported.locator('[data-testid="stMetricValue"]')).to_have_text("100", timeout=LONG)
        exported.locator('[data-testid="stSelectbox"] input').click()
        exported.get_by_role("option", name="West").click()
        expect(exported.locator('[data-testid="stMetricValue"]')).to_have_text("250")
        box = exported.locator('[data-testid="stMetricValue"]').bounding_box()
        select = exported.locator('[data-testid="stSelectbox"]').bounding_box()
        assert box is not None and select is not None and box["y"] < select["y"]  # laid out as designed
        exported.goto(f"http://127.0.0.1:{port}/page_2")
        expect(exported.locator('[data-testid="stSelectbox"]')).to_be_visible(timeout=LONG)
        exported.close()
    finally:
        process.terminate()
        process.wait(timeout=20)

    # ----- closing the notebook stops its Streamlit process and removes its temporary folder
    state = call(server, "GET", f"/streamlit/apps/{cells['app']}")
    assert state["running"] is True and Path(state["folder"]).is_dir()
    workbench.locator(".wb-tabs .tab-close").first.click()
    for _ in range(100):
        if not Path(state["folder"]).exists():
            break
        time.sleep(0.1)
    assert not Path(state["folder"]).exists()
    assert call(server, "GET", "/streamlit/apps")["apps"] == []
    designer.close()
    workbench.close()


def test_a_python_without_streamlit_says_so_with_install(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    """This app's own Python has no Streamlit (it is not a dependency): the cell says what is missing
    and offers Install, and nothing else happens."""
    if STREAMLIT_PYTHON is not None and STREAMLIT_PYTHON == os.path.realpath(sys.executable):
        pytest.skip("this Python happens to have Streamlit")
    book = tmp_path / "plain.ipynb"
    notebook_with_python(server, book, None)
    workbench = open_workbench(browser, server, book)
    cell = add_piece(workbench, 1, FILTER)
    workbench.keyboard.press("Control+Enter")
    expect(cell.locator(".wb-design-notes")).to_contain_text("streamlit", timeout=LONG)
    expect(cell.locator(".wb-design-notes")).to_contain_text("not installed in this document's Python")
    expect(cell.get_by_role("button", name="Install")).to_be_visible()
    expect(cell.locator(".wb-design-state")).to_have_text("Not run yet")
    expect(cell.locator(".monaco-editor")).to_be_visible()  # nothing to show: its code stays
    state = window(server, "streamlit.list")
    assert state["running"] is False and state["problem"]["kind"] == "missing"
    assert "streamlit" in state["problem"]["packages"]
    # The kind picker, the palette and the command-mode key all make a Streamlit cell.
    workbench.locator(".wb-toolbar").get_by_role("button", name="Python", exact=True).click()
    plain = workbench.locator(".wb-cell").nth(2)
    expect(plain.locator("select[aria-label='Cell kind'] option")).to_have_text(
        ["Python", "SQL", "HTML", "Streamlit", "Markdown"]
    )
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("t")
    expect(plain).to_have_class(re.compile("kind-streamlit"))
    workbench.keyboard.press("y")
    expect(plain).to_have_class(re.compile("kind-code"))
    workbench.keyboard.press("Control+Shift+P")
    workbench.locator(".wb-palette-input").fill("streamlit")
    expect(workbench.locator(".wb-palette-item .wb-palette-title")).to_contain_text(
        ["Make it a Streamlit cell", "Add a Streamlit cell (a piece)", "Run or refresh the Streamlit app"]
    )
    workbench.keyboard.press("Escape")
    workbench.close()


@needs_streamlit
def test_a_scripts_streamlit_cells_are_pieces_and_its_pages_are_a_block_of_comments(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    assert STREAMLIT_PYTHON is not None
    script = tmp_path / "sales.py"
    script.write_text("# %%\nx = 1\n", encoding="utf-8")
    call(server, "POST", "/workbench/environment", {"path": str(script), "python": STREAMLIT_PYTHON})
    workbench = open_workbench(browser, server, script)
    expect(workbench.locator(".wb-script .monaco-editor")).to_be_visible(timeout=20000)
    # The agent's door, as the toolbar's Streamlit button does it: a `# %% [streamlit]` cell of plain Python.
    window(server, "streamlit.add", source=FILTER)
    added = window(server, "streamlit.add", source=TOTAL)
    assert [c["name"] for c in added["cells"]] == ["Region filter", "Total"]
    text = window(server, "doc.read")["text"]
    assert "# %% [2] [streamlit]\n# Region filter\n" in text and "# %% [3] [streamlit]\n# Total\n" in text
    ran = window(server, "streamlit.run")
    assert ran["running"] is True and {c["state"] for c in ran["cells"]} == {"current"}
    # The cursor elsewhere: each piece shows live under its marker, its lines put away.
    workbench.locator(".wb-script .monaco-editor").click(position={"x": 200, "y": 30})
    panes = workbench.locator(".wb-design.in-script")
    expect(panes).to_have_count(2, timeout=LONG)
    expect(metric(panes.nth(1).frame_locator(".wb-piece-frame"))).to_have_text("145", timeout=LONG)
    expect(workbench.locator(".wb-script .view-lines")).not_to_contain_text("st.metric")
    # Pushed to a page: the page is kept in the file's own block of comments, and the file is still Python.
    pushed = window(server, "streamlit.push", number=3, name="Sales overview")
    window(server, "streamlit.push", number=2, page=pushed["page"])
    for _ in range(50):
        text = window(server, "doc.read")["text"]
        if text.count('"cell"') == 2:
            break
        time.sleep(0.1)
    block = text[text.index("[streamlit-pages]") :]
    assert block.split("\n")[1].startswith("# The pages of this file's Streamlit app")
    page = json.loads(block.split("\n")[2][2:])
    assert page["name"] == "Sales overview" and [s["cell"] for s in page["pieces"]] == [3, 2]
    compile(text, "sales.py", "exec")
    # Saved and opened again: the pages come back from the block.
    workbench.keyboard.press("Control+s")
    expect(workbench.locator(".wb-tabs .tab-item.active")).not_to_contain_text("●")
    opened = call(server, "POST", "/streamlit/apps", {"path": str(script)}, agent=True)
    assert [p["name"] for p in opened["pages"]] == ["Sales overview"]
    assert [p["cell"] for p in opened["pieces"]] == [2, 3]
    workbench.close()
