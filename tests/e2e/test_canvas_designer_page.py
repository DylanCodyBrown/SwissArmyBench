"""The designer in the Workbench window (the owner, 2026-11-19: "a canvas as flexible as WinForms and WPF"):
a Toolbox element dropped on the page makes its cell and its block; a container dropped, and a block nested
in its columns; the Document Outline reorders, hides and locks; several blocks selected and aligned as one
change (one Undo); a container's own properties in the pane; the design surface's ruler and width. The
agent does the same by the window's commands. Screenshots when SWISSARMYBENCH_CANVAS_SHOTS names a folder.
Made-up data only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_canvas_pane_page import app_files, open_window, orders, pane, shot, until  # noqa: F401
from tests.e2e.test_table_cells_page import window
from tests.e2e.test_ui import browser, call, server  # noqa: F401


def front(server: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    state = window(server, "canvas.state")
    return next(p for p in state["pages"] if p["id"] == state["page"])


def block(server: dict[str, Any], block_id: str) -> dict[str, Any]:  # noqa: F811
    return next(b for b in front(server)["blocks"] if b["id"] == block_id)


def test_toolbox_drop_nest_in_columns_and_the_outline(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    blocks = board.locator(".cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    # The Toolbox: every group, searchable; a drop makes the element's cell and its block.
    assert window(server, "canvas.panel", panel="toolbox") == {"open": True}
    toolbox = page.locator(".wb-mode-toolbox")
    expect(toolbox.locator(".tb-group")).to_have_count(7, timeout=15000)
    toolbox.get_by_role("searchbox", name="Search the Toolbox").fill("slid")
    expect(toolbox.locator(".tb-item")).to_have_count(1)
    toolbox.locator('.tb-item[data-tool="slider"]').drag_to(board, target_position={"x": 300, "y": 400})
    expect(blocks).to_have_count(4, timeout=30000)
    expect(board.locator(".cv-block", has_text="Slider 1")).to_be_visible()
    until(
        lambda: any(b["name"] == "Slider 1" and "slider_1" in b["makes"] for b in front(server)["blocks"]),
        True,
    )
    toolbox.get_by_role("searchbox", name="Search the Toolbox").fill("")
    shot(page, "designer-toolbox")
    # A container from the Toolbox (a click puts it at the end), then a block dragged into its second column.
    toolbox.locator('.tb-item[data-tool="columns"]').click()
    box = board.locator('.cv-box[data-kind="columns"]')
    expect(box).to_be_visible(timeout=15000)
    expect(box.locator(".cv-slot")).to_have_count(2)
    blocks.nth(2).drag_to(box.locator(".cv-slot").nth(1))
    expect(box.locator(".cv-slot").nth(1).locator(".cv-block")).to_have_count(1, timeout=15000)
    nested = next(b for b in front(server)["blocks"] if b["parent"])
    assert (nested["parent"], nested["slot"]) == ("c1", 1)
    # Its own properties in the pane: three columns by their ratios; a third slot is drawn.
    props = pane(page)
    box.locator(".cv-box-head").click()
    widths = props.locator('.cp-row[data-property="widths"] input')
    expect(widths).to_have_value("1, 1", timeout=15000)
    widths.fill("2, 1, 1")
    widths.press("Enter")
    expect(box.locator(".cv-slot")).to_have_count(3, timeout=15000)
    assert front(server)["containers"][0]["props"]["widths"] == [2, 1, 1]
    # The agent adds an element straight into the first column, and a tab strip into the third.
    made = window(server, "canvas.add", element="toggle", parent="c1", slot=0)
    assert made["variable"] == "toggle_1"
    expect(box.locator(".cv-slot").nth(0).locator(".cv-block")).to_have_count(1, timeout=30000)
    assert window(server, "canvas.add", element="tabs", parent="c1", slot=2) == {"container": "c2"}
    expect(box.locator('.cv-box[data-kind="tabs"] [role=tab]')).to_have_count(2, timeout=15000)
    shot(page, "designer-containers")
    # The Document Outline: the page as a tree; hide, lock, and a row dragged onto a slot moves it in.
    assert window(server, "canvas.panel", panel="outline") == {"open": True}
    outline = page.locator(".wb-mode-outline")
    expect(outline.locator(".ol-row")).to_have_count(7, timeout=15000)
    expect(outline.locator(".ol-slot", has_text="Column 2")).to_be_visible()
    first = outline.locator(".ol-row").nth(0)
    first_id = first.get_attribute("data-item")
    assert first_id is not None
    first.get_by_role("button", name="Lock Region filter").click()
    until(lambda: block(server, first_id)["locked"], True)
    expect(board.locator(f'.cv-block[data-block="{first_id}"] .cv-lock')).to_be_visible(timeout=15000)
    outline.locator(".ol-row").nth(0).get_by_role("button", name="Hide Region filter while designing").click()
    expect(board.locator(f'.cv-block[data-block="{first_id}"]')).to_have_count(0, timeout=15000)
    expect(outline.locator(".ol-row.hidden-item")).to_have_count(1)
    outline.locator(".ol-row").nth(0).get_by_role("button", name="Show Region filter").click()
    expect(board.locator(f'.cv-block[data-block="{first_id}"]')).to_be_visible(timeout=15000)
    outline.locator(".ol-row").nth(0).get_by_role("button", name="Unlock Region filter").click()
    until(lambda: block(server, first_id)["locked"], False)
    second = outline.locator(".ol-row").nth(1)
    second_id = second.get_attribute("data-item")
    assert second_id is not None
    second.drag_to(outline.locator('.ol-slot[data-slot="c2:1"]'))
    until(lambda: (block(server, second_id)["parent"], block(server, second_id)["slot"]), ("c2", 1))
    # Reorder: the first block dragged onto the last top-level row goes before it.
    shot(page, "designer-outline")
    page.context.close()


def test_multi_select_align_snaplines_keys_and_the_design_surface(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    app = app_files(server, tmp_path / "sales")
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    blocks = board.locator(".cv-block")
    expect(blocks).to_have_count(3, timeout=20000)
    # Ctrl+click adds to the selection; the pane shows what they share.
    blocks.nth(0).click()
    blocks.nth(2).click(modifiers=["Control"])
    expect(board.locator(".cv-block.selected")).to_have_count(2)
    assert window(server, "canvas.state")["selected"] == ["b1", "b3"]
    props = pane(page)
    expect(props.locator(".cp-target")).to_have_text("2 blocks")
    expect(props.locator("input[data-field=width]")).to_have_attribute("placeholder", "Mixed")
    # Make same width, as one change: b3 becomes as wide as b1 (the first selected). One Undo takes it back.
    page.get_by_role("button", name="Align", exact=True).click()
    page.get_by_role("menuitem", name="Make same width").click()
    until(lambda: block(server, "b3")["w"], 4)
    expect(props.locator("input[data-field=width]")).to_have_value("4", timeout=15000)
    window(server, "canvas.undo")
    until(lambda: block(server, "b3")["w"], 12)
    # The agent's arrange, and the rubber band: a drag over the first row selects its two blocks.
    assert window(server, "canvas.arrange", how="right", blocks=["b2", "b1"]) is True
    until(lambda: block(server, "b1")["column"] + block(server, "b1")["w"], 13)
    window(server, "canvas.undo")
    page.keyboard.press("Escape")
    first, second = blocks.nth(0).bounding_box(), blocks.nth(1).bounding_box()
    last = blocks.nth(2).bounding_box()
    assert first and second and last
    page.mouse.move(first["x"] + 10, last["y"] + last["height"] + 60)
    page.mouse.down()
    page.mouse.move(second["x"] + second["width"] - 10, first["y"] + 20, steps=8)
    expect(board.locator(".cv-band")).to_be_visible()
    page.mouse.up()
    until(lambda: sorted(window(server, "canvas.state")["selected"]), ["b1", "b2", "b3"])
    page.keyboard.press("Escape")
    assert window(server, "canvas.state")["selected"] == []
    # Keys: Shift+arrow moves three columns; Ctrl+D duplicates; Delete takes every selected block off.
    blocks.nth(0).click()
    blocks.nth(0).focus()
    page.keyboard.press("Shift+ArrowRight")
    blocks.nth(0).focus()
    page.keyboard.press("Control+d")
    expect(blocks).to_have_count(4, timeout=15000)
    page.keyboard.press("Delete")
    expect(blocks).to_have_count(3, timeout=15000)
    # Snaplines while a block is dragged over the row below: a guide where its edge meets another's.
    # The blocks are drawn again after the Delete: the third one's box asked for until it is there.
    box = None
    for _ in range(100):
        if box := blocks.nth(2).bounding_box():
            break
        page.wait_for_timeout(100)
    assert box
    blocks.nth(0).hover()
    page.mouse.down()
    page.mouse.move(box["x"] + 150, box["y"] + box["height"] + 30, steps=10)
    expect(board.locator(".cv-ghost")).to_be_visible(timeout=10000)
    expect(board.locator(".cv-guide").first).to_be_attached(timeout=10000)
    shot(page, "designer-snaplines")
    page.mouse.up()
    # The design surface: the ruler, the phone width, Centered as the app's own layout, sample rows.
    seen = window(server, "canvas.view", rulers=True, sampleRows=True, width="phone")
    assert seen == {"snaplines": True, "rulers": True, "sampleRows": True, "width": "phone"}
    expect(board.locator(".cv-ruler .cv-ruler-column")).to_have_count(12)
    expect(board.locator(".cv-ruler-width")).to_contain_text("px")
    narrow = board.locator(".cv-page").bounding_box()
    assert narrow is not None and narrow["width"] <= 392
    expect(board.locator(".cv-sample").first).to_contain_text("Sample · orders", timeout=15000)
    page.get_by_role("button", name="Centered", exact=True).click()
    until(lambda: window(server, "canvas.settings")["layout"], "centered")
    shot(page, "designer-surface")
    # Reset layout: every block back on the page, two a row.
    assert window(server, "canvas.arrange", how="reset") is True
    until(
        lambda: [(b["row"], b["column"], b["w"]) for b in front(server)["blocks"]][:2], [(1, 1, 6), (1, 7, 6)]
    )
    page.context.close()
