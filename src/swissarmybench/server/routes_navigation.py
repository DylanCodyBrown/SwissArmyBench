"""Getting around (services/navigation.py), for the agent (app_navigate): the pages move themselves.

POST /navigate   {"to": "home" | "back" | "forward" | a view, "window": "home" | "catalog" | "workbench"}
GET  /rail       {"labels": true}: the rail shows its names (false: icons only)
PUT  /rail       {"labels": false}: every window follows (rail_changed); kept in rail.json
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.navigation import Navigation


def routes(navigation: Navigation) -> list[BaseRoute]:
    async def go(request: Request) -> Response:
        try:
            return json_response(await navigation.go(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def rail(request: Request) -> Response:
        return json_response(navigation.rail())

    async def set_rail(request: Request) -> Response:
        try:
            return json_response(await navigation.set_rail(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/navigate", go, methods=["POST"]),
        Route("/rail", rail),
        Route("/rail", set_rail, methods=["PUT"]),
    ]
