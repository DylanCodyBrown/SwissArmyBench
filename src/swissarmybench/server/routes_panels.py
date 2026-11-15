"""The panels' switches in Settings (services/panels.py), for every page and the agent (app_panels).

GET  /panels   every panel: id, page, name, on
PUT  /panels   {"workbench.console": false, ...}: turn panels off or on (every window follows)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.panels import Panels


def routes(panels: Panels) -> list[BaseRoute]:
    async def get(request: Request) -> Response:
        return json_response(panels.get())

    async def put(request: Request) -> Response:
        try:
            return json_response(await panels.set(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [Route("/panels", get), Route("/panels", put, methods=["PUT"])]
