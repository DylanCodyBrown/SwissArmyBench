"""Kind colours in Settings (services/kind_colours.py), for every page and the agent (app_kind_colours).

GET  /kind-colours   each kind: its chosen colour (null: the theme's own) and the colour each theme shows
PUT  /kind-colours   {"app": "#7b3fc4", "script": null}: choose (every window follows; kept across restarts)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, error_response, json_response, read_json
from swissarmybench.services.kind_colours import KindColours


def routes(colours: KindColours) -> list[BaseRoute]:
    async def get(request: Request) -> Response:
        return json_response(colours.get())

    async def put(request: Request) -> Response:
        try:
            return json_response(await colours.set(await read_json(request), actor(request)))
        except Exception as error:
            return error_response(error)

    return [Route("/kind-colours", get), Route("/kind-colours", put, methods=["PUT"])]
