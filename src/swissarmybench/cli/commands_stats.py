"""The agent's stats_* commands: every call's statistics: times, sizes and outcomes per table, connection and endpoint; hints.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt


@command(
    "stats",
    "Every call's statistics: time, size, outcome (never a value). "
    "Every call's statistics (connections' reads, queries and writes; APIs' actions): time in parts (wait in "
    "line, connect, first row or byte, total), size, folded vs DuckDB, outcome, who and where, the shape's "
    "fingerprint; the running figures per table, connection and endpoint; hints. Never a value",
    opt("action", "summary (default), slowest, errors, table, connection, endpoint or hints."),
    opt("name", "The table (Connection.table), connection or endpoint (API action) for those views."),
    opt("n", "How many calls (default 20).", "int"),
)
def stats(a: dict[str, Any]) -> Any:
    return api.call("GET", "/stats", params={k: a.get(k) for k in ("action", "name", "n")})
