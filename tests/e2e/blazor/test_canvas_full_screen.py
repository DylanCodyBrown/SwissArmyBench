"""The Canvas full screen in the browser (Pages/Canvas/CanvasPage.Full.cs; the owner, 2026-11-26): F11 hides
the rail, the status bar, the top and bottom bars and the panes, the board fills the window with the strip in
its corner (never under the Collaboration buddy); a widget dropped from the strip's Widgets overlay and
dragged on the board; Escape comes back; left in full screen it opens in it again; the agent's
canvas_full_screen. Made-up project only."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, FloatRect, Page, expect

from tests.e2e.blazor.conftest import call
from tests.e2e.blazor.test_canvas import draw_container, made_up_canvas, open_canvas, saved_nodes


def overlaps(a: FloatRect, b: FloatRect) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def full(page: Page) -> bool:
    return bool(page.evaluate("() => document.body.classList.contains('cvs-full')"))


def test_f11_leaves_the_board_alone_and_escape_brings_everything_back(
    browser: Browser, server: dict[str, Any]
) -> None:
    path = made_up_canvas(server, "Full")
    page = open_canvas(browser, server, path)
    draw_container(page, 60, 60, 420, 260)
    expect(page.locator(".cvs-container")).to_have_count(1)
    expect(page.locator(".cvs-top .cvs-full-toggle")).to_have_attribute("title", "Full screen (F11)")

    page.locator(".cvs-board").click(position={"x": 900, "y": 600})
    page.keyboard.press("F11")
    strip = page.get_by_role("toolbar", name="Full screen")
    expect(strip).to_be_visible()
    assert full(page)
    for gone in (".nav-rail", ".status-bar", ".cvs-top", ".cvs-bottom", ".cvs-pane"):
        expect(page.locator(gone)).to_be_hidden()
    stage = page.locator(".cvs-stage").bounding_box()
    assert stage and stage["x"] <= 1 and stage["y"] <= 1
    assert stage["width"] >= 1600 - 2 and stage["height"] >= 900 - 2
    buddy = page.locator(".collab-buddy").bounding_box()
    held = strip.bounding_box()
    assert buddy and held and not overlaps(buddy, held)

    # The strip's Widgets: a pane over the board, below the buddy; a card dropped on the board goes in.
    strip.locator("[data-pane=widgets]").click()
    overlay = page.locator("aside.cvs-full-overlay[data-pane=widgets]")
    expect(overlay).to_be_visible()
    shown = overlay.bounding_box()
    assert shown and not overlaps(buddy, shown)
    overlay.locator(".cvs-gallery-search").fill("status badge")
    overlay.locator(".cvs-card[data-widget=status_badge]").drag_to(
        page.locator(".cvs-board"), target_position={"x": 700, "y": 420}
    )
    badge = page.locator(".cvs-widget[data-widget=status_badge]")
    expect(badge).to_have_count(1)
    expect(page.locator(".error-note")).to_have_count(0)
    strip.locator("[data-pane=widgets]").click()
    expect(overlay).to_have_count(0)

    # A container dragged on the board in full screen: it moves and the file says so.
    def places() -> list[Any]:
        return [n.get("at") for n in saved_nodes(path)]

    before = places()
    boxes = [c.bounding_box() for c in page.locator(".cvs-container").all()]
    box = min((b for b in boxes if b), key=lambda b: b["y"])  # the one drawn first, at the top left
    page.mouse.move(box["x"] + 120, box["y"] + 120)
    page.mouse.down()
    page.mouse.move(box["x"] + 105, box["y"] + 105, steps=3)
    page.mouse.move(box["x"] + 90, box["y"] + 90, steps=3)
    page.mouse.up()
    for _ in range(50):
        if places() != before:
            break
        page.wait_for_timeout(100)
    assert places() != before
    # Undo from the strip puts it back.
    strip.get_by_role("button", name="Undo").click()
    expect(strip.get_by_role("button", name="Redo")).to_be_enabled()

    page.keyboard.press("Escape")
    expect(page.locator(".cvs-top")).to_be_visible()
    expect(page.locator(".nav-rail")).to_be_visible()
    expect(page.locator(".cvs-bottom")).to_be_visible()
    expect(strip).to_have_count(0)
    assert not full(page)
    page.reload()
    expect(page.locator(".cvs-board")).to_be_visible(timeout=30_000)
    page.wait_for_timeout(500)
    expect(page.locator(".cvs-top")).to_be_visible()
    page.close()


def test_left_in_full_screen_it_opens_in_it_and_the_agent_toggles_it(
    browser: Browser, server: dict[str, Any]
) -> None:
    path = made_up_canvas(server, "Kept")
    page = open_canvas(browser, server, path)
    page.locator(".cvs-top .cvs-full-toggle").click()
    expect(page.get_by_role("toolbar", name="Full screen")).to_be_visible()
    page.reload()
    expect(page.get_by_role("toolbar", name="Full screen")).to_be_visible(timeout=30_000)
    expect(page.locator(".nav-rail")).to_be_hidden()

    canvas = call(server, "POST", "/streamlit/canvases", {"path": path})["canvas"]
    call(server, "POST", f"/streamlit/canvases/{canvas}/full-screen", {"on": False})
    expect(page.locator(".cvs-top")).to_be_visible()
    call(server, "POST", f"/streamlit/canvases/{canvas}/full-screen", {})
    expect(page.get_by_role("toolbar", name="Full screen")).to_be_visible()
    page.get_by_role("button", name="Leave full screen").click()
    expect(page.locator(".cvs-top")).to_be_visible()
    page.close()
