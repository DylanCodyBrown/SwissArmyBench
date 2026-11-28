"""The agent's api_* commands: the project's local sandbox API (API.py): run it, call it, export it for its target.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import command, opt, req

_API = {
    "state": ("GET", "/local-api"),
    "new": ("POST", "/local-api/new"),
    "settings": ("PUT", "/local-api/settings"),
    "run": ("POST", "/local-api/run"),
    "stop": ("POST", "/local-api/stop"),
    "call": ("POST", "/local-api/call"),
    "writes": ("POST", "/local-api/agent-writes"),
    "log": ("GET", "/local-api/log"),
    "address": ("GET", "/local-api/address"),
    "openapi": ("GET", "/local-api/openapi.json"),
    "targets": ("GET", "/local-api/targets"),
    "export": ("POST", "/local-api/export"),
    "scaffold": ("POST", "/local-api/scaffold"),
    "patterns": ("GET", "/local-api/patterns"),
    "plan": ("POST", "/local-api/plan"),
    "check": ("POST", "/local-api/check"),
    "shapes": ("GET", "/local-api/shapes"),
}


@command(
    "api",
    "The project's local sandbox API, API.py (guide: sandbox). The first write call waits for Allow "
    "(it covers the session)",
    req(
        "action",
        "state, new, settings, run, stop, call, writes, log, address, openapi, targets, export, patterns, "
        "plan, scaffold, check, shapes.",
    ),
    opt(
        "args",
        "The action's arguments, an object (guide: sandbox). "
        'state: {"full": true} adds the OpenAPI document; call: {"method", "path", "query"?, "body"?}; '
        'writes: {"allow": bool} (the agent writing this session); settings: {"name", '
        '"target", "base_path"}; plan: {"table", "pattern"?, "fields"?, "other"?} (the patterns ranked for '
        'the table, a pattern\'s steps and its code; writes nothing); scaffold: {"table", "pattern": table|'
        'choices|search|summary|bulk|action|versions|reconcile|export, "fields"?, "other"?, "dry_run"?} '
        "(its endpoints appended to API.py; dry_run: the code only).",
        "json",
    ),
)
def api_command(a: dict[str, Any]) -> Any:
    action = str(a["action"])
    if action == "example":
        raise CommandError(
            "Keep as its example went (2026-11-22): no value is kept. Try it starts from the endpoint's "
            "learned shape: api(state) gives each endpoint's `try`."
        )
    if action not in _API:
        raise CommandError(f"action is one of: {', '.join(_API)}.")
    method, path = _API[action]
    given = dict(a.get("args") or {})
    if action == "state" and given.get("full"):
        path += "?full=true"  # its OpenAPI document too (brief without it)
    return api.call(method, path, None if method == "GET" else given, timeout=900)
