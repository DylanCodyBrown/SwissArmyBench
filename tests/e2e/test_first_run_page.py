# ruff: noqa: F811
"""A first run that feels better (the owner, 2026-11-19), in a real browser, on a server of its own (nothing
open, no connection, no variable): empty pages that lead somewhere (one sentence, the primary button, Try it
with sample data), the rail's names (on until turned off, kept), Add connection's search and crumb, Open a
file and Paste data beside New project, Ctrl+K's recently used first and its keys, a short table filling the
width, the empty Application row gone, the finder's joins drawn at once beside the list, and a new
notebook's hint. Made-up data only.

With SWISSARMYBENCH_FEEL_SHOTS set to a folder, the tests also save light and dark screenshots there (2x)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.environment_helpers import open_variables
from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_FEEL_SHOTS")


def shot(page: Page, name: str) -> None:
    """The page as it is, light then dark (the theme follows the system's)."""
    if not SHOTS:
        return
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    for scheme in ("light", "dark"):
        page.emulate_media(color_scheme=scheme)
        page.wait_for_timeout(300)
        page.screenshot(path=str(Path(SHOTS) / f"{name}-{scheme}.png"))
    page.emulate_media(color_scheme="light")


def home(browser: Browser, server: dict[str, Any], query: str = "", width: int = 1440) -> Page:
    page = browser.new_context(
        viewport={"width": width, "height": 900}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workspace{query}#token={server['token']}")
    expect(page.locator(".nav-rail")).to_be_visible(timeout=20000)
    return page


def test_empty_pages_lead_somewhere_and_the_sample_opens(browser: Browser, server: dict[str, Any]) -> None:
    page = home(browser, server, "?open=connections")
    empty = page.locator(".area-page[data-page='connections'] .empty-state")
    expect(empty).to_be_visible(timeout=20000)
    expect(empty).to_contain_text("DuckDB SQL can read them by name")
    expect(empty.get_by_role("button", name="Add connection")).to_be_visible()
    shot(page, "empty-connections")
    # Variables: its sentence and Add variable (no sample: tables are not variables).
    open_variables(page)
    variables = page.locator(".area-page[data-page='variables'] .empty-state")
    expect(variables).to_be_visible(timeout=20000)
    expect(variables.get_by_role("button", name="Add variable")).to_be_visible()
    expect(variables.get_by_role("button", name="Try it with sample data")).to_have_count(0)
    shot(page, "empty-variables")
    # Session: nothing yet, and a way to start.
    page.locator(".nav-rail [data-area='session']").click()
    session = page.locator(".area-page[data-page='session'] .empty-state")
    expect(session).to_be_visible(timeout=20000)
    expect(session.get_by_role("button", name="Launch Claude")).to_be_visible()
    shot(page, "empty-session")
    # Try it with sample data: three made-up tables open, and the page makes way for the grids.
    page.locator(".nav-rail [data-area='connections']").click()
    expect(empty).to_be_visible(timeout=20000)
    empty.get_by_role("button", name="Try it with sample data").click()
    tabs = page.locator(".tabbar")
    for name in ("customers", "products", "orders"):
        expect(tabs).to_contain_text(name, timeout=20000)
    expect(page.locator(".area-page[data-page='connections']")).to_have_count(0)
    names = {d["name"] for d in call(server, "GET", "/datasets")["datasets"]}
    assert {"customers", "products", "orders"} <= names
    # A short table's columns fill the width; with no project the Application row takes no band.
    page.locator(".tabbar").get_by_text("products", exact=True).click()
    expect(page.locator(".ag-row[row-index='0']:visible").first).to_be_visible(timeout=20000)
    expect(page.locator(".app-row")).to_be_hidden()
    page.wait_for_timeout(400)
    widths = page.evaluate(
        """() => {
          const pane = [...document.querySelectorAll('.ag-root-wrapper')].find((e) => e.offsetParent);
          const view = pane.getBoundingClientRect().width - 80;
          const cols = [...pane.querySelectorAll('.ag-header-cell[col-id]')]
            .filter((c) => !c.closest('.ag-pinned-left-header'))
            .map((c) => c.getBoundingClientRect().width).filter((w) => w > 1);
          return { view, used: cols.reduce((a, b) => a + b, 0), count: cols.length };
        }"""
    )
    assert widths["count"] >= 4 and widths["used"] > widths["view"] * 0.95, widths
    tip = page.locator(".ribbon .ribbon-btn[aria-label='Export']")
    assert "CSV, Excel or Parquet" in (tip.get_attribute("title") or "")
    shot(page, "short-table-fills")
    page.context.close()


def test_the_rail_shows_its_names_until_turned_off(browser: Browser, server: dict[str, Any]) -> None:
    page = home(browser, server, "?open=projects")
    html = page.locator("html")
    expect(html).to_have_class(re.compile(r"\brail-names\b"))  # a first run: the names
    connections = page.locator(".nav-rail [data-area='connections'] .nav-rail-name")
    expect(connections).to_be_visible()
    expect(connections).to_have_text("Connections")
    box = page.locator(".nav-rail").bounding_box()
    assert box and box["width"] > 150
    # Open a file… and Paste data beside New project.
    head = page.locator(".explorer-head .start-actions")
    expect(head.get_by_role("button", name="Open a file…")).to_be_visible(timeout=20000)
    expect(head.get_by_role("button", name="Paste data")).to_be_visible()
    shot(page, "projects-rail-names")
    # Icons only: kept on this computer, so a new window opens the same.
    page.locator(".nav-rail-toggle").click()
    expect(html).not_to_have_class(re.compile(r"\brail-names\b"))
    expect(connections).to_be_hidden()
    assert call(server, "GET", "/rail") == {"labels": False}
    box = page.locator(".nav-rail").bounding_box()
    assert box and box["width"] < 70
    shot(page, "projects-rail-icons")
    other = home(browser, server, "?open=projects")
    expect(other.locator("html")).not_to_have_class(re.compile(r"\brail-names\b"))
    # The right-click menu says it too: Show names, and every window follows.
    other.locator(".nav-rail [data-area='erd']").click(button="right")
    other.locator(".menu").get_by_text("Show names").click()
    expect(other.locator("html")).to_have_class(re.compile(r"\brail-names\b"))
    expect(html).to_have_class(re.compile(r"\brail-names\b"), timeout=10000)
    assert call(server, "GET", "/rail") == {"labels": True}
    other.context.close()
    # Paste data: a copied table opens as a grid at once.
    head.get_by_role("button", name="Paste data").click()
    box_ = page.locator("dialog .paste-box")
    expect(box_).to_be_visible()
    shot(page, "paste-data")
    box_.fill("fruit\tcount\napple\t3\npear\t5\n")
    page.locator("dialog").get_by_role("button", name="Open").click()
    expect(page.locator(".tabbar")).to_contain_text("pasted_", timeout=20000)
    page.context.close()


def test_add_connection_searches_and_has_its_crumb(browser: Browser, server: dict[str, Any]) -> None:
    page = home(browser, server, "?open=connections")
    pane = page.locator(".area-page[data-page='connections']")
    pane.get_by_role("button", name="Add connection").first.click()
    search = pane.get_by_role("searchbox", name="Search the connection types")
    expect(search).to_be_focused(timeout=20000)
    expect(pane.locator(".crumbs")).to_contain_text("Add connection")
    shot(page, "add-connection")
    search.fill("postgres")
    shown = pane.locator(".connection-type:visible")
    expect(shown).to_have_count(1)
    expect(shown).to_contain_text("PostgreSQL")
    shot(page, "add-connection-search")
    search.fill("nothing like this")
    expect(pane.get_by_text("No connection type matches.")).to_be_visible()
    search.fill("sqlite")
    search.press("Enter")
    expect(pane.locator(".crumbs")).to_contain_text("SQLite", timeout=10000)
    # Back, and the kind used last comes first in its group.
    page.go_back()
    expect(search).to_be_visible(timeout=10000)
    expect(pane.locator(".connection-types").first.locator(".connection-type").first).to_contain_text(
        "SQLite"
    )
    page.context.close()


def test_find_data_puts_the_used_first_and_says_its_keys(browser: Browser, server: dict[str, Any]) -> None:
    if not {d["name"] for d in call(server, "GET", "/datasets")["datasets"]} >= {"customers", "orders"}:
        call(server, "POST", "/samples/store")
    page = home(browser, server)
    page.keyboard.press("Control+K")
    dialog = page.locator("dialog.find-data")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".ex-keys")).to_contain_text("Enter opens")
    expect(dialog.locator(".ex-group-recent")).to_have_count(0)
    orders = dialog.locator(".ex-group[data-kind='tables'] .ex-result", has_text="orders").first
    expect(orders).to_be_visible(timeout=20000)
    orders.get_by_role("button", name="Copy name").click()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    page.keyboard.press("Control+K")
    recent = page.locator("dialog.find-data .ex-group-recent")
    expect(recent).to_be_visible(timeout=10000)
    expect(recent.locator("h3")).to_contain_text("Recently used")
    expect(recent.locator(".ex-name").first).to_have_text(re.compile(r"^orders"))
    shot(page, "find-data-recent")
    page.context.close()


def test_the_finder_draws_its_joins_beside_the_list(browser: Browser, server: dict[str, Any]) -> None:
    if not {d["name"] for d in call(server, "GET", "/datasets")["datasets"]} >= {"customers", "orders"}:
        call(server, "POST", "/samples/store")
    call(server, "POST", "/relationships", {"model": {"name": "empty"}, "replace": True})
    page = home(browser, server, "?view=erd")
    page.locator("#erd-view").get_by_role("button", name="Find relationships").click()
    dialog = page.locator("dialog[open]")
    expect(dialog.locator(".rel-found-diagram svg")).to_be_visible(timeout=60000)
    expect(dialog.locator(".rel-found-list .suggestion", has_text="customers")).not_to_have_count(0)
    expect(dialog.locator(".confidence.sure").first).to_be_visible()
    assert len(call(server, "GET", "/relationships")["relationships"]) >= 2  # added at once
    expect(page.locator(".toast", has_text="Added")).to_be_visible()
    shot(page, "finder-drawn")
    page.context.close()


def test_a_new_notebook_says_how_it_works(browser: Browser, server: dict[str, Any]) -> None:
    page = browser.new_context(
        viewport={"width": 1400, "height": 900}, device_scale_factor=2 if SHOTS else 1
    ).new_page()
    page.goto(f"http://127.0.0.1:{server['port']}/workbench?kind=notebook&view=list#token={server['token']}")
    empty = page.locator(".wb-landing .empty-state")
    expect(empty).to_be_visible(timeout=30000)
    expect(empty).to_contain_text("Python, DuckDB SQL and notes")
    shot(page, "empty-notebooks")
    empty.get_by_role("button", name="New notebook").click()
    expect(page.locator(".wb-cell").first).to_contain_text("Shift+Enter runs", timeout=30000)
    shot(page, "notebook-hint")
    page.context.close()


def test_a_project_closes_from_the_projects_page(browser: Browser, server: dict[str, Any]) -> None:
    folder = Path(server["tmp"]) / "close-me"
    call(server, "POST", "/project/new", {"path": str(folder)})
    call(server, "POST", "/project/autosave", {"on": False})
    # Unsaved changes (tables opened, Autosave off), before the page: an arriving table moves Projects away.
    call(server, "POST", "/samples/store")
    page = home(browser, server, "?open=projects")
    projects = page.locator(".area-page[data-page='projects']")
    top = projects.locator(".explorer-open-line")
    expect(top).to_contain_text("close-me is open", timeout=20000)
    card = projects.locator(".explorer-card.is-open")
    expect(card.locator(".explorer-open-mark")).to_be_visible()
    shot(page, "projects-close")
    # The existing question; the first answer (Cancel) keeps it open.
    asked: list[str] = []

    def answer(dialog: Any) -> None:
        asked.append(dialog.message)
        if len(asked) == 1:
            dialog.dismiss()
        else:
            dialog.accept()

    page.on("dialog", answer)
    card.get_by_role("button", name="Close project").click()
    page.wait_for_timeout(800)
    assert asked and "Let them go and close the project?" in asked[0], asked
    expect(top).to_be_visible()
    top.get_by_role("button", name="Close project").click()
    expect(top).to_have_count(0, timeout=20000)
    expect(projects.locator(".explorer-card.is-open")).to_have_count(0)
    expect(projects).to_be_visible()  # the Projects page stays
    assert call(server, "GET", "/project")["project"] is None
    page.context.close()
