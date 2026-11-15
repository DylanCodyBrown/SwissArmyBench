# ruff: noqa: F811
"""The Streamlit canvas (docs/ideas.md, 2026-11-15), in a real browser and with the real Streamlit:
two notebook cells that call Streamlit, live in their cells; a new app's canvas as a tab; the cells
dragged onto it, moved and resized on the 12-column grid; Play showing the live page in place, the
filter driving the total; Edit; a cell edited in the notebook making the page out of date, and Play
giving the new code; a third cell copied and pasted; the app saved, closed and opened again; a cell
deleted (the block says so in red); Export and Save as. And a script's cells that call Streamlit.

Streamlit is not this app's dependency: these tests run when SWISSARMYGRID_STREAMLIT_PYTHON names a
Python with streamlit, pandas and pyarrow, and are skipped otherwise. Made-up data only.

With SWISSARMYGRID_SHOTS set to a folder, the first test also saves screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, FrameLocator, Locator, Page, expect

from swissarmygrid.client import push_client
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import menu
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'
NOTE = '# Note\nst.caption("Made-up orders")'
ORDERS = pd.DataFrame(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [100, 250, 40, 75, 10, 5],
    }
)
LONG = 60000  # Streamlit's first start, in milliseconds
SHOTS = os.environ.get("SWISSARMYGRID_SHOTS")


def open_window(browser: Browser, server: dict[str, Any], path: Path | None = None) -> Page:
    """The Workbench window by its address (with a file to open), in a browser context of its own."""
    context = browser.new_context(
        viewport={"width": 1500, "height": 950}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    opened = f"&open={quote(str(path))}" if path else ""
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}{opened}")
    expect(page.locator(".wb-tab" if path else ".wb-welcome").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.wait_for_timeout(400)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def live(cell: Locator) -> FrameLocator:
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


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[str]:
    close_tables(server)
    url = push_client.push(ORDERS, name="orders", new_grid=True)
    yield url.rsplit("/g/", 1)[1].split("#")[0]
    for app in call(server, "GET", "/streamlit/apps")["apps"]:
        call(server, "DELETE", f"/streamlit/apps/{app['app']}")
    close_tables(server)


def saved_notebook(server: dict[str, Any], path: Path, python: str | None, sources: list[str]) -> None:
    """A saved notebook of Python cells whose environment is `python` (None: this app's own)."""
    cells = [{"kind": "code", "source": source} for source in sources]
    call(server, "POST", "/workbench/save", {"path": str(path), "cells": cells})
    if python:
        call(server, "POST", "/workbench/environment", {"path": str(path), "python": python})


def blocks_of(server: dict[str, Any]) -> list[tuple[Any, ...]]:
    state = window(server, "canvas.state")
    page = next(p for p in state["pages"] if p["id"] == state["page"])
    return [(b["cell"], b["row"], b["column"], b["w"], b["h"]) for b in page["blocks"]]


def choose(workbench: Page, folder: Path, name: str | None, button: str) -> None:
    """The file chooser: go to a folder, name the file (a save), and choose."""
    where = workbench.locator(".file-chooser input[aria-label=Folder]")
    where.fill(str(folder))
    where.press("Enter")
    expect(workbench.locator(".file-chooser [role=status]")).to_contain_text("folder")
    if name is not None:
        workbench.locator(".file-chooser input[aria-label='File name']").fill(name)
    workbench.locator(".file-chooser").get_by_role("button", name=button).click()


@needs_streamlit
def test_cells_dragged_onto_a_canvas_play_live_in_place_and_are_saved(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    assert STREAMLIT_PYTHON is not None
    book = tmp_path / "sales.ipynb"
    saved_notebook(server, book, STREAMLIT_PYTHON, [FILTER, TOTAL, NOTE])
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    tabs = workbench.locator(".wb-tab")

    # ----- any Python cell: the ones that call Streamlit are live in their cells; there is no kind
    expect(cells.nth(1)).to_have_class(re.compile("kind-code"))
    expect(cells.nth(1)).to_have_class(re.compile("kind-streamlit"))  # the look of a live cell
    expect(cells.nth(1).locator("select[aria-label='Cell kind'] option")).to_have_text(
        ["Python", "SQL", "DAX", "HTML", "Markdown"]
    )
    expect(cells.nth(1).locator(".wb-design-state")).to_have_text("Not run yet")
    cells.nth(1).locator(".monaco-editor").click()
    workbench.keyboard.press("Control+Enter")
    expect(metric(live(cells.nth(1)))).to_have_text("145", timeout=LONG)  # East: 100 + 40 + 5
    expect(live(cells.nth(1)).get_by_text("region comes from cell 1")).to_be_visible()
    listed = window(server, "streamlit.list")
    assert [(c["number"], c["name"], c["makes"], c["state"]) for c in listed["cells"]] == [
        (1, "Region filter", ["region"], "current"),
        (2, "Total", [], "current"),
        (3, "Note", [], "current"),
    ]

    # ----- a new app: a canvas, as a tab beside the notebook
    menu(workbench, "Workbench menu", "New Streamlit app")
    expect(tabs).to_have_count(2)
    expect(workbench.locator(".cv-empty")).to_have_text("Drag a Python cell here")
    expect(workbench.get_by_role("button", name="Push to page")).to_have_count(0)
    # Edit | Play: one pair, Edit the mode in front. The status bar has no word for the tab's kind.
    edit_mode = workbench.get_by_role("button", name="Edit", exact=True)
    play_mode = workbench.get_by_role("button", name="Play", exact=True)
    expect(edit_mode).to_have_attribute("aria-pressed", "true")
    expect(play_mode).to_have_attribute("aria-pressed", "false")
    expect(workbench.locator(".wb-status")).not_to_contain_text("Streamlit app")
    tabs.nth(0).click()

    # ----- drag two cells onto the canvas (its tab: both are tabs of one window): links, not copies
    cells.nth(1).locator(".wb-number").drag_to(tabs.nth(1))
    cells.nth(0).locator(".wb-number").hover()
    workbench.mouse.down()
    tab = tabs.nth(1).bounding_box()
    assert tab is not None
    workbench.mouse.move(tab["x"] + 30, tab["y"] + 10, steps=6)
    shot(workbench, "1-a-cell-dragged-onto-the-canvas-tab")
    workbench.mouse.up()
    tabs.nth(1).click()
    blocks = workbench.locator(".cv-block")
    expect(blocks).to_have_count(2)
    # Each block: the cell's first comment, its file and @cell number, what it makes and reads.
    expect(blocks.nth(0).locator(".cv-block-name")).to_have_text("Total")
    expect(blocks.nth(0).locator(".cv-block-where")).to_have_text("sales.ipynb @cell2")
    expect(blocks.nth(0).locator(".cv-block-parts")).to_have_text("reads orders, region")
    expect(blocks.nth(1).locator(".cv-block-parts")).to_have_text("makes region · reads orders")
    assert blocks_of(server) == [(2, 1, 1, 6, None), (1, 1, 7, 6, None)]  # the second beside the first

    # ----- move and resize on the 12-column grid: the filter BELOW the total, four columns wide
    board = workbench.locator(".cv-board")
    box = board.bounding_box()
    assert box is not None
    blocks.nth(1).drag_to(board, target_position={"x": 40, "y": box["height"] - 30})
    expect(blocks.nth(1)).to_have_attribute("data-row", "2")
    blocks.nth(1).locator(".cv-grip").focus()
    for width in ("5", "4"):  # the keyboard stays on the grip through each change
        workbench.keyboard.press("ArrowLeft")
        expect(blocks.nth(1)).to_have_attribute("data-w", width)
        expect(blocks.nth(1).locator(".cv-grip")).to_be_focused()
    blocks.nth(0).locator(".cv-grip").focus()
    for wide in range(7, 13):
        workbench.keyboard.press("ArrowRight")
        expect(blocks.nth(0)).to_have_attribute("data-w", str(wide))
        expect(blocks.nth(0).locator(".cv-grip")).to_be_focused()
    assert blocks_of(server) == [(2, 1, 1, 12, None), (1, 2, 1, 4, None)]
    shot(workbench, "2-blocks-on-the-12-column-grid")

    # ----- Play: the live page, in place. The filter drives the total, though it sits below it.
    workbench.get_by_role("button", name="Play", exact=True).click()
    page = workbench.frame_locator(".cv-frame")
    expect(metric(page)).to_have_text("145", timeout=LONG)
    expect(board).to_be_hidden()
    assert is_above(metric(page), page.locator('[data-testid="stSelectbox"]'))
    pick(page, workbench, "West")
    expect(metric(page)).to_have_text("260")
    # Play is the mode in front now, not Edit.
    expect(play_mode).to_have_attribute("aria-pressed", "true")
    expect(edit_mode).to_have_attribute("aria-pressed", "false")
    # The status bar: the Python the app runs in (the linked notebook's own).
    expect(workbench.locator(".wb-app-python")).to_have_attribute("title", STREAMLIT_PYTHON)
    shot(workbench, "3-the-live-page-after-play")

    # ----- Edit goes back to the blocks; Play again shows the page
    workbench.get_by_role("button", name="Edit", exact=True).click()
    expect(blocks).to_have_count(2)
    expect(workbench.locator(".cv-frame")).to_be_hidden()
    workbench.get_by_role("button", name="Play", exact=True).click()
    expect(metric(page)).to_have_text("145", timeout=LONG)

    # ----- a linked cell edited in the notebook (not saved): out of date; nothing runs by itself
    tabs.nth(0).click()
    cells.nth(1).locator(".wb-number").click()  # its code shows again
    cells.nth(1).locator(".monaco-editor").click()
    workbench.keyboard.press("Control+a")
    workbench.keyboard.insert_text(TOTAL.replace('"Total"', '"Sum of amount"'))
    tabs.nth(1).click()
    stale = workbench.locator(".cv-play")
    expect(stale).to_have_text("Out of date · Play", timeout=20000)
    expect(page.locator('[data-testid="stMetricLabel"]')).to_have_text("Total")
    shot(workbench, "4-out-of-date")
    stale.click()
    expect(page.locator('[data-testid="stMetricLabel"]')).to_have_text("Sum of amount", timeout=LONG)
    expect(workbench.locator(".cv-play")).to_have_text("Play")

    # ----- copy a third cell (C in command mode) and paste it on the canvas (Ctrl+V)
    tabs.nth(0).click()
    cells.nth(2).locator(".wb-number").click()
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("c")
    tabs.nth(1).click()
    workbench.get_by_role("button", name="Edit", exact=True).click()
    board.click(position={"x": 700, "y": box["height"] - 20})
    workbench.keyboard.press("Control+v")
    expect(blocks).to_have_count(3)
    expect(blocks.nth(2).locator(".cv-block-name")).to_have_text("Note")
    assert blocks_of(server)[2][:3] == (3, 2, 5)  # beside the filter: the row has room
    # Pasted into the notebook, the same copy is the cell itself.
    tabs.nth(0).click()
    cells.nth(2).locator(".wb-number").click()
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("v")
    expect(cells).to_have_count(4)
    assert window(server, "doc.read")["cells"][3]["source"] == NOTE
    window(server, "cell.delete", index=3)

    # ----- a second page; the app saved as its own file, closed and opened again
    tabs.nth(1).click()
    workbench.get_by_role("button", name="New page").click()
    expect(workbench.locator(".cv-tab")).to_have_count(2)
    workbench.locator(".cv-tab").nth(1).dblclick()
    workbench.locator(".cv-rename").fill("Notes")
    workbench.locator(".cv-rename").press("Enter")
    tabs.nth(0).click()
    cells.nth(2).locator(".wb-number").drag_to(tabs.nth(1))
    tabs.nth(1).click()
    expect(blocks).to_have_count(1)
    shot(workbench, "6-two-pages")
    expect(tabs.nth(1)).to_contain_text("●")
    workbench.keyboard.press("Control+s")
    choose(workbench, tmp_path, "sales", "Save here")
    expect(tabs.nth(1)).to_have_text(re.compile(r"^sales\.stapp\.json"))
    expect(tabs.nth(1)).not_to_contain_text("●")
    held = json.loads((tmp_path / "sales.stapp.json").read_text())
    assert [p["name"] for p in held["pages"]] == ["Page 1", "Notes"]
    assert held["pages"][0]["blocks"] == [
        {"document": "sales.ipynb", "cell": 2, "row": 1, "column": 1, "width": 12, "height": None},
        {"document": "sales.ipynb", "cell": 1, "row": 2, "column": 1, "width": 4, "height": None},
        {"document": "sales.ipynb", "cell": 3, "row": 2, "column": 5, "width": 6, "height": None},
    ]
    assert "st.metric" not in (tmp_path / "sales.stapp.json").read_text()  # links: no code
    tabs.nth(1).get_by_role("button", name="Close").click()
    expect(tabs).to_have_count(1)
    window(server, "file.open", path=str(tmp_path / "sales.stapp.json"))
    expect(tabs).to_have_count(2)
    expect(blocks).to_have_count(3)
    expect(workbench.locator(".cv-tab")).to_have_text(["Page 1", "Notes"])

    # ----- Export: a folder that runs alone
    target = tmp_path / "exported"
    target.mkdir()
    workbench.get_by_role("button", name="Export…").click()
    choose(workbench, target, None, "Choose this folder")
    expect(workbench.locator(".toast", has_text="streamlit run app.py")).to_be_visible(timeout=LONG)
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "README.txt",
        "app.py",
        "app_pages/notes.py",
        "app_pages/page_1.py",
        "data/orders.parquet",
        "requirements.txt",
    ]
    assert '"Sum of amount"' in (target / "app_pages" / "page_1.py").read_text()  # the cell as it is now

    # ----- Save as: the project as one zip (data.py, pages/*.py, the canvas, the notebook); no rows
    workbench.get_by_role("button", name="Save as zip…").click()
    choose(workbench, tmp_path, "sales-app.zip", "Save here")
    expect(workbench.locator(".toast", has_text="sales-app.zip")).to_be_visible(timeout=LONG)
    with zipfile.ZipFile(tmp_path / "sales-app.zip") as zipped:
        names = sorted(zipped.namelist())
        page_text = zipped.read("pages/page_1.py").decode()
    assert names == [
        "README.txt",
        "data.ipynb",
        "data.py",
        "pages/notes.py",
        "pages/page_1.py",
        "requirements.txt",
        "sales.ipynb",
        "sales.stapp.json",
    ]
    assert page_text.startswith(
        "# Page 1\n"
        "# Written from sales.stapp.json by SwissArmyGrid: change the canvas, not this file.\n"
        "import pandas as pd\nimport streamlit as st\n\nfrom data import orders\n"
    )
    assert not any(name.endswith(".parquet") for name in names)

    # ----- a linked cell deleted in the notebook: its block says so, in red
    tabs.nth(0).click()
    window(server, "cell.delete", index=2)
    tabs.nth(1).click()
    workbench.locator(".cv-tab").nth(0).click()
    gone = workbench.locator(".cv-block.gone")
    expect(gone).to_have_count(1, timeout=20000)
    expect(gone.locator(".cv-block-missing")).to_have_text(f"sales.ipynb has no Python cell 3 now ({book}).")
    shot(workbench, "5-a-missing-cell")

    # ----- the dark theme: the canvas's colours are the theme's tokens; the live page is Streamlit's dark
    workbench.emulate_media(color_scheme="dark")
    expect(workbench.locator("html")).to_have_attribute("data-theme", "dark")
    expect(edit_mode).to_have_attribute("aria-pressed", "true")
    shot(workbench, "7-dark-theme-blocks")
    play_mode.click()
    expect(metric(page)).to_have_text("145", timeout=LONG)
    assert "embed_options=dark_theme" in (workbench.locator(".cv-frame").get_attribute("src") or "")
    shot(workbench, "8-dark-theme-live-page")
    workbench.close()


def test_a_python_without_streamlit_says_so_with_install(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    """This app's own Python has no Streamlit (it is not a dependency): the cell says what is missing
    and offers Install, and nothing else happens. The canvas says the same."""
    if STREAMLIT_PYTHON is not None and STREAMLIT_PYTHON == os.path.realpath(sys.executable):
        pytest.skip("this Python happens to have Streamlit")
    book = tmp_path / "plain.ipynb"
    saved_notebook(server, book, None, [FILTER, "total = 1 + 1\ntotal"])
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    cell = cells.nth(0)
    expect(cell).to_have_class(re.compile("kind-streamlit"))
    cell.locator(".monaco-editor").click()
    workbench.keyboard.press("Control+Enter")
    expect(cell.locator(".wb-design-notes")).to_contain_text("streamlit", timeout=LONG)
    expect(cell.locator(".wb-design-notes")).to_contain_text("not installed in this document's Python")
    expect(cell.get_by_role("button", name="Install")).to_be_visible()
    expect(cell.locator(".wb-design-state")).to_have_text("Not run yet")
    expect(cell.locator(".monaco-editor")).to_be_visible()  # nothing to show: its code stays
    state = window(server, "streamlit.list")
    assert state["running"] is False and state["problem"]["kind"] == "missing"
    assert "streamlit" in state["problem"]["packages"]
    # A plain Python cell is a plain cell: it runs in the kernel, and T makes nothing of it.
    expect(cells.nth(1)).not_to_have_class(re.compile("kind-streamlit"))
    cells.nth(1).locator(".monaco-editor").click()
    workbench.keyboard.press("Control+Enter")
    expect(cells.nth(1).locator(".wb-outputs")).to_contain_text("2", timeout=LONG)
    workbench.keyboard.press("Escape")
    workbench.keyboard.press("t")
    expect(cells.nth(1)).to_have_class(re.compile("kind-code"))
    # Typed into a plain cell, a call of Streamlit makes it live; taken out again, it is plain.
    cells.nth(1).locator(".monaco-editor").click()
    workbench.keyboard.press("Control+a")
    workbench.keyboard.insert_text('st.write("hello")')
    expect(cells.nth(1)).to_have_class(re.compile("kind-streamlit"), timeout=20000)
    workbench.keyboard.press("Control+a")
    workbench.keyboard.insert_text("total = 3")
    expect(cells.nth(1)).not_to_have_class(re.compile("kind-streamlit"), timeout=20000)
    # The palette has the canvas and no Streamlit kind of cell.
    workbench.keyboard.press("Control+Shift+P")
    workbench.locator(".wb-palette-input").fill("streamlit")
    titles = workbench.locator(".wb-palette-item .wb-palette-title")
    expect(titles).to_contain_text(["New Streamlit app"])
    expect(workbench.locator(".wb-palette-item", has_text="Make it a Streamlit cell")).to_have_count(0)
    workbench.keyboard.press("Escape")
    # On a canvas, Play says what is missing, with Install.
    menu(workbench, "Workbench menu", "New Streamlit app")
    workbench.locator(".wb-tab").nth(0).click()
    cells.nth(0).locator(".wb-number").drag_to(workbench.locator(".wb-tab").nth(1))
    workbench.locator(".wb-tab").nth(1).click()
    expect(workbench.locator(".cv-block")).to_have_count(1)
    workbench.get_by_role("button", name="Play", exact=True).click()
    expect(workbench.locator(".cv-problem")).to_contain_text("not installed", timeout=LONG)
    expect(workbench.locator(".cv-install")).to_be_visible()
    expect(workbench.locator(".cv-board")).to_be_visible()  # nothing to show: the blocks stay
    workbench.close()


@needs_streamlit
def test_a_scripts_cells_that_call_streamlit_are_live_and_an_old_marker_is_a_plain_cell(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    assert STREAMLIT_PYTHON is not None
    script = tmp_path / "sales.py"
    # A script saved when there was a Streamlit kind of cell, with its pages block.
    script.write_text(
        f"# %% [1]\nx = 1\n# %% [2] [streamlit]\n{FILTER}\n# %% [3] [streamlit] height=300\n{TOTAL}\n"
        '# %% [streamlit-pages]\n# {"id": "p1", "name": "Old", "pieces": [{"id": "s1", "cell": 3}]}\n',
        encoding="utf-8",
    )
    call(server, "POST", "/workbench/environment", {"path": str(script), "python": STREAMLIT_PYTHON})
    workbench = open_window(browser, server, script)
    expect(workbench.locator(".wb-script .monaco-editor")).to_be_visible(timeout=20000)
    # The markers read as plain cells (the height stays); the old pages block is left as comments.
    for _ in range(100):
        text = window(server, "doc.read")["text"]
        if "[streamlit]" not in text:
            break
        workbench.wait_for_timeout(100)
    assert f"# %% [2]\n{FILTER}\n# %% [3] height=300\n{TOTAL}\n" in text and '"name": "Old"' in text
    compile(text, "sales.py", "exec")
    cells = window(server, "streamlit.list")["cells"]
    assert [(c["number"], c["name"]) for c in cells] == [(2, "Region filter"), (3, "Total")]
    ran = window(server, "streamlit.run")
    assert ran["running"] is True and {c["state"] for c in ran["cells"]} == {"current"}
    # The cursor elsewhere: each live cell shows its page under its marker, its lines put away.
    workbench.locator(".wb-script .monaco-editor").click(position={"x": 200, "y": 30})
    panes = workbench.locator(".wb-design.in-script")
    expect(panes).to_have_count(2, timeout=LONG)
    expect(metric(panes.nth(1).frame_locator(".wb-piece-frame"))).to_have_text("145", timeout=LONG)
    expect(workbench.locator(".wb-script .view-lines")).not_to_contain_text("st.metric")
    # Copy cell (the palette's command) puts the script's cell on a canvas, as a link.
    assert window(server, "cell.copy", number=3) == {"cell": 3, "document": str(script)}
    window(server, "file.newApp")
    window(server, "cell.paste")
    expect(workbench.locator(".cv-block .cv-block-where")).to_have_text("sales.py @cell3")
    played = window(server, "canvas.play")
    assert played["mode"] == "live" and played["running"] is True
    expect(workbench.frame_locator(".cv-frame").get_by_text("reads region")).to_be_visible(timeout=LONG)
    workbench.close()


def test_named_cells_show_in_the_streamlit_cells_pane_and_drag_onto_a_canvas(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    book = tmp_path / "sales.ipynb"
    saved_notebook(server, book, None, [FILTER, TOTAL, NOTE, "threshold = 50"])
    workbench = open_window(browser, server, book)
    cells = workbench.locator(".wb-cell")
    # The pane lists the cells that call Streamlit (not the plain one), by their first comment line.
    pane = workbench.locator(".wb-st")
    entries = pane.locator(".wb-st-cell .wb-data-label")
    expect(entries).to_have_text(["Region filter", "Total", "Note"], timeout=20000)
    expect(pane.locator(".wb-st-doc-name")).to_have_text(["sales.ipynb"])
    # Name a cell in its head: a click on the name area, typed, Enter.
    cells.nth(0).locator(".wb-cell-head").hover()
    cells.nth(0).locator(".wb-cell-name").click()
    workbench.keyboard.type("Pick a region")
    workbench.keyboard.press("Enter")
    expect(cells.nth(0).locator(".wb-cell-name")).to_have_value("Pick a region")
    expect(cells.nth(0).locator(".wb-cell-name")).not_to_be_focused()
    # And by the palette's command, as the agent does: brackets and a hash are a name's own words.
    assert window(server, "cell.name", number=2, name="Sum [East] #1") == {"cell": 2, "name": "Sum [East] #1"}
    expect(cells.nth(1).locator(".wb-cell-name")).to_have_value("Sum [East] #1")
    expect(entries).to_have_text(["Pick a region", "Sum [East] #1", "Note"], timeout=20000)
    expect(pane.locator(".wb-st-cell .wb-data-meta").nth(0)).to_have_text("@cell1makes region · reads orders")
    # Drag an entry from the pane onto a new app's canvas: its block, called by the cell's name.
    window(server, "file.newApp")
    pane.locator(".wb-st-cell").nth(1).drag_to(workbench.locator(".cv-board"))
    blocks = workbench.locator(".cv-block")
    expect(blocks).to_have_count(1)
    expect(blocks.nth(0).locator(".cv-block-name")).to_have_text("Sum [East] #1")
    expect(blocks.nth(0).locator(".cv-block-where")).to_have_text("sales.ipynb @cell2")  # the number links
    # The entry on the canvas page in front has its mark; the agent sees the pane as it is.
    expect(pane.locator(".wb-st-cell.placed")).to_have_count(1)
    expect(pane.locator(".wb-st-cell").nth(1)).to_have_class(re.compile("placed"))
    shot(workbench, "9-named-cells-in-the-streamlit-cells-pane")
    listed = window(server, "data.streamlitCells")
    assert [c["name"] for d in listed["documents"] for c in d["cells"]] == [
        "Pick a region",
        "Sum [East] #1",
        "Note",
    ]
    assert listed["placed"] == [{"document": str(book), "cell": 2}]
    # A click on an entry goes to its cell.
    pane.locator(".wb-st-cell").nth(0).click()
    expect(workbench.locator(".wb-tab.active")).to_contain_text("sales.ipynb")
    expect(cells.nth(0)).to_have_class(re.compile("selected"))
    # Saved, the names are in the cells' metadata; renaming changed no link.
    workbench.keyboard.press("Control+s")
    expect(workbench.locator(".wb-tab.active")).not_to_contain_text("●")
    held = json.loads(book.read_text())["cells"]
    assert [c["metadata"]["swissarmygrid"].get("name") for c in held] == [
        "Pick a region",
        "Sum [East] #1",
        None,
        None,
    ]
    workbench.close()


def test_a_tab_pops_out_with_its_unsaved_text_and_kernel_and_a_cell_drops_across_windows(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    book = tmp_path / "sales.ipynb"
    saved_notebook(server, book, None, ["x = 41", TOTAL])
    first = open_window(browser, server, book)
    cells = first.locator(".wb-cell")
    # The kernel holds a value; the notebook has a change that is not saved (a cell's name).
    cells.nth(0).locator(".monaco-editor").click()
    first.keyboard.press("Control+Enter")
    expect(cells.nth(0).locator(".wb-count")).to_have_text("[1]", timeout=LONG)
    assert window(server, "cell.name", number=2, name="Total by region") == {
        "cell": 2,
        "name": "Total by region",
    }
    expect(first.locator(".wb-tab").nth(0)).to_contain_text("●")
    # Pop the tab out from its right-click menu: the popped window is a page of its own.
    with first.context.expect_page() as opened:
        first.locator(".wb-tab").nth(0).click(button="right")
        first.get_by_role("menuitem", name="Open in its own window").click()
    second = opened.value
    expect(second.locator(".wb-tab")).to_have_count(1, timeout=20000)
    # It MOVED: gone from the first window, here with its change and its numbers.
    expect(first.locator(".wb-tab")).to_have_count(0, timeout=20000)
    expect(second.locator(".wb-tab").nth(0)).to_contain_text("sales.ipynb")
    expect(second.locator(".wb-tab").nth(0)).to_contain_text("●")
    moved = second.locator(".wb-cell")
    expect(moved.nth(1).locator(".wb-cell-name")).to_have_value("Total by region")
    expect(moved.nth(1).locator(".wb-number")).to_have_text("#2")
    expect(moved.nth(0).locator(".wb-count")).to_have_text("[1]")  # its outputs and counts came too
    # The same kernel, still running: what it holds is there.
    moved.nth(1).locator(".monaco-editor").click()
    second.keyboard.press("Control+a")
    second.keyboard.insert_text("x + 1")
    second.keyboard.press("Control+Enter")
    expect(moved.nth(1).locator(".wb-outputs .wb-text")).to_have_text("42", timeout=LONG)
    # The popped window has the Data panel and its Streamlit cells pane, like any Workbench window.
    expect(second.locator(".wb-st")).to_be_visible()
    # A cell dropped onto a canvas in the other window. (Playwright cannot drag between two pages:
    # the drop is sent with the same data a cell's drag carries.)
    first.get_by_role("button", name="Start an app").click()
    board = first.locator(".cv-board")
    expect(board).to_be_visible()
    link = {"document": str(book), "cell": 1, "title": "sales.ipynb"}
    board.evaluate(
        """(board, link) => {
          const data = new DataTransfer();
          data.setData("application/x-swissarmygrid-cell", JSON.stringify(link));
          const box = board.getBoundingClientRect();
          for (const type of ["dragover", "drop"]) {
            const at = { clientX: box.left + 40, clientY: box.top + 40 };
            const event = { dataTransfer: data, bubbles: true, cancelable: true, ...at };
            board.dispatchEvent(new DragEvent(type, event));
          }
        }""",
        link,
    )
    expect(first.locator(".cv-block")).to_have_count(1, timeout=20000)
    expect(first.locator(".cv-block .cv-block-where")).to_have_text("sales.ipynb @cell1")
    # Each window keeps its own groups: the canvas here, the notebook there.
    expect(first.locator(".wb-tab")).to_have_count(1)
    expect(first.locator(".wb-tab").nth(0)).to_contain_text("Untitled app")
    # Moved back to the main window (the agent's command, sent to the window in front of the user).
    second.bring_to_front()
    second.evaluate("() => window.dispatchEvent(new Event('focus'))")
    with_back = window(server, "doc.moveToMain")
    assert with_back["window"] == "main"
    expect(first.locator(".wb-tab", has_text="sales.ipynb")).to_have_count(1, timeout=20000)
    expect(second.locator(".wb-tab")).to_have_count(0)
    second.close()
    first.close()


def test_a_project_opens_with_its_data_first(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    workbench = open_window(browser, server)
    made = window(server, "project.new", folder=str(tmp_path), name="sales", notebooks=["mockups"])
    assert [Path(p).name for p in made["files"]] == ["data.ipynb", "sales.stapp.json", "mockups.ipynb"]
    tabs = workbench.locator(".wb-tab")
    expect(tabs).to_have_text([re.compile(n) for n in ("data.ipynb", "sales.stapp.json", "mockups")])
    expect(tabs.nth(0)).to_have_class(re.compile("active"))  # the data is in front
    # The Data panel lists the project's files: data.py set in under data.ipynb, as its output.
    files = workbench.locator(".wb-files")
    expect(files).to_contain_text("sales/")
    expect(files.locator(".wb-files-list li")).to_have_text(
        [
            re.compile("data.ipynb"),
            re.compile("data.py"),
            re.compile("sales.stapp.json"),
            re.compile("mockups"),
        ]
    )
    # data.ipynb holds the table's read-only cell; the other notebook starts from data.py.
    assert [t["name"] for t in window(server, "tables.list")["tables"]] == ["orders"]
    window(server, "doc.show", index=2)
    assert window(server, "doc.read")["cells"][0]["source"] == "from data import orders"
    # A cell typed into data.ipynb (not saved) is in the export.
    window(server, "doc.show", index=0)
    window(server, "cell.insertBelow", source="big = 200")
    exported = window(server, "project.exportData")
    assert exported["names"] == ["orders", "big"] and exported["fill_in"] == ["orders"]  # sent from Python
    data = (tmp_path / "sales" / "data.py").read_text()
    assert "big = 200" in data and "# ===== FILL IN: orders =====" in data
    compile(data, "data.py", "exec")
    workbench.close()
