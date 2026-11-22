"""What the browser tests share about the Environment page (it took the Structures and Variables places on the
rail, 2026-11-22)."""

from __future__ import annotations

import re
from typing import Any


def open_variables(page: Any) -> None:
    """The settings' and key vaults' page (open=variables), as the user reaches it: the rail's Environment,
    its Settings and secrets tab, Key vaults and more…."""
    page.locator('.nav-rail [data-area="environment"]').click()
    found = page.locator('.area-page[data-page="environment"]')
    found.get_by_role("tab", name=re.compile("^Settings and secrets")).click()
    found.get_by_role("button", name="Key vaults and more…").click()
