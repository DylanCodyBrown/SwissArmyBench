# ruff: noqa: F811
"""The one loading state where it matters (web/src/loading.ts; design principles 8.12), in a real browser with
made-up data: the Connections page's tree while it loads, a connection form's Test, and the Key Finder while
it compares. Each request is held at the browser's door until the test lets it go, so the cover is seen and
the gated part is shown to refuse clicks; then the answer arrives and the gate lifts. Pictures go to
SAB_LOADING_SHOTS when it is set (light and dark, device scale 2)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, Page, Route, expect

from swissarmybench.client import push_client
from tests.e2e.test_connection_sql_page import shop
from tests.e2e.test_ui import browser, call, grid_of, open_grid, orders_url, server  # noqa: F401

SHOTS = os.environ.get("SAB_LOADING_SHOTS")


def shot(page: Page, name: str, target: Any = None) -> None:
    if not SHOTS:
        return
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        page.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
        page.wait_for_timeout(100)
        (target or page).screenshot(path=str(Path(SHOTS) / f"{name}-{theme}.png"))
    page.evaluate("document.documentElement.dataset.theme = 'light'")


class Held:
    """Requests to one address held until let go (`method`: only those)."""

    def __init__(self, method: str | None = None) -> None:
        self.method = method
        self.routes: list[Route] = []
        self.seen = 0

    def __call__(self, route: Route) -> None:
        if self.method and route.request.method != self.method:
            route.continue_()
            return
        self.seen += 1
        self.routes.append(route)

    def release(self) -> None:
        for route in self.routes:
            route.continue_()
        self.routes.clear()


def connections_page(browser: Browser, orders_url: str) -> tuple[Page, Any]:
    page = open_grid(browser, orders_url, device_scale_factor=2, width=1500, height=900)
    page.locator(".nav-rail [data-area='connections']").click()
    return page, page.locator(".area-page[data-page='connections']")


def ensure_shop(server: dict[str, Any], tmp_path_factory: Any) -> None:
    """The made-up Shop connection (once per module's server)."""
    if not any(c["name"] == "Shop" for c in call(server, "GET", "/connections")["connections"]):
        shop(server, tmp_path_factory.mktemp("shop"))


def test_the_tree_is_gated_while_it_loads(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path_factory: Any
) -> None:
    ensure_shop(server, tmp_path_factory)
    page, dialog = connections_page(browser, orders_url)
    held = Held()
    page.route("**/connections/Shop/tree", held)
    # The detail itself first: an empty page that is filling in holds its place with the words.
    usage = Held()
    page.route("**/connections/Shop/usage", usage)
    dialog.locator(".connection-card[data-connection='Shop']").click()
    placeholder = dialog.locator(".area-page-body > .loading-block")
    expect(placeholder).to_contain_text("Loading Shop…")
    expect(placeholder).to_have_attribute("data-shown", "")
    box = placeholder.bounding_box()
    assert box and box["height"] >= 119
    shot(page, "placeholder-in-an-empty-pane", dialog)
    usage.release()
    page.unroute("**/connections/Shop/usage")
    tables = dialog.locator(".connection-tables")
    expect(tables).to_have_attribute("aria-busy", "true", timeout=15000)
    cover = dialog.locator(".busy-cover")
    expect(cover).to_be_visible()
    expect(cover).to_contain_text("Loading Shop's tables…")
    # Exactly the tree: the cover sits over the section's box, the rest of the page stays usable.
    box, over = tables.bounding_box(), cover.bounding_box()
    assert box and over and abs(box["y"] - over["y"]) < 2 and abs(box["height"] - over["height"]) < 2
    assert page.evaluate("document.querySelector('.connection-tables').inert") is True
    search = tables.get_by_role("searchbox", name="Search tables")
    middle = search.bounding_box()
    assert middle
    page.mouse.click(middle["x"] + middle["width"] / 2, middle["y"] + middle["height"] / 2)
    assert page.evaluate("document.activeElement?.classList.contains('conn-tree-search')") is False
    expect(dialog.locator(".connection-used")).not_to_have_attribute("aria-busy", "true")
    shot(page, "cover-on-a-card", dialog.locator(".connection-detail-main"))
    held.release()
    expect(tables.locator(".conn-tree-table")).to_have_count(3, timeout=30000)
    expect(cover).to_have_count(0)
    expect(tables).not_to_have_attribute("aria-busy", "true")
    search.fill("reg")
    expect(tables.locator(".conn-tree-table")).to_have_count(1)
    page.close()


def test_a_connection_test_gates_its_form_and_runs_once(
    browser: Browser, orders_url: str, server: dict[str, Any], tmp_path_factory: Any
) -> None:
    ensure_shop(server, tmp_path_factory)
    page, dialog = connections_page(browser, orders_url)
    dialog.locator(".connection-card[data-connection='Shop']").click()
    dialog.get_by_role("button", name="Edit").click()
    form = dialog.locator(".area-page-body")
    expect(form.get_by_role("heading", name="Edit Shop")).to_be_visible(timeout=15000)
    held = Held("POST")
    page.route("**/connections/test", held)
    test = dialog.get_by_role("button", name="Test connection")
    test.click()
    expect(test).to_be_disabled()
    expect(test).to_have_text("Testing…")
    expect(test.locator(".busy-spinner")).to_have_count(1)
    cover = dialog.locator(".busy-cover")
    expect(cover).to_contain_text("Connecting to Shop…")
    # The form is what is gated: nothing typed into it while it tests.
    expect(form).to_have_attribute("aria-busy", "true")
    assert (
        page.evaluate("document.querySelector('.area-page[data-page=connections] .area-page-body').inert")
        is True
    )
    shot(page, "busy-button", dialog.locator(".area-page-foot"))
    # A second click (or Enter) starts nothing.
    test.dispatch_event("click")
    assert held.seen == 1
    held.release()
    expect(dialog.locator(".status-ok")).to_contain_text("It works", timeout=30000)
    expect(test).to_be_enabled()
    expect(test).to_have_text("Test connection")
    expect(cover).to_have_count(0)
    assert held.seen == 1
    expect(form).not_to_have_attribute("aria-busy", "true")
    page.close()


def test_the_key_finder_is_gated_while_it_compares(browser: Browser, server: dict[str, Any]) -> None:
    customers = pd.DataFrame(
        {"customer_id": range(1, 201), "segment": [("Retail", "Trade")[i % 2] for i in range(200)]}
    )
    orders = pd.DataFrame({"order_id": range(1, 601), "cust": [(i % 180) + 1 for i in range(600)]})
    right = push_client.push(customers, name="kl_customers", new_grid=True)
    left = push_client.push(orders, name="kl_orders", new_grid=True)
    page = open_grid(browser, left, device_scale_factor=2)
    held = Held("POST")
    page.context.route("**/key-finder", held)
    with page.expect_popup() as popup:
        page.locator(".ribbon .ribbon-group").first.get_by_role("button", name="Key Finder").click()
    finder = popup.value
    panel = finder.locator(".keys-window")
    cover = finder.locator(".busy-cover")
    expect(cover).to_contain_text("Comparing with", timeout=20000)
    find = panel.get_by_role("button", name="Find keys")
    assert finder.evaluate("document.querySelector('.keys-window').inert") is True
    find.click(force=True)  # lands on the cover: no second search
    assert held.seen == 1
    shot(finder, "cover-on-the-key-finder", panel)
    held.release()
    expect(panel.locator(".kf-row").first).to_contain_text("cust", timeout=20000)
    expect(cover).to_have_count(0)
    assert finder.evaluate("document.querySelector('.keys-window').inert") is False
    finder.close()
    page.close()
    for url in (left, right):
        call(server, "DELETE", f"/grids/{grid_of(url)}")
