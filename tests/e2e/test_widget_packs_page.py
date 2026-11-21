"""The widget starter packs in the browser: the Canvas's Widgets pane and the Widgets window head each pack's
widgets with its name and description, in the packs' order and before the plain groups; a search by a pack's
words finds its widgets. Screenshots when SWISSARMYBENCH_WIDGET_SHOTS names a folder. Made-up data only."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from swissarmybench_streamlit.domain import widget_packs as packs
from tests.e2e.test_canvas_page import SHOTS, open_canvas, shot
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_widgets_page import open_widgets


def test_the_widgets_pane_and_window_show_the_starter_packs(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tmp_path: Path,
) -> None:
    project = tmp_path / "shop"
    project.mkdir()
    made = call(server, "POST", "/streamlit/canvases", {"name": "Packs", "folder": str(project)})
    page = open_canvas(browser, server, Path(made["path"]))
    gallery = page.locator(".cvs-gallery")
    headings = gallery.locator(".cvs-gallery-group")
    expect(headings.first).to_be_visible()
    texts = [t.strip() for t in headings.all_inner_texts()]
    shown = [t for t in texts if t.lower() in {p.lower() for p in packs.PACKS}]
    assert [s.lower() for s in shown] == [p.lower() for p in packs.PACKS], texts
    assert texts.index(shown[-1]) < next(i for i, t in enumerate(texts) if t.lower() == "buttons")
    sales = gallery.locator(".wg-pack", has=page.locator("[data-pack='Sales dashboard']"))
    expect(sales.locator(".wg-pack-desc")).to_have_text(packs.PACKS["Sales dashboard"])
    expect(gallery.locator(".cvs-card[data-widget='sales_kpi_row']")).to_be_visible()
    if SHOTS:  # the first pack's pictures, when Streamlit is here to draw them (a placeholder otherwise)
        with contextlib.suppress(Exception):
            picture = gallery.locator(".cvs-card[data-widget='sales_filter_bar'] img")
            expect(picture).to_be_visible(timeout=240000)
        shot(page, "canvas-widgets-pane-packs")
        gallery.locator(".cvs-gallery-search").fill("excel")
        page.wait_for_timeout(300)
        shot(page, "canvas-widgets-pane-excel-pack")
        gallery.locator(".cvs-gallery-search").fill("")
    gallery.locator(".cvs-gallery-search").fill("form builder")
    names = gallery.locator(".cvs-card").evaluate_all("cards => cards.map(c => c.dataset.widget)")
    assert sorted(names) == ["form_designer", "form_fill", "form_picker", "form_submissions"], names
    page.context.close()

    window = open_widgets(browser, server, "form_fill")
    groups = [t.strip() for t in window.locator(".wg-items .wg-group").all_inner_texts()]
    assert [g.lower() for g in groups if g.lower() in {p.lower() for p in packs.PACKS}] == [
        p.lower() for p in packs.PACKS
    ]
    expect(window.locator(".wg-items .wg-pack-desc").first).to_have_text(packs.PACKS["Sales dashboard"])
    expect(window.locator(".wg-item[data-widget='form_fill']")).to_have_class("wg-item selected")
    shot(window, "widgets-window-packs")
    window.context.close()
