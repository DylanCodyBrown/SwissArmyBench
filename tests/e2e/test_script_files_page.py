"""The Scripts explorer's tree actions in a real browser (2026-11-21): Rename with its imports' preview,
Duplicate, Delete to the trash, New package. Made-up project files only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_scripts_ide_page import page_of, shop, tree_file  # noqa: F401
from tests.e2e.test_ui import browser, call, server  # noqa: F401


def test_rename_duplicate_delete_and_new_package_in_the_tree(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,  # noqa: F811
) -> None:
    (shop / "scripts" / "report.py").write_text(
        "from etl.load import Loader\nprint(Loader)\n", encoding="utf-8"
    )
    page = page_of(browser, server, "scripts")
    expect(tree_file(page, "scripts/etl/load.py")).to_be_visible(timeout=20000)
    tree_file(page, "scripts/etl/load.py").click()
    expect(page.locator(".wb-tab", has_text="load.py")).to_be_visible(timeout=20000)
    # Rename: the new name, its imports' preview, then the file moved and the import written.
    tree_file(page, "scripts/etl/load.py").click(button="right")
    page.get_by_role("menuitem", name="Rename…").click()
    dialog = page.get_by_role("dialog", name="Rename load.py")
    dialog.get_by_label("New name").fill("loader")
    expect(dialog.locator(".ide-change ins")).to_contain_text("from etl.loader import Loader", timeout=20000)
    dialog.get_by_role("button", name="Rename").click()
    expect(tree_file(page, "scripts/etl/loader.py")).to_be_visible(timeout=20000)
    assert not (shop / "scripts" / "etl" / "load.py").exists()
    assert (shop / "scripts" / "report.py").read_text(encoding="utf-8").startswith("from etl.loader import")
    expect(page.locator(".wb-tab", has_text="loader.py")).to_be_visible()  # its open tab followed it
    # Duplicate: a copy beside it, opened.
    tree_file(page, "scripts/report.py").click(button="right")
    page.get_by_role("menuitem", name="Duplicate").click()
    expect(tree_file(page, "scripts/report_copy.py")).to_be_visible(timeout=20000)
    # Delete: to the trash, on the user's word (answered here: this computer's own trash is never used by a
    # test; tests/test_script_files.py moves a file into a made-up one).
    asked: list[str] = []

    def answer(route: Any) -> None:
        asked.append(route.request.post_data or "")
        route.fulfill(json={"deleted": str(shop / "scripts" / "report_copy.py"), "to": "the Trash"})

    page.route("**/scripts/files/delete", answer)
    tree_file(page, "scripts/report_copy.py").focus()
    page.keyboard.press("Delete")
    page.get_by_role("dialog", name="Delete report_copy.py?").get_by_role(
        "button", name="Move to the trash"
    ).click()
    expect(page.get_by_role("dialog", name="Delete report_copy.py?")).to_have_count(0)
    assert asked and "report_copy.py" in asked[0]
    (shop / "scripts" / "report_copy.py").unlink()
    # New package: its folder and __init__.py.
    page.get_by_role("button", name="New package").click()
    page.get_by_role("dialog", name="New package").get_by_label("Package name").fill("pipeline")
    page.get_by_role("dialog", name="New package").get_by_role("button", name="Create").click()
    expect(tree_file(page, "scripts/pipeline/__init__.py")).to_be_visible(timeout=20000)
    page.context.close()


def test_go_to_definition_into_a_library_opens_it_read_only(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,  # noqa: F811
) -> None:
    (shop / "scripts" / "dump.py").write_text("import json\n\njson.dumps({'loaf': 1})\n", encoding="utf-8")
    page = page_of(browser, server, "scripts")
    tree_file(page, "scripts/dump.py").click()
    dump_tab = page.locator(".wb-tab", has_text="dump.py")
    expect(dump_tab).to_be_visible(timeout=20000)
    page.wait_for_timeout(500)  # the project's own documents come back meanwhile: this one to the front
    dump_tab.click()
    editor = page.locator(".wb-script-editor:visible .monaco-editor").first
    expect(editor).to_be_visible(timeout=20000)
    editor.locator(".view-lines").click()
    page.keyboard.press("Control+End")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("Home")
    for _ in range(7):
        page.keyboard.press("ArrowRight")  # inside dumps
    page.keyboard.press("F12")
    tab = page.locator(".wb-tab[data-kind='library']")
    expect(tab).to_be_visible(timeout=20000)
    body = page.locator(".wb-doc-body.kind-library:visible")
    expect(body.locator(".ide-readonly")).to_have_text("read-only")
    expect(body.locator(".monaco-editor")).to_contain_text("def dumps", timeout=20000)
    # Typing changes nothing: Monaco's read-only message instead.
    body.locator(".view-lines").click()
    page.keyboard.type("x")
    expect(body.locator(".monaco-editor")).not_to_contain_text("xdef")
    page.context.close()


def notebook(source: str) -> str:
    import json

    cell: dict[str, Any] = {
        "cell_type": "code",
        "metadata": {},
        "source": source,
        "outputs": [],
        "execution_count": None,
    }
    return json.dumps({"cells": [cell], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


def test_a_notebook_changed_elsewhere_reloads_in_place_unless_it_has_unsaved_edits(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    shop: Path,  # noqa: F811
) -> None:
    book = shop / "bakery.ipynb"
    book.write_text(notebook("loaves = 12"), encoding="utf-8")
    page = page_of(browser, server, "notebooks")
    page.locator(".wb-codex-file", has_text="bakery.ipynb").click()
    tab = page.locator(".wb-tab", has_text="bakery.ipynb")
    expect(tab).to_be_visible(timeout=20000)
    cells = page.locator(".wb-cell:visible")
    page.wait_for_timeout(500)  # the project's own documents come back meanwhile: this one to the front
    tab.click()
    expect(cells.first).to_contain_text("loaves = 12", timeout=20000)
    # Changed elsewhere with nothing unsaved here: the same tab follows, no question.
    book.write_text(notebook("loaves = 13"), encoding="utf-8")
    expect(cells.first).to_contain_text("loaves = 13", timeout=20000)
    expect(page.locator(".wb-elsewhere")).to_have_count(0)
    expect(page.locator(".wb-tab", has_text="bakery.ipynb")).to_have_count(1)
    # With an unsaved edit here: it asks.
    cells.first.locator(".view-lines").click()
    page.keyboard.press("End")
    page.keyboard.type("0")
    book.write_text(notebook("loaves = 14"), encoding="utf-8")
    expect(page.locator(".wb-elsewhere:visible")).to_contain_text("Changed elsewhere.", timeout=20000)
    expect(cells.first).to_contain_text("loaves = 130")
    page.context.close()
