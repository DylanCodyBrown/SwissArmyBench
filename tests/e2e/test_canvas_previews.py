"""The Canvas board's boxes are never empty (the owner, 2026-11-22: "The pre-built widgets are not rendering
on my machine"; the boxes were empty). The preview route is answered by the test, so each state is drawn
on purpose: a preview still being made shows the widget's name and "Preview is being made…" (the board's
asked first: first=1); one that failed shows its one line and Try again (asked again with retry=1); one
that needs Streamlit shows the one missing-package prompt once and an Install button in its box; the
gallery asks only for the cards in view. Pictures when SWISSARMYBENCH_WIDGET_SHOTS names a folder. Made-up
data."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, Page, Route, expect

from tests.e2e.test_ui import browser, call, server  # noqa: F401

SHOTS = os.environ.get("SWISSARMYBENCH_WIDGET_SHOTS")
MISSING = {
    "feature": "Streamlit widgets",
    "packages": ["streamlit"],
    "python": "/made/up/.venv/bin/python",
    "command": "uv pip install --python /made/up/.venv/bin/python streamlit",
}


def canvas_of(server: dict[str, Any], folder: Path) -> dict[str, Any]:  # noqa: F811
    made: dict[str, Any] = call(
        server, "POST", "/streamlit/canvases", {"name": "Boxes", "folder": str(folder)}
    )
    canvas = made["canvas"]
    send = f"/streamlit/canvases/{canvas}/command"
    call(server, "POST", send, {"kind": "add_container", "x": 0, "y": 0, "w": 1200, "h": 900})
    placed = [
        ("metric", 0, {"label": "Orders this month"}),
        ("data_table", 160, {}),
        ("callout_info", 480, {}),
    ]
    for widget, y, values in placed:
        call(
            server,
            "POST",
            send,
            {"kind": "insert_widget", "widget": widget, "parent": "c1", "x": 0, "y": y, "values": values},
        )
    return made


def test_a_box_whose_preview_is_not_there_is_never_empty(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    tmp_path: Path,
) -> None:
    folder = tmp_path / "boxes"
    folder.mkdir()
    made = canvas_of(server, folder)
    asked: list[str] = []
    fixed = {"data_table": False}

    def answer(route: Route) -> None:
        url = route.request.url
        name = url.split("/streamlit/widgets/", 1)[1].split("/preview", 1)[0]
        asked.append(url)
        body: dict[str, Any] = {"state": "coming", "key": f"{name}-k"}
        if name == "data_table":
            fixed["data_table"] |= "retry=1" in url
            if not fixed["data_table"]:
                body = {
                    "state": "failed",
                    "said": "data_table failed: KeyError: 'region'\nTraceback (most recent call last): ...",
                    "kind": "widget",
                    "retry_in": 600,
                }
        elif name == "callout_info":
            body = {
                "state": "failed",
                "said": "Previews need streamlit in the project's Python.",
                "kind": "setup",
                "retry_in": 600,
                "missing": MISSING,
                "install": "project",
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
    page: Page = context.new_page()
    try:
        page.route(re.compile(r".*/streamlit/widgets/[^/]+/preview\?.*"), answer)
        page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
        page.wait_for_load_state("networkidle")
        page.goto(
            f"http://127.0.0.1:{server['port']}/streamlit/canvas?path={quote(made['path'])}"
            f"#token={server['token']}"
        )
        board = page.locator(".cvs-board")
        expect(board).to_be_visible(timeout=30000)
        # Streamlit missing: the one prompt, once, however many boxes need it.
        prompt = page.locator("dialog.missing-packages")
        expect(prompt).to_be_visible(timeout=15000)
        expect(prompt).to_contain_text("Streamlit widgets will not work without streamlit.")
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / "board-missing-prompt.png"))
        prompt.locator("button", has_text="Not now").click()
        expect(prompt).to_have_count(0)
        # Being made: the widget's name and the words, never an empty box; the instance's own label over it.
        metric = board.locator(".cvs-widget[data-widget='metric']")
        expect(metric.locator(".cvs-ph-name")).to_have_text("metric")
        expect(metric.locator(".cvs-ph-line")).to_have_text("Preview is being made…")
        expect(metric.locator(".cvs-instance-text")).to_have_text("Orders this month")
        # Failed: its one line, and Try again.
        table = board.locator(".cvs-widget[data-widget='data_table']")
        expect(table.locator(".cvs-ph.failed .cvs-ph-line")).to_have_text(
            "data_table failed: KeyError: 'region'"
        )
        assert "Traceback" in (table.locator(".cvs-ph").get_attribute("title") or "")
        # Needs Streamlit: said in its box, with the install a click away.
        callout = board.locator(".cvs-widget[data-widget='callout_info']")
        expect(callout.locator(".cvs-ph-line")).to_have_text("Needs streamlit to draw.")
        expect(callout.locator("button", has_text="Install streamlit")).to_be_visible()
        for box in (metric, table, callout):  # every box shows something
            assert (box.inner_text() or "").strip()
        # The board's own were asked first (first=1); the gallery only for the cards in view.
        assert any("/metric/preview" in u and "first=1" in u for u in asked)
        listed = len(call(server, "GET", "/streamlit/widgets")["widgets"])
        names = {u.split("/streamlit/widgets/", 1)[1].split("/preview", 1)[0] for u in asked}
        assert 3 < len(names) < listed, (len(names), listed)
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / "board-placeholders-light.png"))
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.wait_for_timeout(500)
            page.screenshot(path=str(Path(SHOTS) / "board-placeholders-dark.png"))
            page.evaluate("document.documentElement.dataset.theme = 'light'")
        # Try again: asked with retry=1, and the box is being made again.
        table.locator("button", has_text="Try again").click()
        expect(table.locator(".cvs-ph-line")).to_have_text("Preview is being made…")
        assert any("/data_table/preview" in u and "retry=1" in u for u in asked)
        # Not now holds for the page: no second prompt.
        page.wait_for_timeout(500)
        expect(prompt).to_have_count(0)
    finally:
        context.close()
