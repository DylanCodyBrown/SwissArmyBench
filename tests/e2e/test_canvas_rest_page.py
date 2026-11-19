"""The canvas's remaining work in the Workbench window (2026-11-19): a SQL query from the Toolbox makes its
%%sql cell and its block; the pane's query section shows its connection, the page value its query names and
the block that gives it, and Show as turns its result into a chart. Screenshots when
SWISSARMYBENCH_CANVAS_SHOTS names a folder. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, expect

from tests.e2e.test_canvas_designer_page import block, front
from tests.e2e.test_canvas_pane_page import open_window, orders, pane, shot, until  # noqa: F401
from tests.e2e.test_table_cells_page import window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.test_connections import sqlite_connection

FILTER = '# Region filter\nregion = st.selectbox("Region", ["East", "West"], key="region_pick")'
QUERY = "-- Orders in the region\nSELECT order_id, amount FROM orders WHERE region = {{ region }}"


def _shop(server: dict[str, Any], folder: Path) -> None:  # noqa: F811
    database = folder / "shop.sqlite"
    with sqlite3.connect(database) as made:
        made.execute("CREATE TABLE IF NOT EXISTS orders (order_id INTEGER, region TEXT, amount INTEGER)")
        made.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(1, "East", 100), (2, "West", 250)])
    try:
        call(server, "POST", "/connections", sqlite_connection(database))
    except urllib.error.HTTPError:  # saved by an earlier test: point it here
        call(server, "PUT", "/connections/Shop", sqlite_connection(database))


def query_app(server: dict[str, Any], folder: Path) -> Path:  # noqa: F811
    folder.mkdir(parents=True, exist_ok=True)
    _shop(server, folder)
    notebook = folder / "app.ipynb"
    cells = [
        {"kind": "code", "source": FILTER, "name": "Region filter"},
        {"kind": "sql", "source": QUERY, "connection": "Shop -> by_region", "name": "by_region"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 4, "h": None},
        {"document": str(notebook), "cell": 2, "row": 1, "column": 5, "w": 8, "h": None},
    ]
    app = folder / "orders.stapp.json"
    call(
        server, "POST", "/workbench/save", {"path": str(app), "pages": [{"name": "Orders", "blocks": blocks}]}
    )
    return app


def test_a_sql_block_its_query_section_and_a_query_from_the_toolbox(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    app = query_app(server, tmp_path / "shop")
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    blocks = board.locator(".cv-block")
    expect(blocks).to_have_count(2, timeout=20000)
    expect(board.locator(".cv-query")).to_have_text("SQL")
    props = pane(page)
    blocks.nth(1).click()
    section = props.locator('[data-section="query"]')
    expect(section).to_be_visible(timeout=15000)
    expect(section.locator("select[data-field=connection]")).to_have_value("Shop")
    param = section.locator('[data-param="region"]')
    expect(param).to_contain_text("Region filter")
    shot(page, "query-block-pane")
    # Show as a bar chart: the block's view, and the code the page runs.
    section.locator("select[data-field=as]").select_option("bar")
    until(lambda: block(server, "b2").get("view", {}).get("as"), "bar")
    expect(props.locator("pre.cp-code")).to_contain_text("st.bar_chart(by_region", timeout=15000)
    # The page value's link selects the block that gives it.
    props.locator('[data-param="region"]').click()
    until(lambda: window(server, "canvas.state")["selected"], ["b1"])
    # The Toolbox's SQL query: its %%sql cell in the app notebook and its block.
    assert window(server, "canvas.panel", panel="toolbox") == {"open": True}
    toolbox = page.locator(".wb-mode-toolbox")
    toolbox.get_by_role("searchbox", name="Search the Toolbox").fill("SQL")
    toolbox.locator('.tb-item[data-tool="sql_query"]').click()
    expect(blocks).to_have_count(3, timeout=30000)
    until(lambda: any(b["name"] == "query_1" for b in front(server)["blocks"]), True)
    saved = json.loads((tmp_path / "shop" / "app.ipynb").read_text(encoding="utf-8"))
    assert any(c["source"] and "".join(c["source"]).startswith("%%sql") for c in saved["cells"])
    shot(page, "query-block-toolbox")
    page.context.close()


LEVEL = '# Level\nlevel = st.slider("Level", 1, 9, 3, key="level")'
SIZE = '# Size\nsize = st.slider("Size", 1, 20, 5, key="size")'
ECHO = '# Echo\nimport os\n\nst.write(st.session_state.get("level"), os.environ.get("REGION_DEFAULT", ""))'


def designer_app(server: dict[str, Any], folder: Path) -> Path:  # noqa: F811
    """Two sliders (the same element) and a block that reads the first one's key from session state."""
    folder.mkdir(parents=True, exist_ok=True)
    _shop(server, folder)
    notebook = folder / "app.ipynb"
    cells = [
        {"kind": "code", "source": LEVEL, "name": "Level"},
        {"kind": "code", "source": SIZE, "name": "Size"},
        {"kind": "code", "source": ECHO, "name": "Echo"},
        {"kind": "sql", "source": QUERY, "connection": "Shop -> by_region", "name": "by_region"},
    ]
    call(server, "POST", "/workbench/save", {"path": str(notebook), "cells": cells})
    blocks = [
        {"document": str(notebook), "cell": 1, "row": 1, "column": 1, "w": 6, "h": None},
        {"document": str(notebook), "cell": 2, "row": 1, "column": 7, "w": 6, "h": None},
        {"document": str(notebook), "cell": 3, "row": 2, "column": 1, "w": 12, "h": None},
        {"document": str(notebook), "cell": 4, "row": 3, "column": 1, "w": 12, "h": None},
    ]
    app = folder / "design.stapp.json"
    call(
        server, "POST", "/workbench/save", {"path": str(app), "pages": [{"name": "Design", "blocks": blocks}]}
    )
    return app


def test_binding_lines_shared_properties_and_uses_links(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    app = designer_app(server, tmp_path / "design")
    page = open_window(browser, server, app)
    board = page.locator(".cv .cv-board")
    blocks = board.locator(".cv-block")
    expect(blocks).to_have_count(4, timeout=20000)
    # A session state binding is drawn: Level's key, read by Echo, dashed with the key on it.
    blocks.nth(0).click()
    wire = board.locator('.cv-wires path.cv-wire-state[data-to="b3"]')
    expect(wire).to_have_count(1, timeout=15000)
    assert wire.get_attribute("data-key") == "level"
    expect(board.locator(".cv-wire-key")).to_have_text('session_state["level"]')
    shot(page, "designer-state-binding")
    # Several blocks: a property of the widget they share, set on both cells at once.
    props = pane(page)
    blocks.nth(1).click(modifiers=["Control"])
    expect(props.locator(".cp-target")).to_have_text("2 blocks")
    box = props.locator("input[data-field=max_value]")
    expect(box).to_have_attribute("placeholder", "Mixed", timeout=15000)
    box.fill("30")
    box.press("Enter")
    for block_id in ("b1", "b2"):
        until(lambda b=block_id: _argument(server, b, "max_value"), 30, 20)
    expect(props.locator("input[data-field=locked]")).to_be_visible()
    shot(page, "designer-multi-select")
    # Uses: a variable opens the Variables page at its name; a connection its own card.
    page.keyboard.press("Escape")
    blocks.nth(2).click()
    props.locator('.cp-list[data-list="variables"] .cp-link', has_text="REGION_DEFAULT").click()
    expect(page.get_by_role("searchbox", name="Search variables")).to_have_value(
        "REGION_DEFAULT", timeout=15000
    )
    assert "name=REGION_DEFAULT" in page.url
    page.go_back()
    blocks.nth(3).click()
    props.locator('.cp-list[data-list="connections"] .cp-link', has_text="Shop").click()
    expect(page.locator(".area-page, [data-area=connections]").first).to_be_visible(timeout=15000)
    assert "at=detail" in page.url and "name=Shop" in page.url
    page.context.close()


def _argument(server: dict[str, Any], block_id: str, name: str) -> Any:  # noqa: F811
    apps = call(server, "GET", "/streamlit/apps")["apps"]
    app = [a["app"] for a in apps if a["kind"] == "canvas"][-1]
    seen = call(server, "GET", f"/streamlit/apps/{app}/inspect?page=p1&block={block_id}")
    value = seen["widgets"][0]["arguments"].get(name)
    return value["value"] if value else None


def test_add_to_app_from_a_live_cell(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    folder = tmp_path / "loose"
    folder.mkdir()
    notebook = folder / "widgets.ipynb"
    call(
        server,
        "POST",
        "/workbench/save",
        {"path": str(notebook), "cells": [{"kind": "code", "source": LEVEL}]},
    )
    page = open_window(browser, server, notebook)
    add = page.locator(".wb-piece-add")
    expect(add).to_be_visible(timeout=20000)
    shot(page, "add-to-app")
    add.click()
    board = page.locator(".cv .cv-board")
    expect(board.locator(".cv-block")).to_have_count(1, timeout=30000)
    assert front(server)["blocks"][0]["cell"] == 1
    page.context.close()


def test_designer_views_light_and_dark(
    browser: Browser,  # noqa: F811
    server: dict[str, Any],  # noqa: F811
    orders: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Each designer view, light and dark (the screenshots; the views drawn without an error either way)."""
    app = designer_app(server, tmp_path / "views")
    for dark in (False, True):
        theme = "dark" if dark else "light"
        page = open_window(browser, server, app, dark=dark)
        board = page.locator(".cv .cv-board")
        expect(board.locator(".cv-block")).to_have_count(4, timeout=20000)
        board.locator(".cv-block").nth(0).click()
        expect(board.locator(".cv-wires")).to_have_count(1, timeout=15000)
        shot(page, f"view-wiring-{theme}")
        assert window(server, "canvas.panel", panel="toolbox") == {"open": True}
        expect(page.locator(".wb-mode-toolbox .tb-group").first).to_be_visible(timeout=15000)
        shot(page, f"view-toolbox-{theme}")
        assert window(server, "canvas.panel", panel="outline") == {"open": True}
        expect(page.locator(".wb-mode-outline .ol-row").first).to_be_visible(timeout=15000)
        shot(page, f"view-outline-{theme}")
        props = pane(page)
        board.locator(".cv-block").nth(3).click()
        expect(props.locator('[data-section="query"]')).to_be_visible(timeout=15000)
        shot(page, f"view-properties-{theme}")
        board.locator(".cv-block").nth(1).click(modifiers=["Control"])
        expect(props.locator(".cp-target")).to_have_text("2 blocks", timeout=15000)
        shot(page, f"view-multi-select-{theme}")
        page.context.close()
