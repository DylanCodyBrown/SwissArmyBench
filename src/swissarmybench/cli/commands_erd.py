"""The agent's erd_* commands: eRD tab.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import SCOPE, _q, command, opt, req


@command(
    "erd_text",
    "The ERD as Mermaid text: the tables the open project uses (or all; no project open: the open tables)",
    opt("tables", "Comma-separated dataset names."),
    SCOPE,
)
def erd(a: dict[str, Any]) -> Any:
    return api.call("GET", "/relationships/erd", params={"tables": a.get("tables"), "scope": a.get("scope")})


@command(
    "erd_draw",
    "Draw the relationship model as a diagram card in Analyze.",
    req("grid", "The open table the card is filed with (its id)."),
    opt("tables", "Comma-separated dataset names."),
    opt("title", "Card title (default Relationships)."),
    SCOPE,
)
def add_erd(a: dict[str, Any]) -> Any:
    drawn = api.call("GET", "/relationships/erd", params={"tables": a.get("tables"), "scope": a.get("scope")})
    card = api.call(
        "POST",
        f"/grids/{_q(a['grid'])}/cards",
        {"kind": "diagram", "title": a.get("title") or "Relationships", "body": drawn["mermaid"]},
    )
    return {"card": card["card"], "tables": drawn["tables"]}
