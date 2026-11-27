"""Pop out any page or any table into a window of its own (the owner, 2026-11-27): "that grid or page should
go blank on the original app with a reattach button in the pane to bring it back" / "Grids should have a
reattach button to bring them back." On the made-up sample store: a table popped out with its steps, both
Reattach buttons, the popped-out page closed by the user, a rail page out and back, the agent's command."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.blazor.conftest import FIRST_LOAD_MS, call, loose_file, open_page


def as_agent(info: dict[str, Any], method: str, path: str, body: Any = None) -> Any:
    """The route the agent's command calls (app_navigate's pop: cli/commands_app.py), as the agent."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {info['token']}",
            "X-Actor": "agent",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (127.0.0.1)
        return json.loads(response.read() or b"null")


def orders_with_a_step(server: dict[str, Any]) -> str:
    made = call(server, "POST", "/samples/store", {})
    grid = next(t["grid"] for t in made["tables"] if t["name"].startswith("orders"))
    call(server, "POST", f"/grids/{grid}/step-ops", {"op": "add", "step": {"kind": "distinct", "params": {}}})
    return str(grid)


def popped_out(page: Page, click: Any) -> Page:
    """The window a click pops out, once its page is drawn alone (no rail)."""
    with page.context.expect_page() as opened:
        click()
    own = opened.value
    own.set_default_timeout(15_000)
    own.wait_for_selector("body.popped-out .page-main", timeout=FIRST_LOAD_MS)
    expect(own.locator(".nav-rail")).to_have_count(0)
    return own


def nothing_popped(server: dict[str, Any]) -> None:
    assert call(server, "GET", "/pop-outs")["popped"] == []


def test_a_table_pops_out_with_its_steps_and_reattaches_from_the_placeholder(
    browser: Browser, server: dict[str, Any]
) -> None:
    grid = orders_with_a_step(server)
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()
    own = popped_out(page, lambda: page.get_by_role("button", name="Pop out this table").click())
    # Its own window: the same table alone (one tab), its steps, its rows.
    expect(own.locator(".tabs-row [role=tab]")).to_have_count(1)
    expect(own.locator(".tabs-row [role=tab]")).to_contain_text("orders")
    expect(own.locator(".steps-strip")).to_contain_text("Keep distinct rows")
    expect(own.locator(".ag-row").first).to_be_visible()
    assert f"grid={grid}" in own.url
    # The original tab is blank but for the placeholder; its other tabs stay.
    placeholder = page.locator(".pop-out-placeholder")
    expect(placeholder).to_contain_text("orders is open in its own window")
    expect(page.locator(".ag-row")).to_have_count(0)
    expect(page.locator(".steps-strip")).to_have_count(0)
    assert page.locator(".tabs-row [role=tab]").count() > 1
    assert [e["key"] for e in call(server, "GET", "/pop-outs")["popped"]] == [f"table:{grid}"]
    # A step added in its own window is there when it comes back (its current state).
    call(
        server,
        "POST",
        f"/grids/{grid}/step-ops",
        {"op": "add", "step": {"kind": "limit", "params": {"n": 5}}},
    )
    expect(own.locator(".steps-strip")).to_contain_text("first")
    with own.expect_event("close"):
        placeholder.get_by_role("button", name="Reattach").click()
    expect(placeholder).to_have_count(0)
    expect(page.locator(".steps-strip")).to_contain_text("Keep distinct rows")
    expect(page.locator(".steps-strip")).to_contain_text("first")
    expect(page.locator(".ag-row").first).to_be_visible()
    nothing_popped(server)
    page.close()


def test_the_popped_out_tables_own_reattach_and_closing_its_page(
    browser: Browser, server: dict[str, Any]
) -> None:
    grid = orders_with_a_step(server)
    page = open_page(browser, server, f"tables?grid={grid}")
    expect(page.locator(".ag-row").first).to_be_visible()
    # The tab's menu pops it out too.
    page.locator(".tabs-row [role=tab][aria-selected=true]").click(button="right")
    own = popped_out(page, lambda: page.get_by_role("menuitem", name="Pop out").click())
    expect(page.locator(".pop-out-placeholder")).to_be_visible()
    # Reattach in the popped-out table's own header: back in the original window, its own closed.
    reattach = own.get_by_role("button", name="Reattach")
    expect(reattach).to_have_attribute("title", "Reattach: back in the main window, this window closes")
    with own.expect_event("close"):
        reattach.click()
    expect(page.locator(".pop-out-placeholder")).to_have_count(0)
    expect(page.locator(".ag-row").first).to_be_visible()
    nothing_popped(server)

    # Popped out again and its page closed by the user: the original shows the table again by itself.
    own = popped_out(page, lambda: page.get_by_role("button", name="Pop out this table").click())
    expect(page.locator(".pop-out-placeholder")).to_be_visible()
    own.close()
    expect(page.locator(".pop-out-placeholder")).to_have_count(0)
    expect(page.locator(".ag-row").first).to_be_visible()
    nothing_popped(server)
    page.close()


def test_with_the_main_window_gone_reattach_opens_a_new_one(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_with_a_step(server)
    # A context of its own: closing the main page must leave the popped-out one open.
    context = browser.new_context(viewport={"width": 1360, "height": 860})
    page = context.new_page()
    page.set_default_timeout(15_000)
    page.goto(f"http://127.0.0.1:{server['port']}/blazor/tables?grid={grid}#token={server['token']}")
    page.wait_for_selector(".nav-rail", timeout=FIRST_LOAD_MS)
    expect(page.locator(".ag-row").first).to_be_visible()
    own = popped_out(page, lambda: page.get_by_role("button", name="Pop out this table").click())
    page.close()
    # It keeps working by itself, and its Reattach says what it will do.
    reattach = own.get_by_role("button", name="Reattach")
    expect(reattach).to_have_attribute(
        "title", "Reattach: the main window is closed, so it opens in a new one and this window closes"
    )
    expect(own.locator(".ag-row").first).to_be_visible()
    with own.context.expect_page() as opened:
        reattach.click()
    main = opened.value
    main.wait_for_selector(".nav-rail", timeout=FIRST_LOAD_MS)
    expect(main.locator(".tabs-row [role=tab][aria-selected=true]")).to_contain_text("orders")
    expect(main.locator(".ag-row").first).to_be_visible()
    expect(main.locator(".pop-out-placeholder")).to_have_count(0)
    nothing_popped(server)
    context.close()


def test_a_rail_page_pops_out_in_the_same_state_and_reattaches(
    browser: Browser, server: dict[str, Any]
) -> None:
    page = open_page(browser, server, "connections?add=1")
    expect(page.get_by_role("button", name="Pop out")).to_be_visible()
    own = popped_out(page, lambda: page.get_by_role("button", name="Pop out").click())
    assert own.url.endswith("/blazor/connections?add=1")  # the same state: Add connection, as it was
    placeholder = page.locator(".pop-out-placeholder")
    expect(placeholder).to_contain_text("Connections is open in its own window")
    expect(page.get_by_role("button", name="Pop out")).to_have_count(0)
    expect(page.locator(".nav-rail")).to_be_visible()  # the rail stays: other pages go on working
    # Popped out a second time (the agent's): the window there is stays the only one.
    assert as_agent(server, "POST", "/pop-outs", {"page": "connections"})["existing"] is True
    assert len(page.context.pages) == 2
    placeholder.get_by_role("button", name="Show window").click()
    # Another page of the main window is itself; back on Connections, the placeholder again.
    page.locator(".nav-rail-item[data-area=settings]").click()
    expect(page.locator(".pop-out-placeholder")).to_have_count(0)
    page.locator(".nav-rail-item[data-area=connections]").click()
    expect(placeholder).to_be_visible()
    # The popped-out page moved on (Add connection closed): Reattach shows it where it is now.
    own.goto(own.url.replace("?add=1", ""))
    own.wait_for_selector("body.popped-out .page-main", timeout=FIRST_LOAD_MS)
    expect(placeholder).to_be_visible()  # a reload of the popped-out page keeps it popped out
    with own.expect_event("close"):
        placeholder.get_by_role("button", name="Reattach").click()
    expect(placeholder).to_have_count(0)
    page.wait_for_url("**/blazor/connections")
    nothing_popped(server)
    page.close()


def test_the_agents_command_pops_a_page_out_and_back(browser: Browser, server: dict[str, Any]) -> None:
    page = open_page(browser, server, "")
    with page.context.expect_page() as opened:
        made = as_agent(server, "POST", "/pop-outs", {"page": "settings"})
    assert made["key"] == "page:settings" and made["existing"] is False
    own = opened.value
    own.wait_for_selector("body.popped-out .page-main", timeout=FIRST_LOAD_MS)
    assert own.url.endswith("/blazor/settings")
    listed = as_agent(server, "GET", "/pop-outs")
    assert [(e["name"], e["connected"]) for e in listed["popped"]] == [("Settings", True)] and listed[
        "mains"
    ] == 1
    # The original window shows the placeholder once it is on that page; the screen state says both.
    page.locator(".nav-rail-item[data-area=settings]").click()
    expect(page.locator(".pop-out-placeholder")).to_contain_text("Settings is open in its own window")

    def shows() -> list[str]:
        return [w.get("shows", "") for w in as_agent(server, "GET", "/screen")["windows"]]

    expect(page.locator(".pop-out-placeholder")).to_be_visible()
    page.wait_for_function("() => true")
    for _ in range(40):
        if any("Reattach brings it back" in s for s in shows()) and any("popped out" in s for s in shows()):
            break
        page.wait_for_timeout(250)
    assert any(s.startswith("Settings is open in its own window") for s in shows())
    assert any("Settings, popped out in its own window" in s for s in shows())
    with own.expect_event("close"):
        assert as_agent(server, "POST", "/pop-outs/reattach", {"page": "settings"})["reattached"] is True
    expect(page.locator(".pop-out-placeholder")).to_have_count(0)
    expect(page.locator(".settings-page, .area-page").first).to_be_visible()
    nothing_popped(server)
    page.close()


def test_a_document_pops_out_and_its_tab_shows_the_placeholder(
    browser: Browser, server: dict[str, Any]
) -> None:
    path = loose_file(server, "popped_load.py", text="total = 1 + 2\n")
    page = open_page(browser, server, f"scripts?path={urllib.parse.quote(str(path))}")
    tab = page.locator(".wb-tab", has_text="popped_load.py").first
    expect(tab).to_be_visible()
    page.click(".wb-group.focused button[aria-label='Document menu']")
    own = popped_out(page, lambda: page.locator(".menu-item", has_text="Open in its own window").click())
    expect(own.locator(".wb-tab", has_text="popped_load.py").first).to_be_visible()
    # Its tab stays in the original window, blank but for the placeholder.
    expect(tab).to_be_visible()
    placeholder = page.locator(".wb-doc-body:not([hidden]) .pop-out-placeholder")
    expect(placeholder).to_contain_text("popped_load.py is open in its own window")
    expect(page.locator(".wb-doc-body:not([hidden]) .monaco-editor")).to_be_hidden()
    with own.expect_event("close"):
        placeholder.get_by_role("button", name="Reattach").click()
    expect(placeholder).to_have_count(0)
    expect(page.locator(".wb-doc-body:not([hidden]) .monaco-editor").first).to_be_visible()
    nothing_popped(server)
    page.close()
