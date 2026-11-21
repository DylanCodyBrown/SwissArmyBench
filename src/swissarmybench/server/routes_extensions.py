"""The Extensions page (services/extensions.py), for the page and the agent.

GET    /extensions          every extension: preinstalled, available, installed, coming     extensions_list
POST   /extensions/install  {"id"}: Install (the app restarts; the agent waits for Allow) extensions_install
POST   /extensions/remove   {"id", "confirmed"?}: Remove (the user's asks first)             extensions_remove
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_json, safely
from swissarmybench.services.extensions import Extensions


def routes(extensions: Extensions) -> list[BaseRoute]:
    async def listing(request: Request) -> Response:
        return json_response(extensions.state())

    async def install(request: Request) -> Response:
        return json_response(await extensions.install(await read_json(request), actor(request)))

    async def remove(request: Request) -> Response:
        return json_response(await extensions.remove(await read_json(request), actor(request)))

    return [
        Route("/extensions", listing),
        Route("/extensions/install", safely(install), methods=["POST"]),
        Route("/extensions/remove", safely(remove), methods=["POST"]),
    ]
