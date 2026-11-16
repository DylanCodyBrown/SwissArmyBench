# ruff: noqa: F811
"""Projects as one .sab file in a real browser (the owner, 2026-11-16): the home page's Start view (the
recent projects, Open project…), a reload keeps it, Home brings it back; Save clears the unsaved mark;
saving the open work offers "Keep its rows in the file" for a pasted table. New project is saved first,
then Autosave, then its Grids; the tour is offered on the Start page only; a notebook is imported from
another .sab in the Workbench. Made-up data only."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

STEP = {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "East"}}


@pytest.fixture
def fresh(server: dict[str, Any]) -> Iterator[Path]:
    """No project and no table open; a folder of made-up files of the test's own."""
    call(server, "POST", "/project/close", {"discard": True}) if call(server, "GET", "/project")[
        "project"
    ] else None
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    folder = Path(server["tmp"]) / f"sab_{len(list(Path(server['tmp']).glob('sab_*')))}"
    folder.mkdir()
    (folder / "orders.csv").write_text(
        "order_id,region,units\n1,North,3\n2,East,9\n3,South,5\n4,North,7\n", encoding="utf-8"
    )
    yield folder
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})


def home(browser: Browser, server: dict[str, Any], view: str = "") -> Page:
    page = browser.new_context(viewport={"width": 1400, "height": 860}, device_scale_factor=2).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{view}#token={server['token']}")
    return page


def saved_project(server: dict[str, Any], folder: Path, name: str = "sales") -> Path:
    """A project saved through the server: orders.csv with a step."""
    grid = call(server, "POST", "/datasets/orders/load", {"path": str(folder / "orders.csv")})["grid"]
    call(server, "POST", f"/grids/{grid}/steps", {"steps": [STEP]})
    target = folder / f"{name}.sab"
    call(server, "POST", "/project/save", {"path": str(target)})
    call(server, "POST", "/project/close", {})
    return target


def test_the_start_view_lists_recent_projects_and_opens_one(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    target = saved_project(server, fresh)
    (fresh / "gone.sab").write_bytes(target.read_bytes())
    call(server, "POST", "/project/open", {"path": str(fresh / "gone.sab")})
    call(server, "POST", "/project/close", {})
    (fresh / "gone.sab").unlink()
    page = home(browser, server)
    workspace = page.locator(".workspace")
    expect(workspace).to_have_attribute("data-view", "start", timeout=20000)
    expect(page).to_have_url(re.compile(r"/workspace\?view=start$"))
    start = page.locator("#start-view")
    expect(start.get_by_role("button", name="New project")).to_be_visible()
    expect(start.get_by_role("button", name="Open project…")).to_be_visible()
    recent = start.locator(".start-item[data-path]")
    expect(recent).to_have_count(2)
    missing = start.locator(".start-item.missing")
    expect(missing).to_contain_text("Missing")
    # A reload keeps the view.
    page.reload()
    expect(workspace).to_have_attribute("data-view", "start", timeout=20000)
    # A missing one goes from the list; the other opens: its table, with its step, comes to the front.
    missing.get_by_role("button", name="Remove from the list").click()
    expect(recent).to_have_count(1)
    start.locator(".start-open", has_text="sales").click()
    expect(workspace).to_have_attribute("data-view", "grid", timeout=20000)
    expect(page.locator(".tab-item[data-grid]")).to_have_count(1)
    expect(page.locator(".project-group .project-name")).to_have_text("sales")
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    # Home (the mark) brings the Start view back; Back goes to the table.
    page.locator(".tabbar > a.app-mark").click()
    expect(workspace).to_have_attribute("data-view", "start")
    page.go_back()
    expect(workspace).to_have_attribute("data-view", "grid")
    page.screenshot(path=str(fresh / "opened.png"))
    page.context.close()


def test_open_project_uses_the_file_chooser(browser: Browser, server: dict[str, Any], fresh: Path) -> None:
    target = saved_project(server, fresh, "chooser")
    page = home(browser, server, "?view=start")
    page.locator("#start-view").get_by_role("button", name="Open project…").click()
    dialog = page.locator("dialog.file-chooser")
    where = dialog.get_by_role("textbox", name="Folder")
    where.fill(str(fresh))
    where.press("Enter")
    dialog.locator(".file-row.file", has_text="chooser.sab").click()
    expect(page.locator(".project-group .project-name")).to_have_text("chooser", timeout=20000)
    expect(page.locator(".tab-item[data-grid]")).to_have_count(1)
    assert target.exists()
    page.context.close()


def test_save_clears_the_unsaved_mark(browser: Browser, server: dict[str, Any], fresh: Path) -> None:
    target = saved_project(server, fresh, "marked")
    page = home(browser, server, "?view=start")
    page.locator("#start-view .start-open", has_text="marked").click()
    name = page.locator(".project-group .project-name")
    expect(name).to_have_text("marked", timeout=20000)
    grid = call(server, "GET", "/grids")["grids"][0]["grid"]
    more = [STEP, {"kind": "sort", "params": {"keys": [["units", "desc"]]}}]
    call(server, "POST", f"/grids/{grid}/steps", {"steps": more})
    expect(name).to_have_text("marked ●")
    page.locator(".project-group").get_by_role("button", name="Save", exact=True).click()
    expect(name).to_have_text("marked")
    with zipfile.ZipFile(target) as read:
        manifest = json.loads(read.read("project.json"))
    assert [s["kind"] for s in manifest["tables"][0]["grids"][0]["steps"]] == ["filter", "sort"]
    page.context.close()


def test_save_as_offers_to_keep_a_pasted_tables_rows(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?view=start")
    expect(page.locator(".workspace")).to_have_attribute("data-view", "start", timeout=20000)
    call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})
    request = f"http://127.0.0.1:{server['port']}/datasets/visits/paste"
    response = page.request.post(
        request, data="city\tvisits\nSpringfield\t3\n", headers={"Authorization": f"Bearer {server['token']}"}
    )
    assert response.ok
    expect(page.locator(".tab-item[data-grid]")).to_have_count(2, timeout=20000)
    # No project yet: Ctrl+S saves the open work as one, asking for the rows first, then where.
    page.locator(".tab-item[data-grid]").first.click()
    page.keyboard.press("Control+s")
    dialog = page.locator("dialog.save-project")
    expect(dialog.locator(".keep-rows li")).to_have_count(1)  # orders.csv is read again: no tick
    item = dialog.locator(".keep-rows li", has_text="visits")
    expect(item.get_by_label("Keep its rows in the file")).not_to_be_checked()
    page.screenshot(path=str(fresh / "save-as.png"))
    item.get_by_label("Keep its rows in the file").check()
    dialog.get_by_role("button", name="Save as…").click()
    chooser = page.locator("dialog.file-chooser")
    where = chooser.get_by_role("textbox", name="Folder")
    where.fill(str(fresh))
    where.press("Enter")
    chooser.get_by_label("File name").fill("kept")
    chooser.get_by_role("button", name="Save here").click()
    expect(page.locator(".project-group .project-name")).to_have_text("kept", timeout=20000)
    with zipfile.ZipFile(fresh / "kept.sab") as read:
        names = read.namelist()
    assert "data/visits.parquet" in names and "data/orders.parquet" not in names
    page.context.close()


def choose_save(page: Page, folder: Path, name: str) -> None:
    chooser = page.locator("dialog.file-chooser")
    where = chooser.get_by_role("textbox", name="Folder")
    where.fill(str(folder))
    where.press("Enter")
    chooser.get_by_label("File name").fill(name)
    chooser.get_by_role("button", name="Save here").click()


def test_new_project_is_saved_first_then_autosave_then_its_grids(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?view=start")
    workspace = page.locator(".workspace")
    expect(workspace).to_have_attribute("data-view", "start", timeout=20000)
    page.locator("#start-view").get_by_role("button", name="New project").click()
    # First: where its file goes (the file chooser, saving).
    chooser = page.locator("dialog.file-chooser")
    expect(chooser).to_be_visible()
    choose_save(page, fresh, "planning")
    # Then: Autosave, a switch.
    choice = page.get_by_role("dialog", name="Autosave")
    switch = choice.get_by_role("switch", name="Autosave")
    expect(switch).not_to_be_checked()
    switch.check()
    page.screenshot(path=str(fresh / "autosave.png"))
    choice.get_by_role("button", name="Done").click()
    # Then: the project's Grids, with no table yet: the ways to bring data in.
    expect(workspace).to_have_attribute("data-view", "grids", timeout=20000)
    expect(page).to_have_url(re.compile(r"/workspace\?view=grids$"))
    landing = page.locator("#start-view")
    for name in ("Open a file…", "Paste", "Query", "Catalog", "Add connection"):
        expect(landing.get_by_role("button", name=name, exact=True)).to_be_visible()
    expect(landing.locator(".tour-btn")).to_have_count(0)  # the tour: the Start page's only
    group = page.locator(".project-group")
    expect(group.locator(".project-name")).to_have_text("planning")
    expect(group.get_by_role("switch", name="Autosave")).to_be_checked()
    target = fresh / "planning.sab"
    with zipfile.ZipFile(target) as read:
        assert json.loads(read.read("project.json"))["autosave"] is True
    page.screenshot(path=str(fresh / "grids-landing.png"))
    # A table arrives: it takes the landing's place; closing it brings the landing back.
    call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})
    expect(workspace).to_have_attribute("data-view", "grid", timeout=20000)
    # Autosave: saved quietly, the mark clears by itself.
    expect(group.locator(".project-name")).to_have_text("planning", timeout=20000)
    with zipfile.ZipFile(target) as read:
        assert [t["name"] for t in json.loads(read.read("project.json"))["tables"]] == ["orders"]
    page.locator(".tab-item[data-grid]").first.hover()
    page.locator(".tab-item[data-grid]").first.get_by_role("button", name=re.compile("^Close")).click()
    expect(workspace).to_have_attribute("data-view", "grids", timeout=20000)
    # Off from the project's group: kept in the file.
    group.get_by_role("switch", name="Autosave").uncheck()
    expect(group.get_by_role("switch", name="Autosave")).not_to_be_checked()
    page.wait_for_timeout(300)
    with zipfile.ZipFile(target) as read:
        assert json.loads(read.read("project.json"))["autosave"] is False
    page.context.close()


def test_the_tour_is_offered_on_the_start_page_only(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?view=start")
    expect(page.locator("#start-view .tour-btn")).to_be_visible(timeout=20000)
    expect(page.locator(".app-row .tour-btn")).to_have_count(0)
    for path in ("/workbench", "/catalog"):
        other = page.context.new_page()
        other.goto(f"http://127.0.0.1:{server['port']}{path}#token={server['token']}")
        expect(other.locator(".nav-rail")).to_be_visible(timeout=20000)
        expect(other.locator(".tour-btn, .tour-bubble")).to_have_count(0)
        other.close()
    page.context.close()


def test_a_notebook_is_imported_from_another_project(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    # Another project with a notebook of its own (made up), saved; then a new one, open now.
    source = fresh / "source.sab"
    made = call(server, "POST", "/project/new", {"path": str(source)})["project"]
    cell: dict[str, Any] = {"cell_type": "code", "source": "print('made-up import')", "metadata": {}}
    cells = [cell | {"outputs": [], "execution_count": None}]
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (Path(made["folder"]) / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    call(server, "POST", "/project/save", {})
    call(server, "POST", "/project/new", {"path": str(fresh / "target.sab")})
    page = home(browser, server, "?view=grids")
    with page.context.expect_page() as opened:
        page.evaluate("window.open('/workbench', 'swissarmybench-workbench')")
    workbench = opened.value
    expect(workbench.locator(".wb-top")).to_contain_text("target", timeout=20000)  # the project, once known
    workbench.get_by_role("button", name="Workbench menu", exact=True).first.click()
    workbench.get_by_role("menuitem", name="Import…", exact=True).click()
    dialog = workbench.get_by_role("dialog", name="Import notebooks, scripts and apps")
    dialog.get_by_role("button", name="Another project…").click()
    chooser = workbench.locator("dialog.file-chooser")
    where = chooser.get_by_role("textbox", name="Folder")
    where.fill(str(fresh))
    where.press("Enter")
    chooser.locator(".file-row.file", has_text="source.sab").click()
    dialog.get_by_label("analysis.ipynb").check()
    workbench.screenshot(path=str(fresh / "import.png"))
    dialog.get_by_role("button", name="Import", exact=True).click()
    expect(workbench.locator(".wb-tabs .tab-label", has_text="analysis.ipynb")).to_have_count(
        1, timeout=20000
    )
    listed = call(server, "GET", "/project/documents?kind=notebook")["documents"]
    assert "analysis.ipynb" in {d["path"] for d in listed}
    workbench.close()
    page.context.close()
