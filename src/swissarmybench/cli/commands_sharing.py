"""The agent's sharing_* commands: share a running app with your organization (Microsoft Dev Tunnels).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import command, opt, req


@command(
    "sharing_status",
    "Shared apps: devtunnel, sign-in, each share's link. "
    "Shared apps (Dev Tunnels, organization only): devtunnel installed, signed in, each share's state and link",
    opt("app", "An app's id: its share only."),
    opt("kind", "streamlit (default)."),
)
def sharing_status(a: dict[str, Any]) -> Any:
    query = (
        f"?kind={quote(str(a.get('kind') or 'streamlit'))}&app={quote(str(a['app']))}" if a.get("app") else ""
    )
    return api.call("GET", "/sharing" + query)


@command(
    "sharing_start",
    "Share a launched app with the organization (on Allow). "
    "Share a launched app with the organization (sign-in is the user's); waits for Allow",
    req("app", "The app's id (a canvas's)."),
    opt("kind", "streamlit (default)."),
)
def sharing_start(a: dict[str, Any]) -> Any:
    body = {"kind": a.get("kind") or "streamlit", "app": a["app"]}
    return api.call("POST", "/sharing/start", body, timeout=900)


@command(
    "sharing_stop",
    "Stop sharing an app (on Allow). Stop sharing an app (its link ends); waits for Allow",
    req("app", "The app's id."),
    opt("kind", "streamlit (default)."),
)
def sharing_stop(a: dict[str, Any]) -> Any:
    return api.call("POST", "/sharing/stop", {"kind": a.get("kind") or "streamlit", "app": a["app"]})
