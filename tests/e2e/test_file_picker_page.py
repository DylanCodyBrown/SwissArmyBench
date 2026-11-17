# ruff: noqa: F811
"""Every pick of a file or folder (fileChooser.ts): the system's own dialog first, stood in here (the
browser's requests to /dialogs answered by the test: no real dialog opens), and the page's own picker when
none can open (a test server has no display): its places, breadcrumb, filter, New folder, hidden files, keys
and recent folders. A server of its own, its home folder a made-up one. Made-up files only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from tests.e2e.test_ui import browser, call  # noqa: F401

SHOTS = os.environ.get("SAB_SHOTS_DIALOGS")


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """The app with a made-up home folder (Desktop, Documents, Downloads; a hidden one), its own state."""
    tmp = tmp_path_factory.mktemp("picker")
    home = tmp / "home" / "ada"
    for name in ("Desktop", "Documents", "Downloads", ".config"):
        (home / name).mkdir(parents=True)
    reports = home / "Documents" / "Reports"
    reports.mkdir()
    for name, text in (
        ("orders.csv", "order_id,region,units\n1,North,3\n2,East,9\n"),
        ("regions.csv", "region,manager\nNorth,Ada\nEast,Grace\n"),
        ("notes.md", "made up\n"),
    ):
        (reports / name).write_text(text, encoding="utf-8")
    (reports / "Archive").mkdir()
    (reports / ".cache").mkdir()
    env = os.environ | {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "SWISSARMYBENCH_INFO": str(tmp / "server.json"),
        "SWISSARMYBENCH_STATE": str(tmp / "state"),
        "SWISSARMYBENCH_CLAUDE_DIR": str(tmp / "claude"),
        "SWISSARMYBENCH_PROJECTS_DIR": str(home / "Swiss Army Bench Projects"),
        "SWISSARMYBENCH_WORKBENCH_DIR": str(home / "SwissArmyBench"),
    }
    (home / "Swiss Army Bench Projects").mkdir()
    process = subprocess.Popen([sys.executable, "-m", "swissarmybench.server", "--port", "0"], env=env)
    for _ in range(150):
        try:
            info = json.loads((tmp / "server.json").read_text())
            break
        except (OSError, ValueError):
            time.sleep(0.1)
    else:
        process.kill()
        raise AssertionError("server did not start")
    seed = tmp / "seed.csv"
    seed.write_text("id,name\n1,Made-up\n", encoding="utf-8")
    call(info, "POST", "/datasets/seed/load", {"path": str(seed)})
    yield info | {"tmp": tmp, "home": home, "reports": reports}
    process.terminate()
    process.wait(timeout=20)


def url(server: dict[str, Any], view: str = "") -> str:
    return f"http://127.0.0.1:{server['port']}/workspace{view}#token={server['token']}"


def workspace(browser: Browser, server: dict[str, Any], dark: bool = False, width: int = 1400) -> Page:
    """The workspace with the seed table open (its tab strip's Open file…)."""
    context = browser.new_context(
        viewport={"width": width, "height": 900},
        device_scale_factor=2,
        color_scheme="dark" if dark else "light",
    )
    page = context.new_page()
    page.goto(url(server))
    expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
    return page


def start_view(page: Page, server: dict[str, Any]) -> None:
    page.goto(url(server, "?view=start"))
    expect(page.locator("#start-view")).to_be_visible(timeout=20000)


def open_file(page: Page) -> None:
    page.get_by_role("button", name="Open file…").first.click()


def shot(page: Page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def test_the_page_picker_places_breadcrumb_filter_keys_and_recent(
    browser: Browser, server: dict[str, Any]
) -> None:
    assert call(server, "GET", "/dialogs")["system"] is False  # no display here: the page's own picker
    home, reports = server["home"], server["reports"]
    page = workspace(browser, server)
    try:
        open_file(page)
        chooser = page.locator("dialog.file-chooser")
        places = chooser.get_by_role("navigation", name="Places")
        for name in ("Home", "Desktop", "Documents", "Downloads", "Projects"):
            expect(places.get_by_role("button", name=name, exact=True)).to_be_visible()
        expect(places.locator(".file-place[aria-current]")).to_have_text("Home")
        # A place, then the folder by a double-click; the breadcrumb follows, each part a click.
        places.get_by_role("button", name="Documents", exact=True).click()
        rows = chooser.locator(".file-row")
        rows.filter(has_text="Reports").dblclick()
        crumbs = chooser.get_by_role("navigation", name="Path")
        expect(crumbs.locator(".file-crumb.current")).to_have_text("Reports")
        expect(chooser.get_by_role("textbox", name="Folder")).to_have_value(str(reports))
        # Folders first, then the table files only; hidden ones hidden until the switch.
        expect(rows.locator(".file-name")).to_have_text(["Archive", "orders.csv", "regions.csv"])
        chooser.get_by_label("Hidden files").check()
        expect(rows.first).to_contain_text(".cache")
        chooser.get_by_label("Hidden files").uncheck()
        expect(rows).to_have_count(3)
        # Filter as you type.
        chooser.get_by_role("searchbox", name="Filter").fill("reg")
        expect(rows).to_have_count(1)
        expect(chooser.get_by_role("status")).to_contain_text("matching")
        chooser.get_by_role("searchbox", name="Filter").fill("")
        shot(page, "picker-light")
        # The keys: Backspace up, arrows, Enter opens a folder, Enter picks a file.
        listbox = chooser.get_by_role("listbox", name="Folders and files")
        listbox.focus()
        page.keyboard.press("Backspace")
        expect(crumbs.locator(".file-crumb.current")).to_have_text("Documents")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(crumbs.locator(".file-crumb.current")).to_have_text("Reports")
        crumbs.get_by_role("button", name="ada").click()
        expect(chooser.get_by_role("textbox", name="Folder")).to_have_value(str(home))
        chooser.get_by_role("textbox", name="Folder").fill(str(reports))
        chooser.get_by_role("textbox", name="Folder").press("Enter")
        expect(rows).to_have_count(3)
        listbox.focus()
        for _ in range(2):
            page.keyboard.press("ArrowDown")
        expect(rows.nth(1)).to_have_attribute("aria-selected", "true")
        page.keyboard.press("Enter")
        expect(page.locator(".tab-item[data-grid]", has_text="orders")).to_have_count(1, timeout=20000)
        # Recent, per kind of pick: Open file remembers Reports; a folder pick does not show it.
        open_file(page)
        expect(places.get_by_role("button", name="Reports")).to_be_visible()
        chooser.get_by_role("button", name="Cancel").click()
        expect(chooser).to_have_count(0)
        saved = json.loads((Path(server["tmp"]) / "state" / "dialogs.json").read_text(encoding="utf-8"))
        assert list(saved["recent"].values()) == [[str(reports)]]
        start_view(page, server)
        page.locator("#start-view").get_by_role("button", name="Open project…").click()
        expect(places.get_by_role("button", name="Home", exact=True)).to_be_visible()
        expect(places.get_by_role("button", name="Reports")).to_have_count(0)
        # New folder (a folder pick): named, made, and shown.
        chooser.get_by_role("button", name="New folder").click()
        new_name = chooser.get_by_role("textbox", name="New folder's name")
        new_name.fill("Q3 made-up")
        new_name.press("Enter")
        expect(crumbs.locator(".file-crumb.current")).to_have_text("Q3 made-up")
        assert (home / "Q3 made-up").is_dir()
        page.keyboard.press("Escape")
        expect(chooser).to_have_count(0)
    finally:
        page.context.close()


def test_the_picker_in_dark_and_at_phone_width(browser: Browser, server: dict[str, Any]) -> None:
    for dark, width, name in ((True, 1400, "picker-dark"), (False, 420, "picker-phone")):
        page = workspace(browser, server, dark=dark, width=width)
        try:
            start_view(page, server)
            page.locator("#start-view").get_by_role("button", name="Open project…").click()
            chooser = page.locator("dialog.file-chooser")
            chooser.get_by_role("textbox", name="Folder").fill(str(server["reports"]))
            chooser.get_by_role("textbox", name="Folder").press("Enter")
            expect(chooser.locator(".file-row")).to_have_count(4)
            chooser.locator(".file-row").first.click()
            no_side_scroll = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert no_side_scroll
            shot(page, name)
        finally:
            page.context.close()


# ===== the system's own dialog, stood in =====


def stand_in(context: BrowserContext, answers: list[dict[str, Any]], asked: list[dict[str, Any]]) -> None:
    """GET /dialogs says system dialogs open; each POST /dialogs/choose answers the next of `answers`."""

    def status(route: Route) -> None:
        route.fulfill(json={"system": True, "tool": "tk"})

    def choose(route: Route) -> None:
        asked.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(json=answers.pop(0))

    context.route("**/dialogs", status)
    context.route("**/dialogs/choose", choose)


NO_PAGE_PICKER = """() => { window.__pickerShown = false;
  new MutationObserver(() => {
    if (document.querySelector('dialog.file-chooser')) window.__pickerShown = true;
  }).observe(document.body, { childList: true, subtree: true }); }"""


def test_the_system_dialog_is_used_and_the_page_picker_never_shows(
    browser: Browser, server: dict[str, Any]
) -> None:
    reports = server["reports"]
    page = workspace(browser, server)
    asked: list[dict[str, Any]] = []
    answers: list[dict[str, Any]] = [
        {"path": str(reports / "regions.csv")},
        {"cancelled": True},
        {"busy": True},
        {"path": str(server["home"] / "Documents")},
    ]
    stand_in(page.context, answers, asked)
    try:
        page.reload()
        expect(page.locator(".ag-row[row-index='0']").first).to_be_visible(timeout=20000)
        page.evaluate(NO_PAGE_PICKER)
        # Open file: the path the dialog gave opens as a grid.
        open_file(page)
        expect(page.locator(".tab-item[data-grid]", has_text="regions")).to_have_count(1, timeout=20000)
        assert (
            asked[0]["mode"] == "file" and ".csv" in asked[0]["suffixes"] and asked[0]["title"] == "Open file"
        )
        assert asked[0]["kind"].startswith("file:")
        # A cancel opens nothing; a second dialog while one is open says so.
        tabs = page.locator(".tab-item[data-grid]").count()
        page.get_by_role("button", name="Open file…").first.click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Open file…").first.click()
        expect(page.locator(".toast", has_text="A file dialog is already open")).to_be_visible()
        assert page.locator(".tab-item[data-grid]").count() == tabs
        # Settings' Projects folder: a folder pick, the path sent on.
        page.locator('.nav-rail [data-area="settings"]').click()
        projects = page.locator(".projects-folder-fieldset")
        projects.get_by_role("button", name="Change…").click()
        expect(projects.locator("code")).to_have_text(str(server["home"] / "Documents"), timeout=10000)
        assert asked[-1]["mode"] == "folder" and asked[-1]["title"] == "The projects folder"
        assert page.evaluate("window.__pickerShown") is False
    finally:
        page.context.close()
        call(server, "POST", "/projects/folder", {"default": True})
        for grid in call(server, "GET", "/grids")["grids"]:
            if grid["dataset"] != "seed":
                call(server, "DELETE", f"/datasets/{grid['dataset']}")


def test_a_dialog_that_cannot_open_falls_back_to_the_page_picker(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = workspace(browser, server)
    asked: list[dict[str, Any]] = []
    stand_in(page.context, [{"unavailable": "The tk dialog ended with code 1: no display"}], asked)
    try:
        start_view(page, server)
        page.locator("#start-view").get_by_role("button", name="Open project…").click()
        expect(page.locator("dialog.file-chooser")).to_be_visible()
        assert len(asked) == 1
        page.locator("dialog.file-chooser").get_by_role("button", name="Cancel").click()
        # From then on the page's own, without asking again.
        page.locator("#start-view").get_by_role("button", name="Open project…").click()
        expect(page.locator("dialog.file-chooser")).to_be_visible()
        assert len(asked) == 1
    finally:
        page.context.close()
