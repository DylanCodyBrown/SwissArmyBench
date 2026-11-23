"""The Blazor Connections page against the classic one's elements, on made-up data: the cards' groups and their
colour (the palette), a card's detail (its tools, the tables' tree, Used in, the configuration, Queries' limits),
Add connection's types (the search, Enter), a kind's form (Sign in, Options, the flags, a password's one box), Find
connections on this computer over a made-up Windows home, Import…, the Queries window and the project's sandbox."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from playwright.sync_api import Browser, Page, expect

from tests import found_fixtures as fx
from tests.e2e.blazor.conftest import call, open_page


@pytest.fixture(scope="module", autouse=True)
def made_up_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Find connections looks only in a made-up Windows home folder (set before this module's server starts)."""
    home = fx.windows_home(tmp_path_factory.mktemp("findhome") / "fakehome")
    kept = {k: os.environ.get(k) for k in ("SWISSARMYBENCH_FIND_HOME", "SWISSARMYBENCH_FIND_SYSTEM")}
    os.environ["SWISSARMYBENCH_FIND_HOME"] = str(home)
    os.environ["SWISSARMYBENCH_FIND_SYSTEM"] = "windows"
    yield
    for key, value in kept.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def saved_shop(server: dict[str, Any]) -> str:
    """A made-up DuckDB file saved as the connection Shop (two tables), by the server's own routes."""
    path = Path(server["tmp"]) / "shop.duckdb"
    if not path.exists():
        with duckdb.connect(str(path)) as db:
            db.execute("CREATE TABLE orders AS SELECT i AS order_id, 1 + i % 7 AS customer_id FROM range(1, 51) t(i)")
            db.execute("CREATE TABLE customers AS SELECT i AS customer_id, 'C' || i AS name FROM range(1, 8) t(i)")
    kind = next(t for t in call(server, "GET", "/connections/types")["types"] if t["id"] == "duckdb")
    filled = call(server, "POST", "/blades/fill", {"code": kind["code"], "values": {kind["fields"][0]["id"]: {"text": str(path)}}, "template": "duckdb", "name": None})
    body = {"name": "Shop", "description": "made up", "kind": kind["kind"], "template": "duckdb", "dialect": "duckdb", "variable": "conn", "code": filled["code"], "catalog": kind["catalog"]}
    if not any(c["name"] == "Shop" for c in call(server, "GET", "/connections")["connections"]):
        call(server, "POST", "/connections", body)
    call(server, "POST", "/blades/Shop/refresh")
    return "Shop"


def note(page: Page, words: str) -> None:
    expect(page.locator(".note-corner, .notes").filter(has_text=words).first).to_be_visible()


def test_cards_and_a_cards_colour(browser: Browser, server: dict[str, Any]) -> None:
    saved_shop(server)
    page = open_page(browser, server, "connections")
    expect(page.locator(".connection-group-title").first).to_have_text("Databases")
    card = page.locator(".connection-card[data-name=Shop]")
    expect(card.locator(".connection-card-type")).to_have_text("DuckDB file")
    expect(card).to_contain_text("Only works on your machine")
    card.click()
    expect(page.locator("h1")).to_contain_text("Shop")
    expect(page.locator(".back-btn")).to_have_attribute("aria-label", "Back to Connections")
    page.click("button[aria-label=\"Shop's colour\"]")
    palette = page.locator(".conn-palette")
    expect(palette).to_be_visible()
    palette.locator(".conn-palette-swatch[aria-label=Magenta]").click()
    expect(palette).to_be_hidden()
    assert next(c for c in call(server, "GET", "/connection-colours")["connections"] if c["name"] == "Shop")["chosen"] == "#b3307f"
    page.click("button[aria-label=\"Shop's colour\"]")
    page.keyboard.press("Escape")
    expect(palette).to_be_hidden()
    page.close()


def test_a_connections_detail(browser: Browser, server: dict[str, Any]) -> None:
    saved_shop(server)
    page = open_page(browser, server, "connections?name=Shop")
    tools = page.locator(".connection-detail-tools")
    for words in ("Edit", "Test", "Refresh catalog", "Copy for Python", "Remove"):
        expect(tools.locator(f"text={words}").first).to_be_visible()
    config = page.locator(".connection-config")
    expect(config).to_contain_text("DuckDB file")
    expect(config).to_contain_text('sab.connection("Shop")')
    expect(config).to_contain_text("Read-only")
    expect(page.locator(".connection-used")).to_contain_text("No references")
    tools.locator("button:has-text('Test')").click()
    note(page, "Shop works:")
    tools.locator("button:has-text('Refresh catalog')").click()
    note(page, "Shop: 2 tables")
    # The tables' tree: the search, a preview under its table, Open all asked first.
    tree = page.locator(".connection-tables")
    tree.locator(".conn-tree-search").fill("zzz")
    expect(tree).to_contain_text("No table matches")
    tree.locator(".conn-tree-search").fill("ord")
    orders = tree.locator(".conn-tree-table[data-table=orders]")
    orders.locator("button:has-text('Preview')").click()
    expect(orders.locator(".connection-preview")).to_contain_text("order_id")
    expect(orders).to_contain_text("main.orders: the first")
    tree.locator(".conn-tree-search").fill("")
    tree.locator("button:has-text('Open all')").click()
    expect(page.locator(".dialog")).to_contain_text("Open all 2 tables of main? Each opens as its own grid.")
    page.locator(".dialog button[aria-label=Close]").click()
    # Queries: the limits saved.
    page.fill("input[aria-label='Queries at once']", "6")
    page.locator(".connection-queries button:has-text('Save')").click()
    note(page, "Shop: 6 at once, 4 of them the agent's")
    assert call(server, "GET", "/connections/Shop/limits")["total"] == 6
    # Remove asks in the classic words; No keeps it.
    tools.locator("button:has-text('Remove')").click()
    expect(page.locator(".dialog")).to_contain_text("Remove the connection Shop? Its saved passwords go too.")
    page.keyboard.press("Escape")
    expect(page.locator("h1")).to_contain_text("Shop")
    page.close()


def test_add_connections_types_and_a_form(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "connections?add=1")
    search = page.locator("input[aria-label='Search the connection types']")
    expect(search).to_be_focused()
    search.fill("nothing like it")
    expect(page.locator("text=No connection type matches.")).to_be_visible()
    search.fill("sql server")
    search.press("Enter")
    expect(page).to_have_url(re.compile(r"connections\?kind=sqlserver"))
    expect(page.locator(".connection-form h3")).to_have_text("New SQL Server connection")
    form = page.locator(".connection-form")
    expect(form.locator("select[aria-label='Sign in']")).to_be_visible()
    form.locator("details.connection-options summary").click()
    expect(form.locator(".connection-options-fields input[aria-label='Trust server certificate']")).to_be_visible()
    expect(form.locator("select[aria-label=Encryption]")).to_have_value("mandatory")
    # A password is one box: a variable on its own, never part of one.
    password = form.locator("input[aria-label=Password]")
    password.fill("x$" + "{MADE_UP}y")
    password.blur()
    expect(form.locator(".error-note")).to_contain_text("Password takes one variable on its own")
    password.fill("$" + "{MADE_UP_PASSWORD}")
    password.blur()
    expect(form.locator(".connection-code-text")).to_have_value(re.compile("MADE_UP_PASSWORD"))
    # Sign in switched: its own code, the server's name kept.
    form.locator("input[aria-label=Server]").fill("made-up-server")
    form.locator("input[aria-label=Server]").blur()
    expect(form.locator(".connection-code-text")).to_have_value(re.compile("made-up-server"))
    form.locator("select[aria-label='Sign in']").select_option(label="Microsoft Entra: managed identity (in Azure)")
    expect(form.locator(".connection-code-text")).to_have_value(re.compile("made-up-server"))
    expect(form.locator("input[aria-label=Password]")).to_have_count(0)
    expect(page.locator(".back-btn")).to_have_attribute("aria-label", "Back to Add connection")
    page.close()


def test_find_and_import(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "connections")
    page.click("text=Find connections on this computer…")
    dialog = page.locator(".dialog[aria-label='Find connections on this computer']")
    expect(dialog.locator(".find-count")).to_contain_text("found")
    go = dialog.locator(".dialog-foot button.primary")
    expect(go).to_be_disabled()
    first = dialog.locator(".find-row:not(.find-off) input[type=checkbox]").first
    first.check()
    expect(go).to_have_text(re.compile("Import 1"))
    dialog.locator("input[aria-label='Search the found connections']").fill("no such connection at all")
    expect(dialog.locator(".find-row")).to_have_count(0)
    dialog.locator(".dialog-foot button:has-text('Cancel')").click()
    expect(dialog).to_be_hidden()
    page.click("button:has-text('Import…')")
    expect(page.locator(".dialog[aria-label='Import connections']")).to_contain_text("Another project…")
    page.keyboard.press("Escape")
    page.close()


def test_queries_window_and_the_sandbox(browser: Browser, server: dict[str, Any]) -> None:
    saved_shop(server)
    page = open_page(browser, server, "connections?queries=Shop")
    expect(page.locator(".queries-main h1")).to_contain_text("Queries")
    expect(page.locator("select[aria-label=Connection]")).to_have_value("Shop")
    expect(page.locator(".queries-finished")).to_contain_text("catalog listing")
    page.locator(".queries-finished button:has-text('Clear')").click()
    expect(page.locator(".queries-finished")).to_have_count(0)
    page.goto(page.url.replace("queries=Shop", "sandbox=1"))
    page.wait_for_selector(".sandbox-panel")
    expect(page.locator(".sandbox-panel")).to_contain_text("Open a project: its sandbox lives in its folder.")
    call(server, "POST", "/project/new", {"name": "Made up sandbox"})
    expect(page.locator(".sandbox-panel")).to_contain_text("No tables yet")
    page.click("text=Add table…")
    dialog = page.locator(".dialog[aria-label='Add a table to the sandbox']")
    dialog.locator("select[aria-label=From]").select_option("columns")
    dialog.locator("textarea[aria-label=Columns]").fill("id integer key\nnote text")
    dialog.locator("input[aria-label='Its name in the sandbox']").fill("notes")
    dialog.locator("button:has-text('Add')").click()
    row = page.locator(".sandbox-tables tr[data-table=notes]")
    expect(row).to_contain_text("Made empty, by its columns")
    page.locator(".sandbox-sort:has-text('Rows')").click()
    expect(page.locator("th[aria-sort=ascending]")).to_contain_text("Rows")
    row.locator("button[aria-label='Remove notes']").click()
    note(page, "notes is out of the sandbox.")
    call(server, "POST", "/project/close", {})
    page.close()
