"""The Blazor APIs and Structures pages on made-up data: a made-up orders service's API
(tests/api_standins.py) as a card, its operations explored, Try it (the answer opened as a structure
right there: its tree, a node's path, Open as grid); a structure made from pasted text, its tree and
text views, an edit applied, Close."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.api_standins import Service
from tests.e2e.blazor.conftest import call, open_page


@pytest.fixture(scope="module")
def orders_service() -> Iterator[Service]:
    running = Service().start()
    yield running
    running.stop()


def test_an_api_explored_and_tried(browser: Browser, server: dict[str, Any], orders_service: Service) -> None:
    call(
        server, "POST", "/apis", {"spec_url": orders_service.url + "/openapi.json", "auth": {"type": "none"}}
    )
    page = open_page(browser, server, "apis")
    card = page.locator(".api-card[data-name=Orders]")
    expect(card).to_contain_text("5 operations")
    card.click()
    expect(page.locator(".api-operations")).to_contain_text("/orders/{order_id}")
    expect(page.locator(".api-operation h2")).to_contain_text("/orders")
    expect(page.locator(".api-schema").first).to_contain_text("order_id")

    page.click(".api-operation button:has-text('Send')")
    expect(page.locator(".api-operation [role=status]")).to_contain_text("200")
    tree = page.locator(".structure-tree")
    expect(tree).to_contain_text("items")
    tree.locator(".tree-row", has_text="items").first.click()
    expect(page.locator(".structure-path code")).to_have_text("$.items")
    page.click(".structure-path button:has-text('Open as grid')")
    expect(page.locator(".grid-title")).to_contain_text("items")
    page.close()


def test_a_pasted_structure_its_tree_and_its_text(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "structures")
    page.click("button:has-text('Paste…')")
    page.fill(".dialog input", '{"region": "North", "orders": [{"id": 1, "total": 2.5}]}')
    page.click(".dialog-foot .btn.primary")
    view = page.locator(".structure-view")
    expect(view.locator(".structure-tree")).to_contain_text("region")
    expect(view.locator(".structure-tree")).to_contain_text('"North"')
    view.locator(".tree-row.leaf", has_text="total").click()
    expect(view.locator(".structure-path code")).to_have_text("$.orders[0].total")

    view.locator("button:has-text('Text')").click()
    editor = view.locator(".structure-text .monaco-editor")
    expect(editor).to_contain_text("North")
    # The word North selected (a double click) and South typed over it.
    editor.locator(".view-line span", has_text="North").last.dblclick()
    page.keyboard.type("South")
    page.wait_for_timeout(400)
    view.locator("button:has-text('Apply')").click()
    view = page.locator(".structure-view")
    view.locator("button:has-text('Tree')").click()
    expect(view.locator(".structure-tree")).to_contain_text('"South"')

    listed = call(server, "GET", "/structures")["open"]
    assert any(s["format"] == "json" for s in listed)
    expect(page.locator(".structures-list")).to_contain_text("Pasted")
    page.click(".area-page-actions button:has-text('Close')")
    expect(page.locator(".structures-list")).not_to_contain_text("Pasted")
    page.close()
