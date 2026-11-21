"""Updates (services/updates.py), for the pages and the agent.

GET    /updates           the current version, the latest, whether one is available      app_update_check
PUT    /updates           {"check": false}: Settings' Check for updates (kept)            app_update_check on=
POST   /updates/check     check now (nothing is sent with the switch off)          app_update_check now=
POST   /updates/install   {"version"?, "confirmed"?}: Update to X (the agent's asks)   app_update
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely, with_body
from swissarmybench.services.updates import Updates

# The app's name in the status bar (the owner, 2026-11-17: "It's not an edition now it's the streamlit
# extension. Preinstalled"). The backend says it; the page shows what it is told, with the installed
# extensions in its tooltip. The package, the uv tool and the commands keep their names (swissarmybench, sab).
APP_NAME = "Swiss Army Bench"


def routes(updates: Updates, extensions: Callable[[], list[str]] = list) -> list[BaseRoute]:
    """`extensions`: the installed extensions' names (the version mark's tooltip)."""

    def named() -> dict[str, object]:
        return {"name": APP_NAME, "extensions": extensions()}

    async def state(request: Request) -> Response:
        return json_response(updates.state() | named())

    async def check(request: Request) -> Response:
        # {"asked": true}: the user's button (or the agent's now) checks even with the switch off.
        body = await read_json(request) if await request.body() else {}
        asked = isinstance(body, dict) and body.get("asked") is True
        return json_response(await updates.check(asked=asked) | named())

    async def install(request: Request) -> Response:
        body = await read_json(request) if await request.body() else {}
        return json_response(await updates.install(body, actor(request)))

    return [
        Route("/updates", state),
        Route("/updates", with_body(updates.set), methods=["PUT"]),
        Route("/updates/check", check, methods=["POST"]),
        Route("/updates/install", safely(install), methods=["POST"]),
    ]
