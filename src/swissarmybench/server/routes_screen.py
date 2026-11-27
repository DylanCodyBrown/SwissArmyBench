"""The screen state for the agent (services/screen.py): what each window shows, read from memory.

  GET /screen                 every window in brief, the focused one first
  GET /screen/{window}        one window in full: its id (w1), `focused`, or its kind (tables, scripts...)

The pages report over their live socket (/ws, server/app.py): there is no route to report by, so nothing but
a window says what a window shows.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response
from swissarmybench.services.screen import Screens


def routes(screens: Screens) -> list[BaseRoute]:
    async def every(request: Request) -> Response:
        return json_response(screens.read())

    async def one(request: Request) -> Response:
        return json_response(screens.read(request.path_params["window"]))

    return [
        Route("/screen", every, methods=["GET"]),
        Route("/screen/{window}", one, methods=["GET"]),
    ]
