"""Shared by the Widgets window's and the Canvas's browser tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def until(read: Callable[[], Any], wanted: Any, seconds: float = 15.0) -> None:
    """The server holds what the page wrote (a change made in the page reaches it a moment later)."""
    end = time.monotonic() + seconds
    seen = read()
    while seen != wanted and time.monotonic() < end:
        time.sleep(0.2)
        seen = read()
    assert seen == wanted
