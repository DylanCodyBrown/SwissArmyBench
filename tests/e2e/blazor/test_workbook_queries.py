"""Workbook queries in the browser (the owner, 2026-11-28: "Excel's own Power Query"), on a made-up workbook:
New file's Edit workbook queries… opens its queries as one linked file ("Saves into <workbook>"), a query is
edited and saved, and the workbook's Section1.m on disk has the new M with every other part as it was; Run
file previews the queries as tables from the workbook's own named table; a workbook open in Excel is
refused; a workbook with no Power Query stops a save and adds it only on Add Power Query to this workbook."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl
from playwright.sync_api import Browser, Page, expect

from tests import workbook_queries_data as data
from tests.e2e.blazor.conftest import name_new_file, open_page


def folder_of(server: dict[str, Any], name: str) -> Path:
    folder = Path(server["tmp"]) / "workbench" / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def open_linked(
    browser: Browser, server: dict[str, Any], folder: Path, name: str, queries: bool = True
) -> tuple[Page, Path]:
    workbook = (data.workbook if queries else data.plain_workbook)(folder / "Made Up Sales.xlsx")
    page = open_page(browser, server, "scripts")
    page.click(".wb-top-new")
    page.click(".context-menu [role=menuitem]:has-text('Edit workbook queries')")
    dialog = page.locator(".dialog.new-file")
    dialog.get_by_label("From the file").fill(str(workbook))
    name_new_file(page, name, folder)
    expect(page.locator(".wb-tab.active .tab-label")).to_have_text(f"{name}.pq")
    expect(page.locator(".wb-pq-saves-into")).to_have_text("Saves into Made Up Sales.xlsx")
    return page, workbook


def retype_number(page: Page, old: str, new: str, nth: int = 0) -> None:
    """One edit in the editor, as a person makes it: a number double-clicked and typed over."""
    page.locator(".wb-pq .view-line span", has_text=re.compile(f"^{old}$")).nth(nth).dblclick()
    page.keyboard.type(new)


def test_a_workbooks_query_is_edited_and_saved_back_into_the_workbook(
    browser: Browser, server: dict[str, Any]
) -> None:
    folder = folder_of(server, "saved")
    page, workbook = open_linked(browser, server, folder, "made_up_report")
    before = data.parts_of(workbook)
    lines = page.locator(".wb-pq .view-lines")
    expect(lines).to_contain_text("// workbook: Made Up Sales.xlsx")
    expect(lines).to_contain_text("section Section1;")
    expect(page.locator(".wb-pq-workbook")).to_contain_text("3 workbook queries")

    retype_number(page, "100", "150")
    # Preview save: what would change, nothing written.
    page.click(".wb-pq-preview-save")
    expect(page.locator(".wb-console-head strong")).to_have_text("Save preview")
    expect(page.locator(".wb-pq-change.changed strong")).to_have_text("Sales")
    assert data.section_of(workbook) == data.SECTION

    page.click(".wb-pq .monaco-editor .view-lines")
    page.keyboard.press("Control+S")
    expect(page.locator(".wb-console-head strong")).to_have_text("Saved into the workbook", timeout=30_000)
    expect(page.locator(".sql-status")).to_contain_text("Saved into Made Up Sales.xlsx: 1 changed.")
    expect(page.locator(".wb-pq-backup")).to_contain_text("Made Up Sales.backup.xlsx")
    expect(page.locator(".wb-tab.active .wb-tab-dirty")).to_have_text("")
    # On disk: the workbook's Section1.m has the new M, in Excel's own line ends; nothing else changed.
    section = data.section_of(workbook)
    assert "Table.SelectRows(Source, each [Amount] > 150)" in section and "[Amount] > 100" not in section
    assert "\r\n" in section and "\n" not in section.replace("\r\n", "")
    after = data.parts_of(workbook)
    assert {n for n in after if after[n] != before[n]} == {"customXml/item1.xml"} and list(after) == list(
        before
    )
    assert openpyxl.load_workbook(workbook)["Data"]["A2"].value == "North"
    assert (folder / "Made Up Sales.backup.xlsx").is_file()
    assert "[Amount] > 150" in (folder / "made_up_report.pq").read_text(encoding="utf-8")
    page.close()


def test_run_file_previews_the_workbooks_queries_as_tables(browser: Browser, server: dict[str, Any]) -> None:
    folder = folder_of(server, "run")
    page, workbook = open_linked(browser, server, folder, "made_up_preview")
    page.click(".wb-gcontrols button:has-text('Run file')")
    expect(page).to_have_url(re.compile(r"/blazor/tables\?grid="), timeout=60_000)
    tabs = page.locator(".grid-tab.tab-item")
    expect(tabs.filter(has_text="Sales")).not_to_have_count(0)
    expect(page.locator(".grid-tab.tab-item.current")).to_contain_text("By_Region")
    assert data.section_of(workbook) == data.SECTION  # a run writes nothing into the workbook
    page.close()


def test_a_workbook_open_in_excel_is_not_written(browser: Browser, server: dict[str, Any]) -> None:
    folder = folder_of(server, "locked")
    page, workbook = open_linked(browser, server, folder, "made_up_locked")
    (folder / "~$Made Up Sales.xlsx").write_bytes(b"\x05Maria")
    before = workbook.read_bytes()
    retype_number(page, "100", "250", 1)
    page.keyboard.press("Control+S")
    error = page.locator(".wb-sql-error")
    expect(error).to_contain_text(
        "Made Up Sales.xlsx is open in Excel. Close it in Excel first.", timeout=30_000
    )
    expect(page.locator(".wb-pq-workbook.blocked")).to_contain_text("Open in Excel")
    assert workbook.read_bytes() == before
    page.close()


def test_power_query_is_added_to_a_workbook_only_on_the_users_click(
    browser: Browser, server: dict[str, Any]
) -> None:
    """The owner, 2026-11-28: "Yea optional". A save into a workbook with no Power Query stops and offers;
    the click adds it (one custom XML part, its properties), says so, and the sheets are as they were."""
    folder = folder_of(server, "added")
    page, workbook = open_linked(browser, server, folder, "made_up_first", queries=False)
    before = data.parts_of(workbook)
    line = page.locator(".wb-pq-workbook")
    expect(line).to_contain_text("Made Up Sales.xlsx has no Power Query yet.")
    expect(line.locator(".wb-pq-add-power-query")).to_have_text("Add Power Query to this workbook")

    # A save: the file is saved, the workbook is not touched, and the offer is beside the reason.
    page.click(".wb-pq .monaco-editor .view-lines")
    page.keyboard.press("Control+End")
    page.keyboard.type("// a made-up note")
    page.keyboard.press("Control+S")
    error = page.locator(".wb-sql-error")
    expect(error).to_contain_text("has no Power Query yet. Add Power Query to this workbook", timeout=30_000)
    assert data.parts_of(workbook) == before and not (folder / "Made Up Sales.backup.xlsx").exists()

    error.locator(".wb-pq-add-power-query").click()
    expect(page.locator(".wb-console-head strong")).to_have_text(
        "Power Query added to the workbook", timeout=30_000
    )
    said = page.locator(".wb-pq-added-power-query")
    expect(said).to_contain_text("Added Power Query to Made Up Sales.xlsx: 1 query, connection only")
    expect(said).to_contain_text("customXml/item1.xml and its properties part")
    expect(page.locator(".wb-pq-change.added strong")).to_have_text("Query1")
    expect(page.locator(".wb-pq-backup")).to_contain_text("Made Up Sales.backup.xlsx")
    expect(page.locator(".wb-pq-workbook")).to_contain_text("1 workbook query")
    expect(page.locator(".wb-pq-add-power-query")).to_have_count(0)
    after = data.parts_of(workbook)
    assert set(after) - set(before) == {
        "customXml/item1.xml",
        "customXml/itemProps1.xml",
        "customXml/_rels/item1.xml.rels",
    }
    assert {n for n in before if after[n] != before[n]} == {
        "xl/_rels/workbook.xml.rels",
        "[Content_Types].xml",
    }
    assert data.section_of(workbook).startswith("section Section1;\r\n\r\nshared Query1 = let")
    book = openpyxl.load_workbook(workbook)
    assert book.sheetnames == ["Data"] and book["Data"]["A2"].value == "North"
    page.close()
