"""The six graphical upgrades (the owner, 2026-11-27: "Fix it all") on made-up data: Home's four figure tiles
and its shortened path; the ERD's shared header and empty state; a connection card's short amber badge with
the whole sentence on hover; the Canvas landing's cards (Open, Play, Export); the Project Explorer's card;
Settings in one column with its section list; and the Canvas's bottom bar on one line at 1,360 px."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, expect

from tests.e2e.blazor.conftest import call, choose_path, open_page
from tests.e2e.blazor.test_connections_parity import saved_shop


def made_up_project(server: dict[str, Any], name: str, kind: str = "streamlit") -> Path:
    """A made-up project with the sample store's tables, one more notebook and one script."""
    made = call(server, "POST", "/project/new", {"name": name, "type": kind})
    folder = Path(made["project"]["path"])
    call(server, "POST", "/samples/store", {})
    (folder / "analysis.ipynb").write_text(
        '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}\n', encoding="utf-8"
    )
    (folder / "load.py").write_text("print('made up')\n", encoding="utf-8")
    return folder


def test_homes_figure_tiles_and_short_path(browser: Browser, server: dict[str, Any]) -> None:
    folder = made_up_project(server, "made_up_figures")
    summary = call(server, "GET", "/project/summary")
    page = open_page(browser, server)
    tiles = page.locator(".summary-figures .summary-figure")
    expect(tiles).to_have_count(4)

    # Each tile's number is the summary's own count; the tables' tile adds up the rows in memory.
    rows = sum(t["rows"] or 0 for t in summary["tables"])
    tables = page.locator("[data-figure=tables]")
    expect(tables.locator("strong")).to_have_text(str(len(summary["tables"])))
    expect(tables).to_contain_text(f"{rows:,} rows in memory")
    notebooks = [d["name"] for d in summary["documents"] if d["kind"] == "notebook"]
    scripts = [d["name"] for d in summary["documents"] if d["kind"] == "script"]
    assert "analysis.ipynb" in notebooks and "load.py" in scripts
    expect(page.locator("[data-figure=notebooks] strong")).to_have_text(str(len(notebooks)))
    expect(page.locator("[data-figure=notebooks]")).to_contain_text(notebooks[0])
    expect(page.locator("[data-figure=scripts] strong")).to_have_text(str(len(scripts)))
    expect(page.locator("[data-figure=connections] strong")).to_have_text(str(len(summary["connections"])))
    # The four sit on one line at this width, above the sections.
    tops = tiles.evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().top))")
    assert len(set(tops)) == 1
    assert tops[0] < page.locator("[data-section=tables]").bounding_box()["y"]  # type: ignore[index]

    # The path is its end; the whole of it is the hover's.
    path = page.locator("[data-fact=folder] code")
    expect(path).to_have_text(f"…/{folder.parent.name}/{folder.name}")
    expect(path).to_have_attribute("title", str(folder))

    # A tile is a link, reached by the keyboard, to where its things live.
    tables.focus()
    assert tables.evaluate("e => getComputedStyle(e).outlineStyle") != "none"
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"/blazor/tables$"))
    page.close()


def test_the_erd_has_the_shared_header_and_empty_state(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "POST", "/samples/store", {})
    opened = len(call(server, "GET", "/grids")["grids"])
    page = open_page(browser, server, "erd")
    head = page.locator(".erd-page .area-page-head")
    expect(head.locator(".area-page-title")).to_have_text("ERD")
    expect(head.get_by_role("button", name="Manage relationships")).to_be_visible()
    expect(head).to_contain_text("Import relationships")
    empty = page.locator(".erd-page .empty-state")
    expect(empty.locator("strong")).to_have_text("No relationships yet")
    expect(empty).to_contain_text(f"looks through the {opened} open tables")
    expect(empty.get_by_role("button", name="Find relationships")).to_be_visible()
    # Centred in the page, as every other page's empty state.
    box, body = empty.bounding_box(), page.locator(".erd-page .area-page-body").bounding_box()
    assert box and body
    assert abs((box["x"] + box["width"] / 2) - (body["x"] + body["width"] / 2)) < 24
    page.close()


def test_a_connection_cards_badge_says_the_whole_sentence_on_hover(
    browser: Browser, server: dict[str, Any]
) -> None:
    name = saved_shop(server)
    card = next(c for c in call(server, "GET", "/connections/usage")["connections"] if c["name"] == name)
    whole = "\n".join(note["words"] for note in card["local"])
    assert whole.startswith("Only works on your machine: ")
    page = open_page(browser, server, "connections")
    badge = page.locator(f".connection-card[data-name={name}] .local-only-badge")
    # In view: the short words only. On hover and for a screen reader: the whole sentence.
    expect(badge.locator("[aria-hidden=true]").last).to_have_text("Only works on your machine")
    expect(badge).to_have_attribute("title", whole)
    expect(badge.locator(".sr-only")).to_have_text(whole.replace("\n", " "))
    assert badge.evaluate("e => e.getBoundingClientRect().height") < 30  # one short line, never a paragraph
    link = page.locator(f".connection-card[data-name={name}]")
    assert link.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    page.close()


def test_the_canvas_landings_cards_open_and_export(browser: Browser, server: dict[str, Any]) -> None:
    folder = made_up_project(server, "made_up_cards")
    listed = call(server, "GET", "/streamlit/canvases")["canvases"][0]
    page = open_page(browser, server, "canvas")
    expect(page.locator(".canvas-landing .area-page-title")).to_have_text("Canvas")
    expect(
        page.locator(".canvas-landing .area-page-actions").get_by_role("button", name="New canvas")
    ).to_be_visible()
    card = page.locator(".canvas-card")
    expect(card).to_have_count(1)
    expect(card.locator("[data-fact=pages]")).to_have_text("1 page")
    expect(card.locator("[data-fact=layouts]")).to_have_text("Desktop and Phone layouts")
    expect(card.locator("[data-fact=launched]")).to_have_text("Not launched yet")
    expect(card.locator(".canvas-card-picture")).to_contain_text("Empty page")
    actions = card.locator(".card-actions a")
    expect(actions).to_have_text(["Open", "Play", "Export"])
    opens = f"canvas?path={quote(listed['path'], safe='')}"
    expect(actions.nth(1)).to_have_attribute("href", f"{opens}&do=play")

    # Export: the canvas opens and its own Export… asks where, then writes the app; the address forgets it.
    card.get_by_role("link", name=f"Export {listed['name']}").click()
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    out = folder / "made_up_export"
    out.mkdir()
    choose_path(page, out, folder=True)
    expect(page.locator(".note-corner")).to_contain_text("Exported:")
    assert (out / "app.py").is_file()
    assert "do=" not in page.url

    # Open: the same canvas, nothing run.
    page.go_back()
    expect(page.locator(".canvas-card")).to_be_visible()
    page.locator(".canvas-card").get_by_role("link", name=f"Open {listed['name']}").click()
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    expect(page.locator(".dialog.file-chooser")).to_have_count(0)
    page.close()


def test_the_project_explorers_card(browser: Browser, server: dict[str, Any]) -> None:
    folder = made_up_project(server, "made_up_card_shop")
    page = open_page(browser, server, "?view=projects")
    card = page.locator(".explorer-card", has_text="made_up_card_shop")
    expect(card.locator("[data-fact=type]")).to_have_text("Streamlit app")
    expect(card.locator("[data-fact=where]")).to_have_text("Local")
    expect(card.locator("[data-fact=opened]")).to_have_text(
        re.compile(r"^Opened (just now|\d+ minutes? ago)$")
    )
    counts = card.locator(".explorer-count")
    expect(counts.filter(has_text="notebook")).to_have_text("2 notebooks")
    expect(counts.locator("svg").first).to_be_visible()
    shown = card.locator(".explorer-folder span")
    expect(shown).to_have_text("…/" + "/".join(folder.parts[-4:]))
    expect(card.locator(".explorer-folder")).to_have_attribute("title", str(folder))
    # The open project's stripe is the accent's.
    accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
    probe = "e => { const s = getComputedStyle(e); return [s.borderLeftWidth, s.borderLeftColor]; }"
    width, colour = card.evaluate(probe)
    expected = page.evaluate(
        "c => { const e = document.createElement('i'); e.style.color = c; document.body.append(e);"
        " const v = getComputedStyle(e).color; e.remove(); return v; }",
        accent,
    )
    assert (width, colour) == ("4px", expected)
    expect(card.get_by_role("button", name="Show in folder")).to_be_visible()
    page.close()


def test_settings_section_list_jumps_and_marks_the_section_in_view(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "settings")
    page.set_viewport_size({"width": 1360, "height": 620})
    nav = page.locator(".settings-nav")
    expect(nav.locator(".settings-nav-item").first).to_have_text("Theme")
    expect(nav.locator(".settings-nav-item").nth(1)).to_have_text("Team")
    expect(nav.locator("[aria-current=true]")).to_have_text("Theme")
    # One column: every box under the one before it, the Team box first after Theme.
    boxes = page.locator(".settings-sections .fieldset")
    lefts = boxes.evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().left))")
    assert len(set(lefts)) == 1 and len(lefts) >= 6
    assert "team-fieldset" in (boxes.nth(1).get_attribute("class") or "")

    # A click jumps: the box comes into view and its line is marked.
    nav.get_by_role("button", name="Beta").click()
    expect(page.locator(".beta-fieldset")).to_be_in_viewport()
    expect(nav.locator("[aria-current=true]")).to_have_text("Beta")
    expect(nav).to_be_in_viewport()  # the list stays where it is as the page scrolls

    # Scrolled by hand, the mark follows the box in view.
    page.locator(".area-page-body").evaluate("e => e.scrollTo({ top: 0 })")
    page.locator(".area-page-body").dispatch_event("wheel")
    expect(nav.locator("[aria-current=true]")).to_have_text("Theme")

    # By the keyboard: Enter on a line jumps and the focus goes on from that box.
    nav.get_by_role("button", name="Claude").focus()
    page.keyboard.press("Enter")
    expect(nav.locator("[aria-current=true]")).to_have_text("Claude")
    expect(page.locator(".claude-fieldset")).to_be_focused()
    page.close()


def test_the_canvas_bottom_bar_stays_on_one_line_with_both_panes(
    browser: Browser, server: dict[str, Any]
) -> None:
    made_up_project(server, "made_up_bar")
    path = call(server, "GET", "/streamlit/canvases")["canvases"][0]["path"]
    page = open_page(browser, server, f"canvas?path={quote(path)}")  # 1,360 px wide
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    bottom = page.locator(".cvs-bottom")
    for pane in ("widgets", "properties"):
        expect(bottom.locator(f"button[data-pane={pane}]")).to_have_attribute("aria-pressed", "true")
    one_line = (
        "e => { const tops = [...e.children].filter(c => c.offsetWidth > 0)"
        ".map(c => { const r = c.getBoundingClientRect(); return Math.round(r.top + r.height / 2); });"
        " return Math.max(...tops) - Math.min(...tops) <= 6; }"
    )
    for width in (1360, 1200, 1000):
        page.set_viewport_size({"width": width, "height": 860})
        assert bottom.evaluate(one_line), f"the bar wraps at {width} px"
        assert bottom.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), f"the bar is cut off at {width} px"
        expect(bottom.locator(".cvs-fit")).to_be_in_viewport()
    # What does not fit is in More sizing ("…"), still reachable.
    bottom.get_by_role("button", name="More sizing").click()
    expect(page.locator(".cvs-sizing-menu")).to_contain_text("Columns")
    page.close()
