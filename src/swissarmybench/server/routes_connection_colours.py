"""Connection colours (services/connection_colours.py), for every page and the agent (connections_colours).

GET  /connection-colours         each connection's colour (kept or next free), each theme's, the palette
PUT  /connection-colours/{name}  {"colour": "#0e7c7b"} (null: the next free one): every window follows
POST /connection-colours/uses    {"cells": [{"kind", "source", "connection"}]}: the connections each names
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.connection_colours import ConnectionColours


def routes(colours: ConnectionColours) -> list[BaseRoute]:
    async def get(request: Request) -> Response:
        return json_response(colours.get())

    async def put(request: Request) -> Response:
        try:
            name = request.path_params["name"]
            return json_response(await colours.set(name, await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    async def uses(request: Request) -> Response:
        try:
            return json_response(colours.uses(await read_json(request)))
        except Exception as error:
            return error_response(error)

    return [
        Route("/connection-colours", get),
        Route("/connection-colours/uses", uses, methods=["POST"]),
        Route("/connection-colours/{name}", put, methods=["PUT"]),
    ]
