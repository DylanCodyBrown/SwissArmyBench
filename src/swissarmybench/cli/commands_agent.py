"""The agent's agent_* commands: what only the agent has: the table in front, the inbox, approvals, live events.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt


@command(
    "agent_context",
    "The table in front of the user now, its columns, steps and selection; plus the other open tables.",
)
def current_table(a: dict[str, Any]) -> Any:
    return api.call("GET", "/agent/context")


@command(
    "agent_approvals",
    "Exports waiting for the user's click. Only the user resolves them.",
)
def list_approvals(a: dict[str, Any]) -> Any:
    return api.call("GET", "/agent/approvals")


@command(
    "agent_events",
    "Wait for live events (the user changed a table, opened a table, an approval was asked...) and return them. "
    "Types: grid_updated, grid_shown, grid_closed, dataset_updated, dataset_closed, cards_updated, "
    "relationships_updated, approval_requested, approval_resolved, processes_changed.",
    opt("types", "Only these event types.", "list"),
    opt("seconds", "How long to wait at most (default 30, up to 120).", "int"),
    opt("limit", "Return after this many events (default 1).", "int"),
)
def events(a: dict[str, Any]) -> Any:
    seconds = max(1, min(int(a.get("seconds") or 30), 120))
    limit = max(1, min(int(a.get("limit") or 1), 200))
    types = set(a["types"]) if a.get("types") else None
    found = api.collect_events(types, float(seconds), limit)
    return {"events": found, "waited_for": sorted(types) if types else "any"}


@command(
    "agent_inbox",
    "What the user sent you from the Workbench (right-click an error or code, Send to the agent): "
    "errors with their place, values and traceback, or code, each with the user's question if any",
    opt("all", "Also the ones already read (default: only the waiting ones, which this marks read).", "bool"),
)
def agent_inbox(a: dict[str, Any]) -> Any:
    every = "&all=1" if a.get("all") else ""
    return api.call("GET", f"/agent/inbox?take=1{every}")
