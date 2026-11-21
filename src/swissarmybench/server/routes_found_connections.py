"""Find connections on this computer (services/found_connections.py): the Connections page's button.

POST  /connections/found          {"hints"?}: read the known tools and search the settings folders; the list
                                  (the agent's waits for the user's Allow)                    connections_find
POST  /connections/found/cancel   stop the running search                       connections_find {cancel}
POST  /connections/found/import   {"ids"}: the ticked rows made library connections (the agent's on Allow)
                                                                                     connections_import_found
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from swissarmybench.server.http import actor, json_response, read_body, with_body
from swissarmybench.services.found_connections import FoundConnections


def routes(found: FoundConnections) -> list[BaseRoute]:
    async def scan(request: Request) -> Response:
        raw = await read_body(request, 4096)
        body: Any = json.loads(raw) if raw.strip() else {}
        return json_response(await found.scan(body, actor(request)))

    async def cancel(request: Request) -> Response:
        return json_response(found.cancel())

    return [
        Route("/connections/found", scan, methods=["POST"]),
        Route("/connections/found/cancel", cancel, methods=["POST"]),
        Route("/connections/found/import", with_body(found.import_found), methods=["POST"]),
    ]
