"""The Collaboration panel in the browser (Layout/Collaboration): the buddy icon in every window's top right
corner (never over a page's own buttons) and Ctrl+Shift+M show and hide the panel, floating over the page
without moving it; a note posted with an `@cell` reference, its link clicked through to the cell; the `@` list
with this page's objects first; a reply, a reaction from the full emoji grid and a resolve; a second author's
files showing up live; a project opened with another author's notes: the count and the one-line news with
Open; Collaborate on a table's tab; your name in Settings. Made-up people and data only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import call, open_page, unnamed_controls


def _project(server: dict[str, Any], name: str) -> Path:
    folder = Path(server["tmp"]) / "projects" / name
    call(server, "POST", "/project/new", {"path": str(folder)})
    call(server, "PUT", "/collaboration/profile", {"name": "Avery Lin"})
    cells = [
        {
            "cell_type": "code",
            "metadata": {"swissarmybench": {"number": n}},
            "source": [f"monthly_total_{n} = {n * 100}\n"],
            "outputs": [],
            "execution_count": None,
        }
        for n in (1, 2)
    ]
    notebook = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (folder / "returns.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    return folder


def _panel(page: Page) -> Any:
    return page.locator(".collab-panel")


def _write_note(page: Page, text: str) -> None:
    box = _panel(page).locator(".collab-composer textarea")
    box.click()
    box.press_sequentially(text)


def test_shown_and_hidden_on_two_pages_over_the_page(browser: Browser, server: dict[str, Any]) -> None:
    _project(server, "Panel shown")
    page = open_page(browser, server, "tables")
    main = page.locator(".page-main")
    before = main.bounding_box()
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page)).to_be_visible()
    expect(_panel(page).locator(".collab-title")).to_have_text("Collaboration")
    assert main.bounding_box() == before  # it floats: the page keeps its place and size
    assert _panel(page).evaluate("e => getComputedStyle(e).position") == "fixed"
    assert [c for c in unnamed_controls(page) if "collab" in c] == []  # every control of the panel is named
    _panel(page).get_by_role("button", name="Hide the Collaboration panel").click()
    expect(_panel(page)).to_have_count(0)

    page.goto(page.url.replace("/blazor/tables", "/blazor/notebooks"))
    page.wait_for_selector(".nav-rail")
    button = page.locator(".collab-buddy")
    corner = button.bounding_box()
    assert corner is not None and corner["y"] < 20 and corner["x"] > 1360 - 60  # the top right corner
    button.click()
    expect(_panel(page)).to_be_visible()
    expect(button).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page)).to_have_count(0)
    page.close()


def test_a_note_with_a_cell_reference_reply_react_resolve(browser: Browser, server: dict[str, Any]) -> None:
    folder = _project(server, "Panel notes")
    page = open_page(browser, server, "tables")
    page.keyboard.press("Control+Shift+M")
    panel = _panel(page)
    expect(panel.locator(".collab-empty-words")).to_be_visible()
    _write_note(page, "Please check @cell")
    popup = panel.locator(".collab-popup")
    expect(popup.get_by_role("option", name=re.compile("returns.ipynb cell 2"))).to_be_visible()
    popup.get_by_role("option", name=re.compile("returns.ipynb cell 2")).click()
    panel.locator(".collab-composer textarea").press_sequentially("totals **twice**")
    panel.locator(".collab-composer textarea").press("Enter")
    thread = panel.locator(".collab-item.thread")
    expect(thread).to_have_count(1)
    expect(thread.locator("strong", has_text="twice")).to_be_visible()
    files = list((folder / ".sab" / "collaboration").glob("t-*/*.md"))
    assert len(files) == 1 and "sab:cell/returns.ipynb#2" in files[0].read_text(encoding="utf-8")

    # A reply, a reaction and a resolve, each in the thread.
    thread.locator(".collab-replies").click()
    expect(panel.locator(".collab-thread")).to_be_visible()
    panel.locator(".collab-composer textarea").press_sequentially("Fixed it in the second cell.")
    panel.locator(".collab-composer textarea").press("Enter")
    expect(panel.locator(".collab-thread .collab-message")).to_have_count(2)
    first = panel.locator(".collab-thread .collab-message").first
    first.get_by_role("button", name="Add a reaction").click()
    first.get_by_role("menuitem", name="React 👍").click()
    expect(first.locator(".collab-reaction.mine")).to_contain_text("1")
    # More… opens every emoji, by group and by name.
    first.get_by_role("button", name="Add a reaction").click()
    first.get_by_role("menuitem", name="More emoji").click()
    first.get_by_label("Search emoji by name").fill("party popper")
    first.get_by_role("option", name="party popper").click()
    expect(first.locator(".collab-reaction.mine", has_text="🎉")).to_be_visible()
    panel.get_by_role("button", name="Resolve").click()
    expect(panel.locator(".collab-resolved-line")).to_contain_text("Resolved by avery-lin")
    assert list((folder / ".sab" / "collaboration").glob("t-*/_events/*.toml"))

    # The reference opens the notebook at its cell.
    first.locator("a.collab-ref").click()
    expect(page).to_have_url(re.compile(r"/blazor/notebooks\?path=.*returns\.ipynb&cell=2"))
    expect(page.locator('.wb-cell[data-number="2"]')).to_be_visible(timeout=30_000)
    page.close()


def test_a_second_authors_files_show_up_live(browser: Browser, server: dict[str, Any]) -> None:
    folder = _project(server, "Panel live")
    page = open_page(browser, server, "tables")
    page.keyboard.press("Control+Shift+M")
    expect(_panel(page).locator(".collab-empty-words")).to_be_visible()
    # Sam's computer wrote these (as a Pull brings them): a thread and its first message.
    thread = folder / ".sab" / "collaboration" / "t-5a7e0001"
    thread.mkdir(parents=True)
    (thread / "thread.toml").write_text(
        'id = "t-5a7e0001"\ntitle = "Returns look high"\nchannel = "general"\n'
        'created = "2026-11-25T09:00:00.000000Z"\npinned = false\n\n'
        '[created_by]\nname = "Sam Ortiz"\nlogin = "sam-ortiz"\n',
        encoding="utf-8",
    )
    (thread / "20261125T090000.000000Z-sam-ortiz-5a7e0002.md").write_text(
        '+++\nid = "5a7e0002"\nthread = "t-5a7e0001"\nkind = "note"\ntime = "2026-11-25T09:00:00.000000Z"\n'
        'edited = ""\ndeleted = false\nmentions = ["avery-lin"]\n\n[author]\nname = "Sam Ortiz"\n'
        'login = "sam-ortiz"\n+++\n\n@avery-lin returns look high this month.\n',
        encoding="utf-8",
    )
    item = _panel(page).locator(".collab-item.thread", has_text="Sam Ortiz")
    expect(item).to_be_visible(timeout=20_000)
    expect(item).to_contain_text("returns look high")
    expect(page.locator(".collab-buddy .collab-badge")).to_have_text("1")
    page.close()


def _sams_note(folder: Path, ident: str, words: str) -> None:
    """A note as Sam's computer wrote it (a Pull brings these files)."""
    thread = folder / ".sab" / "collaboration" / f"t-{ident}"
    thread.mkdir(parents=True)
    (thread / "thread.toml").write_text(
        f'id = "t-{ident}"\ntitle = "{words}"\nchannel = "general"\n'
        'created = "2026-11-25T09:00:00.000000Z"\npinned = false\n\n'
        '[created_by]\nname = "Sam Ortiz"\nlogin = "sam-ortiz"\n',
        encoding="utf-8",
    )
    (thread / f"20261125T090000.000000Z-sam-ortiz-{ident}.md").write_text(
        f'+++\nid = "{ident}"\nthread = "t-{ident}"\nkind = "note"\ntime = "2026-11-25T09:00:00.000000Z"\n'
        'edited = ""\ndeleted = false\nmentions = []\n\n[author]\nname = "Sam Ortiz"\n'
        f'login = "sam-ortiz"\n+++\n\n{words}\n',
        encoding="utf-8",
    )


def test_opening_a_project_says_its_new_messages(browser: Browser, server: dict[str, Any]) -> None:
    folder = _project(server, "Panel news")
    call(server, "POST", "/project/close", {"discard": True})
    _sams_note(folder, "5a7e0011", "Returns look high")
    _sams_note(folder, "5a7e0012", "Month end is Friday")
    page = open_page(browser, server, "tables")
    call(server, "POST", "/project/open", {"path": str(folder)})
    expect(page.locator(".collab-buddy .collab-badge")).to_have_text("2")
    news = page.locator(".note-corner .toast", has_text="2 new messages")
    expect(news).to_be_visible()  # this computer's first look: a count alone
    news.get_by_role("button", name="Open").click()
    expect(_panel(page).locator(".collab-thread")).to_be_visible()
    expect(_panel(page).locator(".collab-title")).to_have_text(
        re.compile("Returns look high|Month end is Friday")
    )
    page.close()


def test_the_at_list_offers_this_pages_objects_first(browser: Browser, server: dict[str, Any]) -> None:
    _project(server, "Panel at")
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "tables")
    expect(page.locator(".grid-tab.tab-item").first).to_be_visible()
    page.keyboard.press("Control+Shift+M")
    _write_note(page, "@")
    popup = _panel(page).locator(".collab-popup")
    expect(popup.locator(".collab-pick-section").first).to_have_text("On this page")
    first = popup.get_by_role("option").first
    expect(first).to_contain_text("customers")  # the table in front, then its columns
    expect(popup.locator(".collab-pick-section")).to_have_text(["On this page", "People", "In the project"])
    page.close()


@pytest.mark.parametrize(
    "address",
    [
        "",
        "connections",
        "apis",
        "environment",
        "tables",
        "scripts",
        "notebooks",
        "analyze",
        "extensions",
        "widgets",
    ],
)
def test_the_buddy_never_covers_a_pages_own_buttons(
    browser: Browser, server: dict[str, Any], address: str
) -> None:
    page = open_page(browser, server, address)
    expect(page.locator(".collab-buddy")).to_be_visible()
    expect(page.locator(".pop-out-corner")).to_be_visible()
    page.wait_for_timeout(500)
    assert page.evaluate(UNDER_THE_BUDDY) == [], address
    page.close()


# The controls found at the corner's edges with the corner's own buttons out of the way (the buddy, and the
# Pop out button beside it: the owner, 2026-11-27): none on any page.
UNDER_THE_BUDDY = """() => {
  const own = [...document.querySelectorAll('.collab-buddy, .pop-out-corner')];
  const boxes = own.map((b) => b.getBoundingClientRect());
  const r = { left: Math.min(...boxes.map((b) => b.left)), right: Math.max(...boxes.map((b) => b.right)),
    top: Math.min(...boxes.map((b) => b.top)), bottom: Math.max(...boxes.map((b) => b.bottom)) };
  own.forEach((b) => { b.style.visibility = 'hidden'; });
  const middle = (r.top + r.bottom) / 2;
  const points = [[r.left - 2, middle], [(r.left + r.right) / 2, middle], [r.left + 8, middle],
    [r.right - 8, middle], [r.right + 2, middle], [r.left + 8, r.bottom + 3], [r.right - 8, r.bottom + 3]];
  const found = points.map(([x, y]) => document.elementFromPoint(x, y))
    .map((el) => el && el.closest('button, a[href], input, select, textarea, [role=tab]'))
    .filter(Boolean).map((el) => el.outerHTML.slice(0, 80));
  own.forEach((b) => { b.style.visibility = ''; });
  return found;
}"""


def test_collaborate_on_a_tables_tab(browser: Browser, server: dict[str, Any]) -> None:
    _project(server, "Panel tab")
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "tables")
    tab = page.locator(".grid-tab.tab-item").first
    expect(tab).to_be_visible()
    tab.click(button="right")
    page.locator(".menu-item", has_text="Collaborate").click()
    panel = _panel(page)
    expect(panel).to_be_visible()
    expect(panel.locator(".collab-composer textarea")).to_have_attribute(
        "placeholder", re.compile("A note on ")
    )
    page.close()


def test_your_name_is_set_once_in_settings(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "settings")
    box = page.get_by_label("Your name on the notes")
    box.fill("Avery Lin (finance)")
    box.press("Tab")
    expect(page.locator(".collab-name-fieldset")).to_contain_text("as set here")
    assert call(server, "GET", "/collaboration/profile")["name"] == "Avery Lin (finance)"
    box.fill("")
    box.press("Tab")
    expect(page.locator(".collab-name-fieldset")).not_to_contain_text("as set here")
    page.close()
