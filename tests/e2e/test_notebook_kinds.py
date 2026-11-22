# ruff: noqa: F811
"""A project's notebooks, in a real browser: every notebook is a notebook (the owner, 2026-11-22: "in the
screenshot I still saw app notebooks and data notebooks, that concept is gone we just have notebooks"),
data.ipynb among them (app notebooks went, 2026-11-21: "Creating a widget is what will replace the concept of
app cells and app notebooks"). Opening an old app canvas (.stapp.json) says so in one line. Made-up data only.

With SWISSARMYBENCH_NBKINDS_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from tests.e2e.asks import accept_asks
from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_NBKINDS_SHOTS")
PLAIN = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def window(server: dict[str, Any], command: str, **args: Any) -> Any:
    return call(server, "POST", "/workbench/window", {"command": command, "args": args}, agent=True)["result"]


def workbench(browser: Browser, server: dict[str, Any], query: str = "") -> Page:
    page = browser.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=2).new_page()
    page.on("dialog", lambda d: d.accept())
    accept_asks(page)
    page.goto(f"http://127.0.0.1:{server['port']}/workbench{query}#token={server['token']}")
    expect(page.locator(".wb-codex")).to_be_visible(timeout=20000)  # its explorer (2026-11-21)
    return page


@pytest.fixture
def orchard(server: dict[str, Any], tmp_path: Path) -> Path:
    """A made-up project: data.ipynb, two more notebooks (one held a live Streamlit cell once) and an old
    app canvas (.stapp.json) from before widgets."""
    project = call(server, "POST", "/projects", {"folder": str(tmp_path), "name": "orchard", "app": False})
    folder = Path(project["folder"])
    (folder / "pickers.ipynb").write_text(json.dumps(PLAIN), encoding="utf-8")
    cell: dict[str, Any] = {
        "cell_type": "code",
        "source": "import streamlit as st\nst.write('plums')",
        "metadata": {"swissarmybench": {"number": 1}},
        "outputs": [],
        "execution_count": None,
    }
    (folder / "views.ipynb").write_text(json.dumps({**PLAIN, "cells": [cell]}), encoding="utf-8")
    block = {"id": "b1", "document": "views.ipynb", "cell": 1, "row": 1, "column": 1, "w": 12, "h": None}
    app = {
        "swissarmybench": "streamlit-app",
        "version": 1,
        "pages": [{"id": "p1", "name": "Page 1", "blocks": [block]}],
    }
    (folder / "shop.stapp.json").write_text(json.dumps(app), encoding="utf-8")
    return folder


def tab(page: Page, title: str) -> Locator:
    return page.locator(".wb-tab", has_text=title)


def test_a_projects_notebooks_are_all_notebooks_on_tabs_cards_and_files(
    browser: Browser, server: dict[str, Any], orchard: Path
) -> None:
    page = workbench(browser, server)
    window(server, "project.open", folder=str(orchard))
    for title in ("data.ipynb", "pickers.ipynb", "views.ipynb"):
        expect(tab(page, title)).to_have_attribute("data-kind", "notebook", timeout=30000)
        expect(tab(page, title).locator(".wb-tab-icon")).to_have_attribute("data-icon", "notebook")
        expect(tab(page, title).locator(".wb-tab-icon")).to_have_attribute("title", "Notebook")
    # The agent sees no role either: a notebook is a notebook.
    assert all("role" not in d for d in window(server, "documents")["documents"])
    # The Notebooks page's Files pane: one list, data.ipynb first, every one the notebook's icon.
    explorer = page.locator(".wb-codex.page-notebooks")
    heads = explorer.locator(".wb-codex-group-head > span:not(.wb-codex-count)")
    expect(heads).to_have_text(["Notebooks"], timeout=20000)
    files = explorer.locator(".wb-codex-group[data-group='notebooks'] .wb-codex-file")
    expect(files).to_have_count(3)
    expect(files.first).to_contain_text("data.ipynb")
    for i in range(3):
        expect(files.nth(i).locator("svg").first).to_have_attribute("data-icon", "notebook")
    expect(page.locator("svg[data-icon='appNotebook'], svg[data-icon='dataNotebook']")).to_have_count(0)
    expect(page.get_by_text("Data notebook", exact=True)).to_have_count(0)
    shot(page, "notebooks-page-one-list")
    # New on that page makes a plain notebook (never an app notebook).
    page.get_by_role("button", name="Workbench menu", exact=True).click()
    expect(page.get_by_role("menuitem", name="New app notebook")).to_have_count(0)
    page.get_by_role("menuitem", name="New notebook", exact=True).click()
    made = tab(page, "Untitled notebook")
    expect(made).to_have_attribute("data-kind", "notebook", timeout=20000)
    expect(made.locator(".wb-tab-icon")).to_have_attribute("title", "Notebook")
    # The notebook that held a live Streamlit cell is a plain notebook: its cell is code, never a live page.
    tab(page, "views.ipynb").click()
    expect(page.locator(".wb-cell.kind-streamlit")).to_have_count(0)
    expect(page.locator(".wb-cell.kind-code")).to_have_count(1)


def test_an_old_app_canvas_says_so_in_one_line(
    browser: Browser, server: dict[str, Any], orchard: Path
) -> None:
    """Opening an old .stapp.json (the agent's file.open, or the server's own open) says in one line that
    apps are built from widgets on the Canvas now: never a crash, never a tab."""
    page = workbench(browser, server)
    window(server, "project.open", folder=str(orchard))
    expect(page.locator(".wb-tab")).to_have_count(3, timeout=30000)  # its three notebooks, no canvas
    window(server, "file.open", path=str(orchard / "shop.stapp.json"))
    note = page.locator(".error-note, .toast").filter(has_text="replaced by widgets")
    expect(note.first).to_be_visible(timeout=10000)
    expect(page.locator(".wb-tab")).to_have_count(3)
    with pytest.raises(urllib.error.HTTPError) as said:
        call(server, "POST", "/workbench/open", {"path": str(orchard / "shop.stapp.json")})
    assert "replaced by widgets" in said.value.read().decode()


def test_the_data_explorer_is_beside_every_document(
    browser: Browser, server: dict[str, Any], orchard: Path
) -> None:
    """The Data panel was only beside app notebooks and canvases (2026-11-16); the Data Explorer that
    took its place (2026-11-17) is beside every document once opened: the data notebook, another notebook."""
    page = workbench(browser, server)
    window(server, "project.open", folder=str(orchard))
    panel = page.locator(".wb-explorer")
    expect(tab(page, "data.ipynb")).to_be_visible(timeout=30000)
    tab(page, "data.ipynb").click()
    expect(panel).to_be_hidden()  # off until opened
    assert window(server, "documents")["panes"]["data_explorer"] == "closed"
    assert window(server, "view.explorer", show=True) == {"open": True, "popped": False}
    expect(panel).to_be_visible()
    shot(page, "data-notebook-data-explorer")
    tab(page, "pickers.ipynb").click()
    expect(panel).to_be_visible()
    assert window(server, "documents")["panes"]["data_explorer"] == "open"


def test_a_notebook_outside_a_project_is_plain(browser: Browser, server: dict[str, Any]) -> None:
    page = workbench(browser, server, "?kind=notebook&view=list")
    new = page.locator(".wb-landing").get_by_role("button", name="New notebook")
    expect(new).to_be_visible(timeout=20000)
    new.click()
    made = tab(page, "Untitled notebook")
    expect(made).to_have_attribute("data-kind", "notebook", timeout=20000)
    expect(made.locator(".wb-tab-icon")).to_have_attribute("data-icon", "notebook")
    expect(page.locator(".wb-explorer-toggle")).to_be_visible()
