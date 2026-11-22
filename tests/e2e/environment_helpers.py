"""What the browser tests share about the Environment page (it took the Structures and Variables places on the
rail, 2026-11-22; the Variables page's settings and key vaults are its Settings and secrets tab)."""

from __future__ import annotations

import re
from typing import Any


def open_settings(page: Any) -> Any:
    """The settings and the key vaults, as the user reaches them: the rail's Environment, its Settings and
    secrets tab. The Environment page."""
    found = page.locator('.area-page[data-page="environment"]')
    if not found.is_visible():
        page.locator('.nav-rail [data-area="environment"]').click()
    found.get_by_role("tab", name=re.compile("^Settings and secrets")).click()
    return found


def setting_row(page: Any, name: str) -> Any:
    """A setting's row on the Settings and secrets tab."""
    return page.locator(f'.area-page[data-page="environment"] .env-row[data-name="{name}"]')


def add_setting(page: Any) -> Any:
    """Add a setting…: its form (a dialog over the page)."""
    page.locator('.area-page[data-page="environment"]').get_by_role(
        "button", name="Add a setting…"
    ).first.click()
    return page.locator("dialog .variables-form")
