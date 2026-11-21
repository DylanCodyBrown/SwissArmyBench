# ruff: noqa: F811
"""Panels turned off in Settings (the owner, 2026-11-15): gone from an open Workbench window and the
grid page at once, still gone after a reload, back when turned on. Made-up data only."""

from __future__ import annotations

import urllib.error
from typing import Any

import pandas as pd
import pytest
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_table_cells_page import close_tables, window
from tests.e2e.test_ui import browser, call, server  # noqa: F401
from tests.e2e.test_workbench_page import menu


def test_a_panel_switched_off_is_gone_from_every_window_until_switched_on(
    browser: Browser, server: dict[str, Any]
) -> None:
    close_tables(server)
    url = push_client.push(
        pd.DataFrame({"region": ["East", "West"], "amount": [10, 20]}), name="few", new_grid=True
    )
    grid = browser.new_page(viewport={"width": 1300, "height": 850})
    grid.goto(url)
    expect(grid.locator(".ribbon")).to_be_visible(timeout=20000)
    workbench = browser.new_page(viewport={"width": 1300, "height": 850})
    workbench.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}")
    expect(workbench.locator(".wb-welcome")).to_be_visible(timeout=20000)
    try:
        menu(workbench, "Workbench menu", "New notebook")
        expect(workbench.locator(".wb-status")).to_be_visible()
        expect(workbench.locator(".wb-console-toggle")).to_be_visible()
        # The Data Explorer (2026-11-17): off until opened, then beside the notebook.
        window(server, "view.explorer", show=True)
        expect(workbench.locator(".wb-explorer")).to_be_visible()
        # Settings, from the Workbench's "…": the same Settings as the grid page's, with Panels.
        menu(workbench, "Workbench menu", "Settings…")
        dialog = workbench.locator(".area-page[data-page='settings']")  # a page (2026-11-16)
        panels = dialog.locator("fieldset", has_text="Panels")
        expect(panels.locator("input[type=checkbox]")).to_have_count(
            10
        )  # the modes (2026-11-15) added six; the Data Explorer (2026-11-17) took the Data panel's three;
        # App mode's four went with app notebooks (2026-11-21)
        panels.get_by_label("Outline").uncheck()
        panels.get_by_label("Console").uncheck()
        panels.locator(".panel-page", has_text="Grid page").get_by_label("Ribbon").uncheck()
        workbench.go_back()  # the page goes; Back is how it is left (no Close)
        expect(dialog).to_have_count(0)
        # Gone at once, here and in the grid page: not folded, gone.
        expect(workbench.locator(".wb-console-toggle")).to_be_hidden()
        expect(workbench.locator(".wb-explorer")).to_be_visible()
        expect(grid.locator(".ribbon")).to_be_hidden()
        # Its command says where it went.
        with pytest.raises(urllib.error.HTTPError) as refused:
            window(server, "view.toggleConsole", show=True)
        assert "The Console is turned off in Settings" in refused.value.read().decode()
        # A reload keeps them off (the server holds them, in memory).
        workbench.reload()
        expect(workbench.locator(".wb-tab")).to_have_count(1, timeout=20000)
        expect(workbench.locator(".wb-console-toggle")).to_be_hidden()
        grid.reload()
        expect(grid.locator(".statusbar")).to_be_visible(timeout=20000)
        expect(grid.locator(".ribbon")).to_be_hidden()
        # On again, from the grid page's Settings this time.
        grid.locator(".nav-rail [data-area='settings']").click()
        grid_panels = grid.locator(".area-page[data-page='settings'] fieldset", has_text="Panels")
        expect(grid_panels.get_by_label("Console")).not_to_be_checked()
        grid_panels.get_by_label("Console").check()
        grid_panels.get_by_label("Outline").check()
        grid_panels.locator(".panel-page", has_text="Grid page").get_by_label("Ribbon").check()
        expect(grid.locator(".ribbon")).to_be_visible()
        expect(workbench.locator(".wb-console-toggle")).to_be_visible()
        assert window(server, "view.toggleConsole", show=True) == {"shown": True}
        # The others, as the agent switches them: the Data Explorer, the status bars, the steps strip.
        everything = {
            "workbench.explorer": False,
            "workbench.status": False,
            "grid.steps": False,
            "grid.status": False,
        }
        call(server, "PUT", "/panels", everything, agent=True)
        for gone in (
            workbench.locator(".wb-explorer"),
            workbench.locator(".wb-explorer-toggle"),
            workbench.locator(".wb-status"),
            grid.locator(".statusbar"),
        ):
            expect(gone).to_be_hidden()
        expect(grid.locator(".steps-strip")).to_be_hidden()
        call(server, "PUT", "/panels", dict.fromkeys(everything, True), agent=True)
        expect(workbench.locator(".wb-explorer")).to_be_visible()
        expect(grid.locator(".statusbar")).to_be_visible()
    finally:
        call(
            server,
            "PUT",
            "/panels",
            {"workbench.console": True, "workbench.outline": True, "grid.ribbon": True},
        )
        workbench.close()
        grid.close()
        close_tables(server)
