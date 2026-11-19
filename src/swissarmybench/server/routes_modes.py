"""Project modes (services/modes.py), for every page and the agent (app_mode).

GET  /app/mode    the open project's type and its mode (canvases, families, languages, cell kinds, tools,
                  export); `needs`: the extension its type names that is not on here
GET  /app/modes   every project type this app can make: the base's, then each on extension's
GET  /app/gates   the features a project type keeps closed, Open every feature, the first-open pop-up
                 (POST {every} or {seen})
GET  /app/areas   the rail's areas the on extensions add, each with the footer's mark route it may answer
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.modes import Modes


def routes(modes: Modes) -> list[BaseRoute]:
    async def active(request: Request) -> Response:
        return json_response(modes.active())

    async def every(request: Request) -> Response:
        return json_response({"modes": modes.all()})

    async def areas(request: Request) -> Response:
        return json_response({"areas": modes.areas()})

    async def gates(request: Request) -> Response:
        return json_response(modes.gates())

    return [
        Route("/app/mode", active),
        Route("/app/modes", every),
        Route("/app/areas", areas),
        Route("/app/gates", gates),
        Route("/app/gates", with_body(modes.set_gates), methods=["POST"]),
    ]
