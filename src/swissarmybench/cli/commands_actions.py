"""The agent's actions_* commands: every API's actions through api_adapter: list, run, shapes and drift, discover, build.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _q, command, opt, req

_ACTIONS = ("list", "describe", "run", "shape", "discover", "allow", "offer", "build")


@command(
    "actions",
    "Every API's actions through api_adapter, one envelope (guide: apis); a run that writes and discover wait "
    "for Allow",
    req("action", ", ".join(_ACTIONS) + "."),
    opt("api", "The API's name (the library's), or local (the project's sandbox API)."),
    opt("name", "The action's name (describe, run, shape, offer, build)."),
    opt(
        "args",
        'run: {"inputs": {...}, "required"?: [paths]}; allow: {"allow": false} (Discover\'s, taken back); offer: {"from", "to", "take": bool}; build: {"as": '
        'cell (into data.ipynb)|function ("path": its script)|widget, "inputs"?, "insert"?: false, "canvas"?, '
        '"page"?}.',
        "json",
    ),
)
def actions_command(a: dict[str, Any]) -> Any:
    action = str(a["action"])
    if action not in _ACTIONS:
        raise CommandError(f"action is one of: {', '.join(_ACTIONS)}.")
    given = dict(a.get("args") or {})
    which = {"api": a.get("api") or "", "action": a.get("name") or ""}
    if action == "list":
        return api.call("GET", "/actions" + (f"?api={_q(a['api'])}" if a.get("api") else ""))
    if action in ("describe", "shape"):
        found = api.call("GET", f"/actions/{_q(which['api'])}/{_q(which['action'])}")
        return found if action == "describe" else {k: found[k] for k in ("api", "shape", "contract")}
    if action == "discover":
        return api.call("POST", "/actions/discover", {"api": which["api"]}, timeout=900)
    if action == "allow":  # Discover's remembered Allow taken back (it is given only by the user's answer)
        return api.call("POST", "/actions/allow", {"api": which["api"], "allow": given.get("allow")})
    posted = {"run": "/actions/run", "offer": "/actions/offer", "build": "/actions/build"}
    return api.call("POST", posted[action], given | which, timeout=900)
