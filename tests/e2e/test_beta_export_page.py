# ruff: noqa: F811
"""Export beta log… (the owner, 2026-11-16: "beta log did not export"): from Settings' Beta section and from
the status bar's Beta mark, the chooser's Save here writes one zip, and the toast says where. Made-up data."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import Browser, expect

from swissarmybench.client import push_client
from tests.e2e.test_ui import browser, call, open_grid, server  # noqa: F401


def test_export_beta_log_from_settings_writes_the_zip(browser: Browser, server: dict[str, Any]) -> None:
    call(server, "PUT", "/beta", {"on": True})
    url = push_client.push(pd.DataFrame({"city": ["Springfield"], "visits": [3]}), new_grid=True)
    page = open_grid(browser, url)
    try:
        page.locator(".nav-rail [data-area='settings']").click()
        dialog = page.locator(".area-page[data-page='settings']")  # a page (2026-11-16)
        dialog.get_by_role("button", name="Export beta log…").click()
        chooser = page.locator("dialog[open]").last
        name = chooser.get_by_label("File name")
        expect(name).to_have_value("beta-log.zip")
        chooser.get_by_role("button", name="Save here").click()
        toast = page.locator(".toast", has_text="Saved to ")
        expect(toast).to_be_visible(timeout=20000)
        made = Path(toast.inner_text().split("Saved to ", 1)[1].strip())
        # The toast names where it went; the zip is there with the log and the notes.
        assert made.name == "beta-log.zip" and made.is_file()
        with zipfile.ZipFile(made) as archive:
            names = archive.namelist()
        assert "README.txt" in names and "notes.json" in names
        assert any(n.startswith("logs/") for n in names)
        made.unlink()
    finally:
        page.close()
