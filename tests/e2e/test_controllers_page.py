# ruff: noqa: F811
"""Controllers on the canvas (docs/ideas.md, "After the beta: controllers", 2026-11-15), in a real
browser and with the real Streamlit: a view whose filter is not on the page says, quietly, which default
it reads; Test this page runs AppTest in the notebook's own Python and turns the block that fails red
with the value that broke it; a view that filters a table shows its thin-cell hint, and Move to
data.ipynb puts those lines into a named cell of the project's data.ipynb, leaving one line that reads
them back. Made-up data only.

Streamlit is not this app's dependency: these run when SWISSARMYBENCH_STREAMLIT_PYTHON names a Python
with streamlit, pandas and pyarrow, and are skipped otherwise. With SWISSARMYBENCH_SHOTS set to a
folder, screenshots are saved there (2x)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_streamlit_page import open_window, orders, saved_notebook, shot  # noqa: F401
from tests.e2e.test_table_cells_page import window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_streamlit_apps import STREAMLIT_PYTHON, needs_streamlit

FILTER = """# Region filter
# Makes: region: str = "All"; by_region: table = orders
import streamlit as st

region = st.selectbox("Region", ["All", *sorted(orders["region"].unique())], key="region_pick")
by_region = orders if region == "All" else orders[orders["region"] == region]"""
TOTAL = """# Total for the region
import streamlit as st

if region == "North":
    raise KeyError("North has no target yet")
st.metric(f"Total ({region})", int(by_region["amount"].sum()))"""
BIG = """# Big orders
import streamlit as st

big = orders[orders["amount"] > 50]
st.dataframe(big, hide_index=True)"""


@needs_streamlit
def test_defaults_test_this_page_and_a_thin_cells_move(
    browser: Browser, server: dict[str, Any], orders: str, tmp_path: Path
) -> None:
    made = call(server, "POST", "/projects", {"folder": str(tmp_path), "name": "sales"})
    folder = Path(made["folder"])
    views = folder / "views.ipynb"
    saved_notebook(server, views, STREAMLIT_PYTHON, [FILTER, TOTAL, BIG])
    canvas = folder / "sales.stapp.json"
    page = open_window(browser, server, canvas)
    board = page.locator(".cv-board")
    expect(board).to_be_visible(timeout=20000)
    state = window(server, "canvas.state")
    app, page_id = state["app"], state["page"] or None
    if page_id is None:
        page_id = call(server, "POST", f"/streamlit/apps/{app}/pages", {"name": "Sales"})["page"]

    def place(cell: int, w: int = 6) -> None:
        body = {"document": str(views), "cell": cell, "w": w}
        call(server, "POST", f"/streamlit/apps/{app}/pages/{page_id}/blocks", body, agent=True)

    # The total alone: its filter is not on the page, so it reads the filter's defaults, said quietly.
    place(2)
    total = board.locator(".cv-block", has_text="Total for the region")
    expect(total.locator(".cv-block-default").first).to_have_text(
        "by_region = orders · Region filter is not on this page", timeout=20000
    )
    expect(total.locator(".cv-block-default").nth(1)).to_contain_text("region = 'All'")
    expect(total.locator("[role=alert]")).to_have_count(0)
    shot(page, "1-a-default-said-quietly")
    # The filter placed: no default now. Test this page: AppTest in the notebook's Python tries each
    # region; the total fails on North, and only it turns red.
    place(1)
    expect(total.locator(".cv-block-default")).to_have_count(0)
    page.get_by_role("button", name="Test this page").click()
    expect(board.locator(".cv-block.failed")).to_have_count(1, timeout=120000)
    expect(total.locator(".cv-block-failed")).to_have_text(
        "Region filter: Region = 'North': KeyError: 'North has no target yet'"
    )
    region = board.locator(".cv-block").filter(has=page.locator(".cv-block-name", has_text="Region filter"))
    expect(region.locator(".cv-block-failed")).to_have_count(0)
    expect(page.locator(".toast", has_text="1 block failed")).to_be_visible()
    shot(page, "2-test-this-page-a-block-fails")
    # The agent reads the same.
    tested = call(server, "GET", f"/streamlit/apps/{app}", agent=True)
    blocks = {b["cell"]: b for b in next(p for p in tested["pages"] if p["id"] == page_id)["blocks"]}
    assert blocks[2]["failures"][0]["case"] == "Region filter: Region = 'North'"
    assert (
        blocks[1]["controller"]["role"] == "filter"
        and blocks[1]["controller"]["makes"][0]["default"] == "'All'"
    )
    # The big orders: a view that filters a table. Its hint, and the move to data.ipynb.
    place(3, 12)
    big = board.locator(".cv-block", has_text="Big orders")
    expect(big.locator(".cv-block-thin")).to_contain_text("Filters a table: big", timeout=20000)
    shot(page, "3-a-thin-cell-hint")
    big.get_by_role("button", name="Move to data.ipynb").click()
    expect(page.locator(".toast", has_text="Moved to data.ipynb: big")).to_be_visible(timeout=20000)
    expect(big.locator(".cv-block-thin")).to_have_count(0, timeout=20000)
    # data.ipynb has the named cell; the view's cell reads it back in one line (both unsaved, as typed).
    page.locator(".wb-tab", has_text="data.ipynb").first.click()
    moved = page.locator(".wb-cell", has_text="big = orders[orders[")
    expect(moved).to_have_count(1, timeout=20000)
    shot(page, "4-moved-to-data-ipynb")
    page.locator(".wb-tab", has_text="views.ipynb").first.click()
    expect(page.locator(".wb-cell", has_text="from data import big")).to_have_count(1)
    page.context.close()
