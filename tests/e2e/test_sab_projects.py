# ruff: noqa: F811
"""Projects as folders and the Project Explorer in a real browser (the owner, 2026-11-17): the home page's
cards (a missing one with Remove from list), a reload keeps the view, Home brings it back; Open project…
picks a folder; Save clears the unsaved mark; saving the open work makes it a project and asks "Keep its
rows" for a pasted table; New project from a beginner's type card, then its Grids; the sort and a dragged
custom order kept after a reload; the empty state; no Open a .sab file… (the conversion removed);
the tour is offered on the Projects page only (the rail's mark, 2026-11-18); the grid page with no table is
the Grids landing, a project open or not; a notebook imported from another project in the Workbench.
Screenshots light and dark when SAB_SHOTS is set. Made-up data only."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

STEP = {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "East"}}


def projects_folder() -> Path:
    return Path(os.environ["SWISSARMYBENCH_PROJECTS_DIR"])


@pytest.fixture
def fresh(server: dict[str, Any]) -> Iterator[Path]:
    """No project and no table open, the projects folder and the recent list empty; a folder of made-up
    files of the test's own."""
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})
    for dataset in call(server, "GET", "/datasets")["datasets"]:
        call(server, "DELETE", f"/datasets/{dataset['name']}")
    for recent in call(server, "GET", "/project")["recent"]:
        call(server, "POST", "/project/recent/remove", {"path": recent["path"]})
    shutil.rmtree(projects_folder(), ignore_errors=True)
    call(server, "POST", "/projects/sort", {"by": "opened", "descending": True})
    call(server, "POST", "/projects/explained", {"explained": False})
    folder = Path(server["tmp"]) / f"pf_{len(list(Path(server['tmp']).glob('pf_*')))}"
    folder.mkdir()
    (folder / "orders.csv").write_text(
        "order_id,region,units\n1,North,3\n2,East,9\n3,South,5\n4,North,7\n", encoding="utf-8"
    )
    yield folder
    if call(server, "GET", "/project")["project"]:
        call(server, "POST", "/project/close", {"discard": True})


def home(browser: Browser, server: dict[str, Any], view: str = "", dark: bool = False) -> Page:
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{view}#token={server['token']}")
    return page


def saved_project(server: dict[str, Any], folder: Path, name: str = "sales") -> Path:
    """A project saved through the server: orders.csv with a step, autosave off."""
    grid = call(server, "POST", "/datasets/orders/load", {"path": str(folder / "orders.csv")})["grid"]
    call(server, "POST", f"/grids/{grid}/steps", {"steps": [STEP]})
    target = folder / name
    call(server, "POST", "/project/save", {"path": str(target), "autosave": False})
    call(server, "POST", "/project/close", {})
    return target


def shot(page: Page, folder: Path, name: str) -> None:
    """A picture of the page: into SAB_SHOTS when set (the docs' pictures), else the test's folder."""
    where = Path(os.environ.get("SAB_SHOTS") or folder)
    where.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(where / name))


def manifest_of(folder: Path) -> dict[str, Any]:
    return dict(json.loads((folder / ".sab" / "project.json").read_text(encoding="utf-8")))


def made_up_projects(server: dict[str, Any], fresh: Path) -> None:
    """Three made-up projects in the projects folder (one a Git repository on a branch), one opened."""
    for name, app in (("Regional sales", False), ("Survey results", False), ("Store dashboard", True)):
        call(server, "POST", "/project/new", {"name": name, "app": app, "notebooks": ["analysis"]})
        call(server, "POST", "/project/close", {"discard": True})
    sales = projects_folder() / "Regional sales"
    (sales / ".git").mkdir()
    (sales / ".git" / "HEAD").write_text("ref: refs/heads/q3-close\n", encoding="utf-8")
    call(server, "POST", "/project/open", {"path": str(sales)})
    call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})
    call(server, "POST", "/project/save", {})
    call(server, "POST", "/project/close", {})


def test_the_explorer_lists_projects_as_cards_and_opens_one(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    made_up_projects(server, fresh)
    gone = saved_project(server, fresh, "gone")
    shutil.rmtree(gone)
    page = home(browser, server)
    workspace = page.locator(".workspace")
    # The app starts on the Projects page (no table, no project), a page of its own over the grids'.
    start = page.locator('.area-page[data-page="projects"]')
    expect(start).to_be_visible(timeout=20000)
    expect(page).to_have_url(re.compile(r"/workspace\?(view=grids&)?open=projects$"))
    expect(page.locator('.nav-rail [data-area="projects"]')).to_have_attribute("aria-current", "page")
    expect(start.get_by_role("button", name="New project", exact=True)).to_be_visible()
    cards = start.locator(".explorer-card")
    expect(cards).to_have_count(4)
    sales = start.locator(".explorer-card", has_text="Regional sales")
    expect(sales).to_contain_text("q3-close")
    expect(sales).to_contain_text("1 table")
    expect(start.locator(".explorer-card", has_text="Store dashboard")).to_contain_text("Streamlit app")
    missing = start.locator(".explorer-card.missing")
    expect(missing).to_contain_text("Moved or deleted")
    expect(cards.last).to_have_class(re.compile("missing"))  # a missing one is always last
    # The beginners' types, explained.
    types = start.locator(".explorer-types .pt-card")
    expect(types).to_have_count(2)
    expect(types.first).to_contain_text("Analysis")
    shot(page, fresh, "project-explorer-light.png")
    # A reload keeps the view.
    page.reload()
    expect(start).to_be_visible(timeout=20000)
    # A missing one goes from the list; the other opens: its table, with its step, comes to the front.
    missing.get_by_role("button", name="gone: more").click()
    missing.get_by_role("menuitem", name="Remove from list").click()
    expect(cards).to_have_count(3)
    start.locator(".explorer-card", has_text="Regional sales").locator("h3").click()
    expect(workspace).to_have_attribute("data-view", "grid", timeout=20000)
    expect(start).to_have_count(0)  # Projects made way for the project's grids
    expect(page.locator(".tab-item[data-grid]")).to_have_count(1)
    expect(page.locator(".project-group .project-name")).to_have_text("Regional sales")
    # Home (the rail's mark) brings the Projects page back, the open one marked; Back goes to the table.
    page.locator('.nav-rail [data-area="projects"]').click()
    expect(start.locator(".explorer-card.is-open")).to_contain_text("Regional sales")
    page.go_back()
    expect(start).to_have_count(0)
    expect(workspace).to_have_attribute("data-view", "grid")
    page.context.close()
    dark = home(browser, server, "?open=projects", dark=True)
    expect(dark.locator('.area-page[data-page="projects"] .explorer-card')).to_have_count(3, timeout=20000)
    shot(dark, fresh, "project-explorer-dark.png")
    dark.context.close()


def test_sort_and_a_dragged_custom_order_are_kept_after_a_reload(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    for name in ("Alpha", "Beta", "Gamma"):
        call(server, "POST", "/project/new", {"name": name})
        call(server, "POST", "/project/close", {"discard": True})
    page = home(browser, server, "?open=projects")
    start = page.locator('.area-page[data-page="projects"]')
    names = start.locator(".explorer-card h3")
    expect(names).to_have_count(3, timeout=20000)
    start.get_by_label("Sort by").select_option("name")
    expect(names).to_have_text(["Alpha", "Beta", "Gamma"])
    start.get_by_role("button", name="Ascending").click()
    expect(names).to_have_text(["Gamma", "Beta", "Alpha"])
    # Drag Alpha onto Gamma: Custom, in that order.
    start.locator(".explorer-card", has_text="Alpha").drag_to(
        start.locator(".explorer-card", has_text="Gamma")
    )
    expect(names).to_have_text(["Alpha", "Gamma", "Beta"])
    expect(start.get_by_label("Sort by")).to_have_value("custom")
    # The keyboard's way: a card's menu, Move right.
    beta = start.locator(".explorer-card", has_text="Gamma")
    beta.get_by_role("button", name="Gamma: more").click()
    beta.get_by_role("menuitem", name="Move right").click()
    expect(names).to_have_text(["Alpha", "Beta", "Gamma"])
    page.reload()
    expect(names).to_have_text(["Alpha", "Beta", "Gamma"], timeout=20000)
    # The filter: words in a name.
    start.get_by_label("Search projects").fill("gam")
    expect(names).to_have_text(["Gamma"])
    page.context.close()


def test_the_empty_state_and_new_project_from_a_beginners_type_card(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?open=projects")
    workspace = page.locator(".workspace")
    start = page.locator('.area-page[data-page="projects"]')
    empty = start.locator(".explorer-empty")
    expect(empty).to_contain_text("Create your first project", timeout=20000)
    expect(empty.locator(".pt-card.large")).to_have_count(2)
    shot(page, fresh, "project-explorer-empty.png")
    empty.get_by_role("button", name="Create Streamlit app").click()
    dialog = page.locator("dialog.new-project")
    expect(dialog.get_by_role("radio", name="Streamlit app")).to_have_attribute("aria-checked", "true")
    # The "?" brings the explanations into the chooser.
    dialog.get_by_role("button", name="What kind of project?").click()
    expect(dialog.locator(".pt-card")).to_have_count(2)
    expect(dialog).to_contain_text(str(projects_folder()))
    dialog.get_by_label("Name").fill("Planning")
    shot(page, fresh, "new-project-dialog.png")
    dialog.get_by_role("button", name="Create", exact=True).click()
    # Then: the project's Grids, with no table yet: the ways to bring data in.
    expect(workspace).to_have_attribute("data-view", "grids", timeout=20000)
    group = page.locator(".project-group")
    expect(group.locator(".project-name")).to_have_text("Planning")
    expect(group.get_by_role("switch", name="Autosave")).to_be_checked()  # on by default
    folder = projects_folder() / "Planning"
    assert (folder / ".sab" / "project.json").is_file() and (folder / ".gitignore").is_file()
    assert list(folder.glob("*.stapp.json"))  # a Streamlit app's canvas
    # A table arrives; Autosave keeps .sab/ current by itself.
    call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})
    expect(workspace).to_have_attribute("data-view", "grid", timeout=20000)
    for _ in range(100):
        if [t["name"] for t in manifest_of(folder)["tables"]] == ["orders"]:
            break
        page.wait_for_timeout(200)
    assert [t["name"] for t in manifest_of(folder)["tables"]] == ["orders"]
    page.context.close()


def test_new_projects_folder_picker_opens_before_the_projects_folder_exists(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    """The projects folder is made by the first project: before that, Choose another folder… showed an empty
    list and an empty menu (no way to go anywhere). It shows the nearest folder above that does exist."""
    assert not projects_folder().exists()
    page = home(browser, server, "?open=projects")
    page.locator('.area-page[data-page="projects"]').get_by_role("button", name="New project").first.click()
    page.get_by_role("button", name="Choose another folder…").click()
    chooser = page.locator("dialog.file-chooser")
    expect(chooser.get_by_role("textbox", name="Folder")).not_to_have_value("", timeout=10000)
    expect(chooser.get_by_role("status")).to_contain_text("does not exist yet")
    expect(chooser.get_by_role("navigation", name="Places").locator(".file-place")).not_to_have_count(0)
    chooser.get_by_role("button", name="Cancel").click()
    page.context.close()


def test_open_project_picks_a_folder_and_save_clears_the_mark(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    target = saved_project(server, fresh, "chooser")
    page = home(browser, server, "?open=projects")
    page.locator('.area-page[data-page="projects"]').get_by_role("button", name="Open project…").click()
    dialog = page.locator("dialog.file-chooser")
    where = dialog.get_by_role("textbox", name="Folder")
    where.fill(str(target))
    where.press("Enter")
    expect(where).to_have_value(str(target))
    dialog.get_by_role("button", name="Choose this folder").click()
    name = page.locator(".project-group .project-name")
    expect(name).to_have_text("chooser", timeout=20000)
    expect(page.locator(".tab-item[data-grid]")).to_have_count(1)
    grid = call(server, "GET", "/grids")["grids"][0]["grid"]
    more = [STEP, {"kind": "sort", "params": {"keys": [["units", "desc"]]}}]
    call(server, "POST", f"/grids/{grid}/steps", {"steps": more})
    expect(name).to_have_text("chooser ●")
    page.locator(".project-group").get_by_role("button", name="Save", exact=True).click()
    expect(name).to_have_text("chooser")
    steps = manifest_of(target)["tables"][0]["grids"][0]["steps"]
    assert [s["kind"] for s in steps] == ["filter", "sort"]
    page.context.close()


def test_saving_the_open_work_makes_a_project_and_asks_to_keep_a_pasted_tables_rows(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?open=projects")
    expect(page.locator('.area-page[data-page="projects"]')).to_be_visible(timeout=20000)
    call(server, "POST", "/datasets/orders/load", {"path": str(fresh / "orders.csv")})
    request = f"http://127.0.0.1:{server['port']}/datasets/visits/paste"
    response = page.request.post(
        request, data="city\tvisits\nSpringfield\t3\n", headers={"Authorization": f"Bearer {server['token']}"}
    )
    assert response.ok
    expect(page.locator(".tab-item[data-grid]")).to_have_count(2, timeout=20000)
    # No project yet: Ctrl+S makes the open work one (New project), then Save asks about the rows.
    page.locator(".tab-item[data-grid]").first.click()
    page.locator('.nav-rail [data-area="grids"]').click()
    page.keyboard.press("Control+s")
    dialog = page.locator("dialog.new-project")
    dialog.get_by_label("Name").fill("kept")
    dialog.get_by_role("button", name="Create", exact=True).click()
    expect(page.locator(".project-group .project-name")).to_have_text("kept", timeout=20000)
    page.keyboard.press("Control+s")
    rows = page.locator("dialog.save-project")
    expect(rows.locator(".keep-rows li")).to_have_count(1)  # orders.csv is read again: no tick
    item = rows.locator(".keep-rows li", has_text="visits")
    expect(item.get_by_label("Keep its rows")).not_to_be_checked()
    item.get_by_label("Keep its rows").check()
    rows.get_by_role("button", name="Save").click()
    folder = projects_folder() / "kept"
    for _ in range(50):
        if (folder / ".sab" / "data" / "visits.parquet").is_file():
            break
        page.wait_for_timeout(200)
    assert (folder / ".sab" / "data" / "visits.parquet").is_file()
    assert not (folder / ".sab" / "data" / "orders.parquet").exists()
    assert ".sab/data/" in (folder / ".gitignore").read_text(encoding="utf-8")
    page.context.close()


def test_the_projects_page_offers_no_old_sab_file_import(browser: Browser, server: dict[str, Any]) -> None:
    """The .sab conversion is removed (the owner, 2026-11-17): the Projects page opens folders only."""
    page = home(browser, server, "?open=projects")
    actions = page.locator('.area-page[data-page="projects"] .start-actions')
    expect(actions.get_by_role("button", name="Open project…")).to_be_visible()
    expect(page.get_by_role("button", name="Open a .sab file…")).to_have_count(0)
    page.context.close()


def test_the_tour_is_offered_on_the_projects_page_only(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    page = home(browser, server, "?open=projects")
    expect(page.locator('.area-page[data-page="projects"] .tour-btn')).to_be_visible(timeout=20000)
    expect(page.locator(".app-row .tour-btn")).to_have_count(0)
    for path in ("/workbench", "/catalog"):
        other = page.context.new_page()
        other.goto(f"http://127.0.0.1:{server['port']}{path}#token={server['token']}")
        expect(other.locator(".nav-rail")).to_be_visible(timeout=20000)
        expect(other.locator(".tour-btn, .tour-bubble")).to_have_count(0)
        other.close()
    page.context.close()


def test_the_grid_page_with_no_table_is_the_grids_landing_and_the_mark_opens_projects(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    """The owner (2026-11-18): "give this button its own page for projects dont share the grid as the home
    page". The grid page is only the grids: with no table and no project, its landing (and a link to
    Projects); the mark, the rail's first item, opens Projects over it; Back returns."""
    made_up_projects(server, fresh)
    page = home(browser, server, "?view=grids")
    landing = page.locator(".landing-page")
    expect(landing).to_be_visible(timeout=20000)
    expect(page.locator(".workspace")).to_have_attribute("data-view", "grids")
    expect(landing.get_by_role("button", name="Open a file…")).to_be_visible()
    expect(landing.locator(".landing-projects")).to_contain_text("No project is open.")
    projects = page.locator('.area-page[data-page="projects"]')
    expect(projects).to_have_count(0)
    mark = page.locator(".nav-rail-item").first
    expect(mark).to_have_attribute("data-area", "projects")
    expect(page.locator(".nav-rail [aria-current='page']")).to_have_attribute("data-area", "grids")
    mark.hover()
    expect(mark.locator(".nav-rail-tip")).to_be_visible()
    shot(page, fresh, "rail-mark-tip.png")
    page.mouse.move(700, 500)
    mark.click()
    page.mouse.move(700, 500)
    expect(projects.locator(".explorer-card")).to_have_count(3, timeout=20000)
    expect(mark).to_have_attribute("aria-current", "page")
    # The grid page is not shown: Projects covers everything right of the rail.
    assert (
        page.evaluate("document.elementFromPoint(700, 450).closest('.area-page')?.dataset.page") == "projects"
    )
    shot(page, fresh, "projects-page-light.png")
    page.go_back()
    expect(projects).to_have_count(0)
    expect(landing).to_be_visible()
    # The landing's link goes there too.
    landing.get_by_role("link", name="Projects").click()
    expect(projects).to_be_visible()
    page.context.close()
    dark = home(browser, server, "?open=projects", dark=True)
    expect(dark.locator('.area-page[data-page="projects"] .explorer-card')).to_have_count(3, timeout=20000)
    shot(dark, fresh, "projects-page-dark.png")
    dark.context.close()


def test_a_notebook_is_imported_from_another_project(
    browser: Browser, server: dict[str, Any], fresh: Path
) -> None:
    source = fresh / "source"
    call(server, "POST", "/project/new", {"path": str(source)})
    cell: dict[str, Any] = {"cell_type": "code", "source": "print('made-up import')", "metadata": {}}
    cells = [cell | {"outputs": [], "execution_count": None}]
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (source / "analysis.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    call(server, "POST", "/project/new", {"path": str(fresh / "target")})
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
    where.fill(str(source))
    where.press("Enter")
    expect(where).to_have_value(str(source))
    chooser.get_by_role("button", name="Choose this folder").click()
    dialog.get_by_label("analysis.ipynb").check()
    dialog.get_by_role("button", name="Import", exact=True).click()
    expect(workbench.locator(".wb-tabs .tab-label", has_text="analysis.ipynb")).to_have_count(
        1, timeout=20000
    )
    listed = call(server, "GET", "/project/documents?kind=notebook")["documents"]
    assert "analysis.ipynb" in {d["path"] for d in listed}
    workbench.close()
    page.context.close()
