# ruff: noqa: F811
"""The blades page in a real browser: the list, the blade IDE (the owner, 2026-11-21: "This is an IDE not a
save form": code typed with the lint, Run, Output and Result, Save, Cancel, a table name of its own checked as
it is typed in Properties), New blade, import, export, blade folders and packs. The catalog
panel went (the owner, 2026-11-17): a connection's tables are on the Connections page.

Made-up data only. No test saves a secret: on Windows that would reach the real Credential Manager.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Page, expect

# The grid tests' fixtures (browser, server, orders_url) are imported by name, which pytest needs and ruff
# reads as a redefinition in every test that takes them.
from tests.e2e.test_ui import browser, call, open_grid, orders_url, server  # noqa: F401

# Screenshots of the blade screen, light and dark, where this names a folder (none: no pictures).
SHOTS = os.environ.get("SWISSARMYBENCH_TEST_SHOTS", "")


@pytest.fixture
def warehouse(server: dict[str, Any]) -> Iterator[str]:
    """The Scripts page's Blades (the old blades page went, 2026-11-21; the name is the old fixture's)."""
    yield f"http://127.0.0.1:{server['port']}/scripts?pane=blades#token={server['token']}"
    for blade in call(server, "GET", "/blades")["blades"]:
        call(server, "DELETE", f"/blades/{quote(blade['name'])}")
    for catalog in call(server, "GET", "/catalogs")["catalogs"]:
        call(server, "DELETE", f"/catalogs/{quote(catalog['name'])}")


def blades_menu(page: Page, item: str) -> None:
    """The Blades pane's "…": import (review first), export, blade folders, packs (2026-11-21)."""
    page.get_by_role("button", name="Blades menu").click()
    page.get_by_role("menuitem", name=item).click()


def open_page(browser: Browser, url: str) -> Page:
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_selector(".blade-list")
    page.errors = errors  # type: ignore[attr-defined]
    return page


def test_the_page_follows_the_theme(browser: Browser, warehouse: str) -> None:
    page = open_page(browser, warehouse)
    page.evaluate("localStorage.setItem('swissarmybench.theme', 'hc-dark')")
    page.reload()
    page.goto(warehouse)
    expect(page.locator("html")).to_have_attribute("data-theme", "hc-dark")
    page.evaluate("localStorage.removeItem('swissarmybench.theme')")
    page.close()


def test_the_rail_takes_this_tab_to_the_blades_page(browser: Browser, orders_url: str) -> None:
    """A rail click moves this tab (the owner, 2026-11-16: "the open in new tab is optional")."""
    page = open_grid(browser, orders_url)
    pages = len(page.context.pages)
    page.locator(".nav-rail [data-area='blades']").click()
    # The blades live on the Scripts page, below its files (the owner, 2026-11-21).
    expect(page).to_have_url(re.compile(r"/scripts\?.*pane=blades"), timeout=20000)
    expect(page.locator(".wb-codex-lower.lower-blades .blade-list")).to_be_visible(timeout=20000)
    assert len(page.context.pages) == pages
    page.close()


# ===== portable blades: search, tags, favourites, import, export, blade folders =====


def blade_item(page: Page, name: str) -> Any:
    return page.locator(".blade-item", has=page.locator(f'.blade-name:text-is("{name}")'))


def test_blades_are_found_by_name_description_or_tag_and_favourites_come_first(
    browser: Browser, server: dict[str, Any], warehouse: str
) -> None:
    for name, description, tags in [
        ("Bakery", "Daily bread counts", ["bakery"]),
        ("Orders feed", "What the orders app reads", ["orders-function-app", "sales"]),
        ("Stock", "Shelf stock", ["sales"]),
    ]:
        call(
            server,
            "POST",
            "/blades",
            {"name": name, "kind": "other", "code": "x = 1\n", "description": description, "tags": tags},
        )
    page = open_page(browser, warehouse)
    names = page.locator(".blade-list .blade-name")
    expect(names).to_have_count(3)
    search = page.get_by_label("Search blades")
    search.fill("orders-function")  # a tag
    expect(names).to_have_text(["Orders feed"])
    search.fill("shelf")  # a description
    expect(names).to_have_text(["Stock"])
    search.fill("")
    page.locator(".blade-tags").get_by_role("button", name="sales").click()
    expect(names).to_have_text(["Orders feed", "Stock"])
    page.locator(".blade-tags").get_by_role("button", name="sales").click()  # again: every tag
    expect(names).to_have_count(3)
    blade_item(page, "Stock").get_by_role("button", name="Pin", exact=True).click()
    expect(names.first).to_have_text("Stock")
    expect(blade_item(page, "Stock").get_by_role("button", name="Unpin")).to_have_attribute(
        "aria-pressed", "true"
    )
    pinned = {b["name"]: b["pinned"] for b in call(server, "GET", "/blades")["blades"]}
    assert pinned == {"Bakery": False, "Orders feed": False, "Stock": True}
    page.reload()
    expect(names.first).to_have_text("Stock")  # kept on this computer
    call(server, "PUT", "/blades/Stock/pin", {"pinned": False})
    assert page.errors == []  # type: ignore[attr-defined]
    page.close()


def test_an_imported_blade_file_is_reviewed_first_and_a_taken_name_keeps_both(
    browser: Browser, server: dict[str, Any], warehouse: str, tmp_path: Path
) -> None:
    from swissarmybench.domain.blades import write_blade

    marker = tmp_path / "ran.txt"
    code = f"open({str(marker)!r}, 'w').write('ran')\nconn = 1\n"
    blade_file = tmp_path / "bakery_db.blade.py"
    blade_file.write_text(
        write_blade(
            {
                "name": "Bakery DB",
                "kind": "other",
                "code": code,
                "variable": "conn",
                "description": "The bakery's made-up database",
                "tags": ["bakery", "orders-function-app"],
            }
        ),
        encoding="utf-8",
    )
    page = open_page(browser, warehouse)
    for round_ in (1, 2):
        with page.expect_file_chooser() as chooser:
            blades_menu(page, "Import blades…")
        chooser.value.set_files(str(blade_file))
        dialog = page.locator("dialog")
        expect(dialog.locator(".import-card h3")).to_contain_text("Bakery DB")
        expect(dialog).to_contain_text("The bakery's made-up database")
        dialog.locator("summary", has_text="The code").click()
        expect(dialog.locator("pre")).to_contain_text("conn = 1")
        if round_ == 2:  # the name is taken now: keep both is offered first
            expect(dialog.get_by_label("When Bakery DB is taken")).to_have_value("copy")
        assert not marker.exists()  # reviewing runs nothing
        dialog.get_by_role("button", name="Import 1 blade").click()
        expect(dialog).to_have_count(0)
    expect(page.locator(".blade-list .blade-name")).to_have_text(["Bakery DB", "Bakery DB 2"])
    saved = call(server, "GET", "/blades/Bakery%20DB")
    assert saved["tags"] == ["bakery", "orders-function-app"] and saved["code"] == code
    assert not marker.exists()  # nor does importing
    assert page.errors == []  # type: ignore[attr-defined]
    page.close()


def test_a_blade_folder_lists_its_blade_files_and_the_save_screen_exports(
    browser: Browser, server: dict[str, Any], warehouse: str, tmp_path: Path
) -> None:
    from swissarmybench.domain.blades import write_blade

    folder = tmp_path / "team blades"
    (folder / "apps").mkdir(parents=True)
    (folder / "apps" / "orders.blade.py").write_text(
        write_blade(
            {
                "name": "Orders app DB",
                "kind": "other",
                "code": "conn = 2\n",
                "variable": "conn",
                "tags": ["orders-function-app"],
            }
        ),
        encoding="utf-8",
    )
    (folder / "helper.py").write_text("x = 1\n", encoding="utf-8")  # an ordinary file: not a blade
    page = open_page(browser, warehouse)
    try:
        blades_menu(page, "Blade folders…")
        dialog = page.locator("dialog")
        dialog.get_by_label("Folder to add").fill(str(folder))
        dialog.get_by_role("button", name="Add").click()
        dialog.get_by_role("button", name="Save").click()
        expect(dialog).to_have_count(0)
        orders = blade_item(page, "Orders app DB")
        expect(orders.locator(".blade-file")).to_have_text("file")
        expect(page.locator(".blade-list .blade-name")).to_have_count(1)
        orders.locator(".blade-name").click()
        expect(page.locator(".code-ide:visible")).to_contain_text("orders.blade.py")
        page.locator(".code-ide:visible").get_by_role("button", name="More").click()
        expect(page.get_by_role("menuitem", name="Remove")).to_have_count(0)  # its file is the user's
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Properties").click()
        page.get_by_label("Description").fill("The orders app's database")
        expect(page.locator(".ide-dirty")).to_be_visible()
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator(".ide-dirty")).to_be_hidden()
        assert 'description = "The orders app\'s database"' in (
            folder / "apps" / "orders.blade.py"
        ).read_text(encoding="utf-8")
        page.locator(".code-ide:visible").get_by_role("button", name="More").click()
        with page.expect_download() as download:
            page.get_by_role("menuitem", name="Export").click()
        assert download.value.suggested_filename == "orders_app_db.blade.py"
        assert "conn = 2" in Path(download.value.path()).read_text(encoding="utf-8")
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        call(server, "PUT", "/blades/folders", {"folders": []})
        page.close()


POSTGRES_STARTER = (
    "import psycopg\n\nconn = psycopg.connect(\n"
    '    host="my-server",\n    port=5432,\n    dbname="my_database",\n'
    '    user="my_user",\n    password=secret("password"),\n)\n'
)


def test_import_suggests_values_for_a_blades_settings_and_writes_them_in(
    browser: Browser, server: dict[str, Any], warehouse: str, tmp_path: Path
) -> None:
    from swissarmybench.domain.blades import write_blade

    mine = 'import psycopg\nconn = psycopg.connect(host="db01.corp.local", dbname="sales")\n'
    call(server, "POST", "/blades", {"name": "Sales DB", "kind": "sql", "dialect": "postgres", "code": mine})
    blade_file = tmp_path / "orders_db.blade.py"
    blade_file.write_text(
        write_blade(
            {
                "name": "Orders DB",
                "kind": "sql",
                "dialect": "postgres",
                "code": POSTGRES_STARTER,
                "variable": "conn",
            }
        ),
        encoding="utf-8",
    )
    page = open_page(browser, warehouse)
    with page.expect_file_chooser() as chooser:
        blades_menu(page, "Import blades…")
    chooser.value.set_files(str(blade_file))
    fill = page.locator("dialog fieldset.fill-in")
    expect(fill.locator(".needs-value-badge")).to_have_count(3)  # host, dbname, user
    host = fill.locator(".setting-row", has=page.get_by_label("host (server)"))
    host.get_by_role("button", name="db01.corp.local").click()
    expect(page.get_by_label("host (server)")).to_have_value("db01.corp.local")
    page.get_by_label("dbname (database)").fill("orders")
    page.locator("dialog").get_by_role("button", name="Import 1 blade").click()
    expect(page.locator("dialog")).to_have_count(0)
    saved = call(server, "GET", "/blades/Orders%20DB")["code"]
    assert 'host="db01.corp.local"' in saved and 'dbname="orders"' in saved and 'user="my_user"' in saved
    assert page.errors == []  # type: ignore[attr-defined]
    page.close()


def test_a_long_blade_name_never_hides_the_blade_buttons(
    browser: Browser, server: dict[str, Any], warehouse: str
) -> None:
    for name in ("Quarterly finance extract for the regional managers", "Warehouse"):
        call(server, "POST", "/blades", {"name": name, "kind": "other", "code": "x = 1\n"})
    page = open_page(browser, warehouse)
    listing = page.locator(".blade-list")
    expect(listing.locator(".blade-item")).to_have_count(2)
    assert listing.evaluate("e => e.scrollWidth <= e.clientWidth")
    for item in listing.locator(".blade-item").all():
        expect(item.get_by_role("button", name="Copy the sab.blade line")).to_be_in_viewport()
    page.close()


def test_the_blades_pane_has_no_catalog_panel(browser: Browser, warehouse: str) -> None:
    """ "we dont even need catalog if its just tables": no Catalog section, picker, tree or search; and the
    old blades page's address is the Scripts page's Blades (2026-11-21)."""
    page = open_page(browser, warehouse.replace("/scripts?pane=blades#", "/catalog#"))
    expect(page).to_have_url(re.compile(r"/scripts\?pane=blades"))
    pane = page.locator(".wb-codex-lower.lower-blades")
    expect(pane.get_by_role("heading", name="Connections and blades", exact=True)).to_be_visible()
    expect(pane.locator("#catalog")).to_have_count(0)
    expect(pane.get_by_role("heading", name="Catalog", exact=True)).to_have_count(0)
    expect(pane.locator("select[aria-label='Catalog']")).to_have_count(0)
    expect(pane.get_by_role("searchbox", name="Search the catalog")).to_have_count(0)
    page.close()


def shoot(page: Page, name: str) -> None:
    if not SHOTS:
        return
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(400)
    page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def editor(page: Page) -> Any:
    found = page.locator(".code-ide .ide-editor .monaco-editor")
    expect(found).to_be_visible(timeout=20000)
    return found


def type_in(page: Page, text: str) -> None:
    """The editor's whole text replaced by typing (Monaco's own keys)."""
    editor(page).locator(".view-lines").click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(text)


# No indented lines: Monaco indents a typed line after a colon by itself.
TYPED = (
    "import pandas as pd\n\nprint('baking loaves')\n"
    'make_table = pd.DataFrame({"loaf": ["rye", "spelt", "wheat"], "grams": [800, 750, 900]})\n'
)


def test_the_blade_screen_is_an_ide_typed_linted_run_saved_and_cancelled(
    browser: Browser, server: dict[str, Any], warehouse: str
) -> None:
    call(server, "PUT", "/datasets/orders", {"columns": ["a"], "data": [[1]]})
    page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(warehouse)
    page.wait_for_selector(".blade-list")
    try:
        page.get_by_role("button", name="New blade").first.click()
        dialog = page.get_by_role("dialog", name="New blade")
        dialog.get_by_label("Name").fill("New table")
        dialog.get_by_role("button", name="Create").click()
        ide = page.locator(".code-ide")
        expect(ide.locator(".ide-name")).to_have_text("New table")
        made = call(server, "GET", "/blades/New%20table")
        file = Path(made["file"])
        assert file.is_file() and file.parent.name == "blades"
        # Never crowded (8.14): the panel folded to its tabs; Properties open only on a brand-new scaffold.
        expect(page.locator(".ide-props")).to_be_visible()
        page.get_by_role("button", name="Properties").click()
        expect(page.locator(".ide-props")).to_be_hidden()
        expect(page.locator(".ide-panel")).to_have_class(re.compile("folded"))
        # A lint squiggle as it is typed, its problem listed; fixed, it goes.
        type_in(page, TYPED.replace("make_table = pd.DataFrame", "make_table = missing_name or pd.DataFrame"))
        expect(editor(page).locator(".squiggly-error").first).to_be_attached(timeout=15000)
        expect(ide.locator(".ide-dirty")).to_be_visible()
        page.get_by_role("tab", name=re.compile("Problems")).click()
        expect(page.locator(".ide-problem").first).to_contain_text("missing_name")
        type_in(page, TYPED)
        expect(editor(page).locator(".squiggly-error")).to_have_count(0, timeout=15000)
        # Run: the output, then the table in Result with its count and Open as grid.
        page.get_by_role("button", name="Run", exact=True).click()
        expect(page.locator(".ide-result-table")).to_be_visible(timeout=30000)
        expect(page.locator(".ide-row-count")).to_have_text("3 rows, 2 columns")
        expect(page.locator(".ide-grid tbody tr").first).to_contain_text("rye")
        page.get_by_role("tab", name="Output").click()
        expect(page.locator(".ide-output")).to_contain_text("baking loaves")
        page.get_by_role("tab", name="Result").click()
        assert call(server, "GET", "/blades/New%20table")["code"] == made["code"]  # not saved yet
        # Properties: its table's name checked as it is typed.
        page.get_by_role("button", name="Properties").click()
        field = page.get_by_label("Its table is called")
        expect(field).to_have_attribute("placeholder", "make_table")
        field.fill("orders")
        expect(page.locator(".table-name-check")).to_have_text("orders is already a table")
        field.fill("loaves")
        expect(page.locator(".table-name-check")).to_have_text("available")
        shoot(page, "blade-ide-run")
        # Save (Ctrl+S) writes the file: the code and the header's table name.
        editor(page).locator(".view-lines").click()
        page.keyboard.press("Control+S")
        expect(ide.locator(".ide-dirty")).to_be_hidden(timeout=10000)
        text = file.read_text(encoding="utf-8")
        assert text.endswith(TYPED) and '# table = "loaves"' in text
        # Cancel goes back to the file, asking first when there are unsaved changes.
        type_in(page, "value = 1\n")
        page.get_by_role("button", name="Cancel", exact=True).click()
        page.get_by_role("button", name="Throw them away").click()
        expect(editor(page)).to_contain_text("baking loaves")
        expect(ide.locator(".ide-dirty")).to_be_hidden()
        # The code zooms on its own (Ctrl+= / Ctrl+0 over the code): the size shows only while not 100%.
        zoom = ide.locator(".ide-zoom")
        expect(zoom).to_be_hidden()
        size = editor(page).locator(".view-line").first.evaluate("e => getComputedStyle(e).fontSize")
        editor(page).locator(".view-lines").click()
        page.keyboard.press("Control+Equal")
        page.keyboard.press("Control+Equal")
        expect(zoom).to_have_text("115%")
        assert editor(page).locator(".view-line").first.evaluate("e => getComputedStyle(e).fontSize") != size
        page.keyboard.press("Control+0")
        expect(zoom).to_be_hidden()
        # An edit made outside shows at once while nothing is unsaved.
        file.write_text(text.replace("baking loaves", "fresh from the oven"), encoding="utf-8")
        expect(editor(page)).to_contain_text("fresh from the oven", timeout=10000)
        assert errors == []
    finally:
        page.close()
        call(server, "DELETE", "/datasets/orders")
        call(server, "DELETE", "/blades/New%20table")


def test_a_starter_is_copied_and_a_connection_shows_how_its_tables_are_listed(
    browser: Browser, server: dict[str, Any], warehouse: str
) -> None:
    call(
        server,
        "POST",
        "/blades",
        {
            "name": "Bakery",
            "kind": "sql",
            "template": "sqlite",
            "dialect": "sqlite",
            "code": "import sqlite3\nconn = sqlite3.connect(':memory:')\n",
        },
    )
    page = open_page(browser, warehouse)
    page.goto(warehouse.replace("?pane=blades#", "?pane=blades&blade=Bakery#"))
    page.get_by_role("button", name="Properties").click()
    # Every header field a connection has (2026-11-21): its listing query is one, editable.
    listing = page.get_by_label("How its tables are listed")
    expect(listing).to_have_value(re.compile("sqlite_master"), timeout=20000)
    expect(page.get_by_label("SQL dialect")).to_have_value("sqlite")
    expect(page.get_by_label("Its table is called")).to_have_count(0)
    page.goto(
        warehouse.replace("?pane=blades#", "?pane=blades&blade=SharePoint%20document%20as%20a%20table#")
    )
    expect(page.locator(".code-ide .ide-readonly")).to_have_text("read-only")
    editor(page)
    # A starter's Save is refused, with Copy as your own beside the words.
    page.get_by_role("button", name="Save", exact=True).click()
    note = page.locator(".ide-note")
    expect(note).to_contain_text("starter (read-only)")
    note.get_by_role("button", name="Copy as your own").click()
    expect(page.locator(".code-ide .ide-name")).to_have_text("SharePoint document as a table copy")
    expect(page.locator(".code-ide .ide-readonly")).to_have_count(0)
    call(server, "DELETE", "/blades/SharePoint%20document%20as%20a%20table%20copy")
    assert page.errors == []  # type: ignore[attr-defined]
    page.close()
