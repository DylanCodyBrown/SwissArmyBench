"""The agent's changes_* commands: the open project's change log: the last change to an object, its history, since a time.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt


@command(
    "changes",
    "The open project's change log: each change to a table (columns, source, steps), a connection, an API or "
    "an endpoint's learned shape, API.py, a widget, a canvas page, a notebook or script, a variable or setting: "
    "when, who, what in words and as a difference by name, fingerprints before and after. Never a value",
    opt("action", "last (default: the object's last change), history, since or search."),
    opt(
        "object", "kind:name (table:orders, endpoint:Shop list_orders) or a name alone, for last and history."
    ),
    opt("n", "How many (default 20).", "int"),
    opt("since", "An ISO time, for since (e.g. when you last looked)."),
    opt(
        "kind", "For search: table, connection, api, endpoint, widget, canvas, notebook, script, variable..."
    ),
    opt("who", "For search: user, agent or app."),
    opt("word", "For search: a word in the change's words."),
)
def changes(a: dict[str, Any]) -> Any:
    keys = ("action", "object", "n", "since", "kind", "who", "word")
    return api.call("GET", "/changes", params={k: a.get(k) for k in keys})
