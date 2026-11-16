"""Updates (services/updates.py), for the pages, the tray and the agent.

GET    /updates           the current version, the latest, whether one is available      app_update_check
PUT    /updates           {"check": false}: Settings' Check for updates (kept)            app_update_check on=
POST   /updates/check     check now (nothing is sent with the switch off)          app_update_check now=
POST   /updates/install   {"version"?, "confirmed"?}: Update to X (the agent's asks)   app_update
GET    /updates/tray      the tray's menu: the update, the open tables and documents (tray plumbing)
GET    /autostart         start at sign-in: on or off, and where its entry is                app_autostart
PUT    /autostart         {"on": false}: the tray's switch, `autostart on|off`              app_autostart on=
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.renamed import env
from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.updates import Updates


def edition() -> str:
    """The app's edition: "lite" (Swiss Army Bench Lite) or "full"."""
    return "lite" if env("SWISSARMYBENCH_EDITION").strip().lower() == "lite" else "full"


def routes(updates: Updates) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        # The edition, for the app's name in the status bar: "lite" for Swiss Army Bench Lite (its installer
        # sets SWISSARMYBENCH_EDITION), else the full app.
        return json_response(updates.state() | {"edition": edition()})

    async def switch(request: Request) -> Response:
        try:
            return json_response(await updates.set(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def check(request: Request) -> Response:
        return json_response(await updates.check())

    async def install(request: Request) -> Response:
        try:
            body = await read_json(request) if await request.body() else {}
            return json_response(await updates.install(body, actor(request)))
        except Exception as error:
            return error_response(error)

    async def tray(request: Request) -> Response:
        return json_response(await updates.tray())

    async def autostart(request: Request) -> Response:
        try:
            return json_response(updates.autostart())
        except Exception as error:
            return error_response(error)

    async def set_autostart(request: Request) -> Response:
        try:
            return json_response(updates.set_autostart(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/updates", state),
        Route("/updates", switch, methods=["PUT"]),
        Route("/updates/check", check, methods=["POST"]),
        Route("/updates/install", install, methods=["POST"]),
        Route("/updates/tray", tray),
        Route("/autostart", autostart),
        Route("/autostart", set_autostart, methods=["PUT"]),
    ]
