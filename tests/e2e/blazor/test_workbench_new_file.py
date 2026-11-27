"""New file on the Scripts page (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down
combo that asks what file type you wanna create. SQL python json etc. then scaffolds it for you"), in the
browser on a made-up project: the dropdown's types, SQL picked and named (an open .sql tab with its connection
line), JSON picked (a structure tab), a taken name said in the dialog, a notebook made on the Notebooks page,
the tab strip's "+" with the same choices, and with no project open a Python script and a SQL file starting
untitled as before."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page

TYPES = [
    "Python script (.py)",
    "SQL file (.sql)",
    "JSON (.json)",
    "YAML (.yaml)",
    "TOML (.toml)",
    "XML (.xml)",
    "Markdown (.md)",
    "Plain text (.txt)",
    "Notebook (.ipynb)",
]


def project(server: dict[str, Any], name: str) -> Path:
    """A made-up project, open on the module's server; its folder."""
    state = call(server, "POST", "/project/new", {"path": str(server["tmp"] / "projects" / name)})
    return Path(state.get("folder") or state["project"]["folder"])


def pick(page: Page, line: str) -> None:
    page.click(".wb-top-new")
    page.click(f".context-menu [role=menuitem]:has-text('{line}')")


def test_sql_picked_and_named_opens_a_sql_tab_with_its_connection_line(
    browser: Browser, server: dict[str, Any]
) -> None:
    call(server, "POST", "/samples/store", {})  # the made-up store: customers, orders, products
    folder = project(server, "made_up_new_sql")
    page = open_page(browser, server, "scripts")
    expect(page.locator(".wb-top-new")).to_contain_text("New file")
    page.click(".wb-top-new")
    lines = page.locator(".context-menu [role=menuitem]")
    for at, line in enumerate(TYPES):  # in this order (beta mode's Leave a note… comes after them)
        expect(lines.nth(at)).to_have_text(line)
    page.click(".context-menu [role=menuitem]:has-text('SQL file')")

    dialog = page.locator(".dialog[aria-label='New SQL file']")
    name = dialog.get_by_label("Name")
    expect(name).to_have_value("query.sql")  # the ending filled in
    expect(dialog.get_by_label("Folder")).to_have_value("scripts")
    expect(dialog.get_by_label("Query from")).to_have_value("")  # DuckDB over the open tables
    expect(dialog.locator(".new-file-check")).to_have_text("Makes scripts/query.sql")
    name.fill("orders.json")  # another type's ending: checked, said
    expect(dialog.locator(".new-file-check")).to_contain_text("names a JSON file")
    name.fill("orders_by_month")
    expect(dialog.locator(".new-file-check")).to_have_text("Makes scripts/orders_by_month.sql")
    dialog.get_by_role("button", name="Create").click()

    expect(dialog).to_have_count(0)
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("orders_by_month.sql")
    editor = page.locator(".wb-sql .wb-script-editor .view-lines")
    expect(editor).to_contain_text("-- connection:")
    expect(editor).to_contain_text("customers")  # the first rows of an open table
    expect(page.locator(".wb-sql-from")).to_have_value("")
    made = folder / "scripts" / "orders_by_month.sql"
    text = made.read_text(encoding="utf-8")
    assert text.startswith("-- connection:\n") and 'FROM "customers"\nLIMIT 100;' in text
    expect(page.locator(".files-pane .files-item[data-path='scripts/orders_by_month.sql']")).to_be_visible()

    # The same name again: refused in one plain sentence, the dialog stays for another name.
    pick(page, "SQL file")
    dialog.get_by_label("Name").fill("orders_by_month")
    expect(dialog.locator(".new-file-check")).to_have_text(
        "scripts/orders_by_month.sql is there already: pick another name."
    )
    dialog.get_by_role("button", name="Create").click()
    expect(dialog).to_be_visible()
    expect(dialog.locator(".new-file-check.error")).to_be_visible()
    dialog.get_by_role("button", name="Cancel").click()
    assert made.read_text(encoding="utf-8") == text
    page.close()


def test_json_picked_opens_a_structure_tab(browser: Browser, server: dict[str, Any]) -> None:
    folder = project(server, "made_up_new_json")
    page = open_page(browser, server, "scripts")
    pick(page, "JSON")
    dialog = page.locator(".dialog[aria-label='New JSON']")
    expect(dialog.get_by_label("Name")).to_have_value("data.json")
    expect(dialog.get_by_label("Folder")).to_have_value("structures")
    expect(dialog.get_by_label("Query from")).to_have_count(0)  # only a SQL file asks where it runs
    dialog.get_by_label("Name").fill("made_up_settings")
    dialog.get_by_label("Name").press("Enter")

    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_settings.json")
    expect(page.locator(".structure-doc")).to_be_visible()
    assert (folder / "structures" / "made_up_settings.json").read_text(encoding="utf-8") == "{}\n"

    # Markdown: a plain editor's tab with the file's name as its heading; the tab strip's "+" lists the same.
    page.click(".wb-tab-new")
    expect(page.locator(".context-menu [role=menuitem]").first).to_contain_text("Python script (.py)")
    for line in TYPES:
        expect(page.locator(f".context-menu [role=menuitem]:has-text('{line}')")).to_have_count(1)
    page.click(".context-menu [role=menuitem]:has-text('Markdown')")
    notes = page.locator(".dialog[aria-label='New Markdown']")
    notes.get_by_label("Name").fill("month end")
    notes.get_by_role("button", name="Create").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("month end.md")
    expect(page.locator(".wb-textfile .view-lines")).to_contain_text("# month end")
    expect(page.locator(".wb-run-file")).to_have_count(0)  # nothing runs
    assert (folder / "month end.md").read_text(encoding="utf-8") == "# month end\n"

    # Python: its typed main() under the main guard, in scripts/.
    pick(page, "Python script")
    script = page.locator(".dialog[aria-label='New Python script']")
    script.get_by_label("Name").fill("load_orders")
    script.get_by_role("button", name="Create").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("load_orders.py")
    expect(page.locator(".wb-doc-body:not([hidden]) .wb-script-editor .view-lines")).to_contain_text(
        "def main() -> None:"
    )
    compile((folder / "scripts" / "load_orders.py").read_text(encoding="utf-8"), "load_orders.py", "exec")

    # A notebook opens on the Notebooks page (two pages).
    pick(page, "Notebook")
    book = page.locator(".dialog[aria-label='New Notebook']")
    book.get_by_label("Name").fill("made_up_explore")
    book.get_by_role("button", name="Create").click()
    expect(page.locator(".wb-doc-title")).to_have_text("Notebooks")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_explore.ipynb")
    assert (folder / "made_up_explore.ipynb").is_file()
    page.close()


def test_with_no_project_open_a_script_and_a_sql_file_start_untitled(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    blocked = page.locator(".context-menu [role=menuitem]:has-text('JSON')")
    expect(blocked).to_be_disabled()
    expect(blocked).to_have_attribute("title", "Open a project first: a new file goes in its folder")
    page.click(".context-menu [role=menuitem]:has-text('Python script')")
    expect(page.locator(".dialog")).to_have_count(0)
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("Untitled script")
    pick(page, "SQL file")
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("Untitled SQL file")
    page.close()
