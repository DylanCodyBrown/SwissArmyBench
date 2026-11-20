# ruff: noqa: F811
"""The desktop app's browser keys and files, in the page (the owner, 2026-11-18: "Agreed"). The keys are the
app's only where the page is in the desktop app (`window.sabApp`, which the shell's script puts there: stood
in here); a file read by its path that changes on disk says so on its tab and its pane (Reload, steps kept;
Not now). tests/test_desktop_shell.py runs the real app. Made-up data only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Locator, Page, expect

from tests.e2e.test_ui import browser, call, frames, open_grid, server  # noqa: F401
from tests.e2e.test_workbench_page import seen_by_server

IN_APP = (
    "Object.defineProperty(window, 'sabApp', "
    "{ value: Object.freeze({ app: true, close: () => { window.__closed = true; } }) });"
)


def load(server: dict[str, Any], name: str, path: Path) -> str:
    grid: str = call(server, "POST", f"/datasets/{name}/load", {"path": str(path)})["grid"]
    return grid


def tab(page: Page, name: str) -> Any:
    return page.locator(f".tab-item[title='{name}']")


def front(page: Page) -> str:
    return str(page.locator(".tab-item.active").get_attribute("title"))


def test_the_browsers_keys_are_the_apps_only_in_the_app(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "made-up"
    folder.mkdir()
    for name in ("east_orders", "west_orders"):
        (folder / f"{name}.csv").write_text("order_id,amount\n1,10\n2,20\n3,30\n", encoding="utf-8")
    seen_by_server(server, folder)
    east = load(server, "east_orders", folder / "east_orders.csv")
    load(server, "west_orders", folder / "west_orders.csv")
    call(
        server,
        "POST",
        f"/grids/{east}/steps",
        {"steps": [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 15}}]},
    )
    base = f"http://127.0.0.1:{server['port']}"
    try:
        # In a browser the keys stay the browser's: Ctrl+Tab moves no tab here.
        page = open_grid(browser, f"{base}/g/{east}#token={server['token']}")
        expect(tab(page, "west_orders")).to_have_count(1, timeout=20000)
        page.keyboard.press("Control+Tab")
        frames(page)  # a key's handler has run and drawn by then
        assert front(page) == "east_orders"
        page.context.close()
        # In the app: Ctrl+Tab goes round, Ctrl+W closes the tab in front, Ctrl+Shift+T brings it back with
        # its step, Ctrl+T opens a new query tab; the palette shows the keys.
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        context.add_init_script(IN_APP)
        page = context.new_page()
        page.goto(f"{base}/g/{east}#token={server['token']}")
        expect(tab(page, "west_orders")).to_have_count(1, timeout=20000)
        expect(page.locator(".tab-item.active")).to_have_attribute("title", "east_orders")
        page.locator(".pane:not([hidden]) .ag-header-cell").first.wait_for(timeout=20000)
        page.keyboard.press("Control+Tab")
        expect(page.locator(".tab-item.active")).to_have_attribute("title", "west_orders")
        page.keyboard.press("Control+Shift+Tab")
        expect(page.locator(".tab-item.active")).to_have_attribute("title", "east_orders")
        page.keyboard.press("Control+w")
        expect(tab(page, "east_orders")).to_have_count(0)
        assert page.evaluate("window.__closed === undefined")  # a tab closed, not the window
        page.keyboard.press("Control+Shift+T")
        expect(tab(page, "east_orders")).to_have_count(1, timeout=15000)
        back = [g for g in call(server, "GET", "/grids")["grids"] if g["dataset"] == "east_orders"]
        assert len(back) == 1 and back[0]["steps"] == 1  # its step came back with it
        page.keyboard.press("Control+t")  # the New query page: its first choice has the keys, Enter opens it
        expect(page.locator(".new-query-page")).to_be_visible()
        expect(page.locator(".new-query-choice").first).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator(".tab-item.tab-draft.active")).to_have_count(1)
        page.keyboard.press("Control+w")  # the query draft closes
        expect(page.locator(".tab-item.tab-draft")).to_have_count(0)
        page.keyboard.press("Control+Shift+P")
        palette = page.locator(".wb-palette")
        palette.locator("input").fill("reopen")
        expect(
            palette.locator(".wb-palette-item", has_text="Reopen the last closed tab").locator("kbd")
        ).to_have_text("Ctrl+Shift+T")
        page.keyboard.press("Escape")
        # Every tab closed: Ctrl+W closes the window (the shell's close).
        tabs = page.locator(".tab-item")
        for _ in range(2):
            left = tabs.count() - 1
            page.keyboard.press("Control+w")
            expect(tabs).to_have_count(left)
        page.keyboard.press("Control+w")
        page.wait_for_function("window.__closed === true", timeout=10000)
        context.close()
    finally:
        for name in ("east_orders", "west_orders"):
            try:
                call(server, "DELETE", f"/datasets/{name}")
            except Exception:  # noqa: S110 (closed by the test already)
                pass


def changed_on_disk(bar: Locator, csv: Path, text: str) -> None:
    """Writes the file until the page says it changed. The server stamps a table's file at its first look
    after the load (every 3 s, services/file_watch.py): a write before that look is the stamp itself, so
    the same text is written again (a new modification time) after a look's time, instead of a fixed wait
    for the first look before writing."""
    for _ in range(4):
        csv.write_text(text, encoding="utf-8")
        try:
            expect(bar).to_contain_text("Changed on disk", timeout=3500)
            return
        except AssertionError:
            continue
    expect(bar).to_contain_text("Changed on disk")


def test_a_file_that_changed_on_disk_says_so_with_reload_and_not_now(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "made-up"
    folder.mkdir()
    csv = folder / "stock.csv"
    csv.write_text("sku,qty\nA-1,3\nB-2,5\n", encoding="utf-8")
    seen_by_server(server, folder)
    grid = load(server, "stock", csv)
    call(
        server,
        "POST",
        f"/grids/{grid}/steps",
        {"steps": [{"kind": "filter", "params": {"column": "qty", "op": "gt", "value": 4}}]},
    )
    try:
        page = open_grid(browser, f"http://127.0.0.1:{server['port']}/g/{grid}#token={server['token']}")
        bar = page.locator(".pane:not([hidden]) .file-changed")
        expect(tab(page, "stock")).to_have_count(1, timeout=20000)
        changed_on_disk(bar, csv, "sku,qty\nA-1,3\nB-2,5\nC-3,9\n")
        expect(tab(page, "stock").locator(".tab-changed")).to_have_count(1)
        assert call(server, "GET", f"/grids/{grid}/count")["row_count"] == 1  # never reloaded by itself
        bar.get_by_role("button", name="Reload").click()
        expect(bar).to_have_count(0, timeout=15000)
        expect(tab(page, "stock").locator(".tab-changed")).to_have_count(0)
        assert call(server, "GET", f"/grids/{grid}/count")["row_count"] == 2  # read again, its step kept
        changed_on_disk(bar, csv, "sku,qty\nA-1,3\n")
        bar.get_by_role("button", name="Not now").click()
        expect(bar).to_have_count(0, timeout=10000)
        assert call(server, "GET", f"/grids/{grid}/count")["row_count"] == 2  # kept as it was
        page.context.close()
    finally:
        call(server, "DELETE", "/datasets/stock")
