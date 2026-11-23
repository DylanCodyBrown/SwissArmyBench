"""The Blazor APIs and Structures pages on made-up data: a made-up orders service's API
(tests/api_standins.py) as a card, its operations explored, Try it (the answer opened as a structure
right there: its tree, a node's path, Open as grid); a structure made from pasted text, its tree and
text views, an edit applied, Close."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, expect

from tests.api_standins import API_KEY, Service
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
    card.locator(".api-card-open").click()
    expect(page.locator(".api-operations")).to_contain_text("/orders/{order_id}")
    expect(page.locator(".api-operation h2")).to_contain_text("/orders")
    expect(page.locator(".api-schema").first).to_contain_text("order_id")

    page.click(".api-operation button:has-text('Send')")
    expect(page.locator(".api-operation [role=status]")).to_contain_text("200")
    tree = page.locator(".structure-tree")
    expect(tree).to_contain_text("items")
    # Author a call: Return as table, its rows path, Save as web call; its DuckDB SQL name to copy.
    page.locator(".api-operation input[aria-label='Return as table']").check()
    expect(page.locator(".api-conversion summary")).to_have_text("The DuckDB query")
    page.locator(".api-operation input[aria-label='Records path']").fill("$.items")
    page.locator(".api-operation button:has-text('Save as web call')").click()
    expect(page.locator(".note-corner")).to_contain_text("is a table")
    expect(page.locator(".api-operation button:has-text('Copy name for SQL')")).to_be_visible()
    page.locator(".api-conversion summary").click()
    page.locator(".api-conversion button:has-text('Make it again')").click()
    expect(page.locator(".note-corner")).to_contain_text("The query is made again from the settings.")
    tree.locator(".tree-row", has_text="items").first.click()
    expect(page.locator(".structure-path code")).to_have_text("$.items")
    page.click(".structure-path button:has-text('Open as grid')")
    expect(page.locator(".grid-title")).to_contain_text("items")
    page.close()


def test_a_pasted_structure_its_tree_and_its_text(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "structures")
    page.click(".area-page-actions button:has-text('Paste')")
    dialog = page.locator(".dialog[aria-label=Paste]")
    dialog.locator("textarea[aria-label=Text]").fill(
        '{"region": "North", "orders": [{"id": 1, "total": 2.5}]}'
    )
    dialog.locator("button:has-text('Open')").click()
    tree = page.locator(".structure-tree")
    expect(tree).to_contain_text("region")
    expect(tree).to_contain_text('"North"')
    tree.locator(".structure-row[data-path='$.orders'] .structure-caret").click()
    tree.locator(".structure-row[data-path='$.orders']").click()
    expect(page.locator(".structures-path")).to_have_text("$.orders")

    page.click(".segmented button:has-text('Text')")
    editor = page.locator(".structure-text .monaco-editor")
    expect(editor).to_contain_text("North")
    # The word North selected (a double click) and South typed over it: sent once typing pauses.
    editor.locator(".view-line span", has_text="North").last.dblclick()
    page.keyboard.type("South")
    page.wait_for_timeout(1200)
    page.click(".segmented button:has-text('Tree')")
    expect(page.locator(".structure-tree")).to_contain_text('"South"')

    listed = call(server, "GET", "/structures")["open"]
    assert any(s["format"] == "json" for s in listed)
    tab = page.locator(".structures-tab", has_text="Pasted")
    expect(tab).to_be_visible()
    tab.locator(".structures-tab-close").click()
    if page.locator(".dialog").count():
        page.locator(".dialog-foot button.primary, .dialog-foot button.danger").first.click()
    expect(page.locator(".structures-tab", has_text="Pasted")).to_have_count(0)
    page.close()


def test_the_api_cards_actions_and_the_local_api(
    browser: Browser, server: dict[str, Any], orders_service: Service
) -> None:
    """A card's Refresh (has not changed), Rename and Delete asked first; Search every API; the Local
    sandbox APIs: New local sandbox API… makes API.py, Properties, More's Will this work for real?."""
    if not any(a["name"] == "Orders" for a in call(server, "GET", "/apis")["apis"]):
        call(
            server,
            "POST",
            "/apis",
            {"spec_url": orders_service.url + "/openapi.json", "auth": {"type": "none"}},
        )
    page = open_page(browser, server, "apis")
    card = page.locator(".api-card[data-name=Orders]")
    card.locator("button:has-text('Refresh')").click()
    expect(page.locator(".note-corner")).to_contain_text("Orders has not changed.")
    card.locator("button:has-text('Rename')").click()
    expect(page.locator(".dialog[aria-label='Rename Orders'] input[aria-label='New name']")).to_have_value(
        "Orders"
    )
    page.locator(".dialog[aria-label='Rename Orders'] button:has-text('Cancel')").click()
    card.locator("button:has-text('Delete')").click()
    expect(page.locator(".dialog[aria-label='Delete Orders?']")).to_contain_text(
        "Its API blade, its web call blades and its folder go."
    )
    page.locator(".dialog[aria-label='Delete Orders?'] button:has-text('Cancel')").click()
    page.fill("input[aria-label='Search every API']", "order")
    expect(page.locator(".api-results")).to_contain_text("/orders")
    page.fill("input[aria-label='Search every API']", "")
    call(server, "POST", "/project/new", {"name": "Made up api"})
    page.reload()
    page.wait_for_selector(".nav-rail", timeout=60_000)
    local = page.locator(".local-apis")
    # New project makes API.py; a project without one offers New local sandbox API….
    expect(local.locator(".local-api-bar, button:has-text('New local sandbox API…')").first).to_be_visible()
    if local.locator("button:has-text('New local sandbox API…')").count():
        local.locator("button:has-text('New local sandbox API…')").click()
        page.locator(".dialog[aria-label='New local sandbox API'] button:has-text('Make API.py')").click()
    expect(local.locator(".local-api-bar")).to_contain_text("Not running")
    local.locator("button[aria-label=Properties]").click()
    expect(local.locator("input[aria-label='Its base path']")).to_be_visible()
    local.locator("button[aria-label=More]").click()
    page.locator(".context-menu [role=menuitem]", has_text="Will this work for real?").click()
    expect(page.locator(".dialog[aria-label='Will this work for real?']")).to_contain_text(
        "No endpoint sends SQL to check."
    )
    call(server, "POST", "/project/close", {})
    page.close()


def test_add_api_from_a_document_and_from_the_form(
    browser: Browser, server: dict[str, Any], orders_service: Service
) -> None:
    """Add API: the document's address read (the preview: the file, each operation as its method, a
    table's Try it), a name typed, Add (its explorer follows); the form's endpoint cards (Needed from the
    path, Try it's reason)."""
    page = open_page(browser, server, "apis")
    page.locator(".apis-add").click()
    expect(page.locator("h1.area-page-title")).to_contain_text("Add API")
    page.locator("[role=radio]", has_text="I have an OpenAPI document").click()
    page.locator('input[aria-label="OpenAPI document\'s address"]').fill(orders_service.url + "/openapi.json")
    page.locator(".add-api-part button:has-text('Read')").click()
    operations = page.locator(".add-api-operations")
    expect(operations).to_contain_text("/orders/{order_id}")
    expect(page.locator(".add-api-file")).to_contain_text("API_")
    operations.locator("button[aria-label^='Try ']").first.click()
    expect(page.locator(".add-api-try")).to_contain_text("type it under Sign in to try it")
    key = page.locator(".add-api-values input[aria-label=ORDERS_API_KEY]")
    expect(key).to_have_attribute("type", "password")
    key.fill(API_KEY)
    operations.locator("button[aria-label^='Try ']").first.click()
    expect(page.locator(".add-api-try .status-ok")).to_contain_text("It works")
    key.fill("")  # nothing kept: the value was for Try it only
    page.locator("input[aria-label=Name]").fill("Made up shop")
    expect(page.locator(".add-api-file")).to_contain_text("API_Made_up_shop.py", timeout=15000)
    page.locator(".add-api-foot button:has-text('Add')").click()
    expect(page.locator(".api-operations")).to_contain_text("/orders", timeout=30000)
    assert any(a["name"] == "Made up shop" for a in call(server, "GET", "/apis")["apis"])
    call(server, "POST", "/apis/Made%20up%20shop/delete", {"confirm": True})

    page.locator(".apis-add").click()
    page.locator("[role=radio]", has_text="I'll list the endpoints myself").click()
    page.locator("input[aria-label='Base address']").fill(orders_service.url)
    card = page.locator(".add-api-endpoint[aria-label='Endpoint 1']")
    card.locator("input[aria-label=Path]").fill("/orders/{order_id}")
    expect(card.locator(".add-api-needed")).to_contain_text("order_id")
    expect(card.locator("button:has-text('Try it')")).to_be_disabled()
    card.locator("input[aria-label=Path]").fill("/orders")
    expect(page.locator(".add-api-operations")).to_contain_text("get_orders")
    page.locator(".add-api-part button:has-text('Add an endpoint')").click()
    expect(page.locator(".add-api-endpoint")).to_have_count(2)
    page.locator(".add-api-endpoint[aria-label='Endpoint 2'] button[aria-label='Remove endpoint']").click()
    expect(page.locator(".add-api-endpoint")).to_have_count(1)
    page.close()


def test_open_a_structure_asks_for_a_file(browser: Browser, server: dict[str, Any], tmp_path: Any) -> None:
    """Open…: the system's dialog asked for a file (mode "file", the classic page's word; "open" was
    refused with 400), none here, so the path is typed in the app's own box and the structure opens."""
    made = tmp_path / "made_up_regions.json"
    made.write_text('{"regions": [{"name": "Westmarch", "stores": 3}]}', encoding="utf-8")
    page = open_page(browser, server, "structures")
    with page.expect_response(lambda r: r.url.endswith("/dialogs/choose")) as asked:
        page.locator(".area-page-actions button:has-text('Open…')").click()
    assert asked.value.status == 200
    assert asked.value.request.post_data_json["mode"] == "file"
    box = page.locator(".dialog[aria-label='Open a structure']")
    box.locator("input").fill(str(made))
    box.locator("button:has-text('Choose')").click()
    expect(page.locator(".structures-tab", has_text="made_up_regions")).to_be_visible()
    expect(page.locator(".structure-tree")).to_contain_text("regions")
    page.locator(".structures-tab", has_text="made_up_regions").locator(".structures-tab-close").click()
    page.close()


def test_new_endpoint_the_wizard(browser: Browser, server: dict[str, Any]) -> None:
    """New endpoint… on the local API's More menu: the sandbox's tables, the patterns ranked by the
    table's shape (the server's), a pattern's own steps, the code it adds kept current, Add to API.py;
    the sandbox panel's row opens it on its table."""
    call(server, "POST", "/project/new", {"name": "Made up wizard"})
    columns = [
        {"name": "order_id", "type": "INTEGER", "key": True},
        {"name": "region", "type": "VARCHAR"},
        {"name": "total", "type": "DOUBLE"},
        {"name": "ordered_on", "type": "DATE"},
    ]
    call(server, "POST", "/sandbox/tables", {"from": "columns", "name": "orders", "columns": columns})
    page = open_page(browser, server, "apis")
    local = page.locator(".local-apis")
    expect(local.locator(".local-api-bar")).to_be_visible()
    local.locator("button[aria-label=More]").click()
    page.locator(".context-menu [role=menuitem]", has_text="New endpoint…").click()
    wizard = page.locator(".dialog[aria-label='New endpoint']")
    expect(wizard.locator("select[aria-label=Table]")).to_have_value("orders")
    expect(wizard.locator(".wizard-pattern").first).to_be_visible()
    expect(wizard.locator(".wizard-said")).to_contain_text("for API.py")
    expect(wizard.locator(".wizard-code")).to_contain_text("@endpoint")
    fits = wizard.locator(".wizard-pattern:not(.unfit)")
    assert fits.count() >= 2
    fits.nth(1).locator("input").check()
    expect(wizard.locator(".wizard-step").first).to_be_visible()
    wizard.locator("button:has-text('Add to API.py')").click()
    expect(page.locator(".note-corner")).to_contain_text("new endpoint")
    state = call(server, "GET", "/local-api")
    assert state["endpoints"], state
    page.goto(page.url.split("/blazor/")[0] + "/blazor/apis?endpoint=orders")
    again = page.locator(".dialog[aria-label='New endpoint']")
    expect(again.locator("select[aria-label=Table]")).to_have_value("orders")
    again.locator("button:has-text('Cancel')").click()
    call(server, "POST", "/project/close", {})
    page.close()


def test_what_it_answers_write_rows_and_discover(
    browser: Browser, server: dict[str, Any], orders_service: Service
) -> None:
    """An operation's What it answers (as its specification declares it, Run, Build: the cell's code to
    copy with no project open), Write rows with this call (the rows, the mapping, a dry run that sends
    nothing) and Discover with its Allow remembered (Take it back)."""
    if not any(a["name"] == "Orders" for a in call(server, "GET", "/apis")["apis"]):
        call(
            server,
            "POST",
            "/apis",
            {"spec_url": orders_service.url + "/openapi.json", "auth": {"type": "none"}},
        )
    call(server, "POST", "/samples/store", {})
    page = open_page(browser, server, "apis?name=Orders")
    learned = page.locator(".api-learned")
    expect(learned.locator(".api-learned-line")).to_be_visible()
    expect(learned.locator(".api-learned-kind")).to_be_visible()
    learned.locator("button:has-text('Notebook cell')").click()
    shown = page.locator(".dialog[aria-label='A notebook cell']")
    expect(shown.locator(".api-built-code")).to_contain_text("sab.run")
    shown.locator("button:has-text('Close')").click()
    learned.locator("button.api-run").click()
    expect(page.locator(".note-corner")).to_contain_text("page")
    call(server, "POST", "/project/new", {"name": "Made up builds"})
    learned.locator("button:has-text('Script function')").click()
    pick = page.locator(".dialog[aria-label='Put the function in a script']")
    expect(pick.locator("select[aria-label=Script]")).to_be_visible()
    expect(pick.locator("input[aria-label='New script']")).to_have_value("api_functions.py")
    pick.locator("button:has-text('Cancel')").click()
    call(server, "POST", "/project/close", {})
    call(server, "POST", "/samples/store", {})  # the project's close closed its tables

    page.locator(".api-operations a", has_text="POST").first.click()
    page.locator("button:has-text('Write rows with this call')").click()
    write = page.locator(".api-write-screen")
    expect(write.locator("select[aria-label='The rows'] option").first).to_be_attached()
    expect(write.locator(".api-mapping tbody tr").first).to_be_visible()
    write.locator("button:has-text('Dry run')").click()
    expect(write.locator(".api-write-result")).to_contain_text("Nothing was sent.")
    write.locator("button:has-text('Back')").click()
    expect(page.locator(".api-write-screen")).to_have_count(0)

    page.locator(".api-discover").click()
    allow = page.locator(".dialog", has_text="Discover")
    if allow.count():
        allow.locator("button:has-text('Allow')").first.click()
    expect(page.locator(".note-corner")).to_contain_text("nothing that writes", timeout=30000)
    expect(page.locator(".api-discover-allowed")).to_contain_text("Discover allowed since")
    page.locator(".api-discover-forget").click()
    expect(page.locator(".api-discover-allowed")).to_have_count(0)
    page.close()
