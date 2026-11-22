"""The agent's sandbox_* commands: the project's sandbox: the tables a local sandbox API reads and writes, Reset, checkpoints.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import command, opt, req

_SANDBOX = {
    "list": ("GET", "/sandbox"),
    "add": ("POST", "/sandbox/tables"),
    "remove": ("POST", "/sandbox/tables/remove"),
    "open": ("POST", "/sandbox/tables/open"),
    "reset": ("POST", "/sandbox/reset"),
    "baseline": ("POST", "/sandbox/baseline"),
    "checkpoint": ("POST", "/sandbox/checkpoints"),
    "restore": ("POST", "/sandbox/checkpoints/restore"),
    "variant": ("POST", "/sandbox/tables/variant"),
    "mock": ("POST", "/sandbox/tables/mock"),
    "key": ("POST", "/sandbox/tables/key"),
    "edit": ("POST", "/sandbox/edit"),
    "drop": ("POST", "/sandbox/drop"),
}


@command(
    "sandbox",
    "The project's sandbox (guide: sandbox); reset and drop (Remove the sandbox) wait for Allow",
    req("action", ", ".join(_SANDBOX) + "."),
    opt(
        "args",
        'list: {"sort": name|rows|source|created|changed, "order"}; add: {"from", ...}; variant: {"from": '
        'grid|structure, "table"|"structure", "name"?}; mock: {"table", "connection"}; key: {"table", "key": '
        'column or [columns]}; edit: {"table", "op", ...}; others: {"table"} or {"name"}.',
        "json",
    ),
)
def sandbox(a: dict[str, Any]) -> Any:
    action = str(a["action"])
    if action not in _SANDBOX:
        raise CommandError(f"action is one of: {', '.join(_SANDBOX)}.")
    method, path = _SANDBOX[action]
    given = dict(a.get("args") or {})
    if method == "GET":
        shown = {k: str(v) for k, v in given.items() if k in ("sort", "order") and v}
        return api.call(method, path + ("?" + urlencode(shown) if shown else ""), timeout=900)
    return api.call(method, path, given, timeout=900)
