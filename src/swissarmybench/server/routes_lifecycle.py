"""The server's life (services/lifecycle.py): it runs while the app is open.

GET    /lifecycle          windows open, the last client, busy, held, seconds until it stops   app_lifecycle
POST   /lifecycle/closed   the desktop app closed its last window: stop once nothing else holds  (the app's)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import json_response
from swissarmybench.services.lifecycle import Lifecycle


def routes(lifecycle: Lifecycle) -> list[BaseRoute]:
    async def state(request: Request) -> Response:
        return json_response(lifecycle.state())

    async def closed(request: Request) -> Response:
        return json_response(lifecycle.closed())

    return [
        Route("/lifecycle", state),
        Route("/lifecycle/closed", closed, methods=["POST"]),
    ]
