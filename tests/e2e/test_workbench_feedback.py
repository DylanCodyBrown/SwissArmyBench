# ruff: noqa: F811
"""The owner's feedback on the Workbench (2026-11-16), in a real browser: "new script and open should be
in the bar above along with the save and save as"; "Shouldnt cell 1 have the table inside of it?"; "the
cell should horizontally autoscale"; "differentiate with seperate icons the data notebook vs the app
notebooks"; "The first thing I did was go to scripts thinking that is where I could see the
transformations". Made-up data only.

With SWISSARMYBENCH_WBFEEDBACK_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_WBFEEDBACK_SHOTS")
TABLE = "orchard_q"
QUERY = (
    "SELECT * FROM (VALUES ('North', 14, 2.5), ('South', 9, 1.0), ('East', 31, 4.0), ('West', 3, 0.5))"
    " t(orchard, plums, acres)"
)
STEPS = [
    {"kind": "filter", "params": {"column": "plums", "op": "gt", "value": 5}},
    {"kind": "sort", "params": {"keys": [["plums", "desc"]]}},
]


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def window(server: dict[str, Any], command: str, **args: Any) -> Any:
    """A command of the Workbench window, as the agent sends it."""
    return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)["result"]


def workbench(
    browser: Browser, server: dict[str, Any], query: str = "", width: int = 1500, path: Path | None = None
) -> Page:
    page = browser.new_context(viewport={"width": width, "height": 950}, device_scale_factor=2).new_page()
    page.on("dialog", lambda d: d.accept())
    opened = f"&open={quote(str(path))}" if path else ""
    page.goto(f"http://127.0.0.1:{server['port']}/workbench{query}#token={server['token']}{opened}")
    expect(page.locator(".wb-codex")).to_be_visible(timeout=20000)  # the page's explorer (2026-11-21)
    return page


def close_tables(server: dict[str, Any]) -> None:
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")


@pytest.fixture
def orchard(server: dict[str, Any], tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A table made by a query (as the owner's query_1), two steps on its grid, and a project folder whose
    data.ipynb holds its read-only cell."""
    close_tables(server)
    made = call(server, "POST", f"/datasets/{TABLE}/query", {"sql": QUERY})
    grid = made["grid"]
    call(server, "POST", f"/grids/{grid}/steps", {"steps": STEPS})
    project = call(
        server,
        "POST",
        "/projects",
        {"folder": str(tmp_path), "name": "orchard", "app": False, "tables": [TABLE]},
    )
    folder = Path(project["folder"])
    yield {"grid": grid, "folder": folder, "data": folder / "data.ipynb"}
    close_tables(server)


def test_each_page_has_no_top_bar_an_explorer_and_its_own_new(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The owner (2026-11-21), on the Scripts landing: "scripts should open to on the page a new script
    creator
    just like it does but without all of this at the top. What it should have is a project file explorer"."""
    page = workbench(browser, server, "?kind=script&view=list")
    landing = page.locator(".wb-landing")
    expect(landing).to_be_visible(timeout=20000)
    expect(page.locator(".wb-top")).to_be_hidden()  # no project name, Save, New or Open strip
    explorer = page.locator(".wb-codex.page-scripts")
    expect(explorer).to_be_visible()
    expect(explorer).to_contain_text("No project is open.")
    # The creator: one sentence, New script, Try it with sample data.
    expect(landing.get_by_role("button", name="New script")).to_be_visible()
    expect(landing.get_by_role("button", name="Try it with sample data")).to_be_visible()
    shot(page, "scripts-landing")
    # Notebooks: its own creator and explorer, its menu's New only its kind.
    page.goto(f"http://127.0.0.1:{server['port']}/notebooks?kind=notebook&view=list#token={server['token']}")
    expect(page.locator(".wb-codex.page-notebooks")).to_be_visible(timeout=20000)
    expect(landing.get_by_role("button", name="New notebook")).to_be_visible()
    page.get_by_role("button", name="Workbench menu", exact=True).click()
    expect(page.get_by_role("menuitem", name="New script")).to_have_count(0)
    page.keyboard.press("Escape")
    # The creator's New makes the kind; the creator goes while one is open.
    page.goto(f"http://127.0.0.1:{server['port']}/scripts?kind=script&view=list#token={server['token']}")
    expect(landing).to_be_visible(timeout=20000)
    landing.get_by_role("button", name="New script").click()
    expect(landing).to_be_hidden()
    expect(page.locator(".wb-tab", has_text="Untitled script")).to_be_visible(timeout=20000)
    explorer.get_by_role("button", name="New script").click()
    expect(page.locator(".wb-tab")).to_have_count(2, timeout=20000)


def test_data_ipynbs_table_cell_opens_unfolded_runs_and_shows_its_table_first(
    browser: Browser, server: dict[str, Any], orchard: dict[str, Any]
) -> None:
    # A new project's data.ipynb: the table's cells only, no empty cell of the user's before them.
    saved = json.loads(orchard["data"].read_text(encoding="utf-8"))
    roles = [c["metadata"].get("swissarmybench", {}).get("role", "") for c in saved["cells"]]
    assert roles == ["tables", "table", "transformations"], roles
    page = workbench(browser, server, path=orchard["data"])
    cell = page.locator(".wb-tcell.role-transformations")
    # Unfolded: its code, numbered as a cell.
    expect(cell).to_be_visible(timeout=20000)
    expect(cell.locator(".view-lines")).to_contain_text(f"{TABLE} = duckdb.sql(", timeout=20000)
    expect(cell.locator(".wb-number")).to_have_text(re.compile(r"^#\d+$"))
    # It ran by itself (the kernel started for it), and shows the table: its rows, filtered and sorted.
    frame = cell.frame_locator("iframe.wb-html")
    expect(frame.locator("table")).to_be_visible(timeout=90000)
    expect(frame.locator("tbody tr")).to_have_count(3)
    expect(frame.locator("tbody tr").first).to_contain_text("East")
    expect(cell.locator(".wb-table-state")).to_be_hidden()
    expect(cell.locator(".wb-to-grid")).to_be_hidden()  # the grid has it open already
    # It is the first cell seen: nothing of the user's above it, and the document has no unsaved mark.
    order = page.locator(".wb-cells > section").evaluate_all(
        "els => els.map(e => e.classList.contains('role-transformations') ? 'table'"
        " : e.classList.contains('wb-cell') ? 'user' : 'app')"
    )
    assert order.index("table") < (order.index("user") if "user" in order else len(order)), order
    expect(page.locator(".wb-tab[aria-selected='true'] .wb-tab-dirty")).to_be_hidden()
    shot(page, "data-ipynb-table-cell")
    # Saved, the file holds no rows: the table is drawn again on opening.
    with page.expect_response(lambda r: "/workbench/save" in r.url, timeout=20000):
        window(server, "file.save")
    saved = json.loads(orchard["data"].read_text(encoding="utf-8"))
    assert all(not c.get("outputs") for c in saved["cells"] if c["cell_type"] == "code")


def test_a_table_output_is_readable_in_the_dark_theme(
    browser: Browser, server: dict[str, Any], orchard: dict[str, Any]
) -> None:
    """A table's frame says the theme's colour scheme. A frame whose scheme differs from its page's is given
    an opaque white backdrop by the browser: in the dark theme a DataFrame's light text stood on white."""
    context = browser.new_context(viewport={"width": 1500, "height": 950}, color_scheme="dark")
    page = context.new_page()
    page.on("dialog", lambda d: d.accept())
    opened = quote(str(orchard["data"]))
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}&open={opened}")
    cell = page.locator(".wb-tcell.role-transformations")
    frame = cell.frame_locator("iframe.wb-html")
    expect(frame.locator("table")).to_be_visible(timeout=90000)
    assert frame.locator("html").evaluate("e => getComputedStyle(e).colorScheme") == "dark"
    assert frame.locator("body").evaluate("e => getComputedStyle(e).color") == "rgb(232, 236, 239)"
    assert frame.locator("body").evaluate("e => getComputedStyle(e).backgroundColor") == "rgba(0, 0, 0, 0)"
    context.close()


def test_a_cell_is_as_wide_as_its_pane(browser: Browser, server: dict[str, Any]) -> None:
    page = workbench(browser, server, "", width=2200)
    window(server, "file.newNotebook")
    cell = page.locator(".wb-cell").first
    expect(cell).to_be_visible(timeout=20000)
    pane = page.locator(".wb-gbody").first

    def widths() -> tuple[float, float]:
        return (cell.bounding_box() or {"width": 0})["width"], (pane.bounding_box() or {"width": 0})["width"]

    wide, room = widths()
    assert wide > 1500 and room - wide < 80, (wide, room)
    page.set_viewport_size({"width": 1100, "height": 900})
    page.wait_for_timeout(300)
    narrow, room = widths()
    assert narrow < wide and room - narrow < 80, (narrow, room)


def test_the_data_notebook_has_an_icon_of_its_own(
    browser: Browser, server: dict[str, Any], orchard: dict[str, Any]
) -> None:
    folder: Path = orchard["folder"]
    plain = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (folder / "scratch.ipynb").write_text(json.dumps(plain), encoding="utf-8")
    (folder / "views.ipynb").write_text(
        json.dumps(
            {
                **plain,
                "cells": [
                    {
                        "cell_type": "code",
                        "source": "import streamlit as st\nst.write(1)",
                        "metadata": {"swissarmybench": {"number": 1}},
                        "outputs": [],
                        "execution_count": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app = {
        "swissarmybench": "streamlit-app",
        "version": 1,
        "pages": [
            {
                "id": "p1",
                "name": "Page 1",
                "blocks": [
                    {
                        "id": "b1",
                        "document": "views.ipynb",
                        "cell": 1,
                        "row": 1,
                        "column": 1,
                        "w": 12,
                        "h": None,
                    }
                ],
            }
        ],
    }
    (folder / "shop.stapp.json").write_text(json.dumps(app), encoding="utf-8")
    listed = call(server, "GET", "/project/documents")  # no project open: nothing listed
    assert listed["project"] is None
    page = workbench(browser, server)
    window(server, "project.open", folder=str(folder))

    def icon(title: str) -> Locator:
        return page.locator(".wb-tab", has_text=title).locator(".wb-tab-icon")

    expect(icon("data.ipynb")).to_have_attribute("data-icon", "notebook", timeout=30000)
    # Every notebook is a notebook (2026-11-22: "we just have notebooks"), data.ipynb too.
    expect(icon("scratch.ipynb")).to_have_attribute("data-icon", "notebook")
    expect(icon("views.ipynb")).to_have_attribute("data-icon", "notebook", timeout=20000)
    # The Data panel's files and the landing's cards wear them too.
    for title, name in (
        ("data.ipynb", "notebook"),
        ("scratch.ipynb", "notebook"),
        ("views.ipynb", "notebook"),
    ):
        expect(page.locator(".wb-file-open", has_text=title).locator("svg")).to_have_attribute(
            "data-icon", name
        )
    # The page's explorer (2026-11-21) lists the project's notebooks, each with its kind's icon.
    explorer = page.locator(".wb-codex.page-notebooks")
    views = explorer.locator(".wb-codex-file[data-path='views.ipynb'] svg").first
    expect(views).to_have_attribute("data-icon", "notebook", timeout=20000)
    data = explorer.locator(".wb-codex-file[data-path='data.ipynb'] svg").first
    expect(data).to_have_attribute("data-icon", "notebook")
    shot(page, "notebook-icons")


def test_the_landing_pages_have_no_transformations_and_no_data_panel(
    browser: Browser, server: dict[str, Any], orchard: dict[str, Any]
) -> None:
    """The owner (2026-11-17): "notebooks also has data panel on the left and transformations which is not
    needed"; on Scripts: "I see data on the left which is uneeded". A table's transformations live in
    data.ipynb, which the agent still opens at the table's cell."""
    page = workbench(browser, server, path=orchard["data"])
    expect(page.locator(".wb-tab", has_text="data.ipynb")).to_be_visible(timeout=20000)
    landing = page.locator(".wb-landing")
    for page_name in ("scripts", "notebooks"):
        page.goto(f"http://127.0.0.1:{server['port']}/{page_name}#token={server['token']}")
        expect(page.locator(f".wb-codex.page-{page_name}")).to_be_visible(timeout=20000)
        expect(landing.locator(".wb-landing-table")).to_have_count(0)
        expect(landing.get_by_role("heading", name="Transformations")).to_have_count(0)
        expect(page.locator(".wb-explorer")).to_be_hidden()  # the Data Explorer is off until opened
    expect(page.locator(".wb-tab", has_text="data.ipynb")).to_be_visible(
        timeout=20000
    )  # the project's, again
    shot(page, "notebooks-landing-no-data-panel")
    # The agent still opens a table's transformations: its read-only cell in data.ipynb.
    shown = window(server, "tables.transformations", table=TABLE)
    assert shown["table"] == TABLE and shown["cell"] and shown["document"].endswith("data.ipynb")
    expect(landing).to_be_hidden()
