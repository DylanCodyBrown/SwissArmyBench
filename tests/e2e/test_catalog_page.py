# ruff: noqa: F811
"""The blades page in a real browser: the list, the blade screen (its code read-only, a table name of its
own checked as it is typed, Show its file), New blade, import, export, blade folders and packs. The catalog
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
    """The blades page (the name is the old fixture's: a catalog called Warehouse it no longer loads)."""
    yield f"http://127.0.0.1:{server['port']}/catalog#token={server['token']}"
    for blade in call(server, "GET", "/blades")["blades"]:
        call(server, "DELETE", f"/blades/{quote(blade['name'])}")
    for catalog in call(server, "GET", "/catalogs")["catalogs"]:
        call(server, "DELETE", f"/catalogs/{quote(catalog['name'])}")


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


def test_a_theme_remembered_before_the_rename_is_still_followed(browser: Browser, warehouse: str) -> None:
    """Swiss Army Bench was SwissArmyGrid: a setting this browser kept under the old prefix is read while
    the new key is empty (web/src/dom.ts, test_renamed.py), and the new key wins once it is set."""
    page = open_page(browser, warehouse)
    page.evaluate("localStorage.setItem('swissarmygrid.theme', 'hc-dark')")
    page.reload()
    page.goto(warehouse)
    expect(page.locator("html")).to_have_attribute("data-theme", "hc-dark")
    page.evaluate("localStorage.setItem('swissarmybench.theme', 'hc-light')")
    page.reload()
    page.goto(warehouse)
    expect(page.locator("html")).to_have_attribute("data-theme", "hc-light")
    for key in ("swissarmygrid.theme", "swissarmybench.theme"):
        page.evaluate(f"localStorage.removeItem('{key}')")
    page.close()


def test_the_rail_takes_this_tab_to_the_blades_page(browser: Browser, orders_url: str) -> None:
    """A rail click moves this tab (the owner, 2026-11-16: "the open in new tab is optional")."""
    page = open_grid(browser, orders_url)
    pages = len(page.context.pages)
    page.locator(".nav-rail [data-area='blades']").click()
    expect(page).to_have_url(re.compile(r"/catalog"), timeout=20000)
    expect(page.get_by_role("heading", name="Connections and blades", exact=True)).to_be_visible()
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
            page.get_by_role("button", name="Import blades").click()
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
        page.get_by_role("button", name="Blade folders").click()
        dialog = page.locator("dialog")
        dialog.get_by_label("Folder to add").fill(str(folder))
        dialog.get_by_role("button", name="Add").click()
        dialog.get_by_role("button", name="Save").click()
        expect(dialog).to_have_count(0)
        orders = blade_item(page, "Orders app DB")
        expect(orders.locator(".blade-file")).to_have_text("file")
        expect(page.locator(".blade-list .blade-name")).to_have_count(1)
        orders.locator(".blade-name").click()
        expect(page.locator("#detail")).to_contain_text("orders.blade.py")
        expect(page.locator("#detail").get_by_role("button", name="Remove", exact=True)).to_have_count(
            0
        )  # its file is the user's to remove
        page.get_by_label("Description").fill("The orders app's database")
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator(".status-line")).to_contain_text("Saved Orders app DB.")
        assert 'description = "The orders app\'s database"' in (
            folder / "apps" / "orders.blade.py"
        ).read_text(encoding="utf-8")
        with page.expect_download() as download:
            page.locator("#detail").get_by_role("button", name="Export", exact=True).click()
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
        page.get_by_role("button", name="Import blades").click()
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


def test_a_packs_blade_is_read_only_and_a_new_marketplace_takes_blades(
    browser: Browser, server: dict[str, Any], warehouse: str, tmp_path: Path
) -> None:
    import json as json_module

    from swissarmybench.domain.blades import write_blade

    # A made-up installed pack in this server's own Claude folder (never the machine's).
    root = Path(server["tmp"]) / "claude" / "plugins" / "cache" / "team-blades" / "sales" / "1a2b3c4d5e6f"
    (root / "blades").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "sales"}', encoding="utf-8")
    (root / "blades" / "till.blade.py").write_text(
        write_blade({"name": "Till export", "kind": "other", "code": "rows = [1, 2]\n", "variable": "rows"}),
        encoding="utf-8",
    )
    record = {"plugins": {"sales@team-blades": [{"installPath": str(root), "version": "1a2b3c4d5e6f"}]}}
    (root.parents[3] / "installed_plugins.json").write_text(json_module.dumps(record), encoding="utf-8")
    repo = tmp_path / "data-blades"
    page = open_page(browser, warehouse)
    try:
        till = blade_item(page, "Till export")
        expect(till.locator(".blade-pack")).to_have_text("pack")
        till.locator(".blade-name").click()
        expect(page.locator("#detail")).to_contain_text("From the pack sales@team-blades")
        expect(page.locator("#detail").get_by_role("button", name="Save", exact=True)).to_have_count(0)
        page.locator("#detail").get_by_role("button", name="Copy as your own").click()
        expect(blade_item(page, "Till export copy")).to_have_count(1)
        # The Packs window: the installed pack, the commands, and a new marketplace repository.
        page.get_by_role("button", name="Packs").click()
        packs = page.locator("dialog")
        expect(packs.locator(".set-item", has_text="sales")).to_contain_text("version 1a2b3c4d5e6f")
        expect(packs).to_contain_text("/plugin install <pack>@<marketplace>")
        packs.get_by_role("button", name="New marketplace repository").click()
        form = page.locator("dialog").last
        form.get_by_label("New folder").fill(str(repo))
        form.get_by_label("Marketplace name").fill("data-blades")
        form.get_by_label("First pack's name").fill("bakery")
        form.get_by_role("button", name="Create").click()
        clone = page.locator("dialog .set-item", has_text="editable clone")
        expect(clone).to_contain_text("bakery", timeout=10000)
        clone.get_by_role("button", name="Add blades and tangs").click()
        adding = page.locator("dialog").last
        adding.get_by_label("Blade Till export copy").check()
        adding.get_by_role("button", name="Add", exact=True).click()
        expect(page.locator(".toast").last).to_contain_text("Added 1 files to bakery")
        written = repo / "packs" / "bakery" / "blades" / "till_export_copy.blade.py"
        assert "rows = [1, 2]" in written.read_text(encoding="utf-8")
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()
        call(server, "PUT", "/blades/folders", {"folders": []})
        import shutil

        shutil.rmtree(root.parents[3])


# ===== the blade screen (the owner, 2026-11-17) =====


def test_the_blades_page_has_no_catalog_panel(browser: Browser, warehouse: str) -> None:
    """ "we dont even need catalog if its just tables": no Catalog section, picker, tree or search."""
    page = open_page(browser, warehouse)
    expect(page.get_by_role("heading", name="Connections and blades", exact=True)).to_be_visible()
    expect(page.locator("#catalog")).to_have_count(0)
    expect(page.get_by_role("heading", name="Catalog", exact=True)).to_have_count(0)
    expect(page.locator("select[aria-label='Catalog']")).to_have_count(0)
    expect(page.get_by_role("searchbox", name="Search the catalog")).to_have_count(0)
    expect(page.locator("[role='tree']")).to_have_count(0)
    page.close()


def shoot(page: Page, name: str) -> None:
    if not SHOTS:
        return
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):  # the theme chosen, the page drawn again (Monaco's own theme too)
        page.evaluate(f"localStorage.setItem('swissarmybench.theme', '{theme}')")
        page.reload()
        page.locator(".blade-code .monaco-editor").first.wait_for(timeout=20000)
        page.evaluate("document.querySelectorAll('details.blade-listing').forEach((d) => (d.open = true))")
        page.wait_for_timeout(600)
        page.screenshot(path=str(Path(SHOTS) / f"{name}-{theme}.png"))
    page.evaluate("localStorage.removeItem('swissarmybench.theme')")
    page.reload()
    page.locator(".blade-code .monaco-editor").first.wait_for(timeout=20000)


def test_new_blade_makes_a_file_shown_read_only_with_its_table_name_checked(
    browser: Browser, server: dict[str, Any], warehouse: str
) -> None:
    call(server, "PUT", "/datasets/orders", {"columns": ["a"], "data": [[1]]})
    page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(warehouse)
    page.wait_for_selector(".blade-list")
    # Show its file is the user's click: stood in, so the test opens no file manager.
    page.route("**/blades/*/show", lambda route: route.fulfill(status=200, body='{"shown": "stood in"}'))
    try:
        page.get_by_role("button", name="New blade").first.click()
        page.get_by_role("button", name="A table (a DataFrame)").click()
        expect(page.locator("#detail h2")).to_have_text("Blade: New table")
        made = call(server, "GET", "/blades/New%20table")
        assert Path(made["file"]).is_file() and Path(made["file"]).parent.name == "blades"
        # The code read-only, as tall as it is: Monaco with line numbers, no typing.
        viewer = page.locator(".blade-code .monaco-editor")
        expect(viewer).to_be_visible(timeout=20000)
        expect(page.locator(".blade-code .line-numbers").first).to_be_visible()
        height = page.locator(".blade-code-monaco").evaluate("e => e.getBoundingClientRect().height")
        lines = made["code"].count("\n")
        assert 4 * 18 <= height <= max(lines, 4) * 22 + 20, height
        page.locator(".blade-code .view-lines").click()
        page.keyboard.type("typed")
        assert call(server, "GET", "/blades/New%20table")["code"] == made["code"]
        expect(page.get_by_role("button", name="Show its file")).to_be_visible()
        page.get_by_role("button", name="Show its file").click()
        expect(page.get_by_label("Blade code")).to_be_visible()
        expect(page.get_by_text("Add to the catalog")).to_have_count(0)
        expect(page.get_by_text("How its tables are listed")).to_have_count(0)
        # Its table's name: taken, then available, as it is typed.
        field = page.get_by_label("Its table is called")
        expect(field).to_have_attribute("placeholder", "make_table")
        field.fill("orders")
        expect(page.locator(".table-name-check")).to_have_text("orders is already a table")
        field.fill("orders_by_month")
        expect(page.locator(".table-name-check")).to_have_text("available")
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator(".status-line")).to_contain_text("Saved New table.")
        assert '# table = "orders_by_month"' in Path(made["file"]).read_text(encoding="utf-8")
        shoot(page, "blade-screen")
        # A taken name is refused on save with the same words.
        field = page.get_by_label("Its table is called")
        field.fill("orders")
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator(".status-line")).to_have_text("orders is already a table")
        assert errors == []
    finally:
        page.close()
        call(server, "DELETE", "/datasets/orders")


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
    page.goto(warehouse.replace("/catalog#", "/catalog?blade=Bakery#"))
    listing = page.locator("details.blade-listing")
    expect(listing.locator("summary")).to_have_text("How its tables are listed")
    expect(listing).not_to_have_attribute("open", "")
    listing.locator("summary").click()
    expect(listing.locator(".monaco-editor, pre")).to_contain_text("sqlite_master", timeout=20000)
    expect(page.get_by_label("Its table is called")).to_have_count(0)
    shoot(page, "connection-listing")
    page.goto(warehouse.replace("/catalog#", "/catalog?blade=SharePoint%20document%20as%20a%20table#"))
    expect(page.locator("#detail")).to_contain_text("starter: read-only")
    expect(page.get_by_role("button", name="Show its file")).to_have_count(0)
    expect(page.get_by_role("button", name="Copy as your own")).to_be_visible()
    expect(page.locator(".blade-code .monaco-editor")).to_be_visible(timeout=20000)
    shoot(page, "starter")
    assert page.errors == []  # type: ignore[attr-defined]
    page.close()
