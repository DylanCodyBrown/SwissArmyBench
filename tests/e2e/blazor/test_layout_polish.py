"""Layout the pages keep, on made-up data: a project's card holds its long folder, the Analyze board's empty
sentence reads on one line, an empty state is centred as a whole, the Scripts page's Files rows keep their
mark and action apart, and in a narrow window (1,000 px) the Widgets window's bar and the status bar keep to
one line."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, Page, expect

from .conftest import FIRST_LOAD_MS, call, open_page

# Two boxes overlap when each starts before the other ends, both ways.
OVERLAP = """([a, b]) => {
  const x = document.querySelector(a).getBoundingClientRect();
  const y = document.querySelector(b).getBoundingClientRect();
  return x.left < y.right - 1 && y.left < x.right - 1 && x.top < y.bottom - 1 && y.top < x.bottom - 1;
}"""


def narrow_page(browser: Browser, info: dict[str, Any], path: str) -> Page:
    page = browser.new_page(viewport={"width": 1000, "height": 700})
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{info['port']}/blazor/{path}#token={info['token']}")
    page.wait_for_selector(".nav-rail", timeout=FIRST_LOAD_MS)
    return page


def test_a_projects_card_holds_its_long_folder(browser: Browser, server: dict[str, Any]) -> None:
    name = "a_made_up_project_with_a_long_name_for_its_folder"
    call(server, "POST", "/project/new", {"name": name})
    page = open_page(browser, server, "?view=projects")
    card = page.locator(".explorer-card", has_text=name)
    expect(card).to_be_visible()
    spills = card.evaluate(
        """(card) => { const edge = card.getBoundingClientRect().right;
           return [...card.querySelectorAll('*')].filter((e) => e.getBoundingClientRect().right > edge + 1)
             .map((e) => e.className || e.tagName); }"""
    )
    assert spills == []
    page.close()


def test_the_empty_boards_sentence_reads_on_one_line(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "analyze")
    sentence = page.locator(".analyze-board > p", has_text="The board is empty")
    expect(sentence).to_be_visible()
    box = sentence.bounding_box()
    assert box is not None and box["height"] < 30  # one line (it broke a word a line in one of 12 columns)
    page.close()


def test_an_empty_state_is_centred_as_a_whole(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "session")
    empty = page.locator(".empty-state")
    expect(empty).to_be_visible()
    words, button = empty.locator("p").first.bounding_box(), empty.locator(".btn").first.bounding_box()
    assert words is not None and button is not None
    middle = words["x"] + words["width"] / 2
    assert abs(button["x"] + button["width"] / 2 - middle) < 4  # the button sat at the left of centred words
    page.close()


def test_a_generated_files_row_keeps_its_mark_and_action_apart(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/project/new", {"name": "made_up_rows"})
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "scripts")
    row = page.locator(".wb-codex-file-row", has=page.locator(".wb-codex-action")).first
    expect(row).to_be_visible()
    row.scroll_into_view_if_needed()
    row.evaluate("(row) => row.setAttribute('data-test-row', '1')")
    assert not page.evaluate(OVERLAP, ["[data-test-row] .chip", "[data-test-row] .wb-codex-action"])
    chip = row.locator(".chip").bounding_box()
    assert chip is not None and chip["height"] < 24  # "read-only" on one line
    page.close()


def test_a_narrow_widgets_bar_keeps_its_words_off_its_buttons(browser: Browser, server: dict[str, Any]) -> None:
    page = narrow_page(browser, server, "widgets")
    page.locator(".wg-item, [data-widget]").first.wait_for()
    expect(page.locator(".wg-saved")).to_contain_text("Prebuilt")
    assert not page.evaluate(OVERLAP, [".wg-saved", ".wg-copy"])
    saved = page.locator(".wg-saved").bounding_box()
    assert saved is not None and saved["height"] < 24
    page.close()


def test_a_narrow_status_bar_keeps_to_one_line(browser: Browser, server: dict[str, Any]) -> None:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    page = narrow_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".status-rows")).to_be_visible()
    tall = page.evaluate(
        """() => [...document.querySelectorAll('.status-bar > *')]
             .filter((e) => e.getBoundingClientRect().height > 26).map((e) => e.className)"""
    )
    assert tall == []
    page.close()
