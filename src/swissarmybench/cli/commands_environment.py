"""The agent's environment_* commands: the Environment: everything the project holds, where each is used, its libraries.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import command, opt, req

_ENVIRONMENT = {
    "list": ("GET", "/environment"),
    "show": ("GET", "/environment/show"),
    "libraries": ("GET", "/environment/libraries"),
    "open": ("POST", "/environment/open"),
    "rename": ("POST", "/environment/rename"),
    "keep": ("POST", "/environment/keep"),
    "insert": ("POST", "/environment/insert"),
    "remove": ("POST", "/environment/remove"),
    "clear": ("POST", "/environment/clear"),
    "install": ("POST", "/environment/libraries/install"),
    "update": ("POST", "/environment/libraries/update"),
    "pin": ("POST", "/environment/libraries/pin"),
    "python": ("GET", "/environment/python"),
    "set_python": ("POST", "/environment/python"),
}


_ENVIRONMENT_ASKS = {"list": ("search",), "show": ("kind", "name"), "libraries": ("check",), "python": ()}


@command(
    "environment",
    "Everything the project holds: tables, variables, structures, settings and secrets, libraries, each "
    "with where it is used (guide: environment); clear, keep, install, update, pin and a file's delete "
    "wait for Allow",
    req("action", ", ".join(_ENVIRONMENT) + "."),
    opt(
        "args",
        'list: {"search"}; show, open, insert: {"kind": table|variable|structure|setting|library, "name"}; '
        'rename: + {"to"}; remove: + {"python": true} (a table: also delete it in Python); keep: {"name", '
        '"keep"}; clear: {"tables", "variables", "structures", "dry_run"}; libraries: {"check": true} (ask '
        'the index); install: {"name"} or {"names": [...]}; update: {"name"} or {"all": true}; pin: {"name", '
        '"pinned"}; python: the project\'s own Python (.venv: making, ready, failed), its one session, a '
        'notebook\'s older environment offered; set_python: {"make": true} or {"offer": document, "add"}.',
        "json",
    ),
)
def environment(a: dict[str, Any]) -> Any:
    action = str(a["action"])
    if action not in _ENVIRONMENT:
        raise CommandError(f"action is one of: {', '.join(_ENVIRONMENT)}.")
    method, path = _ENVIRONMENT[action]
    given = dict(a.get("args") or {})
    if method == "GET":
        asked = {k: str(given[k]) for k in _ENVIRONMENT_ASKS[action] if given.get(k) not in (None, "", False)}
        if action == "libraries" and "check" in asked:
            asked["check"] = "1"
        return api.call(method, path + ("?" + urlencode(asked) if asked else ""), timeout=120)
    answer = api.call(method, path, given, timeout=900)
    link = answer.get("link") if action == "open" and isinstance(answer, dict) else None
    if isinstance(link, dict):  # shown in the app as well: a table's grid, else the Environment page
        to = f"grid:{link['grid']}" if link.get("to") == "grid" else "environment"
        api.call("POST", "/navigate", {"to": to})
    return answer
