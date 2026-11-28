"""New file on the Scripts page (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down
combo that asks what file type you wanna create. SQL python json etc. then scaffolds it for you"), in the
browser on a made-up project: the dropdown's types, SQL picked and named (an open .sql tab with its connection
line), JSON picked (a structure tab), a taken name said in the dialog, a notebook made on the Notebooks page,
the tab strip's "+" with the same choices, and with no project open the same dialog asking a folder of this
computer (tests/e2e/blazor/test_named_files.py: every entry point, a project type's own types)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page

TYPES = [
    "Python script (.py)",
    "SQL file (.sql)",
    "Power Query (.pq)",
    "Import Power BI queries… (.pq)",
    "JSON (.json)",
    "YAML (.yaml)",
    "TOML (.toml)",
    "XML (.xml)",
    "Markdown (.md)",
    "Plain text (.txt)",
    "HTML page (.html)",
    "Diagram (.mmd)",
    "README (.md)",
    "Decision record (.md)",
    "Data dictionary (.md)",
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

    # Markdown: read as a document, the file's name its heading; the tab strip's "+" lists the same.
    page.click(".wb-tab-new")
    expect(page.locator(".context-menu [role=menuitem]").first).to_contain_text("Python script (.py)")
    for line in TYPES:
        expect(page.locator(".context-menu [role=menuitem]").get_by_text(line, exact=True)).to_have_count(1)
    page.click(".context-menu [role=menuitem]:has-text('Markdown')")
    notes = page.locator(".dialog[aria-label='New Markdown']")
    notes.get_by_label("Name").fill("month end")
    notes.get_by_role("button", name="Create").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("month end.md")
    expect(page.locator(".wb-textfile .md-reader h1")).to_have_text("month end")  # it opens read
    page.click(".wb-view-source")
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


def test_with_no_project_open_the_dialog_asks_a_folder_and_the_file_is_written_there(
    browser: Browser, server: dict[str, Any]
) -> None:
    loose = server["tmp"] / "made up loose"
    loose.mkdir()
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    lines = page.locator(".context-menu [role=menuitem]")
    for at, line in enumerate(TYPES):  # every base type is made loose: none says Open a project first
        expect(lines.nth(at)).to_have_text(line)
        expect(lines.nth(at)).to_be_enabled()
    page.click(".context-menu [role=menuitem]:has-text('Python script')")
    dialog = page.locator(".dialog[aria-label='New Python script']")
    expect(dialog.locator(".new-file-loose")).to_contain_text("No project is open")
    folder = dialog.get_by_label("Folder", exact=True)
    expect(folder).to_have_value(str(server["tmp"] / "workbench"))  # where a loose file starts
    expect(page.locator(".wb-tab")).to_have_count(0)  # no untitled tab: nothing until it is named

    # Browse…: the app's file picker (no system dialog in a test) picks the folder.
    dialog.get_by_role("button", name="Browse…").click()
    choose_path(page, loose, folder=True)
    expect(folder).to_have_value(str(loose))
    dialog.get_by_label("Name").fill("made_up_tidy")
    expect(dialog.locator(".new-file-check")).to_have_text(f"Makes {loose / 'made_up_tidy.py'}")
    dialog.get_by_role("button", name="Create").click()
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text("made_up_tidy.py")
    expect(page.locator(".wb-script-editor .view-lines")).to_contain_text("def main() -> None:")
    compile((loose / "made_up_tidy.py").read_text(encoding="utf-8"), "made_up_tidy.py", "exec")

    # A folder that is not there is said; nothing is made.
    pick(page, "SQL file")
    sql = page.locator(".dialog[aria-label='New SQL file']")
    sql.get_by_label("Folder", exact=True).fill(str(loose / "nowhere"))
    expect(sql.locator(".new-file-check.error")).to_contain_text("There is no folder")
    sql.get_by_role("button", name="Cancel").click()
    assert sorted(p.name for p in loose.iterdir()) == ["made_up_tidy.py"]
    page.close()
