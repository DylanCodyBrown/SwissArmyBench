# ruff: noqa: F811
"""The Workbench redesign (2026-11-15, docs/ideas.md) in a real browser: tab groups split right and down
by command and by drag, tabs reordered, the layout back after a reload, the Data Explorer opened and
closed, "+ Table" reaching Open file and a connection's tables, and the status bar's kernel menu.

Made-up data only: a CSV of three orders in the test's own folder.
"""

from __future__ import annotations

import re
import urllib.error
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Browser, Locator, Page, expect

from tests.e2e.test_table_cells_page import close_tables, open_workbench, type_cell, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import menu, seen_by_server, start, status, wait_until


def refused(server: dict[str, Any], command: str, **args: Any) -> str:
    """What the window says when a command cannot run."""
    try:
        window(server, command, **args)
    except urllib.error.HTTPError as error:
        return str(error.read().decode())
    raise AssertionError(f"{command} ran")


def titles(group: Locator) -> list[str]:
    return [str(t) for t in group.locator(".wb-tab .tab-label").all_inner_texts()]


def three_tabs(workbench: Page) -> None:
    """Three notebooks in the one group (a script is the Scripts page's since 2026-11-21)."""
    start(workbench)
    start(workbench)
    start(workbench)
    expect(workbench.locator(".wb-tab")).to_have_count(3, timeout=20000)


def drag(workbench: Page, source: Locator, x: float, y: float) -> None:
    """Press on `source`, move in steps to (x, y), let go: as a hand does."""
    box = source.bounding_box()
    assert box
    workbench.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    workbench.mouse.down()
    for step in range(1, 11):
        sx = box["x"] + box["width"] / 2 + (x - box["x"] - box["width"] / 2) * step / 10
        sy = box["y"] + box["height"] / 2 + (y - box["y"] - box["height"] / 2) * step / 10
        workbench.mouse.move(sx, sy)
    workbench.mouse.up()


def test_groups_split_right_and_down_by_command_and_come_back_after_a_reload(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    workbench = open_workbench(browser, server)
    three_tabs(workbench)
    groups = workbench.locator(".wb-group")
    expect(groups).to_have_count(1)
    # Split right: the tab in front moves to a new group on the right, which takes the focus.
    window(server, "group.splitRight")
    expect(groups).to_have_count(2)
    expect(workbench.locator(".wb-gsplit.row > .wb-group")).to_have_count(2)
    assert titles(groups.nth(0)) == ["Untitled notebook 1", "Untitled notebook 2"]
    assert titles(groups.nth(1)) == ["Untitled notebook 3"]
    expect(groups.nth(1)).to_have_class(re.compile(r"\bfocused\b"))
    # Only the focused group's row has the controls.
    expect(groups.nth(1).get_by_role("button", name="Run all")).to_be_visible()
    expect(groups.nth(0).locator(".wb-gcontrols > *")).to_have_count(0)
    assert "only this tab" in refused(server, "group.splitDown")
    # Focus the first group (the agent's command), then Split down from the palette.
    window(server, "group.focus", group=0)
    expect(groups.nth(0)).to_have_class(re.compile(r"\bfocused\b"))
    expect(groups.nth(0).get_by_role("button", name="Run all")).to_be_visible()
    workbench.keyboard.press("Control+Shift+P")
    workbench.get_by_role("combobox", name="Command").fill("split down")
    workbench.keyboard.press("Enter")
    expect(groups).to_have_count(3)
    expect(workbench.locator(".wb-gsplit.row > .wb-gsplit.column > .wb-group")).to_have_count(2)
    listed = window(server, "documents")
    assert [g["documents"] for g in listed["groups"]] == [[0], [1], [2]]
    assert listed["groups"][1]["focused"] is True
    # A splitter moves by keyboard.
    sash = workbench.locator(".wb-gsash.row")
    sash.focus()
    remembered = "() => sessionStorage.getItem('workbench-documents:notebooks')"
    before = workbench.evaluate(remembered)
    workbench.keyboard.press("ArrowRight")
    expect(sash).to_have_attribute("aria-valuenow", "53")
    # Remembered a moment after the last change (the window's session storage): wait until it is.
    workbench.wait_for_function(f"before => ({remembered})() !== before", arg=before)

    # A reload brings back the documents and the groups as they were, the focused one too.
    workbench.reload()
    expect(groups).to_have_count(3, timeout=20000)
    assert [titles(groups.nth(i)) for i in range(3)] == [
        ["Untitled notebook 1"],
        ["Untitled notebook 2"],
        ["Untitled notebook 3"],
    ]
    expect(workbench.locator(".wb-gsplit.row > .wb-gsplit.column > .wb-group")).to_have_count(2)
    expect(groups.nth(1)).to_have_class(re.compile(r"\bfocused\b"))
    flex = workbench.locator(".wb-gsplit.row > .wb-gsplit.column").evaluate(
        "el => parseFloat(el.style.flexGrow)"
    )
    assert abs(flex - 1.06) < 0.02  # the splitter's place too
    # Closing a group's last tab removes the group.
    groups.nth(1).get_by_role("button", name="Close Untitled notebook 2").click()
    expect(groups).to_have_count(2)
    expect(workbench.locator(".wb-gsplit.column")).to_have_count(0)
    workbench.close()


def test_tabs_reorder_and_split_by_drag_with_the_five_way_guide(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    workbench = open_workbench(browser, server)
    three_tabs(workbench)
    group = workbench.locator(".wb-group").first
    # Drag the third tab before the first: the row's order follows.
    first = group.locator(".wb-tab").first.bounding_box()
    assert first
    drag(workbench, group.locator(".wb-tab").nth(2), first["x"] + 8, first["y"] + first["height"] / 2)
    assert titles(group) == ["Untitled notebook 3", "Untitled notebook 1", "Untitled notebook 2"]
    # Drag a tab to the group's right edge: the guide shows where it goes, and it splits right.
    body = group.locator(".wb-gbody").bounding_box()
    assert body
    tab = group.locator(".wb-tab", has_text="Untitled notebook 2")
    box = tab.bounding_box()
    assert box
    workbench.mouse.move(box["x"] + 20, box["y"] + 10)
    workbench.mouse.down()
    for step in range(1, 11):
        workbench.mouse.move(
            box["x"] + 20 + (body["x"] + body["width"] - 30 - box["x"] - 20) * step / 10,
            body["y"] + body["height"] / 2,
        )
    expect(workbench.locator(".wb-compass")).to_be_visible()
    expect(workbench.locator(".wb-drop")).to_have_attribute("data-zone", "right")
    expect(workbench.locator(".wb-drop-zone")).to_have_text("Split right")
    expect(workbench.locator(".wb-tab-ghost")).to_contain_text("Untitled notebook 2")
    workbench.mouse.up()
    groups = workbench.locator(".wb-group")
    expect(groups).to_have_count(2)
    assert titles(groups.nth(1)) == ["Untitled notebook 2"]
    expect(workbench.locator(".wb-compass")).to_have_count(0)
    # Drag a tab to the lower part of the other group: split down there.
    right = groups.nth(1).locator(".wb-gbody").bounding_box()
    assert right
    drag(
        workbench,
        groups.nth(0).locator(".wb-tab", has_text="Untitled notebook 1"),
        right["x"] + right["width"] / 2,
        right["y"] + right["height"] - 30,
    )
    expect(groups).to_have_count(3)
    assert titles(groups.nth(2)) == ["Untitled notebook 1"]
    expect(workbench.locator(".wb-gsplit.column > .wb-group")).to_have_count(2)
    # Dropped in the middle of another group, a group's only tab moves there and its group goes.
    target = groups.nth(0).locator(".wb-gbody").bounding_box()
    assert target
    drag(
        workbench,
        groups.nth(2).locator(".wb-tab").first,
        target["x"] + target["width"] / 2,
        target["y"] + target["height"] / 2,
    )
    expect(groups).to_have_count(2)
    assert titles(groups.nth(0)) == ["Untitled notebook 3", "Untitled notebook 1"]
    # Escape during a drag puts the tab back.
    tab = groups.nth(0).locator(".wb-tab").first
    box = tab.bounding_box()
    assert box
    workbench.mouse.move(box["x"] + 20, box["y"] + 10)
    workbench.mouse.down()
    workbench.mouse.move(box["x"] + 200, box["y"] + 300, steps=5)
    workbench.keyboard.press("Escape")
    workbench.mouse.up()
    expect(groups).to_have_count(2)
    assert titles(groups.nth(0)) == ["Untitled notebook 3", "Untitled notebook 1"]
    # The tab commands: move left and right in the row, and to the next group.
    window(server, "tab.moveLeft", index=window(server, "documents")["groups"][0]["in_front"])
    assert titles(groups.nth(0)) == ["Untitled notebook 1", "Untitled notebook 3"]
    window(server, "group.moveTab", group=1, position=0)
    assert titles(groups.nth(1)) == ["Untitled notebook 1", "Untitled notebook 2"]
    # A splitter dragged by its grip.
    sash = workbench.locator(".wb-gsash.row")
    grip = sash.bounding_box()
    assert grip
    before = groups.nth(0).bounding_box()
    assert before
    workbench.mouse.move(grip["x"] + 3, grip["y"] + grip["height"] / 2)
    workbench.mouse.down()
    workbench.mouse.move(grip["x"] - 150, grip["y"] + grip["height"] / 2, steps=5)
    workbench.mouse.up()
    after = groups.nth(0).bounding_box()
    assert after and after["width"] < before["width"] - 100
    workbench.close()


def test_the_data_panel_folds_and_table_opens_a_file_and_a_connections_table(
    browser: Browser, server: dict[str, Any], tmp_path: Path
) -> None:
    close_tables(server)
    csv = tmp_path / "shop" / "orders.csv"
    csv.parent.mkdir()
    csv.write_text("order_id,region,amount\n1,North,10.5\n2,South,7\n3,North,2.5\n", encoding="utf-8")
    seen_by_server(server, csv.parent)
    call(
        server,
        "POST",
        "/connections",
        {
            "name": "Shop",
            "kind": "other",
            "template": "csv",
            "code": f'from pathlib import Path\npath = Path(r"{csv}")',
            # The CSV template's catalog: the file's columns, the file as the one table.
            "catalog": {
                "language": "python",
                "command": "import pandas as pd\nsample = pd.read_csv(path, nrows=1000)\n"
                '[{"table_schema": path.parent.name, "table_name": path.stem, "column_name": str(n), '
                '"data_type": str(k)} for n, k in sample.dtypes.items()]',
            },
        },
    )
    try:
        workbench = open_workbench(browser, server)
        panel = workbench.locator(".wb-explorer")
        # The Data Explorer (2026-11-17, in the Data panel's place): off until opened; open or closed is
        # this window's own, kept through a reload; Ctrl+Shift+E opens and closes it.
        expect(panel).to_be_hidden()
        workbench.keyboard.press("Control+Shift+E")
        expect(panel).to_be_visible()
        workbench.reload()
        expect(workbench.locator(".wb-explorer")).to_be_visible(timeout=20000)
        workbench.keyboard.press("Control+Shift+E")
        expect(panel).to_be_hidden()
        assert window(server, "view.explorer", show=True) == {"open": True, "popped": False}

        # "+ Table" → Open file…: the file chooser, then the table in the panel with its rows and file.
        start(workbench)
        expect(workbench.locator(".wb-cell")).to_have_count(1, timeout=20000)
        menu(workbench, "Add a table", "Open file…")
        chooser = workbench.locator(".file-chooser")
        folder = chooser.locator("input[aria-label=Folder]")
        folder.fill(str(csv.parent))
        folder.press("Enter")
        chooser.locator(".file-row.file", has_text="orders.csv").dblclick()
        # The table is an Explorer result: its rows and its file.
        panel.locator(".ex-search").fill("orders")
        card = panel.locator(".ex-group[data-kind='tables'] .ex-result", has_text="3 rows")
        expect(card).to_contain_text("orders.csv", timeout=20000)

        # "+ Table" → a connection: its catalog beside the panel, a table there opens its page.
        wait_until(
            lambda: any(
                c["name"] == "Shop" and c["catalog_loaded"]
                for c in call(server, "GET", "/connections")["connections"]
            )
        )
        menu(workbench, "Add a table", "Shop")
        flyout = workbench.locator(".wb-flyout")
        expect(flyout).to_be_visible()
        expect(flyout.get_by_role("combobox", name="Catalog")).to_have_value("Shop")
        item = flyout.locator(".cat-tree [role=treeitem]", has_text="orders").first
        expect(item).to_be_visible(timeout=20000)
        item.click()
        expect(workbench.locator(".wb-tab[data-kind=explorer]")).to_be_visible(timeout=20000)
        expect(workbench.locator(".wb-groups").get_by_role("button", name="Open as grid")).to_be_visible()
        # Escape (or a click elsewhere) puts the catalog away; "+ Blade" shows the saved blades.
        flyout.get_by_role("searchbox", name="Search the catalog").focus()
        workbench.keyboard.press("Escape")
        expect(flyout).to_be_hidden()
        panel.get_by_role("button", name="Add a blade").click()
        expect(flyout.get_by_role("heading", name="Connections and blades")).to_be_visible()
        expect(flyout.locator(".blade-item", has_text="Shop")).to_be_visible()
        workbench.locator(".wb-status").click()  # a click elsewhere
        expect(flyout).to_be_hidden()
        workbench.close()
    finally:
        call(server, "DELETE", f"/blades/{quote('Shop')}")
        close_tables(server)


def test_the_status_bar_has_the_kernel_its_menu_the_environment_and_the_panes(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    workbench = open_workbench(browser, server)
    # Nothing open: the empty state alone, no status bar.
    expect(workbench.get_by_role("button", name="Start a notebook")).to_be_visible()
    expect(workbench.locator(".wb-status")).to_be_hidden()
    workbench.get_by_role("button", name="Start a notebook").click()
    bar = workbench.locator(".wb-status")
    expect(bar).to_be_visible()
    expect(bar.locator(".wb-state")).to_have_text("not started")
    expect(bar.get_by_role("combobox", name="Environment")).to_be_visible()
    type_cell(workbench, 0, "seen = 41 + 1\nseen")
    workbench.keyboard.press("Control+Enter")
    expect(workbench.locator(".wb-cell").first.locator(".wb-text")).to_have_text("42", timeout=60000)
    expect(bar.locator(".wb-state")).to_have_count(0)  # a ready kernel says nothing
    # The kernel's menu: Interrupt and Restart.
    bar.get_by_role("button", name="Kernel").click()
    expect(workbench.get_by_role("menu", name="Kernel").get_by_role("menuitem")).to_have_text(
        ["Interrupt", "Restart"]
    )
    workbench.get_by_role("menuitem", name="Restart").click()
    expect(workbench.locator(".toast", has_text="Restarted")).to_be_visible(timeout=30000)
    # Console and Variables open from here, and say so.
    status(workbench, "Environment")
    expect(bar.get_by_role("button", name="Environment")).to_have_attribute("aria-pressed", "true")
    expect(workbench.get_by_role("region", name="Environment", exact=True)).to_be_visible()
    status(workbench, "Console")
    expect(workbench.locator(".wb-console")).to_be_visible()
    assert window(server, "view.toggleConsole", show=False) == {"shown": False}
    expect(workbench.locator(".wb-console")).to_be_hidden()
    expect(bar.get_by_role("button", name="Console")).to_have_attribute("aria-pressed", "false")
    # No top bar (2026-11-21): the tab names the document, with a dot while it has unsaved changes.
    expect(workbench.locator(".wb-tab.dirty .wb-tab-dirty").first).to_have_text("●")
    expect(workbench.locator(".wb-tab .tab-label").first).to_have_text("Untitled notebook 1")
    workbench.close()


def test_every_action_of_the_old_toolbar_is_in_a_menu(browser: Browser, server: dict[str, Any]) -> None:
    """Where each went (2026-11-15): the top bar, a group's "+ Cell" and "…", the status bar."""
    close_tables(server)
    workbench = open_workbench(browser, server)
    workbench.get_by_role("button", name="Workbench menu").click()
    items = workbench.get_by_role("menu", name="Workbench menu").get_by_role("menuitem")
    names = [
        "New notebook",
        "Open…",
        "In this project…",
        "Split right",
        "Split down",
        "Commands…",
    ]
    for name in names:
        expect(items.filter(has_text=name)).to_have_count(1)
    expect(items.filter(has_text="New script")).to_have_count(0)  # the Scripts page's (2026-11-21)
    workbench.get_by_role("menuitem", name="New notebook").click()
    # No top bar: Save in the document's row, Save as… in its menu (Ctrl+S, Ctrl+Shift+S).
    expect(workbench.locator(".wb-gcontrols").get_by_role("button", name="Save", exact=True)).to_be_enabled()
    workbench.get_by_role("button", name="Add cell").first.click()
    expect(workbench.get_by_role("menu", name="Cell kinds").locator(".wb-menu-text")).to_have_text(
        ["Python", "SQL", "DAX", "HTML", "Markdown"]
    )
    workbench.keyboard.press("Escape")
    expect(workbench.get_by_role("button", name="Run all")).to_be_visible()
    workbench.get_by_role("button", name="Document menu").click()
    items = workbench.get_by_role("menu", name="Document menu").get_by_role("menuitem")
    for name in (
        "Clear every output",
        "Open…",
        "In this project…",
        "Save as…",
        "Interrupt",
        "Restart",
        "Split right",
        "Split down",
        "Close",
    ):
        expect(items.filter(has_text=name)).to_have_count(1)
    workbench.keyboard.press("Escape")
    start(workbench, "New script")  # on the Scripts page
    expect(workbench.get_by_role("button", name="Run file")).to_be_visible()
    # A script has no "+ Cell" (the owner, 2026-11-17: cells are a notebook's).
    expect(workbench.get_by_role("button", name="Add cell")).to_have_count(0)
    workbench.get_by_role("button", name="Document menu").click()
    expect(
        workbench.get_by_role("menu", name="Document menu").get_by_role("menuitem", name="Run statement")
    ).to_be_visible()
    workbench.keyboard.press("Escape")
    # The new tab's "+" offers what starts there: on the Scripts page, a script only.
    workbench.get_by_role("button", name="New tab").click()
    new_tab = workbench.get_by_role("menu", name="New tab")
    expect(new_tab.get_by_role("menuitem", name="New script")).to_be_visible()
    expect(new_tab.get_by_role("menuitem", name="New notebook")).to_have_count(0)
    workbench.keyboard.press("Escape")
    workbench.close()
