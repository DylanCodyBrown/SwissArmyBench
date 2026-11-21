"""Getting around (services/navigation.py), for the agent (app_navigate): the pages move themselves.

POST /navigate   {"to": "home" | "back" | "forward" | a view, "window": "home" | "catalog" | "workbench"}
GET  /rail       {"labels": true}: the rail shows its names (false: icons only)
PUT  /rail       {"labels": false}: every window follows (rail_changed); kept in rail.json
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response, with_body
from swissarmybench.services.navigation import Navigation


def routes(navigation: Navigation) -> list[BaseRoute]:
    async def rail(request: Request) -> Response:
        return json_response(navigation.rail())

    return [
        Route("/navigate", with_body(navigation.go), methods=["POST"]),
        Route("/rail", rail),
        Route("/rail", with_body(navigation.set_rail), methods=["PUT"]),
    ]
