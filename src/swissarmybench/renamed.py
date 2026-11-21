"""Kept only for client/sql_cell.py, which still imports `env` from here: that file is the adapter branch's
and is left alone until it merges, then this module goes. The old SwissArmyGrid names are no longer read.

Standard library only: the plain client uses it.
"""

from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    """An environment variable by its name (SWISSARMYBENCH_X)."""
    return os.environ.get(name, default)
