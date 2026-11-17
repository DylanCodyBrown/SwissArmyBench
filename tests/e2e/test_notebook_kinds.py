# ruff: noqa: F811
"""Data notebooks and app notebooks, in a real browser (the owner, 2026-11-16: "I didnt see that data
notebooks and app notebooks had been seperated in the app yet. the data panel is nice but it should only
show on app notebooks its useless in a data notebook"). In a project data.ipynb is THE data notebook and
every other notebook an app notebook; outside a project a notebook is plain. Made-up data only.

With SWISSARMYBENCH_NBKINDS_SHOTS set to a folder, the tests also save screenshots there (2x)."""

from __future__ import annotations

import json
import os
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

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
    page.goto(f"http://127.0.0.1:{server['port']}/workbench{query}#token={server['token']}")
    expect(page.locator(".wb-top")).to_be_visible(timeout=20000)
    return page


@pytest.fixture
def orchard(server: dict[str, Any], tmp_path: Path) -> Path:
    """A made-up project: data.ipynb, two more notebooks (one a canvas uses, one not yet) and the canvas."""
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


def test_a_projects_notebooks_wear_their_kind_on_tabs_cards_and_files(
    browser: Browser, server: dict[str, Any], orchard: Path
) -> None:
    page = workbench(browser, server)
    window(server, "project.open", folder=str(orchard))
    for title, kind, word in (
        ("data.ipynb", "dataNotebook", "Data notebook"),
        ("pickers.ipynb", "appNotebook", "App notebook"),
        ("views.ipynb", "appNotebook", "App notebook"),
    ):
        expect(tab(page, title)).to_have_attribute("data-kind", kind, timeout=30000)
        expect(tab(page, title).locator(".wb-tab-icon")).to_have_attribute("data-icon", kind)
        expect(tab(page, title).locator(".wb-tab-icon")).to_have_attribute("title", word)
        expect(page.locator(".wb-file-open", has_text=title)).to_have_attribute("title", word)
    # The agent sees the same kinds.
    roles = {d["title"]: d.get("role") for d in window(server, "documents")["documents"]}
    assert roles["data.ipynb"] == "data" and roles["pickers.ipynb"] == "app", roles
    # The Notebooks page: the Transformations first (none here), then the two groups.
    page.locator(".nav-rail [data-area='notebooks']").click()
    landing = page.locator(".wb-landing")
    expect(landing).to_be_visible(timeout=20000)
    headings = landing.locator("h2.wb-landing-section")
    expect(headings).to_have_text(["Data notebook", "App notebooks"], timeout=20000)
    data_cards = landing.locator(".wb-landing-data .wb-landing-card")
    expect(data_cards).to_have_count(1)
    expect(data_cards.first).to_contain_text("data.ipynb")
    expect(data_cards.first.locator(".wb-landing-icon")).to_have_attribute("data-icon", "dataNotebook")
    expect(data_cards.first.locator(".wb-landing-icon")).to_have_attribute("title", "Data notebook")
    apps = landing.locator(".wb-landing-app .wb-landing-card")
    expect(apps).to_have_count(2)
    expect(apps.locator(".wb-landing-icon[data-icon='appNotebook']")).to_have_count(2)
    shot(page, "notebooks-page-two-groups")
    # New on that page makes an app notebook (the project has one data notebook).
    new = page.locator(".wb-top").get_by_role("button", name="New app notebook")
    expect(new).to_be_visible()
    new.click()
    expect(landing).to_be_hidden()
    made = tab(page, "Untitled notebook")
    expect(made).to_have_attribute("data-kind", "appNotebook", timeout=20000)
    expect(made.locator(".wb-tab-icon")).to_have_attribute("title", "App notebook")
    shot(page, "new-app-notebook")


def test_the_data_panel_is_beside_app_notebooks_and_canvases_not_the_data_notebook(
    browser: Browser, server: dict[str, Any], orchard: Path
) -> None:
    page = workbench(browser, server)
    window(server, "project.open", folder=str(orchard))
    panel = page.locator(".wb-data")
    expect(tab(page, "data.ipynb")).to_be_visible(timeout=30000)
    expect(tab(page, "shop.stapp.json").or_(tab(page, "shop"))).to_have_count(1, timeout=20000)
    tab(page, "data.ipynb").click()
    expect(panel).to_be_hidden()
    # Its fold is not offered there: not in the top bar's menu, not as a command.
    assert window(server, "documents")["panes"]["data_panel"] == "away"
    with pytest.raises(urllib.error.HTTPError) as refused:
        window(server, "view.toggleSidebar", collapsed=False)
    assert "not the data notebook" in refused.value.read().decode()
    page.locator(".wb-top button[aria-label='Workbench menu']").click()
    menu = page.get_by_role("menu")
    expect(menu).to_be_visible()
    expect(menu.get_by_text("the Data panel")).to_have_count(0)
    page.keyboard.press("Escape")
    shot(page, "data-notebook-no-data-panel")
    tab(page, "pickers.ipynb").click()
    expect(panel).to_be_visible()
    expect(panel.locator("[data-panel='tables']")).to_be_visible()
    shot(page, "app-notebook-data-panel")
    tab(page, "data.ipynb").click()
    expect(panel).to_be_hidden()
    tab(page, "shop.stapp.json").or_(tab(page, "shop")).click()
    expect(panel).to_be_visible()


def test_a_notebook_outside_a_project_is_plain(browser: Browser, server: dict[str, Any]) -> None:
    page = workbench(browser, server, "?kind=notebook&view=list")
    top = page.locator(".wb-top")
    expect(top.get_by_role("button", name="New notebook")).to_be_visible(timeout=20000)
    top.get_by_role("button", name="New notebook").click()
    made = tab(page, "Untitled notebook")
    expect(made).to_have_attribute("data-kind", "notebook", timeout=20000)
    expect(made.locator(".wb-tab-icon")).to_have_attribute("data-icon", "notebook")
    expect(page.locator(".wb-data")).to_be_visible()
