"""Shared by the Workbench's browser tests (they were the old Streamlit page test's): the Workbench window by
its address, a screenshot when SWISSARMYBENCH_SHOTS names a folder, made-up orders open in a grid, a saved
notebook with its Python."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect

from swissarmybench.client import push_client
from swissarmybench.renamed import env
from tests.e2e.test_table_cells_page import close_tables
from tests.e2e.test_ui import call

LONG = 60000  # Streamlit's first start, in milliseconds
SHOTS = env("SWISSARMYBENCH_SHOTS") or None
ORDERS = pd.DataFrame(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [100, 250, 40, 75, 10, 5],
    }
)


def open_window(browser: Browser, server: dict[str, Any], path: Path | None = None) -> Page:
    """The Workbench window by its address (with a file to open), in a browser context of its own."""
    context = browser.new_context(
        viewport={"width": 1500, "height": 950}, device_scale_factor=2 if SHOTS else 1
    )
    page = context.new_page()
    opened = f"&open={quote(str(path))}" if path else ""
    page.goto(f"http://127.0.0.1:{server['port']}/workbench#token={server['token']}{opened}")
    expect(page.locator(".wb-tab" if path else ".wb-welcome").first).to_be_visible(timeout=20000)
    return page


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.wait_for_timeout(400)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.fixture
def orders(server: dict[str, Any]) -> Iterator[str]:
    close_tables(server)
    url = push_client.push(ORDERS, name="orders", new_grid=True)
    yield url.rsplit("/g/", 1)[1].split("#")[0]
    close_tables(server)


def saved_notebook(server: dict[str, Any], path: Path, python: str | None, sources: list[str]) -> None:
    """A saved notebook of Python cells whose environment is `python` (None: this app's own)."""
    cells = [{"kind": "code", "source": source} for source in sources]
    call(server, "POST", "/workbench/save", {"path": str(path), "cells": cells})
    if python:
        call(server, "POST", "/workbench/environment", {"path": str(path), "python": python})
