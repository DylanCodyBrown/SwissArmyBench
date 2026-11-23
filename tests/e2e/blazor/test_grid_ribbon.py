"""The Blazor Grids page's ribbon (the classic ribbon.ts, cellMenu.ts, stepForms.ts) on the made-up sample
store: a Table tool (Keep first rows through its step editor), a Column tool on a selected column (Sort
Z→A), a step edited from the strip, the selection's numbers in the status bar, and a cell's Copy from its
right-click menu."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, ViewportSize, expect

from tests.e2e.blazor.conftest import call, open_page

# Wide enough that every column of orders is drawn beside a column's card (AG Grid draws only columns on
# screen).
WIDE: ViewportSize = {"width": 1900, "height": 900}


def orders_grid(server: dict[str, Any]) -> str:
    made = call(server, "POST", "/samples/store", {})
    return str(next(t["grid"] for t in made["tables"] if t["name"].startswith("orders")))


def test_table_tool_opens_its_step_editor_and_adds_the_step(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_grid(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    expect(page.locator(".ribbon")).to_contain_text("Table")
    page.click("[data-tool=limit]")
    expect(page.locator(".dialog")).to_contain_text("Add step: Keep first rows")
    page.fill("input[aria-label='Rows to keep']", "12")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".steps-strip")).to_contain_text("Keep the first 12 rows")
    expect(page.locator(".status-rows")).to_contain_text("of 12 (")
    assert call(server, "GET", f"/grids/{grid}")["steps"][-1]["params"] == {"n": 12}

    # The step's words open its editor again: the edit lands in its place.
    page.locator(".step-words", has_text="Keep the first 12 rows").click()
    expect(page.locator(".dialog")).to_contain_text("Edit step: Keep first rows")
    page.fill("input[aria-label='Rows to keep']", "7")
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".status-rows")).to_contain_text("of 7 (")
    steps = call(server, "GET", f"/grids/{grid}")["steps"]
    assert [s["params"] for s in steps if s["kind"] == "limit"] == [{"n": 7}]
    page.close()


def test_column_tool_acts_on_the_selected_column(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_grid(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.set_viewport_size(WIDE)
    expect(page.locator("[data-tool=col-sort-desc]")).to_be_disabled()
    page.click(".ag-header-cell[col-id=amount] .sab-header-name")
    expect(page.locator(".ribbon-target")).to_have_text("amount")
    # The column's numbers in the status bar (counted by the server over the whole column).
    expect(page.locator(".status-selection")).to_contain_text("Count")
    expect(page.locator(".status-selection")).to_contain_text("Sum")
    expect(page.locator("[data-tool=col-bucket]")).to_be_enabled()
    page.click("[data-tool=col-sort-desc]")
    expect(page.locator(".steps-strip")).to_contain_text("Sort by amount descending")
    step = call(server, "GET", f"/grids/{grid}")["steps"][-1]
    assert step["kind"] == "sort" and step["params"]["keys"] == [["amount", "desc"]]

    # A text column cannot be bucketed: the button says why.
    page.click(".ag-header-cell[col-id=status] .sab-header-name")
    expect(page.locator("[data-tool=col-bucket]")).to_be_disabled()
    expect(page.locator("[data-tool=col-bucket]")).to_have_attribute("title", "Number or date columns only.")
    page.close()


def test_filter_editor_ticks_a_columns_values(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_grid(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.set_viewport_size(WIDE)
    page.click(".ag-header-cell[col-id=status] .sab-header-name")
    page.click("[data-tool=col-filter]")
    expect(page.locator(".dialog")).to_contain_text("Add step: Filter")
    first = page.locator(".filter-value").first
    expect(first).to_be_visible()
    value = first.locator(".filter-value-text").inner_text()
    first.locator("input").check()
    page.click(".dialog-foot .btn.primary")
    expect(page.locator(".steps-strip")).to_contain_text(value)
    step = call(server, "GET", f"/grids/{grid}")["steps"][-1]
    assert step["params"] == {"column": "status", "op": "in", "values": [value]}
    page.close()


def test_a_cells_copy_from_its_menu(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_grid(server)
    page = open_page(browser, server, f"grids?grid={grid}")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    cell = page.locator(".ag-row[row-index='0'] .ag-cell[col-id=order_id]")
    expect(cell).not_to_have_text("")
    shown = cell.inner_text().strip()
    cell.click(button="right")
    expect(page.locator(".context-menu")).to_contain_text("order_id, row 1")
    page.click(".context-menu .menu-item:has-text('Copy with headers')")
    expect(page.locator(".toast")).to_contain_text("Copied 1 row × 1 column with headers.")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied.replace("\r\n", "\n").strip() == f"order_id\n{shown}"

    # Keep these: the clicked cell's value as a filter step.
    cell.click(button="right")
    page.click(".context-menu .menu-item:has-text('Keep these')")
    expect(page.locator(".steps-strip")).to_contain_text("order_id equals")
    expect(page.locator(".status-rows")).to_contain_text("Rows 1–1 of 1 (")
    page.close()


def test_copy_as_code_is_verified_before_it_is_offered(browser: Browser, server: dict[str, Any]) -> None:
    grid = orders_grid(server)
    call(
        server,
        "POST",
        f"/grids/{grid}/step-ops",
        {"op": "add", "step": {"kind": "limit", "params": {"n": 5}}},
    )
    page = open_page(browser, server, f"grids?grid={grid}")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.click("[data-tool=code]")
    dialog = page.locator(".dialog")
    expect(dialog).to_contain_text("Verified")
    expect(dialog.locator(".monaco-editor")).to_contain_text("LIMIT 5")
    dialog.locator("button:has-text('Copy as SQL')").click()
    expect(page.locator(".toast")).to_contain_text("Copied the verified SQL query.")
    assert "LIMIT 5" in page.evaluate("navigator.clipboard.readText()")
    page.close()
